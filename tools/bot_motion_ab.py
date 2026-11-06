#!/usr/bin/env python3
"""bot_motion_ab.py run TAG maps bots secs seeds variant...   (variant: path to a build[:HALO_BOT_OFF names])
   bot_motion_ab.py cmp TAG variantA variantB [metric...]
   bot_motion_ab.py re TAG                                   (the figures again from kept logs)

Environment: BOT_MOTION_DATA, the folder with maps/ in it; BOT_MOTION_POINTS, a JSON file of
{"map": [[x, y, z], ...]} (the places each map is toured round: its flag bases); BOT_MOTION_DIR,
where the results (motion_TAG.json) and, with KEEP=1, the games' logs go (default: here).

run: each map, seed and variant toured (HALO_BOT_GOTO=tour round the map's flag bases, HALO_BOT_TRAJ),
     the figures of tools/bot_motion.py for each, into motion_TAG.json (added to).
cmp: the same games of two variants side by side: for each figure, the mean of A, of B, the mean
     difference per game with a 95% interval (bootstrap over the games), and how many games went
     each way."""
import sys, os, json, shutil, subprocess, tempfile, random, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot_motion

POINTS = json.load(open(os.environ.get("BOT_MOTION_POINTS", "points.json")))
DATA = os.environ.get("BOT_MOTION_DATA", ".")
HERE = os.environ.get("BOT_MOTION_DIR", ".")
LOCK = threading.Lock()


def play(k, binary, off, m, seed, bots, secs, extra):
    w = tempfile.mkdtemp(prefix="mo_")
    exe = w + "/game"
    shutil.copy(binary, exe)
    pts = POINTS[m]
    env = dict(os.environ)
    env.update({"SDL_VIDEO_DRIVER": "dummy", "SDL_AUDIO_DRIVER": "dummy", "HALO_NULL_RENDERER": "1", "HALO_NO_AUDIO": "1",
                "HALO_NET_ONLINE": "false", "HALO_UPDATE_AUTO": "false", "HALO_DATA_ROOT": DATA, "HALO_SAVE_ROOT": w + "/save",
                "HALO_NET_ADDRESS": "127.0.0.%d" % (200 + k % 2), "HALO_NET_BROADCAST": "127.0.0.%d" % (200 + k % 2),
                "HALO_NETWORK_TEST": "local:%s:slayer" % m, "HALO_NETWORK_TEST_START": "3", "HALO_BOTS": str(bots),
                "HALO_RANDOM_SEED": str(seed), "HALO_BOT_SKILL": "10", "HALO_GAME_SPEED": "3", "HALO_BOT_LOG": "1",
                "HALO_BOT_NOCACHE": "1", "HALO_BOT_TRAJ": "1", "HALO_BOT_GOTO": "tour", "HALO_BOT_PEACE": "1",
                "HALO_BOT_TOUR": ";".join("%.2f,%.2f,%.2f" % tuple(p) for p in pts), "HALO_BOT_OFF": off})
    env.update(extra)
    try:
        with open(w + "/o", "w") as f:
            for _ in range(20):
                try:
                    subprocess.run([exe], cwd=w, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=secs)
                    break
                except subprocess.TimeoutExpired:
                    break
                except OSError as e:
                    if e.errno != 26:
                        raise
                    import time
                    time.sleep(0.5)
        text = open(w + "/o", errors="replace").read()
    finally:
        subprocess.run(["pkill", "-9", "-f", exe], capture_output=True)
        shutil.rmtree(w, ignore_errors=True)
    r = bot_motion.analyse(text, [tuple(q) for q in pts])
    r["crash"] = "EXCEPTION" in text or "segmentation" in text.lower()
    if os.environ.get("KEEP"):
        open(HERE + "/mo_%s_%s_%s_%s.txt" % (os.path.basename(binary) + off, m.replace("@", "_"), seed, bots), "w").write(text)
    return r


def run(tag, maps, bots, secs, seeds, variants):
    path = HERE + "/motion_%s.json" % tag
    results = json.load(open(path)) if os.path.exists(path) else {}
    jobs = [(v, m, s) for m in maps for s in seeds for v in variants if "%s|%s|%s|%s" % (v, m, s, bots) not in results]

    def one(a):
        k, (v, m, s) = a
        b, _, off = v.partition(":")
        r = play(k, b, off, m, s, bots, secs, {})
        key = "%s|%s|%s|%s" % (v, m, s, bots)
        with LOCK:
            results[key] = r
            json.dump(results, open(path, "w"), indent=0)
        print("%-26s %-14s s%-3s %s" % (v[-26:], m, s, " ".join("%s %s" % (k2, r[k2]) for k2 in
              ("pace", "held", "swerve", "zigzag", "dither", "facing", "falls", "bumps", "legs", "leg_s", "ratio"))), flush=True)
    with ThreadPoolExecutor(2) as p:
        list(p.map(one, enumerate(jobs)))


def cmp(tag, a, b, metrics):
    results = json.load(open(HERE + "/motion_%s.json" % tag))
    games = {}
    for key, r in results.items():
        v, m, s, bots = key.split("|")
        games.setdefault((m, s, bots), {})[v] = r
    both = [(g, d[a], d[b]) for g, d in sorted(games.items()) if a in d and b in d]
    metrics = metrics or ["legs", "leg_s", "pace", "held", "swerve", "swerve95", "zigzag", "dither", "facing", "falls", "bumps", "given_up"]
    print("%d games both have" % len(both))
    random.seed(1)
    for k in metrics:
        pairs = [(ra[k], rb[k]) for g, ra, rb in both if ra.get(k) is not None and rb.get(k) is not None]
        if not pairs:
            continue
        d = [y - x for x, y in pairs]
        ma = sum(x for x, y in pairs) / len(pairs)
        mb = sum(y for x, y in pairs) / len(pairs)
        boots = sorted(sum(random.choice(d) for _ in d) / len(d) for _ in range(2000))
        lo, hi = boots[50], boots[1949]
        up = sum(1 for x in d if x > 0)
        down = sum(1 for x in d if x < 0)
        sure = "  *" if lo > 0 or hi < 0 else ""
        print("%-9s A %8.3f  B %8.3f  B-A %+8.3f (%+.1f%%)  95%% [%+.3f, %+.3f]  B higher in %d, lower in %d%s" %
              (k, ma, mb, mb - ma, 100.0 * (mb - ma) / ma if ma else 0.0, lo, hi, up, down, sure))


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3].split(","), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6].split(","), sys.argv[7:])
    elif sys.argv[1] == "cmp":
        cmp(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:])


def reanalyse(tag):
    """the figures again from the kept logs (logs/mo_*), after the analysis changes"""
    import glob, re as _re
    path = HERE + "/motion_%s.json" % tag
    results = json.load(open(path))
    for key in list(results):
        v, m, s, bots = key.split("|")
        b, _, off = v.partition(":")
        log = HERE + "/mo_%s_%s_%s_%s.txt" % (os.path.basename(b) + off, m.replace("@", "_"), s, bots)
        if os.path.exists(log):
            text = open(log, errors="replace").read()
            r = bot_motion.analyse(text, [tuple(q) for q in POINTS[m]])
            r["crash"] = "EXCEPTION" in text or "segmentation" in text.lower()
            results[key] = r
    json.dump(results, open(path, "w"), indent=0)


if __name__ == "__main__" and sys.argv[1] == "re":
    reanalyse(sys.argv[2])
