"""JSONL interrupt and decision logs plus a per-run summary."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path


class RunLog:
    def __init__(self, root: str | Path = "runs"):
        self.dir = Path(root) / time.strftime("%Y%m%d-%H%M%S")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.interrupts = (self.dir / "interrupts.jsonl").open("w")
        self.decisions = (self.dir / "decisions.jsonl").open("w")
        self.by_decider: Counter[str] = Counter()
        self.games: list[dict] = []
        self.by_kind: Counter[str] = Counter()
        self.by_source: Counter[str] = Counter()
        self.by_place: dict[str, Counter[str]] = {}

    def write(self, record: dict) -> None:
        self.interrupts.write(json.dumps(record) + "\n")
        self.interrupts.flush()
        kind = record["kind"]
        self.by_kind[kind] += 1
        self.by_source[record["source"]] += 1
        self.by_place.setdefault(record["snapshot"]["place"], Counter())[kind] += 1

    def decision(self, record: dict) -> None:
        self.decisions.write(json.dumps(record) + "\n")
        self.decisions.flush()
        self.by_decider[record["decider"]] += 1

    def end_game(self, game: dict) -> None:
        self.games.append(game)

    def close(self) -> dict:
        self.interrupts.close()
        self.decisions.close()
        summary = {
            "games": self.games,
            "interrupts_total": sum(self.by_kind.values()),
            "by_kind": dict(self.by_kind.most_common()),
            "by_source": dict(self.by_source),
            "decisions_by_decider": dict(self.by_decider),
            "by_place": {p: dict(c.most_common()) for p, c in sorted(self.by_place.items())},
        }
        (self.dir / "summary.json").write_text(json.dumps(summary, indent=2))
        return summary
