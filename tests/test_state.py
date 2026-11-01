from helpers import add_monster, make_state, map_message

from ladder.state import BG_UNSEEN, GameState, strip_tags


def test_run_length_x_coordinates():
    state = GameState()
    state.apply({"msg": "map", "cells": [
        {"x": -1, "y": -7, "mf": 2, "g": "#"}, {"mf": 1, "g": "."}, {"mf": 1, "g": "."},
        {"x": 5, "y": -7, "mf": 26}, {"x": -1, "y": -6, "mf": 2},
    ]})
    assert state.cells[(0, -7)]["g"] == "."
    assert state.cells[(1, -7)]["mf"] == 1
    assert state.cells[(5, -7)]["mf"] == 26
    assert state.cells[(-1, -6)]["mf"] == 2


def test_partial_cell_update_keeps_other_fields():
    state = GameState()
    state.apply({"msg": "map", "cells": [{"x": 0, "y": 0, "mf": 1, "g": ".", "t": {"bg": 5, "ov": [1]}}]})
    state.apply({"msg": "map", "cells": [{"x": 0, "y": 0, "t": {"ov": [2]}}]})
    cell = state.cells[(0, 0)]
    assert cell["mf"] == 1 and cell["t"] == {"bg": 5, "ov": [2]}


def test_clear_starts_a_new_level():
    state = make_state(["@.."])
    seq = state.level_seq
    msg, _ = map_message(["..@"], clear=True)
    state.apply(msg)
    assert state.level_seq == seq + 1
    assert len(state.cells) == 3


def test_monster_info_merges_and_bare_ids_inherit():
    state = make_state(["@....", "....."])
    add_monster(state, (3, 0), 7, "orc", threat=1)
    state.apply({"msg": "map", "cells": [{"x": 4, "y": 1, "mon": {"id": 8}, "t": {"bg": 1}}]})
    names = sorted(m.name for m in state.hostiles())
    assert names == ["orc", "orc"]


def test_monster_moves_and_vacated_cell_clears():
    state = make_state(["@...."])
    add_monster(state, (4, 0), 3, "rat")
    state.apply({"msg": "map", "cells": [{"x": 4, "y": 0, "mon": None}, {"x": 3, "y": 0, "mon": {"id": 3}}]})
    [rat] = state.hostiles()
    assert rat.pos == (3, 0)


def test_remembered_monster_out_of_view_is_not_hostile_in_view():
    state = make_state(["@...."])
    add_monster(state, (4, 0), 3, "rat")
    state.apply({"msg": "map", "cells": [{"x": 4, "y": 0, "col": 8, "t": {"bg": 1 | BG_UNSEEN}}]})
    assert state.hostiles() == []
    assert state.cells[(4, 0)]["mon"] == 3          # still remembered


def test_plants_and_allies_are_not_hostile():
    state = make_state(["@...."])
    state.apply({"msg": "map", "cells": [{"x": 2, "y": 0, "mf": 11, "t": {"bg": 1},
                                          "mon": {"id": 1, "name": "plant", "att": 0, "typedata": {"no_exp": True}}}]})
    add_monster(state, (3, 0), 2, "hound", att=4)
    assert state.hostiles() == []
    assert len(state.monsters()) == 2


def test_uniques_are_flagged():
    state = make_state(["@...."])
    add_monster(state, (4, 0), 9, "Natasha", threat=2)
    [m] = state.hostiles()
    assert m.unique
    assert state.snapshot()["hostiles"][0]["unique"] is True


def test_player_partial_updates_and_place():
    state = make_state(["@"])
    state.apply({"msg": "player", "hp": 7, "status": [{"light": "Pois", "col": 9}]})
    assert state.hp == 7 and state.hp_max == 20
    assert state.place == "D:1"
    assert state.statuses == ["Pois"]


def test_messages_strip_tags_and_flag_death():
    assert strip_tags("<lightred>You encounter <white>an orc<lightgrey>.") == "You encounter an orc."
    state = GameState()
    state.apply({"msg": "msgs", "messages": [{"text": "<red>You die...<lightgrey>", "turn": 3}]})
    assert state.dead
