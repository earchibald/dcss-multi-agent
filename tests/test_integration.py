"""Live tests against the webtiles server: `docker compose up -d`, then `uv run pytest -m integration`.

They use their own account ("laddertest"); its password is created in Keychain on first run.
"""

import json
from pathlib import Path

import pytest

from ladder.games import crawlrc
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


def test_caught_in_a_web_reflex_struggles_free(game, tmp_path):
    """Tab only says "You are caught in a web!"; a move struggles. Run 20261101-175256 ended there."""
    conn, state = game
    conn.start_scenario(SCENARIOS / "ribbon_worms.yaml", "b", "f", "b")
    reflex = Reflex(conn, state, RunLog(tmp_path))
    caught_at, freed = None, False
    for _ in range(15):
        if state.caught and caught_at is None:
            caught_at = state.turn
        if caught_at is not None and not state.caught:
            freed = True
            break
        action = reflex.stub.next_action(state)
        if state.caught:
            assert action == "struggle"
        before = state.turn
        reflex.step(action)
        if action == "struggle":
            assert state.turn > before                # struggling takes a turn: no "no progress"
    assert caught_at is not None, "the ribbon worms never webbed us"
    assert freed


def test_seeded_run_visits_the_shop_greedy_explore_would_hang_in(game, tmp_path):
    """Seed 777's explore walks into Doito's Book Boutique at turn 39. Opened by explore, the shop
    menu sends no input_mode and act() waits forever, so Reflex visits shops itself first."""
    import faulthandler
    conn, state = game
    conn.start_game("b", "f", "b", seed=777)
    reflex = Reflex(conn, state, RunLog(tmp_path))
    faulthandler.dump_traceback_later(120, exit=True)   # a regression hangs: fail loudly instead
    try:
        reflex.run(max_steps=20)
    finally:
        faulthandler.cancel_dump_traceback_later()
    assert reflex.stub.shops_seen and state.turn > 39
