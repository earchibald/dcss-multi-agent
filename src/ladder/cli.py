"""`ladder` commands: spike, cockpit, jev-eval, retune."""

from __future__ import annotations

import argparse
import json

from . import jeveval, profiles
from .conn import DEFAULT_URL
from .games import run_games
from .jev import Jev
from .routing import Thresholds


def spike(args: argparse.Namespace) -> None:
    def report(ev: str, **data) -> None:
        if ev == "run_start":
            print(f"Logging to {data['dir']}")
        elif ev == "game_end":
            print(json.dumps(data))

    summary = run_games(args, on_event=report)
    print(json.dumps({k: summary[k] for k in ("interrupts_total", "by_source", "by_kind")}, indent=2))


def thresholds_from(args: argparse.Namespace) -> Thresholds:
    return Thresholds(threat=args.threat, needs_plan=args.needs_plan, player_worthy=args.player_worthy,
                      goal_max_threat=args.goal_max_threat, goal_confidence=args.goal_confidence)


def add_threshold_args(p: argparse.ArgumentParser) -> None:
    d = Thresholds()
    p.add_argument("--threat", type=float, default=d.threat, help="rule 2: threat score (0–3) to Strategy")
    p.add_argument("--needs-plan", type=float, default=d.needs_plan, help="rule 2: needs_plan probability")
    p.add_argument("--player-worthy", type=float, default=d.player_worthy, help="rule 3: player_worthy probability")
    p.add_argument("--goal-max-threat", type=float, default=d.goal_max_threat, help="rule 4: max threat to run a goal")
    p.add_argument("--goal-confidence", type=float, default=d.goal_confidence, help="rule 4: next_goal confidence")


def jev_eval(args: argparse.Namespace) -> None:
    jev = None if args.dry_run else Jev(profiles.for_tier("jev"))
    summary = jeveval.evaluate(args.run_dir, jev, limit=args.limit, thresholds=thresholds_from(args))
    print(json.dumps(summary, indent=2))


def retune(args: argparse.Namespace) -> None:
    summary = jeveval.retune(args.run_dir, thresholds_from(args))
    sweep = summary.pop("sweep")
    print(json.dumps(summary, indent=2))
    print("\nthreat  needs_plan  player_worthy   strategy  tactics  reflex_goal")
    for g in sweep:
        print(f"{g['threat']:>6}  {g['needs_plan']:>10}  {g['player_worthy']:>13}   "
              f"{g.get('strategy', 0):>8}  {g.get('tactics', 0):>7}  {g.get('reflex_goal', 0):>11}")


def cockpit(args: argparse.Namespace) -> None:
    from .cockpit import serve
    serve(args, thresholds_from(args))


def add_game_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--games", type=int, default=1)
    p.add_argument("--max-steps", type=int, default=300, help="Reflex actions per game")
    p.add_argument("--max-turns", type=int, default=20000, help="game turns per game")
    p.add_argument("--seed", type=int, default=None, help="first game's seed; later games add 1")
    p.add_argument("--user", default="ladderbot", help="webtiles account; password lives in Keychain")
    p.add_argument("--server", default=DEFAULT_URL)
    p.add_argument("--species", default="b", help="species menu key (dcss-api example: b)")
    p.add_argument("--background", default="f", help="background menu key")
    p.add_argument("--weapon", default="b", help="weapon menu key")
    p.add_argument("--out", default="runs")
    p.add_argument("--record", action="store_true", help="also save raw protocol messages per game")


def main() -> None:
    parser = argparse.ArgumentParser(prog="ladder")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("spike", help="play games with the Reflex loop and log every interrupt")
    add_game_args(p)
    p = sub.add_parser("cockpit", help="play with the web cockpit: live stream, decisions, mode and idle switch")
    add_game_args(p)
    p.add_argument("--port", type=int, default=8090, help="cockpit port on 127.0.0.1")
    p.add_argument("--mode", choices=("assisted", "autonomous"), default="assisted")
    p.add_argument("--idle-minutes", type=int, default=0, help="go autonomous after this many idle minutes; 0 = never")
    p.add_argument("--jev", action="store_true", help="also ask Jev about each interrupt and show its route (shadow)")
    p.add_argument("--delay", type=float, default=0.0,
                   help="seconds to wait between Reflex actions so you can follow along; 0 = full speed")
    p.add_argument("--open", action="store_true", help="open the cockpit in a browser")
    add_threshold_args(p)
    p = sub.add_parser("jev-eval", help="ask Jev about every logged interrupt and route it")
    p.add_argument("run_dir")
    p.add_argument("--limit", type=int, default=None, help="at most this many Jev calls")
    p.add_argument("--dry-run", action="store_true", help="build the requests and apply rule 1 only")
    add_threshold_args(p)
    p = sub.add_parser("retune", help="re-route stored Jev answers under other thresholds (no calls)")
    p.add_argument("run_dir")
    add_threshold_args(p)
    args = parser.parse_args()
    if getattr(args, "idle_minutes", 0) < 0:
        parser.error("--idle-minutes is 0 (never) or a positive number of minutes")
    if not 0 <= getattr(args, "delay", 0) <= 60:
        parser.error("--delay is 0 (full speed) to 60 seconds")
    {"spike": spike, "cockpit": cockpit, "jev-eval": jev_eval, "retune": retune}[args.cmd](args)


if __name__ == "__main__":
    main()
