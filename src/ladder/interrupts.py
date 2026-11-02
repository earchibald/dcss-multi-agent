"""Reflex interrupt detection.

An interrupt is anything that should stop routine stepping and be looked at by
a higher tier. `source` says who noticed it:
  - "dcss":   DCSS itself stopped the action (explore/travel/rest stops, the
              ones our crawlrc tunes). We only classify what happened.
  - "ladder": our own detectors, for things DCSS doesn't stop for.
Interrupts that are themselves decisions carry a `decision_type`; the routing
policy sends those straight to Strategy without a Jev call.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field

from .state import MF_UNEXPLORED, NOT_WALKABLE, THREAT_NAMES, GameState

# Actions that run as DCSS "delays" (multi-turn, natively interruptible)
DELAY_ACTIONS = {"explore", "travel", "rest"}
# Actions expected to spend game time
TIMED_ACTIONS = DELAY_ACTIONS | {"fight", "struggle", "descend"}

RE_EXPLORED = re.compile(r"Done exploring|Partly explored", re.I)
RE_HOSTILE_STOP = re.compile(r"is nearby|are nearby|comes? into view|There are monsters nearby", re.I)
RE_TELEPORT = re.compile(r"teleport|surroundings (?:suddenly )?seem different|yanked", re.I)
RE_TRAP = re.compile(r"\btrap\b", re.I)
RE_MESSAGE_STOPS = [
    ("god_wrath", re.compile(r"wrath finds you", re.I)),
    ("low_hp_warning", re.compile(r"LOW HITPOINT WARNING")),
    ("stat_drain", re.compile(r"You feel a little less (?:mighty|clever|agile)", re.I)),
]

FEATURE_DECISIONS = {
    "downstairs": "descend_stairs",
    "branch_stairs": "enter_branch",
    "portal": "enter_portal",
    "altar": "choose_god",
}

HANDLED_BLOCKS = {None, "more"}


@dataclass
class Interrupt:
    kind: str
    source: str
    detail: dict = field(default_factory=dict)
    decision_type: str | None = None

    def to_dict(self) -> dict:
        return {"kind": self.kind, "source": self.source, "decision_type": self.decision_type,
                "detail": self.detail}


@dataclass
class Before:
    """The parts of state an action is judged against."""
    turn: int
    hp: int
    xl: int
    level_seq: int
    place: str
    statuses: frozenset[str]
    hostile_ids: frozenset[int]
    features: dict
    items: frozenset
    frontier_groups: int
    msg_index: int

    @classmethod
    def capture(cls, state: GameState) -> "Before":
        return cls(
            turn=state.turn, hp=state.hp, xl=state.player.get("xl", 0),
            level_seq=state.level_seq, place=state.place,
            statuses=frozenset(state.statuses),
            hostile_ids=frozenset(m.id for m in state.hostiles()),
            features=dict(state.features()), items=frozenset(state.items()),
            frontier_groups=frontier_groups(state), msg_index=len(state.messages),
        )


def frontier_groups(state: GameState, radius: int = 7) -> int:
    """Count separate groups of walkable cells that border unexplored space near the player.

    Three or more groups means several unexplored directions: a junction.
    """
    px, py = state.pos
    cells = state.cells

    def walkable(c):
        return c is not None and c.get("mf", 0) not in NOT_WALKABLE

    frontier = set()
    for (x, y), c in cells.items():
        if max(abs(x - px), abs(y - py)) > radius or not walkable(c):
            continue
        if any((cells.get((x + dx, y + dy)) or {}).get("mf") == MF_UNEXPLORED
               for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy):
            frontier.add((x, y))
    groups = 0
    seen = set()
    for start in frontier:
        if start in seen:
            continue
        groups += 1
        stack = [start]
        seen.add(start)
        while stack:
            x, y = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (x + dx, y + dy)
                    if n in frontier and n not in seen:
                        seen.add(n)
                        stack.append(n)
    return groups


def feature_kind(state: GameState, pos, kind: str) -> str:
    if kind == "feature" and state.cells.get(pos, {}).get("g") == "_":
        return "altar"
    return kind


class Detector:
    """Stateful across actions: HP history, progress counter, debounce flags."""

    def __init__(self, slope_window: int = 5, slope_fraction: float = 0.3, no_progress_limit: int = 2):
        self.slope_window = slope_window
        self.slope_fraction = slope_fraction
        self.no_progress_limit = no_progress_limit
        self.hp_history: deque[tuple[int, int]] = deque(maxlen=64)
        self.slope_armed = True
        self.no_progress = 0

    def reset_level(self) -> None:
        self.hp_history.clear()
        self.slope_armed = True
        self.no_progress = 0

    def detect(self, before: Before, state: GameState, action: str, blocking: str | None,
               mode: str = "explore") -> list[Interrupt]:
        out: list[Interrupt] = []
        new_msgs = [m["text"] for m in state.messages[before.msg_index:]]
        joined = "\n".join(new_msgs)
        same_level = state.level_seq == before.level_seq

        # --- terminal / prompts -----------------------------------------
        if blocking == "died" or state.dead:
            return [Interrupt("died", "dcss", {"last_messages": new_msgs[-5:]})]
        if blocking not in HANDLED_BLOCKS:
            stat = blocking == "text_input" and "Increase (S)trength" in joined
            out.append(Interrupt("prompt", "ladder", {"reason": blocking},
                                 decision_type="stat_choice" if stat else None))

        # --- level change -----------------------------------------------
        if not same_level:
            self.reset_level()
            feats = sorted({feature_kind(state, p, k) for p, k in state.features().items()})
            out.append(Interrupt("level_change", "ladder", {"from": before.place, "to": state.place,
                                                            "features_seen": feats}))

        # --- hostiles (DCSS stops delays when they come into view) -------
        hostiles = state.hostiles()
        new_hostiles = [m for m in hostiles if m.id not in before.hostile_ids]
        refused = action in DELAY_ACTIONS and hostiles and RE_HOSTILE_STOP.search(joined)
        if new_hostiles or refused:
            shown = new_hostiles or hostiles
            out.append(Interrupt("hostile_in_view", "dcss", {
                "monsters": [{"name": m.name, "dist": state.distance(m.pos),
                              "threat": THREAT_NAMES.get(m.threat, m.threat), "unique": m.unique}
                             for m in shown],
                "explore_refused": bool(refused and not new_hostiles),
            }, decision_type="engage_unique" if any(m.unique for m in shown) else None))

        if same_level:
            # --- items and features (explore_stop) ------------------------
            new_items = state.items() - before.items
            if new_items:
                out.append(Interrupt("item_in_view", "dcss", {"count": len(new_items)}))
            for pos, kind in state.features().items():
                if pos in before.features:
                    continue
                kind = feature_kind(state, pos, kind)
                out.append(Interrupt("feature_in_view", "dcss",
                                     {"feature": kind, "glyph": state.cells[pos].get("g"),
                                      "dist": state.distance(pos)},
                                     decision_type=FEATURE_DECISIONS.get(kind)))

        # --- damage and message-shaped stops ------------------------------
        if action in DELAY_ACTIONS and same_level and state.hp < before.hp:
            out.append(Interrupt("hp_loss", "dcss", {"lost": before.hp - state.hp}))
        if RE_TELEPORT.search(joined):
            out.append(Interrupt("teleport", "dcss", {"message": _first(RE_TELEPORT, new_msgs)}))
        if RE_TRAP.search(joined):
            out.append(Interrupt("trap", "dcss", {"message": _first(RE_TRAP, new_msgs)}))
        for name, rx in RE_MESSAGE_STOPS:
            if rx.search(joined):
                out.append(Interrupt("message_stop", "dcss", {"pattern": name, "message": _first(rx, new_msgs)}))
        if action == "explore" and RE_EXPLORED.search(joined):
            out.append(Interrupt("level_explored", "dcss", {"message": _first(RE_EXPLORED, new_msgs)},
                                 decision_type="descend_stairs"))
        if state.player.get("xl", 0) > before.xl:
            out.append(Interrupt("xl_up", "ladder", {"xl": state.player.get("xl")}))

        # --- our detectors ------------------------------------------------
        out += self._hp_slope(before, state)
        added = sorted(set(state.statuses) - before.statuses)
        if added:
            out.append(Interrupt("status_change", "ladder",
                                 {"added": added, "removed": sorted(before.statuses - set(state.statuses))}))
        if mode == "travel" and same_level:
            groups = frontier_groups(state)
            if groups >= 3 and groups > before.frontier_groups:
                out.append(Interrupt("junction", "ladder", {"frontier_groups": groups}))

        # --- no progress (only when nothing else explains the stop) --------
        if action in TIMED_ACTIONS and state.turn == before.turn and same_level and not out:
            self.no_progress += 1
            if self.no_progress >= self.no_progress_limit:
                out.append(Interrupt("no_progress", "ladder", {"action": action, "repeats": self.no_progress,
                                                               "last_message": new_msgs[-1] if new_msgs else None}))
        elif state.turn != before.turn:
            self.no_progress = 0
        return out

    def _hp_slope(self, before: Before, state: GameState) -> list[Interrupt]:
        turn, hp, hp_max = state.turn, state.hp, state.hp_max
        for point in ((before.turn, before.hp), (turn, hp)):
            if not self.hp_history or self.hp_history[-1][0] != point[0]:
                self.hp_history.append(point)
            else:
                self.hp_history[-1] = point
        if hp >= 0.9 * hp_max:
            self.slope_armed = True
            return []
        window = [h for t, h in self.hp_history if turn - t <= self.slope_window]
        drop = max(window) - hp if window else 0
        if self.slope_armed and drop >= self.slope_fraction * hp_max:
            self.slope_armed = False
            return [Interrupt("hp_slope", "ladder", {"dropped": drop, "turns": self.slope_window,
                                                     "hp": hp, "hp_max": hp_max})]
        return []


def _first(rx: re.Pattern, texts: list[str]) -> str | None:
    return next((t for t in texts if rx.search(t)), None)
