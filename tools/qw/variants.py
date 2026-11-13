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
    # --- pacing, from human winners (docs/human-mibe-reference.md) ----------------------
    # Each logs a QWDBG line on stderr the first time it changes qw's choice, as evidence.
    "lair_xl12": ("Lair only from XL 12: until then finish D:1-11, then D:12-15 one level at a time",
                  """do
    local old_ready = ready_for_lair
    local held_xl
    function ready_for_lair()
        if not old_ready() then
            return false
        end
        if you.xl() < 12 then
            if held_xl ~= you.xl() then
                held_xl = you.xl()
                crawl.stderr("QWDBG\\t" .. you.turns() .. "\\tpacing lair_xl12: Lair found, held at XL "
                    .. you.xl())
            end
            return false
        end
        return true
    end

    local old_next = goal_normal_next
    local said
    function goal_normal_next(final)
        local goal = old_next(final)
        if goal == "Lair" and you.xl() < 12 then
            for d = 12, branch_depth("D") do
                local level = "D:" .. d
                if not explored_level_range(level) then
                    if said ~= level then
                        said = level
                        crawl.stderr("QWDBG\\t" .. you.turns() .. "\\tpacing lair_xl12: XL "
                            .. you.xl() .. ", " .. level .. " before the Lair")
                    end
                    return level
                end
            end
        end
        return goal
    end
end"""),
    "vaults_late": ("Vaults:1-4 only after the second Lair rune, unless XL 19",
                    """do
    local old_next = goal_normal_next
    local said
    function goal_normal_next(final)
        local goal = old_next(final)
        if goal and you.xl() < 19 and goal == make_level_range("Vaults", 1, -1) then
            local second = next_branch(lair_branch_order(), 1)
            local rune_end = second and branch_end(second)
            if rune_end and not explored_level_range(rune_end) then
                if said ~= rune_end then
                    said = rune_end
                    crawl.stderr("QWDBG\\t" .. you.turns() .. "\\tpacing vaults_late: XL " .. you.xl()
                        .. ", " .. rune_end .. " before " .. goal)
                end
                return rune_end
            end
        end
        return goal
    end
end"""),
    "sigmund_leave": ("below XL 10, when Sigmund was seen on this level, is not in view (invisible) "
                      "and HP is under 90%, walk to the up stairs and take them instead of flailing "
                      "(at most 10 times a level)",
                      """do
    local seen_turn, seen_level
    local retreats = {}
    local old_update = update_invis_monsters
    function update_invis_monsters(closest_invis_pos)
        if you.xl() < 10 then
            for _, enemy in ipairs(qw.enemy_list) do
                if enemy:name() == "Sigmund" then
                    seen_turn = you.turns()
                    seen_level = you.where()
                end
            end
        end
        return old_update(closest_invis_pos)
    end

    -- Forget him once he is dead ("You kill Sigmund!", "Sigmund dies!").
    local old_message = c_message
    function c_message(text, channel)
        if seen_turn and text:find("Sigmund") and (text:find("kill") or text:find("dies")) then
            seen_turn, seen_level = nil, nil
        end
        return old_message(text, channel)
    end

    local function sigmund_unseen()
        if you.xl() >= 10 or not seen_turn or seen_level ~= you.where()
                or (retreats[seen_level] or 0) >= 10 then
            return false
        end
        for _, enemy in ipairs(qw.enemy_list) do
            if enemy:name() == "Sigmund" then
                return false
            end
        end
        -- Only once hurt: at full HP qw's own plans run, so arriving back at full HP
        -- does not bounce straight up the stairs again.
        local hp, mhp = you.hp()
        return hp < 0.9 * mhp
    end

    local old_flail = plan_flail_at_invis
    function plan_flail_at_invis()
        if sigmund_unseen() and qw.can_flee_upstairs and not unable_to_use_stairs() then
            local hp, mhp = you.hp()
            if feature_is_upstairs(view.feature_at(0, 0)) then
                retreats[seen_level] = (retreats[seen_level] or 0) + 1
                crawl.stderr("QWDBG\\t" .. you.turns() .. "\\tpacing sigmund_leave: up from " .. you.where()
                    .. " at XL " .. you.xl() .. " HP " .. hp .. "/" .. mhp)
                go_upstairs(you.status("spiked"))
                return true
            end
            local result = best_move_towards_positions(qw.flee_positions, true)
            if result and move_to(result.move) then
                return true
            end
        end
        return old_flail()
    end
end"""),
    "snake_last": ("Lair branch order Spider, Swamp, Shoals, Snake: Snake never first, Spider always first",
                   """do
    local old_order = lair_branch_order
    function lair_branch_order()
        if c_persist.lair_branch_order then
            return c_persist.lair_branch_order
        end
        -- The roll qw's "random" preference makes, so the game's dice stay in step.
        crawl.random2(2)
        c_persist.lair_branch_order = { "Spider", "Swamp", "Shoals", "Snake" }
        crawl.stderr("QWDBG\\t" .. you.turns() .. "\\tpacing snake_last: order "
            .. table.concat(c_persist.lair_branch_order, ","))
        return c_persist.lair_branch_order
    end
end"""),
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


def on_top_of(base: str, spec: str) -> str:
    """A settings file's Lua (e.g. runs/qw/combo1-lua/MiBe_mace.lua) followed by the variants in spec,
    so a variant runs against frozen settings that are not in VARIANTS verbatim."""
    parts = [base.rstrip("\n") + "\n"]
    for name in spec.split("+"):
        note, code = VARIANTS[name]
        parts.append(f"-- {name}: {note}\n{code}\n")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> None:
    import argparse
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Write run.py --lua files: a base settings file plus variants.")
    ap.add_argument("--base", type=Path, required=True, help="settings Lua to start from")
    ap.add_argument("--out", type=Path, required=True, help="directory for <spec>.lua")
    ap.add_argument("specs", nargs="+", help='variant names, "a+b" joins')
    a = ap.parse_args(argv)
    base = a.base.read_text(encoding="utf-8")
    if "local qw, const = ladder_qw, ladder_const" not in base:
        base = "local qw, const = ladder_qw, ladder_const\n" + base
    a.out.mkdir(parents=True, exist_ok=True)
    for spec in a.specs:
        path = a.out / f"{spec.replace('+', '_')}.lua"
        path.write_text(on_top_of(base, spec), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
