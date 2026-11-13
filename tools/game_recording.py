#!/usr/bin/env python3
"""Sums up game recordings (debug.record_games: logs/game_*.csv).

    python tools/game_recording.py logs/game_*.csv

For each recording, its build, map and game type, and how its bots and its
people played: how far they went in each 5 seconds alive, how much of the
time alive they stood still, jumps a minute, kills and deaths a minute, how
much of their time was spent fighting someone, and what the bots' goals
were. For telling one build's bots from another's by the games played with
them."""
import csv
import math
import sys
from collections import Counter, defaultdict


def read(path):
    head = {}
    rows = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        lines = []
        for line in f:
            if line.startswith("#"):
                key, _, value = line[1:].partition(":")
                head[key.strip()] = value.strip()
            else:
                lines.append(line)
    for row in csv.DictReader(lines):
        rows.append(row)
    return head, rows


def summary(path):
    head, rows = read(path)
    players = defaultdict(lambda: {"alive": 0, "moved": 0.0, "still": 0, "air": 0, "jumps": 0, "fight": 0,
                                   "goals": Counter(), "kills": 0, "deaths": 0, "bot": 0, "name": ""})
    last = {}
    times = set()
    for row in rows:
        try:
            t = float(row["t"])
        except (TypeError, ValueError):
            continue
        times.add(t)
        p = players[row["player"]]
        p["name"], p["bot"] = row["name"], row["bot"] == "1"
        if row.get("kills"):
            p["kills"], p["deaths"] = int(row["kills"]), int(row["deaths"])
        if row["alive"] != "1":
            last.pop(row["player"], None)
            continue
        x, y, z = float(row["x"]), float(row["y"]), float(row["z"])
        p["alive"] += 1
        air = row["airborne"] == "1"
        was = last.get(row["player"])
        if was:
            step = math.dist((x, y), was[:2])
            if step < 3.0:  # (not a respawn or a teleporter)
                p["moved"] += step
            if air and not was[2] and row["vehicle"] == "-":
                p["jumps"] += 1
        last[row["player"]] = (x, y, air)
        if float(row["speed"] or 0) < 0.3 and not air:
            p["still"] += 1
        if row.get("target") not in (None, "", "-1"):
            p["fight"] += 1
        if p["bot"]:
            p["goals"][row.get("goal") or "-"] += 1
    rate = 5.0  # lines a second
    minutes = (max(times) - min(times)) / 60.0 if times else 0.0
    print(f"{path}")
    print(f"  {head.get('build', '?')}")
    print(f"  {head.get('map', '?')}, {head.get('game', '?')}, {minutes:.1f} minutes; bots {head.get('bots', '?')}")
    groups = {"bots": [p for p in players.values() if p["bot"]], "people": [p for p in players.values() if not p["bot"]]}
    for label, group in groups.items():
        alive = sum(p["alive"] for p in group)
        if not alive:
            continue
        mins = alive / rate / 60.0
        goals = Counter()
        for p in group:
            goals.update(p["goals"])
        total = sum(goals.values()) or 1
        print(f"  {label} ({len(group)}): {sum(p['moved'] for p in group) / (alive / rate / 5.0):.1f} u moved a 5 s alive, "
              f"{100.0 * sum(p['still'] for p in group) / alive:.0f}% stood still, "
              f"{sum(p['jumps'] for p in group) / mins:.1f} jumps a minute, "
              f"{100.0 * sum(p['fight'] for p in group) / alive:.0f}% fighting, "
              f"kills {sum(p['kills'] for p in group) / max(minutes, 0.01) / len(group):.2f} and deaths "
              f"{sum(p['deaths'] for p in group) / max(minutes, 0.01) / len(group):.2f} a minute each")
        if label == "bots":
            print("    goals: " + ", ".join(f"{g} {100.0 * n / total:.0f}%" for g, n in goals.most_common(6)))
    for p in sorted(players.values(), key=lambda p: -p["kills"]):
        if p["alive"]:
            print(f"    {p['name']:<14} {p['kills']:>3} kills {p['deaths']:>3} deaths, "
                  f"{p['moved'] / (p['alive'] / rate / 5.0):.1f} u a 5 s, {100.0 * p['still'] / p['alive']:.0f}% still")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    for path in sys.argv[1:]:
        summary(path)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
