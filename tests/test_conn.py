import json

import dcss_api
import pytest

from ladder.conn import ActResult, Connection, classify_error, reply_modes


@pytest.mark.parametrize("text, reason", [
    ("Blocking due to 'more' message.", "more"),
    ("Blocking due to text input necessary from user (likely for level up message).", "text_input"),
    ("Character died.", "died"),
    ("Blocking due to a 'skills to train' txt menu.", "skills"),
    ("Something unexpected", "error:Something unexpected"),
])
def test_classify_api_errors(text, reason):
    assert classify_error(dcss_api.APIErr(text)) == reason


def test_classify_pickup_blocking_error():
    assert classify_error(dcss_api.BlockingErr("Pickup")) == "pickup"


# What a spectator joining sends to the player's socket (seen live on 0.34)
RESEND = [{"msg": "update_spectators", "count": 1}, {"msg": "version", "text": "Dungeon Crawl Stone Soup 0.34.0"},
          {"msg": "options"}, {"msg": "layout"}, {"msg": "ui_state", "state": 0},
          {"msg": "player", "turn": 25}, {"msg": "ui-stack", "items": []}, {"msg": "input_mode", "mode": 1}]
REPLY = [{"msg": "input_mode", "mode": 0}, {"msg": "player", "turn": 26}, {"msg": "input_mode", "mode": 1}]


def test_reply_modes_skips_a_spectator_resend():
    assert reply_modes(RESEND) == []
    assert reply_modes(RESEND + REPLY) == [0, 1]
    assert reply_modes(REPLY + RESEND) == [0, 1]


class FakeWeb:
    """Frames queued on the socket; read_until reads frames until one holds an input_mode."""

    def __init__(self, *frames):
        self.frames = list(frames)
        self.queue = []
        self.sent = []

    def write_key(self, key):
        self.sent.append(key)

    def read_until(self, msg):
        while self.frames:
            frame = self.frames.pop(0)
            self.queue += frame
            if any(m["msg"] == msg for m in frame):
                return
        raise AssertionError("read_until would block forever")

    def get_message(self):
        return json.dumps(self.queue.pop(0)) if self.queue else None


def test_act_reads_past_a_resend_that_arrived_while_idle():
    conn = Connection.__new__(Connection)
    conn.on_message, conn.record = lambda m: None, None
    conn.web = FakeWeb(RESEND, REPLY)
    result = conn.act("s")
    assert [m for m in result.messages if m["msg"] == "player"][-1]["turn"] == 26
    assert conn.web.frames == []


class RcWeb(FakeWeb):
    """get_rc_file reads the frames already on the wire, then the server's answer."""

    def __init__(self, *frames, raises=None):
        super().__init__(*frames)
        self.raises = raises

    def get_rc_file(self, game_id):
        while self.frames:
            self.queue += self.frames.pop(0)
        if self.raises:
            raise self.raises
        self.queue.append({"msg": "rcfile_contents", "contents": "x"})


def _conn(web):
    conn = Connection.__new__(Connection)
    conn.on_message, conn.record = lambda m: None, None
    conn.web = web
    return conn


def test_catch_up_reads_a_late_ready_signal_and_hides_its_own_question():
    late = [{"msg": "input_mode", "mode": 0}, {"msg": "input_mode", "mode": 1}, {"msg": "msgs", "messages": []}]
    conn = _conn(RcWeb(late))
    result = conn.catch_up()
    assert result.blocking is None
    assert [m["msg"] for m in result.messages] == ["input_mode", "input_mode", "msgs"]
    assert conn.web.frames == []


def test_quit_game_catches_up_before_asking_to_quit():
    """A late ready signal read as Ctrl-Q's reply hid the prompt, and the save was left behind."""
    from ladder.conn import ActResult
    conn, calls = _conn(FakeWeb()), []
    conn.catch_up = lambda: calls.append("catch_up") or ActResult()
    conn.act = lambda *keys, **kw: calls.append(keys) or ActResult()
    conn.quit_game()
    assert calls == ["catch_up", ("key_ctrl_q",)]


class Dcss041Web(FakeWeb):
    """dcss-api 0.4.1's read_until (lib.rs): frames are read until one holds the awaited message; a frame
    with a prompt in it raises after the whole frame is queued, and if that frame also held the awaited
    message the "found" mark stays set, so the next read_until returns at once whatever it waits for.
    A frame is (messages, error text or None). `found` starts set, as act() leaves it after a text prompt."""

    def __init__(self, *frames, found=True):
        super().__init__(*frames)
        self.found = found

    def read_until(self, msg):
        while not self.found:
            if not self.frames:
                raise AssertionError(f"read_until({msg!r}) would block forever")
            frame, error = self.frames.pop(0)
            self.queue += frame
            self.found = any(m["msg"] == msg for m in frame)
            if error:
                raise dcss_api.APIErr(error)
        self.found = False


MORE = "Blocking due to 'more' message."
# After "quit" + Enter on a new character, as recorded live (0.34, 2026-11-15); the summary's frame and the
# exit's are apart, and the game asks for nothing after the summary.
QUIT_SCREENS = [
    ([{"msg": "close_input"}, {"msg": "input_mode", "mode": 0}, {"msg": "msgs", "more": True},
      {"msg": "input_mode", "mode": 5}], MORE),
    ([{"msg": "input_mode", "mode": 0}, {"msg": "menu", "tag": "inventory"}, {"msg": "msgs"}], None),
    ([{"msg": "close_menu"}, {"msg": "input_mode", "mode": 5}, {"msg": "ui-push", "type": "game-over"}], MORE),
    ([{"msg": "ui-pop"}], None),
    ([{"msg": "game_ended", "reason": "quit"}], None),
    ([{"msg": "go_lobby"}], None),
]


def test_quit_waits_for_the_game_to_end_before_letting_go():
    """The wrong-dungeon bug: the quit returned at once (the read after a prompt), the socket closed before
    the game took the word, and the game was saved; the next seeded start resumed it at turn 0."""
    conn = _conn(Dcss041Web(*QUIT_SCREENS))
    prompt = [{"msg": "msgs", "messages": [{"text": 'Are you sure? (Confirm with "quit".) '}]}]
    conn.catch_up = lambda: ActResult()
    conn.act = lambda *keys, **kw: ActResult(blocking="text_input", messages=prompt)
    assert conn.quit_game() is True
    assert conn.web.sent == ["q", "u", "i", "t", "key_enter", "key_enter", "key_esc", "key_enter"]
    assert len(conn.web.frames) <= 1                              # read through to game_ended at least


def test_wait_game_end_gives_up_rather_than_reading_for_ever():
    conn = _conn(Dcss041Web(*[([{"msg": "input_mode", "mode": 0}], None)] * 3, found=False))
    assert conn.wait_game_end(max_reads=3) is False


def test_menu_left_open():
    from ladder.conn import menu_left_open
    use, yes_no, close = {"msg": "menu", "tag": "use_item"}, {"msg": "menu"}, {"msg": "close_menu"}
    assert not menu_left_open([use, close, {"msg": "close_all_menus"}])
    assert menu_left_open([close, {"msg": "input_mode", "mode": 8}, yes_no])    # "Keep equipping yourself?"
    assert not menu_left_open([{"msg": "input_mode", "mode": 1}])


def test_act_through_a_menu_stops_at_a_second_menu():
    frames = [[{"msg": "close_menu"}, {"msg": "input_mode", "mode": 8}, {"msg": "menu", "items": []}]]
    result = _conn(FakeWeb(*frames)).act("d", through_menu=True)
    assert result.blocking == "menu"


def test_act_stops_at_a_yes_no_question_without_a_menu():
    # nothing more comes until it is answered: reading on would wait for ever
    result = _conn(FakeWeb([{"msg": "input_mode", "mode": 0}], [{"msg": "input_mode", "mode": 8}])).act("key_esc")
    assert result.blocking == "yesno"


def _ready(turn, pos=None):
    player = {"msg": "player", "turn": turn, **({"pos": pos} if pos else {})}
    return [{"msg": "input_mode", "mode": 0}, {"msg": "input_mode", "mode": 1}, player]


class ScrollGame(FakeWeb):
    """A game cancelling a scroll's item menu, as seen on 0.34 (run A-rules-h, seed 500033).

    Esc closes the menu and asks "really abort?" as a Y/N menu. A key that arrives before that menu
    is up is not taken by it: the game keeps it and runs it as a command after the question is
    answered ("Unknown command."), a reply of its own. Moves reply with the new position.
    """

    def __init__(self, asks=True):
        super().__init__()
        self.asks, self.state, self.pending, self.turn, self.x = asks, "item_menu", [], 413, 0

    def write_key(self, key):
        super().write_key(key)
        if self.state == "item_menu":           # Esc
            if self.asks:
                self.state = "closing"
                self.frames.append([{"msg": "close_menu"}, {"msg": "input_mode", "mode": 8},
                                    {"msg": "menu", "items": [{"text": " Y - Yes"}]}])
            else:
                self.state = "command"
                self.frames.append([{"msg": "close_menu"}, {"msg": "input_mode", "mode": 1}])
        elif self.state == "closing":           # typed ahead: misses the question
            self.pending.append(key)
        elif self.state == "question":          # answered
            self.state = "command"
            self.turn += 1
            self.frames.append([{"msg": "close_menu"}] + _ready(self.turn))
            for _ in self.pending:              # the stray key, run as a command
                self.frames.append(_ready(self.turn) + [{"msg": "msgs", "messages": [{"text": "Unknown command."}]}])
            self.pending = []
        else:                                   # a move
            self.turn += 1
            self.x -= 1
            self.frames.append(_ready(self.turn, {"x": self.x, "y": 0}))

    def read_until(self, msg):
        super().read_until(msg)
        if self.state == "closing":             # the question's menu has been read: it is up now
            self.state = "question"


@pytest.mark.parametrize("asks", [True, False])
def test_cancelling_a_scroll_prompt_leaves_no_reply_behind(asks):
    from ladder.conn import cancel_prompt
    game = ScrollGame(asks)
    conn = _conn(game)
    cancel_prompt(conn)
    assert game.sent == (["key_esc", "Y"] if asks else ["key_esc"])
    for step in range(1, 4):                    # each move's reply is that move's, not the one before
        result = conn.act("key_dir_w")
        positions = [m["pos"]["x"] for m in result.messages if m["msg"] == "player" and "pos" in m]
        assert positions == [-step]
    assert game.frames == [] and game.pending == []


def test_the_old_typed_ahead_cancel_put_every_reply_a_key_behind():
    # what the bot did before: Esc and Y together. The stray Y's reply is read as the next key's.
    game = ScrollGame(True)
    conn = _conn(game)
    conn.act("key_esc", "Y", through_menu=True)
    assert game.pending == ["Y"]
    conn.act("key_esc")                         # Reflex answers the question that was left open
    first = conn.act("key_dir_w")
    assert [m["messages"][0]["text"] for m in first.messages if m["msg"] == "msgs"] == ["Unknown command."]
    assert not any(m["msg"] == "player" and "pos" in m for m in first.messages)     # the move's reply is late
    assert len(game.frames) == 1
