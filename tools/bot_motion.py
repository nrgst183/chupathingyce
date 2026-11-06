#!/usr/bin/env python3
"""How the bots move, in numbers, from a game's log with HALO_BOT_TRAJ=1 (and HALO_BOT_LOG=1).

    python3 tools/bot_motion.py out.txt [more logs...]        the figures for each log
    python3 tools/bot_motion.py --json out.txt                ... as JSON

Each bot on foot is followed tick by tick (port/linux/game/bots.c, bot_trace_move). The figures are
over the ticks it is going somewhere (moving, not fighting, alive), and are made so that less is
better unless said:

  pace          its speed along the ground over a full run's, on the ground and not mid-jump (more is better)
  held          the share of those ticks it is all but standing (under a third of a run)
  swerve        how fast the way it goes turns, radians a second (the mean); swerve95, the worst twentieth
  zigzag        times a minute the way it goes swings back on itself (over 135 degrees inside half a second)
  dither        how fast the way it means to go (the route's) turns, radians a second: the plan changing its mind
  facing        how far off the way it goes it faces, radians (the mean): looking where you go is what people do
  falls         falls of more than a unit and a half it did not set out to make (not a drop of the route's, under way or
                a few links on), an hour
  bumps         times a minute two bots stand closer than half a unit (bodies in each other)
  legs, leg_s   tour legs made, and their mean seconds (HALO_BOT_GOTO=tour), when the log has them
  ratio         the legs' seconds over what the navigation reckoned (less is better)
"""
import sys, re, math, json, collections

TICKS = 30.0


def angle(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def analyse(text, points=()):
    """points: the places the bots are sent to (a turn round there is arriving, not a zigzag)"""
    rows = collections.defaultdict(list)
    for line in text.splitlines():
        i = line.find("trj ")
        if i < 0:
            continue
        p = line[i + 4:].split()
        if len(p) < 19:
            continue
        rows[int(p[0])].append((int(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[6]), float(p[7]),
                                float(p[8]), float(p[9]), int(p[10]), float(p[11]), int(p[14]), int(p[15]), int(p[16]), int(p[17]),
                                int(p[19]) if len(p) > 19 else -1))
    # a full run: what the bots go at most of the time they are going flat out
    speeds = sorted(math.hypot(r[4], r[5]) * TICKS for rs in rows.values() for r in rs if r[9] and not r[12] and not r[14])
    run = speeds[int(len(speeds) * 0.9)] if speeds else 2.25
    run = max(run, 1.0)
    moving = held = 0
    pace = 0.0
    swerve = []
    dither = []
    facing = []
    zigzags = 0
    falls = 0
    minutes = 0.0
    for b, rs in rows.items():
        rs.sort()
        last = None
        heads = collections.deque()
        fall_from = None
        for r in rs:
            t, x, y, z, vx, vy, vz, yaw, myaw, mv, spd, travel, air, committed, fighting, upcoming = r
            if last is not None and (t - last[0] != 1 or math.hypot(x - last[1], y - last[2]) > 2.0):
                last = None  # (a gap, a respawn, a teleport: start again)
                heads.clear()
                fall_from = None
            going = mv and not fighting and spd > 0.0  # (meaning to go: not standing on purpose, waiting, lying in wait)
            speed = math.hypot(vx, vy) * TICKS
            if going:
                minutes += 1.0 / TICKS / 60.0
                if not air and not committed:
                    moving += 1
                    pace += min(speed / run, 1.2)
                    if speed < run / 3.0 and all(math.hypot(x - q[0], y - q[1]) > 2.0 for q in points):
                        held += 1
                if last is not None:
                    dither.append(abs(angle(myaw - last[8])) * TICKS)
                if speed > run * 0.5:
                    head = math.atan2(vy, vx)
                    facing.append(abs(angle(yaw - head)))
                    if last is not None and math.hypot(last[4], last[5]) * TICKS > run * 0.5:
                        swerve.append(abs(angle(head - math.atan2(last[5], last[4]))) * TICKS)
                    heads.append((t, head))
                    while heads and t - heads[0][0] > 15:
                        heads.popleft()
                    if heads and abs(angle(head - heads[0][1])) > 2.36 and all(math.hypot(x - q[0], y - q[1]) > 3.0 for q in points):
                        zigzags += 1
                        heads.clear()
            # (a fall: down more than a unit inside a second and a half, in the air since a moment when
            # no drop, jump or gap of the route's was under way or a few links on)
            if air:
                if fall_from is None:
                    planned = travel in (1, 2, 3, 4, 5) or upcoming in (2, 3) or committed
                    fall_from = (t, z, planned)
                elif not fall_from[2] and fall_from[1] - z > 1.5 and t - fall_from[0] < 60:
                    falls += 1
                    fall_from = (fall_from[0], fall_from[1], True)  # (counted: not again on the way down)
            else:
                fall_from = None
            last = r
    # bodies in each other: at each tick, the pairs nearer than half a unit
    at = collections.defaultdict(list)
    for b, rs in rows.items():
        for r in rs:
            if r[9]:
                at[r[0]].append((b, r[1], r[2], r[3]))
    close = 0
    for t, ps in at.items():
        if t % 3:
            continue
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                if math.hypot(ps[i][1] - ps[j][1], ps[i][2] - ps[j][2]) < 0.5 and abs(ps[i][3] - ps[j][3]) < 1.0:
                    close += 1
    legs = re.findall(r"tour bot\d+ leg to \S+ \S+ \S+ (in|given up after) ([\d.]+) s(?: \(reckoned ([-\d.]+) s\))?", text)
    done = [(float(s), float(e) if e else 0.0) for how, s, e in legs if how == "in"]
    pairs = [(a, e) for a, e in done if e > 1.0]
    sw = sorted(swerve)
    out = {
        "run": round(run, 2),
        "pace": round(pace / max(moving, 1), 3),
        "held": round(held / max(moving, 1), 3),
        "swerve": round(sum(swerve) / max(len(swerve), 1), 3),
        "swerve95": round(sw[int(len(sw) * 0.95)] if sw else 0.0, 3),
        "zigzag": round(zigzags / max(minutes, 1e-6), 3),
        "dither": round(sum(dither) / max(len(dither), 1), 3),
        "facing": round(sum(facing) / max(len(facing), 1), 3),
        "falls": round(falls / max(minutes / 60.0, 1e-6), 2),
        "bumps": round(close / 10.0 / max(minutes, 1e-6), 3),
        "legs": len(done),
        "given_up": len(legs) - len(done),
        "leg_s": round(sum(a for a, e in done) / max(len(done), 1), 2),
        "ratio": round(sum(a for a, e in pairs) / sum(e for a, e in pairs), 3) if pairs else None,
        "bot_minutes": round(minutes, 2),
    }
    return out


def tour_points(text):
    """the tour's places, from the log's tour lines"""
    found = set()
    for m in re.finditer(r"tour bot\d+ leg to ([-\d.]+) ([-\d.]+) ([-\d.]+)", text):
        found.add((float(m.group(1)), float(m.group(2)), float(m.group(3))))
    return sorted(found)


if __name__ == "__main__":
    args = sys.argv[1:]
    as_json = args[:1] == ["--json"]
    if as_json:
        args = args[1:]
    results = {p: analyse(open(p, errors="replace").read(), tour_points(open(p, errors="replace").read())) for p in args}
    if as_json:
        print(json.dumps(results, indent=1))
    else:
        for p, r in results.items():
            print(p, " ".join("%s %s" % kv for kv in r.items()))
