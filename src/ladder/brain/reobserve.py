"""`ladder brain reobserve`: the `sight` fields for steps logged before they existed, from protocol logs.

Each self-play game keeps every webtiles message (`game<seed>.protocol.jsonl.gz` beside its
`steps.jsonl`). Folding them through a `GameState` again rebuilds the state the brain saw at each choice;
`features.sight` then reads what the old observation left out. The work is lining each logged step up
with its moment in the log:

  - Points: every `_ladder` note (the keys about to be sent; logs from round 1 on), or every
    `input_mode` message in older logs that have no notes.
  - A step matches a point when the turn, HP and depth agree and every monster it lists stands where
    it says. The check then re-runs `observe` there and compares the fields (CHECK). An exact match is
    taken at once; an inexact one is held, and taken only if no exact point of the same turn follows.
  - A point can serve several steps (a choice that sent no key leaves no note).

What comes out is a sidecar per step log, `<out>/<path of the log under its root>/steps.x.jsonl`: one
line per step, `{"game", "step", "ok", "exact", "x"}` with `x` the `sight` dict, or `"ok": false` when
the step could not be placed (no protocol log, or the replay never reached it). corpus.build folds the
sidecars in; a step without one stays marked missing (`seen_missing`), never silently zero.

Games on evaluation dungeons (seeds from corpus.HOLDOUT_SEED up) are never read.
"""

from __future__ import annotations

import gzip
import json
import multiprocessing as mp
import time
from pathlib import Path

from ..state import GameState
from .corpus import HOLDOUT_SEED, seed_of, step_files
from .features import MAX_MONS, observe, sight

SIDECAR = "steps.x.jsonl"
CHECK = ("turn", "place", "depth", "hp", "hp_max", "mp", "xl", "progress", "ac", "ev", "sh", "str", "dex",
         "poison_survival", "n_hostiles", "on_down", "on_up", "dist_down", "dist_up", "open_neighbors", "status")
V4_MON_KEYS = ("name", "dx", "dy", "threat", "unique")


def _try(state: GameState, o: dict) -> tuple[list[str], dict] | None:
    """None if this point can't be the step's; else (fields observe gets wrong here, the sight dict)."""
    if state.turn != o["turn"] or state.hp != o["hp"] or state.player.get("depth", 0) != o["depth"]:
        return None
    px, py = state.pos
    by_pos = {(m.pos[0] - px, m.pos[1] - py): m for m in state.hostiles()}
    want = [(m["dx"], m["dy"]) for m in o["mons"]]
    if not all(w in by_pos for w in want):
        return None
    keep = [by_pos[w] for w in want]                   # in the step's order; active_hostiles drops ignored ones
    ctx = {"level_explored": o.get("level_explored"), "level_turn": o["turn"] - o.get("level_turns", 0),
           "level_steps": o.get("level_steps", 0), "hp_delta": o.get("hp_delta", 0.0),
           "last_action": o.get("last_action")}
    re = observe(state, list(keep), ctx)
    bad = [f for f in CHECK if f in o and re.get(f) != o[f]]
    if [{k: m.get(k) for k in V4_MON_KEYS} for m in re["mons"]] != [{k: m.get(k) for k in V4_MON_KEYS} for m in o["mons"]]:
        bad.append("mons")
    return bad, sight(state, keep[:MAX_MONS])


def align(steps: list[dict], protocol: Path) -> list[dict]:
    """For each step (in order), {"ok", "exact", "bad", "x"} or {"ok": False}, from the game's protocol log."""
    out: list[dict] = [{"ok": False} for _ in steps]
    state = GameState()
    k = 0
    pending: tuple[int, list[str], dict] | None = None     # the first inexact candidate for step k
    has_notes = False

    def accept(bad: list[str], x: dict) -> None:
        nonlocal k, pending
        out[k] = {"ok": True, "exact": not bad, "bad": bad, "x": x}
        k += 1
        pending = None

    def at_point() -> None:
        nonlocal pending
        while k < len(steps):
            o = steps[k]["obs"]
            if pending and pending[0] == k and state.turn != o["turn"]:
                accept(pending[1], pending[2])
                continue
            hit = _try(state, o)
            if hit is None:
                return
            bad, x = hit
            if bad:
                if not pending or pending[0] != k:
                    pending = (k, bad, x)
                return
            accept([], x)

    with gzip.open(protocol, "rt") as fh:
        for line in fh:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue                                    # the last line of a killed game
            if msg.get("msg") == "_ladder":
                has_notes = True
                at_point()
                continue
            state.apply(msg)
            if not has_notes and msg.get("msg") == "input_mode":
                at_point()
            if k == len(steps):
                break
    if pending and pending[0] == k:
        accept(pending[1], pending[2])
    return out


def _read_steps(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("type") != "end" and "obs" in r:
            rows.append(r)
    return rows


def sidecar_for(steps_file: Path) -> list[dict]:
    """Sidecar lines for one steps.jsonl: each game in it aligned against its own protocol log."""
    rows = _read_steps(steps_file)
    by_game: dict = {}
    for r in rows:
        by_game.setdefault(r.get("game"), []).append(r)
    lines = []
    for game, steps in by_game.items():
        seed = seed_of(game)
        if seed >= HOLDOUT_SEED:
            continue                                        # evaluation dungeons: never read
        proto = steps_file.parent / f"game{seed}.protocol.jsonl.gz"
        if any("obsx" in s["obs"] for s in steps):
            got = [{"ok": True, "exact": True, "bad": [], "x": None, "live": True} for _ in steps]
        elif seed >= 0 and proto.exists():
            got = align(steps, proto)
        else:
            got = [{"ok": False, "why": "no protocol log"} for _ in steps]
        for s, g in zip(steps, got):
            lines.append({"game": game, "step": s.get("step"), **g})
    return lines


def _job(args: tuple[str, str]) -> dict:
    src, dst = Path(args[0]), Path(args[1])
    t0 = time.time()
    try:
        lines = sidecar_for(src)
    except (OSError, EOFError, ValueError) as e:                # a torn gzip, an unreadable file
        return {"file": str(src), "error": f"{type(e).__name__}: {e}"}
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(x, separators=(",", ":")) + "\n" for x in lines))
    tmp.replace(dst)
    return {"file": str(src), "steps": len(lines), "ok": sum(x["ok"] for x in lines),
            "exact": sum(bool(x.get("exact")) for x in lines),
            "no_protocol": sum(x.get("why") == "no protocol log" for x in lines), "secs": round(time.time() - t0, 2)}


def run(roots: list[str | Path], out: str | Path, workers: int = 4, fresh: bool = False, log=print) -> dict:
    """Write a sidecar for every steps.jsonl under `roots` into `out`, mirroring the paths under each root."""
    out = Path(out)
    jobs = []
    for root in roots:
        root = Path(root)
        for f in step_files(root):
            dst = out / f.parent.relative_to(root) / SIDECAR
            if fresh or not dst.exists() or dst.stat().st_mtime < f.stat().st_mtime:
                jobs.append((str(f), str(dst)))
    log(f"reobserve: {len(jobs)} step logs to align, {workers} at once")
    t0 = time.time()
    done: list[dict] = []
    with mp.get_context("spawn").Pool(workers) as pool:
        for i, r in enumerate(pool.imap_unordered(_job, jobs, chunksize=4), 1):
            done.append(r)
            if i % 200 == 0 or i == len(jobs):
                log(f"  [{i}/{len(jobs)}] {time.time() - t0:.0f}s")
    summary = coverage(roots, out)
    summary["errors"] = [r for r in done if "error" in r]
    summary["seconds"] = round(time.time() - t0)
    out.mkdir(parents=True, exist_ok=True)
    (out / "reobserve.json").write_text(json.dumps(summary, indent=1))
    return summary


def coverage(roots: list[str | Path], out: str | Path) -> dict:
    """How many steps under `roots` have sight fields, from all the sidecars there are, by top directory."""
    out = Path(out)
    by: dict[str, dict] = {}
    for root in roots:
        root = Path(root)
        for f in step_files(root):
            rel = f.parent.relative_to(root)
            side = out / rel / SIDECAR
            top = by.setdefault(rel.parts[0] if rel.parts else ".", {"steps": 0, "ok": 0, "exact": 0, "no_protocol": 0})
            if not side.exists():
                continue
            for line in side.read_text().splitlines():
                x = json.loads(line)
                top["steps"] += 1
                top["ok"] += bool(x["ok"])
                top["exact"] += bool(x.get("exact"))
                top["no_protocol"] += x.get("why") == "no protocol log"
    tot = {k: sum(v[k] for v in by.values()) for k in ("steps", "ok", "exact", "no_protocol")}
    with_log = tot["steps"] - tot["no_protocol"]
    return {"total": tot, "aligned_share": round(tot["ok"] / max(tot["steps"], 1), 5),
            "aligned_share_with_protocol": round(tot["ok"] / max(with_log, 1), 5), "by_top": by}
