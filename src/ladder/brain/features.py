"""What the trained brain sees: an observation dict, and the numbers made from it.

`observe` reads a `GameState` into a plain JSON dict (the thing a step log stores).
`encode` turns that dict into the network's inputs. Keeping the two apart means a logged game
can be re-encoded after the features change.

Changing ACTIONS, COMPONENTS or what `encode` emits breaks the model contract: bump
FEATURE_VERSION, rebuild the corpus and retrain. `TrainedNet` refuses a mismatched model.

Version 5 keeps version 4's numbers as the front of each vector (SELF_GROUPS, MON_GROUPS) and adds:
  - "table": per monster, what the shipped monster table (monsters.py) says about its name; totals over
    the view in the character vector. Needs only the names, so every logged step re-encodes.
  - "seen": what `sight` reads from the game state beyond names: each monster's damage level,
    behaviour, poison, net or web, status icons and estimated HP left; the weapon in hand; a few
    numbers about the map around the character. Steps logged before version 5 get these from
    `ladder brain reobserve`, which replays the protocol log; a step without them has `seen_missing`
    set and zeros, never zeros alone.
"""

from __future__ import annotations

import math
import zlib
from collections import deque

import numpy as np

from ..state import MF_STAIR_DOWN, MF_STAIR_UP, MF_TRAP, MF_UNEXPLORED, MF_UNSEEN, NOT_WALKABLE, GameState, Monster
from ..travel import DIRECTIONS
from . import gear, monsters

FEATURE_VERSION = 5
SIGHT_VERSION = 1          # the `obsx` field of an observation: which `sight` fields it carries

# What the brain can ask Reflex to do. Order is the model's output order.
ACTIONS = ["explore", "fight", "rest", "descend", "flee_up", "quaff_heal", "quaff_unknown",
           "read_unknown", "read_teleport", "wait", "berserk", "wield", "wear"]
N_ACTIONS = len(ACTIONS)

# What the network predicts for each action (corpus.py computes them from what happened next).
COMPONENTS = ["died_soon", "hp_lost", "xp_soon", "depth_go", "xp_go", "died_go", "depth_end"]
N_COMPONENTS = len(COMPONENTS)

MAX_MONS = 8
NAME_BUCKETS = 24
STATUSES = ["Pois", "Conf", "Slow", "Fast", "Berserk", "-Berserk", "Might", "Held", "Corr", "Para", "Tele",
            "Drain", "Weak", "Invis", "Constr", "silenced", "Blind", "Vertigo"]

POTIONS, SCROLLS = 7, 5
# Both count as `heal` (one input, one action), but they do different things (potion.cc): curing heals
# 5-11 and ends poison and confusion; heal wounds heals 10-37 and cures nothing. `inventory` also counts
# them apart, and `quaff_heal` picks one by the need (policy.heal_potion). Not inputs: no contract change.
CURING, HEAL_WOUNDS = "curing", "heal wounds"
HEALING = (CURING, HEAL_WOUNDS)
# places below the Dungeon count as deeper than its early floors
BRANCH_BASE = {"Dungeon": 0, "Temple": 4, "Lair": 9, "Orcish Mines": 10, "Sewer": 3, "Ossuary": 4,
               "Bailey": 8, "Ice Cave": 10, "Volcano": 10}
DEEP_BRANCH = 14


def progress_depth(place: str, depth: int) -> int:
    """One number for "how far in": Dungeon floors count as themselves, branches from where they hang."""
    return BRANCH_BASE.get(place or "Dungeon", DEEP_BRANCH) + (depth or 0)


# The Lair and the branches below it (webtiles' place names). `Style.lair` goes there and comes back; the score stays
# the deepest Dungeon level.
LAIR_BRANCHES = {"Lair", "Swamp", "Shoals", "Snake Pit", "Spider Nest", "Slime Pits"}


def score_depth(place: str, depth: int) -> int:
    """The number a game's `max_depth` (its score) is the largest of: `progress_depth`, except that a place in the Lair
    or below it counts 0, so a game that dies in the Lair scores the deepest Dungeon level it reached. Every other place
    counts as before the Lair detour existed (the Abyss, reached by banishment, still as DEEP_BRANCH + its depth), so
    runs played without `Style.lair`, which never enter the Lair, score exactly as they did."""
    return 0 if place in LAIR_BRANCHES else progress_depth(place, depth)


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


def inventory(state: GameState, largest: bool = False) -> dict:
    """The consumables the brain has actions for, with the letter of one of each kind.

    The letter is the first stack found, or with `largest` the biggest stack: among unknowns that is the
    likeliest to be a common kind (curing, identify), and trying it tells the most.
    """
    out = {"heal": 0, "curing": 0, "heal_wounds": 0, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 0,
           "letters": {}}
    biggest: dict[str, int] = {}
    for item in (state.player.get("inv") or {}).values():
        name, qty, base = item.get("name", ""), item.get("quantity", 1) or 0, item.get("base_type")
        if not name or qty <= 0 or base not in (POTIONS, SCROLLS):
            continue
        known = " of " in name and "{unknown}" not in name
        if base == POTIONS:
            kind = ("heal" if any(h in name for h in HEALING) else None) if known else "unknown_potions"
        else:
            kind = ("teleport" if "teleportation" in name else None) if known else "unknown_scrolls"
        # a healing potion is also counted as itself, so `perform` can choose between the two
        which = ("curing" if CURING in name else "heal_wounds") if kind == "heal" else None
        for k in filter(None, (kind, which)):
            out[k] += qty
            if k not in out["letters"] or (largest and qty > biggest[k]):
                out["letters"][k], biggest[k] = chr(item.get("letter", ord("a"))), qty
    return out


# --- what `sight` reads beyond names (FEATURE_VERSION 5) ------------------------------------------------

# A cell's foreground tile flags (webtiles enums.js, fg_flags), as one 64-bit number: an int, or
# [low, high] 32-bit words once the high word is used.
FG_BEH_SHIFT, FG_MDAM_SHIFT, FG_POISON_SHIFT = 20, 30, 59
FG_NET, FG_WEB = 0x00800000, 0x01000000
# behaviour: STAB is asleep (or otherwise helpless), MAY_STAB unaware or wandering
BEHAVIOUR = {1: "asleep", 2: "unaware", 3: "fleeing", 4: "paralysed"}
# damage level -> share of max HP left, the middle of the band `mons_get_damage_level` (mon-util.cc)
# reports: none, light (<100%), moderate (<=80%), heavy (<=60%), severe (<=40%), almost dead (<=20%)
MDAM_LEFT = {0: 1.0, 1: 0.9, 2: 0.7, 3: 0.5, 4: 0.3, 7: 0.1}
# status icons on a monster's cell (t.icons): tile numbers of DCSS 0.34's TILEI_* (tiledef-icons.h)
ICONS = {10192: "summoned", 10191: "summoned", 10201: "berserk", 10202: "frenzied", 10203: "slowed",
         10204: "hasted", 10205: "might", 10206: "petrifying", 10207: "petrified", 10208: "blind",
         10211: "confused", 10219: "corroded", 10220: "swift", 10228: "dazed", 10237: "weakened",
         10245: "paralysed", 10198: "sticky_flame", 10200: "constricted", 10238: "teleporting"}
BUFFED = {"berserk", "frenzied", "hasted", "might", "swift"}
DEBUFFED = {"slowed", "petrifying", "petrified", "blind", "confused", "corroded", "dazed", "weakened",
            "paralysed", "sticky_flame", "constricted"}
RAY = 7                    # how far the map rays look


def fg_bits(cell: dict) -> int | None:
    """A cell's foreground flags as one number, or None if the cell has none."""
    fg = (cell.get("t") or {}).get("fg")
    if fg is None:
        return None
    if isinstance(fg, list):
        return (fg[0] & 0xFFFFFFFF) | ((fg[1] if len(fg) > 1 else 0) << 32)
    return fg & 0xFFFFFFFF


def _walkable(state: GameState, pos: tuple[int, int]) -> bool:
    c = state.cells.get(pos)
    return c is not None and c.get("mf", 0) not in NOT_WALKABLE


def sight(state: GameState, mons: list[Monster]) -> dict:
    """The observation fields added in FEATURE_VERSION 5 that need the game state, not only names.

    `mons` are the monsters in the order of the observation's "mons". Returns {"mons": [per monster],
    "wpn", "wpn_held", "map", "obsx"}; observe() merges it in, and `reobserve` rebuilds it for steps logged
    before it existed.
    """
    px, py = state.pos
    per = []
    for m in mons:
        cell = state.cells.get(m.pos, {})
        v = fg_bits(cell)
        icons = (cell.get("t") or {}).get("icons") or []
        avghp = (state.monster_info.get(m.id, {}).get("typedata") or {}).get("avghp")
        per.append({"fg": v is not None,
                    "mdam": 0 if v is None else (v >> FG_MDAM_SHIFT) & 7,
                    "beh": 0 if v is None else (v >> FG_BEH_SHIFT) & 7,
                    "pois": 0 if v is None else (v >> FG_POISON_SHIFT) & 3,
                    "caught": bool(v and v & (FG_NET | FG_WEB)),
                    "st": sorted({ICONS[i] for i in icons if isinstance(i, int) and i in ICONS}),
                    "avghp": avghp})
    rays = []
    for dx, dy in DIRECTIONS:
        n = 0
        while n < RAY and _walkable(state, (px + dx * (n + 1), py + dy * (n + 1))):
            n += 1
        rays.append(n)
    near = [(px + dx, py + dy) for dx in range(-3, 4) for dy in range(-3, 4) if (dx, dy) != (0, 0)]
    open2 = sum(_walkable(state, p) for p in near if max(abs(p[0] - px), abs(p[1] - py)) <= 2)
    unseen3 = sum(1 for p in near if (state.cells.get(p) or {}).get("mf", MF_UNSEEN) in (MF_UNSEEN, MF_UNEXPLORED))
    wall = {d: not _walkable(state, (px + d[0], py + d[1])) for d in ((0, -1), (0, 1), (-1, 0), (1, 0))}
    corridor = (wall[(0, -1)] and wall[(0, 1)]) or (wall[(-1, 0)] and wall[(1, 0)])
    inv = state.player.get("inv") or {}
    wielded = inv.get(str(state.player.get("weapon_index", -1)))
    w = gear.weapon(wielded) if wielded else None
    return {"mons": per, "wpn": round(w[0], 2) if w else None, "wpn_held": wielded is not None,
            "map": {"open2": open2, "unseen3": unseen3, "corridor": bool(corridor), "rays": rays},
            "obsx": SIGHT_VERSION}


def merge_sight(obs: dict, extra: dict) -> dict:
    """`obs` with a `sight` result folded in (per monster into its "mons" entries, the rest at the top)."""
    out = {**obs, **{k: v for k, v in extra.items() if k != "mons"}}
    out["mons"] = [{**m, **x} for m, x in zip(obs["mons"], extra["mons"])]
    return out


def observe(state: GameState, hostiles: list[Monster], ctx: dict) -> dict:
    """The moment as a JSON dict. `ctx` is what the tiers object remembers (see policy.BrainTiers)."""
    p = state.player
    px, py = state.pos
    here = state.cells.get(state.pos, {}).get("mf")
    d_down = 0 if here == MF_STAIR_DOWN else path(state, MF_STAIR_DOWN)[1]
    d_up = 0 if here == MF_STAIR_UP else path(state, MF_STAIR_UP)[1]
    mons = sorted(hostiles, key=lambda m: state.distance(m.pos))
    better = gear.upgrades(state, ctx.get("worn") or {}, kit=bool(ctx.get("kit")))
    open_n = sum(1 for dx, dy in DIRECTIONS
                 if (c := state.cells.get((px + dx, py + dy))) and c.get("mf", 0) not in NOT_WALKABLE)
    obs = {
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
        "inv": {**{k: v for k, v in inventory(state).items() if k != "letters"},
                "wield": int(bool(better["wield"])), "wear": int(bool(better["wear"]))},
        "on_down": here == MF_STAIR_DOWN, "on_up": here == MF_STAIR_UP,
        "dist_down": d_down, "dist_up": d_up, "open_neighbors": open_n,
        "level_explored": bool(ctx.get("level_explored")),
        "level_steps": ctx.get("level_steps", 0), "level_turns": state.turn - ctx.get("level_turn", state.turn),
        "hp_delta": ctx.get("hp_delta", 0.0), "last_action": ctx.get("last_action"),
    }
    return merge_sight(obs, sight(state, mons[:MAX_MONS]))


def _cap(x: float, hi: float) -> float:
    return max(0.0, min(float(x), hi)) / hi


def table_stats(m: dict, hp: float, hp_max: float) -> tuple[list[float], dict | None]:
    """The "table" numbers for one monster (TABLE_MON of them), and its table entry."""
    k = monsters.lookup(m["name"])
    if k is None:
        return [0.0] * TABLE_MON, None
    per_turn = k["dmg"] * k["speed"] / 10                   # most it can deal in one of our turns
    row = [1.0, _cap(k["hd"], 30), _cap(k["hp"] / hp_max, 4), _cap(per_turn / max(hp, 1), 2),
           float(k["speed"] > 10), float(k["speed"] < 10)]
    row += [float(kind in k["kinds"]) for kind in monsters.KINDS]
    row.append(min(math.log1p(k["exp"]) / 10, 1.0))
    return row, k


def seen_stats(m: dict, k: dict | None, hp_max: float) -> list[float]:
    """The "seen" numbers for one monster (SEEN_MON of them); zeros when the step has no `sight` fields."""
    if not m.get("fg"):
        return [0.0] * SEEN_MON
    left = MDAM_LEFT.get(m.get("mdam", 0), 1.0)
    avg = m.get("avghp") or (k["hp"] if k else 0.0)
    st = set(m.get("st") or [])
    row = [1.0, left, _cap(avg * left / hp_max, 4)]
    row += [float(m.get("beh") == b) for b in BEHAVIOUR]
    row += [float(m.get("pois", 0) > 0), float(bool(m.get("caught"))), float("summoned" in st),
            float(bool(st & BUFFED)), float(bool(st & DEBUFFED))]
    return row


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
    table_rows, seen_rows = [], []
    for i, (m, d) in enumerate(zip(mons[:MAX_MONS], dists)):
        row = [_cap(d, 8), m["dx"] / 8, m["dy"] / 8, float(d <= 1), float(m["unique"])]
        row += [float(m["threat"] == t) for t in range(4)]
        bucket = zlib.crc32(m["name"].lower().encode()) % NAME_BUCKETS
        row += [float(b == bucket) for b in range(NAME_BUCKETS)]
        trow, k = table_stats(m, obs["hp"], hp_max)
        srow = seen_stats(m, k, hp_max)
        table_rows.append(trow)
        seen_rows.append(srow)
        m_arr[i] = row + trow + srow
        mask[i] = 1
    # "table" totals over the view. Columns of a table row: known, hd, hp, per-turn damage, fast, slow,
    # the kinds (ranged first), experience
    t = np.asarray(table_rows, dtype=np.float32).reshape(-1, TABLE_MON)
    s += [_cap(t[:, 2].sum() * 4, 8), _cap(t[:, 3].sum() * 2, 4), float(t[:, 3].max(initial=0)),
          float(t[:, 1].max(initial=0)), _cap(t[:, 4].sum(), 8), _cap(t[:, 6].sum(), 8),
          _cap(len(t) - t[:, 0].sum(), 8)]
    # "seen": whether the step has them at all, the weapon, the map around, then totals over the view
    # (estimated HP left, monsters asleep or unaware)
    have = obs.get("obsx") is not None
    mp = obs.get("map") or {}
    rays = mp.get("rays") or [0] * len(DIRECTIONS)
    sr = np.asarray(seen_rows, dtype=np.float32).reshape(-1, SEEN_MON)
    s += [float(not have),
          _cap(obs.get("wpn") or 0, 20), float(have and bool(obs.get("wpn_held")) and obs.get("wpn") is None),
          _cap(mp.get("open2", 0), 24), float(bool(mp.get("corridor"))),
          _cap(min(rays), RAY), _cap(sum(rays) / len(rays), RAY), _cap(max(rays), RAY),
          _cap(mp.get("unseen3", 0), 48),
          _cap(sr[:, 2].sum() * 4, 8), _cap(sr[:, 3].sum() + sr[:, 4].sum(), 8)]
    return np.asarray(s, dtype=np.float32), m_arr, mask


V4_MON = 5 + 4 + NAME_BUCKETS
TABLE_MON = 6 + len(monsters.KINDS) + 1
SEEN_MON = 3 + len(BEHAVIOUR) + 5
MON_DIM = V4_MON + TABLE_MON + SEEN_MON
V4_SELF = 37 + len(STATUSES) + 2 * N_ACTIONS
TABLE_SELF, SEEN_SELF = 7, 11
SELF_DIM = V4_SELF + TABLE_SELF + SEEN_SELF
# Where each group of inputs sits, as [start, end) columns: version 4's, the table's, then sight's.
# "name" is the name hash inside "v4". The offline comparison (docs/trained-brain.md) trains on subsets.
SELF_GROUPS = {"v4": (0, V4_SELF), "table": (V4_SELF, V4_SELF + TABLE_SELF),
               "seen": (V4_SELF + TABLE_SELF, SELF_DIM)}
MON_GROUPS = {"v4": (0, V4_MON), "name": (9, V4_MON), "table": (V4_MON, V4_MON + TABLE_MON),
              "seen": (V4_MON + TABLE_MON, MON_DIM)}
