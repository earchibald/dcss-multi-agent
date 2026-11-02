"""Reflex against a scripted connection: which keys it sends, and which decisions it asks."""

from helpers import add_monster, make_state, player, say

from ladder.conn import ActResult
from ladder.decisions import Answer, for_interrupt
from ladder.interrupts import Before, Interrupt
from ladder.pace import PACE_MS, pace_key, pace_ms, pace_rc
from ladder.reflex import Hooks, Reflex, StubTiers
from ladder.runlog import RunLog
from ladder.state import MF_FLOOR, MF_WALL

SHOP_ROOM = [
    "#########",
    "#@....∩.#",
    "#.......#",
    "#########",
]


class FakeConn:
    """Records keys. Each act() runs the next scripted change to the game state, if any."""

    def __init__(self, state, changes=()):
        self.state, self.changes, self.sent = state, list(changes), []

    def act(self, *keys):
        self.sent.append(keys)
        if self.changes:
            self.changes.pop(0)(self.state)
        return ActResult()

    def open_menu(self, *keys):
        self.sent.append(("menu",) + keys)
        return ActResult(blocking="menu")


class Asked(Hooks):
    def __init__(self):
        self.asked = []

    def decide(self, request):
        self.asked.append(request.decision_type)
        return Answer(request.recommended, "stub")


def walk(state, x, y):
    player(state, pos={"x": x, "y": y}, turn=state.turn + 1)


def test_stub_visits_a_shop_before_exploring_and_remembers_it_under_the_player():
    state = make_state(SHOP_ROOM)
    stub = StubTiers()
    assert stub.unvisited_shop(state) == (6, 1) and stub.next_action(state) == "shop"
    state.cells[(6, 1)]["g"] = "@"                  # standing on it hides the shop glyph
    assert stub.next_action(state) == "shop"
    stub.shops_seen.add((6, 1))
    assert stub.next_action(state) == "explore"


def test_reflex_walks_to_the_shop_then_opens_and_closes_its_menu(tmp_path):
    """Greedy explore would open the shop itself; its menu sends no input_mode, and act() waited forever."""
    state = make_state(SHOP_ROOM)
    walk(state, 5, 1)
    conn = FakeConn(state, [lambda s: walk(s, 6, 1)])
    reflex = Reflex(conn, state, RunLog(tmp_path))
    reflex.step("shop")
    assert conn.sent == [("key_dir_e",)]
    reflex.step("shop")
    assert conn.sent[1:] == [("menu", "<"), ("key_esc",)]
    assert reflex.stub.next_action(state) == "explore"


def test_downstairs_in_view_is_asked_once_per_level(tmp_path):
    state = make_state(["#########", "#@......#", "#.......#", "#########"])

    def stairs_at(x):
        return lambda s: (s.apply({"msg": "map", "cells": [{"x": x, "y": 2, "mf": 13, "g": ">", "t": {"bg": 1}}]}),
                          walk(s, 2, 1))

    hooks = Asked()
    reflex = Reflex(FakeConn(state, [stairs_at(5), stairs_at(7)]), state, RunLog(tmp_path), hooks=hooks)
    reflex.step("explore")
    reflex.step("explore")
    assert hooks.asked == ["descend_stairs"]


# Crazy Yiuf's cottage: he stands behind a runed door, which autofight won't path through
COTTAGE = [
    "#########",
    "#@...+.Y#",
    "#....####",
    "#.>..#",
    "######",
]


def cottage(**kw):
    state = make_state([row.replace("Y", ".") for row in COTTAGE], **kw)
    add_monster(state, (7, 1), 7, "Crazy Yiuf", threat=2)
    return state


def test_when_autofight_cant_path_to_a_target_reflex_walks_there_itself(tmp_path):
    state = cottage()
    conn = FakeConn(state, [lambda s: say(s, "No reachable target in view!"), lambda s: walk(s, 2, 1)])
    reflex = Reflex(conn, state, RunLog(tmp_path))
    reflex.step(reflex.stub.next_action(state))
    assert conn.sent == [("key_tab",)]
    assert reflex.stub.next_action(state) == "approach"
    reflex.step("approach")
    assert conn.sent[1] == ("key_dir_e",)
    assert reflex.stub.next_action(state) == "fight"       # autofight again from the new square


def test_a_hostile_with_no_known_path_is_left_alone(tmp_path):
    state = cottage()
    state.cells[(5, 1)]["mf"] = MF_WALL                    # no door after all
    reflex = Reflex(FakeConn(state), state, RunLog(tmp_path))
    reflex.stub.approach = True
    reflex.step("approach")
    assert reflex.stub.ignored == {7} and reflex.stub.next_action(state) == "explore"
    add_monster(state, (2, 1), 7, "Crazy Yiuf", threat=2)  # next to us: it counts again
    assert reflex.stub.next_action(state) == "fight"


def test_explore_refused_by_a_left_alone_monster_puts_it_back_in_play():
    state = cottage()
    stub = StubTiers()
    stub.ignored = {7}
    before = Before.capture(state)
    refused = Interrupt("hostile_in_view", "dcss", {"explore_refused": True})
    stub.observe("explore", before, state, [refused])
    assert stub.ignored == set()


def test_a_unique_can_be_left_alone_or_left_behind(tmp_path):
    state = cottage()
    interrupt = Interrupt("hostile_in_view", "dcss",
                          {"monsters": [{"name": "Crazy Yiuf", "dist": 6, "threat": "tough", "unique": True}]},
                          decision_type="engage_unique")
    req = for_interrupt(interrupt, state, False)
    assert "Crazy Yiuf (tough, 6 squares away)" in req.question
    assert {"fight", "avoid", "leave"} <= req.keys()
    reflex = Reflex(FakeConn(state), state, RunLog(tmp_path))
    reflex._apply(Answer("leave", "player"))
    assert reflex.stub.ignored == {7} and reflex.stub.next_action(state) == "travel"
    state.cells[(2, 3)]["mf"] = MF_FLOOR                   # no known stairs: only "avoid"
    assert "leave" not in for_interrupt(interrupt, state, False).keys()


class Paced(Hooks):
    def __init__(self, ms):
        self.ms = ms

    def pace_ms(self):
        return self.ms


def test_reflex_sends_the_pace_key_only_when_the_pace_changes(tmp_path):
    state = cottage()
    hooks = Paced(150)
    conn = FakeConn(state)
    reflex = Reflex(conn, state, RunLog(tmp_path), hooks=hooks)
    reflex._pace()
    reflex._pace()
    hooks.ms = -1
    reflex._pace()
    assert conn.sent == [(pace_key(150),), (pace_key(-1),)]


def test_pace_curve_has_a_floor_and_full_speed_draws_nothing():
    assert pace_ms(0) == -1
    assert [pace_ms(d) for d in (0.25, 1, 5, 60)] == [100, 150, 250, 700]
    rc = pace_rc()
    for ms in PACE_MS:
        i = PACE_MS.index(ms)
        assert f"macros += M \\{{{ord(pace_key(ms))}}} ===ladder_pace_{i}" in rc
        assert f'crawl.setopt("travel_delay = {ms}")' in rc
