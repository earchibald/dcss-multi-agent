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
    # --- stuck loops ------------------------------------------------------------------
    # qw counts itself stuck only while no plan acts (qw.stuck_turns, plan_random_step), so a
    # plan that acts every turn without getting anywhere runs until Zot's clock has drained
    # max HP to 1 and qw quits ("quitting", ~40,000 turns). Three such loops; join all three
    # with "dest_giveup+travel_walk+bounce_giveup". Each logs QWDBG lines when it acts.
    "dest_giveup": ("drop a move destination still unreached after 400 moves on this level (and "
                    "don't take it up again here): seed 100628 was teleported into a pocket of D:7 "
                    "and walked a loop towards its old 'safety' square for 36,000 turns",
                    """do
    local LIMIT = 400
    local key, moves = nil, 0
    local banned, banned_where = {}, nil
    local old = plan_move_towards_destination
    function plan_move_towards_destination()
        local dest = qw.move_destination
        if not dest then
            return old()
        end
        local where = you.where()
        if banned_where ~= where then
            banned, banned_where = {}, where
        end
        local k = where .. "@" .. dest.x .. "," .. dest.y
        if k ~= key then
            key, moves = k, 0
        end
        if banned[k] or moves >= LIMIT then
            if not banned[k] then
                banned[k] = true
                crawl.stderr("QWDBG\\t" .. you.turns() .. "\\tunstick dest_giveup: dropped "
                    .. tostring(qw.move_reason) .. " destination " .. k .. " after " .. moves
                    .. " moves")
            end
            qw.move_destination = nil
            qw.move_reason = nil
            key, moves = nil, 0
            return false
        end
        local acted = old()
        if acted then
            moves = moves + 1
        end
        return acted
    end
end"""),
    "travel_walk": ("when travel (G) to a branch fails here with 'Sorry, I don't know how to get "
                    "there.' and the entrance is on this level's map, walk to it (into the plants "
                    "that block it) and take it: dpeg_oklobed_lair rings the Lair entrance with "
                    "plants, and qw bounced between the two levels until it quit",
                    """do
    local failed = {}  -- level -> branch whose travel failed there
    local last_branch
    local said = {}
    local old_message = c_message
    function c_message(text, channel)
        if last_branch and text:find("know how to get there", 1, true) then
            failed[you.where()] = last_branch
        end
        return old_message(text, channel)
    end

    local old_send = send_travel
    function send_travel(branch, depth)
        last_branch = branch
        local where = you.where()
        if branch ~= "D" and failed[where] == branch and you.branch() ~= branch then
            local ok, entrance = pcall(branch_entrance, branch)
            if ok and entrance then
                local tag = where .. ">" .. branch
                if view.feature_at(0, 0) == entrance then
                    crawl.stderr("QWDBG\\t" .. you.turns() .. "\\tunstick travel_walk: on the "
                        .. branch .. " entrance on " .. where .. ", taking it")
                    go_downstairs()
                    return
                end
                local result = best_move_towards_features({ entrance }, true)
                if result then
                    if not said[tag] then
                        said[tag] = true
                        crawl.stderr("QWDBG\\t" .. you.turns() .. "\\tunstick travel_walk: travel to "
                            .. branch .. " failed on " .. where .. ", walking to its entrance")
                    end
                    move_towards_destination(result.move, result.dest, "goal")
                    return
                end
            end
        end
        return old_send(branch, depth)
    end
end"""),
    "bounce_giveup": ("after 40 quick hops back to the level just left (each stay 6 turns or less), "
                      "count both as explored: qw's search for unexplored stairs resets the other "
                      "level's stairs each time, so a level with a stair it can never reach "
                      "(seed 100601: D:7/D:8) is never done",
                      """do
    local LIMIT = 40
    local gave_up = {}
    local last_where, last_turn, prev_where, run = nil, nil, nil, 0
    local function track()
        local where, turn = you.where(), you.turns()
        if where == last_where then
            return
        end
        if prev_where == where and last_turn and turn - last_turn <= 6 then
            run = run + 1
        else
            run = 0
        end
        prev_where, last_where, last_turn = last_where, where, turn
        if run >= LIMIT and not (gave_up[where] and gave_up[prev_where]) then
            gave_up[where], gave_up[prev_where] = true, true
            run = 0
            crawl.stderr("QWDBG\\t" .. you.turns() .. "\\tunstick bounce_giveup: " .. LIMIT
                .. " quick hops back and forth between " .. prev_where .. " and " .. where
                .. ", both counted explored")
        end
    end

    local function given_up(branch, depth)
        return gave_up[make_level(branch, depth)]
    end

    local old_update = update_goal
    function update_goal()
        track()
        return old_update()
    end

    local old_explored = explored_level
    function explored_level(branch, depth)
        return given_up(branch, depth) or old_explored(branch, depth)
    end

    local old_autoexplored = autoexplored_level
    function autoexplored_level(branch, depth)
        return given_up(branch, depth) or old_autoexplored(branch, depth)
    end

    local old_have = have_all_stairs
    function have_all_stairs(branch, depth, dir, feat_state)
        return given_up(branch, depth) or old_have(branch, depth, dir, feat_state)
    end

    local old_count = count_stairs
    function count_stairs(branch, depth, dir, feat_state)
        if given_up(branch, depth) then
            return num_required_stairs(branch, depth, dir)
        end
        return old_count(branch, depth, dir, feat_state)
    end

    local old_reset = reset_stone_stairs
    function reset_stone_stairs(branch, depth, dir)
        if not given_up(branch, depth) then
            return old_reset(branch, depth, dir)
        end
    end

    local old_finalize = finalize_travel_depth
    function finalize_travel_depth(result)
        if not given_up(result.branch, result.depth) then
            return old_finalize(result)
        end
    end
end"""),
    "portal_expire": ("forget a timed portal when it closes in view ('the gate leading to a gauntlet "
                      "disappears!'), and apply qw's 800-turn portal timeout whenever qw heads for a "
                      "portal: qw only drops a portal on 'The walls and floor vibrate strangely', the "
                      "message for a portal closing out of sight, and checks the timeout only when it "
                      "re-plans. Seed 100532 (t10a) fought beside a Gauntlet gate until it closed and "
                      "walked to the empty arch for 26,000 turns",
                      """do
    local old_message = c_message
    function c_message(text, channel)
        local result = old_message(text, channel)
        if text:find(" disappears!", 1, true) or text:find("vanishes just as you enter", 1, true) then
            local where = you.where()
            local expiring = c_persist.expiring_portals and c_persist.expiring_portals[where]
            if expiring and expiring[1] then
                crawl.stderr("QWDBG\\t" .. you.turns() .. "\\tunstick portal_expire: " .. tostring(expiring[1])
                    .. " on " .. where .. " closed in view")
                remove_expired_portal(where)
            end
        end
        return result
    end

    local old_go = plan_go_to_portal_entrance
    function plan_go_to_portal_entrance()
        update_expired_portals()
        return old_go()
    end
end"""),
    "stairs_backtrack": ("after 20 searches for unexplored stairs on one visit to a level, take qw's "
                         "own backtrack plan (back through the stairs we know, the stair search reset) "
                         "instead of searching again: qw only concludes 'no more reachable unexplored "
                         "stairs' after two searches from the same square, and the autoexplore between "
                         "searches moves it every time. Seed 100705 came back up into a tree-ringed "
                         "grove on D:1 whose last unexplored down stair is outside the ring, and "
                         "searched for it for 15,000 turns",
                         """do
    local LIMIT = 20
    local where_seen, tries = nil, 0
    local old = plan_go_to_unexplored_stairs
    function plan_go_to_unexplored_stairs()
        local where = you.where()
        if where ~= where_seen then
            where_seen, tries = where, 0
        end
        if tries >= LIMIT then
            local acted = plan_unexplored_stairs_backtrack()
            if acted then
                crawl.stderr("QWDBG\\t" .. you.turns() .. "\\tunstick stairs_backtrack: " .. tries
                    .. " searches for unexplored stairs on " .. where .. ", backtracking")
                tries = 0
            end
            return acted
        end
        local result = old()
        if result ~= false then
            tries = tries + 1
        end
        return result
    end
end"""),
    "new_game_branches": ("rebuild qw's branch entrance depths once qw has emptied c_persist for a new "
                          "game: initialize() runs initialize_branch_data() before first_turn_initialize() "
                          "empties c_persist, so the depths come from the previous game's "
                          "c_persist.branch_entries (run.py's workers keep one c_persist file across "
                          "games), and qw only ever moves an entrance shallower. After a game with Lair on "
                          "D:9, a Lair found on D:11 stays 'on D:9': when crawl's travel can't path to the "
                          "real entrance (seed 100820: it is inside an exclusion), qw heads up the stairs "
                          "towards D:9 instead of walking there, crawl's travel brings it back down, and it "
                          "bounces until it quits (seeds 100820, 101021, 100724). Also makes a game "
                          "independent of the game its worker played before",
                          """do
    local BRANCHES = { "Temple", "Orc", "Elf", "Lair", "Swamp", "Shoals", "Snake", "Spider", "Slime",
        "Vaults", "Crypt", "Tomb", "Depths", "Zot" }
    local function depths()
        local d = {}
        for _, br in ipairs(BRANCHES) do
            local ok, parent, lo, hi = pcall(parent_branch, br)
            d[br] = ok and (tostring(parent) .. ":" .. tostring(lo) .. "-" .. tostring(hi)) or "?"
        end
        return d
    end

    local old = first_turn_initialize
    function first_turn_initialize()
        -- qw's own test for a game it has not set up yet.
        local new_game = not (you.turns() > 0 and c_persist.record)
        local result = old()
        if new_game then
            local before = depths()
            if not c_persist.branch_entries then
                c_persist.branch_entries = {}
            end
            initialize_branch_data()
            local after = depths()
            local changed = {}
            for _, br in ipairs(BRANCHES) do
                if before[br] ~= after[br] then
                    changed[#changed + 1] = br .. " " .. before[br] .. " -> " .. after[br]
                end
            end
            if #changed > 0 then
                crawl.stderr("QWDBG\\t" .. you.turns() .. "\\tunstick new_game_branches: entrance depths "
                    .. "left from the last game reset: " .. table.concat(changed, ", "))
            end
        end
        return result
    end
end"""),
    # --- loops with no turn passing ---------------------------------------------------
    # Crawl calls ready() at most 1000 times without a turn passing (main.cc,
    # lua_calls_no_turn): the next call prints "Infinite lua loop detected, aborting." and
    # ready() is never called again until a turn passes. Headless, nothing else ever acts, so
    # crawl spins at 100% CPU with no qw output until the time limit: the "hung" games.
    # ladder.lua's QWSTALL counts decisions (500), but a decision can take two ready() calls
    # (a quiver change yields), so crawl's limit can come first.
    "evoke_noturn": ("an evoke at the same turn as the last one is skipped: qw's attack_wand plan "
                     "returns nil, so qw's own 'failed despite returning true' check never sees a "
                     "zap that took no turn (quiver unchanged, line of fire blocked by a plant) and "
                     "zaps forever: seed 100604 (t05) hung on Lair:5",
                     """do
    local last_turn
    local said = {}
    local old = plan_targeted_evoke
    function plan_targeted_evoke()
        local turn = you.turns()
        if last_turn == turn then
            local where = you.where()
            if not said[where] then
                said[where] = true
                crawl.stderr("QWDBG\\t" .. turn .. "\\tunstick evoke_noturn: the last evoke took no turn on "
                    .. where .. ", skipping evokes until a turn passes")
            end
            return false
        end
        local result = old()
        if result == nil then
            -- nil is qw's "evoked": remember the turn it was sent on.
            last_turn = turn
        end
        return result
    end
end"""),
    "ready_watchdog": ("after 900 ready() calls with no turn passing, write QWSTALL (run.py then ends "
                       "the game as 'stalled') before crawl's own limit of 1000 bans ready() and the "
                       "game idles to the time limit",
                       """do
    local LIMIT = 900
    local calls, turn_seen = 0, nil
    local old_ready = ready
    function ready()
        local turn = you.turns()
        if turn ~= turn_seen then
            turn_seen, calls = turn, 0
        end
        calls = calls + 1
        if calls == LIMIT then
            crawl.stderr("QWSTALL\\tready:" .. calls .. "\\t" .. turn .. "\\t" .. you.where())
        end
        return old_ready()
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
