"""`ladder brain ...`: self-play, corpus, train, evaluate, and the loop that chains them."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from . import selfplay
from .corpus import HOLDOUT_SEED
from .policy import Style

CHAMPION = "models/brain.json"
EVAL_SEED = HOLDOUT_SEED      # evaluation games use seeds from here up; self-play and training never do


def _progress(end: dict, done: int, total: int) -> None:
    where = f"{end.get('place', '?')}:{end.get('depth', '?')}" if "place" in end else "-"
    print(f"  [{done}/{total}] seed {end['game']}: {end['ended_by']}  reached {end.get('max_depth', '-')}"
          f"  at {where}  xl {end.get('xl', '-')}  turn {end.get('turn', '-')}"
          + (f"  ({end.get('escalation') or end.get('error')})" if end.get("escalation") or end.get("error") else ""),
          flush=True)


def _style(args: argparse.Namespace) -> Style:
    style = Style()
    for pair in args.style or []:
        key, _, value = pair.partition("=")
        if not hasattr(style, key):
            raise SystemExit(f"no style weight '{key}' (have: {', '.join(vars(style))})")
        setattr(style, key, float(value))
    return style


def _play(args: argparse.Namespace, name: str, seeds: list[int], model: str | None, epsilon: float) -> dict:
    print(f"{name}: {len(seeds)} games, model {model or 'none (rules of thumb)'}, epsilon {epsilon}")
    s = selfplay.run(name, seeds, workers=args.workers, model=model, epsilon=epsilon, style=_style(args),
                     out=args.out, server=args.server, species=args.species, background=args.background,
                     weapon=args.weapon, max_steps=args.max_steps, max_turns=args.max_turns, on_game=_progress)
    print("  " + json.dumps({k: v for k, v in s.items() if k not in ("results", "style", "name", "model")}))
    return s


def cmd_selfplay(args: argparse.Namespace) -> None:
    name = args.name or time.strftime("play-%Y%m%d-%H%M%S")
    _play(args, name, list(range(args.seed, args.seed + args.games)), args.model, args.epsilon)


def learn_from(args: argparse.Namespace) -> list[str]:
    """Where the corpus is read from: every steps.jsonl under --runs, after turning any new recording
    of a person's game (play<n>.jsonl, written by the cockpit's proxy) into one."""
    from .humanplay import convert_all
    for done in convert_all(args.runs, Path(args.out) / "human"):
        print(f"  human play: {done['file']} -> {done['rows']} rows {done['by_action']}")
    return args.roots or [args.runs]


def cmd_corpus(args: argparse.Namespace) -> None:
    from .corpus import build
    print(json.dumps(build(learn_from(args), args.corpus), indent=1))


def cmd_forks(args: argparse.Namespace) -> None:
    from .forks import plan
    jobs = plan(args.roots or [args.runs], args.points, alternatives=args.alternatives, horizon=args.horizon,
                seed=args.seed)
    name = args.name or time.strftime("forks-%Y%m%d-%H%M%S")
    print(f"{name}: {len(jobs)} forks, continuing with {args.model or 'the rules of thumb'}")
    s = selfplay.run(name, jobs, workers=args.workers, model=args.model, epsilon=0.0, style=_style(args),
                     out=args.out, server=args.server, species=args.species, background=args.background,
                     weapon=args.weapon, max_steps=args.max_steps, max_turns=args.max_turns, on_game=_progress)
    diverged = sum("replay diverged" in (r.get("escalation") or "") for r in s["results"])
    print(f"  {s['games']} played, {s['lost']} lost, {diverged} left the recorded game, {s['seconds']} s")


def cmd_human(args: argparse.Namespace) -> None:
    from .humanplay import convert
    for f in args.files:
        print(json.dumps(convert(f, Path(args.out) / "human"), indent=1))
    if not args.files:
        learn_from(args)


def cmd_train(args: argparse.Namespace) -> None:
    from .net import check_parity
    from .train import train
    train(args.corpus, args.model_out, hidden=args.hidden, epochs=args.epochs, note=args.note)
    print(f"parity with torch: {check_parity(args.model_out):.5f}")


def evaluate(args: argparse.Namespace, model: str | None, games: int) -> dict:
    """Play the evaluation seeds with no exploration. Results are kept per model and reused."""
    from .fleet import eval_name
    # a style given on the command line is part of what is being measured
    name = eval_name(model, args.style)
    done = Path(args.out) / name / "results.json"
    if done.exists() and not getattr(args, "fresh", False):
        s = json.loads(done.read_text())
        # results written before a style weight existed were played with its default
        if len(s["results"]) >= games and {**Style().to_dict(), **(s.get("style") or {})} == _style(args).to_dict():
            return s
    return _play(args, name, list(range(EVAL_SEED, EVAL_SEED + games)), model, 0.0)


def compare(a: dict, b: dict) -> dict:
    """Seed by seed: how often `a` got deeper than `b`."""
    da = {r["game"]: r["max_depth"] for r in a["results"] if "max_depth" in r}
    db = {r["game"]: r["max_depth"] for r in b["results"] if "max_depth" in r}
    both = sorted(set(da) & set(db))
    return {"seeds": len(both), "deeper": sum(da[s] > db[s] for s in both), "same": sum(da[s] == db[s] for s in both),
            "shallower": sum(da[s] < db[s] for s in both)}


def cmd_versus(args: argparse.Namespace) -> None:
    rows = [(m, evaluate(args, None if m == "baseline" else m, args.games)) for m in args.models]
    print(f"\n{'model':28} {'games':>5} {'mean depth':>10} {'median':>6} {'best':>4} {'mean xl':>7} {'died':>4} {'turns':>6}")
    for m, s in rows:
        print(f"{Path(m).stem:28} {s['games']:>5} {s['mean_depth']:>10} {s['median_depth']:>6} {s['max_depth']:>4} "
              f"{s['mean_xl']:>7} {s['died']:>4} {s['mean_turns']:>6}")
    for m, s in rows[1:]:
        print(f"{Path(m).stem} vs {Path(rows[0][0]).stem}: {compare(s, rows[0][1])}")


def cmd_iterate(args: argparse.Namespace) -> None:
    """Self-play with the champion, fork its games, retrain on everything, evaluate, promote if it gets deeper."""
    from .corpus import build
    from .net import check_parity
    from .train import train

    champion = Path(args.champion)
    ledger_path = champion.parent / "brain.ledger.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {"rounds": []}
    for _ in range(args.rounds):
        n = len(ledger["rounds"])
        current = str(champion) if champion.exists() else None
        seed = args.seed + n * 10_000
        play = _play(args, f"iter{n}", list(range(seed, seed + args.games)), current, args.epsilon)
        if args.fork_points:
            from .forks import plan
            jobs = plan([Path(args.out) / f"iter{n}"], args.fork_points, seed=n)
            print(f"forks{n}: {len(jobs)} forks of this round's games")
            forks = selfplay.run(f"forks{n}", jobs, workers=args.workers, model=current, epsilon=0.0,
                                 style=_style(args), out=args.out, server=args.server, species=args.species,
                                 background=args.background, weapon=args.weapon, max_steps=args.max_steps,
                                 max_turns=args.max_turns)
            print(f"  {forks['games']} played, {forks['lost']} lost, {forks['seconds']} s")
        meta = build(learn_from(args), args.corpus)
        print(f"  corpus: {meta['rows']} rows from {meta['games']} games ({meta['deaths']} deaths), {meta['by_source']}")
        candidate = champion.parent / f"iter{n}.json"
        info = train(args.corpus, candidate, hidden=args.hidden, epochs=args.epochs, note=f"round {n}",
                     log=lambda line: print("  " + line))
        check_parity(candidate)
        old = evaluate(args, current, args.eval_games)
        new = evaluate(args, str(candidate), args.eval_games)
        versus = compare(new, old)
        # Only games both sides finished are compared. If many were lost (the server paused, the
        # laptop slept) the ones left are not the same test, and the round promotes nothing.
        complete = versus["seeds"] >= 0.9 * args.eval_games
        promoted = complete and (new["mean_depth"], -new["died"]) > (old["mean_depth"], -old["died"])
        if promoted:
            shutil.copy(candidate, champion)
        keys = ("mean_depth", "median_depth", "max_depth", "mean_xl", "died")
        row = {"round": n, "candidate": str(candidate),
               "selfplay": {k: play[k] for k in ("games", "mean_depth", "died", "seconds")},
               "corpus_rows": meta["rows"], "val": info["val"],
               "champion": {k: old[k] for k in keys}, "challenger": {k: new[k] for k in keys},
               "versus": versus, "promoted": promoted, "at": time.strftime("%Y-%m-%d %H:%M")}
        ledger["rounds"].append(row)
        ledger_path.write_text(json.dumps(ledger, indent=1))
        print(f"round {n}: candidate {new['mean_depth']} vs champion {old['mean_depth']} mean depth over "
              f"{versus['seeds']} seeds ({versus}) -> {'promoted' if promoted else 'kept the champion'}"
              + ("" if complete else f" (only {versus['seeds']} of {args.eval_games} evaluation games finished: re-run "
                                     f"`ladder brain eval {current or 'baseline'} {candidate} --fresh`)"))


def cmd_fleet_jobs(args: argparse.Namespace) -> None:
    from .fleet import jobs
    print(json.dumps(jobs(json.loads(Path(args.spec).read_text()), out=args.out)))


def cmd_fleet_shard(args: argparse.Namespace) -> None:
    from .fleet import shard
    spec = json.loads(Path(args.spec).read_text())
    print(f"{spec['name']} batch {spec['tag']}: {len(spec['jobs'])} games, {spec['workers']} workers", flush=True)
    s = shard(spec, on_game=_progress)
    print("FLEET-SHARD " + json.dumps({k: v for k, v in s.items() if k not in ("results", "style")}), flush=True)


def cmd_fleet_merge(args: argparse.Namespace) -> None:
    from .fleet import merge
    print(json.dumps(merge(Path(args.out) / args.name), indent=1))


def add_parser(sub) -> None:
    p = sub.add_parser("brain", help="the trained brain: self-play, corpus, train, eval, iterate")
    bsub = p.add_subparsers(dest="brain_cmd", required=True)

    def common(q, play=True):
        q.add_argument("--out", default="runs/brain", help="where self-play games are written and read")
        q.add_argument("--runs", default="runs", help="searched for step logs and recordings of your own games")
        q.add_argument("--corpus", default="runs/brain/corpus.npz")
        if not play:
            return
        from ..conn import DEFAULT_URL
        q.add_argument("--workers", type=int, default=4, help="games at once, one account each (ladderbrain<k>)")
        q.add_argument("--server", default=DEFAULT_URL)
        q.add_argument("--species", default="b")
        q.add_argument("--background", default="f")
        q.add_argument("--weapon", default="b")
        q.add_argument("--max-steps", type=int, default=4000)
        q.add_argument("--max-turns", type=int, default=40000)
        q.add_argument("--style", nargs="*", metavar="KEY=VALUE", help="style weights, e.g. died_go=-3 margin=0.1")

    q = bsub.add_parser("selfplay", help="play games and log every step")
    common(q)
    q.add_argument("--name")
    q.add_argument("--games", type=int, default=20)
    q.add_argument("--seed", type=int, default=1)
    q.add_argument("--model", help="model file; without one the rules of thumb play")
    q.add_argument("--epsilon", type=float, default=0.2, help="share of choices made at random")
    q.set_defaults(fn=cmd_selfplay)

    q = bsub.add_parser("corpus", help="turn step logs into training rows")
    common(q, play=False)
    q.add_argument("roots", nargs="*", help="directories to search for steps.jsonl (default: --runs)")
    q.set_defaults(fn=cmd_corpus)

    q = bsub.add_parser("forks", help="replay recorded games to a choice and try the other actions there")
    common(q)
    q.add_argument("roots", nargs="*", help="directories whose self-play games to fork (default: --runs)")
    q.add_argument("--name")
    q.add_argument("--points", type=int, default=200, help="moments to fork")
    q.add_argument("--alternatives", type=int, default=3, help="other actions tried at each")
    q.add_argument("--horizon", type=int, default=0,
                   help="game turns played after the fork; 0 = to the end, which the depth_end label needs")
    q.add_argument("--model", help="plays on after the fork; without one the rules of thumb do")
    q.add_argument("--seed", type=int, default=0, help="which moments are picked")
    q.set_defaults(fn=cmd_forks)

    q = bsub.add_parser("human", help="turn recordings of your own games (play<n>.jsonl) into step logs")
    common(q, play=False)
    q.add_argument("files", nargs="*", help="recordings to convert (default: every new one under --runs)")
    q.set_defaults(fn=cmd_human, roots=None)

    q = bsub.add_parser("train", help="train a model from the corpus (needs torch: uv sync --group train)")
    common(q, play=False)
    q.add_argument("--model-out", default="models/candidate.json")
    q.add_argument("--hidden", type=int, default=64)
    q.add_argument("--epochs", type=int, default=20)
    q.add_argument("--note", default="")
    q.set_defaults(fn=cmd_train)

    q = bsub.add_parser("eval", aliases=["versus"], help="play fixed seeds with each model and compare ('baseline' = no model)")
    common(q)
    q.add_argument("models", nargs="+")
    q.add_argument("--games", type=int, default=30)
    q.add_argument("--fresh", action="store_true", help="replay even if results exist")
    q.set_defaults(fn=cmd_versus)

    # used by the ladder-fleet app (mac/Fleet), which plays batches of games on other Macs
    q = bsub.add_parser("fleet-jobs", help="expand a fleet request (JSON file) into runs of jobs")
    common(q, play=False)
    q.add_argument("spec")
    q.set_defaults(fn=cmd_fleet_jobs)
    q = bsub.add_parser("fleet-shard", help="play one fleet batch (JSON file) on this host")
    q.add_argument("spec")
    q.set_defaults(fn=cmd_fleet_shard)
    q = bsub.add_parser("fleet-merge", help="combine a fleet run's batches into its results.json")
    common(q, play=False)
    q.add_argument("name")
    q.set_defaults(fn=cmd_fleet_merge)

    q = bsub.add_parser("iterate", help="self-play, retrain, evaluate, promote; repeat")
    common(q)
    q.add_argument("roots", nargs="*", help="directories to learn from (default: --runs)")
    q.add_argument("--rounds", type=int, default=1)
    q.add_argument("--games", type=int, default=60, help="self-play games per round")
    q.add_argument("--eval-games", type=int, default=30)
    q.add_argument("--fork-points", type=int, default=100,
                   help="moments of each round's games to replay and try the other actions at; 0 = none")
    q.add_argument("--seed", type=int, default=1)
    q.add_argument("--epsilon", type=float, default=0.2)
    q.add_argument("--hidden", type=int, default=64)
    q.add_argument("--epochs", type=int, default=20)
    q.add_argument("--champion", default=CHAMPION)
    q.set_defaults(fn=cmd_iterate)


def main(args: argparse.Namespace) -> None:
    args.fn(args)
