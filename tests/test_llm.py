"""Adapters against stand-in SDK clients: request shapes in, normalized responses out."""

import json
from types import SimpleNamespace as NS

import pytest

from ladder.llm import (FALLBACK_BETA, AnthropicAdapter, CapabilityError, OpenAIAdapter, Request, Tool,
                        adapter_for, check)
from ladder.profiles import Profile, for_tier, load

SCHEMA = {"type": "object", "properties": {"pick": {"type": "string"}}, "required": ["pick"],
          "additionalProperties": False}
TOOL = Tool("fight_melee", "Attack one adjacent monster", {
    "type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"],
    "additionalProperties": False})

OPUS = Profile("anthropic", "anthropic", "https://api.anthropic.com", "claude-opus-5",
               supports=("tools", "json_schema", "effort", "fallbacks"), fallbacks="default")
DS_ANTH = Profile("deepseek-anth", "anthropic", "https://api.deepseek.com/anthropic", "deepseek-chat",
                  supports=("tools",))
DS_OAI = Profile("deepseek-oai", "openai", "https://api.deepseek.com", "deepseek-chat",
                 supports=("tools", "json_object"))
OAI_SCHEMA = Profile("local", "openai", "http://localhost:11434/v1", "qwen", supports=("tools", "json_schema"))


class FakeAnthropic:
    def __init__(self, content, stop_reason="end_turn"):
        self.calls = []
        msg = NS(content=content, stop_reason=stop_reason, model="claude-opus-5",
                 usage={"input_tokens": 120, "output_tokens": 30})
        create = lambda **kw: (self.calls.append(kw), msg)[1]
        self.messages = NS(create=create)
        self.beta = NS(messages=NS(create=create))


class FakeOpenAI:
    def __init__(self, message, finish_reason="stop"):
        self.calls = []
        completion = NS(choices=[NS(message=message, finish_reason=finish_reason)], model="deepseek-chat",
                        usage={"prompt_tokens": 100, "completion_tokens": 20})
        self.chat = NS(completions=NS(create=lambda **kw: (self.calls.append(kw), completion)[1]))


def test_anthropic_json_with_default_fallbacks():
    fake = FakeAnthropic([NS(type="text", text=json.dumps({"pick": "A"}))])
    resp = AnthropicAdapter(OPUS, fake).complete(
        Request("You advise a DCSS player.", [{"role": "user", "content": "Orcs ahead."}], json_schema=SCHEMA))
    sent = fake.calls[0]
    assert sent["model"] == "claude-opus-5"
    assert sent["fallbacks"] == "default" and sent["betas"] == [FALLBACK_BETA]
    assert sent["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
    assert "thinking" not in sent                      # Opus 5 runs adaptive thinking by default
    assert resp.data == {"pick": "A"} and not resp.refused


def test_anthropic_tools_are_strict_and_tool_calls_come_back():
    fake = FakeAnthropic([NS(type="tool_use", id="tu_1", name="fight_melee", input={"target": "rat"})],
                         stop_reason="tool_use")
    resp = AnthropicAdapter(OPUS, fake).complete(Request("s", [{"role": "user", "content": "rat"}], tools=[TOOL]))
    assert fake.calls[0]["tools"][0]["strict"] is True
    assert resp.tool_calls[0].name == "fight_melee" and resp.tool_calls[0].input == {"target": "rat"}


def test_anthropic_refusal_is_flagged_not_parsed():
    fake = FakeAnthropic([], stop_reason="refusal")
    resp = AnthropicAdapter(OPUS, fake).complete(Request("s", [{"role": "user", "content": "x"}], json_schema=SCHEMA))
    assert resp.refused and resp.data is None


def test_custom_anthropic_endpoint_without_fallbacks_uses_plain_messages():
    fake = FakeAnthropic([NS(type="text", text="ok")])
    AnthropicAdapter(DS_ANTH, fake).complete(Request("s", [{"role": "user", "content": "x"}]))
    assert "fallbacks" not in fake.calls[0] and "betas" not in fake.calls[0]


def test_capability_check_refuses_json_on_a_profile_without_it():
    with pytest.raises(CapabilityError, match="lacks json"):
        AnthropicAdapter(DS_ANTH, FakeAnthropic([])).complete(
            Request("s", [{"role": "user", "content": "x"}], json_schema=SCHEMA))


def test_openai_json_object_puts_schema_in_the_system_prompt():
    fake = FakeOpenAI(NS(content='{"pick": "B"}', tool_calls=None, refusal=None))
    resp = OpenAIAdapter(DS_OAI, fake).complete(
        Request("You advise a DCSS player.", [{"role": "user", "content": "Orcs."}], json_schema=SCHEMA))
    sent = fake.calls[0]
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["messages"][0]["role"] == "system" and '"pick"' in sent["messages"][0]["content"]
    assert resp.data == {"pick": "B"}


def test_openai_json_schema_and_tool_calls():
    call = NS(id="call_1", function=NS(name="fight_melee", arguments='{"target": "rat"}'))
    fake = FakeOpenAI(NS(content=None, tool_calls=[call], refusal=None), finish_reason="tool_calls")
    resp = OpenAIAdapter(OAI_SCHEMA, fake).complete(
        Request("s", [{"role": "user", "content": "rat"}], tools=[TOOL]))
    assert fake.calls[0]["tools"][0]["function"]["strict"] is True
    assert resp.tool_calls[0].input == {"target": "rat"} and resp.stop_reason == "tool_calls"
    fake = FakeOpenAI(NS(content='{"pick": "C"}', tool_calls=None, refusal=None))
    OpenAIAdapter(OAI_SCHEMA, fake).complete(Request("s", [{"role": "user", "content": "x"}], json_schema=SCHEMA))
    assert fake.calls[0]["response_format"]["type"] == "json_schema"


def test_adapter_for_picks_by_style_and_rejects_systemone():
    assert isinstance(adapter_for(DS_OAI, FakeOpenAI(NS())), OpenAIAdapter)
    with pytest.raises(ValueError):
        adapter_for(Profile("typesafe", "systemone", "https://api.typesafe.ai", "jev-latest"))


def test_repo_tiers_use_opus_5_and_spares_cover_both_styles():
    assert for_tier("strategy").model == "claude-opus-5"
    assert for_tier("tactics").model == "claude-opus-5"
    profiles, _ = load()
    assert {p.style for p in profiles.values()} >= {"anthropic", "openai", "systemone"}
    check(profiles["deepseek-oai"], {"json"})
    with pytest.raises(CapabilityError):
        check(profiles["deepseek-anth"], {"json"})
