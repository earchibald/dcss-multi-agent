"""Reflex against a scripted connection: which keys it sends, and which decisions it asks."""

from helpers import make_state, player

from ladder.conn import ActResult
from ladder.decisions import Answer
from ladder.reflex import Hooks, Reflex, StubTiers
from ladder.runlog import RunLog

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
