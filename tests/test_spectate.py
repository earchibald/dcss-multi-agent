"""The spectator against a fake webtiles: waits for the user's game in the lobby, follows it, records it."""

import json
import queue
import threading

import pytest
from websockets.sync.server import serve

from ladder.spectate import Spectator, unbundle

PLAYER = {"msg": "player", "hp": 20, "hp_max": 24, "turn": 70, "depth": 1, "place": "Dungeon", "xl": 3,
          "pos": {"x": 1, "y": 1}}


def bundle(*msgs):
    return json.dumps({"msgs": list(msgs)})


def test_unbundle_takes_bundles_and_single_messages():
    assert unbundle(bundle({"msg": "ping"}, {"msg": "pong"})) == [{"msg": "ping"}, {"msg": "pong"}]
    assert unbundle('{"msg": "msgs", "messages": []}') == [{"msg": "msgs", "messages": []}]


@pytest.fixture
def webtiles():
    """One game of laddertest's: listed in the lobby after a moment, then watched, then ended."""
    asked = queue.Queue()

    def handler(ws):
        assert ws.subprotocol == "no-compression"
        ws.send(bundle({"msg": "ping"}))
        assert json.loads(ws.recv()) == {"msg": "pong"}
        ws.send(bundle({"msg": "lobby_clear"}, {"msg": "lobby_entry", "id": 1, "username": "someone"},
                       {"msg": "lobby_complete"}))
        ws.send(bundle({"msg": "lobby_entry", "id": 2, "username": "LadderTest"}))
        asked.put(json.loads(ws.recv()))
        ws.send(bundle({"msg": "watching_started", "username": "laddertest"}, PLAYER,
                       {"msg": "msgs", "messages": [{"text": "You hit the <red>rat</red>.", "turn": 70}]}))
        ws.send(bundle({**PLAYER, "hp": 3, "turn": 75}))
        ws.send(bundle({"msg": "game_ended", "reason": "saved"}, {"msg": "go_lobby"}))
        try:
            ws.recv()                  # until the spectator hangs up
        except Exception:
            pass

    with serve(handler, "127.0.0.1", 0, subprotocols=["no-compression"]) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"ws://127.0.0.1:{server.socket.getsockname()[1]}/socket", asked
        server.shutdown()


def test_follows_the_users_game_and_records_it(webtiles, tmp_path):
    url, asked = webtiles
    statuses, events, ended = [], [], threading.Event()

    def on_event(ev, **data):
        events.append((ev, data))
        if data["state"] == "ended":
            ended.set()

    sp = Spectator(url, "laddertest", statuses.append, on_event, record_dir=tmp_path, every=0.01)
    sp.start()
    try:
        assert ended.wait(5)
    finally:
        sp.stop()
    assert asked.get_nowait() == {"msg": "watch", "username": "laddertest"}
    assert [e[1]["state"] for e in events] == ["watching", "ended"]
    assert events[0][1]["record"] == str(tmp_path / "player1.protocol.jsonl")
    assert events[1][1]["reason"] == "saved" and not events[1][1]["died"]
    assert events[1][1]["snapshot"]["turn"] == 75
    assert statuses[-1]["player"] and statuses[-1]["snapshot"]["hp"] == 3
    assert "You hit the rat." in statuses[0]["messages"] + statuses[-1]["messages"]
    lines = (tmp_path / "player1.protocol.jsonl").read_text().splitlines()
    assert [json.loads(line)["msg"] for line in lines] == ["player", "msgs", "player"]
