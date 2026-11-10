"""Step logs in, training rows out.

Every `steps.jsonl` under the given roots is a set of games (selfplay.py writes them for the brain's
games, humanplay.py for a person's). For each step the label is what happened afterwards in that same
game, as six numbers (features.COMPONENTS):

    died_soon   1 if the character died within SOON_TURNS game turns
    hp_lost     the deepest HP drop within SOON_TURNS, as a fraction of max HP (all of it on death)
    xp_soon     experience levels gained within XP_TURNS (fractions from the progress bar)
    depth_go    new depths reached later on *and survived for SETTLE_TURNS*, each discounted by
                exp(-turns / TAU_GO) from the step to the turn the depth was settled
    xp_go       experience gained later on, discounted the same way
    died_go     exp(-turns until death / TAU_DEATH), 0 if the game didn't end in death
    depth_end   how many depths deeper than now this game ever got, undiscounted: the number the
                evaluation counts. The discounted ones all prefer sooner to later, which is a preference
                for the stairs over exploring first; this one has none.

DCSS can't be forked the way s1-battle's simulator can, so a row only knows the outcome of the action
that was taken. Random exploration during self-play (--epsilon) is what lets the network compare actions.

A game that stopped without a death (limits, a hang, nothing possible) is cut off there: its later
rewards count as zero, which undervalues its last moves a little.
"""

from __future__ import annotations

import json
import math
import zlib
from pathlib import Path

import numpy as np

from .features import ACTIONS, MAX_MONS, MON_DIM, N_COMPONENTS, SELF_DIM, encode, progress_depth
from .net import contract
from .policy import REPLAY_DIVERGED

SOON_TURNS, XP_TURNS, TAU_GO, TAU_DEATH = 30, 100, 1500.0, 400.0
# A new depth counts once the character has lasted this many game turns after first reaching it.
# Paying on arrival taught the first models to dive: the stairs earned the reward, whoever died below.
SETTLE_TURNS = 200
DANGER_DROP = 0.25
HOLDOUT_SEED = 500_000    # seeds from here up are evaluation's (cli.EVAL_SEED)
VAL_FOLD = 5              # one game in five is held out, by a hash of where it came from


def seed_of(game) -> int:
    """The dungeon seed behind a game id: the id itself, or the front of a fork's "<seed>-<step>-<action>"."""
    head = str(game).split("-")[0]
    return int(head) if head.isdigit() else -1


def read_games(roots: list[str | Path]) -> list[dict]:
    """[{id, steps, end}] for every game in every steps.jsonl under `roots`."""
    games = []
    # ids are relative to the root, so the held-out games stay the same wherever the corpus lives
    files = {f.resolve(): f.parent.relative_to(root) for root in roots for f in Path(root).rglob("steps.jsonl")}
    for f, rel in sorted(files.items()):
        by_game: dict = {}
        for line in f.read_text().splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue                       # the last line of a game that was killed
            g = by_game.setdefault(r.get("game"), {"id": f"{rel}#{r.get('game')}", "steps": [], "end": None})
            if r.get("type") == "end":
                g["end"] = r
            else:
                g["steps"].append(r)
        for key, g in by_game.items():
            if seed_of(key) >= HOLDOUT_SEED:
                continue                       # evaluation dungeons are never trained on
            if (g["end"] or {}).get("escalation", "") and REPLAY_DIVERGED in g["end"]["escalation"]:
                continue                       # a fork whose replay left the recorded game: not that game
            # a fork's replayed steps are the original game's, already in the corpus from there
            g["skip"] = sum(1 for s in g["steps"] if s.get("source") == "replay")
            if len(g["steps"]) > g["skip"]:
                games.append(g)
    return games


def _point(o: dict) -> tuple[int, float, float, int]:
    return (o["turn"], o["hp"] / max(o["hp_max"], 1), o["xl"] + o.get("progress", 0) / 100,
            progress_depth(o["place"], o["depth"]))


def settled_depth(turn: np.ndarray, depth: np.ndarray) -> np.ndarray:
    """At each point, the deepest depth first reached at least SETTLE_TURNS before it."""
    reached = np.maximum.accumulate(depth)
    out = np.full(len(turn), reached[0])
    j = 0
    for i in range(len(turn)):
        while j < i and turn[j + 1] + SETTLE_TURNS <= turn[i]:
            j += 1
        if turn[j] + SETTLE_TURNS <= turn[i]:
            out[i] = reached[j]
    return np.maximum.accumulate(out)


def label(game: dict) -> np.ndarray:
    """Outcome components for each step of one game: [steps, N_COMPONENTS]."""
    pts = [_point(s["obs"]) for s in game["steps"]]
    end = game["end"] or {}
    died = bool(end.get("died"))
    if end.get("turn") is not None and "hp" in end:
        pts.append(_point(end))
    elif died:
        pts.append((end.get("turn", pts[-1][0]), 0.0, pts[-1][2], pts[-1][3]))
    n = len(game["steps"])
    turn = np.array([p[0] for p in pts], dtype=np.float64)
    hp = np.array([p[1] for p in pts])
    xp = np.array([p[2] for p in pts])
    best = settled_depth(turn, np.array([p[3] for p in pts], dtype=np.float64))
    if died:
        hp[-1] = 0.0
    out = np.zeros((n, N_COMPONENTS), dtype=np.float32)
    reached = np.maximum.accumulate(np.array([p[3] for p in pts], dtype=np.float64))
    out[:, 6] = reached[-1] - reached[:n]
    # discounted sums, from the back: G_i = d_i * (r_{i+1} + G_{i+1})
    g_depth = g_xp = 0.0
    for i in range(len(pts) - 2, -1, -1):
        d = math.exp(-(turn[i + 1] - turn[i]) / TAU_GO)
        g_depth = d * (best[i + 1] - best[i] + g_depth)
        g_xp = d * (max(xp[i + 1] - xp[i], 0.0) + g_xp)
        if i < n:
            out[i, 3], out[i, 4] = g_depth, g_xp
    for i in range(n):
        j = i
        low, top = hp[i], xp[i]
        while j + 1 < len(pts) and turn[j + 1] - turn[i] <= XP_TURNS:
            j += 1
            if turn[j] - turn[i] <= SOON_TURNS:
                low = min(low, hp[j])
            top = max(top, xp[j])
        to_death = turn[-1] - turn[i]
        soon = died and to_death <= SOON_TURNS
        out[i, 0] = float(soon)
        out[i, 1] = hp[i] if soon else max(hp[i] - low, 0.0)
        out[i, 2] = top - xp[i]
        out[i, 5] = math.exp(-to_death / TAU_DEATH) if died else 0.0
    return out


def build(roots: list[str | Path], out: str | Path) -> dict:
    """Encode and label every game under `roots` into `out` (.npz) and `out`.meta.json."""
    games = read_games(roots)
    cols: dict[str, list] = {k: [] for k in ("self", "mons", "mask", "avail", "action", "base", "q", "human", "fork", "group", "val")}
    sources: dict[str, int] = {}
    for g in games:
        q = label(g)
        # held out by dungeon where there is one, so a game and its forks land on the same side
        seed = seed_of(g["steps"][0].get("game"))
        val = zlib.crc32((str(seed) if seed >= 0 else g["id"]).encode()) % VAL_FOLD == 0
        for step, row in list(zip(g["steps"], q))[g.get("skip", 0):]:
            if step["action"] not in ACTIONS:
                continue
            s, m, mask = encode(step["obs"], step["avail"])
            cols["self"].append(s)
            cols["mons"].append(m)
            cols["mask"].append(mask)
            cols["avail"].append([float(a in step["avail"]) for a in ACTIONS])
            cols["action"].append(ACTIONS.index(step["action"]))
            cols["base"].append(ACTIONS.index(step["baseline"]) if step.get("baseline") in ACTIONS else -1)
            cols["q"].append(row)
            cols["human"].append(float(step.get("source") == "human"))
            cols["fork"].append(float(step.get("source") == "fork"))
            # rows with the same group are the same moment: a recorded choice and the forks tried from it
            cols["group"].append(zlib.crc32(f"{seed}:{step.get('step')}".encode()) if seed >= 0 else -1)
            cols["val"].append(val)
            sources[step.get("source", "?")] = sources.get(step.get("source", "?"), 0) + 1
    n = len(cols["action"])
    arrays = {
        "self": np.asarray(cols["self"], dtype=np.float32).reshape(n, SELF_DIM),
        "mons": np.asarray(cols["mons"], dtype=np.float32).reshape(n, MAX_MONS, MON_DIM),
        "mask": np.asarray(cols["mask"], dtype=np.float32).reshape(n, MAX_MONS),
        "avail": np.asarray(cols["avail"], dtype=np.float32).reshape(n, len(ACTIONS)),
        "action": np.asarray(cols["action"], dtype=np.int64),
        "base": np.asarray(cols["base"], dtype=np.int64),
        "q": np.asarray(cols["q"], dtype=np.float32).reshape(n, N_COMPONENTS),
        "human": np.asarray(cols["human"], dtype=np.float32),
        "fork": np.asarray(cols["fork"], dtype=np.float32),
        "group": np.asarray(cols["group"], dtype=np.int64),
        "val": np.asarray(cols["val"], dtype=bool),
    }
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **arrays)
    ends = [g["end"] or {} for g in games]
    meta = {**contract(), "rows": n, "val_rows": int(arrays["val"].sum()), "games": len(games),
            "deaths": sum(bool(e.get("died")) for e in ends), "by_source": sources,
            "by_action": {a: int((arrays["action"] == i).sum()) for i, a in enumerate(ACTIONS)},
            "roots": [str(r) for r in roots],
            "labels": {"soon_turns": SOON_TURNS, "xp_turns": XP_TURNS, "tau_go": TAU_GO, "tau_death": TAU_DEATH,
                       "settle_turns": SETTLE_TURNS,
                       "danger_drop": DANGER_DROP}}
    Path(f"{out}.meta.json").write_text(json.dumps(meta, indent=1))
    return meta
