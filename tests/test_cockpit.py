"""Cockpit hub (who answers which decision, idle switch, shadow Jev routes) and its HTTP guard rails."""

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError

import pytest

from helpers import add_monster, make_state
from ladder.authority import AUTONOMOUS, Authority
from ladder.cockpit import GAME_GONE, ChildHooks, Hub, game_links, handover_text, make_handler, watch_url
from ladder.decisions import END_GAME, TAKE_OVER, Answer, for_escalation, for_interrupt, stat_choice
from ladder.interrupts import Interrupt
from ladder.jev import Answers, JevResult
from ladder.reflex import Escalation, Hooks, StubTiers

ROOM = ["#######", "#..@..#", "#.....#", "#######"]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def request(decision_type="choose_god", **context):
    state = make_state(ROOM)
    req = for_interrupt(Interrupt("feature_in_view", "dcss", {"feature": "altar", "dist": 3},
                                  decision_type=decision_type), state, level_explored=False)
    req.id = "1-5-1"
    req.context.update(context)
    return req.to_dict()


def hub(**kw):
    sent = []
    clock = Clock()
    h = Hub(Authority(**kw), sent.append, clock=clock)
    return h, sent, clock


def test_pinned_decision_waits_for_the_player():
    h, sent, _ = hub()
    h.handle({"ev": "decision", "request": request()})
    assert sent == [] and h.pending_view()["decision_type"] == "choose_god"
    assert h.decide("1-5-1", "worship") == "'worship' isn't an option"
    assert h.decide("1-5-1", "skip") is None
    assert sent == [{"cmd": "answer", "id": "1-5-1", "choice": "skip", "decider": "player", "reason": "your call"}]
    assert h.pending is None and h.decide("1-5-1", "skip")      # answered once only


def test_deferred_decision_goes_to_strategy_at_once():
    h, sent, _ = hub()
    req = request("descend_stairs")
    req["decision_type"] = "descend_stairs"
    req["context"]["level_explored"] = True
    h.handle({"ev": "decision", "request": req})
    assert h.pending is None and sent[0]["decider"] == "strategy" and sent[0]["choice"] == req["recommended"]


def test_switching_to_autonomous_hands_over_the_waiting_card():
    h, sent, _ = hub()
    h.handle({"ev": "decision", "request": request()})
    assert h.set_mode("sideways")
    h.set_mode(AUTONOMOUS)
    assert sent[0]["decider"] == "strategy" and h.pending is None
    h.handle({"ev": "decision", "request": {**request(), "id": "1-6-2"}})
    assert sent[1]["decider"] == "strategy"                       # pinned too: autonomous means autonomous


def test_idle_switch_counts_down_and_takes_over():
    h, sent, clock = hub(idle_minutes=2)
    h.handle({"ev": "decision", "request": request()})
    clock.now += 60
    h.tick()
    assert sent == [] and h.pending_view()["takeover_in_s"] == 60.0
    clock.now += 60
    h.tick()
    assert sent[0]["decider"] == "strategy" and h.authority.mode == AUTONOMOUS
    assert [e["by"] for e in h.events if e["ev"] == "mode"] == ["idle"]


def test_idle_settings_validate():
    h, _, _ = hub()
    assert h.set_idle(-1) and h.set_idle(1.5) and h.set_idle(True)
    assert h.set_idle(0) is None and h.pending_view() is None


def test_stop_answers_a_waiting_card_with_take_over():
    h, sent, _ = hub()
    h.handle({"ev": "decision", "request": request()})
    h.stop()
    assert sent[0]["choice"] == TAKE_OVER and sent[1] == {"cmd": "stop"}


def test_controls_after_the_game_process_exits_say_so_instead_of_raising():
    """Issue 4: the player took the wheel, the run ended, then Hold hit a closed pipe."""
    def closed(cmd):
        raise BrokenPipeError(32, "Broken pipe")
    h = Hub(Authority(), closed, clock=Clock())
    h.handle({"ev": "decision", "request": request()})
    assert h.decide("1-5-1", "skip") == GAME_GONE and h.pending      # the card stays until the pump notices
    h.child_gone()
    assert h.pending is None and h.run["state"] == "error"
    assert h.hold(True) == GAME_GONE and not h.held
    assert h.stop() == GAME_GONE
    h.tick()


def test_step_and_speed_reach_the_game_and_validate():
    h, sent, _ = hub()
    assert h.step(0) and h.step(1.5) and h.step(True) and h.step(1001)
    assert h.step(3) is None and h.held and sent == [{"cmd": "step", "n": 3}]
    assert h.set_speed(-1) and h.set_speed(61) and h.set_speed("2") and h.set_speed(float("nan"))
    assert h.set_speed(1.5) is None and h.settings()["delay"] == 1.5 and sent[-1] == {"cmd": "speed", "delay": 1.5}
    h.child_gone()
    assert h.step(1) == GAME_GONE and h.set_speed(0) == GAME_GONE


def test_records_route_without_jev_and_shadow_route_with_it():
    record = {"game": 1, "step": 3, "action": "explore", "kind": "hostile_in_view", "source": "dcss",
              "decision_type": None, "detail": {"monsters": []}, "messages": [],
              "snapshot": {"turn": 30, "place": "D:1", "hostiles": [{"name": "rat", "dist": 4, "threat": "easy"}],
                           "status": []}}
    h, _, _ = hub()
    h.handle({"ev": "record", "record": record})
    h.handle({"ev": "record", "record": {**record, "kind": "level_explored", "decision_type": "descend_stairs"}})
    assert [e["route"]["tier"] for e in h.events] == ["reflex", "strategy"]

    class FakeJev:
        def ask(self, state):
            assert state["monsters"][0]["name"] == "rat"
            raw = {"threat": {"score": 2.4}, "needs_plan": {"noul": 0.1}, "unfamiliar": {"noul": 0.1},
                   "player_worthy": {"noul": 0.1}, "next_goal": {"choice": "none"}}
            return JevResult(Answers.parse(raw), "jev-latest", {}, 120.0)

    h = Hub(Authority(), lambda m: None, jev=FakeJev())
    h.handle({"ev": "record", "record": record})
    h.pool.shutdown(wait=True)
    event = h.events[0]
    assert event["route"]["tier"] == "strategy" and event["route"]["rule"] == 2
    assert h.tiers == {"strategy": 1}


def test_decision_requests_offer_only_what_reflex_can_do():
    state = make_state(ROOM)
    explored = for_interrupt(Interrupt("level_explored", "dcss", {}, decision_type="descend_stairs"), state, False)
    assert explored.recommended == "descend" and explored.context["level_explored"]
    assert stat_choice(state, False).keys() == {"S", "I", "D"}           # the prompt is open: no way out
    assert "fight_on" not in for_escalation("stuck", state, False).keys()
    add_monster(state, (5, 1), 7, "Natasha", threat=2)
    esc = for_escalation("low hp", state, False)
    assert {"fight_on", "end_game", "take_over"} <= esc.keys() and esc.recommended == "take_over"
    assert esc.context["threat"] == 2


class Pipe:
    def __init__(self, incoming):
        self.incoming, self.sent = list(incoming), []

    def send(self, m):
        self.sent.append(m)

    def recv(self):
        return self.incoming.pop(0)

    def poll(self, timeout=0):
        return bool(self.incoming)


def test_stub_struggles_out_of_webs_and_stuck_means_leave_it_saved():
    """Run 20261101-175256: webbed at 32/33 HP, Tab only said so, and Strategy took 'end game'."""
    webbed = make_state(ROOM, hp=32, hp_max=33, status=[{"light": "Held"}])
    assert StubTiers().next_action(webbed) == "struggle"
    add_monster(webbed, (5, 1), 7, "ribbon worm")
    assert StubTiers().next_action(webbed) == "struggle"
    free = make_state(ROOM)
    add_monster(free, (5, 1), 7, "ribbon worm")
    assert StubTiers().next_action(free) == "fight"
    hurt = make_state(ROOM, hp=5, status=[{"light": "Held"}])
    add_monster(hurt, (5, 1), 7, "kobold")
    with pytest.raises(Escalation):
        StubTiers().next_action(hurt)                 # low HP still asks first
    esc = for_escalation("no progress on 'fight'", webbed, False)
    assert esc.recommended == TAKE_OVER
    assert Hooks().decide(esc).choice == END_GAME     # `spike` plays alone: no one to hand the game to


def test_child_hooks_wait_for_their_own_answer():
    req = for_interrupt(Interrupt("feature_in_view", "dcss", {"dist": 2}, decision_type="choose_god"),
                        make_state(ROOM), False)
    req.id = "1-2-1"
    pipe = Pipe([{"cmd": "hold"}, {"cmd": "answer", "id": "old"},
                 {"cmd": "answer", "id": "1-2-1", "choice": "skip", "decider": "player"}])
    hooks = ChildHooks(pipe)
    assert hooks.decide(req) == Answer("skip", "player", "")
    assert hooks.held and pipe.sent[0]["ev"] == "decision"
    pipe.incoming = [{"cmd": "stop"}]
    assert hooks.checkpoint() is False


@pytest.fixture
def server():
    h, _, _ = hub()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), None)
    srv.RequestHandlerClass = make_handler(h, srv.server_address[1])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield h, srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def call(port, path, body=None, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="POST" if body is not None else "GET",
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except HTTPError as e:
        return e.code, e.read()


def test_http_serves_page_and_applies_settings(server):
    h, port = server
    status, body = call(port, "/")
    assert status == 200 and b"Ladder cockpit" in body
    assert call(port, "/api/idle", {"minutes": 5})[0] == 200 and h.authority.idle_minutes == 5
    assert call(port, "/api/mode", {"mode": "nope"})[0] == 409


def test_http_refuses_other_origins_and_hosts(server):
    h, port = server
    assert call(port, "/api/mode", {"mode": "autonomous"}, {"Origin": "http://evil.example"})[0] == 403
    assert call(port, "/api/mode", {"mode": "autonomous"}, {"Host": "evil.example"})[0] == 403
    assert call(port, "/api/mode", {"mode": "autonomous"}, {"Content-Type": "text/plain"})[0] == 415
    assert h.authority.mode == "assisted"


def test_watch_url():
    assert watch_url("ws://localhost:8080/socket", "ladderbot") == "http://localhost:8080/#watch-ladderbot"


def test_handover_names_the_keychain_item_the_login_uses():
    links = game_links("wss://crawl.example/socket", "ladderbot")
    assert links["lobby"] == "https://crawl.example/"
    assert "-s dcss-ladder -a dcss-account/ladderbot -w" in links["password_cmd"]
    text = handover_text(links, {"game": 1, "final_place": "D:1", "turns": 199})
    assert "D:1, turn 199" in text and "log in as ladderbot" in text


def test_stall_warning_only_when_the_game_should_be_moving():
    h, _, clock = hub()
    h.handle({"ev": "run_start", "dir": "runs/x", "user": "ladderbot", "games": 1})
    clock.now += 60
    h.tick()
    assert [e["stalled"] for e in h.events if e["ev"] == "stall"] == [True]
    h.handle({"ev": "step", "game": 1, "step": 2, "action": "explore", "snapshot": {}, "messages": []})
    assert [e["stalled"] for e in h.events if e["ev"] == "stall"] == [True, False]
    h.handle({"ev": "decision", "request": request()})
    clock.now += 600
    h.tick()                                          # waiting on the player is not a stall
    assert len([e for e in h.events if e["ev"] == "stall"]) == 2


def test_child_steps_n_actions_then_holds():
    pipe = Pipe([{"cmd": "step", "n": 2}])
    hooks = ChildHooks(pipe)
    assert hooks.checkpoint() and hooks.checkpoint()
    assert pipe.sent == [] and hooks._holding()      # two actions ran; the third waits for the player
    pipe.poll = lambda timeout=0: False               # Resume arrives only once it is waiting
    pipe.incoming = [{"cmd": "resume"}]
    assert hooks.checkpoint()
    assert pipe.sent == [{"ev": "paused", "paused": True}, {"ev": "paused", "paused": False}]
    assert not hooks.held and not hooks.steps_left


def test_child_paces_actions_and_takes_commands_while_it_waits():
    import time
    pipe = Pipe([{"cmd": "speed", "delay": 0}])
    hooks = ChildHooks(pipe, delay=30)
    hooks.last_action = time.monotonic()
    started = time.monotonic()
    assert hooks.checkpoint() and hooks.delay == 0
    assert time.monotonic() - started < 5             # the new speed cut the 30 s pause short
    pipe.incoming = [{"cmd": "stop"}]
    hooks.delay, hooks.last_action = 30, time.monotonic()
    assert hooks.checkpoint() is False


def test_http_step_and_speed(server):
    h, port = server
    assert call(port, "/api/speed", {"delay": 2})[0] == 200 and h.delay == 2
    assert call(port, "/api/speed", {"delay": "fast"})[0] == 409
    assert call(port, "/api/step", {"n": 5})[0] == 200 and h.held
