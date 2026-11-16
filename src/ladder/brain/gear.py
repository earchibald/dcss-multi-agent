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

WEAPON, ARMOUR, SCROLLS = 0, 2, 5

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

# --- `Style.kit` only: nothing below changes what is ranked or worn with it off -------------------------------
# The heaviest shield (SH 13, against the kite shield's 8 and the buckler's 3 in item-prop.cc), ranked a little
# above the kite shield. qw wears a shield whenever it has one (SHIELD_CRAZY).
KIT_ARMOURS = {**ARMOURS, "tower shield": ("shield", 7)}
JEWELLERY = 6             # OBJ_JEWELLERY
RING_SLOTS = 2
# What a ring or amulet is worth to a Minotaur Berserker of Trog with a mace, by qw's own valuation
# (runs/qw/build-zk/qw.lua: item_property, linear_property_value 3033-3058, absolute_property_value 2760-2878 at
# level 1, with no Slime or Zot planned). (per point of the ring's plus, flat value). Jewellery is identified when
# picked up in 0.34; a kind left out (intelligence, wizardry, magical power, stealth, magic regeneration, wildshape,
# chemistry, dissipation, nothing) is worth nothing to this character and is never put on.
JEWEL_VALUES = {
    "ring of protection": (50, 0), "ring of evasion": (50, 0), "ring of slaying": (50, 0),
    "ring of strength": (35, 0), "ring of dexterity": (15, 0),
    "ring of poison resistance": (0, 225), "ring of see invisible": (0, 200), "ring of flight": (0, 200),
    "ring of protection from fire": (0, 125), "ring of protection from cold": (0, 125),
    "ring of willpower": (0, 100), "ring of resist corrosion": (0, 50), "ring of positive energy": (0, 25),
    "amulet of faith": (0, 1000), "amulet of reflection": (0, 220), "amulet of regeneration": (0, 200),
    "amulet of guardian spirit": (0, 100), "amulet of the acrobat": (0, 100),
}
# The rc lines `Style.kit` adds (selfplay.py): pick up a tower shield too, one at a time, as crawlrc.txt's
# `ladder_gear` does for the rest.
KIT_RC = """
{
add_autopickup_func(function(it, name)
  if it.class(true) ~= "armour" or it.is_useless then return nil end
  if not name:find("tower shield", 1, true) then return nil end
  for _, mine in ipairs(items.inventory()) do
    if mine.name():find("tower shield", 1, true) then return nil end
  end
  return true
end)
}
"""
JEWEL_GAIN = 50           # swap a worn piece only for one worth this much more


def jewel(item: dict) -> tuple[str, str, float] | None:
    """(slot "ring" or "amulet", kind, value) for a ring or amulet worth wearing, else None. Artefacts are left alone,
    as `_usable` leaves them for weapons and armour; so are pieces the game marks useless to this character."""
    name = item.get("name", "")
    if item.get("base_type") != JEWELLERY or (item.get("quantity", 1) or 0) <= 0 or item.get("useless") \
            or ARTEFACT.search(name):
        return None
    entry = _match(name, JEWEL_VALUES)
    if entry is None:
        return None
    kind = max((k for k in JEWEL_VALUES if k in name.lower()), key=len)
    per_plus, flat = entry
    value = per_plus * (item.get("plus") or 0) + flat
    return ("amulet" if kind.startswith("amulet") else "ring", kind, value) if value > 0 else None


def jewellery_choice(pieces: list[tuple[str, dict, bool]]) -> str | None:
    """The letter to press `P` on next, given the pack's jewellery as (letter, item, worn): a piece to put on into a
    free slot, or a worn one to take off because a piece worth JEWEL_GAIN more waits for its slot (`P` on a worn piece
    takes it off; with both ring slots full `P` on a third asks which to remove, as text, which this avoids). A worn
    piece of a kind already worn twice over counts for nothing, so a second ring of poison resistance is not put on.
    None when nothing should change."""
    for slot, slots in (("amulet", 1), ("ring", RING_SLOTS)):
        worn, spare = [], []
        for letter, item, on in pieces:
            j = jewel(item)
            if j and j[0] == slot:
                (worn if on else spare).append((j[2], j[1], letter))
        # a non-plus kind already worn adds nothing a second time
        kinds_on = {k for _, k, _ in worn if JEWEL_VALUES[k][0] == 0}
        spare = [s for s in spare if s[1] not in kinds_on]
        if not spare:
            continue
        best = max(spare)
        if len(worn) < slots:
            return best[2]
        low = min(worn)
        if best[0] >= low[0] + JEWEL_GAIN:
            return low[2]
    return None


def worn_from_menu(messages: list[dict]) -> list[tuple[str, str, bool]]:
    """(letter, text, worn) for each item in the last menu among `messages` (an item's line ends "(worn)" when it is
    on, "(weapon)" when wielded)."""
    items = []
    for m in messages:
        if m.get("msg") == "menu":
            items = m.get("items") or []
    out = []
    for it in items:
        keys = it.get("hotkeys") or []
        if not keys:
            continue
        text = re.sub(r"<[^>]*>", "", it.get("text", ""))
        out.append((chr(keys[0]), text, "(worn)" in text or "(weapon)" in text))
    return out


def enchant_target(reason: str, menu: list[tuple[str, str, bool]], worn: dict[str, str] | None = None) -> str | None:
    """The letter to answer an enchant armour (`enchant_item`), enchant weapon or brand weapon prompt with, from its
    menu (`worn_from_menu`), which lists only what the scroll can still improve: the weapon in hand for a weapon
    scroll; for armour, the body armour worn, else the shield, else any other piece worn. None: nothing fit."""
    on = [(letter, text) for letter, text, w in menu if w]
    if reason in ("enchant_weapon", "brand_weapon"):
        return next((letter for letter, text in on if "(weapon)" in text), None)
    if reason != "enchant_item":
        return None
    order = {"body": 0, "shield": 1}
    ranked = []
    for letter, text in on:
        entry = _match(text, KIT_ARMOURS)
        ranked.append((order.get(entry[0], 2) if entry else 3, letter))
    return min(ranked)[1] if ranked else None



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


def armour(item: dict, kit: bool = False) -> tuple[str, float] | None:
    """(kind, score) for a piece of armour the brain ranks, else None. `kit` (`Style.kit`) also ranks KIT_ARMOURS."""
    entry = _match(item.get("name", ""), KIT_ARMOURS if kit else ARMOURS) if _usable(item, ARMOUR) else None
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


def upgrades(state: GameState, worn: dict[str, str], kit: bool = False) -> dict[str, str | None]:
    """{"wield": letter or None, "wear": letter or None}: the best change of each sort, if any is better.
    `kit` (`Style.kit`) ranks the armour of KIT_ARMOURS too."""
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
        a = armour(item, kit)
        if not a or worn.get(a[0]) == str(slot) or (a[0] == "shield" and (two_handed or not current)):
            continue
        on = armour(inv.get(worn.get(a[0], ""), {}), kit)
        better = a[1] - (on[1] if on else 0.0)
        if better >= MIN_GAIN and better > gain:
            gain, out["wear"] = better, chr(item.get("letter", 0))
    return out


def kind_of(state: GameState, letter: str, kit: bool = False) -> tuple[str, str] | None:
    """(kind, inventory slot) of the armour with this letter."""
    for slot, item in (state.player.get("inv") or {}).items():
        if chr(item.get("letter", 0)) == letter and (a := armour(item, kit)):
            return a[0], str(slot)
    return None
