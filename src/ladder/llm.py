"""LLM adapters for the Tactics and Strategy tiers.

One small call interface, one adapter per API style:
  - "anthropic": the official Anthropic SDK, any base URL (api.anthropic.com,
    DeepSeek's /anthropic endpoint, …)
  - "openai":    the official OpenAI SDK against any Chat Completions-compatible
    base URL (DeepSeek, local servers, …)
Tiers ask for capabilities ("tools", "json"); profiles declare what they support.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from .profiles import Profile

# What each capability flag in profiles.toml means
CAPABILITIES = {
    "tools": "function/tool calling",
    "json_schema": "JSON output constrained to a schema",
    "json_object": "JSON output without a schema (schema goes in the prompt)",
    "effort": "Anthropic output_config.effort",
    "fallbacks": "Anthropic server-side refusal fallbacks",
}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class CapabilityError(RuntimeError):
    pass


@dataclass
class Tool:
    name: str
    description: str
    schema: dict                    # JSON Schema for the arguments; strict-mode shaped


@dataclass
class Request:
    system: str
    messages: list[dict]            # [{"role": "user" | "assistant", "content": str}]
    json_schema: dict | None = None
    tools: list[Tool] = field(default_factory=list)
    max_tokens: int = 16000


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class Response:
    text: str
    data: Any = None                # parsed JSON when a schema was requested
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = ""
    refused: bool = False
    model: str = ""
    usage: dict = field(default_factory=dict)


class Adapter(Protocol):
    profile: Profile

    def complete(self, request: Request) -> Response: ...


def needs(request: Request) -> set[str]:
    out = set()
    if request.tools:
        out.add("tools")
    if request.json_schema is not None:
        out.add("json")
    return out


def check(profile: Profile, required: set[str]) -> None:
    """Refuse a profile that can't provide what a tier needs. "json" is met by either JSON flag."""
    have = set(profile.supports)
    missing = [c for c in required if not (c == "json" and have & {"json_schema", "json_object"}) and c not in have]
    if missing:
        raise CapabilityError(f"profile '{profile.name}' lacks {', '.join(sorted(missing))}")


def _usage(obj) -> dict:
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return {k: v for k, v in obj.model_dump().items() if isinstance(v, int)}
    return dict(obj)


class AnthropicAdapter:
    def __init__(self, profile: Profile, client=None):
        self.profile = profile
        if client is None:
            import anthropic
            # With no Keychain item named, the SDK resolves credentials itself
            # (ANTHROPIC_API_KEY, or an `ant auth login` profile).
            client = anthropic.Anthropic(api_key=profile.api_key(), base_url=profile.base_url) \
                if profile.keychain_service else anthropic.Anthropic(base_url=profile.base_url)
        self.client = client

    def complete(self, request: Request) -> Response:
        check(self.profile, needs(request))
        kwargs: dict = {
            "model": self.profile.model,
            "max_tokens": request.max_tokens,
            "system": request.system,
            "messages": request.messages,
        }
        output_config: dict = {}
        if request.json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.json_schema}
        if self.profile.effort and "effort" in self.profile.supports:
            output_config["effort"] = self.profile.effort
        if output_config:
            kwargs["output_config"] = output_config
        if request.tools:
            kwargs["tools"] = [{"name": t.name, "description": t.description, "strict": True,
                                "input_schema": t.schema} for t in request.tools]
        if self.profile.fallbacks and "fallbacks" in self.profile.supports:
            kwargs["fallbacks"] = self.profile.fallbacks
            kwargs["betas"] = [FALLBACK_BETA]
            msg = self.client.beta.messages.create(**kwargs)
        else:
            msg = self.client.messages.create(**kwargs)

        refused = msg.stop_reason == "refusal"
        text = "".join(b.text for b in msg.content if b.type == "text") if not refused else ""
        calls = [ToolCall(b.id, b.name, b.input) for b in msg.content if b.type == "tool_use"]
        data = json.loads(text) if request.json_schema is not None and text else None
        return Response(text=text, data=data, tool_calls=calls, stop_reason=msg.stop_reason or "",
                        refused=refused, model=msg.model, usage=_usage(msg.usage))


class OpenAIAdapter:
    def __init__(self, profile: Profile, client=None):
        self.profile = profile
        if client is None:
            import openai
            client = openai.OpenAI(api_key=profile.api_key() or "none", base_url=profile.base_url)
        self.client = client

    def complete(self, request: Request) -> Response:
        check(self.profile, needs(request))
        system = request.system
        kwargs: dict = {"model": self.profile.model, "max_tokens": request.max_tokens}
        if request.json_schema is not None:
            if "json_schema" in self.profile.supports:
                kwargs["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": "result", "schema": request.json_schema, "strict": True}}
            else:
                kwargs["response_format"] = {"type": "json_object"}
                system += ("\n\nReply with a single JSON object that matches this JSON Schema:\n"
                           + json.dumps(request.json_schema))
        if request.tools:
            kwargs["tools"] = [{"type": "function", "function": {
                "name": t.name, "description": t.description, "parameters": t.schema, "strict": True}}
                for t in request.tools]
        kwargs["messages"] = [{"role": "system", "content": system}, *request.messages]
        completion = self.client.chat.completions.create(**kwargs)

        choice = completion.choices[0]
        message = choice.message
        refusal = getattr(message, "refusal", None)
        text = message.content or ""
        calls = [ToolCall(c.id, c.function.name, json.loads(c.function.arguments or "{}"))
                 for c in (message.tool_calls or [])]
        data = json.loads(text) if request.json_schema is not None and text and not refusal else None
        return Response(text=text, data=data, tool_calls=calls, stop_reason=choice.finish_reason or "",
                        refused=bool(refusal), model=completion.model, usage=_usage(completion.usage))


ADAPTERS = {"anthropic": AnthropicAdapter, "openai": OpenAIAdapter}


def adapter_for(profile: Profile, client=None) -> Adapter:
    try:
        cls = ADAPTERS[profile.style]
    except KeyError:
        raise ValueError(f"profile '{profile.name}' has style '{profile.style}', not an LLM style") from None
    return cls(profile, client)
