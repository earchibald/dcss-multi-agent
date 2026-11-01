"""Live tests against the webtiles server: `docker compose up -d`, then `uv run pytest -m integration`.

They use their own account ("laddertest"); its password is created in Keychain on first run.
"""

import json
from pathlib import Path

import pytest

from ladder.cli import crawlrc
from ladder.conn import Connection
from ladder.reflex import Reflex
from ladder.runlog import RunLog
from ladder.state import GameState

pytestmark = pytest.mark.integration
SCENARIOS = Path(__file__).parent / "scenarios"
USER = "laddertest"


@pytest.fixture
def game():
    state = GameState()
    conn = Connection(on_message=state.apply)
    conn.login(USER)
    conn.set_rc(crawlrc())
    yield conn, state
    if not state.dead:
        conn.quit_game()
    conn.close()


def test_scenario_room_raises_the_expected_interrupts(game, tmp_path):
    conn, state = game
    conn.start_scenario(SCENARIOS / "kobold_room.yaml", "b", "f", "b")
    log = RunLog(tmp_path)
    reflex = Reflex(conn, state, log)

    first = reflex.step("explore")
    by_kind = {i.kind: i for i in first}
    assert "hostile_in_view" in by_kind
    assert [m["name"] for m in by_kind["hostile_in_view"].detail["monsters"]] == ["kobold"]
    assert "item_in_view" in by_kind

    for _ in range(20):                    # the stub fights until the kobold is gone
        if not state.hostiles():
            break
        reflex.step("fight")
    assert state.hostiles() == []
    log.close()
    records = [json.loads(line) for line in (log.dir / "interrupts.jsonl").open()]
    assert all(r["snapshot"]["place"] == "D:1" for r in records)


def test_seeded_reflex_run_walks_stops_and_logs(game, tmp_path):
    conn, state = game
    conn.start_game("b", "f", "b", seed=12345)
    log = RunLog(tmp_path)
    result = Reflex(conn, state, log).run(max_steps=60)
    summary = log.close()

    assert result["steps"] > 10
    assert result["turns"] > 50
    assert summary["interrupts_total"] > 5
    assert summary["by_source"].get("dcss", 0) > 0
    assert {"item_in_view", "hostile_in_view"} <= set(summary["by_kind"])
