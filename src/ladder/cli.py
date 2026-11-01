"""`ladder spike`: run the Reflex prototype against the local webtiles server."""

from __future__ import annotations

import argparse
import json
from importlib import resources

from .conn import DEFAULT_URL, Connection
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
    args = parser.parse_args()
    if args.cmd == "spike":
        spike(args)


if __name__ == "__main__":
    main()
