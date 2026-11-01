"""`ladder spike`: run the Reflex prototype against the local webtiles server."""

from __future__ import annotations

import argparse
import json
from importlib import resources

from .conn import DEFAULT_URL, Connection
from . import jeveval, profiles
from .jev import Jev
from .routing import Thresholds
from .reflex import Reflex
from .runlog import RunLog
from .state import GameState


def crawlrc() -> str:
    return resources.files("ladder").joinpath("crawlrc.txt").read_text()


def spike(args: argparse.Namespace) -> None:
    log = RunLog(args.out)
    print(f"Logging to {log.dir}")
    for game_no in range(1, args.games + 1):
        state = GameState()
        record = open(log.dir / f"game{game_no}.protocol.jsonl", "w") if args.record else None
        conn = Connection(args.server, on_message=state.apply, record=record)
        try:
            conn.login(args.user)
            conn.set_rc(crawlrc())
            seed = None if args.seed is None else args.seed + game_no - 1
            conn.start_game(args.species, args.background, args.weapon, seed=seed)
            game = Reflex(conn, state, log, game_no).run(max_steps=args.max_steps, max_turns=args.max_turns)
            game["seed"] = seed
            log.end_game(game)
            print(json.dumps(game))
            if not state.dead:
                conn.quit_game()
        finally:
            conn.close()
            if record:
                record.close()
    summary = log.close()
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="ladder")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("spike", help="play games with the Reflex loop and log every interrupt")
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
    p = sub.add_parser("jev-eval", help="ask Jev about every logged interrupt and route it")
    p.add_argument("run_dir")
    p.add_argument("--limit", type=int, default=None, help="at most this many Jev calls")
    p.add_argument("--dry-run", action="store_true", help="build the requests and apply rule 1 only")
    add_threshold_args(p)
    p = sub.add_parser("retune", help="re-route stored Jev answers under other thresholds (no calls)")
    p.add_argument("run_dir")
    add_threshold_args(p)
    args = parser.parse_args()
    {"spike": spike, "jev-eval": jev_eval, "retune": retune}[args.cmd](args)


if __name__ == "__main__":
    main()
