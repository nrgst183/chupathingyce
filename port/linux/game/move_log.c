/*
MOVE_LOG.C

debug.move_log (HALO_MOVE_LOG): this copy's own players' movement, a line a
tick, for working out how a person moves: how a crouch jump is timed, how
high it gets the feet and what it costs of the run, to teach the bots
(bot_move.c). Each local player on foot in a game gets:

logs/move_log.csv: a line a tick, from the game's own state after the tick
(game.c calls in after players_update_after_game): the tick, the player, the
feet (the unit's origin), the velocity in units a second, the speed across
the ground, the way faced, the stick, whether jump and crouch are held, how
far crouched the body is (0 standing .. 1 down), whether it is in the air
and for how many ticks, and the map.

logs/move_jumps.txt: a line for each jump (each time the feet leave the
ground and come down again), worked out from the ticks: where and how fast it
left the ground, when crouch was pressed and let go against the tick it left
the ground, how high the feet went above where they left (the highest, and
the most the crouch lifted them in one tick), where it came down (higher or
lower than it left, how far across), how fast it was going when it came down
and the slowest it went in the air, and how fast half a second and a second
after. Also in debug.txt, as "move:" lines.

Nothing is written unless it is asked for, and the files are begun afresh
each time the game starts.
*/

#include "cseries.h"
#include "game/game.h"
#include "game/players.h"
#include "main/main.h"
#include "objects/objects.h"
#include "units/bipeds.h"
#include "units/units.h"

#include <math.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#include "../src/port_folders.h"

int config_boolean(char const *name);
const char *platform_folder(enum port_folder folder);
void platform_log(char const *format, ...);

void move_log_tick(void);

#define MOVE_LOG_PLAYERS 4
#define MOVE_LOG_AFTER 30 /* ticks after a landing the speed is watched for */

struct move_jump
{
	int on; /* 1 in the air, 2 down and being watched */
	long left_tick;
	real_point3d left_at;
	real left_speed;
	long crouch_on; /* the tick crouch went down, from the tick it left (NONE: never) */
	long crouch_off;
	long crouch_before; /* crouch was held when it left the ground */
	real highest;
	real lift; /* the most the feet went up in one tick from crouching, at the top of its arc or not */
	long lift_tick;
	long landed_tick;
	real_point3d landed_at;
	real landed_speed;
	real slowest;
	real speed_half;
	real speed_second;
	long jumps; /* jump presses while in the air (none take) */
};

static struct
{
	int asked;
	int on;
	long watched;
	FILE *ticks;
	FILE *jumps;
	long jump_count;
	struct
	{
		long unit_index;
		int was_airborne;
		real was_z;
		real was_crouch;
		int was_crouch_held;
		int was_jump_held;
		long crouch_down_tick;
		struct move_jump jump;
	} players[MOVE_LOG_PLAYERS];
} move_log;

static real move_log_ground_speed(real_vector3d const *velocity)
{
	return (real)sqrt(velocity->i * velocity->i + velocity->j * velocity->j) * TICKS_PER_SECOND;
}

static void move_log_open(void)
{
	char path[512], folder[400];
	move_log.asked = TRUE;
	move_log.on = config_boolean("debug.move_log");
	move_log.watched = getenv("HALO_MOVE_LOG_PLAYER") ? atol(getenv("HALO_MOVE_LOG_PLAYER")) : NONE;
	if (!move_log.on)
		return;
	/* (in the logs folder, beside debug.txt; where that cannot be written,
	   the folder the game was started in) */
	snprintf(folder, sizeof(folder), "%s", platform_folder(_port_folder_logs));
	snprintf(path, sizeof(path), "%s/move_log.csv", folder);
	move_log.ticks = fopen(path, "w");
	if (!move_log.ticks)
	{
		snprintf(folder, sizeof(folder), ".");
		snprintf(path, sizeof(path), "%s/move_log.csv", folder);
		move_log.ticks = fopen(path, "w");
	}
	snprintf(path, sizeof(path), "%s/move_jumps.txt", folder);
	move_log.jumps = fopen(path, "w");
	if (move_log.ticks)
		fprintf(move_log.ticks, "tick,player,x,y,z,vx,vy,vz,ground_speed,yaw,stick_forward,stick_left,jump,crouch_held,crouch,airborne,airborne_ticks,map\n");
	platform_log("move: logging the movement of this copy's players to %s/move_log.csv and move_jumps.txt%s", folder,
		move_log.ticks && move_log.jumps ? "" : " (could not open them)");
}

static char const *move_log_map(void)
{
	char const *name = main_get_multiplayer_map_name();
	return name && *name ? name : main_get_map_name();
}

static void move_log_jump_done(short local, struct move_jump const *jump)
{
	char line[512];
	real across = (real)sqrt((jump->landed_at.x - jump->left_at.x) * (jump->landed_at.x - jump->left_at.x) +
		(jump->landed_at.y - jump->left_at.y) * (jump->landed_at.y - jump->left_at.y));
	char crouch[96];
	if (jump->crouch_before)
		snprintf(crouch, sizeof(crouch), "crouched as it left%s", jump->crouch_off != NONE ? "" : ", all the way");
	else if (jump->crouch_on != NONE)
		snprintf(crouch, sizeof(crouch), "crouch at tick %ld", jump->crouch_on);
	else
		snprintf(crouch, sizeof(crouch), "no crouch");
	if (jump->crouch_off != NONE)
		snprintf(crouch + strlen(crouch), sizeof(crouch) - strlen(crouch), ", let go at tick %ld", jump->crouch_off);
	snprintf(line, sizeof(line),
		"jump %ld player %d on %s: left t%ld at %.2f %.2f %.2f at %.2f u/s, %s; highest %.3f up (tick %ld lifted the most by crouching, %.3f); "
		"down after %ld ticks %.3f %s where it left, %.2f across, at %.2f u/s (the slowest in the air %.2f); %.2f u/s half a second on, %.2f a second on%s",
		move_log.jump_count, local, move_log_map(), jump->left_tick, jump->left_at.x, jump->left_at.y, jump->left_at.z, jump->left_speed, crouch,
		jump->highest, jump->lift_tick, jump->lift, jump->landed_tick - jump->left_tick, (real)fabs(jump->landed_at.z - jump->left_at.z),
		jump->landed_at.z >= jump->left_at.z ? "above" : "below", across, jump->landed_speed, jump->slowest, jump->speed_half, jump->speed_second,
		jump->jumps ? ", jump pressed in the air" : "");
	if (move_log.jumps)
	{
		fprintf(move_log.jumps, "%s\n", line);
		fflush(move_log.jumps);
	}
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
		struct biped_datum *biped;
		/* (testing: HALO_MOVE_LOG_PLAYER=n, the player of that index in the
		   game as well, a bot's, as the last of the slots) */
		if (local == NONE && move_log.watched >= 0 && DATUM_INDEX_TO_ABSOLUTE_INDEX(iterator.datum_index) == move_log.watched)
			local = MOVE_LOG_PLAYERS - 1;
		real_vector3d const *velocity;
		real_point3d const *at;
		boolean airborne, crouch_held, jump_held;
		real speed, yaw;

		if (local < 0 || local >= MOVE_LOG_PLAYERS || player->unit_index == NONE)
			continue;
		biped = biped_try_and_get(player->unit_index);
		if (!biped || biped->object.parent_object_index != NONE)
		{
			move_log.players[local].unit_index = NONE;
			continue;
		}
		at = &biped->object.position;
		velocity = &biped->object.translational_velocity;
		airborne = TEST_FLAG(biped->biped.flags, _biped_airborne_bit) != 0;
		crouch_held = TEST_FLAG(biped->unit.control_flags, _unit_control_crouch_modifier_bit) != 0;
		jump_held = TEST_FLAG(biped->unit.control_flags, _unit_control_jump_bit) != 0;
		speed = move_log_ground_speed(velocity);
		yaw = (real)atan2(biped->unit.desired_facing_vector.j, biped->unit.desired_facing_vector.i);
		if (move_log.ticks)
		{
			fprintf(move_log.ticks, "%ld,%d,%.4f,%.4f,%.4f,%.3f,%.3f,%.3f,%.3f,%.3f,%.2f,%.2f,%d,%d,%.2f,%d,%d,%s\n", now, local, at->x, at->y, at->z,
				velocity->i * TICKS_PER_SECOND, velocity->j * TICKS_PER_SECOND, velocity->k * TICKS_PER_SECOND, speed, yaw,
				biped->unit.throttle.i, biped->unit.throttle.j, jump_held, crouch_held, biped->biped.crouch, airborne,
				(int)biped->biped.airborne_ticks, move_log_map());
			if (now % 30 == 0)
				fflush(move_log.ticks);
		}
		{
			struct move_jump *jump = &move_log.players[local].jump;
			boolean same = move_log.players[local].unit_index == player->unit_index;
			if (!same)
			{
				csmemset(&move_log.players[local], 0, sizeof(move_log.players[local]));
				move_log.players[local].unit_index = player->unit_index;
				move_log.players[local].crouch_down_tick = NONE;
			}
			if (crouch_held && !move_log.players[local].was_crouch_held)
				move_log.players[local].crouch_down_tick = now;
			/* (off the ground: a jump begun, or a walk off an edge) */
			if (same && airborne && !move_log.players[local].was_airborne && jump->on != 1)
			{
				if (jump->on == 2)
					move_log_jump_done(local, jump);
				csmemset(jump, 0, sizeof(*jump));
				jump->on = 1;
				jump->left_tick = now;
				jump->left_at = *at;
				jump->left_speed = speed;
				jump->crouch_before = crouch_held;
				jump->crouch_on = crouch_held ? 0 : NONE;
				jump->crouch_off = NONE;
				jump->slowest = speed;
				jump->lift_tick = NONE;
				move_log.jump_count++;
			}
			else if (jump->on == 1)
			{
				jump->highest = MAX(jump->highest, at->z - jump->left_at.z);
				jump->slowest = MIN(jump->slowest, speed);
				if (crouch_held && jump->crouch_on == NONE)
					jump->crouch_on = now - jump->left_tick;
				if (!crouch_held && move_log.players[local].was_crouch_held && jump->crouch_off == NONE)
					jump->crouch_off = now - jump->left_tick;
				if (jump_held && !move_log.players[local].was_jump_held)
					jump->jumps++;
				/* (the crouch's lift: the feet up more than the arc took them, in a
				   tick the body folded in) */
				if (biped->biped.crouch > move_log.players[local].was_crouch + 0.01f)
				{
					real lift = at->z - move_log.players[local].was_z - velocity->k;
					if (lift > jump->lift)
					{
						jump->lift = lift;
						jump->lift_tick = now - jump->left_tick;
					}
				}
				if (!airborne)
				{
					jump->on = 2;
					jump->landed_tick = now;
					jump->landed_at = *at;
					jump->landed_speed = speed;
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
		}
		move_log.players[local].was_airborne = airborne;
		move_log.players[local].was_z = at->z;
		move_log.players[local].was_crouch = biped->biped.crouch;
		move_log.players[local].was_crouch_held = crouch_held;
		move_log.players[local].was_jump_held = jump_held;
	}
}
