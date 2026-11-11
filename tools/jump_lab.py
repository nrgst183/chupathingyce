#!/usr/bin/env python3
"""Made-up jumps up, tried by a bot (HALO_BOT_REPLAY, port/linux/game/move_log.c), to find what a jump up takes.

    python3 tools/jump_lab.py make MAP N out.txt     N ledges of MAP, from a navigation dump nav/MAP.txt (HALO_BOT_NAVDUMP; HALO_BOT_HIGHRISE=1.15 for the high ones), each tried every way
    JUMP_LAB_GAME=build/linux64/chupathingy JUMP_LAB_DATA=~/halo python3 tools/jump_lab.py run out.txt log.txt
    python3 tools/jump_lab.py score out.txt log.txt   made or not, and how quick

Each way: off the ground 0.5 to 2.1 from the face, after a run of 2.2 at a full run, and the legs not tucked, tucked
from the third tick, tucked so the lift is done three ticks before the face (held, or a tap of four ticks), or held from
six before."""
import sys, os, json, math, random, re, shutil, subprocess, tempfile, collections
RUN = 2.25; TICK = 1 / 30.0
# techniques: (name, takeoff distance from the face, tuck) ; tuck: None, ("early",), ("late", lead), ("tap", lead, length)
DISTANCES = [0.5, 0.9, 1.3, 1.7, 2.1]
TUCKS = [("none",), ("early",), ("late", 3), ("tap", 3, 4), ("hold", 6)]
def load(m):
    g = None; spans = collections.defaultdict(list); R = []
    for line in open(os.path.join(os.environ.get("JUMP_LAB_NAV", "nav"), "%s.txt" % m)):
        f = line.split()
        if f[0] == "grid": g = (float(f[1]), float(f[2]))
        elif f[0] == "s": spans[(int(f[1]), int(f[2]))].append(float(f[3]))
        elif f[0] == "r" and f[2] == "1": R.append(dict(id=int(f[1]), start=tuple(map(float, f[5:8])), edge=tuple(map(float, f[8:11])), end=tuple(map(float, f[11:14]))))
    return g, spans, R
def floor(g, spans, x, y, z, tol=0.12):
    c = (int((x - g[0]) / 0.1), int((y - g[1]) / 0.1))
    return any(abs(v - z) < tol for v in spans.get(c, []))
def make(m, n, out):
    random.seed(m)
    g, spans, R = load(m)
    picked = []
    random.shuffle(R)
    for r in R:
        rise = r["end"][2] - r["edge"][2]
        if not 0.35 <= rise <= 1.15: continue
        dx, dy = r["end"][0] - r["edge"][0], r["end"][1] - r["edge"][1]; d = math.hypot(dx, dy)
        if d < 0.05: continue
        fx, fy = dx / d, dy / d
        ez = r["edge"][2]
        # (run-up floor, level, 4.5 units straight back; floor on top 0.8 past where it lands)
        if not all(floor(g, spans, r["edge"][0] - fx * k, r["edge"][1] - fy * k, ez) for k in [0.3 + 0.2 * i for i in range(22)]): continue
        if not all(floor(g, spans, r["end"][0] + fx * k, r["end"][1] + fy * k, r["end"][2], 0.15) for k in (0.3, 0.6, 0.8)): continue
        if any(math.dist(r["edge"], p["edge"]) < 2.5 for p in picked): continue
        # (the face: the first cell along the line whose floor is the top's)
        face = None
        for i in range(0, 15):
            k = 0.1 * i
            if floor(g, spans, r["edge"][0] + fx * k, r["edge"][1] + fy * k, r["end"][2], 0.15): face = k; break
        if face is None: continue
        picked.append(dict(r, rise=round(rise, 2), f=(fx, fy), face=face))
        if len(picked) >= n: break
    lines = []; meta = []
    for p in picked:
        fx, fy = p["f"]; yaw = math.atan2(fy, fx)
        # (the face's line: edge + f*face; distances from there)
        fxp, fyp = p["edge"][0] + fx * p["face"], p["edge"][1] + fy * p["face"]
        for D in DISTANCES:
            for t in TUCKS:
                run = 2.2  # (units of run before the take-off, at full speed)
                sx, sy = fxp - fx * (D + 0.2 + run), fyp - fy * (D + 0.2 + run)
                jump_tick = int(round(run / (RUN * TICK)))
                total = jump_tick + 50
                # (when it gets to the face: about D/RUN after the jump)
                t_face = jump_tick + 1 + int(round(D / (RUN * TICK)))
                rows = []
                for k in range(total):
                    jump = 1 if jump_tick <= k < jump_tick + 3 else 0
                    crouch = 0
                    if t[0] == "early": crouch = 1 if jump_tick + 3 <= k < jump_tick + 33 else 0
                    elif t[0] == "late": crouch = 1 if max(jump_tick + 2, t_face - 6 - t[1]) <= k < jump_tick + 33 else 0
                    elif t[0] == "tap": crouch = 1 if max(jump_tick + 2, t_face - 6 - t[1]) <= k < max(jump_tick + 2, t_face - 6 - t[1]) + t[2] else 0
                    elif t[0] == "hold": crouch = 1 if max(jump_tick + 2, t_face - 6 - t[1]) <= k < jump_tick + 33 else 0
                    vx = RUN * fx if k == 0 else 0; vy = RUN * fy if k == 0 else 0
                    rows.append("%.4f %.4f %.4f %.3f %.3f 0 %.4f 0 1 0 %d %d" % (sx, sy, p["edge"][2], vx, vy, yaw, jump, crouch))
                meta.append(dict(map=m, id=p["id"], rise=p["rise"], D=D, tuck="-".join(map(str, t)), target=p["end"], face=(fxp, fyp), f=p["f"], jump_tick=jump_tick))
                lines.append("# %s %d" % (m, jump_tick))
                lines.extend(rows)
    open(out, "w").write("\n".join(lines) + "\n")
    json.dump(meta, open(out + ".json", "w"))
    print(out, len(picked), "ledges", len(meta), "stretches")
def run(out, log, speed="10"):
    m = json.load(open(out + ".json"))[0]["map"]
    w = tempfile.mkdtemp(prefix="jl_", dir=None); shutil.copy(os.environ.get("JUMP_LAB_GAME", "build/linux64/chupathingy"), w + "/game")
    env = dict(os.environ, SDL_VIDEO_DRIVER="dummy", SDL_AUDIO_DRIVER="dummy", HALO_NULL_RENDERER="1", HALO_NO_AUDIO="1", HALO_NET_ONLINE="false",
               HALO_UPDATE_AUTO="false", HALO_DATA_ROOT=os.environ.get("JUMP_LAB_DATA", "."), HALO_SAVE_ROOT=w + "/save",
               HALO_NETWORK_TEST="local:%s:slayer" % m, HALO_NETWORK_TEST_START="3", HALO_BOTS="1", HALO_BOT_PEACE="1", HALO_GAME_SPEED=speed,
               HALO_BOT_REPLAY=os.path.abspath(out), HALO_BOT_REPLAY_TIMES="1", HALO_BOT_REPLAY_WAIT="20")
    env.setdefault("HALO_NET_ADDRESS", "127.0.0.%d" % (100 + hash(out) % 50)); env["HALO_NET_BROADCAST"] = env["HALO_NET_ADDRESS"]
    n = len(json.load(open(out + ".json")))
    try:
        with open(log, "w") as f:
            try: subprocess.run([w + "/game"], cwd=w, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=60 + n * 110 / 30.0 / float(speed) * 1.3)
            except subprocess.TimeoutExpired: pass
    finally:
        subprocess.run(["pkill", "-9", "-f", w + "/game"], capture_output=True); shutil.rmtree(w, ignore_errors=True)
def score(out, logs):
    meta = json.load(open(out + ".json"))
    paths = collections.defaultdict(dict)
    for log in logs:
        for l in open(log, errors="replace"):
            mm = re.search(r"replay (\d+) (\d+) (\S+) (\S+) (\S+) (\d)", l)
            if mm: paths[int(mm.group(1))][int(mm.group(2))] = tuple(map(float, mm.group(3, 4, 5)))
    res = []
    for i, m in enumerate(meta):
        p = paths.get(i)
        if not p: continue
        tz = m["target"][2]; fx, fy = m["f"]
        made_at = None
        for k in sorted(p):
            x, y, z = p[k]
            past = (x - m["face"][0]) * fx + (y - m["face"][1]) * fy
            if past > 0.25 and abs(z - tz) < 0.12:
                made_at = k; break
        res.append(dict(m, made=made_at is not None, ticks=(made_at - m["jump_tick"]) if made_at is not None else None))
    return res
if __name__ == "__main__":
    if sys.argv[1] == "make": make(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    elif sys.argv[1] == "run": run(sys.argv[2], sys.argv[3])
    else:
        R = score(sys.argv[2], sys.argv[3:])
        json.dump(R, open(sys.argv[2] + ".score.json", "w"))
        print(len(R), "scored,", sum(r["made"] for r in R), "made")
