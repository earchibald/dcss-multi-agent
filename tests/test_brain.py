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

from ladder.brain import corpus, policy
from ladder.brain.cli import compare
from ladder.brain.features import (ACTIONS, COMPONENTS, FEATURE_VERSION, MAX_MONS, MON_DIM, N_ACTIONS,
                                   N_COMPONENTS, SELF_DIM, V4_SELF, encode, inventory, observe, path,
                                   progress_depth)
from ladder.brain.net import ModelMismatch, TrainedNet, contract
from ladder.brain.policy import (BLOCK_TURNS, CALM_DOWN, FORK_DONE, IDLE_LIMIT, ITEM_PROMPTS, REPLAY_DIVERGED,
                                 UNTIL_LEVEL,
                                 BrainTiers, Style, available, baseline, heal_potion, poison_lethal_after_rage,
                                 poison_share, teleport_rule)
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
    assert (inv["curing"], inv["heal_wounds"]) == (2, 0)
    assert inv["letters"] == {"heal": "a", "curing": "a", "unknown_potions": "b", "unknown_scrolls": "c",
                              "teleport": "d"}


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
    assert inv == {"heal": 0, "curing": 0, "heal_wounds": 0, "unknown_potions": 0, "unknown_scrolls": 0,
                   "teleport": 0, "letters": {}}


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
    n = V4_SELF                              # the version-4 inputs end with these two blocks
    assert s[n - 2 * N_ACTIONS:n - N_ACTIONS].tolist() == [float(a == "rest") for a in ACTIONS]
    assert s[n - N_ACTIONS:n].tolist() == [float(a in ("explore", "rest")) for a in ACTIONS]


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
    tiers = BrainTiers(FakeNet(q_for("descend", "depth_end", 1.0)), rng=random.Random(0))
    assert tiers.next_action(stairs_state()) == "travel"       # descend, off the stairs, is a "travel" step
    last = tiers.last
    assert last["action"] == "descend" and last["baseline"] == "explore" and last["source"] == "net"
    assert last["avail"] == ["explore", "descend"]
    assert set(last["values"]) == {"explore", "descend"} and last["values"]["descend"] > last["values"]["explore"]
    assert last["danger"] == 0.1
    assert last["obs"]["dist_down"] == 3
    assert tiers.choice == "descend" and tiers.last_action == "descend"


def test_baseline_kept_within_margin():
    tiers = BrainTiers(FakeNet(q_for("descend", "depth_end", 0.04)), Style(margin=0.05), rng=random.Random(0))
    assert tiers.next_action(stairs_state()) == "explore"
    assert tiers.last["source"] == "net" and tiers.last["action"] == "explore"


def test_actions_with_too_few_training_examples_are_ignored():
    counts = {a: 1000 for a in ACTIONS} | {"descend": 3}
    tiers = BrainTiers(FakeNet(q_for("descend", "depth_end", 5.0), counts=counts), Style(min_count=40), rng=random.Random(0))
    assert tiers.next_action(stairs_state()) == "explore"
    counts["descend"] = 40
    tiers = BrainTiers(FakeNet(q_for("descend", "depth_end", 5.0), counts=counts), Style(min_count=40), rng=random.Random(0))
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
    assert d["model"] == "fake" and d["epsilon"] == 0.2 and d["style"]["margin"] == 0.25
    assert BrainTiers().describe()["model"] is None


class ScriptedConn:
    def __init__(self, results=()):
        self.sent, self.results = [], list(results)

    def act(self, *keys, **kw):
        self.sent.append((keys, kw))
        return self.results.pop(0) if self.results else ActResult()

    def catch_up(self):
        self.caught_up = getattr(self, "caught_up", 0) + 1
        return getattr(self, "behind", None) or ActResult()


def test_perform_quaffs_the_right_letter_through_the_menu():
    state = make_state(["@..."])
    with_inv(state, s0=item("potion of curing", POTIONS, 1, 101))
    conn = ScriptedConn([ActResult(blocking="menu")])
    BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "quaff_heal")
    assert conn.sent == [(("q",), {}), (("e",), {"through_menu": True})]


def test_a_menu_key_first_catches_up_with_the_game():
    # explore can leave a late "ready" unread; the menu would then open unseen
    state = make_state(["@..."])
    with_inv(state, s0=item("potion of curing", POTIONS, 1, 101))
    conn = ScriptedConn([ActResult(blocking="menu")])
    BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "quaff_heal")
    assert conn.caught_up == 1


def test_a_prompt_found_while_catching_up_is_returned_and_no_key_sent():
    state = make_state(["@..."])
    with_inv(state, s0=item("potion of curing", POTIONS, 1, 101))
    conn = ScriptedConn()
    conn.behind = ActResult(blocking="text_input")
    result = BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "quaff_heal")
    assert result.blocking == "text_input" and conn.sent == []


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
                         ActResult(blocking="menu", messages=[{"text": "really abort?"}]),
                         ActResult(messages=[{"text": "second"}])])
    result = BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "read_unknown")
    # one key at a time: Esc, and Y only once "really abort (and waste the scroll)?" is up
    assert [k for k, _ in conn.sent] == [("r",), ("a",), ("key_esc",), ("Y",)]
    assert [m["text"] for m in result.messages] == ["menu", "first", "really abort?", "second"]


def test_perform_types_no_y_when_cancelling_asks_nothing():
    # acquirement's menu just closes on Esc; a Y sent with it was run later as a command, and every
    # reply after that was the previous key's (the staircase loop)
    state = make_state(["@..."])
    with_inv(state, s0=item("scroll labelled FOO", SCROLLS, 1, 97))
    conn = ScriptedConn([ActResult(blocking="menu"), ActResult(blocking="acquirement"), ActResult()])
    result = BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "read_unknown")
    assert [k for k, _ in conn.sent] == [("r",), ("a",), ("key_esc",)]
    assert result.blocking is None


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
    # the descent counts once it has been survived for SETTLE_TURNS: here at turn 400, from 100
    game = {"id": "g", "steps": [step(point(0, 20, depth=1)), step(point(100, 20, depth=2)),
                                 step(point(400, 20, depth=2))], "end": None}
    out = corpus.label(game)
    assert out[0, COMPONENTS.index("depth_go")] == pytest.approx(math.exp(-400 / corpus.TAU_GO))
    assert out[2, COMPONENTS.index("depth_go")] == 0                     # nothing known after the last step


def test_label_depth_end_is_depths_gained_by_the_end_undiscounted():
    game = {"id": "g", "steps": [step(point(0, 20, depth=1)), step(point(100, 20, depth=2)),
                                 step(point(5000, 20, depth=2)), step(point(9000, 20, depth=4))],
            "end": {"type": "end", "died": False, "turn": 9500, "hp": 20, "hp_max": 20, "xl": 1, "progress": 0,
                    "place": "Dungeon", "depth": 5}}
    out = corpus.label(game)[:, COMPONENTS.index("depth_end")]
    assert out.tolist() == [4.0, 3.0, 3.0, 1.0]                  # the end record's depth 5 counts, however late
    last = {"id": "g", "steps": [step(point(0, 20, depth=3)), step(point(50, 20, depth=3))], "end": None}
    assert corpus.label(last)[:, COMPONENTS.index("depth_end")].tolist() == [0.0, 0.0]


def test_default_style_ranks_actions_by_depth_end_minus_died_soon():
    def pick(q):
        return BrainTiers(FakeNet(q), rng=random.Random(0)).next_action(stairs_state())
    assert pick(q_for("descend", "depth_end", 0.2)) == "explore"      # better, but under the 0.25 margin
    assert pick(q_for("descend", "depth_end", 0.3)) == "travel"       # over it: the net's pick (descend) wins
    q = q_for("descend", "depth_end", 0.5)                            # 0.5 less died_soon 0.4 is 0.1: short of it
    q[ACTIONS.index("descend"), COMPONENTS.index("died_soon")] = 0.4
    assert pick(q) == "explore"
    assert pick(q_for("descend", "depth_go", 5.0)) == "explore"       # depth_go is not in the default


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
    end["turn"] = 300                          # depth 2 (reached at 50) is settled by then
    game = {"id": "g", "steps": [step(point(0, 20, depth=1)), step(point(50, 20, depth=2))], "end": end}
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


def test_a_resumed_save_is_quit_and_the_game_started_again(tmp_path, monkeypatch):
    """A seeded start on an account that still holds a game resumes that game, not the seed's dungeon."""
    from ladder.brain import selfplay
    calls = []

    def play(job, cfg, log, beat):
        calls.append("play")
        if calls.count("play") == 1 or job["seed"] == 2:
            raise selfplay.StaleSave("resumed")
        return {"type": "end", "game": job["seed"], "ended_by": "died"}

    sent = []
    pipe = SimpleNamespace(send=sent.append, close=lambda: None)
    monkeypatch.setattr(selfplay, "_play", play)
    monkeypatch.setattr(selfplay, "_clear_save", lambda cfg: calls.append("clear"))
    selfplay._worker(1, {"seed": 1}, False, pipe, {"dir": str(tmp_path)})
    assert calls == ["play", "clear", "play"]
    assert sent[-1] == ("end", {"type": "end", "game": 1, "ended_by": "died", "restarted": "resumed"})
    calls.clear()
    selfplay._worker(1, {"seed": 2}, False, pipe, {"dir": str(tmp_path)})   # still stale: lost, and the slot dirty
    assert calls == ["play", "clear", "play"] and sent[-1][1]["ended_by"] == "error"


NEW_GAME = [{"msg": "msgs", "messages": [
    {"text": "<yellow>Welcome, ladderbrain1 the Minotaur Berserker.<lightgrey>"},
    {"text": "<white>Game seed: 650000 (custom seed)<lightgrey><lightgrey>; </lightgrey>"}]},
    {"msg": "input_mode", "mode": 1}]
RESUMED = [{"msg": "msgs", "messages": [{"text": "<yellow>Welcome back, ladderbrain1 the Minotaur Berserker.<lightgrey>"},
                                        {"text": "<lightred>Trog says: Kill them all!<lightgrey>"}]},
           {"msg": "input_mode", "mode": 1}]


def test_a_game_counts_as_on_its_seed_only_when_the_game_says_so():
    """A throwaway save resumed at turn 0 passes the turn check; its greeting and missing seed give it away."""
    from ladder.brain.selfplay import not_on_seed
    assert not_on_seed(NEW_GAME, 650000) is None
    assert not_on_seed(RESUMED, 650000) == "resumed a saved game"
    assert not_on_seed(NEW_GAME, 650001) is not None
    assert not_on_seed(NEW_GAME, 65000) is not None                 # a prefix of the seed is not the seed
    assert not_on_seed([], 650000) is not None


def test_a_game_resumed_at_turn_0_is_never_played_as_its_seed(tmp_path, monkeypatch):
    """The wrong-dungeon bug: the resumed throwaway is at turn 0, so only its opening shows it."""
    import ladder.conn
    from ladder.brain import selfplay

    class Resumes:
        def __init__(self, url, on_message=None, record=None):
            self.on_message = on_message

        def login(self, user):
            pass

        def set_rc(self, rc):
            pass

        def start_game(self, *a, seed=None):
            for m in RESUMED:
                self.on_message(m)
            return RESUMED

        def close(self):
            pass

    monkeypatch.setattr(ladder.conn, "Connection", Resumes)
    cfg = {"user": "ladderbrain1", "model": None, "style": {}, "epsilon": 0.0, "server": "x", "species": "b",
           "background": "f", "weapon": "b", "max_steps": 10, "max_turns": 10}
    log = RunLog(tmp_path / "g650000")
    with pytest.raises(selfplay.StaleSave, match="resumed"):
        selfplay._play({"seed": 650000}, cfg, log, lambda: None)
    assert (log.dir / "game650000.protocol.jsonl.gz").exists()          # the start is kept to look at
    log.close()


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
    tiers = BrainTiers(FakeNet(q_for("descend", "depth_end", 1.0)), rng=random.Random(0), script=["explore"])
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
    conn = ScriptedConn([ActResult(blocking="menu"), ActResult(blocking=reason), ActResult(blocking="yesno")])
    BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "read_unknown")
    assert [k for k, _ in conn.sent][-2:] == [("key_esc",), ("Y",)]


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

def test_a_shop_in_view_is_fenced_off_once_and_never_visited():
    rows = ["@.∩.."]
    state = make_state(rows)
    tiers = BrainTiers(rng=random.Random(0))
    assert tiers.next_action(state) == "fence_shops"
    assert tiers.last is None                                  # not a brain choice
    assert tiers.next_action(state) == "explore"


def test_fencing_comes_before_fighting_and_sends_the_macro_key():
    state = make_state(["@.∩.."])
    add_monster(state, (4, 0), 1, "rat")
    tiers = BrainTiers(rng=random.Random(0))
    assert tiers.next_action(state) == "fence_shops"
    assert tiers.next_action(state) == "fight"
    conn = ScriptedConn([ActResult()])
    tiers.perform(SimpleNamespace(state=state, conn=conn), "fence_shops")
    assert [k for k, _ in conn.sent] == [(policy.FENCE_KEY,)]


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


def record_stairs_game(directory, game, depths=(1, 1, 1, 2, 2, 3)):
    """A seeded game whose steps can explore or descend (except where a monster is in view or the rules
    chose to rest), one step per entry of `depths`."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "steps.jsonl").open("a") as f:
        for i, d in enumerate(depths):
            o = point(5 * i, 20, depth=d, n_hostiles=int(i == 1))
            base = "rest" if i == 2 else "explore"
            row = {"game": game, "step": i + 1, **step(o, base, ["explore", "rest", "descend"])}
            f.write(json.dumps(row) + "\n")
        f.write(json.dumps({"type": "end", "game": game, "died": True, "turn": 5 * len(depths)}) + "\n")


def test_plan_stairs_forks_both_ways_once_per_level_visit_and_commits(tmp_path):
    from ladder.brain.forks import plan
    root = tmp_path / "runs"
    record_stairs_game(root / "a", 7)
    record_stairs_game(root / "eval", 500_007)                          # an evaluation dungeon: never forked
    jobs = plan([root], 10, kind="stairs", seed=1, horizon=50)
    assert {j["seed"] for j in jobs} == {7}
    assert len(jobs) == 6                                               # D:1, D:2, D:3, two forks each
    by_spot: dict = {}
    for j in jobs:
        by_spot.setdefault(spot(j), []).append(j["script"][-1])
        assert j["commit"] and j["horizon"] == 50
        i = len(j["script"]) - 1
        assert i not in (1, 2)                                          # a monster in view; the rules rested
        assert j["script"][:-1] == ["explore", "explore", "rest", "explore", "explore", "explore"][:i]
    assert all(sorted(alts) == ["descend", "explore"] for alts in by_spot.values())
    assert len(plan([root], 2, kind="stairs", seed=1)) == 4
    with pytest.raises(ValueError, match="kind"):
        plan([root], 2, kind="nope")


def record_spent_game(directory, game):
    """A seeded game with two spells of exhaustion: steps 2-4 (outnumbered at 3 and 4) and 7-8 (outnumbered
    at 8, alone at 7); step 6 is outnumbered but not exhausted, and step 4 has no scroll to read."""
    directory.mkdir(parents=True, exist_ok=True)
    spent = {2, 3, 4, 7, 8}
    crowd = {3, 4, 6, 8}
    with (directory / "steps.jsonl").open("a") as f:
        for i in range(1, 11):
            n = 2 if i in crowd else 1
            o = point(5 * i, 10, status=["-Berserk", "Slow"] if i in spent else [], n_hostiles=n,
                      mons=[mon(dx=1 + k) for k in range(n)])
            avail = ["fight", "read_teleport"] if i != 4 else ["fight"]
            f.write(json.dumps({"game": game, "step": i, **step(o, "fight", avail)}) + "\n")
        f.write(json.dumps({"type": "end", "game": game, "died": True, "turn": 60}) + "\n")


def test_plan_teleport_forks_read_and_fight_once_per_spell(tmp_path):
    from ladder.brain.forks import plan
    root = tmp_path / "runs"
    record_spent_game(root / "a", 7)
    record_spent_game(root / "eval", 500_007)                           # an evaluation dungeon: never forked
    jobs = plan([root], 10, kind="teleport", seed=1, horizon=0)
    assert {j["seed"] for j in jobs} == {7}
    by_spot: dict = {}
    for j in jobs:
        by_spot.setdefault(spot(j), []).append(j["script"][-1])
        assert not j.get("commit") and j["horizon"] == 0
        assert j["script"][:-1] == ["fight"] * (len(j["script"]) - 1)
    # one moment per spell: step 3 (step 4 has no scroll, step 2 is alone) and step 8; step 6 isn't exhausted
    assert sorted(by_spot) == ["7-3", "7-8"]
    assert all(sorted(alts) == ["fight", "read_teleport"] for alts in by_spot.values())
    assert len(plan([root], 1, kind="teleport", seed=1)) == 2
    assert plan([root], 10, kind="teleport", seed=1) == plan([root], 10, kind="teleport", seed=1)


def record_unseen_game(directory, game, first):
    """A seeded game of 8 steps, nothing in view but at step 3 (`flee_up` there is an ordinary retreat); `first`
    is (step, status, action) for the first moment `Style.unseen` could have acted at, later steps alike."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "steps.jsonl").open("a") as f:
        for i in range(1, 9):
            st, act = [], "explore"
            if i == 3:
                o = point(5 * i, 20, n_hostiles=1, mons=[mon()])
                act = "flee_up"
            else:
                if first and i >= first[0]:
                    st, act = first[1], first[2]
                o = point(5 * i, 20, status=st)
            f.write(json.dumps({"game": game, "step": i, **step(o, act, ["explore", "rest", "flee_up"])}) + "\n")
        f.write(json.dumps({"type": "end", "game": game, "died": True, "turn": 45}) + "\n")


def test_plan_unseen_forks_the_first_moment_on_and_off(tmp_path):
    from ladder.brain.forks import plan
    root = tmp_path / "runs"
    record_unseen_game(root / "a", 7, (5, [], "flee_up"))           # going up with nothing in view
    record_unseen_game(root / "b", 8, (6, ["Fire"], "rest"))        # burning, whatever was chosen
    record_unseen_game(root / "c", 9, None)                         # nothing to fork: a retreat in view only
    record_unseen_game(root / "eval", 500_009, (5, [], "read_teleport"))
    jobs = plan([root], 10, kind="unseen", seed=1)
    by = {j["id"]: j for j in jobs}
    assert set(by) == {"7-5-on", "7-5-off", "8-6-on", "8-6-off"}
    assert by["7-5-on"]["script"] == ["explore", "explore", "flee_up", "explore", "flee_up"]
    assert by["7-5-off"]["script"] == ["explore", "explore", "flee_up", "explore"]
    assert by["7-5-off"]["style"] == {"unseen": 0.0} and "style" not in by["7-5-on"]
    assert by["8-6-on"]["script"][-1] == "rest"
    assert len(plan([root], 1, kind="unseen", seed=1)) == 2


def test_a_committed_descend_fork_keeps_descending_on_that_level_only():
    state = stairs_state()
    tiers = BrainTiers(rng=random.Random(0), script=["descend"], commit=True)
    tiers.next_action(state)
    assert tiers.last["source"] == "fork"
    tiers.next_action(state)                                            # the rules would explore again
    assert (tiers.last["action"], tiers.last["source"], tiers.last["baseline"]) == ("descend", "commit", "explore")
    state.level_seq += 1                                                # a new level: the rules again
    tiers.next_action(state)
    assert (tiers.last["action"], tiers.last["source"]) == ("explore", "baseline")
    # without commit the rules take over at once, and committing to explore changes nothing here
    for script, commit in ((["descend"], False), (["explore"], True)):
        tiers = BrainTiers(rng=random.Random(0), script=script, commit=commit)
        tiers.next_action(stairs_state())
        tiers.next_action(stairs_state())
        assert (tiers.last["action"], tiers.last["source"]) == ("explore", "baseline")


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
    assert plain["style"]["margin"] == 0.25 and styled["style"]["margin"] == 0.3
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
        # ...but its next step is not the recorded game's 4th: a different state, in no group
        assert group_by_game[f"{seed}-3-fight"][1] == -1 != group_by_game[str(seed)][3]


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


# --- the wiki's variant of the rules of thumb (Style.wiki, docs/wiki-strategy.md) -------------------

def wiki(o, explored=False):
    return baseline(o, available(o, explored, set(), False), explored, wiki=True)


def test_wiki_rests_to_full_before_exploring():
    o = obs(hp=18)                                           # 90%: the plain rules explore on
    assert baseline(o, available(o, False, set(), False), False) == "explore"
    assert wiki(o) == "rest"
    assert wiki(obs()) == "explore"


def test_wiki_drinks_before_the_rage_not_after():
    inv = {"heal": 1, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 0}
    o = obs(hp=8, inv=inv, god="Trog", n_hostiles=1, mons=[mon()])
    assert baseline(o, available(o, False, set(), False), False) == "berserk"
    assert wiki(o) == "quaff_heal"
    assert wiki(obs(hp=8, god="Trog", n_hostiles=1, mons=[mon()])) == "berserk"      # nothing to drink


def test_wiki_still_rages_early_at_something_tough():
    o = obs(god="Trog", n_hostiles=1, mons=[mon("ogre", dx=2, threat=2)])
    assert wiki(o) == "berserk"


def test_wiki_takes_near_stairs_up_before_anything_is_adjacent():
    hurt = dict(hp=8, god="Trog", depth=3)
    assert wiki(obs(dist_up=3, n_hostiles=1, mons=[mon(dx=2)], **hurt)) == "flee_up"
    assert wiki(obs(dist_up=3, n_hostiles=1, mons=[mon(dx=1)], **hurt)) == "berserk"    # already in melee
    assert wiki(obs(dist_up=9, n_hostiles=1, mons=[mon(dx=2)], **hurt)) == "berserk"    # too far to walk


def test_wiki_last_resorts_when_the_rage_is_spent():
    spent = dict(hp=5, god="Trog", status=["-Berserk"], n_hostiles=1, mons=[mon()])
    inv = {"heal": 0, "unknown_potions": 1, "unknown_scrolls": 1, "teleport": 1}
    assert wiki(obs(inv=inv, **spent)) == "read_teleport"
    assert wiki(obs(inv={**inv, "teleport": 0}, **spent)) == "quaff_unknown"
    assert wiki(obs(inv={**inv, "teleport": 0, "unknown_potions": 0}, **spent)) == "read_unknown"
    assert wiki(obs(inv={**inv, "teleport": 0}, **{**spent, "hp": 9})) == "fight"       # 45%: not yet


# --- the opt-in teleport rules (Style.teleport, policy.teleport_rule) ----------------------------

def rules(o, teleport=0, blocked=frozenset()):
    return baseline(o, available(o, False, set(blocked), False), False, teleport=teleport)


SCROLL = {"heal": 0, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 1}
SPENT = dict(god="Trog", status=["-Berserk", "Slow"], inv=SCROLL, n_hostiles=1, mons=[mon()])
CROWD3 = dict(god="Trog", inv=SCROLL, n_hostiles=3,
              mons=[mon(dx=5, threat=2), mon(dx=6), mon(dx=6, dy=1)])


def test_teleport_is_3_by_default_and_0_plays_as_before():
    for o in (obs(**SPENT), obs(**CROWD3)):
        assert rules(o) == "fight"
        assert baseline(o, available(o, False, set(), False), False) == "fight"
    assert Style().teleport == 3


def test_spent_after_a_rage_reads_teleportation():
    assert rules(obs(**SPENT), 1) == "read_teleport"
    assert rules(obs(**SPENT), 2) == "read_teleport"
    assert rules(obs(**{**SPENT, "hp": 8}), 1) == "read_teleport"           # before the healing potion, too
    assert rules(obs(**{**SPENT, "status": ["-Berserk"]}), 1) == "fight"    # no longer slowed
    assert rules(obs(**{**SPENT, "status": ["Slow"]}), 1) == "fight"        # slowed by something else
    assert rules(obs(**{**SPENT, "inv": {**SCROLL, "teleport": 0}}), 1) == "fight"
    assert rules(obs(**{**SPENT, "n_hostiles": 0, "mons": []}), 1) != "read_teleport"


def test_no_second_scroll_while_a_teleport_is_coming():
    o = obs(**{**SPENT, "status": ["-Berserk", "Slow", "Tele"], "inv": {**SCROLL, "teleport": 2}})
    assert rules(o, 2) == "fight"
    assert teleport_rule(o, 2) == (False, False)


def test_read_teleport_is_not_available_while_a_teleport_is_coming():
    # a model (or a random choice) could pick it from `available`: 33 of 279 model reads on 660000-660599 were
    # made with `Tele` showing, which cancels the teleport already coming
    o = obs(**SPENT)
    assert "read_teleport" in available(o, False, set(), False)
    pending = obs(**{**SPENT, "status": ["-Berserk", "Slow", "Tele"], "inv": {**SCROLL, "teleport": 2}})
    avail = available(pending, False, set(), False)
    assert "read_teleport" not in avail
    assert avail == [a for a in available(o, False, set(), False) if a != "read_teleport"]   # nothing else changes


def test_spent_rule_needs_the_scroll_to_be_readable():
    assert rules(obs(**{**SPENT, "status": ["-Berserk", "Slow", "Conf"]}), 1) == "fight"
    assert rules(obs(**SPENT), 1, blocked={"read_teleport"}) == "fight"


def test_crowded_reads_teleportation_only_at_level_2_and_after_a_rage():
    assert rules(obs(**CROWD3), 1) == "fight"
    assert rules(obs(**CROWD3), 2) == "read_teleport"
    # the rules would rage here (something tough within 2): the rage comes first
    close = obs(**{**CROWD3, "mons": [mon(dx=2, threat=2), mon(dx=6), mon(dx=6, dy=1)]})
    assert rules(close, 2) == "berserk"
    assert rules(obs(**{**CROWD3, "n_hostiles": 2, "mons": CROWD3["mons"][:2]}), 2) == "fight"     # two
    weak = [mon(dx=5), mon(dx=6), mon(dx=6, dy=1)]
    assert rules(obs(**{**CROWD3, "mons": weak}), 2) == "fight"                                    # none dangerous


def outmatched(hp=10, status=("-Berserk", "Slow"), foes=(30, 30), heal=0, **over):
    """Exhausted after a rage at `hp` of 40, with hostiles of the given average HP (unhurt) in view."""
    mons = [{**mon(dx=1 + i), "avghp": a, "mdam": 0} for i, a in enumerate(foes)]
    return obs(**{"god": "Trog", "hp": hp, "hp_max": 40, "status": list(status), "n_hostiles": len(mons),
                  "mons": mons, "inv": {**SCROLL, "heal": heal}, **over})


def test_outmatched_reads_teleportation_at_level_3():
    # 60 HP of hostiles against 10 HP: 6x, far past OUTMATCHED
    assert rules(outmatched(), 3) == "read_teleport"
    assert teleport_rule(outmatched(), 3) == (True, False)
    assert rules(outmatched(status=["-Berserk"]), 3) == "read_teleport"        # no longer slowed: still exhausted
    assert rules(outmatched(heal=1), 3) == "read_teleport"                     # before the healing potion
    assert rules(outmatched(), 0) == "fight"                                   # off by default


def test_outmatched_needs_exhaustion_and_more_foe_hp_than_its_threshold():
    from ladder.brain.policy import OUTMATCHED
    assert OUTMATCHED == 1.5
    for o in (outmatched(status=["Slow"]), outmatched(status=[])):             # slowed by something else; no rage
        assert rules(o, 3) == rules(o, 0) == "berserk"                         # the rules rage, as without the switch
    assert rules(outmatched(hp=20, foes=(29,)), 3) == "fight"                  # 29 < 1.5 x 20
    assert rules(outmatched(hp=20, foes=(30,)), 3) == "read_teleport"          # 30 = 1.5 x 20
    # damage already done to a monster counts against its HP (features.MDAM_LEFT): 3 is half left
    hurt = outmatched(hp=20, foes=(40,))
    hurt["mons"][0]["mdam"] = 3
    assert rules(hurt, 3) == "fight"                                           # 20 left < 30
    # a monster with no avghp falls back to the monster table (an orc has 11 HP or so)
    table = obs(god="Trog", hp=2, hp_max=40, status=["-Berserk"], n_hostiles=1, mons=[mon()], inv=SCROLL)
    assert rules(table, 3) == "read_teleport"


def test_outmatched_is_not_the_spent_or_crowded_rule():
    # level 3 does not read at every spent moment (level 1) or when merely crowded (level 2)
    assert rules(obs(**SPENT), 1) == "read_teleport"
    assert rules(outmatched(hp=30, foes=(10,)), 3) == "fight"                  # spent, but not outmatched
    assert rules(obs(**CROWD3), 3) == "fight"
    assert teleport_rule(obs(**CROWD3), 3) == (False, False)


def test_outmatched_rule_keeps_the_guards():
    pending = outmatched(status=["-Berserk", "Slow", "Tele"])
    assert teleport_rule(pending, 3) == (False, False)                         # a teleport is already coming
    assert rules(pending, 3) == "fight"
    assert rules(outmatched(status=["-Berserk", "Conf"]), 3) == "fight"        # can't read while confused
    assert rules(outmatched(inv=dict(SCROLL, teleport=0)), 3) == "fight"       # no scroll
    assert rules(outmatched(), 3, blocked={"read_teleport"}) == "fight"
    # a retreat up close stairs still comes first, as for level 1
    o = outmatched(hp=30, foes=(50,), dist_up=3)
    avail = available(o, False, set(), False)
    assert baseline(o, avail, False, teleport=3) == "read_teleport"
    assert baseline(o, avail, False, teleport=3, retreat=True) == "flee_up"
    # serious poison: the cure still comes first
    poisoned = outmatched(hp=30, foes=(50,), poison_survival=1, inv={**SCROLL, "heal": 1, "curing": 1})
    assert rules(poisoned, 3) == "quaff_heal"


def test_teleport_switch_is_a_style_and_old_runs_still_match():
    import argparse
    from ladder.brain.cli import _style
    assert _style(argparse.Namespace(style=["teleport=2"])).teleport == 2.0
    # a run saved before the switch existed was played with it off, not with today's default
    old = {k: v for k, v in Style().to_dict().items() if k != "teleport"}
    assert Style.saved(old) == Style(teleport=0)
    assert Style.saved(old) != Style()
    assert Style.saved(Style().to_dict()) == Style()


# --- the opt-in rule to rest out a rage before going on (Style.recover, policy.recovering) -----------

def calm_rules(o, recover=0, explored=False, stalled=False, blocked=frozenset()):
    avail = available(o, explored, set(blocked), stalled, recover=bool(recover))
    return baseline(o, avail, explored, recover=recover)


STAIRS_KNOWN = dict(dist_down=6, god="Trog")


def test_recover_is_on_by_default_and_off_plays_as_before():
    assert Style().recover == 1
    for status in (["-Berserk", "Slow"], ["Berserk"]):
        o = obs(status=status, **STAIRS_KNOWN)
        assert calm_rules(o, Style().recover, explored=True) == "rest"
    # recover=0: the rules as they were before the switch
    for status in (["-Berserk", "Slow"], ["Berserk"]):
        o = obs(status=status, **STAIRS_KNOWN)
        assert calm_rules(o, explored=True) == "descend"
        assert calm_rules(o) == "explore"
        assert "rest" not in available(o, True, set(), False)       # full HP: nothing to rest for, as before


def test_recover_rests_before_the_stairs_while_spent():
    for status in (["-Berserk", "Slow"], ["-Berserk"], ["Slow"], ["Berserk"]):
        o = obs(status=status, **STAIRS_KNOWN)
        assert calm_rules(o, 1, explored=True) == "rest", status
        assert calm_rules(o, 2, explored=True) == "rest", status
    fresh = obs(**STAIRS_KNOWN)
    assert calm_rules(fresh, 1, explored=True) == "descend"
    assert calm_rules(fresh, 2, explored=True) == "descend"


def test_recover_level_1_explores_on_and_level_2_waits():
    o = obs(status=["-Berserk", "Slow"], **STAIRS_KNOWN)
    assert calm_rules(o, 1) == "explore"
    assert calm_rules(o, 2) == "rest"


def test_recover_rests_at_full_hp_even_after_a_rest_that_healed_nothing():
    o = obs(status=["-Berserk"], **STAIRS_KNOWN)
    assert "rest" in available(o, True, set(), True, recover=True)
    assert calm_rules(o, 1, explored=True, stalled=True) == "rest"
    # a rest that passed no time at all is set aside like any other action: then on to the stairs
    assert calm_rules(o, 1, explored=True, blocked={"rest"}) == "descend"
    # not spent: a stalled rest is still ruled out
    assert "rest" not in available(obs(hp=10, **STAIRS_KNOWN), True, set(), True, recover=True)


def test_recover_never_rests_with_something_in_view():
    o = obs(status=["-Berserk", "Slow"], n_hostiles=1, mons=[mon(dx=5)], **STAIRS_KNOWN)
    assert "rest" not in available(o, True, set(), False, recover=True)
    assert calm_rules(o, 2, explored=True) == "fight"


def test_recover_keeps_the_other_calm_choices_first():
    o = obs(status=["-Berserk", "Slow"], hp=10, **STAIRS_KNOWN)          # hurt: the usual rest, either way
    assert calm_rules(o, 0, explored=True) == "rest"
    unknown = obs(status=["-Berserk"], inv={"heal": 0, "unknown_potions": 1, "unknown_scrolls": 0, "teleport": 0},
                  **STAIRS_KNOWN)
    assert calm_rules(unknown, 2, explored=True) == "quaff_unknown"


def test_recover_switch_is_a_style_and_old_runs_still_match():
    import argparse
    from ladder.brain.cli import _style
    assert _style(argparse.Namespace(style=["recover=2"])).recover == 2.0
    assert _style(argparse.Namespace(style=["recover=0"])).recover == 0.0
    # a run saved before the switch existed was played with it off, not with today's default
    old = {k: v for k, v in Style(recover=0).to_dict().items() if k != "recover"}
    assert Style.saved(old) == Style(recover=0, retreat=old["retreat"])
    assert Style.saved(old) != Style()
    assert Style.saved(Style().to_dict()) == Style()                         # one saved since: as saved
    assert Style.saved(Style(recover=0).to_dict()) == Style(recover=0)


def test_recover_reaches_the_rules_inside_brain_tiers():
    seen = {}
    for level in (0, 1):
        tiers = BrainTiers(style=Style(recover=level), rng=random.Random(0))
        state = stairs_state()
        state.player["status"] = [{"light": "-Berserk"}, {"light": "Slow"}]
        tiers.level_explored = True
        seen[level] = tiers.next_action(state)
    assert seen[0] == "travel" and seen[1] == "rest"


# --- the opt-in switch to wait out a rage instead of trying to explore (Style.calm) -------------------

def test_calm_is_off_by_default_and_explore_is_tried_in_a_rage_as_before():
    assert Style().calm == 0
    o = obs(status=["Berserk"], **STAIRS_KNOWN)
    assert "explore" in available(o, False, set(), False)
    assert baseline(o, available(o, False, set(), False), False) == "explore"


def test_calm_waits_out_the_rage_then_explores():
    raging = obs(status=["Berserk"], **STAIRS_KNOWN)
    avail = available(raging, False, set(), True, calm=True)       # even after a rest that healed nothing
    assert "explore" not in avail and "rest" in avail
    assert baseline(raging, avail, False, calm=True) == "rest"
    # the exhaustion after it doesn't stop autoexplore: explore on (resting it out is `recover`'s)
    spent = obs(status=["-Berserk", "Slow"], **STAIRS_KNOWN)
    avail = available(spent, False, set(), False, calm=True)
    assert "explore" in avail and baseline(spent, avail, False, calm=True) == "explore"
    assert calm_rules(spent, 2) == "rest"
    # a level explored to the end: on to the stairs as before (recover=1 rests there)
    assert baseline(raging, available(raging, True, set(), False, calm=True), True, calm=True) == "descend"


def test_calm_never_rests_with_something_in_view():
    o = obs(status=["Berserk"], n_hostiles=1, mons=[mon(dx=5)], **STAIRS_KNOWN)
    assert "rest" not in available(o, False, set(), False, calm=True)


def _refuse_explore(tiers, state, text):
    before = Before.capture(state)
    state.messages.append({"turn": state.turn, "channel": 0, "text": text})
    tiers.observe("explore", before, state, [])


def test_calm_does_not_count_a_refusal_for_the_rage_as_the_level_being_done():
    for calm, blocked in ((0, True), (1, False)):
        state = stairs_state()
        tiers = BrainTiers(style=Style(calm=calm), rng=random.Random(0))
        tiers.choice = "explore"
        _refuse_explore(tiers, state, CALM_DOWN)
        _refuse_explore(tiers, state, CALM_DOWN)
        assert ("explore" in tiers.blocked) == blocked, calm
    # any other refusal still counts
    state = stairs_state()
    tiers = BrainTiers(style=Style(calm=1), rng=random.Random(0))
    tiers.choice = "explore"
    _refuse_explore(tiers, state, "Done exploring.")
    _refuse_explore(tiers, state, "Done exploring.")
    assert tiers.blocked["explore"] == state.turn + BLOCK_TURNS


def test_calm_reaches_the_rules_inside_brain_tiers():
    seen = {}
    for calm in (0, 1):
        tiers = BrainTiers(style=Style(calm=calm), rng=random.Random(0))
        state = stairs_state()
        state.player["status"] = [{"light": "Berserk"}]
        seen[calm] = tiers.next_action(state)
    assert seen[0] == "explore" and seen[1] == "rest"


def test_calm_switch_is_a_style_and_old_runs_still_match():
    import argparse
    from ladder.brain.cli import _style
    assert _style(argparse.Namespace(style=["calm=1"])).calm == 1.0
    old = {k: v for k, v in Style().to_dict().items() if k != "calm"}          # a run saved before the switch
    assert {**Style().to_dict(), **old} == Style().to_dict()
    assert {**Style().to_dict(), **old} != Style(calm=1).to_dict()


# --- the opt-in fight rules: go up when a rage runs out mid-fight, walk to the stairs first (Style.retreat, .stairs)

UP_KNOWN = dict(god="Trog", dist_up=6)
PAIR = dict(n_hostiles=2, mons=[mon(dx=1), mon(dx=2)])
BIG = [{**mon(dx=4), "avghp": 15, "mdam": 0}, {**mon(dx=5), "avghp": 15, "mdam": 2}]    # 15 + 10.5 HP left


def test_retreat_is_2_and_stairs_off_by_default_and_retreat_0_plays_as_before():
    assert Style().retreat == 2 and Style().stairs == 0
    o = obs(status=["-Berserk", "Slow"], **PAIR, **UP_KNOWN)
    assert rules(o) == "fight"
    # the default: a rage that runs out with two left and the stairs up close goes up them
    tiers = BrainTiers(rng=random.Random(0))
    tiers.fight_moves(1, obs(status=["Berserk"], **PAIR, **UP_KNOWN))
    assert tiers.fight_moves(1, o) == (True, True, False)
    # retreat=0: as before the switch
    tiers = BrainTiers(style=Style(retreat=0), rng=random.Random(0))
    tiers.fight_moves(1, obs(status=["Berserk"], **PAIR, **UP_KNOWN))
    assert tiers.fight_moves(1, o) == (False, False, False)
    assert tiers.fight_moves(1, obs(mons=BIG, n_hostiles=2, **UP_KNOWN)) == (False, False, False)


def test_foe_hp_and_big_fight():
    assert policy.foe_hp(obs(mons=BIG, n_hostiles=2)) == pytest.approx(25.5)
    # no game HP to go on: the monster table's
    orc = policy.monsters.lookup("orc")["hp"]
    assert policy.foe_hp(obs(mons=[mon("orc")], n_hostiles=1)) == pytest.approx(orc)
    assert policy.big_fight(obs(mons=BIG, n_hostiles=2, hp=5, hp_max=25))         # against max HP, not HP now
    assert not policy.big_fight(obs(mons=BIG, n_hostiles=2, hp_max=26))
    assert not policy.big_fight(obs())


def test_baseline_retreat_goes_up_first_and_drinks_first_at_half_hp():
    o = obs(status=["-Berserk", "Slow"], **PAIR, **UP_KNOWN)
    avail = available(o, False, set(), False)
    assert "flee_up" in avail and baseline(o, avail, False, retreat=True) == "flee_up"
    hurt = obs(status=["-Berserk", "Slow"], hp=9, inv={"heal": 1, "unknown_potions": 0, "unknown_scrolls": 0,
                                                       "teleport": 0}, **PAIR, **UP_KNOWN)
    assert baseline(hurt, available(hurt, False, set(), False), False, retreat=True) == "quaff_heal"
    # stairs not reachable (unknown, or leaving the dungeon from D:1), or the step went nowhere: fight as before
    for x in (obs(status=["-Berserk"], **PAIR, god="Trog"), obs(status=["-Berserk"], depth=1, **PAIR, **UP_KNOWN)):
        assert baseline(x, available(x, False, set(), False), False, retreat=True) == "fight"
    assert baseline(o, available(o, False, {"flee_up"}, False), False, retreat=True) == "fight"


def test_baseline_rest_out_rests_with_nothing_in_view_until_recovered():
    spent = obs(status=["-Berserk", "Slow"], **UP_KNOWN)
    assert baseline(spent, available(spent, False, set(), False, recover=True), False, rest_out=True) == "rest"
    assert baseline(spent, available(spent, True, set(), False, recover=True), True, rest_out=True) == "rest"
    fresh = obs(**UP_KNOWN)
    assert baseline(fresh, available(fresh, False, set(), False, recover=True), False, rest_out=True) == "explore"


def test_retreat_starts_only_when_a_rage_runs_out_with_two_left_and_keeps_to_that_level():
    tiers = BrainTiers(style=Style(retreat=1), rng=random.Random(0))
    raging, spent = ["Berserk"], ["-Berserk", "Slow"]
    assert tiers.fight_moves(1, obs(status=raging, **PAIR, **UP_KNOWN)) == (False, False, False)
    assert tiers.fight_moves(1, obs(status=spent, **PAIR, **UP_KNOWN)) == (True, True, False)
    # one left in view on the same level: still heading up
    assert tiers.fight_moves(1, obs(status=spent, n_hostiles=1, mons=[mon()], **UP_KNOWN))[0]
    # upstairs (another level): fight what followed, rest once nothing is in view
    assert tiers.fight_moves(2, obs(status=spent, n_hostiles=1, mons=[mon()], **UP_KNOWN)) == (False, True, False)
    assert tiers.fight_moves(2, obs(status=spent, **UP_KNOWN)) == (False, True, False)
    # the exhaustion is over: all as usual
    assert tiers.fight_moves(2, obs(**UP_KNOWN)) == (False, False, False)
    assert tiers.retreat_from is None


def test_retreat_needs_two_left_and_known_stairs_up():
    for after in (obs(status=["-Berserk"], n_hostiles=1, mons=[mon()], **UP_KNOWN),
                  obs(status=["-Berserk"], god="Trog", **PAIR)):
        tiers = BrainTiers(style=Style(retreat=1), rng=random.Random(0))
        tiers.fight_moves(1, obs(status=["Berserk"], **PAIR, **UP_KNOWN))
        assert tiers.fight_moves(1, after) == (False, False, False)
    # spent already, not a rage that ran out just now: no retreat
    tiers = BrainTiers(style=Style(retreat=1), rng=random.Random(0))
    assert tiers.fight_moves(1, obs(status=["-Berserk"], **PAIR, **UP_KNOWN)) == (False, False, False)


def test_retreat_level_2_only_with_the_stairs_up_close():
    for dist, level, leaves in ((8, 2, True), (9, 2, False), (0, 2, True), (40, 1, True), (40, 2, False)):
        tiers = BrainTiers(style=Style(retreat=level), rng=random.Random(0))
        tiers.fight_moves(1, obs(status=["Berserk"], **PAIR, god="Trog", dist_up=dist))
        assert tiers.fight_moves(1, obs(status=["-Berserk"], **PAIR, god="Trog", dist_up=dist,
                                        on_up=dist == 0))[0] == leaves, (dist, level)


def test_retreat_reaches_the_rules_inside_brain_tiers():
    seen = {}
    for level in (0, 1):
        state = make_state(["#########", "#<..@...#", "#.......#", "#########"], depth=3, god="Trog")
        add_monster(state, (5, 1), 1, "orc")
        add_monster(state, (5, 2), 2, "orc")
        tiers = BrainTiers(style=Style(retreat=level), rng=random.Random(0))
        state.player["status"] = [{"light": "Berserk"}]
        assert tiers.next_action(state) == "fight"
        state.player["status"] = [{"light": "-Berserk"}, {"light": "Slow"}]
        seen[level] = tiers.next_action(state)
    assert seen == {0: "fight", 1: "flee_up"}


def test_stairs_walks_up_before_a_big_fight_once_per_fight():
    tiers = BrainTiers(style=Style(stairs=1), rng=random.Random(0))
    big = obs(mons=BIG, n_hostiles=2, **UP_KNOWN)
    assert tiers.fight_moves(1, big) == (False, False, True)
    o = baseline(big, available(big, False, set(), False), False, to_stairs=True)
    assert o == "flee_up"
    # on the stairs: done for this fight, even a step off them
    assert tiers.fight_moves(1, obs(mons=BIG, n_hostiles=2, on_up=True, god="Trog", dist_up=0)) == (False, False, False)
    assert tiers.fight_moves(1, obs(mons=BIG, n_hostiles=2, god="Trog", dist_up=1)) == (False, False, False)
    # nothing in view: the next fight may walk again
    tiers.fight_moves(1, obs(**UP_KNOWN))
    assert tiers.fight_moves(1, big)[2]


def test_stairs_leaves_small_far_adjacent_and_raging_fights_alone():
    for o in (obs(mons=BIG, n_hostiles=2, god="Trog", dist_up=9),                          # too far
              obs(mons=BIG[:1], n_hostiles=1, **UP_KNOWN),                                 # small
              obs(mons=BIG, n_hostiles=2, god="Trog"),                                     # no stairs known
              obs(mons=BIG, n_hostiles=2, status=["Berserk"], **UP_KNOWN)):                # raging
        assert not BrainTiers(style=Style(stairs=1), rng=random.Random(0)).fight_moves(1, o)[2], o
    tiers = BrainTiers(style=Style(stairs=1), rng=random.Random(0))
    near = [{**BIG[0], "dx": 1}, BIG[1]]
    assert not tiers.fight_moves(1, obs(mons=near, n_hostiles=2, **UP_KNOWN))[2]               # adjacent: done
    assert not tiers.fight_moves(1, obs(mons=BIG, n_hostiles=2, **UP_KNOWN))[2]


def test_retreat_and_stairs_switches_are_styles_and_old_runs_still_match():
    import argparse
    from ladder.brain.cli import _style
    assert _style(argparse.Namespace(style=["retreat=1", "stairs=1"])) == Style(retreat=1, stairs=1)
    # a run saved before the switches existed (before recover too) was played with all of them off
    old = {k: v for k, v in Style().to_dict().items() if k not in ("recover", "retreat", "stairs")}
    assert Style.saved(old) == Style(recover=0, retreat=0, stairs=0)
    assert Style.saved(old) != Style()
    # one saved with recover but before retreat existed
    assert Style.saved({**old, "recover": 1.0}) == Style(recover=1, retreat=0)
    assert Style.saved(None) == Style(recover=0, retreat=0, teleport=0, unseen=0)


def test_retreat_level_3_also_leaves_a_fight_met_while_exhausted():
    spent = ["-Berserk", "Slow"]
    # retreat=2: exhaustion alone, without a rage running out just now, does not mark the level
    tiers = BrainTiers(style=Style(retreat=2), rng=random.Random(0))
    assert tiers.fight_moves(1, obs(status=spent, **PAIR, **UP_KNOWN)) == (False, False, False)
    # retreat=3: it does, with two in view and the stairs up close
    tiers = BrainTiers(style=Style(retreat=3), rng=random.Random(0))
    assert tiers.fight_moves(1, obs(status=spent, **PAIR, **UP_KNOWN)) == (True, True, False)
    assert tiers.fight_moves(1, obs(status=["-Berserk"], **PAIR, **UP_KNOWN))[0]           # no longer slowed
    for o in (obs(status=spent, n_hostiles=1, mons=[mon()], **UP_KNOWN),                    # one in view
              obs(status=spent, **PAIR, god="Trog", dist_up=9),                              # stairs too far
              obs(status=spent, **PAIR, god="Trog"),                                         # no stairs known
              obs(status=["Slow"], **PAIR, **UP_KNOWN),                                      # slowed, not exhausted
              obs(**PAIR, **UP_KNOWN)):                                                      # fresh
        assert BrainTiers(style=Style(retreat=3), rng=random.Random(0)).fight_moves(1, o) == (False, False, False), o
    # and still as level 2 when the rage runs out
    tiers = BrainTiers(style=Style(retreat=3), rng=random.Random(0))
    tiers.fight_moves(1, obs(status=["Berserk"], **PAIR, **UP_KNOWN))
    assert tiers.fight_moves(1, obs(status=spent, **PAIR, **UP_KNOWN))[0]


def avoid_obs(hp=40, foes=(30, 30), status=(), tele=1, **over):
    """A fresh character at `hp` of 40 with unhurt hostiles of the given average HP in view, the first adjacent."""
    mons = [{**mon(dx=1 + i, threat=2), "avghp": a, "mdam": 0} for i, a in enumerate(foes)]
    return obs(**{"god": "Trog", "hp": hp, "hp_max": 40, "status": list(status), "n_hostiles": len(mons),
                  "mons": mons, "inv": {**SCROLL, "teleport": tele}, **over})


def avoid_rules(o, avoid, blocked=frozenset()):
    return baseline(o, available(o, False, set(blocked), False), False, teleport=3, avoid=avoid)


def test_avoid_is_off_by_default_and_off_plays_as_before():
    assert Style().avoid == 0
    o = avoid_obs()
    assert avoid_rules(o, 0) == baseline(o, available(o, False, set(), False), False, teleport=3) == "berserk"
    assert not policy.avoid_rule(o, 0)


def test_avoid_reads_teleportation_instead_of_raging_against_k_times_max_hp():
    # 60 HP of hostiles against a maximum of 40: 1.5x
    assert avoid_rules(avoid_obs(), 1.5) == "read_teleport"
    assert avoid_rules(avoid_obs(), 1.6) == "berserk"
    assert avoid_rules(avoid_obs(hp=10), 1.5) == "read_teleport"           # against the maximum, not HP now
    assert avoid_rules(avoid_obs(foes=(20, 20)), 1.5) == "berserk"         # 40 < 60
    far = avoid_obs(mons=[{**mon(dx=5, threat=2), "avghp": 30, "mdam": 0}, {**mon(dx=6), "avghp": 30, "mdam": 0}])
    assert avoid_rules(far, 0) == "fight" and avoid_rules(far, 1.5) == "read_teleport"   # before they arrive, too
    # damage done to them counts (features.MDAM_LEFT: 3 is half left)
    hurt = avoid_obs()
    hurt["mons"][0]["mdam"] = 3
    assert avoid_rules(hurt, 1.5) == "berserk"


def test_avoid_keeps_to_fresh_characters_and_its_guards():
    for st in (["Berserk"], ["-Berserk", "Slow"], ["-Berserk"], ["Tele"]):
        assert not policy.avoid_rule(avoid_obs(status=st), 1.5), st              # exhausted: teleport_rule's part
    for st in (["Berserk"], ["Tele"], ["Conf"]):
        assert avoid_rules(avoid_obs(status=st), 1.5) != "read_teleport", st
    assert avoid_rules(avoid_obs(tele=0), 1.5) == "berserk"                       # no scroll
    assert avoid_rules(avoid_obs(), 1.5, blocked={"read_teleport"}) == "berserk"
    # a teleport is coming: the rage the rules would have begun comes next
    assert avoid_rules(avoid_obs(status=["Tele"]), 1.5) == "berserk"
    # serious poison: the cure first
    poisoned = avoid_obs(hp=30, poison_survival=1, inv={**SCROLL, "heal": 1, "curing": 1})
    assert avoid_rules(poisoned, 1.5) == "quaff_heal"


def test_avoid_reaches_the_rules_inside_brain_tiers():
    seen = {}
    for k in (0, 1.0):
        state = make_state(["#########", "#..@....#", "#.......#", "#########"], depth=3, god="Trog")
        state = with_inv(state, s0=item("scroll of teleportation", SCROLLS, 1, letter=ord("c")))
        for x in range(4, 8):
            add_monster(state, (x, 1), x, "orc warrior")
        tiers = BrainTiers(style=Style(avoid=k), rng=random.Random(0))
        seen[k] = tiers.next_action(state)
    assert seen[0] != "read_teleport" and seen[1.0] == "read_teleport"


def test_avoid_and_retreat_3_are_styles_and_old_runs_still_match():
    import argparse
    from ladder.brain.cli import _style
    assert _style(argparse.Namespace(style=["avoid=1.5", "retreat=3"])) == Style(avoid=1.5, retreat=3)
    # a run saved before `avoid` existed was played with it off, which is also its default
    old = {k: v for k, v in Style().to_dict().items() if k != "avoid"}
    assert Style.saved(old) == Style()


# --- three opt-in switches against the deaths calm=1 adds on D:4-6 (Style.escape, .unique, .calmfor) -----------

EXHAUSTED = ["-Berserk", "Slow"]


def escape_obs(hp=12, status=EXHAUSTED, foes=(10,), tele=1, **over):
    """A character at `hp` of 40 with hostiles of the given average HP in view, the first adjacent."""
    mons = [{**mon(dx=1 + i, threat=2), "avghp": a, "mdam": 0} for i, a in enumerate(foes)]
    return obs(**{"god": "Trog", "hp": hp, "hp_max": 40, "status": list(status), "n_hostiles": len(mons),
                  "mons": mons, "inv": {**SCROLL, "heal": 1, "teleport": tele}, **over})


def switch_rules(o, blocked=frozenset(), **kw):
    return baseline(o, available(o, False, set(blocked), False), False, teleport=3, **kw)


def test_escape_is_off_by_default_and_off_plays_as_before():
    assert Style().escape == 0
    o = escape_obs()
    assert switch_rules(o) == switch_rules(o, escape=0) == "quaff_heal"     # 12 of 40: the potion, then fight on
    assert not policy.escape_rule(o, 0)


def test_escape_reads_teleportation_when_exhausted_and_low_whatever_the_foes():
    # foes' HP 10 against HP 12: under teleport=3's 1.5x, so the rules drink and fight on; escape reads first
    assert switch_rules(escape_obs(), escape=0.35) == "read_teleport"
    assert switch_rules(escape_obs(hp=14), escape=0.35) == "read_teleport"       # 14 = 0.35 x 40
    assert switch_rules(escape_obs(hp=15), escape=0.35) == "quaff_heal"          # above it: as before
    assert switch_rules(escape_obs(status=["-Berserk"]), escape=0.35) == "read_teleport"   # no longer slowed
    for st in ([], ["Berserk"], ["Slow"], EXHAUSTED + ["Tele"]):                      # can rage, raging, not after a rage, coming
        assert not policy.escape_rule(escape_obs(status=st), 0.35), st
    assert switch_rules(escape_obs(tele=0), escape=0.35) == "quaff_heal"          # no scroll
    assert switch_rules(escape_obs(), blocked={"read_teleport"}, escape=0.35) == "quaff_heal"
    assert not policy.escape_rule(obs(status=EXHAUSTED, hp=5, hp_max=40), 0.35)      # nothing in view


def test_escape_reaches_the_rules_inside_brain_tiers():
    seen = {}
    for h in (0, 0.5):
        state = make_state(["#########", "#..@....#", "#.......#", "#########"], depth=5, god="Trog")
        state = with_inv(state, s0=item("scroll of teleportation", SCROLLS, 1, letter=ord("c")))
        player(state, hp=10, hp_max=40, status=[{"light": "-Berserk"}, {"light": "Slow"}])
        add_monster(state, (4, 1), 4, "orc")
        tiers = BrainTiers(style=Style(escape=h), rng=random.Random(0))
        seen[h] = tiers.next_action(state)
    assert seen[0] != "read_teleport" and seen[0.5] == "read_teleport"


def unique_obs(dx=4, threat=3, status=(), tele=1, **over):
    mons = [{**mon("Edmund", dx=dx, threat=threat, unique=True), "avghp": 40, "mdam": 0}]
    return obs(**{"god": "Trog", "hp": 40, "hp_max": 40, "status": list(status), "n_hostiles": 1, "mons": mons,
                  "inv": {**SCROLL, "teleport": tele}, **over})


def test_unique_is_off_by_default_and_off_plays_as_before():
    assert Style().unique == 0
    o = unique_obs(dx=2)
    assert switch_rules(o) == switch_rules(o, unique=0) == "berserk"
    assert not policy.unique_rule(o, 0)


def test_unique_reads_teleportation_at_a_dangerous_unique_and_keeps_away_while_it_comes():
    assert switch_rules(unique_obs(dx=2), unique=1) == "read_teleport"
    assert switch_rules(unique_obs(dx=6), unique=1) == "read_teleport"           # as soon as it is seen
    assert switch_rules(unique_obs(dx=6, status=EXHAUSTED), unique=1) == "read_teleport"
    # not when adjacent (the rage is the answer then), not at threat 2, not a plain monster, not while raging
    assert switch_rules(unique_obs(dx=1), unique=1) == "berserk"
    assert switch_rules(unique_obs(dx=2, threat=2), unique=1) == "berserk"
    plain = unique_obs(dx=2)
    plain["mons"][0]["unique"] = False
    assert switch_rules(plain, unique=1) == "berserk"
    assert not policy.unique_rule(unique_obs(status=["Berserk"]), 1)
    assert switch_rules(unique_obs(dx=2, tele=0), unique=1) == "berserk"          # no scroll: as before
    # the teleport is coming: no rage while the unique is at a distance; toward the stairs up, else wait
    coming = unique_obs(dx=2, status=["Tele"])
    assert switch_rules(coming) == "berserk"
    assert switch_rules(coming, unique=1) == "wait"
    assert switch_rules(unique_obs(dx=2, status=["Tele"], dist_up=5), unique=1) == "flee_up"
    assert switch_rules(unique_obs(dx=1, status=["Tele"]), unique=1) == "berserk"   # adjacent: rage after all


def test_unique_reaches_the_rules_inside_brain_tiers_and_leaves_the_level_after_reading():
    seen, left = {}, {}
    for on in (0, 1):
        state = make_state(["#########", "#..@....#", "#.......#", "#########"], depth=5, god="Trog")
        state = with_inv(state, s0=item("scroll of teleportation", SCROLLS, 1, letter=ord("c")))
        add_monster(state, (7, 1), 7, "Edmund", threat=3)
        tiers = BrainTiers(style=Style(unique=on), rng=random.Random(0))
        seen[on] = tiers.next_action(state)
        left[on] = tiers.level_explored
    assert seen[0] != "read_teleport" and seen[1] == "read_teleport"
    assert not left[0] and left[1]


def test_calmfor_limits_calm_to_the_first_turns_on_a_level():
    assert Style().calmfor == 0
    seen = {}
    for calmfor, turns in ((0, 900), (400, 100), (400, 399), (400, 400), (400, 900)):
        tiers = BrainTiers(style=Style(calm=1, calmfor=calmfor), rng=random.Random(0))
        state = stairs_state()
        state.player["status"] = [{"light": "Berserk"}]
        tiers.level_turn = state.turn - turns
        seen[(calmfor, turns)] = tiers.next_action(state)
        assert tiers.calm_now == (seen[(calmfor, turns)] == "rest")
    assert seen == {(0, 900): "rest", (400, 100): "rest", (400, 399): "rest", (400, 400): "explore",
                    (400, 900): "explore"}
    # after T a refusal for the rage counts toward setting explore aside, as without calm
    tiers = BrainTiers(style=Style(calm=1, calmfor=400), rng=random.Random(0))
    state = stairs_state()
    state.player["status"] = [{"light": "Berserk"}]
    tiers.level_turn = state.turn - 500
    tiers.next_action(state)
    tiers.choice = "explore"
    _refuse_explore(tiers, state, CALM_DOWN)
    _refuse_explore(tiers, state, CALM_DOWN)
    assert "explore" in tiers.blocked
    # calmfor without calm does nothing
    tiers = BrainTiers(style=Style(calmfor=400), rng=random.Random(0))
    state = stairs_state()
    state.player["status"] = [{"light": "Berserk"}]
    assert tiers.next_action(state) == "explore" and not tiers.calm_now


def test_escape_unique_and_calmfor_are_styles_and_old_runs_still_match():
    import argparse
    from ladder.brain.cli import _style
    assert _style(argparse.Namespace(style=["escape=0.35", "unique=1", "calmfor=400", "calm=1"])) == \
        Style(escape=0.35, unique=1, calmfor=400, calm=1)
    # a run saved before the three existed was played with them off, which is also their default
    old = {k: v for k, v in Style().to_dict().items() if k not in ("escape", "unique", "calmfor")}
    assert Style.saved(old) == Style()


def test_evaluate_reuses_a_saved_run_only_when_its_style_matches(tmp_path, monkeypatch):
    import argparse
    from ladder.brain import cli
    old = {k: v for k, v in Style().to_dict().items() if k not in ("recover", "retreat")}
    for name in ("eval-baseline", "eval-baseline-recover=0-retreat=0"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "results.json").write_text(json.dumps({"results": [{"game": 500000}], "style": old}))
    played = []
    monkeypatch.setattr(cli, "_play", lambda args, name, seeds, model, eps: played.append(name) or {"results": []})
    # saved before recover and retreat existed: played with both off, so not today's defaults
    for style, reused in (([], False), (["recover=0", "retreat=0"], True)):
        played.clear()
        s = cli.evaluate(argparse.Namespace(style=style, out=str(tmp_path)), None, 1)
        assert (s.get("style") == old) == reused and bool(played) != reused, style


def test_inventory_largest_stack_first():
    state = with_inv(make_state(["@."]), s0=item("fizzy potion", POTIONS, 1, letter=ord("c")),
                     s1=item("murky potion", POTIONS, 3, letter=ord("d")))
    assert inventory(state)["letters"]["unknown_potions"] == "c"
    assert inventory(state, largest=True)["letters"]["unknown_potions"] == "d"
    assert inventory(state, largest=True)["unknown_potions"] == 4


def test_old_evaluations_without_a_new_style_weight_are_still_reused():
    old = {k: v for k, v in Style().to_dict().items() if k != "wiki"}
    assert {**Style().to_dict(), **old} == Style().to_dict()
    assert {**Style().to_dict(), **old} != Style(wiki=1).to_dict()


# --- curing or heal wounds, and poison against the end of a rage --------------------------------

def potions(curing=0, heal_wounds=0):
    return {"heal": curing + heal_wounds, "curing": curing, "heal_wounds": heal_wounds,
            "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 0}


def test_inventory_counts_curing_and_heal_wounds_apart():
    state = with_inv(make_state(["@."]), s0=item("potion of heal wounds", POTIONS, 2, 97),
                     s1=item("potion of curing", POTIONS, 1, 98))
    inv = inventory(state)
    assert (inv["heal"], inv["curing"], inv["heal_wounds"]) == (3, 1, 2)
    assert inv["letters"]["curing"] == "b" and inv["letters"]["heal_wounds"] == "a"
    o = observe(state, [], {})
    assert o["inv"]["curing"] == 1 and o["inv"]["heal_wounds"] == 2
    # not inputs: the vector is the one models were trained on
    s, _, _ = encode(o, ["rest"])
    assert s.shape == (SELF_DIM,)
    assert np.array_equal(s, encode({**o, "inv": {k: v for k, v in o["inv"].items()
                                                  if k not in ("curing", "heal_wounds")}}, ["rest"])[0])


def test_poison_share_counts_as_the_status_line_does():
    assert poison_share(obs(hp=20, poison_survival=20)) == 0
    assert poison_share(obs(hp=20, poison_survival=7)) == 65              # "quite poisoned"
    assert poison_share(obs(hp=20, poison_survival=6)) == 70              # "seriously poisoned"
    assert poison_share(obs(hp=20, poison_survival=0)) == 100             # lethal (webtiles sends max(0, ...))
    assert poison_share({k: v for k, v in obs(hp=12).items() if k != "poison_survival"}) == 0


def test_heal_potion_is_chosen_by_the_need():
    both = potions(curing=1, heal_wounds=1)
    assert heal_potion(obs(hp=8, poison_survival=0, status=["Pois"], inv=both)) == "curing"     # lethal poison
    assert heal_potion(obs(hp=8, poison_survival=2, status=["Pois"], inv=both)) == "curing"     # serious
    assert heal_potion(obs(hp=8, poison_survival=6, status=["Pois"], inv=both)) == "heal_wounds"  # mild: HP first
    assert heal_potion(obs(hp=8, inv=both)) == "heal_wounds"                                    # just hurt
    assert heal_potion(obs(hp=20, status=["Conf"], inv=both)) == "curing"       # heal wounds refused at full HP


def test_heal_potion_falls_back_to_the_one_held():
    lethal = dict(hp=8, poison_survival=0, status=["Pois"])
    assert heal_potion(obs(inv=potions(heal_wounds=1), **lethal)) == "heal_wounds"   # better than nothing
    assert heal_potion(obs(hp=8, inv=potions(curing=1))) == "curing"
    assert heal_potion(obs(hp=8, inv=potions())) is None
    # an observation from before the split (old step logs) has neither count
    assert heal_potion(obs(hp=8, inv={"heal": 1, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 0})) is None


def test_curing_is_drinkable_at_full_hp_only_when_poisoned_or_confused():
    assert "quaff_heal" in available(obs(status=["Pois"], inv=potions(curing=1)), False, set(), False)
    assert "quaff_heal" in available(obs(status=["Conf"], inv=potions(curing=1)), False, set(), False)
    assert "quaff_heal" not in available(obs(status=["Pois"], inv=potions(heal_wounds=1)), False, set(), False)
    assert "quaff_heal" not in available(obs(inv=potions(curing=1)), False, set(), False)


@pytest.mark.parametrize("survival,want,letter", [(0, "curing", "c"), (2, "curing", "c"),
                                                  (6, "heal_wounds", "d"), (8, "heal_wounds", "d")])
def test_perform_drinks_the_potion_the_moment_needs(survival, want, letter):
    state = make_state(["@..."], hp=8, poison_survival=survival,
                       status=[{"light": "Pois"}] if survival < 8 else [])
    with_inv(state, s0=item("potion of curing", POTIONS, 1, ord("c")),
             s1=item("potion of heal wounds", POTIONS, 1, ord("d")))
    conn = ScriptedConn([ActResult(blocking="menu")])
    BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "quaff_heal")
    assert conn.sent == [(("q",), {}), ((letter,), {"through_menu": True})], want


def test_perform_falls_back_to_heal_wounds_while_poisoned_without_curing():
    state = make_state(["@..."], hp=8, poison_survival=0, status=[{"light": "Pois"}])
    with_inv(state, s0=item("potion of heal wounds", POTIONS, 1, ord("d")))
    conn = ScriptedConn([ActResult(blocking="menu")])
    BrainTiers().perform(SimpleNamespace(state=state, conn=conn), "quaff_heal")
    assert conn.sent == [(("q",), {}), (("d",), {"through_menu": True})]


def test_poison_lethal_after_rage_follows_the_hp_scaling():
    # not raging: x3/2 at the start and x2/3 at the end give the HP back, so only poison lethal now counts
    assert not poison_lethal_after_rage(obs(hp=12))
    assert not poison_lethal_after_rage(obs(hp=12, poison_survival=1, status=["Pois"]))
    assert poison_lethal_after_rage(obs(hp=12, poison_survival=0, status=["Pois"]))
    # raging: the end leaves 2/3 of the HP shown, and the poison still to come is not scaled
    assert not poison_lethal_after_rage(obs(hp=30, poison_survival=11, status=["Berserk", "Pois"]))
    assert poison_lethal_after_rage(obs(hp=30, poison_survival=10, status=["Berserk", "Pois"]))
    assert not poison_lethal_after_rage(obs(hp=30, poison_survival=30, status=["Berserk"]))


def test_no_rage_with_poison_that_would_kill_after_it():
    lethal = hostile_obs(god="Trog", hp=12, poison_survival=0, status=["Pois"])
    assert "berserk" not in available(lethal, False, set(), False)
    assert "berserk" in available({**lethal, "poison_survival": 3}, False, set(), False)
    # without curing, the baseline fights on rather than raging
    assert baseline(lethal, available(lethal, False, set(), False), False) == "fight"


def test_baseline_cures_serious_poison_before_raging():
    o = obs(hp=8, poison_survival=2, status=["Pois"], god="Trog", n_hostiles=1, mons=[mon()],
            inv=potions(curing=1, heal_wounds=1))
    avail = available(o, False, set(), False)
    assert "berserk" in avail                                        # survivable: allowed, just not first
    assert baseline(o, avail, False) == "quaff_heal"
    assert baseline(o, avail, False, wiki=True) == "quaff_heal"
    assert heal_potion(o) == "curing"
    # mild poison: the rage comes first as before
    mild = {**o, "poison_survival": 6}
    assert baseline(mild, available(mild, False, set(), False), False) == "berserk"
    # alone and seriously poisoned: cure rather than rest it off
    alone = {**o, "n_hostiles": 0, "mons": []}
    assert baseline(alone, available(alone, False, set(), False), False) == "quaff_heal"
    lethal = {**o, "poison_survival": 0}
    avail = available(lethal, False, set(), False)
    assert "berserk" not in avail and baseline(lethal, avail, False) == "quaff_heal"


# --- the opt-in rule for being hurt with nothing in view (Style.unseen, BrainTiers.assailed) -----------

TELE1 = {"heal": 0, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 1}


def test_unseen_is_2_by_default_and_off_plays_as_before():
    assert Style().unseen == 2
    old = {k: v for k, v in Style().to_dict().items() if k != "unseen"}      # a run saved before the switch
    assert Style.saved(old) == Style(unseen=0) and Style.saved(old) != Style()
    tiers = BrainTiers(style=Style(unseen=0), rng=random.Random(0))
    assert tiers.assailed(obs(status=["Fire"], hp=10, hp_delta=-0.1, dist_up=4)) is None
    assert tiers.assailed(obs(hp=8, hp_delta=-0.1, dist_up=4)) is None
    assert tiers.assailed(obs(hp=8, hp_delta=-0.1, dist_up=4)) is None
    # without the flag nothing changes: no flee_up or read_teleport with nothing in view
    o = obs(status=["Fire"], hp=10, dist_up=4, inv=TELE1)
    avail = available(o, False, set(), False)
    assert "flee_up" not in avail and "read_teleport" not in avail
    assert baseline(o, avail, False) == "rest"


def test_burning_walks_toward_the_stairs_at_level_1():
    tiers = BrainTiers(style=Style(unseen=1), rng=random.Random(0))
    o = obs(status=["Fire"], hp=10, hp_delta=-0.1, dist_up=4, inv=TELE1)
    assert tiers.assailed(o) == policy.BURNING
    avail = available(o, False, set(), False, assailed=policy.BURNING)
    assert "flee_up" in avail and "read_teleport" not in avail
    assert baseline(o, avail, False, assailed=policy.BURNING) == "flee_up"
    # no stairs up known: toward the stairs down instead; neither known: as before
    down = obs(status=["Fire"], hp=10, dist_down=3)
    assert baseline(down, available(down, False, set(), False, assailed=policy.BURNING), False,
                    assailed=policy.BURNING) == "descend"
    none = obs(status=["Fire"], hp=10)
    assert baseline(none, available(none, False, set(), False, assailed=policy.BURNING), False,
                    assailed=policy.BURNING) == "rest"
    # not on D:1, whose stairs up leave the dungeon
    d1 = obs(status=["Fire"], hp=10, depth=1, dist_up=2)
    assert "flee_up" not in available(d1, False, set(), False, assailed=policy.BURNING)
    # with something in view the fight goes on as before
    assert tiers.assailed(obs(status=["Fire"], hp=10, dist_up=4, n_hostiles=1, mons=[mon(dx=3)])) is None
    # level 1 doesn't act on unseen hits
    tiers = BrainTiers(style=Style(unseen=1), rng=random.Random(0))
    for _ in range(3):
        assert tiers.assailed(obs(hp=8, hp_delta=-0.1, dist_up=4)) is None


def test_unseen_hits_read_teleportation_then_go_up_at_level_2():
    tiers = BrainTiers(style=Style(unseen=2), rng=random.Random(0))
    hit = obs(hp=12, hp_delta=-0.1, dist_up=6, inv=TELE1)
    assert tiers.assailed(hit) is None                        # one fall in HP is not enough
    assert tiers.assailed({**hit, "hp_delta": 0.0}) is None    # a choice with no change doesn't break the run
    assert tiers.assailed(hit) == policy.UNSEEN
    avail = available(hit, False, set(), False, assailed=policy.UNSEEN)
    assert "read_teleport" in avail and "flee_up" in avail
    assert baseline(hit, avail, False, assailed=policy.UNSEEN) == "read_teleport"
    # a teleport already coming, or no scroll: up the stairs
    coming = {**hit, "status": ["Tele"]}
    assert baseline(coming, available(coming, False, set(), False, assailed=policy.UNSEEN), False,
                    assailed=policy.UNSEEN) == "flee_up"
    # burning comes first: a step, not a scroll
    assert tiers.assailed({**hit, "status": ["Fire"]}) == policy.BURNING


def test_unseen_hits_reset_and_leave_out_poison_and_the_end_of_a_rage():
    def fresh():
        return BrainTiers(style=Style(unseen=2), rng=random.Random(0))
    hit = obs(hp=12, hp_delta=-0.1, dist_up=6)
    # HP rising breaks the run
    t = fresh()
    t.assailed(hit)
    t.assailed({**hit, "hp_delta": 0.05})
    assert t.assailed(hit) is None
    # something in view breaks it
    t = fresh()
    t.assailed(hit)
    t.assailed({**hit, "n_hostiles": 1, "mons": [mon()]})
    assert t.assailed(hit) is None
    # nor does the fire's own damage: once it is out, the run starts again
    t = fresh()
    fire = {**hit, "status": ["Fire"]}
    assert t.assailed(fire) == policy.BURNING
    assert t.assailed(fire) == policy.BURNING
    assert t.assailed(hit) is None
    assert t.assailed(hit) == policy.UNSEEN
    # poison doesn't count
    t = fresh()
    pois = {**hit, "status": ["Pois"]}
    t.assailed(pois)
    assert t.assailed(pois) is None
    # nor the HP a rage takes with it as it ends
    t = fresh()
    t.assailed({**hit, "status": ["Berserk"], "hp_delta": 0.0})
    t.assailed({**hit, "status": ["-Berserk", "Slow"]})
    assert t.assailed({**hit, "status": ["-Berserk", "Slow"], "hp_delta": 0.0}) is None
    assert t.assailed({**hit, "status": ["-Berserk", "Slow"]}) is None       # the first hit after it
    assert t.assailed({**hit, "status": ["-Berserk", "Slow"]}) == policy.UNSEEN
