#!/usr/bin/env python3
"""A person's jump, from a movement log (debug.move_log), for a bot to play back
(HALO_BOT_REPLAY, port/linux/game/move_log.c).

    python3 tools/move_replay.py logs/move_log.csv logs/move_jumps.txt <line> replay.txt

<line>: the jump's line in move_jumps.txt (from 1). Writes the ticks from a
second before the feet left the ground to half a second after they came down:
"x y z vx vy vz yaw pitch forward left jump crouch" a tick; and, on its first
line after a #, the map to play it on and the person's own path, for
comparing with what the bot does (tools/move_replay.py compare)."""
import csv, re, sys, math

JUMP = re.compile(r"player (\d+) on (\S+): left t(\d+) at (\S+) (\S+) (\S+) at .*?down after (\d+) ticks")


def map_name(name):
    if "\\" in name:
        return name.split("\\")[-1]
    return name


def extract(log, jumps, line, out):
    text = open(jumps, errors="replace").read().splitlines()[line - 1]
    m = JUMP.search(text)
    if not m:
        sys.exit("not a jump's line: " + text[:80])
    player, mp, tick, x, y, z, air = m.group(1), m.group(2), int(m.group(3)), float(m.group(4)), float(m.group(5)), float(m.group(6)), int(m.group(7))
    rows = list(csv.DictReader(open(log, errors="replace")))
    # (the log is added to game after game: the stretch whose take-off is at the jump's place)
    best = None
    for i, r in enumerate(rows):
        if r["map"] == mp and r["player"] == player and abs(int(r["tick"]) - tick) <= 2 and \
                math.dist((float(r["x"]), float(r["y"]), float(r["z"])), (x, y, z)) < 0.15:
            best = i
            break
    if best is None:
        sys.exit("the jump's ticks are not in " + log)
    start, end = best - 30, best + air + 15
    seg = [r for r in rows[max(start, 0):end] if r["map"] == mp and r["player"] == player and r["vehicle"] == "-"]
    with open(out, "w") as f:
        f.write("# %s %d %s\n" % (map_name(mp), best - max(start, 0), text.split(": ", 1)[1][:120]))
        for r in seg:
            f.write("%s %s %s %s %s %s %s %s %s %s %d %d\n" % (r["x"], r["y"], r["z"], r["vx"], r["vy"], r["vz"], r["yaw"], r["aim_pitch"],
                    r["stick_forward"], r["stick_left"], int(r["jump"]), int(r["crouch_held"])))
    print("%s: %d ticks on %s" % (out, len(seg), map_name(mp)))


def compare(replay, game_log):
    """the bot's path each try against the person's, from a game's log"""
    person = [tuple(map(float, l.split()[:3])) for l in open(replay) if not l.startswith("#")]
    tries = {}
    for l in open(game_log, errors="replace"):
        m = re.search(r"replay (\d+) (\d+) (\S+) (\S+) (\S+) (\d)", l)
        if m:
            tries.setdefault(int(m.group(1)), {})[int(m.group(2))] = tuple(map(float, m.group(3, 4, 5)))
    for t, path in sorted(tries.items()):
        errs = [math.dist(path[k], person[k]) for k in sorted(path) if k < len(person)]
        if errs:
            last = max(k for k in path if k < len(person))
            print("try %d: %d ticks, off by %.3f at most, %.3f at the end (bot %.2f %.2f %.2f, person %.2f %.2f %.2f)" % (
                t, len(errs), max(errs), errs[-1], *path[last], *person[last]))


if __name__ == "__main__":
    if sys.argv[1] == "compare":
        compare(sys.argv[2], sys.argv[3])
    else:
        extract(sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4])
