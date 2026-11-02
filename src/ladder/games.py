"""Play a run of games against the webtiles server. Shared by `ladder spike` and the cockpit."""

from __future__ import annotations

import argparse
from importlib import resources
from typing import Callable

from .conn import Connection
from .pace import pace_rc
from .reflex import Hooks, Reflex
from .runlog import RunLog
from .state import GameState


def crawlrc() -> str:
    return resources.files("ladder").joinpath("crawlrc.txt").read_text() + "\n# Step delay keys (ladder.pace)\n" + pace_rc()


def run_games(args: argparse.Namespace, hooks: Hooks | None = None,
              on_event: Callable[..., None] = lambda ev, **data: None) -> dict:
    log = RunLog(args.out)
    on_event("run_start", dir=str(log.dir), user=args.user, games=args.games)
    for game_no in range(1, args.games + 1):
        state = GameState()
        record = open(log.dir / f"game{game_no}.protocol.jsonl", "w") if args.record else None
        conn = Connection(args.server, on_message=state.apply, record=record)
        try:
            conn.login(args.user)
            conn.set_rc(crawlrc())
            seed = None if args.seed is None else args.seed + game_no - 1
            conn.start_game(args.species, args.background, args.weapon, seed=seed)
            on_event("game_start", game=game_no, seed=seed, snapshot=state.snapshot())
            game = Reflex(conn, state, log, game_no, hooks).run(max_steps=args.max_steps, max_turns=args.max_turns)
            game["seed"] = seed
            log.end_game(game)
            on_event("game_end", **game)
            # A game handed to the player, or stopped from the cockpit, stays saved to resume later.
            if not state.dead and game["ended_by"] not in ("take_over", "stopped"):
                conn.quit_game()
        finally:
            conn.close()
            if record:
                record.close()
        if game["ended_by"] in ("take_over", "stopped"):
            break
    summary = log.close()
    on_event("run_end", summary=summary)
    return summary
