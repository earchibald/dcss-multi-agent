"""Connection to the DCSS webtiles server through dcss-api.

dcss-api's Python binding raises BlockingErr only for pickup menus; every other
blocking condition arrives as APIErr with a fixed message. `classify_error`
turns both into a short reason string the rest of the ladder can act on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, TextIO

import dcss_api

from . import keychain

DEFAULT_URL = "ws://localhost:8080/socket"
GAME_ID = "dcss-0.34"

# (substring of dcss-api's error text, reason)
_ERROR_REASONS = [
    ("'more' message", "more"),
    ("text input", "text_input"),
    ("Character died", "died"),
    ("pickup", "pickup"),
    ("'acquirement'", "acquirement"),
    ("'identify'", "identify"),
    ("'enchant weapon'", "enchant_weapon"),
    ("'brand item'", "enchant_item"),
    ("'brand weapon'", "brand_weapon"),
    ("skills to train", "skills"),
    ("'blink'", "blink"),
    ("'equipping'", "equipping"),
    ("'disrobing'", "disrobing"),
    ("scroll of noise", "noise"),
    ("seed selection", "seed_selection"),
    ("New game choice", "new_game_choice"),
]


def reply_modes(batch: list[dict]) -> list[int]:
    """The input modes in `batch` that answer our keys.

    When a spectator joins, DCSS resends its whole UI state to every socket, the
    player's included: a run that starts with `version` and ends with an
    `input_mode` re-announcing the prompt it already sent. That `input_mode` is
    not a reply. Taking it for one leaves every later act() a reply behind the
    game, which can't recover: the bot keeps acting on a stale picture.
    """
    modes, resend = [], False
    for m in batch:
        if m.get("msg") == "version":
            resend = True
        elif m.get("msg") == "input_mode":
            if resend:
                resend = False
            else:
                modes.append(m.get("mode"))
    return modes


def classify_error(exc: Exception) -> str:
    if isinstance(exc, dcss_api.BlockingErr):
        return str(exc).lower() or "pickup"
    text = str(exc)
    for needle, reason in _ERROR_REASONS:
        if needle.lower() in text.lower():
            return reason
    return "error:" + text


class LoginError(RuntimeError):
    pass


@dataclass
class ActResult:
    """What came back after sending keys and waiting for the game to want input."""
    blocking: str | None = None          # reason the game is waiting on something other than a command
    messages: list[dict] = field(default_factory=list)


class Connection:
    """One webtiles session. Feeds every received message to `on_message`."""

    def __init__(self, url: str = DEFAULT_URL, speed_ms: int = 20,
                 on_message: Callable[[dict], None] | None = None,
                 record: TextIO | None = None):
        self.url = url
        self.speed_ms = speed_ms
        self.on_message = on_message or (lambda m: None)
        self.record = record
        self.web = self._connect()

    def _connect(self):
        web = dcss_api.WebtilePy(self.url, self.speed_ms)
        self._drain(web, deliver=False)
        return web

    def _drain(self, web=None, deliver=True) -> list[dict]:
        web = web or self.web
        out = []
        while (raw := web.get_message()) is not None:
            msg = json.loads(raw)
            out.append(msg)
            if self.record is not None:
                self.record.write(raw + "\n")
            if deliver:
                self.on_message(msg)
        return out

    # --- lobby ---------------------------------------------------------

    def login(self, username: str) -> list[str]:
        """Log in with the Keychain password, registering the account on first use.

        Registering on the same socket after a failed login leaves the session
        unable to log in, so each step gets a fresh socket.
        """
        password, _ = keychain.get_or_create_dcss_password(username)
        try:
            return self._login(username, password)
        except dcss_api.APIErr:
            pass
        self.web.disconnect()
        self.web = self._connect()
        try:
            self.web.register_account(username, password, None)
        except dcss_api.APIErr as e:
            raise LoginError(
                f"Could not log in or register '{username}': {e}. If the server's data volume "
                "outlived the Keychain item, reset it with `docker compose down -v`."
            ) from e
        self.web.disconnect()
        self.web = self._connect()
        return self._login(username, password)

    def _login(self, username: str, password: str) -> list[str]:
        games = self.web.login_with_credentials(username, password)
        self._drain(deliver=False)
        return games

    def set_rc(self, content: str, game_id: str = GAME_ID) -> None:
        self.web.set_rc_file(game_id, content)
        self._drain(deliver=False)

    def start_game(self, species: str, background: str, weapon: str,
                   game_id: str = GAME_ID, seed: int | None = None) -> list[dict]:
        if seed is None:
            self.web.start_game(game_id, species, background, weapon)
        else:
            self.web.start_game_seeded(game_id, str(seed), False, species, background, weapon)
        return self._settle(self._drain())

    def start_scenario(self, yaml_path: str | Path, species: str, background: str, weapon: str,
                       game_id: str = GAME_ID) -> list[dict]:
        self.web.start_game_with_scenario(game_id, species, background, weapon, str(yaml_path))
        return self._settle(self._drain())

    def _settle(self, messages: list[dict]) -> list[dict]:
        """Make sure the game's first command prompt has been consumed.

        dcss-api returns at the first map message. A new game's prompt arrives in the
        same batch; a resumed game's arrives later. Waiting when it already came would
        block forever, and not waiting when it hasn't would leave every later act()
        one prompt behind.
        """
        if any(m.get("msg") == "input_mode" and m.get("mode") == 1 for m in messages):
            return messages
        return messages + self.sync().messages

    def quit_game(self) -> None:
        try:
            self.web.quit_game()
        except (dcss_api.APIErr, dcss_api.BlockingErr):
            pass
        self._drain()

    def close(self) -> None:
        try:
            self.web.disconnect()
        except dcss_api.APIErr:
            pass

    # --- play ----------------------------------------------------------

    def act(self, *keys: str, max_reads: int = 40) -> ActResult:
        """Send keys, then wait until the game asks for a command again.

        Waits on any `input_mode` message rather than only mode 1 (command
        input): a menu opens with mode 0 and never reaches mode 1, and waiting
        for 1 there blocks forever. `--more--` prompts are dismissed here; any
        other prompt or menu is returned to the caller unanswered. A spectator's
        state resend is read past (see `reply_modes`) when keys were sent; a
        bare sync takes whatever prompt comes.
        """
        result = ActResult()
        for key in keys:
            self.web.write_key(key)
        for _ in range(max_reads):
            try:
                self.web.read_until("input_mode")
                reason = None
            except (dcss_api.APIErr, dcss_api.BlockingErr) as e:
                reason = classify_error(e)
            batch = self._drain()
            result.messages += batch
            if reason == "more":
                self.web.write_key("key_enter")
                continue
            if reason:
                result.blocking = reason
                break
            modes = (reply_modes(batch) if keys
                     else [m.get("mode") for m in batch if m.get("msg") == "input_mode"])
            if modes and modes[-1] == 1:
                break
            if any(m.get("msg") in ("menu", "ui-push") for m in batch):
                result.blocking = "menu"
                break
        return result

    def open_menu(self, *keys: str) -> ActResult:
        """Send keys that open a menu (entering a shop), and wait for the menu itself.

        A menu sends no input_mode of its own, so act() would wait forever for one.
        Only call this when the keys are certain to open a menu: this read has no timeout either.
        """
        for key in keys:
            self.web.write_key(key)
        self.web.read_until("menu")
        return ActResult(blocking="menu", messages=self._drain())

    def sync(self) -> ActResult:
        """Wait for the game to ask for a command without sending anything."""
        return self.act()
