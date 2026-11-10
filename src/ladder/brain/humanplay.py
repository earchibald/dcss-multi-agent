"""A person's games as step logs, so the brain learns from human play.

The cockpit's recording proxy (playproxy.py) writes `runs/<dir>/play<n>.jsonl`: the game's messages and the
player's keys in the order they passed, so each key sits after the state it answered. `convert` replays one
through a `GameState` and cuts the keys into commands: the keys from one moment the game waits for a command
(input_mode 1) up to the next. A command that is one of the brain's macro-actions (features.ACTIONS) and took
game time becomes a step line in selfplay.py's format, marked `"source": "human"`, with the observation taken
just before its first key. corpus.py reads both the same way, and its "human" column is what trains the prior.

What maps onto what (anything else, such as menus, equipment, spells, looking, picking up, walking around
by hand, is counted by reason and skipped):
    o                       explore
    Tab, a step or ctrl-step into a hostile, or toward the nearest one         fight
    a step with hostiles in view that brings the known upstairs one closer      flee_up
    5                       rest;  s . Del: wait if hostiles are in view and none adjacent, rest if hurt and alone
    > or G then >           descend;  < with hostiles in view: flee_up
    q / r + item            quaff_heal / quaff_unknown / read_teleport / read_unknown, by the stack it used up

A command whose turn counter didn't move (a refused key, a cancelled menu, "Done exploring") is skipped,
so repeated keys collapse on their own and a fight gives one row per blow, as the bot logs one per Tab.

Key encoding, checked against the recordings and the webtiles server's key_conversion.js: printable keys
arrive as {"msg": "input", "text": ...}; Tab, Escape, ctrl-letters (the letter's code - 64: ctrl-X is 24),
arrows, Home/End/PgUp/PgDn and numpad keys as {"msg": "key", "keycode": ...} with the cio.h codes below.

Only the game's messages and the keys are read; the proxy never records logins or tokens, and nothing raw
is printed or copied here.
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from ..interrupts import RE_EXPLORED
from ..state import MF_STAIR_UP, MF_TRAP, NOT_WALKABLE, GameState, Monster
from .features import ACTIONS, HEALING, POTIONS, SCROLLS, observe, progress_depth
from .policy import available, baseline

MODE_COMMAND = 1                      # webtiles input_mode: waiting for a command
PLAY_FILE = re.compile(r"play(\d+)\.jsonl")

STEPS = {"h": (-1, 0), "j": (0, 1), "k": (0, -1), "l": (1, 0), "y": (-1, -1), "u": (1, -1), "b": (-1, 1), "n": (1, 1)}
DIGITS = dict(zip("12346789", "bjnhlyku"))
# cio.h codes (webtiles key_conversion.js) in the order up, down, left, right, -, home, end, clear, pgup, pgdn
_NAV = "kjhl?yb.un"
KEYCODES: dict[int, str] = {9: "\t", 13: "\r", 27: "esc", -255: "."}         # Delete waits, like s and .
KEYCODES |= {-254 + i: k for i, k in enumerate(_NAV) if k != "?"}
KEYCODES |= {-243 + i: k.upper() for i, k in enumerate(_NAV) if k not in "?."}  # shift: run
KEYCODES |= {-232 + i: "^" + k for i, k in enumerate(_NAV) if k not in "?."}    # ctrl: attack in place
KEYCODES |= {-1000 - int(d): d for d in "12346789"} | {-1005: "."}            # numpad (0.27+ code conversion)
ITEM_VERBS = {"q": POTIONS, "r": SCROLLS}


def key_tokens(msg: dict) -> list[str]:
    """The keys in one player message, as the characters DCSS's command keys use ("^x" for ctrl-x)."""
    if msg.get("msg") == "input":
        return list(msg.get("text") or "")
    code = msg.get("keycode")
    if msg.get("msg") != "key" or not isinstance(code, int):
        return []
    if code in KEYCODES:
        return [KEYCODES[code]]
    if 0 < code < 27:
        return ["^" + chr(code + 96)]
    return [chr(code)] if 32 <= code < 127 else [f"<{code}>"]


def step_of(key: str) -> tuple[int, int] | None:
    """The direction a movement key (plain, shifted, ctrl, digit, arrow) points, if it is one."""
    base = key[1:] if len(key) == 2 and key[0] == "^" else key
    base = DIGITS.get(base, base)
    return STEPS.get(base.lower()) if len(base) == 1 else None


def game_messages(line: dict) -> list[dict]:
    """The proxy unbundles webtiles' {"msgs": [...]} frames, but take a bundle if one slips through."""
    msg = line.get("msg") or {}
    if "msg" not in msg and isinstance(msg.get("msgs"), list):
        return msg["msgs"]
    return [msg]


def _dist_from(state: GameState, goal_mf: int) -> dict[tuple[int, int], int]:
    """Walking distance from every known cell to the nearest cell with `goal_mf` (features.path's rules)."""
    cells = state.cells
    dist = {pos: 0 for pos, c in cells.items() if c.get("mf") == goal_mf}
    queue = deque(dist)
    while queue:
        cur = queue.popleft()
        for dx, dy in STEPS.values():
            nxt = (cur[0] + dx, cur[1] + dy)
            cell = cells.get(nxt)
            if nxt in dist or cell is None or cell.get("mf", 0) in NOT_WALKABLE or cell.get("mf") == MF_TRAP:
                continue
            dist[nxt] = dist[cur] + 1
            queue.append(nxt)
    return dist


def _stacks(state: GameState) -> dict[str, tuple[int, str, int]]:
    """slot -> (base type, name, quantity) for potions and scrolls."""
    return {slot: (it.get("base_type"), it.get("name", ""), it.get("quantity", 1) or 0)
            for slot, it in (state.player.get("inv") or {}).items() if it.get("base_type") in (POTIONS, SCROLLS)}


def item_action(base: int, name: str) -> str | None:
    """The macro-action using this potion or scroll is, by what it was called before use (features.inventory)."""
    if " of " not in name or "{unknown}" in name:
        return "quaff_unknown" if base == POTIONS else "read_unknown"
    if base == POTIONS:
        return "quaff_heal" if any(h in name for h in HEALING) else None
    return "read_teleport" if "teleportation" in name else None


def _dungeon_top(state: GameState) -> bool:
    return state.player.get("place", "") in ("", "Dungeon") and state.player.get("depth", 0) <= 1


@dataclass
class Command:
    """The keys typed from one wait for a command to the next, and the moment before the first."""
    keys: list[str]
    index: int
    turn: int
    level_seq: int
    msg_index: int
    obs: dict
    stacks: dict
    action: str | None = None         # what the first key means, if known before seeing what happened
    reason: str | None = None         # why it can't be a row, if known already


@dataclass
class Converter:
    game: int | str
    state: GameState = field(default_factory=GameState)
    rows: list[dict] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    keys_seen: int = 0
    level_seq: int = -1
    level_explored: bool = False
    level_steps: int = 0
    level_turn: int = 0
    prev_frac: float | None = None
    last_action: str | None = None
    max_depth: int = 0
    first_turn: int | None = None
    ready: bool = False
    current: Command | None = None
    commands: int = 0

    def feed(self, line: dict) -> None:
        if line.get("from") == "game":
            for msg in game_messages(line):
                self.state.apply(msg)
                if msg.get("msg") == "input_mode":
                    self.ready = msg.get("mode") == MODE_COMMAND
                elif msg.get("msg") == "msgs" and any(RE_EXPLORED.search(m.get("text", "")) for m in msg.get("messages", [])):
                    self._sync_level()
                    self.level_explored = True
        elif line.get("from") == "player":
            for key in key_tokens(line.get("msg") or {}):
                self.keys_seen += 1
                if self.ready:
                    self._close()
                    self._open(key)
                    self.ready = False
                elif self.current is not None:
                    self.current.keys.append(key)
                else:
                    self._skip("not_at_command")

    def _skip(self, reason: str, n: int = 1) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + n

    def _sync_level(self) -> None:
        if self.state.level_seq != self.level_seq:
            self.level_seq = self.state.level_seq
            self.level_explored, self.level_steps, self.level_turn = False, 0, self.state.turn

    def _open(self, key: str) -> None:
        state = self.state
        self._sync_level()
        p = state.player
        self.max_depth = max(self.max_depth, progress_depth(p.get("place", ""), p.get("depth", 0)))
        if self.first_turn is None:
            self.first_turn = state.turn
        hostiles = state.hostiles()
        frac = state.hp / state.hp_max
        obs = observe(state, hostiles, {
            "level_explored": self.level_explored, "level_steps": self.level_steps, "level_turn": self.level_turn,
            "hp_delta": 0.0 if self.prev_frac is None else frac - self.prev_frac, "last_action": self.last_action})
        self.commands += 1
        cmd = Command([key], self.commands, state.turn, state.level_seq, len(state.messages), obs, _stacks(state))
        cmd.action, cmd.reason = self._meaning(key, hostiles)
        self.current = cmd

    def _meaning(self, key: str, hostiles: list[Monster]) -> tuple[str | None, str | None]:
        """What the first key of a command means in the state it answered: (action, None) or (None, reason).
        Prefix keys (q, r, G) are settled in _close, once the rest of the command is known."""
        state = self.state
        near = min((state.distance(m.pos) for m in hostiles), default=None)
        if key == "o":
            return "explore", None
        if key == "\t":
            return "fight", None
        if key == "5":
            return "rest", None
        if key in ("s", "."):
            if near is None:
                return ("rest", None) if state.hp < state.hp_max else (None, "wait_unhurt")
            return ("wait", None) if near > 1 else (None, "wait_adjacent")
        if key == ">":
            return "descend", None
        if key == "<":
            return ("flee_up", None) if hostiles else (None, "upstairs")
        if key in ITEM_VERBS or key == "G":
            return None, None
        step = step_of(key)
        if step is None:
            return None, "unmapped"
        if not hostiles:
            return None, "manual_move"
        px, py = state.pos
        to = (px + step[0], py + step[1])
        if any(m.pos == to for m in hostiles) or min(max(abs(m.pos[0] - to[0]), abs(m.pos[1] - to[1])) for m in hostiles) < near:
            return "fight", None
        # the stairs up from D:1 leave the dungeon: never a flight
        if _dungeon_top(state):
            return None, "move_with_hostiles"
        dist = _dist_from(state, MF_STAIR_UP)
        if state.pos in dist and dist.get(to, -1) == dist[state.pos] - 1:
            return "flee_up", None
        return None, "move_with_hostiles"

    def _close(self) -> None:
        cmd, self.current = self.current, None
        if cmd is None:
            return
        state = self.state
        action, reason = cmd.action, cmd.reason
        first = cmd.keys[0]
        # A one-key command's later keys, typed before the game was ready again, answered a --more--
        # or a death screen, or were typed ahead; they aren't part of it. Unknown commands keep theirs.
        whole = first in ITEM_VERBS or first == "G" or reason == "unmapped"
        extra = 0 if whole else len(cmd.keys) - 1
        if extra:
            self._skip("while_busy", extra)
        if first in ITEM_VERBS:
            action, reason = self._used_item(cmd, ITEM_VERBS[first])
        elif first == "G":
            action, reason = ("descend", None) if ">" in cmd.keys[1:2] else (None, "travel")
        # the blow that kills you sends no new turn count, and it is the row that matters most
        took_time = state.turn != cmd.turn or state.level_seq != cmd.level_seq or state.dead
        if action and not took_time:
            action, reason = None, "no_turn"
        if action is None:
            self._skip(reason or "unmapped", len(cmd.keys) - extra)
            return
        self._emit(cmd, action)

    def _used_item(self, cmd: Command, base: int) -> tuple[str | None, str | None]:
        now = _stacks(self.state)
        used = [v for slot, v in cmd.stacks.items() if v[0] == base and (slot not in now or now[slot][2] < v[2])]
        if len(used) != 1:
            return None, "item_cancelled" if not used else "item_unclear"
        action = item_action(used[0][0], used[0][1])
        return (action, None) if action else (None, "item_other")

    def _emit(self, cmd: Command, action: str) -> None:
        obs = cmd.obs
        bot = available(obs, obs["level_explored"], set(), False)
        # the person can do what the bot's rules wouldn't allow; the baseline stays the bot's own pick
        avail = [a for a in ACTIONS if a in bot or a == action]
        self.rows.append({"game": self.game, "step": cmd.index, "obs": obs, "avail": avail,
                          "baseline": baseline(obs, bot or avail, obs["level_explored"]), "action": action,
                          "source": "human"})
        self.prev_frac = obs["hp"] / max(obs["hp_max"], 1)
        self.last_action = action
        if cmd.level_seq == self.level_seq:
            self.level_steps += 1

    def finish(self) -> dict:
        self._close()
        state, p = self.state, self.state.player
        self.max_depth = max(self.max_depth, progress_depth(p.get("place", ""), p.get("depth", 0)))
        return {"type": "end", "game": self.game, "died": state.dead, "turn": state.turn, "place": p.get("place", ""),
                "depth": p.get("depth", 0), "xl": p.get("xl", 1), "progress": p.get("progress", 0),
                "hp": state.hp, "hp_max": state.hp_max, "ended_by": "died" if state.dead else "left",
                "max_depth": self.max_depth, "steps": len(self.rows), "source": "human",
                "last_messages": state.recent_messages(4)}


def out_dir(play_file: Path, out_root: Path) -> Path:
    return Path(out_root) / f"{play_file.parent.name}-{play_file.stem}"


def convert(play_file: str | Path, out_root: str | Path) -> dict:
    """Write `<out_root>/<run dir>-<play stem>/steps.jsonl` for one recording; return what it yielded."""
    play_file = Path(play_file)
    m = PLAY_FILE.fullmatch(play_file.name)
    conv = Converter(game=int(m.group(1)) if m else play_file.stem)
    with play_file.open() as f:
        for raw in f:
            try:
                line = json.loads(raw)
            except json.JSONDecodeError:
                continue                      # a recording cut off mid-line
            if isinstance(line, dict):
                conv.feed(line)
    end = conv.finish()
    directory = out_dir(play_file, Path(out_root))
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "steps.jsonl").open("w") as out:
        for row in conv.rows:
            out.write(json.dumps(row) + "\n")
        out.write(json.dumps(end) + "\n")
    by_action: dict[str, int] = {}
    for row in conv.rows:
        by_action[row["action"]] = by_action.get(row["action"], 0) + 1
    turns = [r["obs"]["turn"] for r in conv.rows]
    return {"file": str(play_file), "out": str(directory / "steps.jsonl"), "rows": len(conv.rows),
            "by_action": by_action, "keys": conv.keys_seen, "commands": conv.commands,
            "skipped": dict(sorted(conv.skipped.items(), key=lambda kv: -kv[1])),
            "turns": [conv.first_turn, end["turn"]] if conv.first_turn is not None else None,
            "row_turns": [min(turns), max(turns)] if turns else None,
            "died": end["died"], "max_depth": end["max_depth"]}


def convert_all(runs_root: str | Path, out_root: str | Path) -> list[dict]:
    """Convert every play<n>.jsonl under `runs_root` whose output is missing or older than it."""
    done = []
    for play_file in sorted(Path(runs_root).rglob("play*.jsonl")):
        if not PLAY_FILE.fullmatch(play_file.name):
            continue                          # player<n>.protocol.jsonl: the spectator's, with no keys
        steps = out_dir(play_file, Path(out_root)) / "steps.jsonl"
        if steps.exists() and steps.stat().st_mtime >= play_file.stat().st_mtime:
            continue
        done.append(convert(play_file, out_root))
    return done
