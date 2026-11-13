"""Play qw on a list of seeds (or a jobs file of forks) in parallel in the DCSS container.

    uv run python tools/qw/run.py --seeds 500000-500059 [--workers 6] [--time-limit 1800]
                                  [--name NAME | --out DIR] [--repeat 2]
                                  [--action-log | --state-log] [--lib-dir /data/qw/lib]
    uv run python tools/qw/run.py --jobs forks.json --state-log --name forks1
    uv run python tools/qw/run.py --seeds 500000-500005 --policy my_policy.lua --state-log

A jobs file is a JSON list of {"seed": 500000, "tag": "500000-tele-812",
"overrides": {"812": {"force": "teleport"}, "900": {"veto": ["melee"], "n": 5}},
"base": "runs/qw/base1/games/500000"}. Overrides are keyed by qw decision index (see
tools/qw/ladder.lua) and reach the game as LADDER_OVERRIDES in that game's rc. "tag" names
the output directory (default "<seed>-<n>"). With "base" (a game directory with an action
or state log), the row gets prefix_match: whether the fork's decisions before its first
override equal the base game's (crawl 0.34 is not always reproducible across processes).

Each game runs as its own console crawl process inside the container in headless mode
(`crawl -headless`: no terminal; any key crawl waits for that qw didn't send reads as
Escape, so death and end-of-game screens close by themselves and the process exits).
No webtiles, no accounts. Worker i has its own save directory under /data/qw/runs/NAME/wI,
so its logfile, scores and qw's c_persist file (<rc>.persist) are its own.

Output in --out (default runs/qw/NAME/):
  results.json      {"meta", "summary", "games": one row per game}
  games/<tag>/      morgue.txt, logfile.txt (the logfile line), and qw's QW* stderr lines
                    as stderr.log, or stderr.log.gz with --state-log (read with log.py)

Plain stdlib. Builds and deploys qw to --lib-dir first (tools/qw/build.py) unless
--no-build.
"""

from __future__ import annotations

import argparse
import gzip
import json
import queue
import re
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import build as qwbuild  # noqa: E402

CONTAINER = qwbuild.CONTAINER
LIB_DIR = qwbuild.LIB_DIR
RUNS_DIR = "/data/qw/runs"
CRAWL = "/crawl/crawl"
MAX_ERRORS = 500  # QWERR lines before a game is treated as stuck in an error loop
PRIMITIVES = {"reroll", "reroll2", "berserk", "trogs_hand", "brothers_in_arms", "teleport", "heal_wounds",
              "flee", "stairs_up", "rest", "attack", "retreat_step", "throw",
              "choke", "stairs_fight"}
NAME_RE = re.compile(r"[A-Za-z0-9_.-]+")

# Each game runs under this. The container's PID 1 is the webtiles server, which never
# waits for processes it did not start, so a crawl whose parent died before it (a killed
# game) stayed in the process table as a zombie for the life of the container. As a child
# subreaper this process inherits such orphans and waits for them.
REAPER = """\
import ctypes, os, sys
ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)  # PR_SET_CHILD_SUBREAPER
main = os.fork()
if main == 0:
    os.execvp(sys.argv[1], sys.argv[1:])
status = 0
while True:
    try:
        pid, st = os.wait()
    except ChildProcessError:
        break
    if pid == main:
        status = st
code = os.waitstatus_to_exitcode(status)
sys.exit(code if code >= 0 else 128 - code)
"""


# --- container helpers -------------------------------------------------------------------


def in_container(container: str, *args: str, check: bool = True):
    return subprocess.run(
        ["docker", "exec", container, *args], check=check, capture_output=True, text=True
    )


def put_file(container: str, path: str, text: str) -> None:
    subprocess.run(
        ["docker", "exec", "-i", container, "tee", path],
        input=text, text=True, check=True, capture_output=True,
    )


# --- parsing -----------------------------------------------------------------------------


def parse_logline(line: str) -> dict[str, str]:
    """Crawl logfile line: key=value fields separated by ':', a literal ':' written '::'."""
    fields = {}
    for part in re.split(r"(?<!:):(?!:)", line.strip()):
        if "=" in part:
            k, v = part.split("=", 1)
            fields[k] = v.replace("::", ":")
    return fields


BRANCH_RE = re.compile(r"([A-Z][A-Za-z' ]+?) \((\d+)/(\d+)\)")


def parse_morgue(text: str) -> dict:
    """Deepest level per branch from the dump's 'Branches:' overview, e.g. 'Dungeon (11/15)'.

    A branch whose entrance was found but never entered shows as (0/N); it is left out.
    """
    out: dict = {"branches": {}}
    m = re.search(r"\nBranches:\n(.*?)\n\n", text, re.S)
    if m:
        for name, deepest, _ in BRANCH_RE.findall(m.group(1)):
            if int(deepest) > 0:
                out["branches"][name.strip()] = int(deepest)
    m = re.search(r"saw (\d+) of its levels", text)
    if m:
        out["levels_seen"] = int(m.group(1))
    return out


def place_depth(place: str) -> tuple[str, int]:
    if ":" in place:
        br, d = place.split(":", 1)
        return br, int(d) if d.isdigit() else 1
    return place, 1


# Branch names as you.where() spells them -> as the dump overview does.
BRANCH_LONG = {"D": "Dungeon", "Orc": "Orcish Mines", "Elf": "Elven Halls",
               "Snake": "Snake Pit", "Spider": "Spider Nest", "Slime": "Slime Pits",
               "Swamp": "Swamp", "Shoals": "Shoals", "Lair": "Lair", "Vaults": "Vaults",
               "Crypt": "Crypt", "Tomb": "Tomb", "Depths": "Depths", "Zot": "Zot",
               "Temple": "Temple"}


# --- overrides -----------------------------------------------------------------------------


def check_spec(spec: dict) -> None:
    if not isinstance(spec, dict) or not ({"force", "veto"} & spec.keys()):
        raise SystemExit(f"override spec needs force or veto: {spec!r}")
    if "force" in spec and spec["force"] not in PRIMITIVES:
        raise SystemExit(f"unknown primitive {spec['force']!r}; one of {sorted(PRIMITIVES)}")
    for name in spec.get("veto", []):
        if not re.fullmatch(r"[a-z_0-9]+", name):
            raise SystemExit(f"bad plan name {name!r}")
    if not isinstance(spec.get("n", 1), int) or spec.get("n", 1) < 1:
        raise SystemExit(f"n must be a positive integer: {spec!r}")


def overrides_lua(overrides: dict) -> str:
    """{"812": {"force": "teleport", "n": 2}} -> '{ [812] = { force = "teleport", n = 2 } }'."""
    items = []
    for key, spec in sorted(overrides.items(), key=lambda kv: int(kv[0])):
        check_spec(spec)
        fields = []
        if "force" in spec:
            fields.append(f'force = "{spec["force"]}"')
        if "veto" in spec:
            fields.append("veto = { " + ", ".join(f'"{v}"' for v in spec["veto"]) + " }")
        fields.append(f"n = {int(spec.get('n', 1))}")
        items.append(f"[{int(key)}] = {{ " + ", ".join(fields) + " }")
    return "{ " + ", ".join(items) + " }"


def _actions(game_dir: Path) -> list[str]:
    for name, opener in (("stderr.log.gz", gzip.open), ("stderr.log", open)):
        if (game_dir / name).exists():
            with opener(game_dir / name, "rt", encoding="utf-8", errors="replace") as fh:
                return [line.rstrip("\n") for line in fh if line.startswith("QWACT\t")]
    return []


def prefix_check(base: Path, fork: Path, overrides: dict) -> dict:
    """Compare a fork's QWACT lines with its base game's before the first override.

    Crawl 0.34 is not fully reproducible across processes (see tools/qw/ladder.lua on
    pairs(); level generation can also differ), so a fork is only a fork of its base if
    the decisions before the first override match.
    """
    k = min((int(d) for d in overrides), default=None)
    a, b = _actions(base), _actions(fork)
    if not a or not b:
        return {"prefix_match": None, "prefix_note": "base or fork has no action log"}
    longest = max(len(a), len(b))
    n = min(k, longest) if k is not None else longest
    first = next((i for i, (x, y) in enumerate(zip(a[:n], b[:n])) if x != y), None)
    if first is None and min(len(a), len(b)) < n:
        first = min(len(a), len(b))  # one game ended before the other
    return {"prefix_match": first is None, "prefix_decisions": n,
            "prefix_first_diff": first}


# --- games -------------------------------------------------------------------------------


class Runner:
    def __init__(self, args, out: Path):
        self.args = args
        self.out = out
        self.container = args.container
        self.lib_dir = args.lib_dir
        self.run_dir = f"{RUNS_DIR}/{args.name}"
        self.policy = args.policy.read_text(encoding="utf-8") if args.policy else None
        self.lua = args.lua.read_text(encoding="utf-8") if args.lua else None
        self.lock = threading.Lock()
        self.done = 0

    def sh(self, script: str, check: bool = False):
        return in_container(self.container, "sh", "-c", script, check=check)

    def worker_dir(self, w: int) -> str:
        return f"{self.run_dir}/w{w}"

    def setup_workers(self) -> None:
        for w in range(1, self.args.workers + 1):
            d = self.worker_dir(w)
            in_container(self.container, "mkdir", "-p", f"{d}/saves", f"{d}/morgue")
        put_file(self.container, f"{self.run_dir}/reap.py", REAPER)

    def write_rc(self, w: int, overrides: dict | None) -> None:
        d = self.worker_dir(w)
        rc = [f"save_dir = {d}/saves", "include = qw-ladder.rc"]
        if self.args.action_log or self.args.state_log:
            rc.append(": LADDER_ACTION_LOG = true")
        if self.args.state_log:
            rc.append(": LADDER_STATE_LOG = true")
        if overrides:
            rc.append(": LADDER_OVERRIDES = " + overrides_lua(overrides))
        if self.lua:
            # A Lua block run after qw.lua: changes qw's settings or replaces its functions.
            # Its last line reports that the whole block ran: a block that fails part-way
            # would otherwise leave qw unchanged and look like a setting with no effect.
            rc += ["<", self.lua.rstrip("\n"), 'crawl.stderr("QWLUA\\tok")', ">"]
        if self.policy:
            # A Lua block that redefines ladder_choose(decision, state).
            rc += [": LADDER_POLICY_STATE = true", "<", self.policy.rstrip("\n"), ">"]
        put_file(self.container, f"{d}/qw.rc", "\n".join(rc) + "\n")

    def crawl_cmd(self, w: int, seed: int, name: str) -> list[str]:
        d = self.worker_dir(w)
        cmd = [
            "docker", "exec", "-e", "LANG=C.UTF-8", "-e", "TERM=xterm", "-w", "/crawl",
            self.container,
            "python3", f"{self.run_dir}/reap.py",
            "timeout", "-s", "KILL", str(self.args.time_limit),
            CRAWL, "-headless", "-name", name, "-seed", str(seed),
            "-lua-max-memory", "128", "-no-player-bones",
            "-rc", f"{d}/qw.rc", "-rcdir", self.lib_dir, "-morgue", f"{d}/morgue",
        ]
        # A "-- combo: GrBe.handaxe" line in the Lua file picks the character, so a
        # variant carries its combo wherever only the file is passed. Read here, per
        # game: the fleet plays several variants in one run, each with its own Lua.
        m = re.search(r"^-- combo: ([A-Za-z.]+)[ \t]*$", self.lua or "", re.M)
        combo = self.args.combo or (m.group(1) if m else None)
        if combo:
            cmd += ["-extra-opt-last", f"combo={combo}"]
        return cmd

    def kill_game(self, w: int, name: str) -> None:
        # Anchored: only crawl itself, not the timeout and reaper whose command lines
        # contain crawl's. They exit by themselves once crawl is gone.
        pattern = f"^{CRAWL} -headless -name {name} .*-rc {self.worker_dir(w)}/qw.rc"
        in_container(self.container, "pkill", "-KILL", "-f", pattern, check=False)

    def logfile_lines(self, w: int) -> list[str]:
        saves = f"{self.worker_dir(w)}/saves"
        r = self.sh(f"cat {saves}/logfile {saves}/logfile-seeded 2>/dev/null")
        return r.stdout.splitlines()

    def logfile_line(self, w: int, name: str, seed: int, before: set[str]) -> str | None:
        """The logfile line for this game: matching name and seed, and new since it started
        (so an earlier game of the same seed in this directory is never picked up)."""
        found = None
        for line in self.logfile_lines(w):
            if line in before:
                continue
            f = parse_logline(line)
            if f.get("name") == name and f.get("seed") == str(seed):
                found = line
        return found

    def morgue_text(self, w: int, name: str) -> str | None:
        r = self.sh(f"ls -t {self.worker_dir(w)}/morgue/morgue-{name}-*.txt 2>/dev/null"
                    " | head -1")
        path = r.stdout.strip()
        if not path:
            return None
        return in_container(self.container, "cat", path, check=False).stdout

    def clear_game(self, w: int, name: str) -> None:
        d = self.worker_dir(w)
        self.sh(f"rm -f {d}/saves/{name}.cs {d}/morgue/morgue-{name}-* "
                f"{d}/morgue/{name}.* {d}/morgue/crash-{name}-*")

    def play(self, w: int, job: dict) -> dict:
        seed, tag = job["seed"], job["tag"]
        name = f"q{seed}"
        gdir = self.out / "games" / tag
        gdir.mkdir(parents=True, exist_ok=True)
        self.clear_game(w, name)
        self.write_rc(w, job.get("overrides"))
        before = set(self.logfile_lines(w))

        counts = {"QWERR": 0, "QWPANIC": 0, "QWACT": 0, "QWOVR": 0, "QWS": 0, "QWLUA": 0}
        ovr_acted = 0
        places: list[tuple[int, str, int]] = []
        first_err = None
        killed = None
        stop_turn = job.get("stop_turn")
        last_xl = None
        if self.args.state_log:
            log = gzip.open(gdir / "stderr.log.gz", "wt", encoding="utf-8", compresslevel=6)
        else:
            log = open(gdir / "stderr.log", "w", encoding="utf-8", buffering=1)
        t0 = time.time()
        with log:
            p = subprocess.Popen(self.crawl_cmd(w, seed, name), stdout=subprocess.DEVNULL,
                                 stderr=subprocess.PIPE, text=True, errors="replace")
            for line in p.stderr:
                log.write(line)
                tagname, _, rest = line.partition("\t")
                if tagname in counts:
                    counts[tagname] += 1
                if tagname == "QWERR" and first_err is None:
                    first_err = rest.strip()
                elif tagname == "QWPLACE":
                    t, pl, xl = rest.rstrip("\n").split("\t")[:3]
                    places.append((int(t), pl, int(xl)))
                # QWOVR <decision> <spec> <acted> [extra fields from choke/stairs_fight]
                elif tagname == "QWOVR" and rest.rstrip("\n").split("\t")[2:3] == ["1"]:
                    ovr_acted += 1
                if tagname == "QWS":
                    at = rest.find("\txl=")
                    if at >= 0:
                        last_xl = int(rest[at + 4:rest.index("\t", at + 1)])
                elif tagname == "QWACT" and stop_turn and not killed:
                    # A fork only needs playing to its horizon: alive there is the answer.
                    if int(rest.split("\t", 2)[1]) >= stop_turn:
                        killed = "stopped"
                        self.kill_game(w, name)
                if counts["QWERR"] > MAX_ERRORS and not killed:
                    killed = "error_loop"
                    self.kill_game(w, name)
                if tagname == "QWSTALL" and not killed:
                    # qw is stuck with no turn passing; the game would only end at
                    # the time limit.
                    killed = "stalled"
                    self.kill_game(w, name)
            rc = p.wait()
        wall = time.time() - t0

        row: dict = {"tag": tag, "seed": seed, "rep": job.get("rep", 1), "worker": w,
                     "overrides": job.get("overrides") or None,
                     "wall_s": round(wall, 1), "exit": rc,
                     "qw_errors": counts["QWERR"], "qw_panics": counts["QWPANIC"],
                     "decisions_logged": counts["QWACT"], "states_logged": counts["QWS"],
                     "overrides_applied": counts["QWOVR"], "overrides_acted": ovr_acted,
                     "first_error": first_err,
                     "lua_loaded": counts["QWLUA"] > 0 if self.lua else None}
        line = self.logfile_line(w, name, seed, before)
        morgue = self.morgue_text(w, name) if line else None
        if line:
            f = parse_logline(line)
            (gdir / "logfile.txt").write_text(line + "\n", encoding="utf-8")
            row.update(
                status="done", xl=int(f.get("xl", 0)), place=f.get("place"),
                absdepth=int(f.get("absdepth", 0)), turns=int(f.get("turn", 0)),
                runes=int(f.get("urune", f.get("nrune", 0)) or 0), ktyp=f.get("ktyp"),
                killer=f.get("killer"), score=int(f.get("sc", 0)), god=f.get("god"),
                char=f.get("char"), tmsg=f.get("tmsg"),
            )
            # The game's last turn: death, quit, or escape (see ktyp).
            row["end_turn"] = row["turns"]
        else:
            # timeout -s KILL exits 137; anything else without a logfile line is a crash.
            row["status"] = killed or ("timeout" if rc in (124, 137) else "crash")
            row["runes"] = None
            row["end_turn"] = None
            if places:
                t, pl, xl = places[-1]
                row.update(xl=last_xl or xl, place=pl, turns_at_last_level=t)
        if morgue:
            (gdir / "morgue.txt").write_text(morgue, encoding="utf-8")
            row.update(parse_morgue(morgue))
        # Deepest D level: the larger of the dump's overview and qw's QWPLACE lines (the
        # overview can lag, e.g. after falling down a shaft and dying on arrival).
        ds = [place_depth(pl)[1] for _, pl, _ in places if place_depth(pl)[0] == "D"]
        overview = row.get("branches", {}).get("Dungeon")
        if overview is not None:
            ds.append(overview)
        row["deepest_d"] = max(ds) if ds else None
        xls = [xl for _, _, xl in places] + ([row["xl"]] if row.get("xl") else [])
        row["max_xl"] = max(xls) if xls else None
        entered = {BRANCH_LONG.get(place_depth(pl)[0], place_depth(pl)[0])
                   for _, pl, _ in places}
        entered |= set(row.get("branches", {}))
        row["branches_entered"] = sorted(entered)
        row["reached_lair"] = "Lair" in entered
        row["levels_entered"] = [pl for _, pl, _ in places]
        if job.get("base"):
            row.update(prefix_check(Path(job["base"]), gdir, job.get("overrides") or {}))
        if row["status"] != "done":
            self.kill_game(w, name)
            self.clear_game(w, name)
        return row

    def run(self, jobs: list[dict]) -> list[dict]:
        q: queue.Queue = queue.Queue()
        for j in jobs:
            q.put(j)
        rows: list[dict] = []

        def work(w: int) -> None:
            while True:
                try:
                    job = q.get_nowait()
                except queue.Empty:
                    return
                try:
                    row = self.play(w, job)
                except Exception as e:  # keep the batch going; record the failure
                    row = {"tag": job["tag"], "seed": job["seed"], "rep": job.get("rep", 1),
                           "worker": w, "status": "runner_error", "error": repr(e)}
                with self.lock:
                    rows.append(row)
                    self.done += 1
                    print(f"[{self.done}/{len(jobs)}] {row['tag']} w{w}: "
                          f"{row.get('status')} {row.get('place')} xl{row.get('xl')} "
                          f"t{row.get('turns')} {row.get('ktyp') or ''} "
                          f"{row.get('wall_s')}s err={row.get('qw_errors')}", flush=True)

        threads = [threading.Thread(target=work, args=(w,), daemon=True)
                   for w in range(1, self.args.workers + 1)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        order = {j["tag"]: i for i, j in enumerate(jobs)}
        return sorted(rows, key=lambda r: order[r["tag"]])


# --- summary -------------------------------------------------------------------------------


def stat(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {"mean": round(statistics.mean(vals), 2), "median": statistics.median(vals),
            "min": min(vals), "max": max(vals), "n": len(vals)}


def tally(values) -> dict:
    out: dict = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def summarize(rows: list[dict]) -> dict:
    done = [r for r in rows if r.get("status") == "done"]
    return {
        "games": len(rows),
        "status": tally(r.get("status", "?") for r in rows),
        "deepest_d_all": stat([r.get("deepest_d") for r in rows]),
        "deepest_d_finished": stat([r.get("deepest_d") for r in done]),
        "xl_finished": stat([r.get("xl") for r in done]),
        "turns_finished": stat([r.get("turns") for r in done]),
        "wall_s": stat([r.get("wall_s") for r in rows]),
        "reached_lair": sum(1 for r in rows if r.get("reached_lair")),
        "runes_total": sum(r.get("runes") or 0 for r in done),
        "games_with_runes": sum(1 for r in done if (r.get("runes") or 0) > 0),
        "wins": sum(1 for r in done if r.get("ktyp") == "winning"),
        "ktyp": tally(r.get("ktyp") or "?" for r in done),
        "top_killers": dict(list(tally(r["killer"] for r in done
                                       if r.get("killer")).items())[:15]),
        "games_with_qw_errors": sum(1 for r in rows if (r.get("qw_errors") or 0) > 0),
        "qw_errors_total": sum(r.get("qw_errors") or 0 for r in rows),
        "games_with_panics": sum(1 for r in rows if (r.get("qw_panics") or 0) > 0),
    }


def determinism(rows: list[dict]) -> list[dict]:
    by_seed: dict[int, list[dict]] = {}
    for r in rows:
        if not r.get("overrides"):
            by_seed.setdefault(r["seed"], []).append(r)
    out = []
    fields = ("turns", "place", "ktyp", "killer", "xl", "score")
    for seed, rs in sorted(by_seed.items()):
        if len(rs) < 2:
            continue
        keys = [tuple(r.get(k) for k in fields) for r in rs]
        out.append({"seed": seed, "identical": len(set(keys)) == 1,
                    "runs": [dict(zip(fields, k)) for k in keys]})
    return out


def parse_seeds(spec: str) -> list[int]:
    seeds: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            seeds += range(int(a), int(b) + 1)
        elif part:
            seeds.append(int(part))
    return seeds


def load_jobs(path: Path) -> list[dict]:
    jobs = []
    for i, j in enumerate(json.loads(path.read_text(encoding="utf-8"))):
        job = {"seed": int(j["seed"]), "tag": str(j.get("tag") or f"{j['seed']}-{i}"),
               "overrides": j.get("overrides") or {}, "rep": 1}
        if j.get("stop_turn"):
            job["stop_turn"] = int(j["stop_turn"])
        if j.get("base"):
            base = Path(j["base"])
            job["base"] = str(base if base.is_absolute() else REPO / base)
        if not NAME_RE.fullmatch(job["tag"]):
            raise SystemExit(f"job tag {job['tag']!r}: letters, digits, _ . - only")
        overrides_lua(job["overrides"])  # validate now, not mid-run
        jobs.append(job)
    tags = [j["tag"] for j in jobs]
    if len(set(tags)) != len(tags):
        raise SystemExit("job tags must be unique")
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--seeds", help="e.g. 500000-500059 or 1,2,3")
    src.add_argument("--jobs", type=Path, help="JSON list of {seed, overrides, tag}")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--time-limit", type=int, default=1800, help="wall-clock seconds per game")
    ap.add_argument("--name", default=None, help="run name (default: qw-<timestamp>)")
    ap.add_argument("--out", type=Path, default=None, help="default runs/qw/<name>")
    ap.add_argument("--repeat", type=int, default=1, help="play each seed this many times")
    ap.add_argument("--action-log", action="store_true",
                    help="one QWACT stderr line per qw decision (turn, place, hp, plan)")
    ap.add_argument("--state-log", action="store_true",
                    help="also a QWS line with qw's state before each decision (gzipped)")
    ap.add_argument("--policy", type=Path, default=None,
                    help="Lua file defining ladder_choose(decision, state); inlined into "
                         "every game's rc (state is built for it even without --state-log)")
    ap.add_argument("--lua", type=Path, default=None,
                    help="Lua file run after qw.lua in every game, to change qw's settings "
                         "or replace its functions (see tools/qw/variants.py)")
    ap.add_argument("--combo", default=None, help="override the combo, e.g. GrBe.handaxe")
    ap.add_argument("--stock", action="store_true", help="build without qw bug fixes")
    ap.add_argument("--stage", default=None,
                    help="build this stage (tools/qw/patches.py STAGES); default up to zk")
    ap.add_argument("--no-build", action="store_true", help="use the qw already deployed")
    ap.add_argument("--lib-dir", default=LIB_DIR,
                    help="container dir holding qw.lua and qw-ladder.rc (deployed there)")
    ap.add_argument("--build-dir", type=Path, default=REPO / "runs/qw/build",
                    help="local build output")
    ap.add_argument("--container", default=CONTAINER)
    args = ap.parse_args()

    args.name = args.name or datetime.now().strftime("qw-%Y%m%d-%H%M%S")
    if not NAME_RE.fullmatch(args.name):
        raise SystemExit("--name: letters, digits, _ . - only")
    if args.combo and not re.fullmatch(r"[A-Za-z.]+", args.combo):
        raise SystemExit("--combo: e.g. MiBe.mace")
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", args.lib_dir):
        raise SystemExit("--lib-dir: an absolute container path")
    out = args.out or REPO / "runs" / "qw" / args.name
    out.mkdir(parents=True, exist_ok=True)

    if args.jobs:
        jobs = load_jobs(args.jobs)
    else:
        seeds = parse_seeds(args.seeds)
        jobs = [{"seed": s, "rep": k, "overrides": {},
                 "tag": f"{s}" if args.repeat == 1 else f"{s}-r{k}"}
                for k in range(1, args.repeat + 1) for s in seeds]

    if not args.no_build:
        qwbuild.deploy(qwbuild.build(REPO / "runs/qw/src", args.build_dir, stock=args.stock,
                                     stage=args.stage),
                       args.container, args.lib_dir)
    version = in_container(args.container, "cat", f"{args.lib_dir}/VERSION").stdout.strip()

    runner = Runner(args, out)
    runner.setup_workers()
    t0 = time.time()
    rows = runner.run(jobs)
    elapsed = time.time() - t0

    result = {
        "meta": {"name": args.name, "qw_version": version, "lib_dir": args.lib_dir,
                 "seeds": args.seeds, "jobs": str(args.jobs) if args.jobs else None,
                 "workers": args.workers, "time_limit_s": args.time_limit,
                 "repeat": args.repeat, "action_log": args.action_log or args.state_log,
                 "state_log": args.state_log,
                 "lua": str(args.lua) if args.lua else None, "policy": str(args.policy) if args.policy else None,
                 "combo": args.combo or "MiBe.mace (tools/qw/ladder.rc)",
                 "container_dir": runner.run_dir, "elapsed_s": round(elapsed, 1),
                 "finished": datetime.now().isoformat(timespec="seconds")},
        "summary": summarize(rows),
        "games": rows,
    }
    det = determinism(rows)
    if det:
        result["determinism"] = det
    (out / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    if det:
        print(json.dumps(det, indent=2))
    print(f"wrote {out / 'results.json'} ({elapsed:.0f}s)")


if __name__ == "__main__":
    main()
