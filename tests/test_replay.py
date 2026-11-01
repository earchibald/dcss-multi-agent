"""Replay a recorded game (seed 12345, Minotaur Berserker, D:1 → D:2) through state and detectors.

Each `input_mode` 1 message marks the end of one action, so the recording can be
cut into action-sized segments without knowing which keys were sent.
"""

import gzip
import json
from pathlib import Path

from ladder.interrupts import Before, Detector
from ladder.state import GameState

FIXTURE = Path(__file__).parent / "fixtures" / "seed12345_d1_d2.protocol.jsonl.gz"


def messages():
    with gzip.open(FIXTURE, "rt") as f:
        return [json.loads(line) for line in f]


def replay():
    state, det, found = GameState(), Detector(), []
    before = Before.capture(state)
    for msg in messages():
        state.apply(msg)
        if msg.get("msg") == "input_mode" and msg.get("mode") == 1:
            found += det.detect(before, state, "explore", None)
            before = Before.capture(state)
    return state, found


def test_final_state_matches_the_recorded_game():
    state, _ = replay()
    assert state.place == "D:2"
    assert state.player["species"] == "Minotaur" and state.player["god"] == "Trog"
    assert state.player["xl"] == 3
    assert state.hostiles() == []          # the last rat is remembered, not in view
    assert any(c.get("mon") is not None for c in state.cells.values())


def test_detectors_find_the_known_events():
    _, found = replay()
    kinds = {i.kind for i in found}
    assert {"level_change", "hostile_in_view", "item_in_view", "status_change", "xl_up"} <= kinds
    uniques = [i for i in found if i.decision_type == "engage_unique"]
    assert any(m["name"] == "Natasha" for i in uniques for m in i.detail["monsters"])
    poisoned = [i for i in found if i.kind == "status_change"]
    assert any("Pois" in i.detail["added"] for i in poisoned)
