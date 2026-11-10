"""What the trained brain sees: an observation dict, and the numbers made from it.

`observe` reads a `GameState` into a plain JSON dict (the thing a step log stores).
`encode` turns that dict into the network's inputs. Keeping the two apart means a logged game
can be re-encoded after the features change.

Changing ACTIONS, COMPONENTS or what `encode` emits breaks the model contract: bump
FEATURE_VERSION, rebuild the corpus and retrain. `TrainedNet` refuses a mismatched model.
"""

from __future__ import annotations

import zlib
from collections import deque

import numpy as np

from ..state import MF_STAIR_DOWN, MF_STAIR_UP, MF_TRAP, NOT_WALKABLE, GameState, Monster
from ..travel import DIRECTIONS

FEATURE_VERSION = 2

# What the brain can ask Reflex to do. Order is the model's output order.
ACTIONS = ["explore", "fight", "rest", "descend", "flee_up", "quaff_heal", "quaff_unknown",
           "read_unknown", "read_teleport", "wait", "berserk"]
N_ACTIONS = len(ACTIONS)

# What the network predicts for each action (corpus.py computes them from what happened next).
COMPONENTS = ["died_soon", "hp_lost", "xp_soon", "depth_go", "xp_go", "died_go"]
N_COMPONENTS = len(COMPONENTS)

MAX_MONS = 8
NAME_BUCKETS = 24
STATUSES = ["Pois", "Conf", "Slow", "Fast", "Berserk", "-Berserk", "Might", "Held", "Corr", "Para", "Tele",
            "Drain", "Weak", "Invis", "Constr", "silenced", "Blind", "Vertigo"]

POTIONS, SCROLLS = 7, 5
HEALING = ("curing", "heal wounds")
# places below the Dungeon count as deeper than its early floors
BRANCH_BASE = {"Dungeon": 0, "Temple": 4, "Lair": 9, "Orcish Mines": 10, "Sewer": 3, "Ossuary": 4,
               "Bailey": 8, "Ice Cave": 10, "Volcano": 10}
DEEP_BRANCH = 14


def progress_depth(place: str, depth: int) -> int:
    """One number for "how far in": Dungeon floors count as themselves, branches from where they hang."""
    return BRANCH_BASE.get(place or "Dungeon", DEEP_BRANCH) + (depth or 0)


def path(state: GameState, goal_mf: int) -> tuple[str | None, int]:
    """(first step key, length) of the shortest known walk to a cell with `goal_mf`; (None, -1) if none."""
    start, cells = state.pos, state.cells
    prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    dist = {start: 0}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if cur != start and cells.get(cur, {}).get("mf") == goal_mf:
            n = dist[cur]
            while prev[cur] != start:
                cur = prev[cur]
            return DIRECTIONS[(cur[0] - start[0], cur[1] - start[1])], n
        for dx, dy in DIRECTIONS:
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in prev:
                continue
            cell = cells.get(nxt)
            if cell is None or cell.get("mf", 0) in NOT_WALKABLE or cell.get("mf") == MF_TRAP:
                continue
            prev[nxt] = cur
            dist[nxt] = dist[cur] + 1
            queue.append(nxt)
    return None, -1


def inventory(state: GameState) -> dict:
    """The consumables the brain has actions for, with the letter of one of each kind."""
    out = {"heal": 0, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 0, "letters": {}}
    for item in (state.player.get("inv") or {}).values():
        name, qty, base = item.get("name", ""), item.get("quantity", 1) or 0, item.get("base_type")
        if not name or qty <= 0 or base not in (POTIONS, SCROLLS):
            continue
        known = " of " in name and "{unknown}" not in name
        if base == POTIONS:
            kind = ("heal" if any(h in name for h in HEALING) else None) if known else "unknown_potions"
        else:
            kind = ("teleport" if "teleportation" in name else None) if known else "unknown_scrolls"
        if kind:
            out[kind] += qty
            out["letters"].setdefault(kind, chr(item.get("letter", ord("a"))))
    return out


def observe(state: GameState, hostiles: list[Monster], ctx: dict) -> dict:
    """The moment as a JSON dict. `ctx` is what the tiers object remembers (see policy.BrainTiers)."""
    p = state.player
    px, py = state.pos
    here = state.cells.get(state.pos, {}).get("mf")
    d_down = 0 if here == MF_STAIR_DOWN else path(state, MF_STAIR_DOWN)[1]
    d_up = 0 if here == MF_STAIR_UP else path(state, MF_STAIR_UP)[1]
    mons = sorted(hostiles, key=lambda m: state.distance(m.pos))
    open_n = sum(1 for dx, dy in DIRECTIONS
                 if (c := state.cells.get((px + dx, py + dy))) and c.get("mf", 0) not in NOT_WALKABLE)
    return {
        "turn": state.turn, "place": p.get("place", ""), "depth": p.get("depth", 0),
        "hp": state.hp, "hp_max": state.hp_max, "mp": p.get("mp", 0), "mp_max": p.get("mp_max", 0),
        "xl": p.get("xl", 1), "progress": p.get("progress", 0),
        "ac": p.get("ac", 0), "ev": p.get("ev", 0), "sh": p.get("sh", 0),
        "str": p.get("str", 0), "int": p.get("int", 0), "dex": p.get("dex", 0),
        "poison_survival": p.get("poison_survival", state.hp),
        "god": p.get("god") or "", "piety": p.get("piety_rank", 0),
        "status": state.statuses,
        "mons": [{"name": m.name, "dx": m.pos[0] - px, "dy": m.pos[1] - py, "threat": m.threat,
                  "unique": m.unique} for m in mons[:MAX_MONS]],
        "n_hostiles": len(mons),
        "inv": {k: v for k, v in inventory(state).items() if k != "letters"},
        "on_down": here == MF_STAIR_DOWN, "on_up": here == MF_STAIR_UP,
        "dist_down": d_down, "dist_up": d_up, "open_neighbors": open_n,
        "level_explored": bool(ctx.get("level_explored")),
        "level_steps": ctx.get("level_steps", 0), "level_turns": state.turn - ctx.get("level_turn", state.turn),
        "hp_delta": ctx.get("hp_delta", 0.0), "last_action": ctx.get("last_action"),
    }


def _cap(x: float, hi: float) -> float:
    return max(0.0, min(float(x), hi)) / hi


def encode(obs: dict, avail: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(self vector [SELF_DIM], monsters [MAX_MONS, MON_DIM], monster mask [MAX_MONS])."""
    hp_max = max(obs["hp_max"], 1)
    mons = obs["mons"]
    dists = [max(abs(m["dx"]), abs(m["dy"])) for m in mons]
    inv = obs["inv"]
    status = obs.get("status") or []
    s = [
        obs["hp"] / hp_max, _cap(hp_max, 200), obs["mp"] / max(obs["mp_max"], 1), _cap(obs["xl"], 27),
        _cap(obs["progress"], 100), _cap(obs["ac"], 40), _cap(obs["ev"], 40), _cap(obs["sh"], 40),
        _cap(obs["str"], 40), _cap(obs["int"], 40), _cap(obs["dex"], 40),
        _cap(progress_depth(obs["place"], obs["depth"]), 30), float(obs["place"] in ("", "Dungeon")),
        _cap(obs["poison_survival"], hp_max),
        _cap(obs["n_hostiles"], 8), _cap(sum(d <= 1 for d in dists), 8), _cap(min(dists, default=8), 8),
        _cap(max((m["threat"] for m in mons), default=0), 3), _cap(sum(m["threat"] for m in mons), 10),
        float(any(m["unique"] for m in mons)),
        _cap(inv["heal"], 5), _cap(inv["unknown_potions"], 5), _cap(inv["unknown_scrolls"], 5), _cap(inv["teleport"], 3),
        float(obs["on_down"]), float(obs["on_up"]), float(obs["dist_down"] >= 0), _cap(obs["dist_down"], 60),
        float(obs["dist_up"] >= 0), _cap(obs["dist_up"], 60), _cap(obs["open_neighbors"], 8),
        float(obs["level_explored"]), _cap(obs["level_steps"], 200), _cap(obs["level_turns"], 3000),
        max(-1.0, min(1.0, obs["hp_delta"])),
        float(obs.get("god") == "Trog"), _cap(obs.get("piety", 0), 6),
    ]
    s += [float(any(x.startswith(name) for x in status)) for name in STATUSES]
    s += [float(obs.get("last_action") == a) for a in ACTIONS]
    s += [float(a in avail) for a in ACTIONS]
    m_arr = np.zeros((MAX_MONS, MON_DIM), dtype=np.float32)
    mask = np.zeros(MAX_MONS, dtype=np.float32)
    for i, (m, d) in enumerate(zip(mons[:MAX_MONS], dists)):
        row = [_cap(d, 8), m["dx"] / 8, m["dy"] / 8, float(d <= 1), float(m["unique"])]
        row += [float(m["threat"] == t) for t in range(4)]
        bucket = zlib.crc32(m["name"].lower().encode()) % NAME_BUCKETS
        row += [float(b == bucket) for b in range(NAME_BUCKETS)]
        m_arr[i] = row
        mask[i] = 1
    return np.asarray(s, dtype=np.float32), m_arr, mask


MON_DIM = 5 + 4 + NAME_BUCKETS
SELF_DIM = 37 + len(STATUSES) + 2 * N_ACTIONS
