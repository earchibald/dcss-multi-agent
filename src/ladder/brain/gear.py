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

# --- `Style.throw` only -------------------------------------------------------------------------------------------
MISSILES = 1              # OBJ_MISSILES
# What qw throws (`want_missile`, runs/qw/build-zk/qw.lua 5503-5510), best first by the game's damage (item-prop.cc).
THROWN = ("javelin", "boomerang", "large rock")
THROW_KEY = chr(9351)     # the rc's ladder_throw macro (THROW_RC)
# The rc lines `Style.throw` adds (selfplay.py):
# - pick up javelins, boomerangs and large rocks the game doesn't mark useless, as qw's autopickup does (explore's
#   greedy pickup then fetches the thrown ones back after a fight);
# - `ladder_throw`, bound to THROW_KEY: throw the quivered missile at the hostile in view whose shot is clear, as qw's
#   `plan_throw` does (`get_ranged_attack_target`, `assess_ranged_position`, `throw_missile`, qw.lua 490-536, 270-404,
#   11166-11201): the game's own beam path (`spells.path`) must reach the target before any other monster; a
#   threat-3 ("extremely dangerous") hostile first, else the nearest; never one adjacent (that is for the mace). Aimed
#   at the target (`do_targeted_command`'s aim_at_target), so a javelin stops there. With nothing quivered, or no
#   clear shot, it does nothing and no time passes.
THROW_RC = """
{
add_autopickup_func(function(it, name)
  if it.class(true) ~= "missile" or it.is_useless then return nil end
  local st = it.subtype()
  if st == "javelin" or st == "boomerang" or st == "large rock" then return true end
  return nil
end)

function ladder_clear_shot(x, y)
  for _, c in ipairs(spells.path("Quicksilver Bolt", x, y, 0, 0, false)) do
    if c[1] == x and c[2] == y then return true end
    if monster.get_monster_at(c[1], c[2]) then return false end
  end
  return false
end

function ladder_throw()
  local q = items.fired_item()
  if not q or q.class(true) ~= "missile" then return end
  local bx, by, bkey
  for x = -7, 7 do
    for y = -7, 7 do
      local d = math.max(math.abs(x), math.abs(y))
      local m = d > 1 and monster.get_monster_at(x, y)
      if m and m:attitude() == 0 and not m:is_firewood() and you.see_cell_solid_see(x, y) then
        local key = (m:threat() >= 3 and 0 or 100) + d
        if (not bkey or key < bkey) and ladder_clear_shot(x, y) then
          bx, by, bkey = x, y, key
        end
      end
    end
  end
  if bkey then crawl.do_targeted_command("CMD_FIRE", bx, by, true) end
end
}
macros += M \\{9351} ===ladder_throw
"""


# --- `Style.kit` 2 only: nothing below changes what is ranked, worn or bought at kit 0 or 1 ---------------------------
# What the game's inventory names really look like (0.34, seen in the protocol): a weapon's brand is terse and in
# brackets ("+0 flail (flame)"), an armour's ego is a property list in braces ("+2 chain mail {rF+}"), and only an
# artefact carries a quoted or "of the" name; the item flags say which is an artefact. The kit 0/1 rules read a brace as
# an artefact (so no ego armour was ever worn: 59 pieces picked up in v6h/A-kit's 200 games, none put on) and a brand
# as " of " (so the brand bonus, the bad-brand check and brand weapon's "unbranded only" never applied).
ARTEFACT_FLAGS = 0x3000   # ISFLAG_RANDART | ISFLAG_UNRANDART (item-status-flag-type.h)
KIT2_ARMOURS = {**KIT_ARMOURS, "troll leather armour": ("body", 3), "steam dragon scales": ("body", 5),
                "acid dragon scales": ("body", 6), "swamp dragon scales": ("body", 7),
                "fire dragon scales": ("body", 8), "ice dragon scales": ("body", 9),
                "quicksilver dragon scales": ("body", 9), "pearl dragon scales": ("body", 10),
                "storm dragon scales": ("body", 10), "shadow dragon scales": ("body", 11),
                "golden dragon scales": ("body", 12), "barding": ("boots", 1)}   # base AC, item-prop.cc
BAD_BRANDS2 = ("distort", "chaos", "distortion")
GOOD_BRAND = 2            # what a brand adds to a weapon's rank (as `weapon` meant to), "pain" and the bad ones aside
# qw's own values (qw.lua: linear_property_value 3033-3058, per point; absolute_property_value 2764-2878, by level,
# at its first level for this character) for the properties an artefact or ego lists in braces. A plus point of an
# armour is worth 50 on this scale (qw's `ac_value`), so a property's worth in AC is its value / PROP_PER_AC.
PROP_LINEAR = {"Slay": 50, "AC": 50, "EV": 50, "SH": 40, "Str": 35, "Dex": 15, "Regen": 200}
PROP_LEVELS = {"rF": (125, 200, 250), "rC": (125, 200, 250), "Will": (100, 200, 300), "rN": (25, 50, 75)}
PROP_NEG = {"rF": (-150, -225, -275), "rC": (-150, -225, -275)}
PROP_FLAT = {"rElec": 75, "rPois": 225, "rCorr": 50, "SInv": 200, "Fly": 200, "Faith": 1000, "Spirit": 100,
             "Acrobat": 100, "Reflect": 20, "Repulsion": 200, "RMsl": 200, "Rampage": 20,
             "Harm": -500, "Ponderous": -300, "*Tele": -300, "*Rage": -300, "*Slow": -100, "*Corrode": -100,
             "-Tele": -10000}
PROP_PER_AC = 50
# A shop's menu gives an armour's ego by its long name ("+2 robe of willpower"); the pack gives its terse one in braces.
VERBOSE_EGOS = {"fire resistance": "rF+", "cold resistance": "rC+", "poison resistance": "rPois", "see invisible": "SInv",
                "willpower": "Will+", "protection": "AC+3", "resistance": "rC+ rF+", "positive energy": "rN+",
                "reflection": "Reflect", "flying": "Fly", "strength": "Str+3", "dexterity": "Dex+3",
                "ponderousness": "Ponderous", "harm": "Harm", "corrosion resistance": "rCorr", "rampaging": "Rampage"}
# a piece with any of these is never worn, wielded or bought, whatever else it has (a negative resistance only counts
# against the rest, as qw sums it)
PROP_BAD = ("Harm", "Ponderous", "*Tele", "*Rage", "*Slow", "*Corrode", "-Tele", "Fragile")
PROP = re.compile(r"^([*+-]?[A-Za-z]+?)([+-]\d+|\++|-+)?$")


def props(name: str) -> tuple[float, bool]:
    """(qw's value of the properties in the name's braces, whether one of them is bad). A weapon's brand, which an
    artefact lists first ("{flame, rF+ Str+3}"), is left to `brand_of`."""
    m = re.search(r"\{([^}]*)\}", name)
    if not m:
        return 0.0, False
    total, bad = 0.0, False
    for tok in m.group(1).replace(",", " ").split():
        p = PROP.match(tok)
        if not p:
            continue
        key, amount = p.group(1), p.group(2) or ""
        level = (int(amount) if amount[1:].isdigit() else (len(amount) if amount.startswith("+") else -len(amount))) \
            if amount else 1
        if key in PROP_LINEAR:
            v = PROP_LINEAR[key] * level
        elif key in PROP_LEVELS:
            v = PROP_LEVELS[key][min(level, 3) - 1] if level > 0 else \
                PROP_NEG.get(key, (-PROP_LEVELS[key][0],) * 3)[min(-level, 3) - 1]
        else:
            v = PROP_FLAT.get(key, 0)
        total += v
        bad = bad or key in PROP_BAD
    return total, bad


def is_artefact(item: dict) -> bool:
    """By the item flags; a name with a quoted or "the ... of" title where there are none (a shop's or acquirement's
    menu line)."""
    if item.get("flags") is not None:
        return bool(item["flags"] & ARTEFACT_FLAGS)
    name = item.get("name", "")
    return '"' in name or name.startswith("the ") or " of the " in name


def brand_of(name: str) -> str | None:
    """The weapon's brand, terse: "(flame)" in the pack; "{flame, ...}" on an artefact; "of flaming" in a menu line."""
    if (m := re.search(r"\((\w+)\)\s*$", name)):
        return m.group(1)
    if (m := re.search(r"\{(\w+),", name)) or (m := re.search(r"\{(\w+)\}", name)):
        return m.group(1) if m.group(1).islower() else None
    if (m := re.search(r" of (flaming|freezing|holy wrath|electrocution|venom|protection|draining|speed|heavy|"
                       r"vampirism|pain|antimagic|distortion|chaos|penetration|reaping|spectralising|rebuke|valour|"
                       r"entangling|sundering|concussion|devious)\b", name)):
        return m.group(1)
    return None


def _usable2(item: dict, base_type: int) -> bool:
    return item.get("base_type") == base_type and (item.get("quantity", 1) or 0) > 0 and not item.get("useless") \
        and not props(item.get("name", ""))[1]


def weapon2(item: dict) -> tuple[float, int] | None:
    """`weapon` with the names read right (kit 2): the brand from brackets, bad brands left out, artefacts ranked by
    their properties too unless one is bad."""
    if not _usable2(item, WEAPON):
        return None
    name = item.get("name", "")
    entry = _match(name, WEAPONS)
    brand = brand_of(name)
    if entry is None or (brand and brand in BAD_BRANDS2):
        return None
    damage, delay, hands = entry
    bonus = GOOD_BRAND if brand and brand != "pain" else 0
    return damage + (item.get("plus") if item.get("plus") is not None else _plus(name)) - 0.5 * (delay - 14) + bonus + \
        props(name)[0] / PROP_PER_AC, hands


def armour2(item: dict) -> tuple[str, float] | None:
    """`armour` with the names read right (kit 2): an ego's or artefact's properties in braces add their worth (qw's
    values) instead of ruling the piece out; any bad property (Harm, Ponderous, *Rage...) still does. The real base AC of
    every dragon armour and troll leather armour."""
    name = item.get("name", "")
    if (m := re.search(r" of ([a-z ]+)$", name)) and m.group(1) in VERBOSE_EGOS and "{" not in name:
        name = f"{name[:m.start()]} {{{VERBOSE_EGOS[m.group(1)]}}}"     # a shop's long name: "robe of willpower"
    if not _usable2({**item, "name": name}, ARMOUR):
        return None
    entry = _match(name, KIT2_ARMOURS)
    if entry is None:
        return None
    kind, score = entry
    plus = item.get("plus") if item.get("plus") is not None else _plus(name)
    return kind, score + plus + props(name)[0] / PROP_PER_AC


def _plus(name: str) -> int:
    m = re.search(r"(?:^|\s)([+-]\d+) ", name)
    return int(m.group(1)) if m else 0


def jewel2(item: dict) -> tuple[str, str, float] | None:
    """`jewel` for kit 2: an artefact ring or amulet is worth what its properties are worth (its listed properties
    include the base ring's own: "ring \"Basageg\" {rElec rF- rC+ AC+4 Int+2}"), unless one is bad; its kind is its own
    name, so it never counts as a repeat."""
    name = item.get("name", "")
    if item.get("base_type") != JEWELLERY or (item.get("quantity", 1) or 0) <= 0 or item.get("useless"):
        return None
    if is_artefact(item) or "{" in name:
        value, bad = props(name)
        slot = "amulet" if "amulet" in name.lower() else "ring"
        return (slot, name, value) if value > 0 and not bad else None
    return jewel(item)


def worth(kind: str, item: dict) -> float | None:
    """The kit 2 rank of a weapon, armour or jewellery dict in one unit (an armour plus point): `weapon2`'s and
    `armour2`'s scores as they are, a ring's or amulet's qw value / PROP_PER_AC."""
    if kind == "weapon":
        w = weapon2(item)
        return w[0] if w else None
    if kind == "armour":
        a = armour2(item)
        return a[1] if a else None
    j = jewel2(item)
    return j[2] / PROP_PER_AC if j else None


# The rc lines `Style.kit` 2's "gear" part adds (selfplay.py): crawlrc.txt's `ladder_gear` takes one piece of each kind,
# so a +2 cloak or a chain mail {rF+} was left lying when one of that kind was already in the pack. Also take a piece of
# a kind the ranking knows that is an artefact, has an ego, or has a higher plus than every one of its kind carried.
KIT2_RC = """
{
local ladder_gear2 = { "great mace", "mace", "flail", "morningstar", "eveningstar", "demon whip", "sacred scourge",
  "ring mail", "scale mail", "chain mail", "plate armour", "dragon scales", "troll leather",
  "cloak", "scarf", "gloves", "boots", "hat", "helmet", "buckler", "kite shield", "tower shield" }
add_autopickup_func(function(it, name)
  local class = it.class(true)
  if class ~= "armour" and class ~= "weapon" then return nil end
  if it.is_useless then return nil end
  local ego = it.ego and it.ego() or nil
  local special = it.artefact or (ego ~= nil and ego ~= "")
  local plus = it.plus or 0
  for _, g in ipairs(ladder_gear2) do
    if name:find(g, 1, true) then
      if not special and plus <= 0 then return nil end
      for _, mine in ipairs(items.inventory()) do
        if mine.name():find(g, 1, true) and not special and (mine.plus or 0) >= plus then return nil end
      end
      return true
    end
  end
  return nil
end)
}
"""
# What a skill manual is worth when acquirement offers one (in armour plus points): the skills this character fights with.
MANUALS = {"Maces & Flails": 2, "Fighting": 2, "Armour": 1.5, "Shields": 1}
# What a consumable bought in a shop is worth (armour plus points), and how many to hold at most. Only what the bot uses:
# its healing potions, teleportation, and the kit's scrolls (`policy.kit_scroll`).
CONSUMABLES = {"potion of heal wounds": (5, 5), "potion of curing": (3, 6), "scroll of teleportation": (4, 4),
               "scroll of acquirement": (6, 9), "scroll of enchant armour": (2, 9),
               "scroll of enchant weapon": (1.5, 9), "scroll of brand weapon": (1.5, 1)}
SHOP_LINE = re.compile(r"^\s*([a-zA-Z]) [-+]\s+(\d+) gold\s+(.*?)\s*(?:\(unknown\))?$")
ACQ_LINE = re.compile(r"^\s*([a-zA-Z]) [-+] (.*)$")


def _held(state: GameState, kind: str) -> int:
    """How many of a consumable ("potion of curing") the pack holds."""
    noun, _, what = kind.partition(" of ")
    n = 0
    for item in (state.player.get("inv") or {}).values():
        name = item.get("name", "")
        if (item.get("quantity", 1) or 0) > 0 and re.search(rf"\b{noun}s? of {re.escape(what)}$", name):
            n += item.get("quantity", 1) or 1
    return n


def offer_gain(name: str, state: GameState, worn: dict[str, str], jewels_on: set[str]) -> float:
    """What a weapon, armour, ring, amulet or manual offered by name (a shop's or acquirement's menu line) would add over
    what is in use, in armour plus points, by the kit 2 ranks; 0 when nothing."""
    inv = state.player.get("inv") or {}
    wielded = inv.get(str(state.player.get("weapon_index", -1)))
    current = weapon2(wielded) if wielded else None
    low = name.lower()
    if (m := re.search(r"manual of (.*)$", name)):
        skill = m.group(1).strip()
        return MANUALS.get(skill, 0) if skill != "Shields" or "shield" in worn else 0
    if re.search(r"\b(ring|amulet)\b", low) and "ring mail" not in low:
        j = jewel2({"name": name, "base_type": JEWELLERY, "quantity": 1})
        if not j:
            return 0
        pieces = [(chr(it.get("letter", 0)), it, chr(it.get("letter", 0)) in jewels_on)
                  for it in inv.values() if it.get("base_type") == JEWELLERY]
        on = sorted(v[2] for _, it, w in pieces if w and (v := jewel2(it)) and v[0] == j[0])
        free = (1 if j[0] == "amulet" else RING_SLOTS) - len(on)
        if free > 0:
            return j[2] / PROP_PER_AC
        return max(0.0, j[2] - on[0]) / PROP_PER_AC if j[2] >= on[0] + JEWEL_GAIN else 0
    item = {"name": name, "quantity": 1}
    if _match(name, WEAPONS):
        w = weapon2({**item, "base_type": WEAPON})
        if not w or not current or (w[1] == 2 and "shield" in worn):
            return 0
        return max(0.0, w[0] - current[0]) if w[0] - current[0] >= MIN_GAIN else 0
    if _match(name, KIT2_ARMOURS):
        a = armour2({**item, "base_type": ARMOUR})
        if not a or (a[0] == "shield" and (not current or current[1] == 2)):
            return 0
        on = armour2(inv.get(worn.get(a[0], ""), {}))
        gain = a[1] - (on[1] if on else 0.0)
        return gain if gain >= MIN_GAIN else 0
    return 0


def acquire_choice(menu: list[tuple[str, str, bool]], state: GameState, worn: dict[str, str], jewels_on: set[str],
                   gold_worth: float) -> str | None:
    """The letter to answer the acquirement menu ("Choose an item to acquire.") with: the offer that adds most
    (`offer_gain`), else the gold (worth `gold_worth`), which is always offered. None if no line parses."""
    best, gold = None, None
    for letter, text, _ in menu:
        m = ACQ_LINE.match(text)
        if not m:
            continue
        name = re.sub(r"^(an?|the) ", "", m.group(2).strip())
        if re.match(r"\d+ gold pieces", name):
            gold = letter
            gain = gold_worth
        else:
            gain = offer_gain(name, state, worn, jewels_on)
        if gain > 0 and (best is None or gain > best[0]):
            best = (gain, letter)
    return best[1] if best else gold


def shop_choice(menu: list[tuple[str, str, bool]], state: GameState, worn: dict[str, str],
                jewels_on: set[str]) -> list[str]:
    """The letters to mark in a shop's menu (" a -   82 gold   a scroll of enchant armour (unknown)"): the most
    valuable first (CONSUMABLES up to their caps, then `offer_gain`), each while the gold left covers its price."""
    gold = state.player.get("gold", 0) or 0
    inv = state.player.get("inv") or {}
    wielded = inv.get(str(state.player.get("weapon_index", -1)))
    ranked = bool(wielded and weapon2(wielded))
    branded = bool(wielded and brand_of(wielded.get("name", "")))
    wanted = []
    for letter, text, _ in menu:
        m = SHOP_LINE.match(text)
        if not m:
            continue
        price, name = int(m.group(2)), re.sub(r"^(an?|the) ", "", m.group(3).strip())
        kind = next((k for k in CONSUMABLES if re.fullmatch(rf"(\d+ )?{k.replace(' of ', 's? of ')}", name)), None)
        if kind:
            value, cap = CONSUMABLES[kind]
            if ("weapon" in kind and not ranked) or (kind == "scroll of brand weapon" and branded) or \
                    _held(state, kind) >= cap:
                continue
        else:
            value = offer_gain(name, state, worn, jewels_on)
        if value > 0:
            wanted.append((-value, price, letter, kind))
    out, seen = [], set()
    for _, price, letter, kind in sorted(wanted):
        if price <= gold and (kind is None or kind not in seen):
            out.append(letter)
            gold -= price
            if kind:
                seen.add(kind)               # one of each consumable per visit: the cap is checked on the pack
    return out


def missiles(state: GameState) -> dict[str, int]:
    """{inventory slot: how many} of the missiles `Style.throw` throws (THROWN), not marked useless."""
    out = {}
    for slot, item in (state.player.get("inv") or {}).items():
        name = item.get("name", "")
        if item.get("base_type") == MISSILES and not item.get("useless") and (item.get("quantity", 1) or 0) > 0 \
                and any(t in name for t in THROWN):
            out[str(slot)] = item.get("quantity", 1) or 1
    return out


def quiver_line(menu: list[tuple[str, str, bool]]) -> str | None:
    """The letter of the best missile to quiver in the `Q` menu ("Quiver which action?": item lines read
    "a - Throw: 6 javelins (quivered)"), by THROWN's order; None if none is listed."""
    for kind in THROWN:
        for letter, text, _ in menu:
            if f"{letter} - Throw:" in text and kind in text:
                return letter
    return None


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


def jewellery_choice(pieces: list[tuple[str, dict, bool]], kit: float = 1) -> str | None:
    """The letter to press `P` on next, given the pack's jewellery as (letter, item, worn): a piece to put on into a
    free slot, or a worn one to take off because a piece worth JEWEL_GAIN more waits for its slot (`P` on a worn piece
    takes it off; with both ring slots full `P` on a third asks which to remove, as text, which this avoids). A worn
    piece of a kind already worn twice over counts for nothing, so a second ring of poison resistance is not put on.
    None when nothing should change. At kit 2, by `jewel2` (artefacts by their properties)."""
    value = jewel2 if kit >= 2 else jewel
    for slot, slots in (("amulet", 1), ("ring", RING_SLOTS)):
        worn, spare = [], []
        for letter, item, on in pieces:
            j = value(item)
            if j and j[0] == slot:
                (worn if on else spare).append((j[2], j[1], letter))
        # a non-plus kind already worn adds nothing a second time
        kinds_on = {k for _, k, _ in worn if JEWEL_VALUES.get(k, (1, 0))[0] == 0}
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


def enchant_target(reason: str, menu: list[tuple[str, str, bool]], worn: dict[str, str] | None = None,
                   kit: float = 1) -> str | None:
    """The letter to answer an enchant armour (`enchant_item`), enchant weapon or brand weapon prompt with, from its
    menu (`worn_from_menu`), which lists only what the scroll can still improve: the weapon in hand for a weapon
    scroll; for armour, the body armour worn, else the shield, else any other piece worn. None: nothing fit.
    At kit 2, armour in qw's order (`get_enchantable_armour`, qw.lua 13631-13680): a worn cloak, gloves, boots or
    helmet first (they are rarely changed, while the body armour is swapped for a heavier one and its plus lost), then
    the body armour if it is plate or dragon scales, then the shield, then any body armour."""
    on = [(letter, text) for letter, text, w in menu if w]
    if reason in ("enchant_weapon", "brand_weapon"):
        return next((letter for letter, text in on if "(weapon)" in text), None)
    if reason != "enchant_item":
        return None
    if kit >= 2:
        ranked = []
        for letter, text in on:
            entry = _match(text, KIT2_ARMOURS)
            kind = entry[0] if entry else ""
            heavy = kind == "body" and ("plate armour" in text or "dragon scales" in text)
            ranked.append((0 if kind in ("cloak", "gloves", "boots", "head") else 1 if heavy else
                           2 if kind == "shield" else 3, letter))
        return min(ranked)[1] if ranked else None
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


def upgrades(state: GameState, worn: dict[str, str], kit: float = False) -> dict[str, str | None]:
    """{"wield": letter or None, "wear": letter or None}: the best change of each sort, if any is better.
    `kit` (`Style.kit`) ranks the armour of KIT_ARMOURS too; at 2 and up, by `weapon2` and `armour2`."""
    rank_w, rank_a = (weapon2, armour2) if kit >= 2 else (weapon, lambda it: armour(it, bool(kit)))
    inv = state.player.get("inv") or {}
    wielded = inv.get(str(state.player.get("weapon_index", -1)))
    current = rank_w(wielded) if wielded else None
    if current:
        # corrosion shows as a minus on the weapon in hand only; without this the brain swaps to the
        # spare, which then shows the minus instead, and back again every turn
        corr = next((int(m.group(1)) for s in state.statuses if (m := re.match(r"Corr \(-(\d+)\)", s))), 0)
        current = (current[0] + corr, current[1])
    out: dict[str, str | None] = {"wield": None, "wear": None}
    if current:                                   # only ever trade one ranked weapon for another
        best = current[0] + MIN_GAIN
        for item in inv.values():
            w = rank_w(item)
            if w and item is not wielded and w[0] >= best and not (w[1] == 2 and "shield" in worn):
                best, out["wield"] = w[0], chr(item.get("letter", 0))
    two_handed = bool(current and current[1] == 2)
    gain = 0.0
    for slot, item in inv.items():
        a = rank_a(item)
        if not a or worn.get(a[0]) == str(slot) or (a[0] == "shield" and (two_handed or not current)):
            continue
        on = rank_a(inv.get(worn.get(a[0], ""), {}))
        better = a[1] - (on[1] if on else 0.0)
        if better >= MIN_GAIN and better > gain:
            gain, out["wear"] = better, chr(item.get("letter", 0))
    return out


def kind_of(state: GameState, letter: str, kit: float = False) -> tuple[str, str] | None:
    """(kind, inventory slot) of the armour with this letter."""
    for slot, item in (state.player.get("inv") or {}).items():
        if chr(item.get("letter", 0)) == letter and (a := (armour2(item) if kit >= 2 else armour(item, bool(kit)))):
            return a[0], str(slot)
    return None
