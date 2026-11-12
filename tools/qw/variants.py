"""Settings of qw to search by whole games (tools/qw/search.py).

Each variant is a few lines of Lua run after qw.lua (run.py --lua). It changes one of qw's
constants or wraps one of its global functions, so variants can be joined: "a+b" is the Lua
of a followed by the Lua of b. qw's `qw` and `const` tables are local to qw.lua; ladder.lua
hands them out as ladder_qw and ladder_const, and lua() starts every block with them.

qw's defaults, for reference (Minotaur Berserker):
- skills: one skill at a time, the best of value / cost. Weapon 1.5 (0.3 at minimum
  delay), Fighting 0.75, Armour and Dodging from the AC and EV they would add.
- threat cutoffs 5 / 10 / 20 (moderate / high / extreme), lowered below XL 10.
- berserk at high threat, or under 50% HP with an enemy within 2.
- at extreme threat a melee character flees or teleports (will_fight_extreme_threat).
- flees up the stairs when under 90% HP and not buffed; rests to full.
- heal wounds under 25% HP; Brothers in Arms at threat 15 with every buff counted.
- Lair as soon as it is found (Trog), Orc after D:15, always a shield, heavy armour.
"""

from __future__ import annotations

# Wraps skill_value(): `body` sees `v` (qw's value, may be nil) and `sk`.
_SKILL = """do
    local old = skill_value
    function skill_value(sk)
        local v = old(sk)
        %s
        return v
    end
end"""

# Maps one percentage passed to reason_to_rest(): 90 is the flee test, 99.9 the rest test.
_REST = """do
    local old = reason_to_rest
    function reason_to_rest(percentage)
        if percentage == %s then
            percentage = %s
        end
        return old(percentage)
    end
end"""

_BROTHERS = """function want_to_brothers_in_arms()
    if not qw.danger_in_los or dangerous_to_attack() or you.teleporting()
            or check_brothers_in_arms(4) then
        return false
    end
    return assess_enemies(const.duration.available).threat >= %s
end"""

_HEAL = """do
    local old = want_to_heal_wounds
    function want_to_heal_wounds()
        return old() or (qw.danger_in_los and hp_is_low(%s))
    end
end"""

_BERSERK_HP = """do
    local old = want_to_berserk
    function want_to_berserk()
        if old() then
            return true
        end
        if not qw.danger_in_los or dangerous_to_melee() or you.berserk() then
            return false
        end
        return hp_is_low(%s) and check_berserkable_enemies()
    end
end"""

VARIANTS: dict[str, tuple[str, str]] = {
    # --- skills -----------------------------------------------------------------------
    "fight_hi": ("Fighting worth 1.5, not 0.75",
                 _SKILL % 'if sk == "Fighting" then v = 1.5 end'),
    "fight_lo": ("Fighting worth 0.4",
                 _SKILL % 'if sk == "Fighting" then v = 0.4 end'),
    "weapon_hi": ("weapon skill worth double",
                  _SKILL % "if v and sk == weapon_skill() then v = v * 2 end"),
    "defence_hi": ("Armour, Dodging and Shields worth 1.5 times as much",
                   "const.ev_value = 1.2\nconst.ac_value = 1.5\nconst.sh_value = 1.125"),
    "defence_lo": ("Armour, Dodging and Shields worth half",
                   "const.ev_value = 0.4\nconst.ac_value = 0.5\nconst.sh_value = 0.375"),
    "dex": ("level-up stat points into Dexterity, not Strength",
            'function choose_stat_gain()\n    return "d"\nend'),
    # --- berserk and threat cutoffs ---------------------------------------------------
    "zerk_early": ("high-threat cutoff 7, not 10: berserk sooner", "const.high_threat = 7"),
    "zerk_late": ("high-threat cutoff 14: berserk later", "const.high_threat = 14"),
    "zerk_hp70": ("berserk under 70% HP with an enemy adjacent, not 50%", _BERSERK_HP % 70),
    "extreme_lo": ("extreme-threat cutoff 14, not 20: flee or teleport sooner",
                   "const.extreme_threat = 14"),
    "extreme_hi": ("extreme-threat cutoff 30: stand more often", "const.extreme_threat = 30"),
    "stand": ("never flee or teleport for extreme threat alone",
              "function will_fight_extreme_threat()\n    return true\nend"),
    # --- Trog's abilities, potions ----------------------------------------------------
    "hand": ("Trog's Hand at moderate threat, not only against qw's list of casters",
             """do
    local old = want_to_trogs_hand
    function want_to_trogs_hand()
        if old() then
            return true
        end
        if you.regenerating() or you.teleporting() then
            return false
        end
        return qw.danger_in_los and not dangerous_to_attack()
            and have_moderate_threat(const.duration.available)
    end
end"""),
    "bia10": ("Brothers in Arms at threat 10, not 15", _BROTHERS % 10),
    "bia7": ("Brothers in Arms at threat 7", _BROTHERS % 7),
    "heal40": ("heal wounds under 40% HP, not 25%", _HEAL % 40),
    "heal55": ("heal wounds under 55% HP", _HEAL % 55),
    # --- fleeing and resting ----------------------------------------------------------
    "flee60": ("flee upstairs under 60% HP, not 90%", _REST % (90, 60)),
    "flee30": ("flee upstairs under 30% HP", _REST % (90, 30)),
    "rest80": ("rest to 80% HP, not to full", _REST % (99.9, 80)),
    # --- route and gear ---------------------------------------------------------------
    "lair_late": ("Lair only after D:1-11 is explored",
                  "function ready_for_lair()\n    return false\nend"),
    "lair_xl11": ("Lair early only from XL 11",
                  """do
    local old = ready_for_lair
    function ready_for_lair()
        return you.xl() >= 11 and old()
    end
end"""),
    "orc_early": ("Orc before D:12 onward, not after D:15", "LATE_ORC = false"),
    "two_hander": ("two-handed weapons allowed (no shield at all cost)",
                   "SHIELD_CRAZY = false"),
    "dodgy": ('armour plan "dodgy" (lighter armour, Dexterity), not "heavy"',
              'function armour_plan()\n    return "dodgy"\nend'),
}


def lua(spec: str) -> str:
    """The Lua for "name" or "name+name+...". "base" is qw unchanged."""
    if spec == "base":
        return "-- qw unchanged\n"
    parts = ["local qw, const = ladder_qw, ladder_const\n"]
    for name in spec.split("+"):
        note, code = VARIANTS[name]
        parts.append(f"-- {name}: {note}\n{code}\n")
    return "\n".join(parts)
