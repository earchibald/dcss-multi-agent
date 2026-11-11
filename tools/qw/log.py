"""Read a qw game log (games/<tag>/stderr.log[.gz] from tools/qw/run.py), one dict per decision.

    from log import read_decisions
    for d in read_decisions("runs/qw/forks1/games/500000-tele-812"):
        d["decision"], d["state"]["hp"], d["action"], d["override"]

    uv run python tools/qw/log.py runs/qw/NAME/games/TAG [--head 5]    # quick look

Each dict:
  decision   qw's decision index (0-based, the same on every replay of a seed)
  state      the QWS fields (numbers as int/float, flags 0/1 as int, text as str), with
             the up-to-5 nearest enemies also gathered into state["enemies"] (list of dicts
             with keys name, dist, threat, ranged, move_delay, damage_level, sleeping,
             wandering, summoned, hasted, berserk); {} if the game ran without --state-log
  action     the plan path that acted, outermost first ("emergency>berserk",
             "force:teleport"; "" if nothing acted)
  turn, place, hp, mhp   from the QWACT line (after the action)
  override   None, or {"spec": "force=teleport n=1", "acted": True}; choke and
             stairs_fight add phase, attackers_here, attackers_choke, choke_dist (a list if the
             decision carried two, e.g. a force that did not act and a veto)
Decisions whose QWACT line is missing (the game ended or errored mid-decision) are
yielded with action None.
"""

from __future__ import annotations

import gzip
import sys
from collections.abc import Iterator
from pathlib import Path

ENEMY_FIELDS = ("name", "dist", "threat", "ranged", "move_delay", "damage_level",
                "sleeping", "wandering", "summoned", "hasted", "berserk")


def _value(v: str):
    if v == "":
        return ""
    if v == "nan":  # e.g. enemy_move_delay with no enemies (0/0 in qw)
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def _open(path: Path):
    path = Path(path)
    if path.is_dir():
        for name in ("stderr.log.gz", "stderr.log"):
            if (path / name).exists():
                path = path / name
                break
        else:
            raise FileNotFoundError(f"no stderr.log[.gz] in {path}")
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, encoding="utf-8", errors="replace")


def parse_state(fields: list[str]) -> dict:
    state: dict = {}
    for f in fields:
        k, _, v = f.partition("=")
        state[k] = _value(v)
    enemies = []
    for i in range(1, 6):
        if not state.get(f"e{i}_name"):
            break
        enemies.append({k: state.get(f"e{i}_{k}") for k in ENEMY_FIELDS})
    state["enemies"] = enemies
    return state


def read_decisions(path) -> Iterator[dict]:
    """Yield one dict per decision from a game's log file or game directory."""
    current: dict | None = None
    with _open(path) as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            tag = parts[0]
            if tag not in ("QWS", "QWOVR", "QWACT"):
                continue
            idx = int(parts[1])
            if current is not None and current["decision"] != idx:
                yield current
                current = None
            if current is None:
                current = {"decision": idx, "state": {}, "action": None, "turn": None,
                           "place": None, "hp": None, "mhp": None, "override": None}
            if tag == "QWS":
                current["state"] = parse_state(parts[2:])
            elif tag == "QWOVR":
                ovr = {"spec": parts[2], "acted": parts[3] == "1"}
                # choke / stairs_fight add "phase=... attackers_here=N ..." fields
                if len(parts) > 4:
                    for f in parts[4].split():
                        k, _, v = f.partition("=")
                        ovr[k] = _value(v)
                prev = current["override"]
                current["override"] = ovr if prev is None else (
                    prev + [ovr] if isinstance(prev, list) else [prev, ovr])
            else:  # QWACT
                current.update(turn=int(parts[2]), place=parts[3], hp=int(parts[4]),
                               mhp=int(parts[5]),
                               action=parts[6] if len(parts) > 6 else "")
                yield current
                current = None
    if current is not None:
        yield current


def main() -> None:
    import argparse
    import json

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", type=Path, help="game directory or stderr.log[.gz]")
    ap.add_argument("--head", type=int, default=3, help="print the first N decisions")
    args = ap.parse_args()
    n = 0
    actions: dict[str, int] = {}
    for d in read_decisions(args.path):
        if n < args.head:
            print(json.dumps(d))
        n += 1
        actions[d["action"] or ""] = actions.get(d["action"] or "", 0) + 1
    print(f"{n} decisions", file=sys.stderr)
    for a, c in sorted(actions.items(), key=lambda kv: -kv[1])[:10]:
        print(f"{c:7d} {a}", file=sys.stderr)


if __name__ == "__main__":
    main()
