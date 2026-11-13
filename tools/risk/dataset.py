"""The death-risk dataset: one row per logged moment of a game, label = died within N game turns.

    uv run python tools/risk/dataset.py build                 # -> runs/risk/rows.npz, runs/risk/games.json
    uv run python tools/risk/dataset.py build --limit 200     # a quick partial build

Two sources:

- **brain**: every `steps.jsonl` under the main checkout's `runs/brain/` (the trained brain, the rules of
  thumb, their forks). One row per choice, from the observation dict `features.observe` wrote.
- **qw**: the devteam's bot, from runs that kept a state log (`--state-log`): `train-base-r1` (training
  seeds 100000-100299), `qw-base-200` (held-out seeds 500000-500199) and the fork runs on the training
  seeds. One row per qw decision, from its `QWS` line (the state before it acts).

A fork (brain or qw) replays a game to one moment and plays on from there; only its rows from that
moment on are kept (the earlier ones are the original game's), and qw's are thinned to one in
QW_FORK_KEEP because there are 2.7M of them.

Labels are not stored: each row keeps its turn, the game's end turn and whether the game ended in a
death, and `label` makes the label for any horizon. A game that ended any other way (quit, timeout,
hang, stopped at a fork's horizon, Lua error loop, won, left) is censored at its last turn: a row is a
known 0 when the game went on at least N more turns, and unknown otherwise.

Features are what the logs really hold, mapped to one schema for both sources, plus each monster in
view looked up in docs/data/monsters-0.34.json (speed, damage, XP, danger tags) and a few things
computed from the game's own earlier rows (HP trend, how busy the last turns were). Nothing after the
moment is used. Fields one source lacks are NaN.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import zlib
from collections import deque
from multiprocessing import Pool
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools" / "qw"))

from ladder.brain.corpus import seed_of  # noqa: E402
from log import parse_state  # noqa: E402  (tools/qw/log.py)

HOLDOUT_SEED = 500_000          # seeds from here up are the held-out dungeons: test only
HORIZONS = (50, 200)
BRAIN_ROOT = REPO.parents[2] / "runs" / "brain" if (REPO.parents[2] / "runs" / "brain").exists() \
    else REPO / "runs" / "brain"
QW_ROOT = REPO / "runs" / "qw"
OUT = REPO / "runs" / "risk"
MONSTERS = REPO / "docs" / "data" / "monsters-0.34.json"

QW_BASE_RUNS = ("train-base-r1", "qw-base-200")
QW_FORK_RUNS = ("forks-r1", "forks-r1c", "forks-r2", "choke1", "choke2", "choke3")
QW_FORK_KEEP = 3                # keep one qw fork row in this many
NOT_DEATH = {None, "", "quitting", "winning", "leaving"}   # qw ktyp values that are not a death

PLAYER_SPEED = 10
NEAREST = 5                     # monsters used per moment: qw logs the 5 nearest, so both use 5
RUNE_BRANCHES = {"Spider", "Snake", "Shoals", "Swamp", "Vaults", "Slime"}
# webtiles' long place names -> qw's short ones
PLACE_SHORT = {"Dungeon": "D", "": "D", "Spider Nest": "Spider", "Snake Pit": "Snake", "Slime Pits": "Slime",
               "Orcish Mines": "Orc", "Elven Halls": "Elf", "Ice Cave": "IceCv", "Pandemonium": "Pan"}
# rough absolute depth of a branch's first floor minus one (where it hangs off, on average)
BRANCH_BASE = {"D": 0, "Temple": 6, "Lair": 9, "Orc": 10, "Spider": 12, "Snake": 12, "Shoals": 12,
               "Swamp": 12, "Vaults": 13, "Elf": 12, "Slime": 13, "Depths": 14, "Crypt": 15, "Tomb": 18,
               "Zot": 19, "Abyss": 10, "Sewer": 3, "Ossuary": 4, "Bailey": 8, "IceCv": 10, "Volcano": 10}
DEFAULT_BASE = 14

MON_TAGS = ("poison", "slows", "paralyses", "confuses", "blinks", "smites", "summons", "hastes", "unique",
            "drains", "corrodes", "trample", "reach", "mesmerises", "petrifies", "banishes")

FEATURES = [
    # the character
    "is_qw", "hp", "mhp", "hp_frac", "mhp_log", "poison_frac", "poison_survival_frac", "after_rage_frac",
    "xl", "ac", "ev", "sh", "str", "dex", "absdepth", "xl_minus_depth",
    "br_dungeon", "br_lair", "br_rune", "br_orc", "br_late", "br_abyss", "br_other",
    "st_berserk", "st_berserk_after", "st_slowed", "st_hasted", "st_confused", "st_poisoned", "st_corroded",
    "st_might", "st_held", "st_constricted", "st_teleporting", "st_paralysed", "st_weak", "st_drained",
    "heal_potions", "teleports", "has_unknown_potion", "has_unknown_scroll", "trog", "piety",
    "level_turns", "on_upstairs", "open_neighbors", "n_hostiles",
    # the monsters in view (nearest NEAREST), from the monster table
    "mon_n", "mon_unknown", "mon_exp_sum", "mon_exp_max", "mon_hd_sum", "mon_hd_max", "mon_hp_sum",
    "mon_dmg_sum", "mon_dmg_max", "mon_dmg_near", "mon_dmg_near_over_hp", "mon_hp_over_hp",
    "mon_adjacent", "mon_within2", "mon_nearest", "mon_fast", "mon_faster_eff",
    *[f"mon_{t.replace(' ', '_')}" for t in MON_TAGS], "mon_ranged_spells",
    # the game's own recent history (earlier rows only)
    "hist_dhp", "hist_min_hp_20", "hist_drop_10", "hist_dt", "hist_rows_20", "hist_since_full",
    # qw only
    "q_threat", "q_threat_rel", "q_ranged_threat", "q_threat_avail_rel", "q_scary", "q_immediate",
    "q_safe", "q_cloudy", "q_danger_los", "q_attack_damage", "q_flee_dist", "q_can_flee_up", "q_allies",
    "q_sk_fighting", "q_n_haste", "q_n_might", "q_can_berserk", "q_mon_sleeping", "q_mon_ranged",
    "q_mon_hasted", "q_mon_damage_level",
    # brain only
    "b_threat_max", "b_threat_sum", "b_dist_up", "b_dist_down", "b_explored",
]
F_INDEX = {f: i for i, f in enumerate(FEATURES)}
META = ["source", "game", "seed", "fork", "turn", "end_turn", "died", "xl", "deep", "hp_frac"]


# ---------------------------------------------------------------------------------------------------
# labels


def label(turns, end_turn: float, died: bool, horizon: int) -> np.ndarray:
    """1 = died within `horizon` game turns of the row, 0 = known alive `horizon` turns later, -1 = unknown.

    A game that ended in a death at `end_turn` labels every row: 1 if the death came within `horizon`
    turns, else 0. A game that ended any other way is censored there: the character was alive at
    `end_turn`, so a row at least `horizon` turns before it is a 0 and a later row is unknown.
    """
    left = end_turn - np.asarray(turns, dtype=np.float64)
    if died:
        return np.where(left <= horizon, 1, 0).astype(np.int8)
    return np.where(left >= horizon, 0, -1).astype(np.int8)


def labels(meta: dict, horizon: int) -> np.ndarray:
    """`label` over every row of a built dataset (vectorised)."""
    left = meta["end_turn"].astype(np.float64) - meta["turn"]
    died = meta["died"].astype(bool)
    return np.where(died, np.where(left <= horizon, 1, 0), np.where(left >= horizon, 0, -1)).astype(np.int8)


# ---------------------------------------------------------------------------------------------------
# monsters


class MonsterBook:
    """Name -> numbers from docs/data/monsters-0.34.json, with a few fallbacks for derived names."""

    DERIVED = ("zombie", "skeleton", "simulacrum")

    def __init__(self, path: Path = MONSTERS):
        data = json.loads(Path(path).read_text())
        self.by_name: dict[str, dict] = {}
        for m in data["monsters"]:
            dmg = sum(a.get("damage", 0) or 0 for a in m.get("attacks") or [])
            tags = set(m.get("tags") or [])
            spells = m.get("spells") or []
            self.by_name[m["name"].lower()] = {
                "hd": m.get("hd") or 0, "hp": m.get("hp") or 0.0, "speed": m.get("speed") or 10,
                "exp": m.get("exp") or 0, "dmg": dmg, "tags": tags,
                "ranged": bool(spells),
            }
        self.cache: dict[str, dict | None] = {}
        self.misses: dict[str, int] = {}

    def lookup(self, name: str) -> dict | None:
        key = (name or "").strip().lower()
        if key in self.cache:
            return self.cache[key]
        hit = self._find(key)
        self.cache[key] = hit
        if hit is None:
            self.misses[key] = self.misses.get(key, 0) + 1
        return hit

    def _find(self, key: str) -> dict | None:
        for k in (key, key.removeprefix("the "), key.removeprefix("a "), key.removeprefix("an ")):
            if k in self.by_name:
                return self.by_name[k]
        words = key.split()
        if words and words[0] == "dancing":
            return self.by_name.get("dancing weapon")
        if words and words[-1] == "beast" and len(words) > 1:
            return self.by_name.get("mutant beast")   # "larval weirdsting beast" and the like
        if words and words[0] == "spectral" and " ".join(words[1:]) in self.by_name:
            return self.by_name[" ".join(words[1:])]
        if words and words[-1] in self.DERIVED and " ".join(words[:-1]) in self.by_name:
            return self.by_name[" ".join(words[:-1])]
        # "Grum the Hunter"-style vault names and adjectives: try shorter tails, then heads
        for i in range(1, len(words)):
            if " ".join(words[i:]) in self.by_name:
                return self.by_name[" ".join(words[i:])]
        for i in range(len(words) - 1, 0, -1):
            if " ".join(words[:i]) in self.by_name:
                return self.by_name[" ".join(words[:i])]
        if key.endswith("s") and key[:-1] in self.by_name:
            return self.by_name[key[:-1]]
        return None


def monster_features(row: np.ndarray, mons: list[tuple[str, float]], book: MonsterBook, hp: float,
                     player_speed: float) -> None:
    """Fill the mon_* columns from [(name, distance)] (nearest first, at most NEAREST)."""
    mons = sorted(mons, key=lambda m: m[1])[:NEAREST]
    known = [(book.lookup(n), d) for n, d in mons]
    f = F_INDEX
    row[f["mon_n"]] = len(mons)
    row[f["mon_unknown"]] = sum(1 for k, _ in known if k is None)
    ks = [(k, d) for k, d in known if k is not None]
    rate = [k["dmg"] * k["speed"] / 10 for k, _ in ks]
    row[f["mon_exp_sum"]] = sum(k["exp"] for k, _ in ks)
    row[f["mon_exp_max"]] = max((k["exp"] for k, _ in ks), default=0)
    row[f["mon_hd_sum"]] = sum(k["hd"] for k, _ in ks)
    row[f["mon_hd_max"]] = max((k["hd"] for k, _ in ks), default=0)
    row[f["mon_hp_sum"]] = sum(k["hp"] for k, _ in ks)
    row[f["mon_dmg_sum"]] = sum(rate)
    row[f["mon_dmg_max"]] = max(rate, default=0)
    near = sum(r for r, (_, d) in zip(rate, ks) if d <= 2)
    row[f["mon_dmg_near"]] = near
    row[f["mon_dmg_near_over_hp"]] = near / max(hp, 1)
    row[f["mon_hp_over_hp"]] = row[f["mon_hp_sum"]] / max(hp, 1)
    row[f["mon_adjacent"]] = sum(1 for _, d in mons if d <= 1)
    row[f["mon_within2"]] = sum(1 for _, d in mons if d <= 2)
    row[f["mon_nearest"]] = min((d for _, d in mons), default=9)
    row[f["mon_fast"]] = sum(1 for k, _ in ks if k["speed"] > PLAYER_SPEED)
    row[f["mon_faster_eff"]] = sum(1 for k, _ in ks if k["speed"] > player_speed)
    for t in MON_TAGS:
        row[f[f"mon_{t.replace(' ', '_')}"]] = sum(1 for k, _ in ks if t in k["tags"])
    row[f["mon_ranged_spells"]] = sum(1 for k, _ in ks if k["ranged"])


# ---------------------------------------------------------------------------------------------------
# common character fields


def place_features(row: np.ndarray, branch: str, depth: int) -> tuple[float, bool]:
    f = F_INDEX
    br = PLACE_SHORT.get(branch, branch)
    absdepth = BRANCH_BASE.get(br, DEFAULT_BASE) + (depth or 0)
    row[f["absdepth"]] = absdepth
    row[f["br_dungeon"]] = br == "D"
    row[f["br_lair"]] = br == "Lair"
    row[f["br_rune"]] = br in RUNE_BRANCHES
    row[f["br_orc"]] = br in ("Orc", "Elf")
    row[f["br_late"]] = br in ("Depths", "Crypt", "Tomb", "Zot")
    row[f["br_abyss"]] = br == "Abyss"
    row[f["br_other"]] = not any(row[f[k]] for k in ("br_dungeon", "br_lair", "br_rune", "br_orc", "br_late",
                                                     "br_abyss"))
    return absdepth, br in RUNE_BRANCHES


def character(row: np.ndarray, hp, mhp, ps, berserk: bool) -> None:
    f = F_INDEX
    hp, mhp = float(hp or 0), float(max(mhp or 1, 1))
    ps = hp if ps is None or ps == "" else float(ps)
    row[f["hp"]], row[f["mhp"]] = hp, mhp
    row[f["hp_frac"]] = hp / mhp
    row[f["mhp_log"]] = math.log1p(mhp)
    base = mhp * 2 / 3 if berserk else mhp          # a rage shows max HP at 3/2
    row[f["poison_frac"]] = max(hp - ps, 0) / base
    row[f["poison_survival_frac"]] = ps / base
    # HP once the rage ends: HP is scaled by 2/3 and the poison is not (docs/knowledge-bots.md)
    row[f["after_rage_frac"]] = (ps - hp / 3 if berserk else ps) / base


class History:
    """Past-only features from the game's own earlier rows."""

    def __init__(self):
        self.rows: deque = deque()     # (turn, hp_frac)
        self.last_full = None

    def fill(self, row: np.ndarray, turn: float, hp_frac: float) -> None:
        f = F_INDEX
        while self.rows and self.rows[0][0] < turn - 20:
            self.rows.popleft()
        prev = self.rows[-1] if self.rows else None
        row[f["hist_dhp"]] = hp_frac - prev[1] if prev else 0.0
        row[f["hist_dt"]] = min(turn - prev[0], 1000) if prev else 1000
        row[f["hist_min_hp_20"]] = min([h for _, h in self.rows] + [hp_frac])
        recent = [h for t, h in self.rows if t >= turn - 10]
        row[f["hist_drop_10"]] = max(max(recent, default=hp_frac) - hp_frac, 0.0)
        row[f["hist_rows_20"]] = len(self.rows)
        if hp_frac >= 0.999:
            self.last_full = turn
        row[f["hist_since_full"]] = min(turn - self.last_full, 1000) if self.last_full is not None else 1000
        self.rows.append((turn, hp_frac))


def _new_row() -> np.ndarray:
    return np.full(len(FEATURES), np.nan, dtype=np.float32)


def _deep(xl, rune: bool) -> bool:
    return (xl or 0) >= 12 or rune


# ---------------------------------------------------------------------------------------------------
# brain


def _status(status: list[str], name: str) -> bool:
    return any(s == name or s.startswith(name + " ") for s in status)


def brain_row(o: dict, book: MonsterBook, hist: History) -> tuple[np.ndarray, bool]:
    f = F_INDEX
    row = _new_row()
    st = o.get("status") or []
    berserk = _status(st, "Berserk")
    row[f["is_qw"]] = 0
    character(row, o["hp"], o["hp_max"], o.get("poison_survival"), berserk)
    for k in ("xl", "ac", "ev", "sh", "str", "dex"):
        row[f[k]] = o.get(k, 0) or 0
    absdepth, rune = place_features(row, o.get("place", ""), o.get("depth", 0))
    row[f["xl_minus_depth"]] = (o.get("xl") or 1) - absdepth
    slowed = _status(st, "Slow") or any(s.startswith("Fast+Slow") for s in st)
    hasted = _status(st, "Fast")
    row[f["st_berserk"]] = berserk
    row[f["st_berserk_after"]] = _status(st, "-Berserk")
    row[f["st_slowed"]] = slowed
    row[f["st_hasted"]] = hasted
    row[f["st_confused"]] = _status(st, "Conf")
    row[f["st_poisoned"]] = _status(st, "Pois") or o["hp"] > (o.get("poison_survival") or o["hp"])
    row[f["st_corroded"]] = any(s.startswith("Corr") for s in st)
    row[f["st_might"]] = _status(st, "Might")
    row[f["st_held"]] = _status(st, "Held")
    row[f["st_constricted"]] = _status(st, "Constr")
    row[f["st_teleporting"]] = _status(st, "Tele")
    row[f["st_paralysed"]] = _status(st, "Para")
    row[f["st_weak"]] = _status(st, "Weak")
    row[f["st_drained"]] = _status(st, "Drain")
    inv = o.get("inv") or {}
    row[f["heal_potions"]] = inv.get("heal", 0)
    row[f["teleports"]] = inv.get("teleport", 0)
    row[f["has_unknown_potion"]] = (inv.get("unknown_potions", 0) or 0) > 0
    row[f["has_unknown_scroll"]] = (inv.get("unknown_scrolls", 0) or 0) > 0
    row[f["trog"]] = o.get("god") == "Trog"
    row[f["piety"]] = o.get("piety", 0) or 0
    row[f["level_turns"]] = o.get("level_turns", 0) or 0
    row[f["on_upstairs"]] = bool(o.get("on_up"))
    row[f["open_neighbors"]] = o.get("open_neighbors", 0) or 0
    row[f["n_hostiles"]] = o.get("n_hostiles", 0) or 0
    mons = o.get("mons") or []
    speed = PLAYER_SPEED * (1.5 if (hasted or berserk) else 1) * (2 / 3 if slowed else 1)
    monster_features(row, [(m["name"], max(abs(m["dx"]), abs(m["dy"]))) for m in mons], book, o["hp"], speed)
    row[f["b_threat_max"]] = max((m.get("threat", 0) for m in mons), default=0)
    row[f["b_threat_sum"]] = sum(m.get("threat", 0) for m in mons)
    row[f["b_dist_up"]] = o.get("dist_up", -1)
    row[f["b_dist_down"]] = o.get("dist_down", -1)
    row[f["b_explored"]] = bool(o.get("level_explored"))
    hist.fill(row, o["turn"], row[f["hp_frac"]])
    return row, rune


def read_brain_file(path: str) -> list[dict]:
    """Every game in one steps.jsonl, as {rows, meta...}."""
    book = MonsterBook()
    by_game: dict = {}
    with open(path) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue                       # the last line of a game that was killed
            g = by_game.setdefault(r.get("game"), {"steps": [], "end": None})
            if r.get("type") == "end":
                g["end"] = r
            else:
                g["steps"].append(r)
    out = []
    for key, g in by_game.items():
        steps, end = g["steps"], g["end"] or {}
        if not steps or any(s.get("source") == "human" for s in steps):
            continue                           # a person's game: no seed, often a take-over
        if "replay diverged" in str(end.get("escalation") or ""):
            continue                           # a fork that left the recorded game
        fork = any(s.get("source") in ("replay", "fork") for s in steps)
        died = bool(end.get("died"))
        last = steps[-1]["obs"]["turn"]
        end_turn = end.get("turn", last) if end else last
        hist = History()
        rows, turns, xls, deep = [], [], [], []
        for s in steps:
            o = s["obs"]
            row, rune = brain_row(o, book, hist)
            if s.get("source") == "replay":
                continue                       # the original game's rows, kept from there
            rows.append(row)
            turns.append(o["turn"])
            xls.append(o.get("xl", 1))
            deep.append(_deep(o.get("xl"), rune))
        if not rows:
            continue
        misses, book.misses = book.misses, {}  # counted once, on the file's first game
        out.append({"source": "brain", "run": str(Path(path).parent), "id": f"{Path(path).parent}#{key}",
                    "seed": seed_of(key), "fork": fork, "died": died, "end_turn": end_turn,
                    "ended_by": end.get("ended_by") or ("no end line" if not end else "?"),
                    "max_depth": end.get("max_depth"), "steps": len(steps), "rows": np.stack(rows),
                    "turn": np.asarray(turns), "xl": np.asarray(xls), "deep": np.asarray(deep),
                    "misses": misses})
    return out


# ---------------------------------------------------------------------------------------------------
# qw


def qw_row(s: dict, book: MonsterBook, hist: History) -> tuple[np.ndarray, bool]:
    f = F_INDEX
    row = _new_row()
    num = _num
    berserk = num(s.get("berserk")) > 0
    row[f["is_qw"]] = 1
    character(row, s.get("hp"), s.get("mhp"), s.get("poison_survival"), berserk)
    for k in ("xl", "ac", "ev", "sh", "str", "dex"):
        row[f[k]] = num(s.get(k))
    absdepth, rune = place_features(row, s.get("branch") or "D", int(num(s.get("depth"))))
    row[f["xl_minus_depth"]] = num(s.get("xl")) - absdepth
    slowed, hasted = num(s.get("slowed")) > 0, num(s.get("hasted")) > 0
    row[f["st_berserk"]] = berserk
    row[f["st_berserk_after"]] = num(s.get("berserk_cooldown")) > 0 or num(s.get("exhausted")) > 0
    row[f["st_slowed"]] = slowed
    row[f["st_hasted"]] = hasted
    row[f["st_confused"]] = num(s.get("confused")) > 0
    row[f["st_poisoned"]] = num(s.get("poisoned")) > 0
    row[f["st_corroded"]] = num(s.get("corrosion")) > 0
    row[f["st_might"]] = num(s.get("mighty")) > 0
    row[f["st_held"]] = num(s.get("caught")) > 0
    row[f["st_constricted"]] = num(s.get("constricted")) > 0
    row[f["st_teleporting"]] = num(s.get("teleporting")) > 0
    row[f["heal_potions"]] = num(s.get("n_heal_wounds")) + num(s.get("n_curing"))
    row[f["teleports"]] = num(s.get("n_teleport"))
    row[f["has_unknown_potion"]] = num(s.get("unid_potion_stacks")) > 0
    row[f["has_unknown_scroll"]] = num(s.get("unid_scroll_stacks")) > 0
    row[f["trog"]] = s.get("god") == "Trog"
    row[f["piety"]] = num(s.get("piety_rank"))
    row[f["level_turns"]] = num(s.get("turns_on_level"))
    row[f["on_upstairs"]] = num(s.get("on_upstairs"))
    row[f["open_neighbors"]] = num(s.get("adjacent_floor"))
    row[f["n_hostiles"]] = num(s.get("enemy_count"))
    en = s.get("enemies") or []
    speed = PLAYER_SPEED * (1.5 if (hasted or berserk) else 1) * (2 / 3 if slowed else 1)
    monster_features(row, [(e["name"], num(e.get("dist"))) for e in en], book, num(s.get("hp")), speed)
    high = max(num(s.get("high_threat_level")), 1.0)
    row[f["q_threat"]] = num(s.get("threat"))
    row[f["q_threat_rel"]] = num(s.get("threat")) / high
    row[f["q_ranged_threat"]] = num(s.get("ranged_threat"))
    row[f["q_threat_avail_rel"]] = num(s.get("threat_avail")) / high
    row[f["q_scary"]] = num(s.get("scary_enemy"))
    row[f["q_immediate"]] = num(s.get("immediate_danger"))
    row[f["q_safe"]] = num(s.get("position_is_safe"))
    row[f["q_cloudy"]] = num(s.get("position_is_cloudy"))
    row[f["q_danger_los"]] = num(s.get("danger_in_los"))
    row[f["q_attack_damage"]] = num(s.get("attack_damage"))
    fd = num(s.get("flee_dist"), -1)
    row[f["q_flee_dist"]] = fd if fd >= 0 else 99
    row[f["q_can_flee_up"]] = num(s.get("can_flee_upstairs"))
    row[f["q_allies"]] = num(s.get("allies_3"))
    row[f["q_sk_fighting"]] = num(s.get("sk_fighting"))
    row[f["q_n_haste"]] = num(s.get("n_haste"))
    row[f["q_n_might"]] = num(s.get("n_might"))
    row[f["q_can_berserk"]] = num(s.get("can_berserk"))
    row[f["q_mon_sleeping"]] = sum(1 for e in en if num(e.get("sleeping")) > 0)
    row[f["q_mon_ranged"]] = sum(1 for e in en if num(e.get("ranged")) > 0)
    row[f["q_mon_hasted"]] = sum(1 for e in en if num(e.get("hasted")) > 0)
    row[f["q_mon_damage_level"]] = max((num(e.get("damage_level")) for e in en), default=0)
    hist.fill(row, num(s.get("turn")), row[f["hp_frac"]])
    return row, rune


def _num(v, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _qw_states(path: Path, start: int):
    """(decision, state) for each QWS line at or after decision `start` (a cheap skip before it)."""
    name = path / "stderr.log.gz" if (path / "stderr.log.gz").exists() else path / "stderr.log"
    opener = gzip.open if name.suffix == ".gz" else open
    with opener(name, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.startswith("QWS\t"):
                continue
            head, idx, rest = line.split("\t", 2)
            idx = int(idx)
            if idx < start:
                continue
            yield idx, parse_state(rest.rstrip("\n").split("\t"))


def qw_died(game: dict) -> bool:
    """A qw game (an entry of results.json) that ended in a death: finished, killed by something.

    Quitting (qw idles, then quits), winning, leaving, a timeout, a stall, a Lua error loop and a fork
    stopped at its horizon are not deaths.
    """
    return game.get("status") == "done" and game.get("ktyp") not in NOT_DEATH


def read_qw_game(args: tuple) -> list[dict]:
    run, game = args
    book = MonsterBook()
    path = QW_ROOT / run / "games" / game["tag"]
    fork_at = None
    if game.get("overrides"):
        if game.get("prefix_match") is False:
            return []                          # the replay left the base game: not that game
        fork_at = min(int(k) for k in game["overrides"])
    ktyp = game.get("ktyp")
    died = qw_died(game)
    hist = History()
    rows, turns, xls, deep = [], [], [], []
    keep_salt = zlib.crc32(game["tag"].encode())
    try:
        for idx, s in _qw_states(path, 0 if fork_at is None else max(fork_at - 60, 0)):
            if not s:
                continue
            row, rune = qw_row(s, book, hist)
            if fork_at is not None and (idx < fork_at or (idx + keep_salt) % QW_FORK_KEEP):
                continue
            rows.append(row)
            turns.append(_num(s.get("turn")))
            xls.append(_num(s.get("xl")))
            deep.append(_deep(_num(s.get("xl")), rune))
    except (OSError, EOFError, ValueError):
        pass                                   # a truncated log: keep what was read, censor below
    if not rows:
        return []
    last = float(max(turns))
    end_turn = float(game.get("end_turn") or game.get("turns") or last) if died else last
    if not died and game.get("status") == "done" and game.get("end_turn"):
        end_turn = float(game["end_turn"])    # quit or won: alive until the logfile's last turn
    return [{"source": "qw", "run": run, "id": f"qw/{run}/{game['tag']}", "seed": int(game["seed"]),
             "fork": fork_at is not None, "died": died, "end_turn": end_turn,
             "ended_by": f"{game.get('status')}:{ktyp}", "max_depth": game.get("absdepth"),
             "steps": len(rows), "rows": np.stack(rows), "turn": np.asarray(turns), "xl": np.asarray(xls),
             "deep": np.asarray(deep), "misses": book.misses}]


# ---------------------------------------------------------------------------------------------------
# build


def _dedupe_key(g: dict) -> tuple | None:
    """Two brain games on the same dungeon that went exactly the same way."""
    if g["source"] != "brain" or g["fork"]:
        return None
    return (g["seed"], g["end_turn"], g["died"], g["steps"], g["max_depth"], int(g["rows"][-1, F_INDEX["hp"]]))


def jobs(brain_root: Path, qw_root: Path, limit: int | None):
    brain = sorted(str(p) for p in brain_root.rglob("steps.jsonl"))
    qw = []
    for run in QW_BASE_RUNS + QW_FORK_RUNS:
        res = json.loads((qw_root / run / "results.json").read_text())
        qw += [(run, g) for g in res["games"] if (qw_root / run / "games" / g["tag"]).exists()]
    if limit:
        brain, qw = brain[:limit], qw[:limit]
    return brain, qw


def build(brain_root: Path, qw_root: Path, out: Path, workers: int, limit: int | None = None) -> dict:
    brain, qw = jobs(brain_root, qw_root, limit)
    games: list[dict] = []
    with Pool(workers) as pool:
        for gs in pool.imap_unordered(read_brain_file, brain, chunksize=8):
            games += gs
        for gs in pool.imap_unordered(read_qw_game, qw, chunksize=4):
            games += gs
    games.sort(key=lambda g: g["id"])
    seen, kept, dupes = set(), [], 0
    for g in games:
        k = _dedupe_key(g)
        if k is not None and k in seen:
            dupes += 1
            continue
        seen.add(k)
        kept.append(g)
    misses: dict[str, int] = {}
    for g in kept:
        for k, v in g["misses"].items():
            misses[k] = misses.get(k, 0) + v
    X = np.concatenate([g["rows"] for g in kept])
    n = [len(g["rows"]) for g in kept]
    rep = lambda v: np.repeat(np.asarray(v), n)  # noqa: E731
    meta = {
        "source": rep([g["source"] == "qw" for g in kept]).astype(np.int8),
        "game": rep(np.arange(len(kept))).astype(np.int32),
        "seed": rep([g["seed"] for g in kept]).astype(np.int64),
        "fork": rep([g["fork"] for g in kept]).astype(bool),
        "turn": np.concatenate([g["turn"] for g in kept]).astype(np.float64),
        "end_turn": rep([g["end_turn"] for g in kept]).astype(np.float64),
        "died": rep([g["died"] for g in kept]).astype(bool),
        "xl": np.concatenate([g["xl"] for g in kept]).astype(np.float32),
        "deep": np.concatenate([g["deep"] for g in kept]).astype(bool),
    }
    meta["hp_frac"] = X[:, F_INDEX["hp_frac"]].copy()
    out.mkdir(parents=True, exist_ok=True)
    np.savez(out / "rows.npz", X=X, features=np.array(FEATURES), **meta)
    table = [{k: g[k] for k in ("id", "source", "run", "seed", "fork", "died", "end_turn", "ended_by", "max_depth",
                               "steps")} | {"rows": len(g["rows"]), "max_xl": float(g["xl"].max()),
                                            "deep_rows": int(g["deep"].sum())} for g in kept]
    info = {"games": len(kept), "rows": int(len(X)), "duplicate_brain_games_dropped": dupes,
            "monster_name_misses": dict(sorted(misses.items(), key=lambda kv: -kv[1])[:40]),
            "monster_lookups_missed": int(sum(misses.values()))}
    (out / "games.json").write_text(json.dumps({"info": info, "games": table}, indent=0))
    return info


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--brain-root", type=Path, default=BRAIN_ROOT)
    b.add_argument("--qw-root", type=Path, default=QW_ROOT)
    b.add_argument("--out", type=Path, default=OUT)
    b.add_argument("--workers", type=int, default=14)
    b.add_argument("--limit", type=int, default=None, help="only this many brain files and qw games")
    args = ap.parse_args()
    info = build(args.brain_root, args.qw_root, args.out, args.workers, args.limit)
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
