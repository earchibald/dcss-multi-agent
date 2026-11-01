import json

import pytest

from ladder import jeveval, keychain
from ladder.jev import QUESTIONS, Answers, Jev, build_state
from ladder.profiles import MissingKey, Profile, load
from ladder.routing import Thresholds, needs_jev, route

PROFILE = Profile("typesafe", "systemone", "https://api.typesafe.ai", "jev-latest", "dcss-ladder", "typesafe")


def record(kind="hostile_in_view", decision_type=None, game=1, step=1, hostiles=None, **detail):
    return {
        "game": game, "step": step, "action": "explore", "kind": kind, "source": "dcss",
        "decision_type": decision_type, "detail": detail,
        "snapshot": {"place": "D:2", "turn": 900, "hp": 20, "hp_max": 27, "xl": 3, "species": "Minotaur",
                     "god": "Trog", "status": [], "hostiles": hostiles or []},
        "messages": ["You encounter an adder."],
    }


def response(threat=0.4, needs_plan=0.1, unfamiliar=0.2, worthy=0.1, goal="fight_melee", goal_conf=0.9):
    """Shaped like the documented SystemOneResponse."""
    return {"model": "jev-1", "usage": {"input_tokens": 300, "output_tokens": 10}, "answers": {
        "threat": {"type": "score", "score": threat, "confidence": 0.8, "probabilities": {}},
        "needs_plan": {"type": "noul", "noul": needs_plan},
        "unfamiliar": {"type": "noul", "noul": unfamiliar},
        "player_worthy": {"type": "noul", "noul": worthy},
        "next_goal": {"type": "choice", "choice": goal, "confidence": goal_conf, "probabilities": {}},
    }}


def answers(**kw):
    return Answers.parse(response(**kw)["answers"])


def test_question_set_shape():
    assert QUESTIONS["threat"]["type"] == "score" and len(QUESTIONS["threat"]["criteria"]) == 4
    assert {QUESTIONS[q]["type"] for q in ("needs_plan", "unfamiliar", "player_worthy")} == {"noul"}
    assert "none" in QUESTIONS["next_goal"]["criteria"]


def test_state_names_the_parts_the_questions_reference():
    state = build_state(record(hostiles=[{"name": "adder", "dist": 4, "threat": "tough"}]), ["rat"])
    assert set(state) == {"interrupt", "player", "monsters", "recent_messages", "seen_before"}
    assert state["monsters"] == [{"name": "adder", "distance": 4, "threat_estimate": "tough"}]
    assert state["player"]["hp"] == "20/27"


@pytest.mark.parametrize("rec, ans, tier, rule", [
    (record("feature_in_view", "descend_stairs", feature="downstairs"), None, "strategy", 1),
    (record("level_change"), None, "none", 0),
    (record(), answers(threat=2.4), "strategy", 2),
    (record(), answers(needs_plan=0.8), "strategy", 2),
    (record(), answers(worthy=0.75), "strategy", 3),
    (record(), answers(threat=0.3, goal="fight_melee", goal_conf=0.9), "reflex_goal", 4),
    (record(), answers(threat=0.3, goal="fight_melee", goal_conf=0.5), "tactics", 5),
    (record(), answers(threat=1.3, goal="fight_melee", goal_conf=0.95), "tactics", 5),
    (record(), answers(threat=0.3, goal="none", goal_conf=0.95), "tactics", 5),
])
def test_routing_rules(rec, ans, tier, rule):
    r = route(rec, ans)
    assert (r.tier, r.rule) == (tier, rule)


def test_thresholds_move_the_boundary():
    assert route(record(), answers(threat=1.7)).tier == "tactics"
    assert route(record(), answers(threat=1.7), Thresholds(threat=1.5)).tier == "strategy"


def test_rule_one_and_bookkeeping_skip_jev():
    assert not needs_jev(record("feature_in_view", "choose_god", feature="altar"))
    assert not needs_jev(record("xl_up"))
    assert needs_jev(record("item_in_view"))


def test_client_sends_documented_request_with_keychain_key(monkeypatch):
    monkeypatch.setattr(keychain, "get_item", lambda service, account: "sk-test")
    sent = {}

    def transport(url, headers, body):
        sent.update(url=url, headers=headers, body=body)
        return response(threat=1.1)

    result = Jev(PROFILE, transport).ask({"interrupt": {"kind": "hostile_in_view"}})
    assert sent["url"] == "https://api.typesafe.ai/v1/systemone"
    assert sent["headers"]["Authorization"] == "Bearer sk-test"
    assert sent["body"]["model"] == "jev-latest" and set(sent["body"]["questions"]) == set(QUESTIONS)
    assert result.answers.threat == 1.1 and result.usage["input_tokens"] == 300


def test_missing_key_explains_how_to_add_it(monkeypatch):
    monkeypatch.setattr(keychain, "get_item", lambda service, account: None)
    with pytest.raises(MissingKey, match="security add-generic-password -s dcss-ladder -a typesafe -w"):
        PROFILE.api_key()


def test_repo_profiles_point_jev_at_its_own_keychain_item():
    profiles, tiers = load()
    p = profiles[tiers["jev"]]
    assert (p.style, p.keychain_service, p.keychain_account) == ("systemone", "dcss-ladder", "typesafe")


def test_evaluate_then_retune_without_new_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(keychain, "get_item", lambda service, account: "sk-test")
    recs = [
        record(step=1, hostiles=[{"name": "rat", "dist": 3, "threat": "trivial"}]),
        record("feature_in_view", "descend_stairs", step=2, feature="downstairs"),
        record(step=3, hostiles=[{"name": "orc priest", "dist": 6, "threat": "tough"}]),
        record("xl_up", step=4),
    ]
    (tmp_path / "interrupts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
    replies = iter([response(threat=0.2, goal_conf=0.9), response(threat=1.8, needs_plan=0.4)])
    calls = []

    def transport(url, headers, body):
        calls.append(body["state"])
        return next(replies)

    summary = jeveval.evaluate(tmp_path, Jev(PROFILE, transport))
    assert summary["jev_calls"] == 2
    assert summary["by_tier"] == {"reflex_goal": 1, "strategy": 1, "tactics": 1, "none": 1}
    assert calls[1]["seen_before"] == ["rat", "downstairs"]

    tuned = jeveval.retune(tmp_path, Thresholds(threat=1.5))
    assert tuned["by_tier"]["strategy"] == 2 and len(calls) == 2
    assert len(tuned["sweep"]) == 27
