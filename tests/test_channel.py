"""The Claude Code channel: MCP handshake, which cockpit events reach Claude, notes both ways."""

import io
import json
import re
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from ladder.authority import Authority
from ladder.channel import INSTRUCTIONS, Channel, sse, to_channel
from ladder.cockpit import NO_CHANNEL, Hub, make_handler


class Out:
    """Thread-safe capture of what the channel writes to stdout."""

    def __init__(self):
        self.lines: list[dict] = []
        self.buf = ""
        self.lock = threading.Lock()

    def write(self, s: str) -> None:
        with self.lock:
            self.buf += s
            *done, self.buf = self.buf.split("\n")
            self.lines += [json.loads(line) for line in done if line]

    def flush(self) -> None:
        pass

    def notes(self) -> list[dict]:
        with self.lock:
            return [m["params"] for m in self.lines if m.get("method") == "notifications/claude/channel"]


def until(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def rpc(ch: Channel, method: str, params=None, mid=1) -> dict:
    return ch.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})


def test_handshake_declares_a_channel_with_tools():
    ch = Channel(Out())
    r = rpc(ch, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}})
    caps = r["result"]["capabilities"]
    assert caps["experimental"] == {"claude/channel": {}} and caps["tools"] == {}
    assert r["result"]["protocolVersion"] == "2025-06-18" and "reply tool" in r["result"]["instructions"]
    assert {t["name"] for t in rpc(ch, "tools/list")["result"]["tools"]} == {"reply", "cockpit_state"}
    assert rpc(ch, "ping")["result"] == {}
    assert rpc(ch, "resources/list")["error"]["code"] == -32601
    assert ch.handle({"jsonrpc": "2.0", "method": "notifications/cancelled"}) is None
    assert 'source="cockpit"' in INSTRUCTIONS


def test_serve_speaks_newline_delimited_json_rpc():
    out = Out()
    inp = io.StringIO('{"jsonrpc":"2.0","id":7,"method":"ping"}\n\nnot json\n')
    Channel(out).serve(inp)
    assert out.lines[0] == {"jsonrpc": "2.0", "id": 7, "result": {}}
    assert out.lines[1]["error"]["code"] == -32700


def record(kind, **detail):
    return {"ev": "record", "seq": 3, "record": {"kind": kind, "game": 1, "step": 40, "detail": detail,
                                                 "snapshot": {"place": "D:2", "turn": 812, "hp": 3, "hp_max": 20},
                                                 "messages": ["The kobold hits you."]}}


def test_only_what_a_coding_agent_should_see_is_forwarded():
    text, meta = to_channel({"ev": "note", "by": "player", "text": "why did it stop?"}, "runs/x")
    assert text == "why did it stop?" and meta == {"kind": "note", "from": "player", "run": "runs/x"}
    assert to_channel({"ev": "note", "by": "claude", "text": "looking"}) is None      # our own reply, echoed
    text, meta = to_channel(record("escalation", reason="no safe stairs"))
    assert "Reflex is stuck: no safe stairs" in text and "D:2, turn 812" in text and "kobold" in text
    assert meta == {"kind": "record", "interrupt": "escalation", "game": "1", "step": "40"}
    assert to_channel(record("died"))[1]["interrupt"] == "died"
    assert to_channel(record("hostile_in_view", monsters=[])) is None
    assert to_channel({"ev": "stall", "stalled": True, "seconds": 50})[1]["kind"] == "stall"
    assert to_channel({"ev": "stall", "stalled": False}) is None
    assert "Traceback" in to_channel({"ev": "error", "message": "Traceback ..."})[0]
    assert "escalation: stuck" in to_channel({"ev": "game_end", "game": 2, "ended_by": "escalation",
                                               "final_place": "D:3", "turns": 900, "xl": 4, "escalation": "stuck"})[0]
    assert to_channel({"ev": "run_start", "dir": "runs/y", "user": "ladderbot"})[1]["run"] == "runs/y"
    for ev in ("status", "settings", "pending", "decided", "mode", "route", "run", "game_start"):
        assert to_channel({"ev": ev}) is None


def test_meta_keys_are_identifiers_and_values_strings():
    for e in (record("no_progress", action="explore", repeats=3), {"ev": "note", "by": "player", "text": "x"},
              {"ev": "game_end", "game": 1}):
        _, meta = to_channel(e, "runs/z")
        assert all(re.fullmatch(r"[A-Za-z0-9_]+", k) and isinstance(v, str) for k, v in meta.items())


def test_sse_parses_data_lines_and_skips_pings():
    stream = [b": ping\n", b"\n", b'data: {"ev": "hello"}\n', b"\n", b'data: {"ev": "note",\n', b'data: "seq": 2}\n', b"\n"]
    assert list(sse(stream)) == [{"ev": "hello"}, {"ev": "note", "seq": 2}]


def note(seq, text="hi"):
    return {"ev": "note", "seq": seq, "by": "player", "text": text}


def test_reconnect_replays_only_what_the_same_cockpit_sent_meanwhile():
    out = Out()
    ch = Channel(out)
    ch.on_event({"ev": "hello", "boot": "a", "run": {"state": "running", "dir": "runs/a"}, "events": [note(1, "old")]})
    assert out.notes() == []                                   # a cockpit's backlog is history on first contact
    ch.on_event(note(4, "live"))
    ch.on_event({"ev": "hello", "boot": "a", "run": {"state": "running"}, "events": [note(1), note(4), note(6, "missed")]})
    assert [n["content"] for n in out.notes()] == ["live", "missed"]
    ch.on_event({"ev": "hello", "boot": "b", "run": {"state": "starting"}, "events": [note(9, "other")]})
    ch.on_event(note(2, "fresh"))                              # a new cockpit's seq starts low again
    assert [n["content"] for n in out.notes()][-1] == "fresh" and len(out.notes()) == 3


def test_losing_the_cockpit_mid_run_says_so_once():
    out = Out()
    ch = Channel(out)
    ch.on_event({"ev": "hello", "boot": "a", "run": {"state": "running", "dir": "runs/a"}, "events": []})
    ch.lost()
    ch.lost()
    assert [n["meta"] for n in out.notes()] == [{"kind": "cockpit", "run": "runs/a"}]
    ch.on_event({"ev": "hello", "boot": "b", "run": {"state": "finished"}, "events": []})
    ch.lost()
    assert len(out.notes()) == 1


def test_hub_notes_validate_and_need_a_listener():
    h = Hub(Authority(), lambda m: None)
    assert h.note("hello", "player") == NO_CHANNEL
    assert h.note("hello", "someone") and h.note("  ", "claude") and h.note("x" * 5000, "claude")
    q, snap = h.subscribe(channel=True)
    assert "boot" in snap and h.settings()["channel"] is True
    assert h.note(" saw a hang on D:3 \n", "player") is None
    assert h.events[-1]["ev"] == "note" and h.events[-1]["text"] == "saw a hang on D:3"
    h.unsubscribe(q, channel=True)
    assert h.settings()["channel"] is False


@pytest.fixture
def cockpit():
    h = Hub(Authority(), lambda m: None)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), None)
    srv.RequestHandlerClass = make_handler(h, srv.server_address[1])
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield h, srv
    srv.shutdown()
    srv.server_close()


def test_end_to_end_notes_both_ways_and_state(cockpit):
    h, srv = cockpit
    out = Out()
    ch = Channel(out, f"http://127.0.0.1:{srv.server_address[1]}", retry_max=0.2)
    ch.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    try:
        assert until(lambda: h.channels == 1)
        h.handle({"ev": "run_start", "dir": "runs/e2e", "user": "ladderbot"})
        assert h.note("why did it stop on D:2?", "player") is None
        assert until(lambda: len(out.notes()) == 2)
        start, asked = out.notes()
        assert start["meta"]["kind"] == "run_start"
        assert asked == {"content": "why did it stop on D:2?", "meta": {"kind": "note", "from": "player", "run": "runs/e2e"}}

        r = rpc(ch, "tools/call", {"name": "reply", "arguments": {"text": "a bug in travel.py; fixing"}})
        assert "isError" not in r["result"]
        assert h.events[-1]["by"] == "claude" and h.events[-1]["text"] == "a bug in travel.py; fixing"

        r = rpc(ch, "tools/call", {"name": "cockpit_state", "arguments": {}})
        state = json.loads(r["result"]["content"][0]["text"])
        assert state["run"]["dir"] == "runs/e2e" and state["settings"]["channel"] is True
        assert state["recent_events"][-1]["by"] == "claude"
        assert rpc(ch, "tools/call", {"name": "reply", "arguments": {"text": ""}})["result"]["isError"]
        assert rpc(ch, "tools/call", {"name": "nope"})["result"]["isError"]
        time.sleep(0.2)
        assert len(out.notes()) == 2                           # Claude's own reply isn't sent back to it
    finally:
        ch.stopping.set()


def test_tools_say_when_the_cockpit_is_not_running():
    ch = Channel(Out(), "http://127.0.0.1:9")                  # nothing listens on the discard port
    r = rpc(ch, "tools/call", {"name": "reply", "arguments": {"text": "hello"}})
    assert r["result"]["isError"] and "ladder cockpit" in r["result"]["content"][0]["text"]
    assert rpc(ch, "tools/call", {"name": "cockpit_state"})["result"]["isError"]
