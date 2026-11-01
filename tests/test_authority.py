import pytest

from ladder.authority import (ASSISTED, AUTONOMOUS, CONDITIONAL, Authority, Pending, Rule,
                              condition_holds)


def test_assisted_mode_follows_the_rules():
    a = Authority()
    assert a.decide("pick_up_item").decider == "strategy"
    assert a.decide("quaff_unknown").decider == "player"
    assert a.decide("choose_god").decider == "player"


def test_conditional_deferral():
    a = Authority()
    assert a.decide("descend_stairs", {"level_explored": False, "threat": 0.4}).decider == "player"
    assert a.decide("descend_stairs", {"level_explored": True}).decider == "strategy"
    assert a.decide("descend_stairs", {"threat": 2.3}).decider == "strategy"


def test_autonomous_mode_decides_everything_including_pins():
    a = Authority(mode=AUTONOMOUS)
    for t in ("choose_god", "engage_unique", "quaff_unknown", "descend_stairs"):
        assert a.decide(t).decider == "strategy"


def test_idle_switch_hands_over_after_the_set_minutes():
    a = Authority(idle_minutes=10)
    pending = Pending("quaff_unknown", posted_at=1000.0)
    assert a.check_idle(pending, now=1000.0 + 9 * 60) is None
    verdict = a.check_idle(pending, now=1000.0 + 10 * 60)
    assert verdict.decider == "strategy"
    assert a.mode == AUTONOMOUS and a.switched_by_idle
    a.set_mode(ASSISTED)                                # the player comes back
    assert not a.switched_by_idle and a.decide("quaff_unknown").decider == "player"


def test_idle_zero_means_never():
    a = Authority(idle_minutes=0)
    assert a.check_idle(Pending("choose_god", 0.0), now=10 ** 9) is None
    with pytest.raises(ValueError):
        Authority(idle_minutes=-1)


def test_condition_terms():
    assert condition_holds(["hp_frac < 0.25"], {"hp_frac": 0.2})
    assert not condition_holds(["hp_frac < 0.25", "level_explored"], {"hp_frac": 0.5})
    with pytest.raises(ValueError):
        condition_holds(["threat => 2"], {})
    assert Authority(rules={"x": Rule(CONDITIONAL, ["threat >= 1"])}).decide("x", {"threat": 1}).decider == "strategy"
