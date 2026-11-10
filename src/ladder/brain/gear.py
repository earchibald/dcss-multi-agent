"""Which weapon and armour in the pack are better than what is in use.

The brain's `wield` and `wear` actions decide *when* to change equipment; this module decides *what*,
by a fixed ranking. The rc's autopickup function (crawlrc.txt) collects the same kinds of item.

Only maces and flails are ranked, because that is the skill the self-play character trains: a weapon
of another kind is neither picked nor replaced. Artefacts are left alone (their properties can be bad,
and some ask "really?" before they go on).

The webtiles protocol says which slot the weapon is in (`weapon_index`) but not what is worn, so the
brain keeps `worn` itself: {kind: inventory slot}, seeded at the start of a game and kept current from
the "You finish putting on..." messages.
"""

from __future__ import annotations

import re

from ..state import GameState

WEAPON, ARMOUR = 0, 2

# base name -> (damage, attack delay, hands)
WEAPONS = {
    "club": (5, 13, 1), "whip": (6, 11, 1), "mace": (8, 14, 1), "flail": (10, 14, 1),
    "morningstar": (13, 15, 1), "demon whip": (11, 11, 1), "sacred scourge": (12, 11, 1),
    "eveningstar": (15, 15, 1), "dire flail": (13, 13, 2), "great mace": (17, 17, 2),
}
# base name -> (kind, score): armour class for body armour, a nominal 1 for the small pieces
ARMOURS = {
    "robe": ("body", 2), "animal skin": ("body", 2), "leather armour": ("body", 3),
    "troll leather armour": ("body", 4), "ring mail": ("body", 5), "scale mail": ("body", 6),
    "chain mail": ("body", 8), "plate armour": ("body", 10), "crystal plate armour": ("body", 14),
    "dragon scales": ("body", 8), "steam dragon scales": ("body", 5), "acid dragon scales": ("body", 6),
    "swamp dragon scales": ("body", 7), "gold dragon scales": ("body", 12),
    "cloak": ("cloak", 1), "scarf": ("cloak", 0.5), "gloves": ("gloves", 1), "boots": ("boots", 1),
    "hat": ("head", 0.5), "helmet": ("head", 1), "buckler": ("shield", 3), "kite shield": ("shield", 5),
}
BAD_BRANDS = ("distortion", "chaos", "ponderousness", "harm")
ARTEFACT = re.compile(r'"| of the |\{')
MIN_GAIN = 0.5


def _match(name: str, table: dict):
    """The entry for the longest base name found in `name` ("great mace" before "mace")."""
    low = name.lower()
    hits = [k for k in table if re.search(rf"\b{re.escape(k)}\b", low)]
    return table[max(hits, key=len)] if hits else None


def _usable(item: dict, base_type: int) -> bool:
    name = item.get("name", "")
    return (item.get("base_type") == base_type and (item.get("quantity", 1) or 0) > 0 and not item.get("useless")
            and not ARTEFACT.search(name) and not any(b in name for b in BAD_BRANDS))


def weapon(item: dict) -> tuple[float, int] | None:
    """(score, hands) for a weapon the brain ranks, else None."""
    entry = _match(item.get("name", ""), WEAPONS) if _usable(item, WEAPON) else None
    if entry is None:
        return None
    damage, delay, hands = entry
    branded = " of " in item["name"]
    return damage + (item.get("plus") or 0) - 0.5 * (delay - 14) + (2 if branded else 0), hands


def armour(item: dict) -> tuple[str, float] | None:
    """(kind, score) for a piece of armour the brain ranks, else None."""
    entry = _match(item.get("name", ""), ARMOURS) if _usable(item, ARMOUR) else None
    if entry is None:
        return None
    kind, score = entry
    return kind, score + (item.get("plus") or 0) + (0.5 if " of " in item["name"] else 0)


def initial_worn(state: GameState) -> dict[str, str]:
    """At the start of a game everything wearable in the pack is on."""
    worn = {}
    for slot, item in (state.player.get("inv") or {}).items():
        if (a := armour(item)):
            worn.setdefault(a[0], str(slot))
    return worn


def upgrades(state: GameState, worn: dict[str, str]) -> dict[str, str | None]:
    """{"wield": letter or None, "wear": letter or None}: the best change of each sort, if any is better."""
    inv = state.player.get("inv") or {}
    wielded = inv.get(str(state.player.get("weapon_index", -1)))
    current = weapon(wielded) if wielded else None
    if current:
        # corrosion shows as a minus on the weapon in hand only; without this the brain swaps to the
        # spare, which then shows the minus instead, and back again every turn
        corr = next((int(m.group(1)) for s in state.statuses if (m := re.match(r"Corr \(-(\d+)\)", s))), 0)
        current = (current[0] + corr, current[1])
    out: dict[str, str | None] = {"wield": None, "wear": None}
    if current:                                   # only ever trade one ranked weapon for another
        best = current[0] + MIN_GAIN
        for item in inv.values():
            w = weapon(item)
            if w and item is not wielded and w[0] >= best and not (w[1] == 2 and "shield" in worn):
                best, out["wield"] = w[0], chr(item.get("letter", 0))
    two_handed = bool(current and current[1] == 2)
    gain = 0.0
    for slot, item in inv.items():
        a = armour(item)
        if not a or worn.get(a[0]) == str(slot) or (a[0] == "shield" and (two_handed or not current)):
            continue
        on = armour(inv.get(worn.get(a[0], ""), {}))
        better = a[1] - (on[1] if on else 0.0)
        if better >= MIN_GAIN and better > gain:
            gain, out["wear"] = better, chr(item.get("letter", 0))
    return out


def kind_of(state: GameState, letter: str) -> tuple[str, str] | None:
    """(kind, inventory slot) of the armour with this letter."""
    for slot, item in (state.player.get("inv") or {}).items():
        if chr(item.get("letter", 0)) == letter and (a := armour(item)):
            return a[0], str(slot)
    return None
