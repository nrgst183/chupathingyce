#!/usr/bin/env python3
"""What the bots' personality traits do, from game recordings.

    python tools/bot_traits.py [--trait NAME] logs/game_*.csv

Each bot's behaviour in each recording (debug.record_games) is measured, per
bot: kills and deaths, how it moves, how it fights, where it goes and what
it goes for, how it plays with its side. With --trait, the bots are split by
that trait (from the "# bot" lines at the top of the recording) into the low
and the high half, and each measure compared, with its size against how much
the measure varies from bot to bot anyway (an effect of 1 is a difference as
big as that spread). A game of bots with the trait pinned low for half of
them and high for the others (HALO_BOT_TRAIT="flanker=0/1") is the plainest
test: the two halves play the same game.

Without --trait, the measures for every bot, for a look."""
import argparse
import csv
import math
import statistics as st
from collections import Counter, defaultdict

POWER = ("rocket", "sniper", "fuel rod", "flamethrower")


def read(path):
    traits, rows = {}, []
    lines = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("# bot "):
                head, _, rest = line[6:].partition(": ")
                index = head.split(" ", 1)[0]
                values = {}
                for part in rest.split():
                    k, _, v = part.partition("=")
                    try:
                        values[k] = float(v)
                    except ValueError:
                        pass
                traits[index] = values
            elif not line.startswith("#"):
                lines.append(line)
    for row in csv.DictReader(lines):
        try:
            row["t"] = float(row["t"])
        except (TypeError, ValueError):
            continue
        if row["alive"] == "1":
            try:
                row["x"], row["y"], row["z"] = float(row["x"]), float(row["y"]), float(row["z"])
                row["speed"] = float(row["speed"] or 0)
            except (TypeError, ValueError):
                continue
        rows.append(row)
    return traits, rows


def angle_between(a, b):
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def measure(path):
    """per bot index: {measure: value}"""
    traits, rows = read(path)
    by_t = defaultdict(dict)
    for r in rows:
        by_t[r["t"]][r["player"]] = r
    times = sorted(by_t)
    if len(times) < 10:
        return {}, traits
    teams = len({r["team"] for r in rows if r.get("bot") == "1"}) <= 2 and len({r["team"] for r in rows}) <= 2
    m = defaultdict(lambda: defaultdict(float))
    deaths_at = defaultdict(list)
    spawned = {}
    prev = None
    windows = defaultdict(Counter)
    visited = defaultdict(set)
    for t in times:
        cur = by_t[t]
        alive = {p: r for p, r in cur.items() if r["alive"] == "1" and isinstance(r["x"], float)}
        for p, r in cur.items():
            if r.get("bot") != "1":
                continue
            b = m[p]
            if r["alive"] != "1" or not isinstance(r["x"], float):
                continue
            if prev and (p not in prev or prev[p]["alive"] != "1"):
                spawned[p] = t
            b["alive"] += 1
            fighting = r["target"] not in ("", "-1", None)
            air = r["airborne"] == "1"
            b["fighting"] += fighting
            b["air"] += air
            b["still"] += r["speed"] < 0.3 and not air
            b["crouch"] += float(r["crouch"] or 0) > 0.5 and not air
            b["vehicle"] += r["vehicle"] != "-"
            b["power"] += any(w in (r["weapon"] or "") for w in POWER)
            goal = r["goal"] or ""
            b["goal_item"] += goal.startswith("item")
            b["goal_hold"] += goal.startswith("hold")
            b["goal_roam"] += goal.startswith("roam")
            b["goal_enemy"] += goal.startswith("enemy")
            b["goal_lurk"] += "lurk" in goal
            b["goal_perch"] += "perch" in goal
            visited[p].add((round(r["x"] / 3), round(r["y"] / 3), round(r["z"] / 2)))
            others = [o for q, o in alive.items() if q != p]
            if others:
                near_any = min(math.dist((r["x"], r["y"]), (o["x"], o["y"])) for o in others)
                b["near_any"] += near_any
                mates = [o for o in others if teams and o["team"] == r["team"]]
                if mates:
                    b["near_mate"] += min(math.dist((r["x"], r["y"]), (o["x"], o["y"])) for o in mates)
                    b["mate_samples"] += 1
            if fighting and r["target"] in alive:
                o = alive[r["target"]]
                b["fight_dist"] += math.dist((r["x"], r["y"], r["z"]), (o["x"], o["y"], o["z"]))
                b["fight_samples"] += 1
                b["fight_low_shield"] += float(r["shield"] or 1) < 0.3
                try:
                    b["trigger"] += int(r.get("buttons") or "0", 16) & 0x800 != 0
                except ValueError:
                    pass
            if not fighting:
                b["moved_calm"] += 0
            if prev and p in prev and prev[p]["alive"] == "1" and isinstance(prev[p]["x"], float):
                q = prev[p]
                step = math.dist((r["x"], r["y"]), (q["x"], q["y"]))
                if step < 3.0:
                    b["moved"] += step
                if air and q["airborne"] == "0" and r["vehicle"] == "-":
                    b["jumps"] += 1
                if r.get("grenades") and q.get("grenades"):
                    try:
                        thrown = int(q["grenades"]) - int(r["grenades"])
                        if 0 < thrown <= 2:
                            b["grenades"] += thrown
                    except ValueError:
                        pass
        # kills and deaths this sample
        if prev:
            killers = [p for p, r in cur.items() if p in prev and r["kills"] and prev[p]["kills"] and int(r["kills"]) > int(prev[p]["kills"])]
            dead = [p for p, r in cur.items() if p in prev and r["deaths"] and prev[p]["deaths"] and int(r["deaths"]) > int(prev[p]["deaths"])]
            for k in killers:
                windows[k][int(t // 30)] += 1
                kr = prev[k]
                if kr["alive"] != "1" or not isinstance(kr["x"], float):
                    continue
                victims = [v for v in dead if v != k and prev[v]["alive"] == "1" and isinstance(prev[v]["x"], float)]
                if not victims:
                    continue
                v = min(victims, key=lambda v: math.dist((kr["x"], kr["y"]), (prev[v]["x"], prev[v]["y"])))
                vr = prev[v]
                b = m[k]
                b["kills_seen"] += 1
                # from the side or behind: the killer off the victim's aim by more than 60 degrees
                to_killer = math.atan2(kr["y"] - vr["y"], kr["x"] - vr["x"])
                try:
                    b["kill_flank"] += angle_between(to_killer, float(vr["aim_yaw"])) > math.radians(60)
                except ValueError:
                    pass
                b["kill_busy"] += vr["target"] not in ("", "-1", k)
                b["kill_fresh"] += t - spawned.get(v, -99) < 5.0
            for d in dead:
                r = prev[d]
                if r["alive"] != "1" or not isinstance(r["x"], float):
                    continue
                b = m[d]
                spot = (r["x"], r["y"], r["z"])
                b["deaths_seen"] += 1
                b["death_again"] += any(math.dist(spot, s) < 4.0 and t - when < 120 for s, when in deaths_at[d])
                deaths_at[d].append((spot, t))
                killer = next((k for k in killers if k != d), None)
                if killer is not None:
                    b["death_by_other"] += r["target"] not in ("", "-1", killer)
        prev = cur
    minutes = (times[-1] - times[0]) / 60.0
    out = {}
    for p, b in m.items():
        if b["alive"] < 50:
            continue
        last = [r for r in rows if r["player"] == p and (r["kills"] or "").isdigit() and (r["deaths"] or "").isdigit()]
        kills = int(last[-1]["kills"]) if last else 0
        deaths = int(last[-1]["deaths"]) if last else 0
        alive_s = b["alive"] / 5.0
        w = [windows[p].get(i, 0) for i in range(int(minutes * 2) + 1)]
        res = {
            "kills/min": kills / minutes, "deaths/min": deaths / minutes,
            "moved per 5 s": b["moved"] / alive_s * 5, "stood still %": 100 * b["still"] / b["alive"],
            "jumps/min": b["jumps"] / alive_s * 60, "in the air %": 100 * b["air"] / b["alive"],
            "crouched %": 100 * b["crouch"] / b["alive"], "fighting %": 100 * b["fighting"] / b["alive"],
            "fight distance": b["fight_dist"] / b["fight_samples"] if b["fight_samples"] else float("nan"),
            "trigger held in fights %": 100 * b["trigger"] / b["fight_samples"] if b["fight_samples"] else float("nan"),
            "low shields in fights %": 100 * b["fight_low_shield"] / b["fight_samples"] if b["fight_samples"] else float("nan"),
            "grenades/min": b["grenades"] / alive_s * 60, "in a vehicle %": 100 * b["vehicle"] / b["alive"],
            "power weapon %": 100 * b["power"] / b["alive"],
            "nearest player": b["near_any"] / b["alive"],
            "nearest teammate": b["near_mate"] / b["mate_samples"] if b["mate_samples"] else float("nan"),
            "map covered (cells)": len(visited[p]),
            "goal item %": 100 * b["goal_item"] / b["alive"], "goal hold %": 100 * b["goal_hold"] / b["alive"],
            "goal roam %": 100 * b["goal_roam"] / b["alive"], "goal enemy %": 100 * b["goal_enemy"] / b["alive"],
            "lurking %": 100 * b["goal_lurk"] / b["alive"],
            "kills from side/behind %": 100 * b["kill_flank"] / b["kills_seen"] if b["kills_seen"] else float("nan"),
            "kills on the busy %": 100 * b["kill_busy"] / b["kills_seen"] if b["kills_seen"] else float("nan"),
            "kills on the just spawned %": 100 * b["kill_fresh"] / b["kills_seen"] if b["kills_seen"] else float("nan"),
            "deaths where it died before %": 100 * b["death_again"] / b["deaths_seen"] if b["deaths_seen"] else float("nan"),
            "deaths to a third party %": 100 * b["death_by_other"] / b["deaths_seen"] if b["deaths_seen"] else float("nan"),
            "kills per 30 s, spread": (st.pstdev(w) / st.mean(w)) if len(w) > 2 and st.mean(w) > 0 else float("nan"),
        }
        out[p] = res
    return out, traits


def compare(paths, trait):
    low, high = defaultdict(list), defaultdict(list)
    for path in paths:
        bots, traits = measure(path)
        values = [traits[p].get(trait) for p in bots if p in traits and trait in traits[p]]
        if not values:
            continue
        middle = st.median(values)
        for p, res in bots.items():
            v = traits.get(p, {}).get(trait)
            if v is None:
                continue
            side = low if v < middle or (v == middle and int(p) % 2 == 0) else high
            for k, x in res.items():
                if not math.isnan(x):
                    side[k].append(x)
    rows = []
    for k in low:
        a, b = low[k], high.get(k, [])
        if len(a) < 2 or len(b) < 2:
            continue
        spread = st.pstdev(a + b) or 1e-9
        rows.append((k, st.mean(a), st.mean(b), (st.mean(b) - st.mean(a)) / spread, len(a), len(b)))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trait")
    ap.add_argument("--min", type=float, default=0.0, help="only the measures with an effect at least this big")
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args()
    if a.trait:
        rows = compare(a.paths, a.trait)
        print(f"{a.trait}: low half against high half ({len(a.paths)} recordings)")
        for k, lo, hi, eff, nl, nh in sorted(rows, key=lambda r: -abs(r[3])):
            if abs(eff) >= a.min:
                print(f"  {k:32s} {lo:8.2f} -> {hi:8.2f}   effect {eff:+.2f}")
        return
    for path in a.paths:
        bots, traits = measure(path)
        print(path)
        for p, res in sorted(bots.items(), key=lambda kv: int(kv[0])):
            print("  bot", p, ", ".join(f"{k} {v:.1f}" for k, v in res.items() if not math.isnan(v)))


if __name__ == "__main__":
    main()
