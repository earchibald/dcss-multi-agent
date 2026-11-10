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
"""

from __future__ import annotations

import random

from .corpus import read_games

LATE_WINDOW = 40          # choices before the end of a game that count as "late"


def plan(roots: list, points: int, *, alternatives: int = 3, horizon: int = 1500, late_share: float = 0.7,
         seed: int = 0) -> list[dict]:
    """Jobs for selfplay.run: up to `points` moments, each forked once per alternative action."""
    rng = random.Random(seed)
    candidates = []
    for g in read_games(roots):
        first = g["steps"][0]
        # only whole seeded self-play games, from their first choice, can be replayed
        if not isinstance(first["game"], int) or first.get("step") != 1 or g.get("skip"):
            continue
        if any(s.get("source") in ("human", "replay", "fork") for s in g["steps"]):
            continue
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
