import json

import dcss_api
import pytest

from ladder.conn import Connection, classify_error, reply_modes


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
