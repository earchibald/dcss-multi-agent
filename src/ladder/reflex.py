"""Reflex tier prototype: walk, stop, log.

Reflex runs routine actions (explore, rest, travel) and runs the detectors
after each one. There are no models yet. `StubTiers` stands in for Jev,
Tactics and Strategy with the simplest deterministic responses that keep a
game moving, so a run produces interrupt data across several levels. When the
stub has no safe answer it ends the game and records an escalation: those are
the cases the real higher tiers exist for.
"""

from __future__ import annotations

from dataclasses import dataclass

from .conn import ActResult, Connection
from .interrupts import Before, Detector, Interrupt
from .runlog import RunLog
from .state import MF_STAIR_DOWN, GameState
from .travel import first_step

KEYS = {
    "explore": ("o",),
    "rest": ("5",),
    "fight": ("key_tab",),
    "descend": (">",),
}


@dataclass
class Escalation(Exception):
    reason: str


class StubTiers:
    """Placeholder decisions. Every branch here is a job for a real tier later."""

    def __init__(self, fight_hp_floor: float = 0.5, rest_below: float = 0.8):
        self.fight_hp_floor = fight_hp_floor
        self.rest_below = rest_below
        self.level_explored = False
        self.rest_stalled_at: tuple[int, int] | None = None

    def next_action(self, state: GameState) -> str:
        hostiles = state.hostiles()
        frac = state.hp / state.hp_max
        if hostiles:
            if frac > self.fight_hp_floor:
                return "fight"
            raise Escalation(f"hp {state.hp}/{state.hp_max} with hostiles in view: "
                             + ", ".join(m.name for m in hostiles[:3]))
        if frac < self.rest_below and self.rest_stalled_at != (state.turn, state.hp):
            return "rest"
        if self.level_explored:
            if state.cells.get(state.pos, {}).get("mf") == MF_STAIR_DOWN:
                return "descend"
            if first_step(state, MF_STAIR_DOWN) is None:
                raise Escalation("level explored but no known path to a downstairs")
            return "travel"
        return "explore"

    def observe(self, action: str, before: Before, state: GameState, interrupts: list[Interrupt]) -> None:
        kinds = {i.kind for i in interrupts}
        if "level_explored" in kinds:
            self.level_explored = True
        if "level_change" in kinds:
            self.level_explored = False
            self.rest_stalled_at = None
        if action == "rest" and state.hp == before.hp:
            self.rest_stalled_at = (state.turn, state.hp)
        if "no_progress" in kinds:
            raise Escalation(f"no progress on '{action}'")


class Reflex:
    def __init__(self, conn: Connection, state: GameState, log: RunLog, game_no: int = 1):
        self.conn = conn
        self.state = state
        self.log = log
        self.game_no = game_no
        self.detector = Detector()
        self.stub = StubTiers()
        self.steps = 0
        self.escalation: str | None = None

    def run(self, max_steps: int = 300, max_turns: int = 20000) -> dict:
        start_turn = self.state.turn
        try:
            while self.steps < max_steps and self.state.turn - start_turn < max_turns:
                if self.state.dead:
                    break
                action = self.stub.next_action(self.state)
                self.step(action)
        except Escalation as e:
            self.escalation = e.reason
            self._record(Interrupt("escalation", "ladder", {"reason": e.reason}), action="stub")
        return {
            "game": self.game_no,
            "steps": self.steps,
            "turns": self.state.turn,
            "final_place": self.state.place,
            "xl": self.state.player.get("xl"),
            "species": self.state.player.get("species"),
            "died": self.state.dead,
            "escalation": self.escalation,
        }

    def step(self, action: str) -> list[Interrupt]:
        self.steps += 1
        before = Before.capture(self.state)
        if action == "travel":
            mode = "travel"
            result = self.conn.act(first_step(self.state, MF_STAIR_DOWN))
        else:
            mode = "explore"
            result = self.conn.act(*KEYS[action])
        result = self._answer_prompts(result)
        interrupts = self.detector.detect(before, self.state, action, result.blocking, mode)
        for i in interrupts:
            self._record(i, action)
        self.stub.observe(action, before, self.state, interrupts)
        return interrupts

    def _answer_prompts(self, result: ActResult) -> ActResult:
        """Stub answers for prompts that would otherwise wedge the game."""
        for _ in range(3):
            if result.blocking in (None, "more", "died"):
                return result
            recent = " ".join(self.state.recent_messages(3))
            if result.blocking == "text_input" and "Increase (S)trength" in recent:
                nxt = self.conn.act("S")          # stat_choice: a Strategy decision later
            else:
                nxt = self.conn.act("key_esc")
            nxt.messages = result.messages + nxt.messages
            original = result.blocking
            result = nxt
            if result.blocking is None:
                result.blocking = original     # keep the prompt visible to the detector
                return result
        return result

    def _record(self, interrupt: Interrupt, action: str) -> None:
        record = {"game": self.game_no, "step": self.steps, "action": action, **interrupt.to_dict(),
                  "snapshot": self.state.snapshot(), "messages": self.state.recent_messages(4)}
        self.log.write(record)
