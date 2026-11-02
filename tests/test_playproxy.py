"""The recording proxy against a fake webtiles: forwards page and socket, records keys, never secrets."""

import json
import threading
import urllib.request
from urllib.error import HTTPError

import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect
from websockets.sync.server import serve

from ladder.playproxy import PlayProxy

PLAYER = {"msg": "player", "hp": 20, "hp_max": 24, "turn": 70, "place": "Dungeon", "depth": 1}


def bundle(*msgs):
    return json.dumps({"msgs": list(msgs)})


@pytest.fixture
def webtiles():
    """Logs in by token, starts a game on "play", and answers each key with a new turn."""
    def page(connection, request):
        if request.path != "/socket":
            return connection.respond(200, f"client.html for {request.headers['Host']}\n")
        return None

    def game(ws):
        turn = 70
        for raw in ws:
            msg = json.loads(raw)
            if msg["msg"] == "token_login":
                ws.send(bundle({"msg": "login_success", "username": "laddertest"}))
            elif msg["msg"] == "play":
                ws.send(bundle({"msg": "game_started"}, {**PLAYER, "turn": turn}))
            elif msg["msg"] in ("key", "input"):
                turn += 1
                ws.send(bundle({**PLAYER, "turn": turn}))
            elif msg["msg"] == "set_login_cookie":
                ws.send(bundle({"msg": "login_cookie", "cookie": "laddertest%20NEWTOKEN", "expires": 7}))

    with serve(game, "127.0.0.1", 0, process_request=page, subprotocols=["no-compression"]) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"ws://127.0.0.1:{server.socket.getsockname()[1]}/socket"
        server.shutdown()


@pytest.fixture
def proxy(webtiles, tmp_path):
    events = []
    p = PlayProxy(webtiles, 0, lambda: tmp_path, on_event=lambda ev, **d: events.append((ev, d))).start()
    yield p, events, tmp_path
    p.close()


def test_page_comes_from_webtiles_with_the_proxys_host(proxy):
    p, _, _ = proxy
    with urllib.request.urlopen(f"http://127.0.0.1:{p.port}/") as r:
        assert r.read().decode() == f"client.html for 127.0.0.1:{p.port}\n"


def test_refuses_other_hosts_and_other_sites_sockets(proxy):
    p, _, _ = proxy
    req = urllib.request.Request(f"http://127.0.0.1:{p.port}/", headers={"Host": "evil.example"})
    with pytest.raises(HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 403
    with pytest.raises(InvalidStatus):
        connect(f"ws://127.0.0.1:{p.port}/socket", origin="http://evil.example")


def test_records_keys_between_game_states_and_never_tokens(proxy):
    p, events, tmp_path = proxy
    with connect(f"ws://127.0.0.1:{p.port}/socket", origin=f"http://127.0.0.1:{p.port}") as ws:
        play(ws)
        assert p.hang_up("LadderTest") == 1      # handing back from the cockpit
        with pytest.raises(ConnectionClosed):
            ws.recv(timeout=5)
    for _ in range(50):                          # the relay thread finishes closing the file
        if any(d["state"] == "saved" for _, d in events):
            break
        threading.Event().wait(0.05)

    path = tmp_path / "play1.jsonl"
    text = path.read_text()
    assert "SECRET" not in text and "NEWTOKEN" not in text and "token_login" not in text
    lines = [json.loads(line) for line in text.splitlines()]
    assert lines[0]["msg"]["msg"] == "session" and lines[0]["msg"]["user"] == "laddertest"
    flow = [(x["from"], x["msg"]["msg"], x["msg"].get("turn")) for x in lines[1:]]
    assert flow == [("game", "game_started", None), ("game", "player", 70), ("player", "key", None),
                    ("game", "player", 71), ("player", "input", None), ("game", "player", 72)]
    assert [d["state"] for ev, d in events if ev == "player_keys"] == ["recording", "saved"]
    assert p.hang_up("laddertest") == 0


def play(ws):
    """Log in by token, start the game, press two keys, ask for a fresh login cookie."""
    ws.send(json.dumps({"msg": "token_login", "cookie": "laddertest%20SECRET"}))
    assert json.loads(ws.recv())["msgs"][0]["msg"] == "login_success"
    ws.send(json.dumps({"msg": "play", "game_id": "dcss-0.34"}))
    ws.recv()
    ws.send('{"msg":"key","keycode":1}')
    ws.recv()
    ws.send(json.dumps({"msg": "input", "text": "h"}))
    ws.recv()
    ws.send(json.dumps({"msg": "set_login_cookie"}))
    assert "NEWTOKEN" in ws.recv()                 # the browser still gets its cookie
