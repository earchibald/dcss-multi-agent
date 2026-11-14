"""What the brain knows about a monster from its name: a table shipped with the package.

`monsters-0.34.json` beside this file is a compact copy of `docs/data/monsters-0.34.json` (made from
DCSS 0.34's mon-data.h by tools/knowledge/monsters.py): hit dice, average HP, the sum of its attacks'
maximum damage, speed (10 = normal), experience, and a few kinds of threat. It ships inside
`src/ladder` so every worker that plays the brain has it. Rebuild it after the source changes with

    uv run python -m ladder.brain.monsters docs/data/monsters-0.34.json

`lookup` maps a name as webtiles shows it ("the Ogre", "orc zombie", "spectral ogre", "Grum the Hunter")
to an entry, with the same fallbacks as tools/risk's MonsterBook.
"""

from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path

TABLE = Path(__file__).with_name("monsters-0.34.json")

# The kinds of threat the brain is told about, each from the source's tags, flags, attack flavours and
# spells. Kept few: each one wants a different answer in a fight (docs/wiki-strategy.md, section 3).
KINDS = ("ranged", "poison", "disables", "blinks", "summons", "drains", "smites", "reach")
_DISABLES = {"paralyses", "petrifies", "sleep", "mesmerises", "ensnares", "slows", "confuses", "drags",
             "anchors", "banishes"}
_DRAINS = {"drains", "corrodes", "weakens", "vampiric", "strips willpower", "antimagic"}
# a spell counts as an attack from range when its name says so (the source has no targeting field)
_RANGED_SPELL = re.compile(
    r"bolt|shot|arrow|spit|breath|throw|hurl|ball|lance|ray\b|dart|blast|beam|barrage|bullet|cannonade|"
    r"spray|splinter|icicle|strike|smiting|torment|pain|agony|gaze|orb |damnation|lightning|fire storm|"
    r"brain bite|sting|shock|freeze|flay|irradiate|mindburst|siphon|drain life|vampiric|creeping frost|"
    r"bombard|mortar|eruption|surge|sandblast|gust|vortex|seracfall|landbreaker|upheaval|harpoon|bolas|"
    r"barbs|primal wave|glaciate|chain|airstrike|refrigeration|flash freeze|resonance|venom",
    re.IGNORECASE)


def _kinds(m: dict) -> list[str]:
    tags = set(m.get("tags") or [])
    flags = set(m.get("flags") or [])
    flavours = {a.get("flavour", "") for a in m.get("attacks") or []}
    spells = [s.get("spell", "") for s in m.get("spells") or []]
    has = {
        "ranged": bool(flags & {"archer", "prefer ranged"}) or any(_RANGED_SPELL.search(s) for s in spells),
        "poison": "poison" in tags or any(f.startswith("poison") for f in flavours),
        "disables": bool(tags & _DISABLES) or bool(flavours & {"confuse", "poison paralyse", "minipara"}),
        "blinks": "blinks" in tags or "swoop" in tags,
        "summons": "summons" in tags,
        "drains": bool(tags & _DRAINS) or bool(flavours & {"drain", "vampiric", "corrode", "acid", "antimagic"}),
        "smites": "smites" in tags,
        "reach": "reach" in tags or any("reach" in f for f in flavours),
    }
    return [k for k in KINDS if has[k]]


def compact(source: str | Path) -> dict:
    """The shipped table, from the full monster data."""
    data = json.loads(Path(source).read_text())
    out = {}
    for m in data["monsters"]:
        out[m["name"].lower()] = {
            "hd": m.get("hd") or 0, "hp": round(float(m.get("hp") or 0.0), 1), "speed": m.get("speed") or 10,
            "dmg": sum(a.get("damage", 0) or 0 for a in m.get("attacks") or []), "exp": m.get("exp") or 0,
            "kinds": _kinds(m),
        }
    return {"version": data["meta"]["version"], "source": str(source), "monsters": out}


@lru_cache(maxsize=1)
def table() -> dict[str, dict]:
    return json.loads(TABLE.read_text())["monsters"]


DERIVED = ("zombie", "skeleton", "simulacrum")


@lru_cache(maxsize=4096)
def lookup(name: str) -> dict | None:
    """The table's entry for a monster name as the game shows it, or None."""
    by = table()
    key = (name or "").strip().lower()
    for k in (key, key.removeprefix("the "), key.removeprefix("a "), key.removeprefix("an ")):
        if k in by:
            return by[k]
    words = key.split()
    if not words:
        return None
    if words[0] == "dancing":
        return by.get("dancing weapon")
    if words[-1] == "beast" and len(words) > 1:
        return by.get("mutant beast")              # "larval weirdsting beast" and the like
    if words[0] == "spectral" and " ".join(words[1:]) in by:
        return by[" ".join(words[1:])]
    if words[-1] in DERIVED and " ".join(words[:-1]) in by:
        return by[" ".join(words[:-1])]
    # vault names ("Grum the Hunter") and adjectives: try shorter tails, then heads
    for i in range(1, len(words)):
        if " ".join(words[i:]) in by:
            return by[" ".join(words[i:])]
    for i in range(len(words) - 1, 0, -1):
        if " ".join(words[:i]) in by:
            return by[" ".join(words[:i])]
    if key.endswith("s") and key[:-1] in by:
        return by[key[:-1]]
    return None


if __name__ == "__main__":
    TABLE.write_text(json.dumps(compact(sys.argv[1] if len(sys.argv) > 1 else "docs/data/monsters-0.34.json"),
                                separators=(",", ":"), sort_keys=True))
    print(f"wrote {TABLE} ({TABLE.stat().st_size // 1024} KB, {len(table())} monsters)")
