"""Counterfactual forks by replay: what would the other actions have led to, from the same moment?

DCSS can't be cloned mid-game, but a seeded game is deterministic: the same seed and the same choices
give the same game, message for message. So a recorded game can be replayed to any of its choices,
a different action taken there, and the game played on with the rules of thumb (or a model). The
fork's step log is an ordinary one, whose replayed steps are marked `replay` (the corpus skips them)
and whose changed step is marked `fork`. Together with the original game that gives several actions'
outcomes from one identical state, which is the comparison the network has to learn and the thing
s1-battle got from `World.clone`.

A fork costs a replay of everything before it, so points are chosen where a choice matters most:
mostly the last choices before a death, some anywhere there was more than one thing to do.

`kind="stairs"` picks a different kind of moment: nothing in view, both `explore` and `descend`
possible, and the rules of thumb choosing one of them. Each is forked twice, once each way, both
played on by the same policy, so the pair compares going down now with exploring on from the same state.
The rows otherwise seldom compare those two. A `descend` is one step toward the stairs, after which the
rules would turn back to exploring, so these forks commit (`BrainTiers.commit`): on that level the
forked action replaces the other one wherever the rules would choose it.
"""

from __future__ import annotations

import random

from .corpus import HOLDOUT_SEED, read_games

LATE_WINDOW = 40          # choices before the end of a game that count as "late"
KINDS = ("any", "stairs")
STAIRS = ("explore", "descend")


def _replayable(g: dict) -> bool:
    first = g["steps"][0]
    # only whole seeded self-play games, from their first choice, can be replayed
    if not isinstance(first["game"], int) or first.get("step") != 1 or g.get("skip"):
        return False
    if first["game"] >= HOLDOUT_SEED:      # evaluation dungeons are never forked (read_games drops them too)
        return False
    return not any(s.get("source") in ("human", "replay", "fork", "commit") for s in g["steps"])


def _stairs_moment(s: dict) -> bool:
    return s.get("baseline") in STAIRS and all(a in s["avail"] for a in STAIRS) and not s["obs"].get("n_hostiles")


def plan(roots: list, points: int, *, alternatives: int = 3, horizon: int = 0, late_share: float = 0.7,
         seed: int = 0, kind: str = "any") -> list[dict]:
    """Jobs for selfplay.run: up to `points` moments, each forked once per alternative action.

    `kind="stairs"`: up to `points` explore-or-descend moments, at most one per visit to a level, each
    forked both ways with `commit` (`alternatives` and `late_share` don't apply).
    """
    if kind not in KINDS:
        raise ValueError(f"no fork kind {kind!r} (have: {', '.join(KINDS)})")
    rng = random.Random(seed)
    games = [g for g in read_games(roots) if _replayable(g)]
    if kind == "stairs":
        return _plan_stairs(games, points, horizon, rng)
    candidates = []
    for g in games:
        n = len(g["steps"])
        for i, s in enumerate(g["steps"]):
            if len(s["avail"]) > 1:
                candidates.append((g, i, i >= n - LATE_WINDOW and bool((g["end"] or {}).get("died"))))
    late = [c for c in candidates if c[2]]
    rest = [c for c in candidates if not c[2]]
    rng.shuffle(late)
    rng.shuffle(rest)
    n_late = min(len(late), round(points * late_share))
    jobs = []
    for g, i, _ in late[:n_late] + rest[:points - n_late]:
        step = g["steps"][i]
        others = [a for a in step["avail"] if a != step["action"]]
        rng.shuffle(others)
        prefix = [s["action"] for s in g["steps"][:i]]
        for alt in others[:alternatives]:
            jobs.append({"seed": step["game"], "id": f"{step['game']}-{i + 1}-{alt}", "script": prefix + [alt],
                         "horizon": horizon})
    return jobs


def _plan_stairs(games: list[dict], points: int, horizon: int, rng: random.Random) -> list[dict]:
    visits: dict = {}
    for g in games:
        for i, s in enumerate(g["steps"]):
            if _stairs_moment(s):
                o = s["obs"]
                visits.setdefault((g["id"], o["place"], o["depth"]), []).append((g, i))
    keys = sorted(visits)
    rng.shuffle(keys)
    jobs = []
    for key in keys[:points]:
        g, i = rng.choice(visits[key])
        step = g["steps"][i]
        prefix = [s["action"] for s in g["steps"][:i]]
        for alt in STAIRS:
            jobs.append({"seed": step["game"], "id": f"{step['game']}-{i + 1}-{alt}", "script": prefix + [alt],
                         "horizon": horizon, "commit": True})
    return jobs
