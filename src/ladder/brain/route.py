"""`Style.lair`: the Lair detour. Find the Lair's entrance, go in, explore Lair:1 to Lair:`floors`, come back up and
go on down the Dungeon from the level of the entrance, as qw does with its goal list (runs/qw/build-zk/qw.lua:
`goal_normal_next` 3912-3990 enters the Lair as soon as `branch_found("Lair")` and the level in hand is explored,
`ready_for_lair` 4571-4586 always holds for a Trog worshipper; `explored_level_range("Lair")` then keeps it there until
Lair:1-5 are explored, and the next goal, D:12, takes it back up by interlevel travel, `plan_go_command` 12715-12735 with
`send_travel` 12681-12690).

Nothing here is an action: the route only changes where a "descend" goes. When the rules of thumb would take the
stairs down (or, on a level with none, have nothing left to do), `BrainTiers.auto_step` takes a "lair" step instead,
while the route wants one (`LairRoute.wants`):
- in the Dungeon, once the entrance is known: on the entrance's level, a step toward it, or `>` on it (with no known
  way to it, explore is let go on LAIR_NO_WAY times first); on a deeper
  level (a shaft, or a descend in a fight), a step toward the stairs up, or `<` on them;
- in the Lair, on Lair:`floors` or deeper, and on any Lair level once the way back has begun: a step toward the stairs
  up, or `<` on them. Above Lair:`floors` the rules' own descend goes on down the Lair.
So the rules still decide when a level is done (explored, or cut short by a rage), when to rest first and when to
fight; the route decides only which stairs.

The entrance is found by the rc's `ladder_find_lair` (LAIR_RC), bound to LAIR_KEY: it reads the game's map knowledge
(`view.feature_at`, the feature names qw reads) for "enter_lair" and prints where, relative to the character. It is
pressed when a branch staircase not yet looked at is on the map of a Dungeon level (`needs_scan`); it takes no game
time. The place bookkeeping (`arrived`) runs on every level change, from the game's own place and depth, so teleports,
shafts and stairs taken in a fight all land in the right phase.

Every loop is bounded: LAIR_ENTRIES entries at most, LAIR_FAILS steps that went nowhere or found no way, and
LAIR_CLIMB levels climbed back toward the entrance; past any of them the route is given up ("off") and the rules
descend as they would without it.
"""

from __future__ import annotations

import re

from ..state import MF_STAIR_BRANCH, GameState

LAIR_KEY = chr(9352)      # the rc's ladder_find_lair macro (LAIR_RC)
LAIR_FLOORS = {1: 4, 2: 5}   # Style.lair -> the deepest Lair level explored before turning back
LAIR_ENTRIES = 3          # entries into the Lair at most (fleeing up out of Lair:1 and going back in counts again)
LAIR_FAILS = 5            # "lair" steps that went nowhere, or found no known way, before the route is given up
LAIR_FROM = range(8, 12)  # the Dungeon levels the Lair's entrance is on (crawl-ref branch-data.h: BRANCH_LAIR, D 8-11)
LAIR_NO_WAY = 2           # times the entrance had no known way to it (explore is then let go on) before giving up
LAIR_CLIMB = 3            # Dungeon levels below the entrance's that the route climbs back from (else given up)

# The rc lines `Style.lair` adds (selfplay.py). The scan covers every map cell relative to the character (the map is
# 80 x 70), about 23,000 lookups: well inside the game's Lua throttle (50,000 instructions between pauses, 15 pauses).
LAIR_RC = """
{
function ladder_find_lair()
  local n = 0
  for x = -80, 80 do
    for y = -70, 70 do
      if view.feature_at(x, y) == "enter_lair" then
        crawl.mpr("ladder_lair " .. x .. " " .. y)
        n = n + 1
      end
    end
  end
  if n == 0 then crawl.mpr("ladder_lair none") end
end
}
macros += M \\{9352} ===ladder_find_lair
"""
# The game capitalises a message's first letter ("Ladder_lair -3 5"; seen in the real game, job `brain-v6m/probe1.py`)
LAIR_SEEN = re.compile(r"^ladder_lair (-?\d+) (-?\d+)$", re.I)


def where(state: GameState) -> tuple[str, int]:
    """(branch as webtiles names it, depth): "Dungeon" for D (an empty place too)."""
    return state.player.get("place") or "Dungeon", state.player.get("depth", 0) or 0


class LairRoute:
    """The detour's state across levels. Phases: "seek" (not yet entered, or out again before the way back began),
    "in" (in the Lair, going down), "back" (on the way up), "done" (out at the entrance's level), "off" (given up)."""

    def __init__(self, level: int):
        self.floors = LAIR_FLOORS.get(int(level), 4)
        self.entrance: tuple[int, tuple[int, int]] | None = None   # (Dungeon depth, map square)
        self.entrance_seq: int | None = None   # the level visit (`GameState.level_seq`) its square is counted in
        self.rescanned: int | None = None      # the visit last scanned, so a visit is scanned once at most
        self.no_way = 0                        # times no known way led to the entrance (LAIR_NO_WAY)
        self.scanned: set[tuple[int, tuple[int, int]]] = set()      # (level_seq, square) of branch stairs looked at
        self.phase = "seek"
        self.entries = 0
        self.fails = 0
        self.levels: list[int] = []        # Lair levels reached, in order of first arrival
        self.events: list[dict] = []       # for the end-of-game record
        self.why_off: str | None = None

    # --- bookkeeping ---------------------------------------------------

    def event(self, what: str, state: GameState, **extra) -> None:
        p = state.player
        branch, depth = where(state)
        self.events.append({"what": what, "place": f"{branch}:{depth}", "turn": state.turn, "xl": p.get("xl", 0),
                            "ac": p.get("ac", 0), "hp_max": p.get("hp_max", 0), **extra})

    def give_up(self, why: str, state: GameState) -> None:
        if self.phase != "off":
            self.phase, self.why_off = "off", why
            self.event("off", state, why=why)

    def arrived(self, state: GameState, came_from: str) -> None:
        """A level change (`BrainTiers.observe`): move the phase on from where the character now is."""
        branch, depth = where(state)
        if branch == "Lair":
            if not came_from.startswith("Lair"):
                self.entries += 1
                self.event("enter", state)
            if depth not in self.levels:
                self.levels.append(depth)
                self.event("arrive", state)
            if self.phase in ("seek", "done"):
                self.phase = "in"
            if self.phase == "in" and depth > self.floors:
                self.phase = "back"                  # a shaft or a descend in a fight took it past the last level
                self.event("back", state, why="below the last level")
        elif branch == "Dungeon" and came_from.startswith("Lair"):
            if self.phase == "back":
                self.phase = "done"
                self.event("out", state)
            elif self.phase == "in":
                # fled up out of Lair:1 before the way back began: go in again later, a bounded number of times
                self.event("fled_out", state)
                self.phase = "seek"
                if self.entries >= LAIR_ENTRIES:
                    self.give_up("entries", state)
        elif branch == "Dungeon" and self.phase == "done" and self.entrance and depth > self.entrance[0] and \
                not any(e["what"] == "resume" for e in self.events):
            self.event("resume", state)

    def needs_scan(self, state: GameState) -> bool:
        """Whether to press LAIR_KEY now: on a Dungeon level the Lair can hang from (LAIR_FROM), in "seek", either a
        branch staircase not yet looked at is on the map and the entrance isn't known, or this is the entrance's level
        on a visit after the one it was found on. Webtiles' map squares are counted from where each visit to a level
        began (the start of a game is (0, 0); job `brain-v6m/probe1.py`), so a square kept from another visit points
        somewhere else: in the first tuning run, 10 of the 28 games that found the entrance fled up out of Lair:1 (or
        left the level) and then gave the route up for "no known way" to a square that was no longer the entrance.
        Not on other levels: the key takes no game time but is a command all the same, and in the smoke run one game in
        18 that never reached the Lair played on differently after a scan on D:5 (the Temple's staircase)."""
        branch, depth = where(state)
        if self.phase != "seek" or branch != "Dungeon" or depth not in LAIR_FROM:
            return False
        if self.entrance:
            return depth == self.entrance[0] and self.entrance_seq != state.level_seq and \
                self.rescanned != state.level_seq
        return any(c.get("mf") == MF_STAIR_BRANCH and (state.level_seq, pos) not in self.scanned
                   for pos, c in state.cells.items())

    def scanned_now(self, state: GameState, texts: list[str]) -> None:
        """After LAIR_KEY: note every branch staircase on this level as looked at, and the entrance if printed (again,
        in this visit's squares, when it was known from another visit; not printed then, the route is given up)."""
        self.scanned |= {(state.level_seq, pos) for pos, c in state.cells.items() if c.get("mf") == MF_STAIR_BRANCH}
        again = self.entrance is not None
        self.rescanned = state.level_seq
        px, py = state.pos
        for t in texts:
            hit = LAIR_SEEN.match(t.strip())
            if hit:
                self.entrance = (where(state)[1], (px + int(hit.group(1)), py + int(hit.group(2))))
                self.entrance_seq = state.level_seq
                self.event("found_again" if again else "found", state, square=list(self.entrance[1]))
                return
        if again:
            self.give_up("the entrance not found again", state)

    # --- what to do ----------------------------------------------------

    def target(self, state: GameState) -> str | None:
        """Where the next "lair" step goes now: "entrance", "up", or None (the rules' own descend)."""
        branch, depth = where(state)
        if self.phase == "seek" and self.entrance and branch == "Dungeon":
            if depth == self.entrance[0]:
                # a square from another visit is no square here: scan first (`needs_scan`)
                return "entrance" if self.entrance_seq == state.level_seq else None
            if depth > self.entrance[0]:
                return "up"
            return None
        if branch == "Lair" and (self.phase == "back" or (self.phase == "in" and depth >= self.floors)):
            return "up"
        return None

    def wants(self, state: GameState) -> bool:
        """Whether a descend now should be a "lair" step instead (and, on Lair:`floors`, the way back starts)."""
        aim = self.target(state)
        if aim == "up" and where(state)[0] == "Dungeon" and self.entrance and \
                where(state)[1] - self.entrance[0] > LAIR_CLIMB:
            self.give_up("too deep below the entrance", state)
            return False
        return aim is not None

    def start_back(self, state: GameState) -> None:
        if self.phase == "in":
            self.phase = "back"
            self.event("back", state, why="last level done")

    def failed(self, state: GameState, why: str) -> None:
        self.fails += 1
        if self.fails >= LAIR_FAILS:
            self.give_up(f"fails: {why}", state)

    def record(self) -> dict:
        return {"floors": self.floors, "phase": self.phase, "entrance": list(self.entrance[1]) if self.entrance else None,
                "entrance_depth": self.entrance[0] if self.entrance else None, "entries": self.entries,
                "levels": self.levels, "fails": self.fails, "why_off": self.why_off, "events": self.events}
