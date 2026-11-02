"""Model profiles: a tier points at a profile, a profile names its Keychain item."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import keychain

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "profiles.toml"


class MissingKey(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    style: str
    base_url: str
    model: str
    keychain_service: str | None = None
    keychain_account: str | None = None
    supports: tuple[str, ...] = ()
    effort: str | None = None
    fallbacks: str | None = None
    thinking: str | None = None     # "enabled" | "disabled", for models that think by default

    def api_key(self) -> str | None:
        """The profile's key from Keychain. Local endpoints may have none."""
        if not self.keychain_service:
            return None
        key = keychain.get_item(self.keychain_service, self.keychain_account)
        if not key:
            raise MissingKey(
                f"No Keychain item for profile '{self.name}' (service '{self.keychain_service}', "
                f"account '{self.keychain_account}'). Add it with:\n"
                f"  security add-generic-password -s {self.keychain_service} -a {self.keychain_account} -w"
            )
        return key


def load(path: str | Path = DEFAULT_PATH) -> tuple[dict[str, Profile], dict[str, str]]:
    data = tomllib.loads(Path(path).read_text())
    profiles = {}
    for name, p in data.get("profiles", {}).items():
        kc = p.get("keychain") or {}
        profiles[name] = Profile(name=name, style=p["style"], base_url=p["base_url"].rstrip("/"),
                                 model=p["model"], keychain_service=kc.get("service"),
                                 keychain_account=kc.get("account"), supports=tuple(p.get("supports", ())),
                                 effort=p.get("effort"), fallbacks=p.get("fallbacks"),
                                 thinking=p.get("thinking"))
    return profiles, dict(data.get("tiers", {}))


# What each LLM tier needs from its profile (see llm.CAPABILITIES)
TIER_NEEDS = {"tactics": {"json"}, "strategy": {"json"}}


def for_tier(tier: str, path: str | Path = DEFAULT_PATH) -> Profile:
    profiles, tiers = load(path)
    profile = profiles[tiers[tier]]
    if tier in TIER_NEEDS:
        from .llm import check
        check(profile, TIER_NEEDS[tier])
    return profile
