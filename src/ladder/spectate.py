"""Follow the player's game as an anonymous webtiles spectator, and record it.

While the player has the wheel the bot's game process is gone, so the cockpit would go blind.
`Spectator` watches the user's games from the lobby instead: it folds what webtiles sends
spectators into a `GameState`, so the cockpit's Game panel keeps up, and writes every message to
`player<n>.protocol.jsonl` in the run directory, the same format as a bot game's `--record`, so the
player's games are kept to learn from.

It speaks the webtiles protocol itself rather than through dcss-api: dcss-api's reads block with
no timeout and hold the GIL, and a spectator has to notice when there is nothing to watch.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from .state import GameState


def unbundle(raw: str | bytes) -> list[dict]:
    """Webtiles sends `{"msgs": [...]}` bundles; older servers send one message per frame."""
    data = json.loads(raw)
    if "msg" not in data and isinstance(data.get("msgs"), list):
        return data["msgs"]
    return [data]


def next_record(record_dir: Path) -> Path:
    n = 1
    while (path := record_dir / f"player{n}.protocol.jsonl").exists():
        n += 1
    return path


class Spectator:
    """Watches `user`'s games while `stop()` hasn't been called, reconnecting when the server drops."""

    def __init__(self, url: str, user: str, on_status: Callable[[dict], None],
                 on_event: Callable[..., None], record_dir: Path | None = None,
                 every: float = 0.25, retry: float = 2.0):
        self.url = url
        self.user = user
        self.on_status = on_status
        self.on_event = on_event
        self.record_dir = record_dir
        self.every = every              # seconds between status updates
        self.retry = retry
        self.stopped = threading.Event()
        self.ws = None
        self.state: GameState | None = None
        self.record = None
        self.dirty = False
        self.published = 0.0

    def start(self) -> Callable[[], None]:
        threading.Thread(target=self.run, name="spectate", daemon=True).start()
        return self.stop

    def stop(self) -> None:
        self.stopped.set()
        if self.ws is not None:
            self.ws.close()

    def run(self) -> None:
        while not self.stopped.is_set():
            try:
                with connect(self.url, subprotocols=["no-compression"], open_timeout=10,
                             max_size=None) as ws:
                    self.ws = ws
                    if self.stopped.is_set():
                        return
                    self._session(ws)
            except (OSError, TimeoutError, WebSocketException):
                pass
            finally:
                self._end("stopped following" if self.stopped.is_set() else "lost the connection to webtiles")
            self.stopped.wait(self.retry)

    def _session(self, ws) -> None:
        asked = False
        while not self.stopped.is_set():
            try:
                raw = ws.recv(timeout=self.every)
            except TimeoutError:
                self._publish()
                continue
            for msg in unbundle(raw):
                kind = msg.get("msg")
                if kind == "ping":
                    ws.send(json.dumps({"msg": "pong"}))     # webtiles hangs up on a client that doesn't
                elif self.state is not None:
                    if kind in ("game_ended", "go_lobby"):
                        self._end(msg.get("reason") or "left the game")
                        asked = False
                    else:
                        self._apply(msg)
                elif kind == "watching_started":
                    self._begin()
                elif kind == "lobby_entry" and not asked and msg.get("username", "").lower() == self.user.lower():
                    ws.send(json.dumps({"msg": "watch", "username": self.user}))
                    asked = True
                elif kind == "go_lobby":
                    asked = False       # the game ended before we got in; wait for the next one
            self._publish()

    def _begin(self) -> None:
        self.state = GameState()
        path = None
        if self.record_dir is not None:
            self.record_dir.mkdir(parents=True, exist_ok=True)
            path = next_record(self.record_dir)
            self.record = open(path, "w")
        self.on_event("player_game", state="watching", user=self.user, record=str(path) if path else None)

    def _apply(self, msg: dict) -> None:
        self.state.apply(msg)
        if self.record is not None:
            self.record.write(json.dumps(msg) + "\n")
        self.dirty = True

    def _publish(self, force: bool = False) -> None:
        if not self.dirty or self.state is None or not self.state.player:
            return
        now = time.monotonic()
        if not force and now - self.published < self.every:
            return
        self.dirty, self.published = False, now
        self.on_status({"game": None, "step": None, "action": None, "player": True,
                        "snapshot": self.state.snapshot(), "messages": self.state.recent_messages(5),
                        "msg_total": len(self.state.messages)})

    def _end(self, reason: str) -> None:
        if self.state is None:
            return
        self._publish(force=True)
        snapshot = self.state.snapshot() if self.state.player else None
        died = self.state.dead
        self.state = None
        if self.record is not None:
            self.record.close()
            self.record = None
        self.on_event("player_game", state="ended", user=self.user, reason=reason, died=died,
                      snapshot=snapshot)
