#!/usr/bin/env python3
"""Writes the ways people take about the maps that the bots' navigation has
none of, from the movement logs (debug.move_log; port/linux/game/move_log.c),
into port/linux/game/bot_people_ways.c, which the navigation adds to each
map's ways (bot_aas.c) and the bots then take as the person did
(bot_move.c, bot_move_travel_people):

    python tools/bot_people_ways.py logs/move_routes.txt logs/move_jumps.txt [more logs...]

A way is kept when the log has it as a jump or a fall from one area to
another the navigation has no way between ("unknown" in move_routes.txt),
and the person's time for it beats the navigation's by more than half a
second and by more than two fifths; with the jump's line in move_jumps.txt
(where it left the ground, how fast, which way, when the crouch went down and
came up, where it came down). The same way taken more than once (from and to
within half a unit) is kept once: the quickest, and how many times it was
taken. Run it again with more logs: the ways already in the file are kept
unless the logs have them again."""

import math
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "port/linux/game/bot_people_ways.c"

UNKNOWN = re.compile(r"unknown t(\d+) player \d+ on (\S+): (a jump|a fall) from area -?\d+ at ([-\d.]+) ([-\d.]+) ([-\d.]+) to area -?\d+ at "
                     r"([-\d.]+) ([-\d.]+) ([-\d.]+) in ([\d.]+) s, [\d.]+ across, [\d.]+ (?:up|down); the navigation "
                     r"(?:takes ([\d.]+) s by the ways it has|has no way at all)")
JUMP = re.compile(r"jump \d+ player \d+ on (\S+): left t(\d+) at ([-\d.]+) ([-\d.]+) ([-\d.]+) at ([\d.]+) u/s, .*?; "
                  r"(no crouch|crouched as it left|crouch at tick (\d+))(?:, let go at tick (\d+)|, held down)?.*?"
                  r"down after (\d+) ticks ([\d.]+) (above|below) where it left, ([\d.]+) across")


def map_of(name):
    return name.replace("/", "\\").split("\\")[-1].split("@")[0]


def read(paths):
    unknowns, jumps = [], []
    for path in paths:
        for line in open(path, errors="replace"):
            m = UNKNOWN.match(line)
            if m:
                g = m.groups()
                unknowns.append(dict(map=map_of(g[1]), how=g[2], frm=tuple(map(float, g[3:6])), to=tuple(map(float, g[6:9])),
                                     time=float(g[9]), nav=float(g[10]) if g[10] else 99.0))
            m = JUMP.match(line)
            if m:
                g = m.groups()
                on = 0 if g[6] == "crouched as it left" else int(g[7]) if g[7] else -1
                off = int(g[8]) if g[8] else (-1 if on < 0 else 999)
                rise = float(g[10]) * (1 if g[11] == "above" else -1)
                jumps.append(dict(map=map_of(g[0]), frm=tuple(map(float, g[2:5])), speed=float(g[5]), on=on, off=off, ticks=int(g[9]),
                                  rise=rise, across=float(g[12])))
    return unknowns, jumps


def main():
    unknowns, jumps = read(sys.argv[1:])
    ways = []
    for u in unknowns:
        if not (u["nav"] >= u["time"] + 0.5 and u["nav"] >= 1.4 * u["time"]):
            continue
        # (its jump: left the ground where the move began)
        # (and came down where the move ended: not on a bank it slid down
        # from, nor somewhere it went on from in the air again)
        across = math.dist(u["frm"][:2], u["to"][:2])
        near = [j for j in jumps if j["map"] == u["map"] and math.dist(j["frm"], u["frm"]) < 0.08 and abs(j["across"] - across) < 0.35 and
                abs(j["rise"] - (u["to"][2] - u["frm"][2])) < 0.15]
        if not near:
            continue
        j = near[0]
        # (longer in the air than a jump can be, for how far it came down: not
        # a jump but a slide down a bank, the feet off the ground, or carried)
        drop = u["frm"][2] - u["to"][2]
        flight = (2.1 + math.sqrt(max(0.0, 2.1 * 2.1 + 2 * 3.21 * drop))) / 3.21
        if j["ticks"] / 30.0 > flight + 0.25:
            continue
        heading = math.atan2(u["to"][1] - u["frm"][1], u["to"][0] - u["frm"][0])
        way = dict(map=u["map"], frm=u["frm"], to=u["to"], heading=heading, speed=j["speed"], on=j["on"], off=j["off"],
                   time=min(u["time"], j["ticks"] / 30.0 + 0.1), nav=u["nav"], seen=1)
        for w in ways:
            if w["map"] == way["map"] and math.dist(w["frm"], way["frm"]) < 0.5 and math.dist(w["to"], way["to"]) < 0.5:
                w["seen"] += 1
                if way["time"] < w["time"]:
                    way["seen"] = w["seen"]
                    w.update(way)
                break
        else:
            ways.append(way)
    ways.sort(key=lambda w: (w["map"], w["frm"]))
    lines = [
        "/*",
        "BOT_PEOPLE_WAYS.C",
        "",
        "Written by tools/bot_people_ways.py from movement logs (debug.move_log): the",
        "ways about the maps people took that the bots' navigation had none of, and",
        "how they took them. Each: the map, where the feet left the ground and where",
        "they came down, the way it was going (radians), how fast (units a second),",
        "the tick after leaving the ground the crouch went down and came up (-1: no",
        "crouch; 999: held to the landing), the person's time for it, the",
        "navigation's time by its own ways then, and how many times it was taken.",
        "*/",
        "",
        "#include \"bot_internal.h\"",
        "",
        "struct bot_people_way const bot_people_ways[] =",
        "{",
    ]
    for w in ways:
        lines.append('\t{ "%s", { %.2ff, %.2ff, %.2ff }, { %.2ff, %.2ff, %.2ff }, %.3ff, %.2ff, %d, %d, %.2ff, %.1ff, %d },' % (
            w["map"], *w["frm"], *w["to"], w["heading"], w["speed"], w["on"], w["off"], w["time"], min(w["nav"], 99.0), w["seen"]))
    lines += ["\t{ NULL }", "};", "", "long const bot_people_way_count = %d;" % len(ways), ""]
    OUT.write_text("\n".join(lines))
    print("%d ways written to %s" % (len(ways), OUT))
    for w in ways:
        print("  %-12s %6.2f %6.2f %6.2f -> %6.2f %6.2f %6.2f  %.1f s (navigation %.1f), crouch %d..%d, seen %d" % (
            w["map"], *w["frm"], *w["to"], w["time"], w["nav"], w["on"], w["off"], w["seen"]))


if __name__ == "__main__":
    main()
