from helpers import add_monster, make_state, map_message, player, say

from ladder.interrupts import Before, Detector, frontier_groups

ROOM = [
    "#########",
    "#@......#",
    "#.......#",
    "#.......#",
    "#########",
]


def kinds(interrupts):
    return [i.kind for i in interrupts]


def run(state, action="explore", blocking=None, mode="explore", detector=None, change=None):
    """Capture Before, apply `change(state)`, then detect."""
    detector = detector or Detector()
    before = Before.capture(state)
    if change:
        change(state)
    return detector.detect(before, state, action, blocking, mode)


def test_quiet_step_has_no_interrupts():
    state = make_state(ROOM)
    assert run(state, change=lambda s: player(s, turn=11, pos={"x": 2, "y": 1})) == []


def test_new_hostile_is_a_native_stop():
    state = make_state(ROOM)
    out = run(state, change=lambda s: add_monster(s, (6, 2), 1, "kobold", threat=0))
    [i] = out
    assert (i.kind, i.source, i.decision_type) == ("hostile_in_view", "dcss", None)
    assert i.detail["monsters"][0] == {"name": "kobold", "dist": 5, "threat": "trivial", "unique": False}


def test_unique_maps_to_engage_unique():
    state = make_state(ROOM)
    [i] = run(state, change=lambda s: add_monster(s, (6, 2), 1, "Sigmund", threat=2))
    assert i.decision_type == "engage_unique"


def test_explore_refused_by_known_hostile():
    state = make_state(ROOM)
    add_monster(state, (6, 2), 1, "endoplasm")
    [i] = run(state, change=lambda s: say(s, "An endoplasm is nearby!"))
    assert i.kind == "hostile_in_view" and i.detail["explore_refused"]


def test_items_and_features_and_their_decisions():
    state = make_state(ROOM)

    def reveal(s):
        s.apply({"msg": "map", "cells": [
            {"x": 5, "y": 2, "mf": 6, "g": "?", "t": {"bg": 1}},
            {"x": 7, "y": 3, "mf": 13, "g": ">", "t": {"bg": 1}},
            {"x": 3, "y": 3, "mf": 15, "g": "_", "t": {"bg": 1}},
        ]})
    out = run(state, change=reveal)
    by_kind = {(i.kind, i.detail.get("feature")): i for i in out}
    assert ("item_in_view", None) in by_kind
    assert by_kind[("feature_in_view", "downstairs")].decision_type == "descend_stairs"
    assert by_kind[("feature_in_view", "altar")].decision_type == "choose_god"


def test_new_level_is_one_interrupt_not_a_feature_flood():
    state = make_state(ROOM)

    def descend(s):
        msg, _ = map_message(["#####", "#@.>#", "#.<.#", "#####"], clear=True)
        s.apply(msg)
        player(s, depth=2, turn=12)
    out = run(state, action="descend", change=descend)
    assert kinds(out) == ["level_change"]
    assert out[0].detail == {"from": "D:1", "to": "D:2", "features_seen": ["downstairs", "upstairs"]}


def test_hp_loss_counts_only_during_delays():
    state = make_state(ROOM)
    assert "hp_loss" in kinds(run(state, action="rest", change=lambda s: player(s, hp=18, turn=12)))
    state = make_state(ROOM)
    assert "hp_loss" not in kinds(run(state, action="fight", change=lambda s: player(s, hp=18, turn=12)))


def test_hp_slope_fires_once_then_rearms_after_recovery():
    det = Detector()
    state = make_state(ROOM, hp=20, hp_max=20, turn=10)
    run(state, action="fight", detector=det, change=lambda s: player(s, hp=17, turn=11))
    out = run(state, action="fight", detector=det, change=lambda s: player(s, hp=12, turn=12))
    assert kinds(out) == ["hp_slope"] and out[0].detail["dropped"] == 8
    assert run(state, action="fight", detector=det, change=lambda s: player(s, hp=6, turn=13)) == []
    run(state, action="rest", detector=det, change=lambda s: player(s, hp=19, turn=60))
    run(state, action="fight", detector=det, change=lambda s: player(s, hp=15, turn=61))
    assert kinds(run(state, action="fight", detector=det, change=lambda s: player(s, hp=9, turn=62))) == ["hp_slope"]


def test_status_change_reports_added_statuses():
    state = make_state(ROOM)
    [i] = run(state, action="fight", change=lambda s: player(s, turn=11, status=[{"light": "Pois"}]))
    assert i.kind == "status_change" and i.detail["added"] == ["Pois"]


def test_no_progress_after_repeated_stalls():
    det = Detector()
    state = make_state(ROOM)
    assert run(state, action="fight", detector=det, change=lambda s: say(s, "No target in view!")) == []
    [i] = run(state, action="fight", detector=det, change=lambda s: say(s, "No target in view!"))
    assert i.kind == "no_progress" and i.detail["repeats"] == 2


def test_stat_prompt_is_a_stat_choice_decision():
    state = make_state(ROOM)
    [i] = run(state, action="fight", blocking="text_input",
              change=lambda s: (say(s, "Increase (S)trength, (I)ntelligence, or (D)exterity? "),
                                player(s, turn=11)))
    assert (i.kind, i.decision_type) == ("prompt", "stat_choice")


def test_level_explored_message():
    state = make_state(ROOM)
    [i] = run(state, change=lambda s: say(s, "Done exploring."))
    assert (i.kind, i.decision_type) == ("level_explored", "descend_stairs")


def test_message_stops_and_traps():
    state = make_state(ROOM)
    out = run(state, change=lambda s: (say(s, "* * * LOW HITPOINT WARNING * * *", "You found a dart trap!"),
                                       player(s, turn=11)))
    assert sorted(kinds(out)) == ["message_stop", "trap"]


def test_death_short_circuits():
    state = make_state(ROOM)
    assert kinds(run(state, action="fight", blocking="died", change=lambda s: say(s, "You die..."))) == ["died"]


CROSS = [
    "???????????",
    "????#.#????",
    "????#.#????",
    "#####.#####",
    "?....@....?",
    "#####.#####",
    "????#.#????",
    "????#?#????",
]


def test_frontier_groups_counts_unexplored_directions():
    assert frontier_groups(make_state(CROSS)) == 4
    assert frontier_groups(make_state(ROOM)) == 0


def test_junction_fires_only_while_travelling():
    corridor = make_state(["#####", "?.@.#", "#####"])

    def arrive(s):
        msg, _ = map_message(CROSS)
        s.apply(msg)
        player(s, pos={"x": 5, "y": 4}, turn=11)
    out = run(corridor, action="travel", mode="travel", change=arrive)
    assert "junction" in kinds(out)
    corridor = make_state(["#####", "?.@.#", "#####"])
    assert "junction" not in kinds(run(corridor, action="explore", mode="explore", change=arrive))
