"""Look into the qw games playing right now: is each one being played, or stuck?

    uv run python tools/qw/peek.py                 every game in every live run
    uv run python tools/qw/peek.py --game 100604   one game: its last decisions
    uv run python tools/qw/peek.py --watch 10      repeat every 10 seconds
    uv run python tools/qw/peek.py --json          the verdicts as JSON

Reads runs/qw/<run>/live.json, which run.py rewrites every few seconds from each game's
log lines. Verdicts, worst first:

  hung      no log line for HUNG_S seconds. The game is inside one decision (or one
            engine call) and not returning; it will only end at the time limit.
  frozen    decisions are logged but the turn count has not moved for FROZEN_S seconds
            (run.py ends such a game itself once qw reports QWSTALL).
  circling  turns pass, but the last decisions are a few plans repeated on one level with
            no XL gain, and the game has been on the level for CIRCLING_TURNS turns.
  playing   anything else.

Plain stdlib.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "runs" / "qw"
STALE_S = 30  # a live.json older than this belongs to a run that is no longer running
HUNG_S = 60
FROZEN_S = 60
CIRCLING_TURNS = 5000  # turns on one level before repeated plans count as circling
CIRCLING_PLANS = 3  # at most this many distinct plans in the recent decisions
CIRCLING_MIN = 150  # recent decisions needed before judging
ORDER = {"hung": 0, "frozen": 1, "circling": 2, "playing": 3}


def verdict(g: dict, now: float) -> tuple[str, str]:
    """(verdict, why) for one game entry of live.json."""
    quiet = now - g["last_line"]
    if quiet >= HUNG_S:
        where = "inside a decision" if g.get("in_decision_since") else "between decisions"
        return "hung", f"no output for {quiet:.0f}s, {where}"
    still = now - g["turn_changed"]
    if g.get("turn") is not None and still >= FROZEN_S:
        return "frozen", f"turn {g['turn']} unchanged for {still:.0f}s"
    recent = g.get("recent") or []
    if len(recent) >= CIRCLING_MIN and (g.get("turns_on_level") or 0) >= CIRCLING_TURNS:
        plans = {r[3] for r in recent}
        places = {r[1] for r in recent}
        if len(plans) <= CIRCLING_PLANS and len(places) == 1:
            return "circling", (f"{g['turns_on_level']} turns on {g.get('place')}, "
                                f"only {', '.join(sorted(plans))}")
    rate = g.get("turns_60s")
    return "playing", f"{rate} turns in the last minute" if rate is not None else "just started"


def live_runs(now: float, include_stale: bool = False) -> list[dict]:
    runs = []
    for path in sorted(ROOT.glob("*/live.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if doc.get("finished") or (now - doc["updated"] > STALE_S and not include_stale):
            continue
        runs.append(doc)
    return runs


def rows(runs: list[dict], now: float) -> list[dict]:
    out = []
    for doc in runs:
        for g in doc["games"]:
            v, why = verdict(g, now)
            out.append({"run": doc["name"], "seed": g["seed"], "worker": g["worker"],
                        "verdict": v, "why": why, "minutes": round((now - g["started"]) / 60, 1),
                        "limit_minutes": round(doc["time_limit_s"] / 60),
                        "turn": g.get("turn"), "place": g.get("place"), "xl": g.get("xl"),
                        "hp": g.get("hp"), "mhp": g.get("mhp")})
    return sorted(out, key=lambda r: (ORDER[r["verdict"]], -r["minutes"]))


def show(runs: list[dict], now: float) -> None:
    if not runs:
        print("no live runs (no runs/qw/*/live.json updated in the last "
              f"{STALE_S}s)")
        return
    for doc in runs:
        print(f"{doc['name']}: {doc['done']}/{doc['total']} done, "
              f"{len(doc['games'])} playing")
    print(f"{'verdict':9} {'run':24} {'seed':>7} {'min':>5} {'turn':>6} {'place':9} "
          f"{'xl':>2} {'hp':>7}  why")
    for r in rows(runs, now):
        hp = f"{r['hp']}/{r['mhp']}" if r["hp"] is not None else "-"
        print(f"{r['verdict']:9} {r['run'][:24]:24} {r['seed']:>7} {r['minutes']:>5} "
              f"{r['turn'] if r['turn'] is not None else '-':>6} {r['place'] or '-':9} "
              f"{r['xl'] if r['xl'] is not None else '-':>2} {hp:>7}  {r['why']}")


def show_game(runs: list[dict], seed: int, now: float, last: int) -> None:
    for doc in runs:
        for g in doc["games"]:
            if g["seed"] != seed:
                continue
            v, why = verdict(g, now)
            print(f"{doc['name']} seed {seed} worker {g['worker']}: {v} ({why})")
            print(f"  playing for {(now - g['started']) / 60:.1f} of "
                  f"{doc['time_limit_s'] / 60:.0f} minutes; {g['decisions']} decisions; "
                  f"last output {now - g['last_line']:.0f}s ago")
            print(f"  turn {g.get('turn')} at {g.get('place')}, XL {g.get('xl')}, "
                  f"HP {g.get('hp')}/{g.get('mhp')}, {g.get('turns_on_level')} turns on level; "
                  f"{g.get('turns_60s')} turns in the last minute, "
                  f"{g.get('turns_300s')} in the last five")
            print("  last decisions (turn, place, hp, plan):")
            for t, place, hp, plan in g["recent"][-last:]:
                print(f"    {t:>6} {place:9} {hp:>4}  {plan}")
            return
    print(f"seed {seed} is not playing in any live run")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--game", type=int, default=None, help="seed of one game to show in detail")
    ap.add_argument("--last", type=int, default=20, help="decisions shown with --game")
    ap.add_argument("--watch", type=float, default=None, help="repeat every N seconds")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    while True:
        now = time.time()
        runs = live_runs(now)
        if args.json:
            print(json.dumps(rows(runs, now)))
        elif args.game is not None:
            show_game(runs, args.game, now, args.last)
        else:
            show(runs, now)
        if not args.watch:
            return
        time.sleep(args.watch)
        print()


if __name__ == "__main__":
    main()
