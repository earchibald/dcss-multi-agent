"""The local brain: features, policy, corpus labels, the numpy/torch round trip, and the result summaries."""

import json
import math
import random
import zlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import add_monster, make_state, player

from ladder.brain import corpus
from ladder.brain.cli import compare
from ladder.brain.features import (ACTIONS, COMPONENTS, FEATURE_VERSION, MAX_MONS, MON_DIM, N_ACTIONS,
                                   N_COMPONENTS, SELF_DIM, encode, inventory, observe, path, progress_depth)
from ladder.brain.net import ModelMismatch, TrainedNet, contract
from ladder.brain.policy import (BLOCK_TURNS, FORK_DONE, IDLE_LIMIT, ITEM_PROMPTS, REPLAY_DIVERGED, UNTIL_LEVEL,
                                 BrainTiers, Style, available, baseline)
from ladder.brain.selfplay import summarize
from ladder.conn import ActResult
from ladder.interrupts import Before, Interrupt
from ladder.reflex import Escalation, Reflex
from ladder.runlog import RunLog
from ladder.state import MF_STAIR_DOWN, MF_STAIR_UP
from ladder.travel import DIRECTIONS

POTIONS, SCROLLS = 7, 5


def item(name, base, qty=1, letter=97):
    return {"name": name, "quantity": qty, "base_type": base, "letter": letter}


def with_inv(state, **slots):
    state.apply({"msg": "player", "inv": {k.lstrip("s"): v for k, v in slots.items()}})
    return state


def obs(**over):
    """A hand-made observation (what features.observe returns): full HP, alone, a level left to explore."""
    base = {
        "turn": 100, "place": "Dungeon", "depth": 3, "hp": 20, "hp_max": 20, "mp": 0, "mp_max": 0,
        "xl": 3, "progress": 10, "ac": 2, "ev": 8, "sh": 0, "str": 12, "int": 8, "dex": 10,
        "poison_survival": 20, "status": [], "mons": [], "n_hostiles": 0,
        "inv": {"heal": 0, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 0},
        "on_down": False, "on_up": False, "dist_down": -1, "dist_up": -1, "open_neighbors": 4,
        "level_explored": False, "level_steps": 5, "level_turns": 50, "hp_delta": 0.0, "last_action": None,
    }
    base.update(over)
    return base


def mon(name="orc", dx=1, dy=0, threat=1, unique=False):
    return {"name": name, "dx": dx, "dy": dy, "threat": threat, "unique": unique}


# --- features ----------------------------------------------------------------

def test_inventory_classifies_consumables():
    state = make_state(["@."])
    with_inv(state, s0=item("potion of curing", POTIONS, 2, 97),
             s1=item("fizzy red potion", POTIONS, 3, 98),
             s2=item("scroll labelled XYZ ZYX", SCROLLS, 1, 99),
             s3=item("scroll of teleportation", SCROLLS, 2, 100),
             s4=item("potion of speed", POTIONS, 1, 101),          # known, but no action for it
             s5=item("a +0 dagger", 0, 1, 102))
    inv = inventory(state)
    assert (inv["heal"], inv["unknown_potions"], inv["unknown_scrolls"], inv["teleport"]) == (2, 3, 1, 2)
    assert inv["letters"] == {"heal": "a", "unknown_potions": "b", "unknown_scrolls": "c", "teleport": "d"}


def test_inventory_heal_wounds_and_unknown_tag():
    state = make_state(["@."])
    with_inv(state, s0=item("potion of heal wounds", POTIONS, 1, 97),
             s1=item("potion of {unknown}", POTIONS, 1, 98),
             s2=item("scroll of teleportation {unknown}", SCROLLS, 1, 99))
    inv = inventory(state)
    assert inv["heal"] == 1
    assert inv["unknown_potions"] == 1                    # tagged {unknown}: not trusted as identified
    assert inv["unknown_scrolls"] == 1 and inv["teleport"] == 0


def test_inventory_empty():
    inv = inventory(make_state(["@."]))
    assert inv == {"heal": 0, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 0, "letters": {}}


def test_inventory_ignores_empty_stacks():
    state = make_state(["@."])
    state.player["inv"] = {"0": item("potion of curing", POTIONS, 0)}
    assert inventory(state)["heal"] == 0


def test_encode_shapes_with_and_without_monsters():
    """Fails if a feature is added to encode without updating SELF_DIM / MON_DIM (or the reverse)."""
    full = obs(mons=[mon("orc", 1, 0), mon("Sigmund", -3, 2, 2, True)], n_hostiles=2,
               status=["Pois"], last_action="fight",
               inv={"heal": 1, "unknown_potions": 1, "unknown_scrolls": 1, "teleport": 1})
    for o in (full, obs()):
        s, m, mask = encode(o, ["explore", "fight"])
        assert s.shape == (SELF_DIM,) and s.dtype == np.float32
        assert m.shape == (MAX_MONS, MON_DIM) and m.dtype == np.float32
        assert mask.shape == (MAX_MONS,)
    s, m, mask = encode(full, ["fight"])
    assert mask.tolist() == [1, 1] + [0] * (MAX_MONS - 2)
    assert np.isfinite(s).all() and np.isfinite(m).all()
    assert m[2:].sum() == 0
    assert m[:2].any(axis=1).all()


def test_encode_caps_monsters_at_max():
    o = obs(mons=[mon(f"m{i}", i + 1, 0) for i in range(MAX_MONS + 4)], n_hostiles=MAX_MONS + 4)
    _, _, mask = encode(o, ["fight"])
    assert mask.sum() == MAX_MONS


def test_encode_marks_available_and_last_action():
    s, _, _ = encode(obs(last_action="rest"), ["explore", "rest"])
    n = len(s)
    assert s[n - 2 * N_ACTIONS:n - N_ACTIONS].tolist() == [float(a == "rest") for a in ACTIONS]
    assert s[n - N_ACTIONS:].tolist() == [float(a in ("explore", "rest")) for a in ACTIONS]


def test_observe_reads_a_game_state():
    state = make_state(["#####", "#@..>", "#####"], hp=12, hp_max=20, turn=77)
    add_monster(state, (3, 1), 4, "jackal", threat=1)
    o = observe(state, state.hostiles(), {"level_turn": 50, "last_action": "fight"})
    assert o["hp"] == 12 and o["turn"] == 77 and o["n_hostiles"] == 1
    assert o["mons"][0]["dx"] == 2 and o["mons"][0]["dy"] == 0
    assert o["dist_down"] == 3 and o["dist_up"] == -1
    assert o["level_turns"] == 27
    assert o["on_down"] is False
    json.dumps(o)                                          # a step log stores it as JSON
    encode(o, ["fight"])


def test_path_finds_the_stairs():
    state = make_state(["#####", "#@..>", "#####"])
    assert path(state, MF_STAIR_DOWN) == (DIRECTIONS[(1, 0)], 3)


def test_path_goes_around_walls():
    state = make_state(["@#>", "...", "###"])
    key, n = path(state, MF_STAIR_DOWN)
    assert n == 2 and key == DIRECTIONS[(1, 1)]            # diagonal down, then diagonal up


def test_path_none_when_walled_off():
    state = make_state(["@#>"])
    assert path(state, MF_STAIR_DOWN) == (None, -1)


def test_path_to_stairs_up():
    state = make_state(["<.@"])
    assert path(state, MF_STAIR_UP) == (DIRECTIONS[(-1, 0)], 2)


def test_progress_depth():
    assert progress_depth("Dungeon", 3) == 3
    assert progress_depth("", 3) == 3
    assert progress_depth("Lair", 2) == 11                 # branches count as deeper than early floors
    assert progress_depth("Zot", 2) == 16                  # an unlisted branch is deep
    assert progress_depth("Dungeon", 0) == 0


# --- state: inventory folding --------------------------------------------------

def test_inv_partial_update_keeps_the_rest_of_the_slot():
    state = make_state(["@."])
    state.apply({"msg": "player", "inv": {"0": item("potion of curing", POTIONS, 3)}})
    state.apply({"msg": "player", "inv": {"0": {"quantity": 2}}})
    slot = state.player["inv"]["0"]
    assert slot["quantity"] == 2 and slot["name"] == "potion of curing" and slot["base_type"] == POTIONS
    assert inventory(state)["heal"] == 2


def test_inv_slot_emptied_by_base_type_100_or_zero_quantity():
    state = make_state(["@."])
    state.apply({"msg": "player", "inv": {"0": item("potion of curing", POTIONS), "1": item("fizzy potion", POTIONS)}})
    state.apply({"msg": "player", "inv": {"0": {"base_type": 100}}})
    assert "0" not in state.player["inv"] and "1" in state.player["inv"]
    state.apply({"msg": "player", "inv": {"1": {"quantity": 0}}})
    assert state.player["inv"] == {}


def test_inv_survives_player_messages_without_inv():
    state = make_state(["@."])
    state.apply({"msg": "player", "inv": {"0": item("potion of curing", POTIONS)}})
    player(state, hp=5)
    assert state.player["inv"]["0"]["name"] == "potion of curing"
    assert state.hp == 5


def test_inv_freed_letter_can_be_refilled():
    state = make_state(["@."])
    state.apply({"msg": "player", "inv": {"0": item("a", POTIONS)}})
    state.apply({"msg": "player", "inv": {"0": {"base_type": 100}}})
    state.apply({"msg": "player", "inv": {"0": item("scroll of teleportation", SCROLLS, 1)}})
    assert inventory(state)["teleport"] == 1


# --- policy --------------------------------------------------------------------

def test_available_alone_and_with_hostiles():
    alone = available(obs(dist_down=5), False, set(), False)
    assert "explore" in alone and "descend" in alone
    assert "fight" not in alone and "wait" not in alone
    assert alone == [a for a in ACTIONS if a in alone]     # in ACTIONS order
    near = obs(n_hostiles=1, mons=[mon(dx=4)], dist_down=5)
    with_h = available(near, False, set(), False)
    assert "fight" in with_h and "wait" in with_h and "explore" not in with_h


def test_explore_is_not_offered_once_the_level_is_explored():
    assert "explore" in available(obs(), False, set(), False)
    assert "explore" not in available(obs(), True, set(), False)


def test_rest_only_when_alone_and_hurt():
    assert "rest" not in available(obs(), False, set(), False)
    assert "rest" in available(obs(hp=10), False, set(), False)
    assert "rest" in available(obs(mp=0, mp_max=5), False, set(), False)
    assert "rest" not in available(obs(hp=10), False, set(), True)             # rest stalled
    assert "rest" not in available(obs(hp=10, n_hostiles=1, mons=[mon()]), False, set(), False)


def test_flee_up_not_offered_on_dungeon_depth_one():
    hostile = dict(n_hostiles=1, mons=[mon(dx=3)], dist_up=4)
    assert "flee_up" not in available(obs(place="Dungeon", depth=1, **hostile), False, set(), False)
    assert "flee_up" not in available(obs(place="", depth=1, **hostile), False, set(), False)
    assert "flee_up" in available(obs(place="Dungeon", depth=2, **hostile), False, set(), False)
    assert "flee_up" in available(obs(place="Lair", depth=1, **hostile), False, set(), False)
    assert "flee_up" not in available(obs(place="Dungeon", depth=2, **{**hostile, "dist_up": -1}), False, set(), False)
    assert "flee_up" in available(obs(place="Dungeon", depth=2, on_up=True, n_hostiles=1, mons=[mon()]),
                                  False, set(), False)


def test_quaff_heal_needs_a_potion_and_a_wound():
    inv = {"heal": 1, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 0}
    assert "quaff_heal" in available(obs(hp=5, inv=inv), False, set(), False)
    assert "quaff_heal" not in available(obs(hp=20, inv=inv), False, set(), False)
    assert "quaff_heal" not in available(obs(hp=5), False, set(), False)


def test_unknown_and_teleport_items():
    inv = {"heal": 0, "unknown_potions": 1, "unknown_scrolls": 1, "teleport": 1}
    calm = available(obs(inv=inv), False, set(), False)
    assert "quaff_unknown" in calm and "read_unknown" in calm and "read_teleport" not in calm
    hot = available(obs(inv=inv, n_hostiles=1, mons=[mon()]), False, set(), False)
    assert "read_teleport" in hot


def test_wait_only_when_no_hostile_is_adjacent():
    assert "wait" in available(obs(n_hostiles=1, mons=[mon(dx=3, dy=1)]), False, set(), False)
    assert "wait" not in available(obs(n_hostiles=1, mons=[mon(dx=1, dy=1)]), False, set(), False)
    assert "wait" not in available(obs(n_hostiles=2, mons=[mon(dx=5), mon(dx=-1)]), False, set(), False)


def test_blocked_actions_are_removed():
    assert "explore" in available(obs(), False, set(), False)
    assert "explore" not in available(obs(), False, {"explore"}, False)


def test_baseline_quaffs_at_low_hp_with_hostiles():
    inv = {"heal": 1, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 0}
    o = obs(hp=8, inv=inv, n_hostiles=1, mons=[mon()])
    assert baseline(o, available(o, False, set(), False), False) == "quaff_heal"


def test_baseline_fights_otherwise():
    o = obs(hp=8, n_hostiles=1, mons=[mon()])                # hurt, but no potion
    assert baseline(o, available(o, False, set(), False), False) == "fight"
    o = obs(hp=20, n_hostiles=1, mons=[mon()])
    assert baseline(o, available(o, False, set(), False), False) == "fight"


def test_baseline_rests_when_hurt_and_alone():
    o = obs(hp=10)
    assert baseline(o, available(o, False, set(), False), False) == "rest"


def test_baseline_explores_then_descends():
    o = obs(dist_down=4)
    assert baseline(o, available(o, False, set(), False), False) == "explore"
    o = obs(dist_down=4, level_explored=True)
    assert baseline(o, available(o, True, set(), False), True) == "descend"


def test_baseline_falls_back_when_the_usual_choice_is_blocked():
    o = obs(dist_down=4)
    assert baseline(o, available(o, False, {"explore"}, False), False) == "descend"


class FakeNet:
    """Stands in for TrainedNet: fixed predictions, whatever the input."""

    def __init__(self, q=None, prior=None, counts=None, danger=0.1):
        self.q = np.zeros((N_ACTIONS, N_COMPONENTS), dtype=np.float32) if q is None else q
        self.prior = np.zeros(N_ACTIONS, dtype=np.float32) if prior is None else prior
        self.counts = {a: 1000 for a in ACTIONS} if counts is None else counts
        self.name = "fake"
        self.danger = danger
        self.calls = 0

    def forward(self, s, mons, mask):
        self.calls += 1
        assert s.shape == (SELF_DIM,)
        return self.q, self.danger, self.prior


def q_for(action, component="depth_go", value=1.0):
    q = np.zeros((N_ACTIONS, N_COMPONENTS), dtype=np.float32)
    q[ACTIONS.index(action), COMPONENTS.index(component)] = value
    return q


def stairs_state():
    """Unexplored level with a known downstairs: explore and descend are both possible; explore is the baseline."""
    return make_state(["#####", "#@..>", "#####"])


def test_without_a_net_the_baseline_is_played():
    tiers = BrainTiers(rng=random.Random(0))
    assert tiers.next_action(stairs_state()) == "explore"
    assert tiers.last["source"] == "baseline" and tiers.last["action"] == "explore"
    assert "values" not in tiers.last


def test_net_pick_beats_baseline_by_more_than_margin():
    tiers = BrainTiers(FakeNet(q_for("descend", value=1.0)), rng=random.Random(0))
    assert tiers.next_action(stairs_state()) == "travel"       # descend, off the stairs, is a "travel" step
    last = tiers.last
    assert last["action"] == "descend" and last["baseline"] == "explore" and last["source"] == "net"
    assert last["avail"] == ["explore", "descend"]
    assert set(last["values"]) == {"explore", "descend"} and last["values"]["descend"] > last["values"]["explore"]
    assert last["danger"] == 0.1
    assert last["obs"]["dist_down"] == 3
    assert tiers.choice == "descend" and tiers.last_action == "descend"


def test_baseline_kept_within_margin():
    tiers = BrainTiers(FakeNet(q_for("descend", value=0.04)), Style(margin=0.05), rng=random.Random(0))
    assert tiers.next_action(stairs_state()) == "explore"
    assert tiers.last["source"] == "net" and tiers.last["action"] == "explore"


def test_actions_with_too_few_training_examples_are_ignored():
    counts = {a: 1000 for a in ACTIONS} | {"descend": 3}
    tiers = BrainTiers(FakeNet(q_for("descend", value=5.0), counts=counts), Style(min_count=40), rng=random.Random(0))
    assert tiers.next_action(stairs_state()) == "explore"
    counts["descend"] = 40
    tiers = BrainTiers(FakeNet(q_for("descend", value=5.0), counts=counts), Style(min_count=40), rng=random.Random(0))
    assert tiers.next_action(stairs_state()) == "travel"


def test_the_baseline_is_trusted_even_when_never_seen():
    counts = dict.fromkeys(ACTIONS, 0)
    tiers = BrainTiers(FakeNet(q_for("explore", value=1.0), counts=counts), rng=random.Random(0))
    assert tiers.next_action(stairs_state()) == "explore"


def test_style_weights_change_the_choice_without_retraining():
    assert BrainTiers(FakeNet(q_for("descend", "died_soon", 1.0)), rng=random.Random(0)
                      ).next_action(stairs_state()) == "explore"          # the net fears descending
    q2 = q_for("descend", "xp_go", 1.0)
    assert BrainTiers(FakeNet(q2), Style(xp_go=2.0), rng=random.Random(0)).next_action(stairs_state()) == "travel"
    assert BrainTiers(FakeNet(q2), Style(xp_go=0.0), rng=random.Random(0)).next_action(stairs_state()) == "explore"


def test_human_prior_can_tip_the_choice():
    prior = np.zeros(N_ACTIONS, dtype=np.float32)
    prior[ACTIONS.index("descend")] = 5.0
    net = FakeNet(prior=prior)
    assert BrainTiers(net, Style(human=0.0), rng=random.Random(0)).next_action(stairs_state()) == "explore"
    assert BrainTiers(net, Style(human=0.5), rng=random.Random(0)).next_action(stairs_state()) == "travel"


def test_epsilon_one_picks_randomly_among_available():
    net = FakeNet()
    picks = set()
    for seed in range(40):
        tiers = BrainTiers(net, epsilon=1.0, rng=random.Random(seed))
        tiers.next_action(stairs_state())
        assert tiers.last["source"] == "random"
        assert tiers.last["baseline"] == "explore"
        picks.add(tiers.last["action"])
    assert picks == {"explore", "descend"}
    assert net.calls == 0


def test_a_lone_available_action_is_never_randomised():
    state = make_state(["@..."])                                # no stairs: only explore
    tiers = BrainTiers(FakeNet(), epsilon=1.0, rng=random.Random(0))
    assert tiers.next_action(state) == "explore"
    assert tiers.last["source"] == "baseline"


def test_hostiles_make_the_brain_fight():
    state = make_state(["@...."])
    add_monster(state, (1, 0), 1, "rat")
    tiers = BrainTiers(rng=random.Random(0))
    assert tiers.next_action(state) == "fight"
    tiers.approach = True
    assert tiers.next_action(state) == "approach"


def test_caught_in_a_web_struggles_without_a_choice():
    state = make_state(["@..."], status=[{"light": "Held"}])
    tiers = BrainTiers(rng=random.Random(0))
    assert tiers.next_action(state) == "struggle"
    assert tiers.last is None and tiers.choice is None


def test_nothing_possible_escalates():
    state = make_state(["@..."], hp=20)
    tiers = BrainTiers(rng=random.Random(0))
    tiers.level_explored = True                                 # no stairs known, nothing hurt: nothing to do
    assert tiers.next_action(state) == "wait"                   # ...but let a turn pass (gas clears)
    tiers.blocked["wait"] = UNTIL_LEVEL
    with pytest.raises(Escalation, match="nothing the brain can do"):
        tiers.next_action(state)


def test_no_progress_on_a_brain_action_blocks_it_instead_of_raising():
    state = stairs_state()
    tiers = BrainTiers(rng=random.Random(0))
    tiers.next_action(state)
    assert tiers.choice == "explore"
    tiers.observe("explore", Before.capture(state), state, [])    # no game time used: once is forgiven
    assert "explore" not in tiers.blocked
    tiers.observe("explore", Before.capture(state), state, [Interrupt("prompt", "ladder", {})])
    assert tiers.blocked["explore"] == state.turn + BLOCK_TURNS
    assert tiers.next_action(state) == "travel"                 # explore is off the table; descend is left
    assert tiers.last["avail"] == ["descend"]


def test_no_progress_on_an_item_blocks_until_the_next_level():
    state = make_state(["@..."])
    with_inv(state, s0=item("fizzy red potion", POTIONS, 1, 97))
    tiers = BrainTiers(rng=random.Random(0))
    tiers.choice = "quaff_unknown"
    tiers.observe("quaff_unknown", Before.capture(state), state, [Interrupt("no_progress", "ladder", {})])
    tiers.observe("quaff_unknown", Before.capture(state), state, [])
    assert tiers.blocked["quaff_unknown"] == UNTIL_LEVEL
    tiers.observe("explore", Before.capture(state), state, [Interrupt("level_change", "dcss", {})])
    assert tiers.blocked == {} and tiers.level_steps == 0


def test_no_progress_on_a_non_brain_action_still_raises():
    state = make_state(["@..."], status=[{"light": "Held"}])
    tiers = BrainTiers(rng=random.Random(0))
    assert tiers.next_action(state) == "struggle"
    with pytest.raises(Escalation):
        tiers.observe("struggle", Before.capture(state), state, [Interrupt("no_progress", "ladder", {})])


def test_describe():
    d = BrainTiers(FakeNet(), epsilon=0.2).describe()
    assert d["model"] == "fake" and d["epsilon"] == 0.2 and d["style"]["margin"] == 0.05
    assert BrainTiers().describe()["model"] is None


class ScriptedConn:
    def __init__(self, results=()):
        self.sent, self.results = [], list(results)

    def act(self, *keys, **kw):
        self.sent.append((keys, kw))
        return self.results.pop(0) if self.results else ActResult()


def test_perform_quaffs_the_right_letter_through_the_menu():
    state = make_state(["@..."])
    with_inv(state, s0=item("potion of curing", POTIONS, 1, 101))
    conn = ScriptedConn([ActResult(blocking="menu")])
    BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "quaff_heal")
    assert conn.sent == [(("q",), {}), (("e",), {"through_menu": True})]


def test_perform_sends_no_letter_when_the_verb_is_refused():
    # reading while silenced opens no menu; the letter alone would be a command of its own
    state = make_state(["@..."])
    with_inv(state, s0=item("scroll labelled FOO", SCROLLS, 1, 99))
    conn = ScriptedConn([ActResult()])
    BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "read_unknown")
    assert conn.sent == [(("r",), {})]


def test_perform_without_the_item_sends_nothing():
    conn = ScriptedConn()
    result = BrainTiers().perform(SimpleNamespace(state=make_state(["@..."]), conn=conn), "quaff_heal")
    assert conn.sent == [] and result.blocking is None


def test_perform_cancels_a_scroll_that_asks_for_a_target():
    state = make_state(["@..."])
    with_inv(state, s0=item("scroll labelled FOO", SCROLLS, 1, 97))
    first = ActResult(blocking="blink", messages=[{"text": "first"}])
    conn = ScriptedConn([ActResult(blocking="menu", messages=[{"text": "menu"}]), first,
                         ActResult(messages=[{"text": "second"}])])
    result = BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "read_unknown")
    assert [k for k, _ in conn.sent] == [("r",), ("a",), ("key_esc", "Y")]
    assert [m["text"] for m in result.messages] == ["menu", "first", "second"]


def test_perform_wait_and_flee_and_unknown_action():
    conn = ScriptedConn()
    tiers = BrainTiers()
    tiers.perform(SimpleNamespace(state=make_state(["@..."]), conn=conn), "wait")
    assert conn.sent[-1][0] == ("s",)
    tiers.perform(SimpleNamespace(state=make_state(["<@.."], hp=5), conn=conn), "flee_up")
    assert conn.sent[-1][0] == (DIRECTIONS[(-1, 0)],)
    on_stairs = make_state(["..<"])
    on_stairs.apply({"msg": "player", "pos": {"x": 2, "y": 0}})
    tiers.perform(SimpleNamespace(state=on_stairs, conn=conn), "flee_up")
    assert conn.sent[-1][0] == ("<",)
    assert tiers.perform(SimpleNamespace(state=on_stairs, conn=conn), "explore") is None


def test_reflex_hands_brain_actions_to_its_tiers(tmp_path):
    state = make_state(["@....", "....."])
    add_monster(state, (4, 0), 1, "rat")
    conn = ScriptedConn()
    reflex = Reflex(conn, state, RunLog(tmp_path), tiers=BrainTiers())
    reflex.step("wait")
    assert conn.sent[0][0] == ("s",)


# --- corpus --------------------------------------------------------------------

def point(turn, hp, hp_max=20, depth=1, xl=1, progress=0, place="Dungeon", **over):
    return obs(turn=turn, hp=hp, hp_max=hp_max, depth=depth, xl=xl, progress=progress, place=place, **over)


def step(o, action="explore", avail=None, source="baseline"):
    return {"obs": o, "avail": avail or [action], "baseline": action, "action": action, "source": source}


def test_label_death_soon():
    game = {"id": "g", "steps": [step(point(0, 20)), step(point(100, 10)), step(point(110, 5))],
            "end": {"type": "end", "died": True, "turn": 120}}
    out = corpus.label(game)
    assert out.shape == (3, N_COMPONENTS)
    died, lost, died_go = (COMPONENTS.index(c) for c in ("died_soon", "hp_lost", "died_go"))
    assert out[0, died] == 0 and out[0, lost] == 0
    assert out[1, died] == 1 and out[1, lost] == pytest.approx(0.5)      # 20 turns before the death: all of 10/20
    assert out[2, died] == 1 and out[2, lost] == pytest.approx(0.25)     # all of its current 5/20
    assert out[2, died_go] == pytest.approx(math.exp(-10 / corpus.TAU_DEATH))
    assert out[0, died_go] == pytest.approx(math.exp(-120 / corpus.TAU_DEATH))


def test_label_hp_drop_without_death():
    game = {"id": "g", "steps": [step(point(0, 20)), step(point(10, 8)), step(point(500, 8))], "end": None}
    out = corpus.label(game)
    assert out[0, COMPONENTS.index("hp_lost")] == pytest.approx(0.6)
    assert out[0, COMPONENTS.index("died_soon")] == 0 and out[0, COMPONENTS.index("died_go")] == 0


def test_label_depth_go_is_discounted_by_time():
    game = {"id": "g", "steps": [step(point(0, 20, depth=1)), step(point(100, 20, depth=2))], "end": None}
    out = corpus.label(game)
    assert out[0, COMPONENTS.index("depth_go")] == pytest.approx(math.exp(-100 / corpus.TAU_GO))
    assert out[1, COMPONENTS.index("depth_go")] == 0                     # nothing known after the last step


def test_label_xp_soon_and_go():
    game = {"id": "g", "steps": [step(point(0, 20, xl=1, progress=0)), step(point(50, 20, xl=2, progress=50))],
            "end": None}
    out = corpus.label(game)
    assert out[0, COMPONENTS.index("xp_soon")] == pytest.approx(1.5)
    assert out[0, COMPONENTS.index("xp_go")] > 1.4


def test_label_truncated_game_without_an_end_record():
    game = {"id": "g", "steps": [step(point(t, 20)) for t in (0, 10, 20)], "end": None}
    out = corpus.label(game)
    assert out.shape == (3, N_COMPONENTS) and np.isfinite(out).all()
    assert out[:, COMPONENTS.index("died_soon")].sum() == 0


def test_label_end_record_with_state_is_used_as_a_last_point():
    end = {"type": "end", "died": False, "turn": 40, "hp": 20, "hp_max": 20, "xl": 1, "progress": 0,
           "place": "Dungeon", "depth": 2}
    game = {"id": "g", "steps": [step(point(0, 20, depth=1))], "end": end}
    assert corpus.label(game)[0, COMPONENTS.index("depth_go")] > 0


def write_game(directory, game_no, rows, died=False, end_turn=None, actions=("explore", "fight", "rest", "descend")):
    with (directory / "steps.jsonl").open("a") as f:
        for i, (turn, hp, depth) in enumerate(rows):
            hostile = i % 3 == 0
            o = point(turn, hp, depth=depth, mons=[mon("orc", 2, 0)] if hostile else [], n_hostiles=int(hostile))
            f.write(json.dumps({"game": game_no, **step(o, actions[i % len(actions)], list(actions))}) + "\n")
        f.write(json.dumps({"game": game_no, "type": "end", "died": died, "turn": end_turn or rows[-1][0]}) + "\n")


def synthetic_corpus(tmp_path, games=12, length=30, seed=0):
    rng = random.Random(seed)
    root = tmp_path / "runs"
    root.mkdir()
    for g in range(games):
        turn, hp, depth, rows = 0, 20, 1, []
        for _ in range(length):
            turn += rng.randint(1, 40)
            hp = max(1, min(20, hp + rng.randint(-6, 5)))
            depth += rng.random() < 0.1
            rows.append((turn, hp, depth))
        write_game(root, g, rows, died=g % 3 == 0, end_turn=rows[-1][0] + 5)
    return root


def test_build_writes_consistent_arrays_and_meta(tmp_path):
    root = synthetic_corpus(tmp_path)
    out = tmp_path / "out" / "c.npz"
    meta = corpus.build([root], out)
    data = np.load(out)
    n = meta["rows"]
    assert n == 12 * 30
    for key in ("self", "mons", "mask", "avail", "action", "base", "q", "human", "val"):
        assert data[key].shape[0] == n, key
    assert data["self"].shape == (n, SELF_DIM)
    assert data["mons"].shape == (n, MAX_MONS, MON_DIM)
    assert data["q"].shape == (n, N_COMPONENTS)
    assert data["avail"].shape == (n, N_ACTIONS)
    assert np.isfinite(data["self"]).all() and np.isfinite(data["q"]).all()
    saved = json.loads(Path(f"{out}.meta.json").read_text())
    assert saved == meta
    for key, want in contract().items():
        assert saved[key] == want
    assert saved["games"] == 12 and saved["deaths"] == 4
    assert saved["val_rows"] == int(data["val"].sum())
    assert sum(saved["by_action"].values()) == n and saved["by_source"] == {"baseline": n}


def test_build_validation_split_is_by_game(tmp_path):
    root = synthetic_corpus(tmp_path)
    out = tmp_path / "c.npz"
    corpus.build([root], out)
    val = np.load(out)["val"]
    pos = 0
    for g in corpus.read_games([root]):                      # every game is wholly in or wholly out, by its hash
        rows = val[pos:pos + len(g["steps"])]
        seed = corpus.seed_of(g["steps"][0]["game"])             # held out by dungeon, so forks follow their game
        key = str(seed) if seed >= 0 else g["id"]
        assert rows.all() == (zlib.crc32(key.encode()) % corpus.VAL_FOLD == 0) and (rows.all() or not rows.any())
        pos += len(g["steps"])
    assert pos == len(val)


def test_build_skips_unknown_actions_and_torn_lines(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    write_game(root, 1, [(0, 20, 1), (10, 20, 1), (20, 20, 1)])
    with (root / "steps.jsonl").open("a") as f:
        f.write(json.dumps({"game": 2, **step(point(0, 20), "juggle")}) + "\n")
        f.write('{"game": 2, "obs": {"tur')                  # a game killed mid-write
    meta = corpus.build([root], tmp_path / "c.npz")
    assert meta["rows"] == 3 and meta["games"] == 2


def test_build_marks_human_rows(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    (root / "steps.jsonl").write_text("".join(
        json.dumps({"game": 1, **step(point(t, 20), "explore", source="human")}) + "\n" for t in (0, 5, 9)))
    out = tmp_path / "c.npz"
    corpus.build([root], out)
    assert np.load(out)["human"].tolist() == [1.0, 1.0, 1.0]


# --- net + train round trip ------------------------------------------------------

@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    pytest.importorskip("torch")
    from ladder.brain.train import train
    tmp = tmp_path_factory.mktemp("train")
    root = synthetic_corpus(tmp, games=14, length=30, seed=1)
    cpath = tmp / "c.npz"
    corpus.build([root], cpath)
    model = tmp / "m.json"
    info = train(cpath, model, epochs=2, hidden=16, log=lambda *_: None)
    return model, info


def test_train_writes_a_model_that_matches_torch(trained):
    from ladder.brain.net import check_parity
    model, info = trained
    assert model.exists() and model.with_suffix(".parity.json").exists()
    assert info["rows"] > 0 and info["val_rows"] > 0 and info["params"] > 0
    assert check_parity(model) < 2e-3


def test_trained_net_forward_shapes(trained):
    model, _ = trained
    net = TrainedNet.load(model)
    assert net.name == "m" and set(net.counts) == set(ACTIONS)
    for o in (obs(mons=[mon(), mon("bat", 3, 3)], n_hostiles=2), obs()):
        q, danger, prior = net.forward(*encode(o, ["explore", "fight"]))
        assert q.shape == (N_ACTIONS, N_COMPONENTS)
        assert isinstance(danger, float) and 0.0 <= danger <= 1.0
        assert prior.shape == (N_ACTIONS,)
        assert np.isfinite(q).all() and np.isfinite(prior).all()


def test_trained_net_drives_brain_tiers(trained):
    model, _ = trained
    tiers = BrainTiers(TrainedNet.load(model), rng=random.Random(0))
    assert tiers.next_action(stairs_state()) in ("explore", "travel")
    assert tiers.last["source"] == "net"


def test_model_with_another_feature_version_is_refused(trained, tmp_path):
    model, _ = trained
    data = json.loads(model.read_text())
    assert data["feature_version"] == FEATURE_VERSION
    data["feature_version"] = FEATURE_VERSION + 1
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data))
    with pytest.raises(ModelMismatch, match="feature_version"):
        TrainedNet.load(bad)


def test_model_with_changed_actions_or_wrong_format_is_refused(trained, tmp_path):
    model, _ = trained
    data = json.loads(model.read_text())
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({**data, "actions": data["actions"][:-1]}))
    with pytest.raises(ModelMismatch, match="actions"):
        TrainedNet.load(bad)
    bad.write_text(json.dumps({**data, "format": "something-else"}))
    with pytest.raises(ModelMismatch):
        TrainedNet.load(bad)


def test_train_refuses_a_corpus_built_for_another_contract(tmp_path):
    pytest.importorskip("torch")
    from ladder.brain.train import train
    root = synthetic_corpus(tmp_path, games=6, length=10)
    cpath = tmp_path / "c.npz"
    corpus.build([root], cpath)
    meta_path = Path(f"{cpath}.meta.json")
    meta = json.loads(meta_path.read_text())
    meta["feature_version"] += 1
    meta_path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="rebuild"):
        train(cpath, tmp_path / "m.json", epochs=1, hidden=8, log=lambda *_: None)


# --- self-play summaries -----------------------------------------------------------

def result(game, depth, xl=3, turn=1000, died=False, ended_by="limit"):
    return {"game": game, "max_depth": depth, "xl": xl, "turn": turn, "died": died, "ended_by": ended_by}


def test_summarize():
    results = [result(1, 2, 3, 1000, True, "died"), result(2, 4, 5, 3000, False, "limit"),
               result(3, 3, 4, 2000, True, "died"), {"game": 4, "ended_by": "hung"}]
    s = summarize(results)
    assert s["games"] == 3 and s["lost"] == 1
    assert s["mean_depth"] == 3.0 and s["median_depth"] == 3 and s["max_depth"] == 4
    assert s["mean_xl"] == 4.0 and s["mean_turns"] == 2000 and s["died"] == 2
    assert s["ended_by"] == {"died": 2, "limit": 1, "hung": 1}


def test_summarize_when_nothing_was_played():
    assert summarize([]) == {"games": 0, "lost": 0}
    assert summarize([{"game": 1, "ended_by": "hung"}]) == {"games": 0, "lost": 1}


def test_compare_seed_by_seed():
    a = {"results": [result(1, 5), result(2, 3), result(3, 2), result(4, 9), {"game": 5, "ended_by": "hung"}]}
    b = {"results": [result(1, 4), result(2, 3), result(3, 6), result(5, 1), {"game": 6, "ended_by": "hung"}]}
    assert compare(a, b) == {"seeds": 3, "deeper": 1, "same": 1, "shallower": 1}
    assert compare(b, a) == {"seeds": 3, "deeper": 1, "same": 1, "shallower": 1}
    assert compare({"results": []}, b) == {"seeds": 0, "deeper": 0, "same": 0, "shallower": 0}


# --- forks: replaying a script ------------------------------------------------------

class NoRandom(random.Random):
    """An rng that fails the test if anything asks it for a number."""

    def random(self):
        raise AssertionError("the rng was consulted")

    def choice(self, seq):
        raise AssertionError("the rng was consulted")


def test_script_is_replayed_in_order_and_its_last_choice_is_the_fork():
    state = stairs_state()
    tiers = BrainTiers(FakeNet(q_for("descend", value=5.0)), epsilon=1.0, rng=NoRandom(),
                       script=["descend", "explore", "descend"])
    picks = []
    for _ in range(3):
        tiers.next_action(state)
        picks.append((tiers.last["action"], tiers.last["source"]))
    assert picks == [("descend", "replay"), ("explore", "replay"), ("descend", "fork")]
    assert tiers.fork_turn == state.turn
    # the script is spent: back to the usual choosing (epsilon 1.0 now means a random pick)
    tiers.rng = random.Random(0)
    tiers.next_action(state)
    assert tiers.last["source"] == "random"
    # ...and with epsilon 0 and no net, the baseline
    tiers = BrainTiers(rng=random.Random(0), script=["descend"])
    tiers.next_action(state)
    assert tiers.last["source"] == "fork"
    tiers.next_action(state)
    assert tiers.last["source"] == "baseline" and tiers.last["action"] == "explore"


def test_script_with_a_net_returns_to_the_net_afterwards():
    state = stairs_state()
    tiers = BrainTiers(FakeNet(q_for("descend", value=1.0)), rng=random.Random(0), script=["explore"])
    tiers.next_action(state)
    assert tiers.last["source"] == "fork"
    tiers.next_action(state)
    assert tiers.last["source"] == "net" and tiers.last["action"] == "descend"


def test_script_action_that_is_not_available_diverges():
    tiers = BrainTiers(rng=random.Random(0), script=["explore", "fight"])
    state = stairs_state()
    tiers.next_action(state)
    with pytest.raises(Escalation, match=REPLAY_DIVERGED):
        tiers.next_action(state)


def test_fork_horizon_ends_the_game_after_fork_turn_plus_horizon():
    state = stairs_state()                                     # turn 10
    tiers = BrainTiers(rng=random.Random(0), script=["explore"], horizon=100)
    tiers.next_action(state)
    assert tiers.fork_turn == 10
    player(state, turn=110)
    tiers.next_action(state)                                   # exactly at the horizon: still playing
    player(state, turn=111)
    with pytest.raises(Escalation, match=FORK_DONE):
        tiers.next_action(state)


def test_no_horizon_plays_on_and_the_horizon_is_measured_from_the_fork():
    state = stairs_state()
    tiers = BrainTiers(rng=random.Random(0), script=["explore"], horizon=0)
    tiers.next_action(state)
    player(state, turn=10 ** 6)
    tiers.next_action(state)
    # before the fork point is reached there is no horizon to measure from
    tiers = BrainTiers(rng=random.Random(0), script=["explore", "explore"], horizon=5)
    tiers.next_action(state)
    player(state, turn=10 ** 7)
    tiers.next_action(state)                                   # the fork choice itself, taken at a late turn
    assert tiers.last["source"] == "fork"


# --- the idle fallback ---------------------------------------------------------------

def stuck_state():
    return make_state(["@..."], hp=20)


def test_idle_waits_when_nothing_else_is_possible():
    tiers = BrainTiers(rng=random.Random(0))
    tiers.level_explored = True
    assert tiers.next_action(stuck_state()) == "wait"
    assert tiers.last["avail"] == ["wait"] and tiers.last["action"] == "wait"
    assert tiers.idle == 1


def test_every_tenth_idle_wait_looks_at_the_level_again():
    state = stuck_state()
    tiers = BrainTiers(rng=random.Random(0))
    tiers.level_explored = True
    tiers.blocked["explore"] = UNTIL_LEVEL
    for _ in range(9):
        assert tiers.next_action(state) == "wait"
    assert tiers.level_explored and "explore" in tiers.blocked
    assert tiers.next_action(state) == "wait"                  # the tenth
    assert tiers.idle == 10 and tiers.level_explored is False and "explore" not in tiers.blocked
    assert tiers.next_action(state) == "explore"


def test_idle_limit_escalates():
    state = stuck_state()
    tiers = BrainTiers(rng=random.Random(0))
    tiers.level_explored = True
    tiers.idle = IDLE_LIMIT - 1
    assert tiers.next_action(state) == "wait"
    tiers.level_explored = True                                # the reset at 60 would otherwise offer explore
    with pytest.raises(Escalation, match="nothing the brain can do"):
        tiers.next_action(state)


def test_time_passing_on_another_action_resets_idle_but_waiting_does_not():
    state = stairs_state()
    tiers = BrainTiers(rng=random.Random(0))
    tiers.idle = 5
    tiers.choice = "wait"
    before = Before.capture(state)
    player(state, turn=state.turn + 1)
    tiers.observe("wait", before, state, [])
    assert tiers.idle == 5
    tiers.choice = "explore"
    before = Before.capture(state)
    player(state, turn=state.turn + 3)
    tiers.observe("explore", before, state, [])
    assert tiers.idle == 0


# --- stall blocking ------------------------------------------------------------------

def test_two_timeless_actions_in_a_row_block_it_for_a_while():
    state = stairs_state()
    tiers = BrainTiers(rng=random.Random(0))
    tiers.choice = "descend"
    for _ in range(2):
        tiers.observe("travel", Before.capture(state), state, [])
    assert tiers.blocked == {"descend": state.turn + BLOCK_TURNS}
    assert tiers.stalls == {}
    assert tiers.level_explored is False                       # only a blocked "fight" gives up on exploring


def test_blocked_item_actions_stay_blocked_until_the_next_level():
    state = make_state(["@..."])
    tiers = BrainTiers(rng=random.Random(0))
    for name in ("read_unknown", "quaff_unknown", "quaff_heal", "read_teleport"):
        tiers.choice = name
        for _ in range(2):
            tiers.observe(name, Before.capture(state), state, [])
        assert tiers.blocked[name] == UNTIL_LEVEL


def test_blocked_fight_gives_up_exploring_and_ignores_the_visible_hostiles():
    state = make_state(["@...."])
    add_monster(state, (3, 0), 7, "eel")
    add_monster(state, (4, 0), 8, "eel")
    tiers = BrainTiers(rng=random.Random(0))
    tiers.choice = "fight"
    tiers.observe("fight", Before.capture(state), state, [])
    assert not tiers.level_explored and tiers.ignored == set()
    tiers.observe("fight", Before.capture(state), state, [])
    assert tiers.blocked["fight"] == state.turn + BLOCK_TURNS
    assert tiers.level_explored is True and tiers.ignored == {7, 8}


def test_a_turn_passing_clears_the_stall_count():
    state = stairs_state()
    tiers = BrainTiers(rng=random.Random(0))
    tiers.choice = "explore"
    tiers.observe("explore", Before.capture(state), state, [])
    assert tiers.stalls == {"explore": 1}
    before = Before.capture(state)
    player(state, turn=state.turn + 1)
    tiers.observe("explore", before, state, [])
    assert tiers.stalls == {}
    tiers.observe("explore", Before.capture(state), state, [])   # a single timeless one again: forgiven
    assert tiers.blocked == {}


def test_a_new_level_counts_as_time_passing():
    state = stairs_state()
    tiers = BrainTiers(rng=random.Random(0))
    tiers.choice = "descend"
    tiers.stalls["descend"] = 1
    before = Before.capture(state)
    state.level_seq += 1
    tiers.observe("descend", before, state, [])
    assert tiers.blocked == {} and tiers.stalls == {}


# --- available: berserk, silence, confusion ----------------------------------------------

def hostile_obs(**over):
    return obs(n_hostiles=1, mons=[mon(dx=3)], **over)


def test_berserk_needs_trog_hostiles_and_no_rage_or_exhaustion():
    assert "berserk" in available(hostile_obs(god="Trog"), False, set(), False)
    assert "berserk" not in available(hostile_obs(god="Okawaru"), False, set(), False)
    assert "berserk" not in available(hostile_obs(), False, set(), False)
    assert "berserk" not in available(obs(god="Trog"), False, set(), False)              # nobody to fight
    assert "berserk" not in available(hostile_obs(god="Trog", status=["Berserk"]), False, set(), False)
    assert "berserk" not in available(hostile_obs(god="Trog", status=["-Berserk"]), False, set(), False)
    assert "berserk" in available(hostile_obs(god="Trog", status=["Pois"]), False, set(), False)


ALL_ITEMS = {"heal": 1, "unknown_potions": 1, "unknown_scrolls": 1, "teleport": 1}


def test_no_potions_or_scrolls_while_berserk():
    o = hostile_obs(hp=5, inv=ALL_ITEMS)
    free = available(o, False, set(), False)
    assert {"quaff_heal", "quaff_unknown", "read_unknown", "read_teleport"} <= set(free)
    raging = available({**o, "status": ["Berserk"]}, False, set(), False)
    assert not {"quaff_heal", "quaff_unknown", "read_unknown", "read_teleport"} & set(raging)
    assert "fight" in raging


def test_no_reading_while_silenced_or_confused_but_potions_are_fine():
    o = hostile_obs(hp=5, inv=ALL_ITEMS)
    for status in ("silenced", "Conf"):
        a = available({**o, "status": [status]}, False, set(), False)
        assert "read_unknown" not in a and "read_teleport" not in a, status
        assert "quaff_heal" in a and "quaff_unknown" in a, status


# --- through_menu and perform ---------------------------------------------------------------

def test_through_menu_sends_the_letter_only_into_a_menu():
    conn = ScriptedConn([ActResult(blocking="menu", messages=[{"text": "a"}]), ActResult(messages=[{"text": "b"}])])
    result = BrainTiers.through_menu(conn, "q", "c")
    assert conn.sent == [(("q",), {}), (("c",), {"through_menu": True})]
    assert [m["text"] for m in result.messages] == ["a", "b"]
    for blocking in (None, "more", "text_input"):
        conn = ScriptedConn([ActResult(blocking=blocking)])
        assert BrainTiers.through_menu(conn, "q", "c").blocking == blocking
        assert conn.sent == [(("q",), {})]


def test_berserk_is_sent_as_an_ability_only_once_the_menu_is_up():
    state = make_state(["@..."])
    conn = ScriptedConn([ActResult(blocking="menu")])
    BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "berserk")
    assert conn.sent == [(("a",), {}), (("a",), {"through_menu": True})]
    conn = ScriptedConn([ActResult()])                         # no menu (not a Trog worshipper, say)
    BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "berserk")
    assert conn.sent == [(("a",), {})]


@pytest.mark.parametrize("reason", sorted(ITEM_PROMPTS))
def test_item_prompts_are_cancelled(reason):
    state = make_state(["@..."])
    with_inv(state, s0=item("scroll labelled FOO", SCROLLS, 1, 97))
    conn = ScriptedConn([ActResult(blocking="menu"), ActResult(blocking=reason)])
    BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "read_unknown")
    assert [k for k, _ in conn.sent][-1] == ("key_esc", "Y")


def test_other_prompts_after_an_item_are_left_for_reflex():
    # the potion's turn killed something and the level-up stat prompt came up: Esc would not answer it
    state = make_state(["@..."])
    with_inv(state, s0=item("fizzy red potion", POTIONS, 1, 97))
    stat = ActResult(blocking="text_input", messages=[{"text": "Increase (S)trength"}])
    conn = ScriptedConn([ActResult(blocking="menu"), stat])
    result = BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "quaff_unknown")
    assert result.blocking == "text_input"
    assert [k for k, _ in conn.sent] == [("q",), ("a",)]


# --- the shop guard --------------------------------------------------------------------------

def test_an_unvisited_shop_is_visited_unless_berserk():
    rows = ["@.∩.."]
    assert BrainTiers(rng=random.Random(0)).next_action(make_state(rows)) == "shop"
    raging = make_state(rows, status=[{"light": "Berserk"}])
    tiers = BrainTiers(rng=random.Random(0))
    assert tiers.next_action(raging) == "wait"
    assert tiers.last is None                                  # not a brain choice


def test_no_shop_visit_once_the_level_is_explored_or_hostiles_are_about():
    rows = ["@.∩.."]
    tiers = BrainTiers(rng=random.Random(0))
    tiers.level_explored = True
    assert tiers.next_action(make_state(rows)) != "shop"
    state = make_state(rows)
    add_monster(state, (4, 0), 1, "rat")
    assert BrainTiers(rng=random.Random(0)).next_action(state) == "fight"


# --- corpus: seeds, forks, holdout --------------------------------------------------------------

def test_seed_of():
    assert corpus.seed_of(123) == 123
    assert corpus.seed_of("123-45-fight") == 123
    assert corpus.seed_of("7") == 7
    assert corpus.seed_of("human1") == -1
    assert corpus.seed_of("play3-x") == -1
    assert corpus.seed_of("-5") == -1


def put(directory, game, sources, end=None, actions=("explore", "fight"), numbered=True, d=1):
    """Append a game's steps (one per entry of `sources`) and an end record to directory/steps.jsonl."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "steps.jsonl").open("a") as f:
        for i, src in enumerate(sources):
            o = point(10 * i, 20, depth=d)
            row = {"game": game, **step(o, actions[i % len(actions)], list(actions), source=src)}
            if numbered:
                row["step"] = i + 1
            f.write(json.dumps(row) + "\n")
        f.write(json.dumps({"type": "end", "game": game, "died": False, "turn": 10 * len(sources), **(end or {})}) + "\n")


def test_read_games_drops_evaluation_seeds(tmp_path):
    put(tmp_path, corpus.HOLDOUT_SEED - 1, ["baseline"] * 2)
    put(tmp_path, corpus.HOLDOUT_SEED, ["baseline"] * 2)
    put(tmp_path, f"{corpus.HOLDOUT_SEED + 5}-3-fight", ["replay", "fork"])
    assert [g["steps"][0]["game"] for g in corpus.read_games([tmp_path])] == [corpus.HOLDOUT_SEED - 1]


def test_read_games_skips_replayed_steps_and_drops_diverged_or_all_replay_forks(tmp_path):
    put(tmp_path, "5-3-fight", ["replay", "replay", "fork", "baseline"])
    put(tmp_path, "5-4-rest", ["replay", "replay", "replay"])                     # nothing of its own
    put(tmp_path, "5-9-wait", ["replay", "fork"], end={"escalation": f"{REPLAY_DIVERGED} at choice 2: wait not in []"})
    put(tmp_path, "5-2-rest", ["replay", "fork"], end={"escalation": "something else"})
    put(tmp_path, 6, ["baseline", "baseline"])
    games = {str(g["steps"][0]["game"]): g for g in corpus.read_games([tmp_path])}
    assert set(games) == {"5-3-fight", "5-2-rest", "6"}
    assert games["5-3-fight"]["skip"] == 2 and games["5-2-rest"]["skip"] == 1 and games["6"]["skip"] == 0


def test_build_emits_only_a_forks_own_rows(tmp_path):
    root = tmp_path / "runs"
    put(root, "5-3-fight", ["replay", "replay", "fork", "baseline"])
    out = tmp_path / "c.npz"
    meta = corpus.build([root], out)
    data = np.load(out)
    assert meta["rows"] == 2 and meta["games"] == 1
    assert data["fork"].tolist() == [1.0, 0.0]
    assert data["human"].tolist() == [0.0, 0.0]
    assert meta["by_source"] == {"fork": 1, "baseline": 1}
    assert data["q"].shape == (2, N_COMPONENTS)


def test_game_ids_are_relative_to_the_root(tmp_path):
    import shutil
    a, b = tmp_path / "a" / "runs", tmp_path / "b" / "elsewhere"
    for g in range(15):
        put(a / "brain" / f"g{g}", "human", ["baseline"] * 3)       # no seed, so the split goes by where it is
    shutil.copytree(a, b)
    ids_a = [g["id"] for g in corpus.read_games([a])]
    ids_b = [g["id"] for g in corpus.read_games([b])]
    assert ids_a == ids_b and len(ids_a) == 15
    assert all(str(tmp_path) not in i for i in ids_a)
    corpus.build([a], tmp_path / "a.npz")
    corpus.build([b], tmp_path / "b.npz")
    va, vb = np.load(tmp_path / "a.npz")["val"], np.load(tmp_path / "b.npz")["val"]
    assert va.tolist() == vb.tolist() and va.any() and not va.all()


# --- forks.plan ------------------------------------------------------------------------------------

CYCLE = ("explore", "fight", "rest")


def record_game(directory, game, n=100, died=True, single_at=4):
    """A seeded game of n steps cycling through CYCLE; step index `single_at` has one choice only."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "steps.jsonl").open("a") as f:
        for i in range(n):
            a = list(CYCLE) if i != single_at else [CYCLE[i % 3]]
            row = {"game": game, "step": i + 1, **step(point(5 * i, 20), CYCLE[i % 3], a)}
            f.write(json.dumps(row) + "\n")
        f.write(json.dumps({"type": "end", "game": game, "died": died, "turn": 5 * n}) + "\n")


def plan_root(tmp_path):
    root = tmp_path / "runs"
    record_game(root / "g7", 7)
    record_game(root / "g8", 8, n=30, died=False)
    return root


def spot(job):
    return job["id"].rsplit("-", 1)[0]


def test_plan_makes_jobs_from_recorded_actions_and_alternatives(tmp_path):
    from ladder.brain.forks import plan
    jobs = plan([plan_root(tmp_path)], 6, alternatives=2, horizon=300, seed=3)
    assert jobs and all(j["horizon"] == 300 for j in jobs)
    for j in jobs:
        seed, at, alt = j["id"].split("-")
        assert int(seed) == j["seed"] and int(at) == len(j["script"]) and j["script"][-1] == alt
        i = int(at) - 1
        assert j["script"][:-1] == [CYCLE[k % 3] for k in range(i)]
        assert alt != CYCLE[i % 3] and alt in CYCLE
        assert i != 4                                           # that step had a single choice


def test_plan_caps_alternatives_and_points(tmp_path):
    from ladder.brain.forks import plan
    root = plan_root(tmp_path)
    jobs = plan([root], 5, alternatives=1, seed=0)
    assert len(jobs) == 5 and len({spot(j) for j in jobs}) == 5       # one fork per point, five points
    jobs = plan([root], 5, alternatives=2, seed=0)
    assert len({spot(j) for j in jobs}) == 5 and len(jobs) == 10


def test_plan_late_share_takes_points_from_the_last_choices_before_a_death(tmp_path):
    from ladder.brain.forks import LATE_WINDOW, plan
    root = tmp_path / "runs"
    record_game(root, 7, n=200, died=True)
    jobs = plan([root], 8, late_share=1.0, seed=2)
    assert len({spot(j) for j in jobs}) == 8
    assert all(len(j["script"]) - 1 >= 200 - LATE_WINDOW for j in jobs)
    # without a death nothing is late, so the points come from anywhere
    alive = tmp_path / "alive"
    record_game(alive, 9, n=200, died=False)
    steps = {len(j["script"]) - 1 for j in plan([alive], 30, late_share=1.0, seed=2)}
    assert min(steps) < 200 - LATE_WINDOW


def test_plan_is_deterministic_per_seed(tmp_path):
    from ladder.brain.forks import plan
    root = plan_root(tmp_path)
    assert plan([root], 6, seed=11) == plan([root], 6, seed=11)
    assert plan([root], 6, seed=11) != plan([root], 6, seed=12)


def test_plan_uses_only_whole_seeded_self_play_games(tmp_path):
    from ladder.brain.forks import plan
    root = tmp_path / "runs"
    record_game(root / "ok", 7, n=20)
    put(root / "human", "play1", ["human"] * 6)                       # not a seeded id
    put(root / "mixed", 11, ["baseline", "human", "baseline"])        # a person's step in it
    put(root / "unnumbered", 12, ["baseline"] * 4, numbered=False)    # no step numbers
    put(root / "fork", "7-5-fight", ["replay"] * 4 + ["fork", "baseline"])
    put(root / "replayed", 14, ["replay", "baseline"])                # int id, but replayed steps
    put(root / "forked", 15, ["baseline", "fork"])
    jobs = plan([root], 100, alternatives=5, seed=0)
    assert jobs and {j["seed"] for j in jobs} == {7}


def test_plan_needs_the_first_step_to_be_numbered_one(tmp_path):
    from ladder.brain.forks import plan
    root = tmp_path / "runs"
    put(root, 13, ["baseline"] * 4)
    lines = [json.loads(line) for line in (root / "steps.jsonl").read_text().splitlines()]
    for r in lines:
        if "step" in r:
            r["step"] += 1                                             # a log that starts mid-game
    (root / "steps.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines))
    assert plan([root], 10) == []


# --- train: fork rows --------------------------------------------------------------------------------

def forked_corpus(tmp_path):
    root = synthetic_corpus(tmp_path, games=12, length=30, seed=4)
    rng = random.Random(9)
    for g in range(14):
        rows = [(10 * i + rng.randint(0, 5), rng.randint(2, 20), 1) for i in range(12)]
        write_game(root, f"{g}-6-rest", rows, died=True)
    out, seen = [], {}
    for line in (root / "steps.jsonl").read_text().splitlines():
        r = json.loads(line)
        if isinstance(r["game"], str) and r.get("type") != "end":
            n = seen[r["game"]] = seen.get(r["game"], 0) + 1
            r["source"] = "replay" if n <= 3 else "fork" if n == 4 else "baseline"
        out.append(json.dumps(r))
    (root / "steps.jsonl").write_text("\n".join(out) + "\n")
    cpath = tmp_path / "c.npz"
    corpus.build([root], cpath)
    return cpath


def test_train_honours_fork_weight(tmp_path):
    pytest.importorskip("torch")
    from ladder.brain.train import train
    cpath = forked_corpus(tmp_path)
    data = np.load(cpath)
    assert ((data["fork"] > 0) & ~data["val"]).any()           # the fork rows are in the training split
    for w in (0.0, 500.0):
        info = train(cpath, tmp_path / f"m{w}.json", epochs=3, hidden=16, fork_weight=w, log=lambda *_: None)
        assert info["rows"] > 0
    a = json.loads((tmp_path / "m0.0.json").read_text())["layers"]
    b = json.loads((tmp_path / "m500.0.json").read_text())["layers"]
    assert a != b
    # same weight, same seed: the same model
    train(cpath, tmp_path / "again.json", epochs=3, hidden=16, fork_weight=500.0, log=lambda *_: None)
    assert json.loads((tmp_path / "again.json").read_text())["layers"] == b


def test_train_keeps_the_best_epoch(tmp_path):
    pytest.importorskip("torch")
    from ladder.brain.train import train
    logs = []
    info = train(forked_corpus(tmp_path), tmp_path / "m.json", epochs=3, hidden=16, log=logs.append)
    assert 1 <= info["epochs"] <= 3
    assert any(f"kept epoch {info['epochs']} of 3" in line for line in logs)


# --- cli.evaluate's run names --------------------------------------------------------------------------

def eval_args(tmp_path, *style, fresh=False):
    return SimpleNamespace(out=str(tmp_path), style=list(style) or None, fresh=fresh)


@pytest.fixture
def fake_play(monkeypatch):
    from ladder.brain import cli as brain_cli
    calls = []

    def play(args, name, seeds, model, epsilon):
        calls.append((name, list(seeds), model, epsilon))
        s = {"name": name, "style": brain_cli._style(args).to_dict(), "games": len(seeds),
             "results": [result(seed, 3) for seed in seeds]}
        (Path(args.out) / name).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / name / "results.json").write_text(json.dumps(s))
        return s

    monkeypatch.setattr(brain_cli, "_play", play)
    return calls


def test_evaluate_stores_a_styled_run_under_its_own_name(tmp_path, fake_play):
    from ladder.brain.cli import EVAL_SEED, evaluate
    plain = evaluate(eval_args(tmp_path), None, 3)
    styled = evaluate(eval_args(tmp_path, "margin=0.3"), None, 3)
    assert [c[0] for c in fake_play] == ["eval-baseline", "eval-baseline-margin=0.3"]
    assert plain["style"]["margin"] == 0.05 and styled["style"]["margin"] == 0.3
    assert fake_play[0][1] == [EVAL_SEED, EVAL_SEED + 1, EVAL_SEED + 2] and fake_play[0][3] == 0.0
    assert (tmp_path / "eval-baseline" / "results.json").exists()
    assert (tmp_path / "eval-baseline-margin=0.3" / "results.json").exists()


def test_evaluate_names_by_model_and_sorted_style(tmp_path, fake_play):
    from ladder.brain.cli import evaluate
    evaluate(eval_args(tmp_path, "xp_go=1", "died_go=-3"), "models/cand.json", 2)
    assert fake_play[0][0] == "eval-cand-died_go=-3-xp_go=1" and fake_play[0][2] == "models/cand.json"


def test_evaluate_reuses_matching_results_and_replays_otherwise(tmp_path, fake_play):
    from ladder.brain.cli import evaluate
    evaluate(eval_args(tmp_path, "margin=0.3"), None, 3)
    evaluate(eval_args(tmp_path, "margin=0.3"), None, 3)
    evaluate(eval_args(tmp_path, "margin=0.3"), None, 2)         # fewer games than are on record: reused
    assert len(fake_play) == 1
    evaluate(eval_args(tmp_path, "margin=0.3"), None, 5)         # more wanted than played
    assert len(fake_play) == 2
    evaluate(eval_args(tmp_path, "margin=0.3", fresh=True), None, 5)
    assert len(fake_play) == 3


def test_evaluate_replays_when_the_stored_style_differs(tmp_path, fake_play):
    from ladder.brain.cli import evaluate
    evaluate(eval_args(tmp_path, "margin=0.3"), None, 3)
    path = tmp_path / "eval-baseline-margin=0.3" / "results.json"
    stored = json.loads(path.read_text())
    stored["style"]["margin"] = 0.9
    path.write_text(json.dumps(stored))
    evaluate(eval_args(tmp_path, "margin=0.3"), None, 3)
    assert len(fake_play) == 2


def test_a_fork_is_held_out_with_its_dungeon_and_shares_a_group_with_its_moment(tmp_path):
    root = tmp_path / "runs"
    for seed in range(20):
        put(root / f"g{seed}", seed, ["baseline"] * 4)
        put(root / f"f{seed}", f"{seed}-3-fight", ["replay", "replay", "fork", "baseline"])
    out = tmp_path / "c.npz"
    corpus.build([root], out)
    data = np.load(out)
    games = corpus.read_games([root])
    pos, val_by_game, group_by_game = 0, {}, {}
    for g in games:
        n = len(g["steps"]) - g["skip"]
        val_by_game[str(g["steps"][0]["game"])] = set(data["val"][pos:pos + n].tolist())
        group_by_game[str(g["steps"][0]["game"])] = data["group"][pos:pos + n].tolist()
        pos += n
    assert any(v == {True} for v in val_by_game.values()) and any(v == {False} for v in val_by_game.values())
    for seed in range(20):
        assert val_by_game[str(seed)] == val_by_game[f"{seed}-3-fight"] and len(val_by_game[str(seed)]) == 1
        # the fork's own step (its 3rd) and the recorded game's 3rd step are the same moment
        assert group_by_game[f"{seed}-3-fight"][0] == group_by_game[str(seed)][2]


def test_fork_regret_compares_the_actions_tried_at_one_moment():
    pytest.importorskip("torch")
    from ladder.brain.train import fork_regret
    group = np.array([1, 1, 1, 2, 2, -1])
    fork = np.array([0, 1, 1, 0, 1, 0], dtype=np.float32)
    true = np.array([0.0, 1.0, 0.5, 0.2, 0.1, 9.0])
    pred = np.array([0.0, 0.9, 0.1, 0.0, 0.5, 9.0])           # picks the best in moment 1, the worse in moment 2
    r = fork_regret(group, fork, true, pred)
    assert r["moments"] == 2 and r["top1"] == 0.5
    assert r["regret"] == pytest.approx((0.0 + 0.1) / 2)
    assert r["recorded"] == pytest.approx((1.0 + 0.0) / 2)
    assert fork_regret(group, np.zeros(6, dtype=np.float32), true, pred) == {"moments": 0}
