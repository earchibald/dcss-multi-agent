"""Decision points: the moments Reflex stops and someone has to choose.

A `DecisionRequest` is built from an interrupt (or an escalation, or a prompt)
with the options Reflex can actually carry out. `recommended` is the stub's
pick until Strategy exists; `Authority` decides whether the player or Strategy
answers. Every request also offers two ways out: end the game, or leave it
saved so the player can take the wheel in webtiles.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .interrupts import Interrupt
from .state import MF_STAIR_DOWN, THREAT_NAMES, GameState
from .travel import first_step

END_GAME, TAKE_OVER = "end_game", "take_over"
EXITS = [
    {"key": TAKE_OVER, "label": "Take the wheel", "exit": True},
    {"key": END_GAME, "label": "End game", "exit": True},
]
THREAT_LEVEL = {name: level for level, name in THREAT_NAMES.items()}


@dataclass
class DecisionRequest:
    decision_type: str
    question: str
    options: list[dict]              # {key, label, exit?}
    recommended: str                 # an option key: the stub's pick until Strategy exists
    context: dict                    # what Authority's deferral conditions read
    snapshot: dict = field(default_factory=dict)
    id: str = ""

    def keys(self) -> set[str]:
        return {o["key"] for o in self.options}

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Answer:
    choice: str
    decider: str                     # player | strategy | stub
    reason: str = ""


def context_for(state: GameState, level_explored: bool) -> dict:
    """Authority context. `threat` is the worst monster in view on webtiles' 0–3 scale until Jev runs live."""
    levels = [THREAT_LEVEL.get(m["threat"], 0) for m in state.snapshot()["hostiles"]]
    return {"level_explored": level_explored, "hp_frac": round(state.hp / max(state.hp_max, 1), 2),
            "threat": max(levels, default=0)}


def _request(decision_type: str, question: str, options: list[dict], recommended: str, state: GameState,
             level_explored: bool, exits: bool = True) -> DecisionRequest:
    return DecisionRequest(decision_type, question, options + (EXITS if exits else []), recommended,
                           context_for(state, level_explored), state.snapshot())


def for_interrupt(interrupt: Interrupt, state: GameState, level_explored: bool) -> DecisionRequest | None:
    t, d = interrupt.decision_type, interrupt.detail
    if t == "descend_stairs" and (interrupt.kind == "level_explored" or level_explored):
        return _request(t, f"{state.place} is explored. Go down?",
                        [{"key": "descend", "label": "Travel to > and descend"}], "descend", state, True)
    if t == "descend_stairs":
        return _request(t, f"Downstairs in view, {d.get('dist', '?')} squares away. Keep exploring {state.place}?",
                        [{"key": "explore", "label": "Keep exploring"},
                         {"key": "descend", "label": "Descend now"}], "explore", state, False)
    if t == "choose_god":
        return _request(t, "An altar is in view. Worshipping isn't automated yet.",
                        [{"key": "skip", "label": "Skip the altar"}], "skip", state, level_explored)
    if t == "engage_unique":
        uniques = [m for m in d.get("monsters", []) if m.get("unique")]
        seen = ", ".join(f"{m['name']} ({m['threat']}, {m['dist']} squares away)" for m in uniques)
        options = [{"key": "fight", "label": "Fight"},
                   {"key": "avoid", "label": "Leave it alone and keep exploring"}]
        if first_step(state, MF_STAIR_DOWN) or state.cells.get(state.pos, {}).get("mf") == MF_STAIR_DOWN:
            options.append({"key": "leave", "label": "Leave it alone and take the stairs down"})
        return _request(t, f"{seen} in view. Fight?", options, "fight", state, level_explored)
    return None


def stat_choice(state: GameState, level_explored: bool) -> DecisionRequest:
    """The level-up stat prompt is open in the game, so there is no way out but to answer it."""
    return _request("stat_choice", "Level up: raise which stat?",
                    [{"key": "S", "label": "Strength"}, {"key": "I", "label": "Intelligence"},
                     {"key": "D", "label": "Dexterity"}], "S", state, level_explored, exits=False)


def for_escalation(reason: str, state: GameState, level_explored: bool) -> DecisionRequest:
    """The stub has no safe answer. It recommends leaving the game saved: ending it can't be undone, and
    whoever answers (Strategy in autonomous mode) may be answering for a character that is fine."""
    options = [{"key": "fight_on", "label": "Fight on anyway"}] if state.hostiles() else []
    return _request("escalation", f"Reflex is stuck: {reason}", options, TAKE_OVER, state, level_explored)
