"""Play whole games with the trained brain and keep every step: the corpus the next model learns from.

Each game is a process, in one of `--workers` slots. A slot has its own webtiles account
(`ladderbrain1`, `ladderbrain2`, ...), since an account has one save. A game writes into
`<out>/<name>/g<seed>/<timestamp>/`:
  - `steps.jsonl`: one line per choice the brain made (observation, what was possible, what the rules of
    thumb would do, what was done and who chose), and one `"type": "end"` line per game
  - `game<seed>.protocol.jsonl.gz`: every webtiles message, so features can be rebuilt from scratch
  - the usual `interrupts.jsonl`, `decisions.jsonl`, `summary.json`
`<out>/<name>/results.json` has one row per game and the averages.

dcss-api's reads have no timeout, so the parent watches each game's heartbeat and kills one that goes
quiet. It is recorded as `hung`, and the save it left is quit before that account's next game.
"""

from __future__ import annotations

import gzip
import json
import multiprocessing as mp
import random
import shutil
import statistics
import time
from dataclasses import asdict
from multiprocessing import connection
from pathlib import Path

from .policy import Style

ACCOUNT = "ladderbrain"
QUIET_SECONDS = 60


class StaleSave(RuntimeError):
    """The game that started is an old one the account had saved, not a new one on the seed asked for."""


def _play(job: dict, cfg: dict, log, beat) -> dict:
    from ..conn import Connection
    from ..games import crawlrc
    from ..reflex import Hooks, Reflex
    from ..state import GameState
    from .net import load_model
    from .policy import BrainTiers
    from .steplog import StepLog

    seed, user = job["seed"], cfg["user"]
    game_id = job.get("id", seed)
    steps = StepLog(log.dir)
    raw = log.dir / f"game{seed}.protocol.jsonl"       # plain while playing, so a killed game's is readable
    record = raw.open("w", buffering=1)                # line by line: a killed game keeps its last lines
    net = load_model(cfg["model"]) if cfg["model"] else None
    tiers = steps.attach(BrainTiers(net, Style(**cfg["style"]), cfg["epsilon"], random.Random(seed * 7919 + 1),
                                    job.get("script"), job.get("horizon", 0), job.get("commit", False)), game_id)

    class Recorder(Hooks):
        def on_step(self, reflex, action):
            beat()

    def start():
        state = GameState()
        conn = Connection(cfg["server"], on_message=state.apply, record=record)
        conn.login(user)
        conn.set_rc(crawlrc())
        conn.start_game(cfg["species"], cfg["background"], cfg["weapon"], seed=seed)
        return state, conn

    state, conn = start()
    try:
        if state.turn > 1:
            # The account still held a game (one that ended without a death and wasn't quit), and a
            # seeded start resumed it: that is not this seed's dungeon.
            raise StaleSave(f"{user} resumed a saved game at turn {state.turn}")
        beat()
        game = Reflex(conn, state, log, seed, Recorder(), tiers).run(max_steps=cfg["max_steps"], max_turns=cfg["max_turns"])
        end = steps.end(game_id, state, game, tiers)
        log.end_game(game)
        if not state.dead:
            conn.quit_game()
        return end
    finally:
        conn.close()
        record.close()
        steps.close()
        with raw.open("rb") as src, gzip.open(f"{raw}.gz", "wb") as dst:
            shutil.copyfileobj(src, dst)
        raw.unlink()


def _clear_save(cfg: dict) -> None:
    """Abandon whatever game the account has saved (one that hung, or was killed).

    A seeded start waits for the seed menu, which never comes while a save exists. A plain start
    resumes the save (or begins a throwaway game), and either can be quit.
    """
    import dcss_api

    from ..conn import GAME_ID, Connection, classify_error
    from ..games import crawlrc
    conn = Connection(cfg["server"])
    try:
        conn.login(cfg["user"])
        conn.set_rc(crawlrc())
        try:
            conn.web.start_game(GAME_ID, cfg["species"], cfg["background"], cfg["weapon"])
        except (dcss_api.APIErr, dcss_api.BlockingErr) as e:
            if classify_error(e) == "more":                    # the save opens on a --more--
                conn.web.write_key("key_enter")
        if not any(m.get("msg") == "input_mode" and m.get("mode") == 1 for m in conn._drain()):
            # the save reopens the prompt the game was killed at: answer it first
            blocking = conn.sync().blocking
            for _ in range(4):
                if blocking in (None, "more", "died"):
                    break
                if blocking == "text_input":                   # the level-up stat prompt takes no Esc
                    blocking = conn.act("S").blocking
                else:                                          # a scroll's target: cancel, and yes, waste it
                    blocking = conn.act("key_esc", "Y", through_menu=True).blocking
        conn.quit_game()
    finally:
        conn.close()


def usable_slots(server: str, workers: int, log=print) -> list[int]:
    """The slots whose account can log in, checked one after another.

    Each is registered on first use. Webtiles corrupts an account when several register at the same
    moment (the stored hash comes out two characters long, and no password opens it again), so this
    must not happen in the workers, in parallel. A slot that can't log in is left out.
    """
    from ..conn import Connection, LoginError
    good = []
    for k in range(1, workers + 1):
        conn = Connection(server)
        try:
            conn.login(f"{ACCOUNT}{k}")
            good.append(k)
        except LoginError as e:
            log(f"  leaving out {ACCOUNT}{k}: {e}")
        finally:
            conn.close()
    return good


def _worker(k: int, job: dict, clear: bool, pipe, cfg: dict) -> None:
    """One game in its own process, so a hang costs that game and nothing else."""
    from ..runlog import RunLog
    cfg = {**cfg, "user": f"{ACCOUNT}{k}"}
    if clear:
        _clear_save(cfg)
        pipe.send(("beat", None))
    game_id = job.get("id", job["seed"])
    log = RunLog(Path(cfg["dir"]) / f"g{game_id}")
    try:
        try:
            end = _play(job, cfg, log, lambda: pipe.send(("beat", None)))
        except StaleSave:
            _clear_save(cfg)                                   # quit the old game, then start this one again
            pipe.send(("beat", None))
            end = _play(job, cfg, log, lambda: pipe.send(("beat", None)))
    except Exception as e:  # noqa: BLE001  (a lost game shouldn't lose the run)
        end = {"type": "end", "game": game_id, "ended_by": "error", "error": f"{type(e).__name__}: {e}"}
    finally:
        log.close()
    pipe.send(("end", end))
    pipe.close()


def summarize(results: list[dict]) -> dict:
    played = [r for r in results if "max_depth" in r]
    if not played:
        return {"games": 0, "lost": len(results)}
    depths = [r["max_depth"] for r in played]
    ended: dict[str, int] = {}
    for r in results:
        ended[r.get("ended_by", "?")] = ended.get(r.get("ended_by", "?"), 0) + 1
    return {"games": len(played), "lost": len(results) - len(played),
            "mean_depth": round(statistics.mean(depths), 2), "median_depth": statistics.median(depths),
            "max_depth": max(depths), "mean_xl": round(statistics.mean(r["xl"] for r in played), 2),
            "mean_turns": round(statistics.mean(r["turn"] for r in played)),
            "died": sum(r["died"] for r in played), "ended_by": ended}


def run(name: str, seeds: list, *, workers: int = 4, model: str | None = None, epsilon: float = 0.0,
        style: Style | None = None, out: str = "runs/brain", server: str | None = None,
        species: str = "b", background: str = "f", weapon: str = "b", max_steps: int = 4000,
        max_turns: int = 40000, on_game=lambda end, done, total: None) -> dict:
    from ..conn import DEFAULT_URL
    directory = Path(out) / name
    directory.mkdir(parents=True, exist_ok=True)
    cfg = {"dir": str(directory), "model": model, "epsilon": epsilon, "style": asdict(style or Style()),
           "server": server or DEFAULT_URL, "species": species, "background": background, "weapon": weapon,
           "max_steps": max_steps, "max_turns": max_turns}
    ctx = mp.get_context("spawn")
    # a job is a seed, or a dict with "seed" and, for a fork, "id", "script", "horizon" and maybe "commit"
    todo = [s if isinstance(s, dict) else {"seed": s} for s in seeds]
    procs: dict[int, tuple] = {}                               # slot -> (process, seed, its pipe)
    seen: dict[int, float] = {}
    slots = usable_slots(cfg["server"], workers)
    if not slots:
        raise RuntimeError("no self-play account could log in")
    dirty = dict.fromkeys(slots, True)                         # may the account hold a stale save?
    ready = dict.fromkeys(dirty, 0.0)
    results: list[dict] = []
    started = time.time()

    def finish(k: int, end: dict) -> None:
        proc, _, pipe = procs.pop(k)
        proc.join(timeout=5)
        if proc.is_alive():
            proc.terminate()
        pipe.close()
        results.append(end)
        on_game(end, len(results), len(seeds))

    while len(results) < len(seeds):
        for k in dirty:
            if k not in procs and todo and time.time() >= ready[k]:
                job = todo.pop(0)
                seed = job.get("id", job["seed"])
                # A pipe per game, not a shared queue: killing a process that holds a queue's lock
                # leaves the queue dead for everyone else.
                recv, send = ctx.Pipe(duplex=False)
                proc = ctx.Process(target=_worker, args=(k, job, dirty[k], send, cfg), daemon=True)
                proc.start()
                send.close()
                procs[k], seen[k], dirty[k] = (proc, seed, recv), time.time(), False
        by_pipe = {pipe: k for k, (_, _, pipe) in procs.items()}
        for pipe in connection.wait(list(by_pipe), timeout=2):
            k = by_pipe[pipe]
            try:
                while k in procs and pipe.poll():
                    ev, data = pipe.recv()
                    seen[k] = time.time()
                    if ev == "end":
                        dirty[k] = data["ended_by"] == "error"
                        finish(k, data)
            except (EOFError, OSError):
                seed = procs[k][1]                             # it died without a word
                dirty[k], ready[k] = True, time.time() + 12
                finish(k, {"type": "end", "game": seed, "ended_by": "crashed"})
        for k, (proc, seed, _) in list(procs.items()):
            if time.time() - seen[k] > QUIET_SECONDS:
                proc.terminate()
                dirty[k], ready[k] = True, time.time() + 12    # webtiles saves a dropped game after about 10 s
                finish(k, {"type": "end", "game": seed, "ended_by": "hung"})
    summary = {"name": name, "model": model, "epsilon": epsilon, "style": cfg["style"],
               "seconds": round(time.time() - started), **summarize(results),
               "results": sorted(results, key=lambda r: str(r["game"]))}
    (directory / "results.json").write_text(json.dumps(summary, indent=1))
    return summary
