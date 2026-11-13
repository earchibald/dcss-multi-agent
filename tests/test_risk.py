"""The death-risk dataset's labels and censoring (tools/risk/dataset.py)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "risk"))

from dataset import label, labels, qw_died  # noqa: E402


def test_a_death_labels_every_row():
    turns = [0, 100, 149, 150, 199, 200]
    # died at turn 200: rows within 50 turns of it are 1, earlier rows are known 0
    assert label(turns, 200, True, 50).tolist() == [0, 0, 0, 1, 1, 1]


def test_a_censored_game_has_unknown_last_turns():
    turns = [0, 100, 149, 150, 151, 200]
    # quit, timed out or stopped at turn 200: alive then, so rows 50+ turns before it are 0, later unknown
    assert label(turns, 200, False, 50).tolist() == [0, 0, 0, 0, -1, -1]


def test_a_censored_game_is_never_a_death():
    for horizon in (1, 50, 200, 10_000):
        assert (label(np.arange(0, 1000, 7), 1000, False, horizon) != 1).all()


def test_vectorised_labels_match():
    rng = np.random.default_rng(0)
    turn = rng.integers(0, 5000, 2000).astype(np.float64)
    end = turn + rng.integers(0, 600, 2000)
    died = rng.random(2000) < 0.5
    meta = {"turn": turn, "end_turn": end, "died": died}
    for h in (50, 200):
        want = [label([t], e, d, h)[0] for t, e, d in zip(turn, end, died)]
        assert labels(meta, h).tolist() == want


def test_qw_endings():
    assert qw_died({"status": "done", "ktyp": "mon"})
    assert qw_died({"status": "done", "ktyp": "pois"})
    assert not qw_died({"status": "done", "ktyp": "quitting"})
    assert not qw_died({"status": "done", "ktyp": "winning"})
    assert not qw_died({"status": "stopped", "ktyp": None})       # a fork at its horizon
    assert not qw_died({"status": "timeout", "ktyp": None})
    assert not qw_died({"status": "error_loop", "ktyp": "mon"})   # the runner's word, not the game's
