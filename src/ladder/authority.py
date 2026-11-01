"""Who makes a decision: the player, or Strategy.

Assisted mode: the player decides every decision type that isn't deferred.
Autonomous mode: Strategy (the most senior model) decides everything, pins
included. Autonomous means autonomous.

Idle switch: while a decision waits on the player in assisted mode, after
`idle_minutes` without a response the session switches to autonomous mode and
Strategy takes the decision. 0 means never.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ASK, DEFERRED, CONDITIONAL, PINNED = "ask", "deferred", "conditional", "pinned"
ASSISTED, AUTONOMOUS = "assisted", "autonomous"

_TERM = re.compile(r"^\s*([a-z_]+)\s*(?:(>=|<=|>|<|==)\s*(-?\d+(?:\.\d+)?))?\s*$")


def condition_holds(condition: list[str], context: dict) -> bool:
    """Any-of list of terms: `level_explored` (truthy) or `threat >= 2.0`."""
    for term in condition:
        m = _TERM.match(term)
        if not m:
            raise ValueError(f"bad condition term: {term!r}")
        key, op, num = m.groups()
        value = context.get(key)
        if op is None:
            if value:
                return True
            continue
        if value is None:
            continue
        n = float(num)
        if {"<": value < n, "<=": value <= n, ">": value > n, ">=": value >= n, "==": value == n}[op]:
            return True
    return False


@dataclass
class Rule:
    status: str = ASK
    condition: list[str] = field(default_factory=list)   # for CONDITIONAL


# Starting rules from the concept page's decision-type table; everything else asks.
DEFAULT_RULES = {
    "descend_stairs": Rule(CONDITIONAL, ["level_explored", "threat >= 2.0"]),
    "flee_level": Rule(DEFERRED),
    "break_off_fight": Rule(DEFERRED),
    "pick_up_item": Rule(DEFERRED),
    "drop_item": Rule(DEFERRED),
    "engage_unique": Rule(PINNED),
    "choose_god": Rule(PINNED),
}


@dataclass
class Pending:
    decision_type: str
    posted_at: float                 # seconds, the caller's clock


@dataclass
class Verdict:
    decider: str                     # "player" | "strategy"
    reason: str


class Authority:
    def __init__(self, mode: str = ASSISTED, idle_minutes: int = 0, rules: dict[str, Rule] | None = None):
        if idle_minutes < 0:
            raise ValueError("idle_minutes is 0 (never) or a positive number of minutes")
        self.mode = mode
        self.idle_minutes = idle_minutes
        self.rules = dict(DEFAULT_RULES if rules is None else rules)
        self.switched_by_idle = False

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.switched_by_idle = False

    def decide(self, decision_type: str, context: dict | None = None) -> Verdict:
        if self.mode == AUTONOMOUS:
            return Verdict("strategy", "autonomous mode")
        rule = self.rules.get(decision_type, Rule())
        if rule.status == DEFERRED:
            return Verdict("strategy", "deferred")
        if rule.status == CONDITIONAL and condition_holds(rule.condition, context or {}):
            return Verdict("strategy", "deferral condition holds")
        return Verdict("player", "pinned" if rule.status == PINNED else "asks the player")

    def check_idle(self, pending: Pending, now: float) -> Verdict | None:
        """Hand a waiting decision to Strategy once the player has been idle long enough."""
        if self.mode != ASSISTED or self.idle_minutes == 0:
            return None
        if now - pending.posted_at < self.idle_minutes * 60:
            return None
        self.mode = AUTONOMOUS
        self.switched_by_idle = True
        return Verdict("strategy", f"no response for {self.idle_minutes} min; switched to autonomous")
