"""tools/qw/chain.py (the chain file) and tools/qw/peek.py (playing or stuck)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools" / "qw"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"qw_{name}", TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


chain = load("chain")
peek = load("peek")


def test_chain_parse_folds_common_into_runs():
    steps = chain.parse(
        "# a comment\n"
        "common --no-build --time-limit 60\n"
        "\n"
        "run --seeds 1-2 --name a   # trailing comment\n"
        "wait other\n"
        "compare base a\n"
    )
    assert steps == [
        ("run", ["--no-build", "--time-limit", "60", "--seeds", "1-2", "--name", "a"]),
        ("wait", ["other"]),
        ("compare", ["base", "a"]),
    ]
    assert chain.run_name(steps[0][1]) == "a"


@pytest.mark.parametrize("text", [
    "play --name a\n",  # unknown step
    "run --seeds 1-2\n",  # no name
    "run --name a --slots /tmp/x\n",  # the chain owns --slots
    "run --name a\nrun --name a\n",  # duplicate
    "compare\n",
])
def test_chain_parse_rejects(text):
    with pytest.raises(SystemExit):
        chain.parse(text)


NOW = 10_000.0


def game(**over) -> dict:
    g = {"seed": 1, "worker": 1, "started": NOW - 600, "last_line": NOW - 1, "turn": 5000,
         "turn_changed": NOW - 1, "place": "D:5", "xl": 8, "hp": 50, "mhp": 60,
         "turns_on_level": 300, "decisions": 900, "in_decision_since": None,
         "turns_60s": 4000, "turns_300s": 9000,
         "recent": [[5000 + i, "D:5", 50, ["explore", "attack", "rest", "stairs"][i % 4]]
                    for i in range(200)]}
    g.update(over)
    return g


def test_verdict_playing():
    assert peek.verdict(game(), NOW)[0] == "playing"


def test_verdict_hung_names_the_open_decision():
    v, why = peek.verdict(game(last_line=NOW - 90, in_decision_since=NOW - 90), NOW)
    assert v == "hung" and "inside a decision" in why


def test_verdict_frozen_when_turn_stops_but_output_flows():
    assert peek.verdict(game(turn_changed=NOW - 120), NOW)[0] == "frozen"


def test_verdict_circling_needs_long_stay_and_few_plans():
    loop = [[5000 + i, "D:9", 50, "explore"] for i in range(200)]
    assert peek.verdict(game(recent=loop, turns_on_level=8000), NOW)[0] == "circling"
    # A short stay, or varied plans, is ordinary play.
    assert peek.verdict(game(recent=loop, turns_on_level=400), NOW)[0] == "playing"
    assert peek.verdict(game(turns_on_level=8000), NOW)[0] == "playing"


def test_rows_sort_worst_first():
    doc = {"name": "r", "time_limit_s": 3600, "games": [
        game(seed=1), game(seed=2, last_line=NOW - 90), game(seed=3, turn_changed=NOW - 120)]}
    assert [r["seed"] for r in peek.rows([doc], NOW)] == [2, 3, 1]
