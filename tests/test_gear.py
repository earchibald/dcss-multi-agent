"""Gear choices (brain/gear.py), the wield and wear actions, and settled depths in the corpus labels."""

import math
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import make_state
from test_brain import ScriptedConn, mon, obs, point, step

from ladder.brain import corpus, gear
from ladder.brain.features import COMPONENTS
from ladder.brain.policy import BrainTiers, available, baseline
from ladder.conn import ActResult

WEAPON, ARMOUR = 0, 2


def gi(name, base, letter, plus=0, **kw):
    return {"base_type": base, "name": name, "plus": plus, "letter": letter, "quantity": 1, "useless": 0, **kw}


def game_state(inv, wielded=None, status=()):
    state = make_state(["@."])
    state.player["inv"] = {str(k): v for k, v in inv.items()}
    state.player["weapon_index"] = -1 if wielded is None else wielded
    state.player["status"] = [{"light": s} for s in status]
    return state


# --- weapon / armour ---------------------------------------------------------------------------

def test_weapon_matches_longest_name():
    great = gear.weapon(gi("+0 great mace", WEAPON, 97))
    mace = gear.weapon(gi("+0 mace", WEAPON, 97))
    assert great[1] == 2 and mace[1] == 1
    assert great[0] == pytest.approx(17 - 0.5 * 3) and mace[0] == 8


def test_armour_matches_longest_name():
    assert gear.armour(gi("+0 troll leather armour", ARMOUR, 97)) == ("body", 4)
    assert gear.armour(gi("+0 leather armour", ARMOUR, 97)) == ("body", 3)
    assert gear.armour(gi("+2 chain mail", ARMOUR, 97, plus=2)) == ("body", 10)


@pytest.mark.parametrize("name", ['the "Mace of Doom" (mace)', "+0 mace of the Gods", "+0 mace {rPois}",
                                  "+0 mace of distortion", "+0 mace of chaos"])
def test_weapon_skips_artefacts_and_bad_brands(name):
    assert gear.weapon(gi(name, WEAPON, 97)) is None


def test_ranking_skips_useless_unranked_and_wrong_type():
    assert gear.weapon(gi("+0 mace", WEAPON, 97, useless=1)) is None
    assert gear.weapon(gi("+0 hand axe", WEAPON, 97)) is None
    assert gear.weapon(gi("+0 mace", ARMOUR, 97)) is None
    assert gear.armour(gi("+0 chain mail", ARMOUR, 97, useless=1)) is None
    assert gear.armour(gi('"Lear\'s hauberk" (chain mail)', ARMOUR, 97)) is None
    assert gear.armour(gi("+0 mace", WEAPON, 97)) is None


def test_branded_weapon_scores_more():
    assert gear.weapon(gi("+0 mace of flaming", WEAPON, 97))[0] == 10


def test_initial_worn_and_kind_of():
    state = game_state({0: gi("+0 mace", WEAPON, 97), 1: gi("+0 leather armour", ARMOUR, 98),
                        2: gi("+0 buckler", ARMOUR, 99)})
    assert gear.initial_worn(state) == {"body": "1", "shield": "2"}
    assert gear.kind_of(state, "c") == ("shield", "2")
    assert gear.kind_of(state, "a") is None                    # a weapon
    assert gear.kind_of(state, "z") is None


# --- upgrades ----------------------------------------------------------------------------------

def test_better_mace_family_weapon_is_offered():
    state = game_state({0: gi("+0 mace", WEAPON, 97), 1: gi("+0 flail", WEAPON, 98)}, wielded=0)
    assert gear.upgrades(state, {})["wield"] == "b"


def test_worse_or_equal_weapon_is_not_offered():
    state = game_state({0: gi("+0 flail", WEAPON, 97), 1: gi("+0 mace", WEAPON, 98),
                        2: gi("+0 flail", WEAPON, 99)}, wielded=0)
    assert gear.upgrades(state, {})["wield"] is None
    state = game_state({0: gi("+0 mace", WEAPON, 97), 1: gi("+0 mace", WEAPON, 98)}, wielded=0)
    assert gear.upgrades(state, {})["wield"] is None


def test_unranked_wielded_weapon_is_never_replaced():
    state = game_state({0: gi("+0 hand axe", WEAPON, 97), 1: gi("+0 great mace", WEAPON, 98)}, wielded=0)
    assert gear.upgrades(state, {})["wield"] is None
    assert gear.upgrades(game_state({1: gi("+0 flail", WEAPON, 98)}), {})["wield"] is None   # bare hands


def test_two_hander_not_offered_with_a_shield():
    inv = {0: gi("+0 mace", WEAPON, 97), 1: gi("+0 great mace", WEAPON, 98)}
    assert gear.upgrades(game_state(inv, wielded=0), {"shield": "5"})["wield"] is None
    assert gear.upgrades(game_state(inv, wielded=0), {})["wield"] == "b"


def test_shield_not_offered_while_wielding_a_two_hander():
    inv = {0: gi("+0 great mace", WEAPON, 97), 1: gi("+0 buckler", ARMOUR, 98)}
    assert gear.upgrades(game_state(inv, wielded=0), {})["wear"] is None
    inv[0] = gi("+0 mace", WEAPON, 97)
    assert gear.upgrades(game_state(inv, wielded=0), {})["wear"] == "b"


def test_better_body_armour_is_offered_and_the_worn_piece_is_not():
    state = game_state({0: gi("+0 leather armour", ARMOUR, 97), 1: gi("+0 chain mail", ARMOUR, 98)})
    assert gear.upgrades(state, {"body": "0"})["wear"] == "b"
    assert gear.upgrades(state, {"body": "1"})["wear"] is None          # the chain mail is on already


def test_empty_slots_are_filled():
    state = game_state({0: gi("+0 leather armour", ARMOUR, 97), 1: gi("+0 cloak", ARMOUR, 98),
                        2: gi("+0 boots", ARMOUR, 99)})
    assert gear.upgrades(state, {"body": "0"})["wear"] in ("b", "c")
    assert gear.upgrades(state, {"body": "0", "cloak": "1"})["wear"] == "c"
    assert gear.upgrades(state, {"body": "0", "cloak": "1", "boots": "2"})["wear"] is None


def test_corrosion_does_not_make_a_worse_spare_look_better():
    # real bug: corroded flail showed -4, the +0 mace looked better, then the mace showed -4 ...
    inv = {0: gi("-4 flail", WEAPON, 97, plus=-4), 1: gi("+0 mace", WEAPON, 98)}
    assert gear.upgrades(game_state(inv, wielded=0, status=["Corr (-4)"]), {})["wield"] is None
    assert gear.upgrades(game_state(inv, wielded=0), {})["wield"] == "b"      # without the status it would


# --- policy ------------------------------------------------------------------------------------

def inv_obs(**over):
    return obs(inv={"heal": 0, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 0, **over})


def test_wield_and_wear_available_only_when_calm_and_better():
    got = available(inv_obs(wield=1, wear=1), False, set(), False)
    assert "wield" in got and "wear" in got
    assert "wear" not in available(inv_obs(wield=1, wear=0), False, set(), False)
    assert "wield" not in available(inv_obs(wield=0, wear=1), False, set(), False)


def test_wield_and_wear_not_available_with_hostiles_or_berserk():
    hostile = obs(inv={"heal": 0, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 0,
                       "wield": 1, "wear": 1}, n_hostiles=1, mons=[mon()])
    got = available(hostile, False, set(), False)
    assert "wield" not in got and "wear" not in got
    got = available(dict(inv_obs(wield=1, wear=1), status=["Berserk"]), False, set(), False)
    assert "wield" not in got and "wear" not in got
    assert "wield" not in available(inv_obs(wield=1), False, {"wield"}, False)


def test_old_observations_without_gear_keys_still_work():
    got = available(inv_obs(), False, set(), False)
    assert "wield" not in got and "wear" not in got and "explore" in got


def test_baseline_puts_gear_first_when_nothing_is_hostile():
    o = inv_obs(wield=1, wear=1)
    avail = available(o, False, set(), False)
    assert baseline(o, avail, False) == "wield"
    assert baseline(o, [a for a in avail if a != "wield"], False) == "wear"
    hostile = dict(o, n_hostiles=1, mons=[mon()])
    assert baseline(hostile, ["fight", "wield", "wear"], False) == "fight"


def gear_state():
    return game_state({0: gi("+0 mace", WEAPON, 97), 1: gi("+0 leather armour", ARMOUR, 98),
                       2: gi("+0 chain mail", ARMOUR, 99), 3: gi("+0 flail", WEAPON, 100)}, wielded=0)


def worn_batch(text):
    return [{"msg": "msgs", "messages": [{"text": text}]}]


def test_perform_wear_sends_the_key_then_the_letter_and_records_the_piece():
    tiers = BrainTiers()
    tiers.worn = {"body": "1"}
    conn = ScriptedConn([ActResult(blocking="menu"),
                         ActResult(messages=worn_batch("You finish putting on the chain mail."))])
    tiers.perform(SimpleNamespace(state=gear_state(), conn=conn), "wear")
    assert [k for k, _ in conn.sent] == [("W",), ("c",)]
    assert conn.sent[1][1] == {"through_menu": True}
    assert tiers.worn == {"body": "2"}


def test_perform_wear_forgets_a_piece_that_the_key_took_off():
    tiers = BrainTiers()
    tiers.worn = {"body": "1"}                     # believed to be on, so the wrong piece was named
    conn = ScriptedConn([ActResult(blocking="menu"), ActResult(messages=worn_batch("You finish taking off it."))])
    tiers.perform(SimpleNamespace(state=gear_state(), conn=conn), "wear")
    assert "body" not in tiers.worn


def test_perform_wear_leaves_worn_alone_without_a_message():
    tiers = BrainTiers()
    tiers.worn = {"body": "1"}
    conn = ScriptedConn([ActResult(blocking="menu"), ActResult(messages=worn_batch("Nothing happens."))])
    tiers.perform(SimpleNamespace(state=gear_state(), conn=conn), "wear")
    assert tiers.worn == {"body": "1"}


def test_perform_wield_sends_w_then_the_letter():
    tiers = BrainTiers()
    tiers.worn = {}
    conn = ScriptedConn([ActResult(blocking="menu")])
    tiers.perform(SimpleNamespace(state=gear_state(), conn=conn), "wield")
    assert [k for k, _ in conn.sent] == [("w",), ("d",)]


def test_perform_sends_nothing_when_nothing_is_better():
    state = game_state({0: gi("+0 flail", WEAPON, 97), 1: gi("+0 chain mail", ARMOUR, 98)}, wielded=0)
    tiers = BrainTiers()
    tiers.worn = {"body": "1"}
    conn = ScriptedConn()
    for action in ("wield", "wear"):
        assert tiers.perform(SimpleNamespace(state=state, conn=conn), action).messages == []
    assert conn.sent == []


# --- settled depth -----------------------------------------------------------------------------

def test_settled_depth_example():
    out = corpus.settled_depth(np.array([0, 100, 150, 300, 360, 400, 1000.]), np.array([1, 1, 2, 2, 3, 3, 3.]))
    assert out.tolist() == [1, 1, 1, 1, 2, 2, 3]


def depth_go(game):
    return corpus.label(game)[:, COMPONENTS.index("depth_go")]


def test_label_depth_reached_just_before_the_end_earns_nothing():
    turn = corpus.SETTLE_TURNS - 50
    game = {"id": "g", "steps": [step(point(0, 20, depth=1)), step(point(turn // 2, 20, depth=1)),
                                 step(point(turn, 20, depth=2))], "end": None}
    assert depth_go(game).tolist() == [0, 0, 0]
    ended = dict(game, end={"type": "end", "died": True, "turn": turn + 50})
    assert depth_go(ended)[:2].tolist() == [0, 0]               # died 50 turns after arriving: not settled


def test_label_depth_survived_past_settle_turns_earns_the_reward():
    late = 100 + corpus.SETTLE_TURNS + 50
    game = {"id": "g", "steps": [step(point(0, 20, depth=1)), step(point(100, 20, depth=2)),
                                 step(point(late, 20, depth=2))], "end": None}
    out = depth_go(game)
    assert out[0] == pytest.approx(math.exp(-late / corpus.TAU_GO))
    assert out[1] > 0
