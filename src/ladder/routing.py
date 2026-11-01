"""Routing policy: code, not a model, decides which tier handles an interrupt.

First match wins (concept page, draft B):
  1. the interrupt is itself a decision type      → Strategy, no Jev call
  2. threat ≥ T or needs_plan ≥ P                  → Strategy
  3. player_worthy ≥ W                             → Strategy (recommend mode)
  4. low threat and a confident allowlisted goal   → run the goal in Reflex
  5. everything else                               → Tactics
Bookkeeping interrupts aren't routed at all.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .jev import GOAL_ALLOWLIST, Answers

BOOKKEEPING = {"level_change", "xl_up", "escalation", "died"}


@dataclass(frozen=True)
class Thresholds:
    threat: float = 2.0            # score scale 0–3: trivial, routine, serious, deadly
    needs_plan: float = 0.6
    player_worthy: float = 0.7
    goal_max_threat: float = 1.0
    goal_confidence: float = 0.8

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Route:
    tier: str                      # strategy | tactics | reflex_goal | none
    rule: int                      # 0 = not routed
    goal: str | None = None
    reason: str = ""


def needs_jev(record: dict) -> bool:
    return record["kind"] not in BOOKKEEPING and not record.get("decision_type")


def route(record: dict, answers: Answers | None, t: Thresholds = Thresholds()) -> Route:
    if record["kind"] in BOOKKEEPING:
        return Route("none", 0, reason="bookkeeping")
    if record.get("decision_type"):
        return Route("strategy", 1, reason=f"decision type {record['decision_type']}")
    if answers is None:
        raise ValueError("rules 2–5 need Jev answers")
    if answers.threat >= t.threat:
        return Route("strategy", 2, reason=f"threat {answers.threat:.2f}")
    if answers.needs_plan >= t.needs_plan:
        return Route("strategy", 2, reason=f"needs_plan {answers.needs_plan:.2f}")
    if answers.player_worthy >= t.player_worthy:
        return Route("strategy", 3, reason=f"player_worthy {answers.player_worthy:.2f}")
    if (answers.threat < t.goal_max_threat and answers.next_goal in GOAL_ALLOWLIST
            and answers.next_goal_confidence >= t.goal_confidence):
        return Route("reflex_goal", 4, goal=answers.next_goal,
                     reason=f"{answers.next_goal} at confidence {answers.next_goal_confidence:.2f}")
    return Route("tactics", 5, reason="default")
