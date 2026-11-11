"""Compare qw runs on the same seeds: the first run named is the baseline.

    uv run python tools/qw/compare.py qw-base-200 pol-r1-200 pol-hand-200
"""

from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "runs" / "qw"


def load(name: str) -> dict[int, dict]:
    games = json.loads((ROOT / name / "results.json").read_text())["games"]
    return {g["seed"]: g for g in games}


def measures(g: dict) -> dict[str, float]:
    xl = g.get("max_xl") or g.get("xl") or 0
    return {
        "xl": xl,
        "deepest D": g.get("deepest_d") or 0,
        "past D:5": float((g.get("deepest_d") or 0) > 5),
        "reached Lair": float(bool(g.get("reached_lair"))),
        "XL 12+": float(xl >= 12),
        "runes": g.get("runes") or 0,
        "won": float(g.get("ktyp") == "winning"),
    }


def main() -> None:
    names = sys.argv[1:]
    runs = {n: load(n) for n in names}
    base = runs[names[0]]
    for n in names:
        r = runs[n]
        seeds = sorted(set(r) & set(base))
        odd = sum(1 for s in seeds if r[s].get("status") != "done")
        print(f"\n{n}: {len(seeds)} seeds ({odd} not played to an end)")
        for key in measures(base[seeds[0]]):
            mine = [measures(r[s])[key] for s in seeds]
            line = f"  {key:13} {st.mean(mine):6.2f}"
            if n != names[0]:
                diff = [measures(r[s])[key] - measures(base[s])[key] for s in seeds]
                se = st.stdev(diff) / len(diff) ** 0.5
                line += (f"   vs {names[0]}: {st.mean(diff):+.2f} (se {se:.2f}), better on "
                         f"{sum(d > 0 for d in diff)}, worse on {sum(d < 0 for d in diff)}")
            print(line)


if __name__ == "__main__":
    main()
