"""Reflex tier prototype: walk, stop, log.

Reflex runs routine actions (explore, rest, travel) and runs the detectors
after each one. There are no models yet. `StubTiers` stands in for Jev,
Tactics and Strategy with the simplest deterministic responses that keep a
game moving, so a run produces interrupt data across several levels. When the
stub has no safe answer it ends the game and records an escalation: those are
the cases the real higher tiers exist for.

Decision points (stairs, altars, uniques, the stat prompt, escalations) go
through `Hooks.decide`. The default hooks take the stub's recommendation, so
`ladder spike` plays alone; the cockpit's hooks ask Authority, and through it
the player or Strategy.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import decisions
from .conn import ActResult, Connection
from .decisions import END_GAME, Answer, DecisionRequest
from .interrupts import Before, Detector, Interrupt
from .runlog import RunLog
from .state import MF_STAIR_DOWN, GameState
from .travel import first_step, step_toward

KEYS = {
    "explore": ("o",),
    "rest": ("5",),
    "fight": ("key_tab",),
    "struggle": ("key_dir_e",),     # held in a web or net, any move struggles; Tab only says you're caught
    "descend": (">",),
}


@dataclass
class Escalation(Exception):
    reason: str


@dataclass
class GameOver(Exception):
    """A decision ended the game: `end_game`, or `take_over` (left saved for the player)."""
    choice: str


class Hooks:
    """How Reflex reaches the tiers above and the cockpit. These defaults play alone."""

    def checkpoint(self) -> bool:
        """Called before every action; False stops the game where it is."""
        return True

    def decide(self, request: DecisionRequest) -> Answer:
        if request.decision_type == "escalation":
            # Playing alone there is no one to take the wheel: end this game and go on to the next.
            return Answer(END_GAME, "stub", "playing alone, no one to take the wheel")
        return Answer(request.recommended, "stub", "stub recommendation")

    def on_record(self, record: dict) -> None:
        pass

    def on_step(self, reflex: "Reflex", action: str) -> None:
        pass


class StubTiers:
    """Placeholder decisions. Every branch here is a job for a real tier later."""

    def __init__(self, fight_hp_floor: float = 0.5, rest_below: float = 0.8):
        self.fight_hp_floor = fight_hp_floor
        self.rest_below = rest_below
        self.level_explored = False
        self.fight_anyway = False          # set by a "fight on" answer; lasts until no hostiles are in view
        self.rest_stalled_at: tuple[int, int] | None = None
        self.shops: set[tuple[int, int]] = set()           # shops on this level; the glyph hides under @
        self.shops_seen: set[tuple[int, int]] = set()      # the ones we have looked inside
        self.descend_asked = False                          # "downstairs in view" asked once per level

    def unvisited_shop(self, state: GameState) -> tuple[int, int] | None:
        self.shops |= state.shops()
        return min(self.shops - self.shops_seen, key=state.distance, default=None)

    def next_action(self, state: GameState) -> str:
        hostiles = state.hostiles()
        frac = state.hp / state.hp_max
        if not hostiles:
            self.fight_anyway = False
        if hostiles and frac <= self.fight_hp_floor and not self.fight_anyway:
            raise Escalation(f"hp {state.hp}/{state.hp_max} with hostiles in view: "
                             + ", ".join(m.name for m in hostiles[:3]))
        if state.caught:
            return "struggle"
        if hostiles:
            return "fight"
        if frac < self.rest_below and self.rest_stalled_at != (state.turn, state.hp):
            return "rest"
        if self.level_explored:
            if state.cells.get(state.pos, {}).get("mf") == MF_STAIR_DOWN:
                return "descend"
            if first_step(state, MF_STAIR_DOWN) is None:
                raise Escalation("level explored but no known path to a downstairs")
            return "travel"
        if self.unvisited_shop(state):
            # Greedy explore walks into an unvisited shop and opens its menu, which sends no
            # input_mode, so act() would wait forever. Visit it ourselves, expecting the menu.
            return "shop"
        return "explore"

    def observe(self, action: str, before: Before, state: GameState, interrupts: list[Interrupt]) -> None:
        kinds = {i.kind for i in interrupts}
        if "level_explored" in kinds:
            self.level_explored = True
        if "level_change" in kinds:
            self.level_explored = False
            self.rest_stalled_at = None
            self.shops, self.shops_seen = set(), set()
            self.descend_asked = False
        if action == "rest" and state.hp == before.hp:
            self.rest_stalled_at = (state.turn, state.hp)
        if "no_progress" in kinds:
            raise Escalation(f"no progress on '{action}'")


class Reflex:
    def __init__(self, conn: Connection, state: GameState, log: RunLog, game_no: int = 1,
                 hooks: Hooks | None = None):
        self.conn = conn
        self.state = state
        self.log = log
        self.game_no = game_no
        self.detector = Detector()
        self.stub = StubTiers()
        self.hooks = hooks or Hooks()
        self.steps = 0
        self.decisions = 0
        self.escalation: str | None = None

    def run(self, max_steps: int = 300, max_turns: int = 20000) -> dict:
        start_turn = self.state.turn
        ended_by = "limit"
        while self.steps < max_steps and self.state.turn - start_turn < max_turns:
            if self.state.dead:
                break
            if not self.hooks.checkpoint():
                ended_by = "stopped"
                break
            try:
                action = self.stub.next_action(self.state)
                self.step(action)
            except Escalation as e:
                self._record(Interrupt("escalation", "ladder", {"reason": e.reason}), action="stub")
                answer = self._ask(decisions.for_escalation(e.reason, self.state, self.stub.level_explored))
                if answer.choice == "fight_on":
                    self.stub.fight_anyway = True
                    continue
                self.escalation = e.reason
                ended_by = answer.choice
                break
            except GameOver as e:
                ended_by = e.choice
                break
        if self.state.dead:
            ended_by = "died"
        return {
            "game": self.game_no,
            "steps": self.steps,
            "turns": self.state.turn,
            "final_place": self.state.place,
            "xl": self.state.player.get("xl"),
            "species": self.state.player.get("species"),
            "died": self.state.dead,
            "escalation": self.escalation,
            "ended_by": ended_by,
            "decisions": self.decisions,
        }

    def step(self, action: str) -> list[Interrupt]:
        self.steps += 1
        before = Before.capture(self.state)
        if action == "travel":
            mode = "travel"
            result = self.conn.act(first_step(self.state, MF_STAIR_DOWN))
        elif action == "shop":
            mode = "travel"
            result = self._visit_shop()
        else:
            mode = "explore"
            result = self.conn.act(*KEYS[action])
        result = self._answer_prompts(result)
        interrupts = self.detector.detect(before, self.state, action, result.blocking, mode)
        for i in interrupts:
            self._record(i, action)
        self.hooks.on_step(self, action)
        self.stub.observe(action, before, self.state, interrupts)
        for i in interrupts:
            if i.kind == "feature_in_view" and i.decision_type == "descend_stairs":
                if self.stub.descend_asked:
                    continue                   # a level has three downstairs: one question is enough
                self.stub.descend_asked = True
            request = decisions.for_interrupt(i, self.state, self.stub.level_explored) if i.decision_type else None
            if request:
                self._apply(self._ask(request))
        return interrupts

    def _visit_shop(self) -> ActResult:
        """Walk to the nearest unvisited shop one square at a time; on it, open the menu and leave."""
        shop = self.stub.unvisited_shop(self.state)
        if self.state.pos != shop:
            key = step_toward(self.state, shop)
            if key is None:
                self.stub.shops_seen.add(shop)          # no known way there; explore will deal with it
                return ActResult()
            return self.conn.act(key)
        self.stub.shops_seen.add(shop)
        opened = self.conn.open_menu("<")
        closed = self.conn.act("key_esc")
        closed.messages = opened.messages + closed.messages
        return closed

    def _ask(self, request: DecisionRequest) -> Answer:
        self.decisions += 1
        request.id = f"{self.game_no}-{self.steps}-{self.decisions}"
        answer = self.hooks.decide(request)
        if answer.choice not in request.keys():
            answer = Answer(request.recommended, answer.decider, f"'{answer.choice}' isn't an option; took the recommendation")
        self.log.decision({"game": self.game_no, "step": self.steps, **request.to_dict(),
                           "choice": answer.choice, "decider": answer.decider, "reason": answer.reason})
        return answer

    def _apply(self, answer: Answer) -> None:
        if answer.choice in (END_GAME, decisions.TAKE_OVER):
            raise GameOver(answer.choice)
        if answer.choice == "descend":
            self.stub.level_explored = True    # travel to the stairs, then descend

    def _answer_prompts(self, result: ActResult) -> ActResult:
        """Stub answers for prompts that would otherwise wedge the game."""
        for _ in range(3):
            if result.blocking in (None, "more", "died"):
                return result
            recent = " ".join(self.state.recent_messages(3))
            if result.blocking == "text_input" and "Increase (S)trength" in recent:
                choice = self._ask(decisions.stat_choice(self.state, self.stub.level_explored)).choice
                nxt = self.conn.act(choice)
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
        self.hooks.on_record(record)
