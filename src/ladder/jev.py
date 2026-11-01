"""Jev: narrow System One judgments about an interrupt.

One request per interrupt: the situation as named JSON state, plus the standing
questions. Jev never names a tier; `routing.route` reads the answers.
Request and response shapes follow https://docs.typesafe.ai/api.md.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from .profiles import Profile

# Library goals Jev may hand straight back to Reflex (policy rule 4)
GOAL_ALLOWLIST = ("fight_melee", "pick_up", "keep_exploring", "rest")

QUESTIONS = {
    "threat": {
        "type": "score",
        "instructions": (
            "How dangerous is the situation described in `interrupt` and `monsters` for the "
            "character in `player`, if handled with ordinary melee and no special care? "
            "`threat_estimate` on each monster is the game's own rough rating for this character."
        ),
        "criteria": [
            "Trivial: nothing dangerous, or monsters that die in a hit or two and pose no risk",
            "Routine: some HP loss is likely but there is no real risk of death",
            "Serious: could go badly without care, such as several monsters, a caster, or low HP",
            "Deadly: likely to kill the character if fought head-on",
        ],
    },
    "needs_plan": {
        "type": "noul",
        "instructions": (
            "Handling this situation well needs more than one routine action: for example "
            "repositioning, retreating, using an item or ability, or deciding whether to fight at all."
        ),
    },
    "unfamiliar": {
        "type": "noul",
        "instructions": (
            "The situation includes a monster, item, feature or effect that does not appear in "
            "`seen_before`, so the character has not dealt with it earlier this game."
        ),
    },
    "player_worthy": {
        "type": "noul",
        "instructions": (
            "An experienced Dungeon Crawl Stone Soup player would want to make this call personally "
            "rather than leave it to an assistant."
        ),
    },
    "next_goal": {
        "type": "choice",
        "instructions": "Which single routine goal handles this situation, if any?",
        "criteria": {
            "fight_melee": "A single weak monster that can simply be attacked",
            "pick_up": "An item is worth picking up and nothing threatens the character",
            "keep_exploring": "Nothing here needs doing; carry on exploring",
            "rest": "The character should rest to recover and nothing threatens it",
            "none": "None of these fit: the situation needs more than one routine goal, or is unclear",
        },
    },
}


def build_state(record: dict, seen_before: list[str]) -> dict:
    """Named JSON state for one logged interrupt."""
    snap = record["snapshot"]
    return {
        "interrupt": {"kind": record["kind"], "noticed_by": record["source"], **record["detail"]},
        "player": {
            "species": snap.get("species"), "xl": snap.get("xl"), "god": snap.get("god"),
            "hp": f'{snap.get("hp")}/{snap.get("hp_max")}', "status": snap.get("status") or [],
            "place": snap.get("place"),
        },
        "monsters": [{"name": m["name"], "distance": m["dist"], "threat_estimate": m["threat"],
                      **({"unique": True} if m.get("unique") else {})} for m in snap.get("hostiles", [])],
        "recent_messages": record.get("messages", []),
        "seen_before": seen_before,
    }


@dataclass
class Answers:
    threat: float
    threat_confidence: float
    needs_plan: float
    unfamiliar: float
    player_worthy: float
    next_goal: str
    next_goal_confidence: float
    raw: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, answers: dict) -> "Answers":
        return cls(
            threat=answers["threat"]["score"],
            threat_confidence=answers["threat"].get("confidence", 0.0),
            needs_plan=answers["needs_plan"]["noul"],
            unfamiliar=answers["unfamiliar"]["noul"],
            player_worthy=answers["player_worthy"]["noul"],
            next_goal=answers["next_goal"]["choice"],
            next_goal_confidence=answers["next_goal"].get("confidence", 0.0),
            raw=answers,
        )

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "raw"}


Transport = Callable[[str, dict, dict], dict]


def http_post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


@dataclass
class JevResult:
    answers: Answers
    model: str
    usage: dict
    latency_ms: float


class Jev:
    def __init__(self, profile: Profile, transport: Transport = http_post):
        if profile.style != "systemone":
            raise ValueError(f"Jev needs a systemone profile, got '{profile.style}'")
        self.profile = profile
        self.transport = transport
        self._key: str | None = None

    def request(self, state: dict) -> dict:
        return {"model": self.profile.model, "state": state, "questions": QUESTIONS}

    def ask(self, state: dict) -> JevResult:
        if self._key is None:
            self._key = self.profile.api_key()
        start = time.perf_counter()
        body = self.transport(f"{self.profile.base_url}/v1/systemone",
                              {"Authorization": f"Bearer {self._key}"}, self.request(state))
        latency = (time.perf_counter() - start) * 1000
        return JevResult(Answers.parse(body["answers"]), body.get("model", ""), body.get("usage", {}), latency)
