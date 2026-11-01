"""Run Jev over a logged run and see where the routing policy sends each interrupt.

Answers are stored once in `jev.jsonl`; `retune` recomputes routes for other
thresholds from those stored answers, without asking Jev again.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import replace
from itertools import product
from pathlib import Path

from .jev import Answers, Jev, build_state
from .routing import Route, Thresholds, needs_jev, route


def load_interrupts(run_dir: Path) -> list[dict]:
    with (run_dir / "interrupts.jsonl").open() as f:
        return [json.loads(line) for line in f]


class SeenBefore:
    """Monster names, features and statuses met earlier in the same game."""

    def __init__(self):
        self.by_game: dict[int, list[str]] = {}

    def before(self, record: dict) -> list[str]:
        return list(self.by_game.get(record["game"], []))

    def add(self, record: dict) -> None:
        seen = self.by_game.setdefault(record["game"], [])
        names = [m["name"] for m in record["snapshot"].get("hostiles", [])]
        names += [record["detail"].get("feature")] + record["snapshot"].get("status", [])
        for n in names:
            if n and n not in seen:
                seen.append(n)


def evaluate(run_dir: str | Path, jev: Jev | None, limit: int | None = None,
             thresholds: Thresholds = Thresholds()) -> dict:
    """Ask Jev about every interrupt that needs it. With `jev=None`, only plan the calls."""
    run_dir = Path(run_dir)
    seen = SeenBefore()
    rows, calls = [], 0
    for record in load_interrupts(run_dir):
        row = {"game": record["game"], "step": record["step"], "kind": record["kind"],
               "decision_type": record.get("decision_type")}
        if needs_jev(record) and (limit is None or calls < limit):
            state = build_state(record, seen.before(record))
            row["state"] = state
            if jev is not None:
                result = jev.ask(state)
                calls += 1
                row.update(answers=result.answers.to_dict(), raw_answers=result.answers.raw,
                           model=result.model, usage=result.usage, latency_ms=round(result.latency_ms, 1))
        rows.append(row)
        seen.add(record)
    out = run_dir / ("jev.jsonl" if jev is not None else "jev.plan.jsonl")
    with out.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return summarize(rows, thresholds) | {"file": str(out)}


def _answers(row: dict) -> Answers | None:
    raw = row.get("raw_answers")
    return Answers.parse(raw) if raw else None


def routes(rows: list[dict], thresholds: Thresholds) -> list[Route | None]:
    out = []
    for row in rows:
        answers = _answers(row)
        if answers is None and needs_jev(row):
            out.append(None)                 # not asked (dry run or past --limit)
        else:
            out.append(route(row, answers, thresholds))
    return out


def summarize(rows: list[dict], thresholds: Thresholds) -> dict:
    rs = routes(rows, thresholds)
    by_tier = Counter(r.tier if r else "unasked" for r in rs)
    by_rule = Counter(r.rule for r in rs if r)
    by_kind: dict[str, Counter] = {}
    for row, r in zip(rows, rs):
        by_kind.setdefault(row["kind"], Counter())[r.tier if r else "unasked"] += 1
    latencies = [row["latency_ms"] for row in rows if "latency_ms" in row]
    tokens = Counter()
    for row in rows:
        tokens.update(row.get("usage") or {})
    return {
        "interrupts": len(rows),
        "jev_calls": len(latencies),
        "planned_calls": sum(1 for row in rows if "state" in row),
        "thresholds": thresholds.to_dict(),
        "by_tier": dict(by_tier),
        "by_rule": {str(k): v for k, v in sorted(by_rule.items())},
        "by_kind": {k: dict(v) for k, v in sorted(by_kind.items())},
        "latency_ms": ({"p50": statistics.median(latencies),
                        "p95": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]}
                       if latencies else None),
        "tokens": dict(tokens),
    }


def sweep(rows: list[dict], base: Thresholds = Thresholds()) -> list[dict]:
    """Share of asked interrupts sent to each tier across a small threshold grid."""
    asked = [row for row in rows if row.get("raw_answers")]
    grid = []
    for threat, plan, worthy in product((1.5, 2.0, 2.5), (0.5, 0.6, 0.7), (0.6, 0.7, 0.8)):
        t = replace(base, threat=threat, needs_plan=plan, player_worthy=worthy)
        tiers = Counter(r.tier for r in routes(asked, t) if r)
        grid.append({"threat": threat, "needs_plan": plan, "player_worthy": worthy, **dict(tiers)})
    return grid


def retune(run_dir: str | Path, thresholds: Thresholds) -> dict:
    with (Path(run_dir) / "jev.jsonl").open() as f:
        rows = [json.loads(line) for line in f]
    return summarize(rows, thresholds) | {"sweep": sweep(rows, thresholds)}
