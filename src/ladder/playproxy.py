"""A recording proxy in front of webtiles, for the player's own games.

A spectator sees the game but not the keys (spectate.py), so it can't tell what the player meant.
Playing through this proxy, the player's browser loads webtiles from it and talks to webtiles
through it. The proxy forwards the page and the socket unchanged, and it writes the game's messages
and the player's keys, in the order they passed, to `runs/<dir>/play<n>.jsonl`: each key sits
between the game state it answered and the state that came back.

One line per message: {"t": seconds since the game started, "from": "game" | "player", "msg": ...}.
The first line is {"from": "proxy", "msg": {"msg": "session", "user", "started"}}.

From the player only keys are kept ("key" and "input"): logins, login tokens and chat never reach
the file, and neither does webtiles' "login_cookie" reply. Webtiles renders its socket address from
the page's Host, so a page loaded from the proxy talks through it. The proxy listens on
127.0.0.1 and takes only its own Host and Origin, so another site can't drive it.

Handing back from the cockpit hangs up the player's sockets here (`hang_up`), so webtiles saves the
game at once and the bot can pick it up.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.http11 import Response
from websockets.sync.client import connect
from websockets.sync.server import serve

from .spectate import unbundle

FROM_PLAYER = {"key", "input"}           # the player's messages worth keeping: keys
NEVER = {"login_cookie"}                 # webtiles' messages that carry a login token
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
       "transfer-encoding", "upgrade", "content-length"}


def next_play(record_dir: Path) -> Path:
    n = 1
    while (path := record_dir / f"play{n}.jsonl").exists():
        n += 1
    return path


class Session:
    """One browser socket: records from webtiles' game_started until the game ends or the socket closes."""

    def __init__(self, record_dir: Callable[[], Path], on_event: Callable[..., None]):
        self.record_dir = record_dir
        self.on_event = on_event
        self.lock = threading.Lock()
        self.user: str | None = None
        self.file = None
        self.path: Path | None = None
        self.t0 = 0.0

    def from_game(self, raw: str | bytes) -> None:
        if not isinstance(raw, str):
            return
        for msg in unbundle(raw):
            kind = msg.get("msg")
            if kind == "login_success":
                self.user = msg.get("username")
            elif kind == "game_started":
                self._open()
            if kind not in NEVER:
                self._write("game", msg)
            if kind in ("game_ended", "go_lobby"):
                self.close()

    def from_player(self, raw: str | bytes) -> None:
        if not isinstance(raw, str):
            return
        try:
            msg = json.loads(raw)
        except ValueError:
            return
        if isinstance(msg, dict) and msg.get("msg") in FROM_PLAYER:
            self._write("player", msg)

    def _open(self) -> None:
        with self.lock:
            if self.file is not None:
                return
            directory = self.record_dir()
            directory.mkdir(parents=True, exist_ok=True)
            self.path = next_play(directory)
            self.file = open(self.path, "w")
            self.t0 = time.monotonic()
            self.file.write(json.dumps({"t": 0, "from": "proxy", "msg": {
                "msg": "session", "user": self.user,
                "started": datetime.now().astimezone().isoformat(timespec="seconds")}}) + "\n")
        self.on_event("player_keys", state="recording", user=self.user, record=str(self.path))

    def _write(self, side: str, msg: dict) -> None:
        with self.lock:
            if self.file is not None:
                self.file.write(json.dumps({"t": round(time.monotonic() - self.t0, 3), "from": side,
                                            "msg": msg}) + "\n")

    def close(self) -> None:
        with self.lock:
            if self.file is None:
                return
            self.file.close()
            self.file = None
        self.on_event("player_keys", state="saved", user=self.user, record=str(self.path))


class PlayProxy:
    """Serves webtiles at http://127.0.0.1:<port>/ and records the games played through it."""

    def __init__(self, server: str, port: int, record_dir: Callable[[], Path],
                 on_event: Callable[..., None] = lambda ev, **data: None):
        self.upstream_ws = server
        parts = urlsplit(server)
        self.upstream = (parts.hostname or "localhost", parts.port or (443 if parts.scheme == "wss" else 80))
        self.https = parts.scheme == "wss"
        self.port = port
        self.record_dir = record_dir
        self.on_event = on_event
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.server = None
        self.lock = threading.Lock()
        self.relays: dict = {}           # browser socket -> (Session, upstream socket)

    def start(self) -> "PlayProxy":
        # Browsers that can inflate ask for no subprotocol, the rest for "no-compression". Either way the
        # proxy sends text: webtiles' client reads text frames whichever it asked for.
        self.server = serve(self._relay, "127.0.0.1", self.port, process_request=self._http,
                            select_subprotocol=lambda ws, offered: "no-compression" if "no-compression" in offered else None,
                            max_size=None)
        self.port = self.server.socket.getsockname()[1]
        self.hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        threading.Thread(target=self.server.serve_forever, name="play-proxy", daemon=True).start()
        return self

    def close(self) -> None:
        if self.server is not None:
            self.server.shutdown()

    def hang_up(self, user: str) -> int:
        """End `user`'s games played through the proxy: webtiles saves a game when its player's socket
        closes. Returns how many sockets were closed."""
        with self.lock:
            mine = [(b, up) for b, (session, up) in self.relays.items()
                    if (session.user or "").lower() == user.lower()]
        for browser, upstream in mine:
            upstream.close()
            browser.close(1000, "handed back to the bot")
        return len(mine)

    def _http(self, connection, request) -> Response | None:
        if request.headers.get("Host") not in self.hosts:
            return connection.respond(403, "wrong host\n")
        if urlsplit(request.path).path == "/socket":
            if request.headers.get("Origin") not in {f"http://{h}" for h in self.hosts}:
                return connection.respond(403, "wrong origin\n")
            return None                                  # go on to the websocket handshake
        return self._forward(connection, request)

    def _forward(self, connection, request) -> Response:
        cls = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
        up = cls(*self.upstream, timeout=30)
        try:
            # Host goes through as the browser sent it: webtiles builds the socket address from it.
            headers = {k: v for k, v in request.headers.raw_items() if k.lower() not in HOP}
            up.request("GET", request.path, headers=headers)
            r = up.getresponse()
            body = r.read()
        except OSError as e:
            return connection.respond(502, f"webtiles didn't answer: {e}\n")
        finally:
            up.close()
        out = Headers([(k, v) for k, v in r.getheaders() if k.lower() not in HOP])
        out["Content-Length"] = str(len(body))
        out["Connection"] = "close"
        return Response(r.status, r.reason, out, body)

    def _relay(self, browser) -> None:
        session = Session(lambda: Path(self.record_dir()), self.on_event)
        try:
            upstream = connect(self.upstream_ws, subprotocols=["no-compression"], max_size=None, open_timeout=10)
        except (OSError, TimeoutError, WebSocketException):
            browser.close(1011, "webtiles didn't answer")
            return

        def down() -> None:
            try:
                for raw in upstream:
                    session.from_game(raw)      # before forwarding: a key can't be written ahead of what it answered
                    browser.send(raw)
            except ConnectionClosed:
                pass
            finally:
                browser.close()

        threading.Thread(target=down, name="play-proxy-down", daemon=True).start()
        with self.lock:
            self.relays[browser] = (session, upstream)
        try:
            for raw in browser:
                session.from_player(raw)
                upstream.send(raw)
        except ConnectionClosed:
            pass
        finally:
            with self.lock:
                self.relays.pop(browser, None)
            upstream.close()
            session.close()
