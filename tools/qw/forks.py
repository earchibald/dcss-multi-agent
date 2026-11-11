"""Choose moments in qw base games to fork, and write the jobs file for tools/qw/run.py.

    uv run python tools/qw/forks.py runs/qw/train-base-r1 --out runs/qw/forks-r1-jobs.json
    uv run python tools/qw/run.py --jobs runs/qw/forks-r1-jobs.json --state-log --name forks-r1 --no-build

A fork replays a base game to one decision, does something qw would not have done there (an
"option": force one of qw's primitives, or veto one of its plans), and lets qw play on until a
horizon some turns later. Alive at the horizon, against the base game at the same turn, is what
tools/qw/learn.py trains on.

Moments come from encounters (runs of decisions with an enemy in view):
- the encounter the base game died in: its start, and where HP first fell under 70% and 40%;
- encounters it survived, sampled, with the same three kinds of moment. Without these the
  model would only ever see moments where anything else beats what qw did.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from log import read_decisions

HORIZON = 2500  # turns after the fork that the game is played for
CROWD = 3  # enemies qw counts as able to reach it, for the "crowd" kind of moment
KIND_FILTER: set[str] | None = None  # --kinds
OPTION_FILTER: set[str] | None = None  # --options
GAP = 4  # decisions without an enemy in view that still belong to the same encounter

# option name -> (override spec, test on the logged state that it can act at all)
CONTROLS = {
    # qw's own choice with the dice re-rolled: what every option is measured against. A base
    # game is one draw, and the fights it died in were picked for that, so the base game
    # itself is not a fair comparison.
    "reroll": ({"force": "reroll"}, lambda s: True),
    "reroll2": ({"force": "reroll2"}, lambda s: True),
}

OPTIONS = {
    "berserk": ({"force": "berserk"}, lambda s: s["can_berserk"] and not s["berserk"]),
    "no_berserk": ({"veto": ["berserk"], "n": 8}, lambda s: s["can_berserk"] and not s["berserk"]),
    "teleport": ({"force": "teleport"}, lambda s: s["can_teleport"] and not s["teleporting"]),
    "heal_wounds": ({"force": "heal_wounds"},
                    lambda s: s["n_heal_wounds"] and s["can_drink"] and s["hp"] < 0.7 * s["mhp"]),
    "flee": ({"force": "flee", "n": 12},
             lambda s: s["can_flee_upstairs"] and s["flee_positions"] and not s["berserk"]),
    "stairs_up": ({"force": "stairs_up"}, lambda s: s["on_upstairs"] and s["can_flee_upstairs"]),
    "trogs_hand": ({"force": "trogs_hand"}, lambda s: s["can_trogs_hand"] and not s["regenerating"]),
    "brothers": ({"force": "brothers_in_arms"}, lambda s: s["can_brothers_in_arms"]),
    "retreat": ({"force": "retreat_step", "n": 3}, lambda s: not s["berserk"]),
    "no_melee": ({"veto": ["melee"], "n": 3}, lambda s: not s["berserk"]),
    # Hold a fight where few enemies can reach (tools/qw/ladder.lua). n bounds the hold; the
    # primitive hands back to qw when the fight is over or nothing better is in reach.
    "choke": ({"force": "choke", "n": 30},
              lambda s: s["enemy_count"] >= 2 and not s["berserk"]),
    "stairs_fight": ({"force": "stairs_fight", "n": 30},
                     lambda s: s["enemy_count"] >= 2 and not s["berserk"]
                     and s["can_flee_upstairs"] and s["flee_positions"] > 0),
}


def encounters(decisions: list[dict]) -> list[list[dict]]:
    out, cur, quiet = [], [], 0
    for d in decisions:
        if d["state"].get("danger_in_los"):
            cur.append(d)
            quiet = 0
        elif cur:
            quiet += 1
            if quiet > GAP:
                out.append(cur)
                cur = []
    if cur:
        out.append(cur)
    return out


def moments(enc: list[dict]) -> dict[str, dict]:
    """The decisions of an encounter worth forking at, by kind."""
    serious = [d for d in enc if d["state"]["threat"] > 0 or d["state"]["immediate_danger"]]
    if not serious:
        return {}
    found = {"start": serious[0]}
    for kind, frac in (("hp70", 0.7), ("hp40", 0.4)):
        hit = next((d for d in serious if d["state"]["hp"] < frac * d["state"]["mhp"]), None)
        if hit is not None and all(hit is not f for f in found.values()):
            found[kind] = hit
    return found


def wanted_moments(enc: list[dict]) -> dict[str, dict]:
    """moments(), plus "crowd" (the first decision with CROWD or more enemies closing), cut
    down to --kinds. A crowd moment may be the same decision as another kind."""
    found = moments(enc)
    if found:
        crowd = next((d for d in enc if d["state"]["enemy_count"] >= CROWD), None)
        if crowd is not None:
            found["crowd"] = crowd
    if KIND_FILTER is not None:
        found = {k: d for k, d in found.items() if k in KIND_FILTER}
    return found


def game_jobs(gdir: Path, row: dict, rng: random.Random, survived_per_game: int,
              max_turn: int | None = None) -> list[dict]:
    decisions = [d for d in read_decisions(gdir) if d["state"] and d["action"] is not None]
    encs = [e for e in encounters(decisions) if moments(e)]
    if not encs:
        return []
    end = row.get("end_turn") or decisions[-1]["turn"]
    died = row.get("status") == "done" and row.get("ktyp") not in ("quitting", "winning", "leaving")
    picked: list[tuple[str, str, dict]] = []
    fatal = encs[-1] if died and end - encs[-1][0]["state"]["turn"] < HORIZON else None
    if fatal:
        picked += [("fatal", kind, d) for kind, d in wanted_moments(fatal).items()]
    # Sample only among encounters that will be kept: filtering afterwards would keep every
    # sampled fight of a short game and few of a long one.
    others = [e for e in encs if e is not fatal and wanted_moments(e)
              and (max_turn is None or e[0]["state"]["turn"] <= max_turn)]
    for enc in rng.sample(others, min(survived_per_game, len(others))):
        kind, d = rng.choice(sorted(wanted_moments(enc).items(), key=lambda kv: kv[0]))
        picked.append(("survived", kind, d))
    jobs = []
    for cls, kind, d in picked:
        s = d["state"]
        for name, (spec, usable) in {**CONTROLS, **OPTIONS}.items():
            if not usable(s) or (OPTION_FILTER is not None and name not in CONTROLS
                                 and name not in OPTION_FILTER):
                continue
            k = d["decision"]
            jobs.append({
                "seed": row["seed"], "tag": f"{row['seed']}-d{k}-{kind}-{name}", "base": str(gdir),
                "overrides": {str(k): spec}, "stop_turn": s["turn"] + HORIZON,
                "option": name, "decision": k, "turn": s["turn"], "class": cls, "kind": kind,
            })
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("base", type=Path, help="a base run directory (results.json, games/)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--survived", type=int, default=2, help="survived encounters sampled per game")
    ap.add_argument("--max-turn", type=int, default=None, help="skip moments later than this turn")
    ap.add_argument("--turn-budget", type=float, default=None,
                    help="total turns to replay, in millions; earliest moments first")
    ap.add_argument("--rng", type=int, default=1)
    ap.add_argument("--kinds", help="comma-separated kinds of moment: start,hp70,hp40,crowd")
    ap.add_argument("--options", help="comma-separated options (controls are always added)")
    ap.add_argument("--controls-for", type=Path,
                    help="an earlier jobs file: write only the control forks for its moments")
    args = ap.parse_args()
    global KIND_FILTER, OPTION_FILTER
    KIND_FILTER = set(args.kinds.split(",")) if args.kinds else None
    OPTION_FILTER = set(args.options.split(",")) if args.options else None

    if args.controls_for:
        seen, jobs = set(), []
        for j in json.loads(args.controls_for.read_text()):
            if (j["seed"], j["decision"]) in seen or j["option"] in CONTROLS:
                continue
            seen.add((j["seed"], j["decision"]))
            for name, (spec, _) in CONTROLS.items():
                jobs.append({**j, "tag": f"{j['seed']}-d{j['decision']}-{name}", "option": name,
                             "overrides": {str(j["decision"]): spec}})
        args.out.write_text(json.dumps(jobs, indent=1))
        print(f"{len(jobs)} control forks for {len(seen)} moments")
        return

    rng = random.Random(args.rng)
    rows = json.loads((args.base / "results.json").read_text())["games"]
    jobs = []
    for row in rows:
        gdir = args.base / "games" / str(row.get("tag", row["seed"]))
        if gdir.exists():
            jobs += game_jobs(gdir, row, rng, args.survived, args.max_turn)
    if args.max_turn:
        jobs = [j for j in jobs if j["turn"] <= args.max_turn]
    jobs.sort(key=lambda j: (j["turn"], j["tag"]))
    if args.turn_budget:
        kept, spent = [], 0.0
        for j in jobs:
            spent += j["stop_turn"] / 1e6
            if spent > args.turn_budget:
                break
            kept.append(j)
        jobs = kept
    args.out.write_text(json.dumps(jobs, indent=1))
    by = {}
    for j in jobs:
        by[(j["class"], j["option"])] = by.get((j["class"], j["option"]), 0) + 1
    print(f"{len(jobs)} forks from {len({j['seed'] for j in jobs})} games, "
          f"{sum(j['stop_turn'] for j in jobs) / 1e6:.1f}M turns to replay")
    for key in sorted(by):
        print(f"  {key[0]:9} {key[1]:12} {by[key]}")


if __name__ == "__main__":
    main()
