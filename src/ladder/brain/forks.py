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

`kind="teleport"` picks moments exhausted after a rage (`-Berserk`) with TELEPORT_CROWD or more hostiles in
view, where a scroll of teleportation can be read and `fight` is possible: one moment, at random, from each
spell of exhaustion. Each is forked twice, to `read_teleport` and to `fight`, both played on by the same
policy, so the pair is a paired estimate of what reading there is worth against fighting on.

`kind="unseen"` needs games played with `--style unseen=1` or more, and picks, once per game, the first moment
that switch (`policy.BrainTiers.assailed`) can have acted at: nothing in view and either burning (`Fire`) or
going up the stairs or reading teleportation, which without a hostile in view only the switch allows. Up to
there the game is the one the rules without the switch would have played. Each moment is forked twice: "on"
takes the recorded action and plays on with the forks' own style (the switch on), "off" replays only the choices
before it and plays on from there with the switch off (`"style": {"unseen": 0}` in the job), so the pair compares
the switch with the plain rules from the moment it first acts, to the end of the game. (In the "off" fork the
last replayed choice, the one before the moment, is the step marked `fork`.)
"""

from __future__ import annotations

import random

from .corpus import HOLDOUT_SEED, read_games

LATE_WINDOW = 40          # choices before the end of a game that count as "late"
KINDS = ("any", "stairs", "teleport", "unseen")
UNSEEN_MOVES = ("flee_up", "read_teleport")    # what only `Style.unseen` chooses with nothing in view
STAIRS = ("explore", "descend")
TELEPORT = ("read_teleport", "fight")
TELEPORT_CROWD = 2        # hostiles in view that make an exhausted moment outnumbered, for kind="teleport"


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


def _exhausted(s: dict) -> bool:
    return "-Berserk" in (s["obs"].get("status") or [])


def _teleport_moment(s: dict) -> bool:
    return _exhausted(s) and s["obs"].get("n_hostiles", 0) >= TELEPORT_CROWD and all(a in s["avail"] for a in TELEPORT)


def _unseen_moment(s: dict) -> bool:
    o = s["obs"]
    return not o.get("n_hostiles") and ("Fire" in (o.get("status") or []) or s["action"] in UNSEEN_MOVES)


def plan(roots: list, points: int, *, alternatives: int = 3, horizon: int = 0, late_share: float = 0.7,
         seed: int = 0, kind: str = "any") -> list[dict]:
    """Jobs for selfplay.run: up to `points` moments, each forked once per alternative action.

    `kind="stairs"`: up to `points` explore-or-descend moments, at most one per visit to a level, each
    forked both ways with `commit` (`alternatives` and `late_share` don't apply).
    `kind="teleport"`: up to `points` exhausted-and-outnumbered moments (`_teleport_moment`), one per spell of
    exhaustion, each forked to `read_teleport` and to `fight` (`alternatives` and `late_share` don't apply).
    `kind="unseen"`: up to `points` games' first `_unseen_moment`, each forked "on" and "off" (module docstring).
    """
    if kind not in KINDS:
        raise ValueError(f"no fork kind {kind!r} (have: {', '.join(KINDS)})")
    rng = random.Random(seed)
    games = [g for g in read_games(roots) if _replayable(g)]
    if kind == "stairs":
        return _plan_stairs(games, points, horizon, rng)
    if kind == "teleport":
        return _plan_teleport(games, points, horizon, rng)
    if kind == "unseen":
        return _plan_unseen(games, points, horizon, rng)
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


def _plan_unseen(games: list[dict], points: int, horizon: int, rng: random.Random) -> list[dict]:
    moments = []
    for g in games:
        i = next((k for k, s in enumerate(g["steps"]) if _unseen_moment(s)), None)
        if i:                                   # not at the first choice: the "off" fork needs a choice to replay
            moments.append((g, i))
    rng.shuffle(moments)
    jobs = []
    for g, i in moments[:points]:
        step = g["steps"][i]
        prefix = [s["action"] for s in g["steps"][:i]]
        jobs.append({"seed": step["game"], "id": f"{step['game']}-{i + 1}-on", "script": prefix + [step["action"]],
                     "horizon": horizon})
        jobs.append({"seed": step["game"], "id": f"{step['game']}-{i + 1}-off", "script": prefix, "horizon": horizon,
                     "style": {"unseen": 0.0}})
    return jobs


def _plan_teleport(games: list[dict], points: int, horizon: int, rng: random.Random) -> list[dict]:
    spells = []                    # (game, the indices of its fork moments) per spell of exhaustion
    for g in games:
        current: list[int] | None = None
        for i, s in enumerate(g["steps"]):
            if not _exhausted(s):
                if current:
                    spells.append((g, current))
                current = None
                continue
            current = current if current is not None else []
            if _teleport_moment(s):
                current.append(i)
        if current:
            spells.append((g, current))
    rng.shuffle(spells)
    jobs = []
    for g, moments in spells[:points]:
        i = rng.choice(moments)
        step = g["steps"][i]
        prefix = [s["action"] for s in g["steps"][:i]]
        for alt in TELEPORT:
            jobs.append({"seed": step["game"], "id": f"{step['game']}-{i + 1}-{alt}", "script": prefix + [alt],
                         "horizon": horizon})
    return jobs
