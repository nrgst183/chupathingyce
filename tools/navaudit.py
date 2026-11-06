#!/usr/bin/env python3
"""navaudit.py [--points points.json] dump.txt...: looks for faults in a navigation dump.

The dump: a game run with HALO_BOT_NAVDUMP=u:\navdump.txt (written into its
save folder) and HALO_BOT_NOCACHE=1 (so that the navigation is built, not
read). --points: a JSON file of {"map": [[x, y, z], ...]}, the places the main
body of the map is the part of (the flags); without it, the largest part.

  traps      groups of areas a bot can get into and not out of (a sink of the
             reachability graph that is not the main body of the map)
  islands    sizeable areas nothing reaches (floor the routes never use)
  dead ends  areas with ways in and none out
  slivers    areas thinner than a body
  odd links  walks up more than a step; jumps straight up (no run at them);
             gaps that end below where a drop would; links to themselves; doubles
"""
import sys, math, collections

TRAVEL = {0: "walk", 1: "jump", 2: "drop", 3: "gap", 4: "ladder", 5: "teleport"}


def load(path):
    areas, reaches = {}, []
    for line in open(path):
        p = line.split()
        if p[0] == "a":
            areas[int(p[1])] = tuple(map(float, p[2:8]))
        elif p[0] == "r":
            reaches.append({"id": int(p[1]), "travel": int(p[2]), "from": int(p[3]), "to": int(p[4]),
                            "start": tuple(map(float, p[5:8])), "edge": tuple(map(float, p[8:11])),
                            "end": tuple(map(float, p[11:14])), "time": float(p[14]), "careful": int(p[16])})
    return areas, reaches


def sccs(nodes, out):
    index, low, on, stack, result, counter = {}, {}, set(), [], [], [0]
    sys.setrecursionlimit(100000)

    def visit(v):
        work = [(v, iter(out[v]))]
        index[v] = low[v] = counter[0]; counter[0] += 1; stack.append(v); on.add(v)
        while work:
            node, it = work[-1]
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]; counter[0] += 1; stack.append(w); on.add(w)
                    work.append((w, iter(out[w])))
                    break
                elif w in on:
                    low[node] = min(low[node], index[w])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    comp = []
                    while True:
                        w = stack.pop(); on.discard(w); comp.append(w)
                        if w == node:
                            break
                    result.append(comp)
    for v in nodes:
        if v not in index:
            visit(v)
    return result


def size(a):
    return max(a[2] - a[0], 0) * max(a[3] - a[1], 0)


def area_at(areas, p):
    for k, a in areas.items():
        if a[0] - 0.05 <= p[0] <= a[2] + 0.05 and a[1] - 0.05 <= p[1] <= a[3] + 0.05 and abs(a[4] - p[2] + 0.1) < 0.6:
            return k
    return None


def audit(path, points=()):
    areas, reaches = load(path)
    out = collections.defaultdict(set)
    inc = collections.defaultdict(set)
    for r in reaches:
        if r["from"] in areas and r["to"] in areas:
            out[r["from"]].add(r["to"]); inc[r["to"]].add(r["from"])
    nodes = list(areas)
    comps = sccs(nodes, out)
    comp_of = {v: i for i, c in enumerate(comps) for v in c}
    main = max(range(len(comps)), key=lambda i: sum(size(areas[v]) for v in comps[i]))
    # (the main body: where the flags are, when they are given)
    for p in points:
        a = area_at(areas, p)
        if a is not None:
            main = comp_of[a]
            break
    # what the main body reaches, and what reaches it
    def flood(start, edges):
        seen = set(start); todo = list(start)
        while todo:
            v = todo.pop()
            for w in edges[v]:
                if w not in seen:
                    seen.add(w); todo.append(w)
        return seen
    from_main = flood(comps[main], out)
    to_main = flood(comps[main], inc)
    # traps: got into from the main body, never back to it
    trapped = [v for v in from_main if v not in to_main]
    trap_groups = collections.defaultdict(list)
    for v in trapped:
        trap_groups[comp_of[v]].append(v)
    traps = []
    for c, vs in trap_groups.items():
        # (a sink: nothing out of the group but to other trapped areas)
        area = sum(size(areas[v]) for v in vs)
        ways_in = [r for r in reaches if r["to"] in vs and r["from"] not in vs and r["from"] in to_main]
        traps.append((area, vs, ways_in))
    traps.sort(key=lambda t: -t[0])
    islands = [v for v in nodes if v not in from_main and size(areas[v]) >= 1.0]
    dead = [v for v in nodes if inc[v] and not out[v]]
    slivers = [v for v in nodes if min(areas[v][2] - areas[v][0], areas[v][3] - areas[v][1]) < 0.15]
    odd = collections.defaultdict(list)
    seen = collections.Counter()
    for r in reaches:
        s, e, d = r["start"], r["end"], r["edge"]
        horiz = math.hypot(e[0] - d[0], e[1] - d[1])
        if r["from"] == r["to"]:
            odd["link to itself"].append(r)
        key = (r["from"], r["to"], r["travel"])
        seen[key] += 1
        if seen[key] == 2:
            odd["double link"].append(r)
        if r["travel"] == 0 and e[2] - s[2] > 0.6:
            odd["walk up more than a step"].append(r)
        if r["travel"] == 1 and math.hypot(e[0] - s[0], e[1] - s[1]) < 0.2:
            odd["jump with no step forward"].append(r)
        if r["travel"] == 3 and horiz < 0.3:
            odd["gap under a body across"].append(r)
        if r["travel"] in (1, 3) and e[2] - d[2] > 0.75:
            odd["jump up past what a jump reaches"].append(r)
        if r["travel"] == 0 and math.hypot(e[0] - s[0], e[1] - s[1]) > 1.5:
            odd["walk longer than an area edge"].append(r)
        if r["time"] <= 0 and r["travel"] not in (0, 5):
            odd["costs nothing"].append(r)
    return areas, reaches, comps, main, traps, islands, dead, slivers, odd


def report(path, points=()):
    areas, reaches, comps, main, traps, islands, dead, slivers, odd = audit(path, points)
    name = path.split("/")[-1].replace(".txt", "")
    print("== %s: %d areas, %d links, main body %d areas" % (name, len(areas), len(reaches), len(comps[main])))
    ss = sorted(size(a) for a in areas.values())
    print("  floor %.0f sq units, median area %.3f sq units" % (sum(ss), ss[len(ss) // 2]))
    print("  traps %d (%.1f sq units), islands >=1 sq unit %d (%.1f sq units), dead ends %d, one cell wide %d (%.0f%%)" % (
        len(traps), sum(t[0] for t in traps), len(islands), sum(size(areas[v]) for v in islands), len(dead), len(slivers),
        100.0 * len(slivers) / max(len(areas), 1)))
    for area, vs, ways_in in traps[:5]:
        a = areas[vs[0]]
        kinds = collections.Counter(TRAVEL[r["travel"]] for r in ways_in)
        print("    trap %.1f sq at %.1f %.1f %.1f (%d areas), in by %s" % (area, (a[0] + a[2]) / 2, (a[1] + a[3]) / 2, a[4], len(vs), dict(kinds)))
    for v in sorted(islands, key=lambda v: -size(areas[v]))[:3]:
        a = areas[v]
        print("    island %.1f sq at %.1f %.1f %.1f" % (size(a), (a[0] + a[2]) / 2, (a[1] + a[3]) / 2, a[4]))
    for k, rs in odd.items():
        r = rs[0]
        print("  %-36s %4d  e.g. %d %s %s -> %s" % (k, len(rs), r["id"], TRAVEL[r["travel"]], r["start"], r["end"]))


import json, os
args = sys.argv[1:]
POINTS = {}
if args[:1] == ["--points"]:
    POINTS = json.load(open(args[1]))
    args = args[2:]
for p in args:
    key = os.path.basename(p).replace(".txt", "").replace("_ce", "@ce")
    report(p, POINTS.get(key, ()))
