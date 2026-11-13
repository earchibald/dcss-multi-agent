"""Play several qw runs back to back with the tail of one overlapping the start of the next.

    uv run python tools/qw/chain.py chain.txt [--workers 9] [--logs DIR]

A run ends with a few slow games while most workers sit idle. Here the next run starts as
soon as the one before has handed out its last game, and all runs share --workers game
slots (run.py --slots), so the machine stays full and never plays more than --workers games.

The chain file has one step per line; blank lines and # comments are skipped:

    common  --no-build --lib-dir /data/qw/lib-zk --time-limit 3600 --state-log
    wait    pace2-t10
    run     --seeds 100700-100899 --lua a.lua --name pace2-combo
    compare pace2-base pace2-t10 pace2-combo

  common   arguments added to every later `run`
  wait     block until runs/qw/<name>/results.json exists (a run started elsewhere)
  run      tools/qw/run.py arguments; needs --name. Output goes to <logs>/<name>.log
  compare  tools/qw/compare.py arguments; runs once every run it names has finished

Plain stdlib.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
ROOT = REPO / "runs" / "qw"
KINDS = ("common", "wait", "run", "compare")
PRINT = threading.Lock()


def say(text: str) -> None:
    with PRINT:
        print(f"{datetime.now():%H:%M:%S} {text}", flush=True)


def parse(text: str) -> list[tuple[str, list[str]]]:
    """The chain file as (kind, arguments) steps, with `common` folded into each run."""
    steps: list[tuple[str, list[str]]] = []
    common: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        words = shlex.split(line, comments=True)
        if not words:
            continue
        kind, rest = words[0], words[1:]
        if kind not in KINDS:
            raise SystemExit(f"line {n}: unknown step {kind!r} (one of {', '.join(KINDS)})")
        if kind == "common":
            common = rest
            continue
        if kind == "run":
            rest = common + rest
            if rest.count("--name") != 1:
                raise SystemExit(f"line {n}: a run needs exactly one --name")
            if "--slots" in rest:
                raise SystemExit(f"line {n}: --slots is set by the chain")
        elif not rest:
            raise SystemExit(f"line {n}: {kind} needs a run name")
        steps.append((kind, rest))
    names = [run_name(a) for k, a in steps if k == "run"]
    if len(set(names)) != len(names):
        raise SystemExit("run names must be unique")
    return steps


def run_name(args: list[str]) -> str:
    return args[args.index("--name") + 1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("chain", type=Path)
    ap.add_argument("--workers", type=int, default=9, help="games at once, over all runs")
    ap.add_argument("--logs", type=Path, default=None, help="default: beside the chain file")
    args = ap.parse_args()
    steps = parse(args.chain.read_text(encoding="utf-8"))
    logs = args.logs or args.chain.resolve().parent
    logs.mkdir(parents=True, exist_ok=True)
    slots = ROOT / ".slots"

    procs: dict[str, subprocess.Popen] = {}
    waiters: list[threading.Thread] = []
    prev: str | None = None

    def compare(names: list[str]) -> None:
        for name in names:
            if name in procs:
                procs[name].wait()
        r = subprocess.run([sys.executable, str(HERE / "compare.py"), *names],
                           capture_output=True, text=True)
        say(f"compare {' '.join(names)}\n{r.stdout}{r.stderr}")

    for kind, rest in steps:
        if kind == "wait":
            say(f"waiting for {rest[0]}")
            while not (ROOT / rest[0] / "results.json").exists():
                time.sleep(10)
        elif kind == "run":
            name = run_name(rest)
            if prev:
                # Start once the run before has no games left to hand out, or has ended.
                while not (ROOT / prev / "drained").exists() and procs[prev].poll() is None:
                    time.sleep(2)
            (ROOT / name / "drained").unlink(missing_ok=True)
            log = open(logs / f"{name}.log", "w", encoding="utf-8")
            cmd = [sys.executable, str(HERE / "run.py"), *rest,
                   "--workers", str(args.workers), "--slots", str(slots)]
            procs[name] = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            say(f"started {name} (log {logs / f'{name}.log'})")
            t = threading.Thread(target=lambda n=name: say(f"finished {n} exit={procs[n].wait()}"))
            t.start()
            waiters.append(t)
            prev = name
        else:
            t = threading.Thread(target=compare, args=(rest,))
            t.start()
            waiters.append(t)
    for t in waiters:
        t.join()
    say("chain finished")


if __name__ == "__main__":
    main()
