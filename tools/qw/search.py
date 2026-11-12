"""Search qw's settings by whole games: play each variant on the same seeds as the base.

    uv run python tools/qw/search.py run --stage s1 --seeds 100000-100149 --variants all
    uv run python tools/qw/search.py table --stage s1
    uv run python tools/qw/search.py run --stage s3 --seeds 500000-500199 --variants hand+bia10

A stage is a set of runs named <stage>-<variant> under runs/qw; "base" (qw unchanged) is
always played first. Runs that already have results are skipped, so a stage can be resumed.
With --fleet the unplayed runs go to the other Macs in one `ladder-fleet qw` call (every
variant of a seed on the same host) instead of the local container.
Variants are in tools/qw/variants.py; "a+b" joins two. Search on training seeds and keep
seeds 500000 and up for the final comparison.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import variants  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "runs" / "qw"


def run_name(stage: str, spec: str) -> str:
    return f"{stage}-{spec.replace('+', '_')}"


def load(stage: str, spec: str) -> dict[int, dict] | None:
    path = ROOT / run_name(stage, spec) / "results.json"
    if not path.exists():
        return None
    return {g["seed"]: g for g in json.loads(path.read_text())["games"]}


def measures(g: dict) -> dict[str, float]:
    xl = g.get("max_xl") or g.get("xl") or 0
    d = g.get("deepest_d") or 0
    return {"xl": xl, "depth": d, "past5": float(d > 5), "lair": float(bool(g.get("reached_lair"))),
            "xl12": float(xl >= 12), "runes": g.get("runes") or 0}


def cmd_run(args) -> None:
    specs = list(variants.VARIANTS) if args.variants == "all" else args.variants.split(",")
    specs = ["base"] + [s for s in specs if s != "base"]
    for spec in specs:
        variants.lua(spec)  # unknown names fail before any game is played
    luadir = ROOT / f"{args.stage}-lua"
    luadir.mkdir(parents=True, exist_ok=True)
    if args.fleet:
        todo = [s for s in specs if not (ROOT / run_name(args.stage, s) / "results.json").exists()]
        cmd = ["ladder-fleet", "qw", "--seeds", args.seeds, "--qw-repo", str(REPO),
               "--time-limit", str(args.time_limit), "--name", f"qw-{args.stage}", "--wait"]
        for spec in todo:
            luafile = luadir / f"{spec.replace('+', '_')}.lua"
            luafile.write_text(variants.lua(spec), encoding="utf-8")
            cmd += ["--run", f"{run_name(args.stage, spec)}={luafile}"]
        print(f"== fleet: {len(todo)} of {len(specs)} runs to play", flush=True)
        if todo and subprocess.run(cmd).returncode != 0:
            sys.exit("ladder-fleet qw failed")
        cmd_table(args)
        return
    for i, spec in enumerate(specs, 1):
        name = run_name(args.stage, spec)
        if (ROOT / name / "results.json").exists():
            print(f"== {i}/{len(specs)} {name}: already played", flush=True)
            continue
        luafile = luadir / f"{spec.replace('+', '_')}.lua"
        luafile.write_text(variants.lua(spec), encoding="utf-8")
        print(f"== {i}/{len(specs)} {name}", flush=True)
        cmd = [sys.executable, str(REPO / "tools/qw/run.py"), "--seeds", args.seeds,
               "--name", name, "--no-build", "--lua", str(luafile),
               "--workers", str(args.workers), "--time-limit", str(args.time_limit)]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (luadir / f"{name}.log").write_text(r.stdout, encoding="utf-8")
        if r.returncode != 0:
            print(f"   run.py exited {r.returncode}: {r.stdout[-400:]}", flush=True)
            continue
        base = load(args.stage, "base")
        if base is None:
            sys.exit("the base run failed; nothing to compare with")
        print("   " + line(args.stage, spec, base), flush=True)
    cmd_table(args)


def line(stage: str, spec: str, base: dict[int, dict]) -> str:
    run = load(stage, spec)
    if run is None:
        return f"{spec:22} not played"
    seeds = sorted(set(run) & set(base))
    odd = sum(1 for s in seeds if run[s].get("status") != "done")
    err = sum(1 for s in seeds if run[s].get("qw_errors"))
    unloaded = sum(1 for s in seeds if run[s].get("lua_loaded") is False)
    out = f"{spec:22} n {len(seeds):3}"
    for key in ("xl", "depth", "past5", "lair", "xl12"):
        mine = [measures(run[s])[key] for s in seeds]
        diff = [measures(run[s])[key] - measures(base[s])[key] for s in seeds]
        se = st.stdev(diff) / len(diff) ** 0.5 if len(diff) > 1 else 0
        if spec == "base":
            out += f"  {key} {st.mean(mine):5.2f}       "
        else:
            out += f"  {key} {st.mean(mine):5.2f} {st.mean(diff):+.2f}±{se:.2f}"
    return out + f"  unfinished {odd} lua-errors {err}" + (
        f"  LUA NOT LOADED {unloaded}" if unloaded else "")


def cmd_table(args) -> None:
    base = load(args.stage, "base")
    if base is None:
        sys.exit(f"no base run for stage {args.stage}")
    specs = sorted(p.name[len(args.stage) + 1:] for p in ROOT.glob(f"{args.stage}-*")
                   if (p / "results.json").exists())

    def xl_gain(spec: str) -> float:
        run = load(args.stage, spec) or {}
        seeds = set(run) & set(base)
        return st.mean(measures(run[s])["xl"] - measures(base[s])["xl"] for s in seeds)

    print(f"\nstage {args.stage}: mean, then difference from base on the same seeds ± SE")
    for spec in sorted(specs, key=xl_gain, reverse=True):
        print(line(args.stage, spec, base))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--stage", required=True)
    r.add_argument("--seeds", required=True)
    r.add_argument("--variants", default="all", help='comma-separated names, "a+b" joins; or all')
    r.add_argument("--workers", type=int, default=6)
    r.add_argument("--time-limit", type=int, default=600)
    r.add_argument("--fleet", action="store_true", help="play on the fleet's hosts")
    r.set_defaults(fn=cmd_run)
    t = sub.add_parser("table")
    t.add_argument("--stage", required=True)
    t.set_defaults(fn=cmd_table)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
