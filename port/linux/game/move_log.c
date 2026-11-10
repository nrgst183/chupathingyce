/*
MOVE_LOG.C

debug.move_log (HALO_MOVE_LOG): this copy's own players' movement written
down, for working out how a person gets about a map: how a crouch jump is
timed, how high it gets the feet and what it costs of the run, which ways
across a map people take that the bots' navigation has no way for, and how
long the ways take against what the navigation reckons, to teach the bots
(bot_move.c, bot_aas.c). The navigation is built for the map when this is on,
bots or none (bots.c), so the areas can be named.

logs/move_log.csv, a line a tick for each local player (game.c calls in after
players_update_after_game), from the game's state after the tick:
  tick, player, map
  vehicle: the vehicle ridden ("-" on foot), and seat: d driving, g on a gun,
    p riding (the position and velocity are then the vehicle's)
  x y z: the feet (the unit's origin); vx vy vz: units a second; ground_speed
  yaw: the way the body faces; aim_yaw, aim_pitch: the way it looks;
    move_yaw: the way it is going; strafe: going against facing (0 straight
    on, +-1.57 sideways, +-3.14 backwards)
  stick_forward, stick_left; buttons: the unit's control flags (hex: 1 crouch,
    2 jump, 40 action, 400 reload, 800 trigger, 1000 second trigger, 2000
    grenade, 4000 swap); jump, crouch_held; crouch: how far crouched (0 .. 1)
  airborne, airborne_ticks; slope: the up of the floor stood on (1 flat)
  floor: the floor under the feet, how far down (0 stood on it; empty: none
    within 6)
  ahead_05 .. ahead_20: the floor half a unit to two units ahead, the way it
    is going (or facing, standing), against the feet (+ higher; empty none
    within 3 down)
  wall_knee, wall_chest: how far ahead the first wall is, at the knee and the
    chest (3: none within 3)
  area: the navigation's area the feet are in (-1 none)
  health, shield, weapon, zoom

logs/move_jumps.txt, a line for each time the feet leave the ground and come
down again: where and how fast it left, the ledge before it then (how far off
its lip, how high), when crouch went down and came up against the tick it
left, how high the feet went and how much the crouch lifted them, how near the
ledge's top the feet went over it, where it came down (above or below, how far
across, the floor's slope), the speeds (landing, slowest in the air, half a
second and a second on), the areas it left and came down in and whether the
navigation has a way between them, and its time for the way against the
jump's.

logs/move_routes.txt: the ways about the map. "unknown": a move from one
area to another the navigation has no way for (a jump, a drop, a walk), with
the navigation's time for it by the ways it knows; every three seconds on
foot, "pace": how far it went and the navigation's time for the same, the two
to set the navigation's reckoning by; and "teleport".

Also in debug.txt, as "move:" lines (the jumps and the unknown ways).
Nothing is written unless it is asked for. The files are added to, every map
and every time the game starts, and each line names the map: delete them to
begin again.
*/

#include "cseries.h"
#include "game/game.h"
#include "game/players.h"
#include "main/main.h"
#include "objects/objects.h"
#include "tag_files/tag_files.h"
#include "units/bipeds.h"
#include "units/units.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../src/port_folders.h"
#include "bot_internal.h"

int config_boolean(char const *name);
const char *platform_folder(enum port_folder folder);
void platform_log(char const *format, ...);

void move_log_tick(void);
boolean move_log_wanted(void);

#define MOVE_LOG_PLAYERS 4
#define MOVE_LOG_AFTER 30 /* ticks after a landing the speed is watched for */
#define MOVE_LOG_PACE 90 /* ticks a pace line is over */
#define MOVE_LOG_NO_FLOOR 99.f

struct move_jump
{
	int on; /* 1 in the air, 2 down and being watched */
	long left_tick;
	real_point3d left_at;
	real left_speed;
	long left_area;
	real lip_off, lip_up; /* the ledge ahead as it left (lip_off <0: none) */
	long crouch_on; /* the tick crouch went down, from the tick it left (NONE: never) */
	long crouch_off;
	long crouch_before; /* crouch was held when it left the ground */
	long crouched_ticks; /* ticks in the air with the body crouched at all */
	real highest;
	real lift; /* the most the feet went up in one tick from crouching */
	long lift_tick;
	real over_lip; /* the least the feet were above the floor under them where that floor was the ledge's top (MOVE_LOG_NO_FLOOR: never over it) */
	long landed_tick;
	real_point3d landed_at;
	real landed_speed;
	real landed_slope;
	long landed_area;
	real slowest;
	real speed_half;
	real speed_second;
	long jumps; /* jump presses while in the air */
};

struct move_player
{
	long unit_index;
	int was_airborne;
	real was_z;
	real_point3d was_at;
	real was_crouch;
	int was_crouch_held;
	int was_jump_held;
	long ground_area; /* the area last stood in, and where, and when */
	real_point3d ground_at;
	long ground_tick;
	real_point3d pace_at;
	long pace_tick;
	struct move_jump jump;
};

static struct
{
	int asked;
	int on;
	long watched;
	FILE *ticks;
	FILE *jumps;
	FILE *routes;
	long jump_count;
	struct move_player players[MOVE_LOG_PLAYERS];
} move_log;

static char const *move_log_map(void)
{
	char const *name = main_get_multiplayer_map_name();
	return name && *name ? name : main_get_map_name();
}

static char const *move_log_short_name(long definition_index)
{
	char const *name = definition_index != NONE ? tag_get_name(definition_index) : NULL;
	char const *last;
	if (!name)
		return "-";
	last = strrchr(name, '\\');
	return last ? last + 1 : name;
}

static real move_log_ground_speed(real_vector3d const *velocity)
{
	return (real)sqrt(velocity->i * velocity->i + velocity->j * velocity->j) * TICKS_PER_SECOND;
}

static FILE *move_log_file(char const *folder, char const *name)
{
	char path[512];
	snprintf(path, sizeof(path), "%s/%s", folder, name);
	return fopen(path, "a");
}

boolean move_log_wanted(void)
{
	return config_boolean("debug.move_log");
}

static void move_log_open(void)
{
	char folder[400];
	move_log.asked = TRUE;
	move_log.on = move_log_wanted();
	move_log.watched = getenv("HALO_MOVE_LOG_PLAYER") ? atol(getenv("HALO_MOVE_LOG_PLAYER")) : NONE;
	if (!move_log.on)
		return;
	/* (in the logs folder, beside debug.txt; where that cannot be written,
	   the folder the game was started in) */
	snprintf(folder, sizeof(folder), "%s", platform_folder(_port_folder_logs));
	move_log.ticks = move_log_file(folder, "move_log.csv");
	if (!move_log.ticks)
	{
		snprintf(folder, sizeof(folder), ".");
		move_log.ticks = move_log_file(folder, "move_log.csv");
	}
	move_log.jumps = move_log_file(folder, "move_jumps.txt");
	move_log.routes = move_log_file(folder, "move_routes.txt");
	/* (added to, not begun afresh: a game started again, for another map,
	   keeps what the last one wrote. The heading once, at the top of a new
	   file) */
	if (move_log.ticks)
		fseek(move_log.ticks, 0, SEEK_END);
	if (move_log.ticks && ftell(move_log.ticks) == 0)
		fprintf(move_log.ticks, "tick,player,map,vehicle,seat,x,y,z,vx,vy,vz,ground_speed,yaw,aim_yaw,aim_pitch,move_yaw,strafe,"
			"stick_forward,stick_left,buttons,jump,crouch_held,crouch,airborne,airborne_ticks,slope,floor,"
			"ahead_05,ahead_10,ahead_15,ahead_20,wall_knee,wall_chest,area,health,shield,weapon,zoom\n");
	platform_log("move: logging the movement of this copy's players to %s/move_log.csv, move_jumps.txt and move_routes.txt%s", folder,
		move_log.ticks && move_log.jumps && move_log.routes ? "" : " (could not open them all)");
}

/* the floor under a point, how far down (MOVE_LOG_NO_FLOOR: none within depth) */
static real move_log_floor(real_point3d const *at, real up, real depth, long ignore)
{
	real_point3d from = *at;
	real ground;
	from.z += up;
	if (!bot_ground(&from, depth + up, ignore, &ground))
		return MOVE_LOG_NO_FLOOR;
	return at->z - ground;
}

static long move_log_area(real_point3d const *at, boolean airborne)
{
	if (!aas_ready())
		return NONE;
	return airborne ? aas_point_area(AAS_FOOT, at) : aas_standing_area(AAS_FOOT, at);
}

/* the navigation's way from one area to another, directly: the kind of the
   first it has (_aas_travel_*), or NONE */
static long move_log_direct_way(long from, long to)
{
	struct aas_area const *area;
	long r;
	if (!aas_ready() || from == NONE || to == NONE)
		return NONE;
	if (from == to)
		return _aas_travel_walk;
	area = aas_area(AAS_FOOT, from);
	for (r = area->first_reach; r < area->first_reach + area->reach_count; r++)
		if (aas_reach(AAS_FOOT, r)->to == to)
			return aas_reach(AAS_FOOT, r)->travel;
	return NONE;
}

static char const *move_log_travel_name(long travel)
{
	switch (travel)
	{
	case _aas_travel_walk: return "a walk";
	case _aas_travel_jump: return "a jump up";
	case _aas_travel_drop: return "a drop";
	case _aas_travel_gap: return "a gap";
	case _aas_travel_ladder: return "a ladder";
	case _aas_travel_teleport: return "a teleporter";
	}
	return "none";
}

static void move_log_line(FILE *file, char const *line)
{
	if (file)
	{
		fprintf(file, "%s\n", line);
		fflush(file);
	}
}

static void move_log_jump_done(short local, struct move_jump const *jump)
{
	char line[1200];
	char crouch[128];
	char lip[96];
	char over[48];
	char nav[192];
	real across = (real)sqrt((jump->landed_at.x - jump->left_at.x) * (jump->landed_at.x - jump->left_at.x) +
		(jump->landed_at.y - jump->left_at.y) * (jump->landed_at.y - jump->left_at.y));
	long way = move_log_direct_way(jump->left_area, jump->landed_area);
	if (jump->crouch_before)
		snprintf(crouch, sizeof(crouch), "crouched as it left");
	else if (jump->crouch_on != NONE)
		snprintf(crouch, sizeof(crouch), "crouch at tick %ld", jump->crouch_on);
	else
		snprintf(crouch, sizeof(crouch), "no crouch");
	if (jump->crouch_on != NONE)
	{
		if (jump->crouch_off != NONE)
			snprintf(crouch + strlen(crouch), sizeof(crouch) - strlen(crouch), ", let go at tick %ld", jump->crouch_off);
		else
			snprintf(crouch + strlen(crouch), sizeof(crouch) - strlen(crouch), ", held down");
		snprintf(crouch + strlen(crouch), sizeof(crouch) - strlen(crouch), " (%ld ticks crouched in the air)", jump->crouched_ticks);
	}
	if (jump->lip_off >= 0.f)
		snprintf(lip, sizeof(lip), "a ledge %.2f up %.1f ahead", jump->lip_up, jump->lip_off);
	else
		snprintf(lip, sizeof(lip), "no ledge within 2 ahead");
	if (jump->over_lip < MOVE_LOG_NO_FLOOR)
		snprintf(over, sizeof(over), "%.3f", jump->over_lip);
	else
		snprintf(over, sizeof(over), "nothing (never over it)");
	if (!aas_ready())
		snprintf(nav, sizeof(nav), "no navigation");
	else
	{
		real time = aas_travel_time(AAS_FOOT, &jump->left_at, &jump->landed_at);
		snprintf(nav, sizeof(nav), "areas %ld to %ld, the navigation's way between them %s, its time %s%.1f s against the jump's %.1f",
			jump->left_area, jump->landed_area, move_log_travel_name(way), time < 0.f ? "(no way) " : "", time < 0.f ? 0.f : time,
			(jump->landed_tick - jump->left_tick) / (real)TICKS_PER_SECOND);
	}
	snprintf(line, sizeof(line),
		"jump %ld player %d on %s: left t%ld at %.2f %.2f %.2f at %.2f u/s, %s; %s; highest %.3f up (the most the crouch lifted in a tick %.3f, "
		"tick %ld); over the ledge's top by %s; down after %ld ticks %.3f %s where it left, %.2f across, on a floor of slope %.2f, at %.2f u/s "
		"(the slowest in the air %.2f); %.2f u/s half a second on, %.2f a second on%s; %s",
		move_log.jump_count, local, move_log_map(), jump->left_tick, jump->left_at.x, jump->left_at.y, jump->left_at.z, jump->left_speed, lip,
		crouch, jump->highest, jump->lift, jump->lift_tick, over, jump->landed_tick - jump->left_tick, (real)fabs(jump->landed_at.z - jump->left_at.z),
		jump->landed_at.z >= jump->left_at.z ? "above" : "below", across, jump->landed_slope, jump->landed_speed, jump->slowest, jump->speed_half,
		jump->speed_second, jump->jumps ? ", jump pressed in the air" : "", nav);
	move_log_line(move_log.jumps, line);
	platform_log("move: %s", line);
}

/* a move from one area to another the navigation has no way for */
static void move_log_unknown(short local, char const *how, long from_area, real_point3d const *from, long to_area, real_point3d const *to, long ticks)
{
	char line[512];
	char nav[64];
	real time = aas_travel_time(AAS_FOOT, from, to);
	if (time < 0.f)
		snprintf(nav, sizeof(nav), "has no way at all");
	else
		snprintf(nav, sizeof(nav), "takes %.1f s by the ways it has", time);
	snprintf(line, sizeof(line), "unknown t%ld player %d on %s: %s from area %ld at %.2f %.2f %.2f to area %ld at %.2f %.2f %.2f in %.1f s, "
		"%.2f across, %.2f %s; the navigation %s",
		game_time_get(), local, move_log_map(), how, from_area, from->x, from->y, from->z, to_area, to->x, to->y, to->z,
		ticks / (real)TICKS_PER_SECOND, bot_distance2d(from, to), (real)fabs(to->z - from->z), to->z >= from->z ? "up" : "down", nav);
	move_log_line(move_log.routes, line);
	platform_log("move: %s", line);
}

void move_log_tick(void)
{
	struct data_iterator iterator;
	struct player_datum *player;
	long now = game_time_get();

	if (!move_log.asked)
		move_log_open();
	if (!move_log.on || !game_in_progress())
		return;
	data_iterator_new(&iterator, player_data);
	while ((player = (struct player_datum *)data_iterator_next(&iterator)) != NULL)
	{
		short local = player->local_player_index;
		struct move_player *mp;
		struct unit_datum *unit;
		struct biped_datum *biped;
		struct object_datum *root;
		long root_index;
		real_vector3d const *velocity;
		real_point3d const *at;
		boolean airborne, crouch_held, jump_held, riding;
		real speed, yaw, aim_yaw, aim_pitch, move_yaw, strafe, slope, floor, ahead[4], wall_knee, wall_chest, look;
		long area, k;
		char seat = '-';
		char const *vehicle = "-";

		/* (testing: HALO_MOVE_LOG_PLAYER=n, the player of that index in the
		   game as well, a bot's, as the last of the slots) */
		if (local == NONE && move_log.watched >= 0 && DATUM_INDEX_TO_ABSOLUTE_INDEX(iterator.datum_index) == move_log.watched)
			local = MOVE_LOG_PLAYERS - 1;
		if (local < 0 || local >= MOVE_LOG_PLAYERS || player->unit_index == NONE)
			continue;
		mp = &move_log.players[local];
		unit = (struct unit_datum *)object_try_and_get(player->unit_index);
		biped = biped_try_and_get(player->unit_index);
		if (!unit || !biped)
		{
			mp->unit_index = NONE;
			continue;
		}
		riding = biped->object.parent_object_index != NONE;
		root_index = object_get_ultimate_parent(player->unit_index);
		root = object_get(root_index);
		if (riding)
		{
			vehicle = move_log_short_name(root->definition_index);
			seat = unit_seat_is_driver(root_index, unit->unit.parent_seat_index) ? 'd' :
				unit_seat_is_gunner(root_index, unit->unit.parent_seat_index) ? 'g' : 'p';
		}
		at = riding ? &root->object.position : &biped->object.position;
		velocity = riding ? &root->object.translational_velocity : &biped->object.translational_velocity;
		airborne = !riding && TEST_FLAG(biped->biped.flags, _biped_airborne_bit) != 0;
		crouch_held = TEST_FLAG(biped->unit.control_flags, _unit_control_crouch_modifier_bit) != 0;
		jump_held = TEST_FLAG(biped->unit.control_flags, _unit_control_jump_bit) != 0;
		speed = move_log_ground_speed(velocity);
		yaw = (real)atan2(biped->unit.desired_facing_vector.j, biped->unit.desired_facing_vector.i);
		aim_yaw = (real)atan2(biped->unit.aiming_vector.j, biped->unit.aiming_vector.i);
		aim_pitch = (real)asin(PIN(biped->unit.aiming_vector.k, -1.f, 1.f));
		move_yaw = speed > 0.05f ? (real)atan2(velocity->j, velocity->i) : yaw;
		strafe = speed > 0.05f ? bot_angle_difference(move_yaw, yaw) : 0.f;
		slope = !airborne && !riding ? biped->biped.ground_plane.n.k : 0.f;
		/* (the ground about it: under the feet, ahead the way it is going,
		   and the walls ahead) */
		look = speed > 0.3f ? move_yaw : yaw;
		floor = move_log_floor(at, 0.2f, 6.f, root_index);
		for (k = 0; k < 4; k++)
		{
			real_point3d there = *at;
			real down;
			there.x += (real)cos(look) * 0.5f * (k + 1);
			there.y += (real)sin(look) * 0.5f * (k + 1);
			down = move_log_floor(&there, 1.5f, 3.f, root_index);
			ahead[k] = down >= MOVE_LOG_NO_FLOOR ? MOVE_LOG_NO_FLOOR : -down;
		}
		{
			real_point3d knee = *at, chest = *at;
			knee.z += 0.3f;
			chest.z += 0.6f;
			wall_knee = bot_probe(&knee, look, 3.f, root_index);
			wall_chest = bot_probe(&chest, look, 3.f, root_index);
		}
		area = riding ? NONE : move_log_area(at, airborne);
		if (move_log.ticks)
		{
			char ahead_text[4][16], floor_text[16];
			long held = unit->unit.current_weapon_index >= 0 && unit->unit.current_weapon_index < MAXIMUM_WEAPONS_PER_UNIT ?
				unit->unit.weapon_object_indices[unit->unit.current_weapon_index] : NONE;
			for (k = 0; k < 4; k++)
			{
				if (ahead[k] >= MOVE_LOG_NO_FLOOR)
					ahead_text[k][0] = 0;
				else
					snprintf(ahead_text[k], sizeof(ahead_text[k]), "%.3f", ahead[k]);
			}
			if (floor >= MOVE_LOG_NO_FLOOR)
				floor_text[0] = 0;
			else
				snprintf(floor_text, sizeof(floor_text), "%.3f", floor);
			fprintf(move_log.ticks, "%ld,%d,%s,%s,%c,%.4f,%.4f,%.4f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.2f,%.2f,%lx,%d,%d,%.2f,%d,%d,%.3f,%s,"
				"%s,%s,%s,%s,%.2f,%.2f,%ld,%.2f,%.2f,%s,%d\n",
				now, local, move_log_map(), vehicle, seat, at->x, at->y, at->z, velocity->i * TICKS_PER_SECOND, velocity->j * TICKS_PER_SECOND,
				velocity->k * TICKS_PER_SECOND, speed, yaw, aim_yaw, aim_pitch, move_yaw, strafe, biped->unit.throttle.i, biped->unit.throttle.j,
				(unsigned long)biped->unit.control_flags, jump_held, crouch_held, biped->biped.crouch, airborne, (int)biped->biped.airborne_ticks,
				slope, floor_text, ahead_text[0], ahead_text[1], ahead_text[2], ahead_text[3], wall_knee, wall_chest, area,
				unit->object.body_vitality, unit->object.shield_vitality, held != NONE && object_try_and_get(held) ?
				move_log_short_name(object_get(held)->definition_index) : "-", (int)unit->unit.current_zoom_level);
			if (now % 30 == 0)
				fflush(move_log.ticks);
		}
		{
			struct move_jump *jump = &mp->jump;
			boolean same = mp->unit_index == player->unit_index;
			if (!same)
			{
				csmemset(mp, 0, sizeof(*mp));
				mp->unit_index = player->unit_index;
				mp->ground_area = NONE;
				mp->pace_tick = now;
				mp->pace_at = *at;
				mp->was_at = *at;
			}
			/* (carried a long way in a tick: a teleporter) */
			if (same && !riding && distance3d(at, &mp->was_at) > 4.f)
			{
				char line[256];
				snprintf(line, sizeof(line), "teleport t%ld player %d on %s: from %.2f %.2f %.2f (area %ld) to %.2f %.2f %.2f (area %ld)", now, local,
					move_log_map(), mp->was_at.x, mp->was_at.y, mp->was_at.z, mp->ground_area, at->x, at->y, at->z, area);
				move_log_line(move_log.routes, line);
				mp->ground_area = area;
				mp->ground_at = *at;
				mp->ground_tick = now;
				mp->pace_tick = now;
				mp->pace_at = *at;
				jump->on = 0;
			}
			if (riding)
			{
				jump->on = 0;
				mp->ground_area = NONE;
			}
			/* (off the ground: a jump begun, or a walk off an edge) */
			else if (same && airborne && !mp->was_airborne && jump->on != 1)
			{
				if (jump->on == 2)
					move_log_jump_done(local, jump);
				csmemset(jump, 0, sizeof(*jump));
				jump->on = 1;
				jump->left_tick = now;
				jump->left_at = mp->was_at;
				jump->left_speed = speed;
				jump->left_area = mp->ground_area;
				jump->crouch_before = crouch_held;
				jump->crouch_on = crouch_held ? 0 : NONE;
				jump->crouch_off = NONE;
				jump->slowest = speed;
				jump->lift_tick = NONE;
				jump->over_lip = MOVE_LOG_NO_FLOOR;
				jump->lip_off = -1.f;
				/* (the ledge ahead: the first floor a quarter of a unit or more up) */
				for (k = 0; k < 4; k++)
				{
					if (ahead[k] < MOVE_LOG_NO_FLOOR && ahead[k] + (at->z - jump->left_at.z) > 0.25f)
					{
						jump->lip_off = 0.5f * (k + 1);
						jump->lip_up = ahead[k] + (at->z - jump->left_at.z);
						break;
					}
				}
				move_log.jump_count++;
			}
			else if (jump->on == 1)
			{
				jump->highest = MAX(jump->highest, at->z - jump->left_at.z);
				jump->slowest = MIN(jump->slowest, speed);
				if (biped->biped.crouch > 0.01f)
					jump->crouched_ticks++;
				if (crouch_held && jump->crouch_on == NONE)
					jump->crouch_on = now - jump->left_tick;
				if (!crouch_held && mp->was_crouch_held && jump->crouch_off == NONE)
					jump->crouch_off = now - jump->left_tick;
				if (jump_held && !mp->was_jump_held)
					jump->jumps++;
				/* (the crouch's lift: the feet up more than the arc took them, in a
				   tick the body folded in) */
				if (biped->biped.crouch > mp->was_crouch + 0.01f)
				{
					real lift = at->z - mp->was_z - velocity->k;
					if (lift > jump->lift)
					{
						jump->lift = lift;
						jump->lift_tick = now - jump->left_tick;
					}
				}
				/* (over the ledge's top: how near the feet came to it) */
				if (jump->lip_off >= 0.f && floor < MOVE_LOG_NO_FLOOR && at->z - floor > jump->left_at.z + 0.25f)
					jump->over_lip = MIN(jump->over_lip, floor);
				if (!airborne)
				{
					jump->on = 2;
					jump->landed_tick = now;
					jump->landed_at = *at;
					jump->landed_speed = speed;
					jump->landed_slope = slope;
					jump->landed_area = area;
				}
			}
			else if (jump->on == 2)
			{
				if (now - jump->landed_tick == MOVE_LOG_AFTER / 2)
					jump->speed_half = speed;
				if (now - jump->landed_tick >= MOVE_LOG_AFTER)
				{
					jump->speed_second = speed;
					move_log_jump_done(local, jump);
					jump->on = 0;
				}
			}
			/* (on the ground in another area: a way the navigation has, or not) */
			if (!riding && !airborne && area != NONE)
			{
				if (mp->ground_area != NONE && area != mp->ground_area && move_log_direct_way(mp->ground_area, area) == NONE &&
					move_log_direct_way(area, mp->ground_area) != _aas_travel_walk)
				{
					char const *how = jump->on == 2 && jump->landed_tick == now ? (jump->highest > 0.05f ? "a jump" : "a fall") : "a walk";
					move_log_unknown(local, how, mp->ground_area, &mp->ground_at, area, at, now - mp->ground_tick);
				}
				mp->ground_area = area;
				mp->ground_at = *at;
				mp->ground_tick = now;
			}
			/* (the pace: every three seconds on foot, how far, against the
			   navigation's time for it) */
			if (riding)
			{
				mp->pace_tick = now;
				mp->pace_at = *at;
			}
			else if (now - mp->pace_tick >= MOVE_LOG_PACE && !airborne)
			{
				real moved = distance3d(at, &mp->pace_at);
				if (moved > 2.f && aas_ready() && move_log.routes)
				{
					real time = aas_travel_time(AAS_FOOT, &mp->pace_at, at);
					char nav[48];
					if (time < 0.f)
						snprintf(nav, sizeof(nav), "has no way");
					else
						snprintf(nav, sizeof(nav), "takes %.2f s", time);
					fprintf(move_log.routes, "pace t%ld player %d on %s: %.2f %.2f %.2f to %.2f %.2f %.2f, %.2f across %.2f %s, in %.1f s; the navigation %s\n",
						now, local, move_log_map(), mp->pace_at.x, mp->pace_at.y, mp->pace_at.z, at->x, at->y, at->z, bot_distance2d(&mp->pace_at, at),
						(real)fabs(at->z - mp->pace_at.z), at->z >= mp->pace_at.z ? "up" : "down", (now - mp->pace_tick) / (real)TICKS_PER_SECOND, nav);
					fflush(move_log.routes);
				}
				mp->pace_tick = now;
				mp->pace_at = *at;
			}
		}
		mp->was_airborne = airborne;
		mp->was_z = at->z;
		mp->was_at = *at;
		mp->was_crouch = biped->biped.crouch;
		mp->was_crouch_held = crouch_held;
		mp->was_jump_held = jump_held;
	}
}
