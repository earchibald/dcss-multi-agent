"""The Python half of `ladder-fleet` (mac/Fleet): games played on other Macs, in batches.

The fleet server on the driving Mac turns a request into named runs of jobs (`jobs`), hands batches
of those jobs to run hosts, and each host plays its batch with `shard`. A batch writes the usual
`g<id>/` directories plus `shard-<tag>.json` (selfplay's `results.json`, renamed so batches don't
overwrite each other). The server copies them back into `<out>/<name>/` and `merge` writes the
run's `results.json`, in the same shape `selfplay.run` writes, so `ladder brain eval` and the corpus
read a fleet run like a local one.

Specs are JSON, so the Swift side never needs to know what a job or a style is:
  request: {"kind": "selfplay" | "eval" | "forks", "games", "seed", "model", "models", "epsilon",
            "style": ["key=value", ...], "name", "fresh", "points", "alternatives", "horizon",
            "fork_seed", "roots", "species", "background", "weapon", "max_steps", "max_turns"}
  runs:    {"runs": [{"name", "jobs": [seed | fork job, ...], "play": {...}}]}
  shard:   {"name", "jobs", "play", "workers", "server", "out", "tag"}
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from . import selfplay
from .corpus import HOLDOUT_SEED
from .policy import Style

PLAY_KEYS = ("species", "background", "weapon", "max_steps", "max_turns")


def style_from(pairs: list[str] | None) -> Style:
    style = Style()
    for pair in pairs or []:
        key, _, value = pair.partition("=")
        if not hasattr(style, key):
            raise ValueError(f"no style weight '{key}' (have: {', '.join(vars(style))})")
        setattr(style, key, float(value))
    return style


def eval_name(model: str | None, pairs: list[str] | None) -> str:
    """The run name `ladder brain eval` uses, so it finds and reuses a fleet evaluation."""
    label = Path(model).stem if model else "baseline"
    return f"eval-{label}" + "".join(f"-{pair}" for pair in sorted(pairs or []))


def _played(directory: Path, style: Style) -> dict:
    """Games a run already has (results.json), by game id, if it was played with this style."""
    done = directory / "results.json"
    if not done.exists():
        return {}
    s = json.loads(done.read_text())
    if {**Style().to_dict(), **(s.get("style") or {})} != style.to_dict():
        return {}
    return {r["game"]: r for r in s.get("results", []) if "max_depth" in r}


def jobs(request: dict, out: str = "runs/brain") -> dict:
    """Expand a request into named runs of jobs. An evaluation skips seeds it already has."""
    kind = request["kind"]
    pairs = request.get("style") or []
    style_from(pairs)                                          # fail here, not on a run host
    play = {"style": pairs, **{k: request[k] for k in PLAY_KEYS if request.get(k) is not None}}
    if kind == "selfplay":
        name = request.get("name") or time.strftime("play-%Y%m%d-%H%M%S")
        seed, games = request.get("seed", 1), request.get("games", 20)
        if seed + games > HOLDOUT_SEED:
            raise ValueError(f"self-play seeds must stay below {HOLDOUT_SEED} (evaluation seeds)")
        return {"runs": [{"name": name, "jobs": list(range(seed, seed + games)),
                          "play": {**play, "model": request.get("model"), "epsilon": request.get("epsilon", 0.2)}}]}
    if kind == "eval":
        games, runs = request.get("games", 30), []
        for m in request.get("models") or ["baseline"]:
            model = None if m == "baseline" else m
            name = eval_name(model, pairs)
            have = {} if request.get("fresh") else _played(Path(out) / name, style_from(pairs))
            todo = [s for s in range(HOLDOUT_SEED, HOLDOUT_SEED + games) if s not in have]
            runs.append({"name": name, "jobs": todo, "already": len(have),
                         "play": {**play, "model": model, "epsilon": 0.0}})
        return {"runs": runs}
    if kind == "forks":
        from .forks import plan
        roots = request.get("roots") or ["runs"]
        planned = plan(roots, request.get("points", 200), alternatives=request.get("alternatives", 3),
                       horizon=request.get("horizon", 0), seed=request.get("fork_seed", 0))
        name = request.get("name") or time.strftime("forks-%Y%m%d-%H%M%S")
        return {"runs": [{"name": name, "jobs": planned,
                          "play": {**play, "model": request.get("model"), "epsilon": 0.0}}]}
    raise ValueError(f"unknown kind '{kind}' (selfplay, eval, forks)")


def shard(spec: dict, on_game=lambda end, done, total: None) -> dict:
    """Play one batch on this host and leave its results as shard-<tag>.json."""
    play = spec["play"]
    kw = {k: play[k] for k in PLAY_KEYS if k in play}
    s = selfplay.run(spec["name"], spec["jobs"], workers=spec["workers"], model=play.get("model"),
                     epsilon=play.get("epsilon", 0.0), style=style_from(play.get("style")), out=spec["out"],
                     server=spec.get("server"), on_game=on_game, **kw)
    directory = Path(spec["out"]) / spec["name"]
    target = directory / f"shard-{spec['tag']}.json"
    (directory / "results.json").replace(target)
    return {**s, "shard": str(target)}


def merge(directory: str | Path) -> dict:
    """Combine a run's batches (and any results.json it had) into results.json."""
    directory = Path(directory)
    shards = sorted(directory.glob("shard-*.json"))
    if not shards:
        raise FileNotFoundError(f"no shard-*.json in {directory}")
    first = json.loads(shards[0].read_text())
    style = Style(**{**Style().to_dict(), **(first.get("style") or {})})
    by_game = _played(directory, style)
    seconds, hosts = 0, {}
    for f in shards:
        s = json.loads(f.read_text())
        seconds += s.get("seconds", 0)
        tag = f.stem.removeprefix("shard-").rsplit("-", 1)[0]
        hosts[tag] = hosts.get(tag, 0) + len(s.get("results", []))
        for r in s.get("results", []):
            # a game played to the end beats a lost attempt at the same seed
            if r["game"] not in by_game or "max_depth" in r:
                by_game[r["game"]] = r
    results = sorted(by_game.values(), key=lambda r: str(r["game"]))
    summary = {"name": directory.name, "model": first.get("model"), "epsilon": first.get("epsilon"),
               "style": asdict(style), "seconds": seconds, **selfplay.summarize(results),
               "fleet": {"shards": len(shards), "games_by_host": hosts}, "results": results}
    (directory / "results.json").write_text(json.dumps(summary, indent=1))
    return {k: v for k, v in summary.items() if k != "results"}
