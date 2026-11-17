"""`steps.jsonl`: one line per choice the brain made, one `"type": "end"` line per game.

Written wherever the brain plays (self-play, `ladder spike --brain`, the cockpit), so every session
adds to the corpus. corpus.py reads these back.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..state import GameState
from .features import score_depth
from .policy import BrainTiers


class StepLog:
    def __init__(self, directory: str | Path):
        self.file = (Path(directory) / "steps.jsonl").open("a")
        self.best = 0
        self.steps = 0

    def attach(self, tiers: BrainTiers, game) -> BrainTiers:
        """Have `tiers` write each choice here, under game id `game`."""
        self.best = self.steps = 0

        def sink(record: dict) -> None:
            self.steps += 1
            o = record["obs"]
            self.best = max(self.best, score_depth(o["place"], o["depth"]))
            self.file.write(json.dumps({"game": game, "step": self.steps, **record}) + "\n")
            self.file.flush()

        tiers.sink = sink
        return tiers

    def end(self, game, state: GameState, summary: dict, tiers: BrainTiers) -> dict:
        p = state.player
        self.best = max(self.best, score_depth(p.get("place", ""), p.get("depth", 0)))
        end = {"type": "end", "game": game, "died": state.dead, "turn": state.turn, "place": p.get("place", ""),
               "depth": p.get("depth", 0), "xl": p.get("xl", 1), "progress": p.get("progress", 0),
               "hp": state.hp, "hp_max": state.hp_max, "ended_by": summary["ended_by"],
               "escalation": summary["escalation"], "max_depth": self.best, "steps": summary["steps"],
               "last_messages": state.recent_messages(4), **tiers.describe()}
        self.file.write(json.dumps(end) + "\n")
        self.file.flush()
        return end

    def close(self) -> None:
        self.file.close()
