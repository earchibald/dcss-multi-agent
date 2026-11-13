"""Patches that make qw (crawl/qw @ 8698adc, July 2024, ~0.32 trunk) run on DCSS 0.34.0.

Each patch replaces an exact snippet in one of qw's Lua files. build.py applies them to a
copy of the source and refuses to build if a snippet is missing or occurs a different
number of times than expected, so a qw update can't silently skip a patch.

qw's own source is not stored in this repo; these snippets are the minimum needed to
locate each change. qw is maintained by the DCSS devteam (https://github.com/crawl/qw).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Patch:
    file: str
    old: str
    new: str
    why: str
    count: int = 1  # expected occurrences of `old`; all are replaced
    # "port": needed to run on 0.34 / Lua 5.4. "bugfix": a qw bug that exists on any
    # version and changes play (build.py --stock leaves these out). "crashfix": a qw bug
    # that raises a Lua error every turn (always applied). "hook": calls into ladder.lua.
    kind: str = "port"
    # The build stage that added the patch. "" is in every build (up to and including
    # stage zk); a named stage is in `build.py --stage NAME` for that stage or a later
    # one in STAGES, so adding a stage never changes what an earlier stage builds.
    stage: str = ""


# Named build stages after zk, in order. build.py --stage NAME includes NAME and the
# stages before it.
STAGES: list[str] = ["zr"]


def patches_for(stage: str | None) -> list[Patch]:
    """The patches that make up a stage's build (None: the unstaged build, i.e. zk)."""
    if stage is not None and stage not in STAGES:
        raise SystemExit(f"unknown stage {stage!r}; stages: {', '.join(STAGES)}")
    allowed = {""} | (set(STAGES[: STAGES.index(stage) + 1]) if stage else set())
    return [p for p in PATCHES if p.stage in allowed]


PATCHES: list[Patch] = [
    # --- qw bugs, independent of the crawl version (left out by build.py --stock) -------
    Patch(
        "player.lua",
        'and not you.transform() == "lich"',
        'and you.transform() ~= "lich"',
        "Operator precedence: `not you.transform() == \"lich\"` is "
        "`(not you.transform()) == \"lich\"`, always false, so can_berserk() was always "
        "false and qw never used Trog's Berserk.",
        kind="bugfix",
    ),
    Patch(
        "plans-rest.lua",
        "        trogs_hand()\n",
        '        use_ability("Trog\'s Hand")\n',
        "qw bug, not version drift: plan_cure_poison() calls trogs_hand(), which is not "
        "defined anywhere ('attempt to call a nil value (global 'trogs_hand')' every turn "
        "once a Trog worshipper at ** piety is badly poisoned). Kept by --stock because "
        "without it the game cannot continue.",
        kind="crashfix",
    ),
    Patch(
        "plans-attack.lua",
        "    local move = get_monster_at(target.pos):get_player_move_towards(true)\n"
        "    local feat = view.feature_at(move.x, move.y)\n",
        "    local move = get_monster_at(target.pos):get_player_move_towards(true)\n"
        "    if not move then\n        return false\n    end\n"
        "    local feat = view.feature_at(move.x, move.y)\n",
        "qw bug: plan_flight_move_towards_enemy() indexes the move without checking it; with "
        "a potion of enlightenment in the pack and no way to step toward the target it "
        "raised 'attempt to index a boolean value (local 'move')' every turn until the "
        "runner ended the game (30 of 200 games when a policy vetoed melee).",
        kind="crashfix",
    ),
    Patch(
        "turn.lua",
        "        dump_count = qw.dump_count + 100\n",
        "        qw.dump_count = qw.dump_count + 100\n",
        "Typo: the counter written was a stray global, so after turn 100 qw wrote a "
        "character dump file on every turn instead of every 100 turns. No effect on "
        "play; saves time.",
        kind="bugfix",
    ),
    Patch(
        "move.lua",
        '    magic(delta_to_vi(pos) .. "YY")\n    return true\nend\n',
        '    if you.status("immotile") then\n        return false\n    end\n\n'
        '    magic(delta_to_vi(pos) .. "YY")\n    return true\nend\n',
        "qw does not know the -Move status (an ironbound beastmaster's bolas, electricity "
        "in water). A step then answers 'You cannot move.' and takes no turn, every move "
        "plan 'fails despite returning true', and the game spins on one turn: 36 of the "
        "41 stalls in search stages 2 and 3, 33 of them in Vaults. Kept by "
        "--stock because without it the game cannot continue.",
        kind="crashfix",
    ),
    Patch(
        "plans-attack.lua",
        'function random_step(reason)\n    if you.mesmerised() then\n',
        'function random_step(reason)\n    if you.status("immotile") then\n'
        '        say("Waiting to move again (" .. reason .. ").")\n'
        '        wait_one_turn()\n        return true\n    end\n\n'
        '    if you.mesmerised() then\n',
        "With move_to() refusing while -Move, the plan of last resort has to pass the "
        "turn itself.",
        kind="crashfix",
    ),
    Patch(
        "player.lua",
        '            return form == "tree" or form == "fungus" and qw.danger_in_los\n',
        '            return form == "tree" or form == "fungus" and qw.danger_in_los\n'
        '                or you.status("immotile")\n',
        "The same -Move status where qw asks the question itself: unable_to_move() only "
        "knew tree and fungus form, so flee, kiting and tactical steps were still planned "
        "while bound.",
        kind="bugfix",
    ),
    Patch(
        "move.lua",
        "    if cache ~= nil then\n",
        "    if cache_result ~= nil then\n",
        "qw bug: distance_map_search_from() tests the undefined global `cache`, not "
        "`cache_result`, so its memo never hits and the search for a flee route is "
        "exponential in the route's length. With a flee position 84 squares away "
        "(seed 500020, Snake:2) crawl span at 100% CPU inside one decision until the "
        "time limit. The search's answer is unchanged.",
        kind="crashfix",
    ),
    Patch(
        "util.lua",
        "        local val1 = a[key]\n        local val2 = b[key]\n",
        "        local val1 = a[key] or 0\n        local val2 = b[key] or 0\n",
        "qw bug: compare_table_keys() compares properties that a result may not have. "
        "Two wand-attack results with none of the attack's properties scored raised "
        "'attempt to compare two nil values' on every decision until the runner ended "
        "the game (seed 500069 in Lair:5, about one game in 300). A missing property "
        "now counts as 0.",
        kind="crashfix",
    ),
    Patch(
        "plans-emergency.lua",
        "function plan_cure_bad_poison()\n"
        "    if not qw.danger_in_los then\n"
        "        return false\n"
        "    end\n"
        "\n"
        "    if you.poison_survival() <= you.hp() - 60 then\n"
        "        if drink_by_name(\"curing\") then\n",
        "function plan_cure_bad_poison()\n"
        "    local survival = you.poison_survival()\n"
        "    if survival > 0 and not qw.danger_in_los then\n"
        "        return false\n"
        "    end\n"
        "\n"
        "    if survival <= 0 or survival <= you.hp() - 60 then\n"
        "        if can_drink() and drink_by_name(\"curing\") then\n",
        "qw bug: poison is cured only when it will take 60 HP or more, and only with an "
        "enemy in view. Under 60 HP a lethal dose never qualifies, so qw dies of poison "
        "holding the cure: on the held-out 200, 18 of the tuned settings' 29 deaths in "
        "Spider, Snake, Shoals and Swamp were lethally poisoned and 28 carried potions "
        "of curing. Lethal poison is now cured wherever it is noticed. The drink is also "
        "skipped while berserk, where it cannot work and raised 'cure_bad_poison failed "
        "despite returning true'.",
        kind="bugfix",
    ),
    Patch(
        "move.lua",
        "    for pos in adjacent_iter(from_pos) do\n"
        "        local result = assess_move(pos, from_pos, dist_map, best_result)\n"
        "        if result then\n"
        "            best_result = result\n"
        "        elseif allow_unsafe and (not best_result or not best_result.safe) then\n",
        "    for pos in adjacent_iter(from_pos) do\n"
        "        local tabu = false\n"
        "        for _, seen in ipairs(ladder_move_tabu or {}) do\n"
        "            tabu = tabu or positions_equal(pos, seen)\n"
        "        end\n"
        "        local result = not tabu\n"
        "            and assess_move(pos, from_pos, dist_map, best_result)\n"
        "        if result then\n"
        "            best_result = result\n"
        "        elseif not tabu and allow_unsafe\n"
        "                and (not best_result or not best_result.safe) then\n",
        "qw bug, part 1 of 2: see plan_move_towards_destination below. best_move_towards() "
        "skips the squares in ladder_move_tabu when it is set.",
        kind="bugfix",
    ),
    Patch(
        "plans-explore.lua",
        "    result = best_move_towards(qw.move_destination, qw.map_pos, true)\n"
        "    if result then\n"
        "        return move_to(result.move)\n"
        "    end\n"
        "\n"
        "    return false\n",
        "    local trail = ladder_move_trail\n"
        "    if not trail or not positions_equal(trail.dest, qw.move_destination) then\n"
        "        trail = { seen = {}, dest = {\n"
        "            x = qw.move_destination.x, y = qw.move_destination.y } }\n"
        "    end\n"
        "    ladder_move_tabu = trail.seen\n"
        "    local result = best_move_towards(qw.move_destination, qw.map_pos, true)\n"
        "    ladder_move_tabu = nil\n"
        "    if not result and #trail.seen > 0 then\n"
        "        trail.seen = {}\n"
        "        result = best_move_towards(qw.move_destination, qw.map_pos, true)\n"
        "    end\n"
        "    ladder_move_trail = nil\n"
        "    if result and move_to(result.move) then\n"
        "        local here = trail.seen[#trail.seen]\n"
        "        if not here or not positions_equal(here, qw.map_pos) then\n"
        "            table.insert(trail.seen, { x = qw.map_pos.x, y = qw.map_pos.y })\n"
        "        end\n"
        "        if #trail.seen > 16 then\n"
        "            table.remove(trail.seen, 1)\n"
        "        end\n"
        "        ladder_move_trail = trail\n"
        "        return true\n"
        "    end\n"
        "\n"
        "    return false\n",
        "qw bug: walking to a destination, a step is chosen from the route that avoids "
        "exclusions when a safe step exists and from the plain route when none does. The "
        "two routes can disagree: from A the safe route goes through B, and at B the next "
        "safe square is a web, so the plain route goes back through A. qw then steps A, B, "
        "A, B until Zot's clock drains it and it quits (seed 500012: 15,620 turns on D:2 "
        "at XL 3; 17 of 400 held-out games ended by quitting). Steps back onto the last "
        "16 squares of the same walk are now skipped (skipping only the square just left "
        "turned seed 500034's two-square loop into a three-square one); when that leaves "
        "no step at all, the trail is forgotten. Also makes `result` local.",
        kind="bugfix",
    ),
    Patch(
        "plans-emergency.lua",
        "function plan_berserk()\n"
        "    if can_berserk() and want_to_berserk() then\n"
        "        return use_ability(\"Berserk\")\n",
        "function plan_berserk()\n"
        "    if can_berserk() and want_to_berserk() then\n"
        "        if you.poisoned() and you.poison_survival() <= you.hp() / 2\n"
        "                and can_drink() and drink_by_name(\"curing\") then\n"
        "            say(\"(to cure poison before going berserk)\")\n"
        "            return true\n"
        "        end\n"
        "\n"
        "        return use_ability(\"Berserk\")\n",
        "qw bug: nothing can be drunk while berserk, and qw goes berserk with poison "
        "already in it. The poison turns lethal mid-rage, the potion is refused ('You are "
        "too berserk!') and qw dies as the rage ends: of the tuned settings' 29 held-out "
        "deaths in Spider, Snake, Shoals and Swamp, 18 were lethally poisoned and 20 were "
        "on berserk cooldown. Poison that will take half the current HP is now cured "
        "first, which costs the turn the rage would have started on.",
        kind="bugfix",
    ),
    Patch(
        "plans-rest.lua",
        "    if drink_by_name(\"curing\") then\n"
        "        say(\"(to cure poison)\")\n",
        "    if can_drink() and drink_by_name(\"curing\") then\n"
        "        say(\"(to cure poison)\")\n",
        "qw bug: plan_cure_poison tries the potion while berserk, twice a turn, and "
        "raises 'Cure_poison failed despite returning true' each time.",
        kind="bugfix",
    ),
    # --- Lua 5.1 -> 5.4 (crawl's bundled Lua is 5.4 by 0.34) ---------------------------
    Patch(
        "turn.lua",
        "function turn_memo_args(name, func, ...)\n",
        "function turn_memo_args(name, func, ...)\n    local arg = table.pack(...)\n",
        "The implicit vararg table `arg` is gone in Lua 5.4 ('attempt to index a nil "
        "value (global 'arg')' on the first turn). table.pack(...) gives the same "
        "table with .n.",
    ),
    Patch(
        "monster-class.lua",
        "function Monster:property_memo_args(name, func, ...)\n",
        "function Monster:property_memo_args(name, func, ...)\n"
        "    local arg = table.pack(...)\n",
        "Same `arg` vararg table fix.",
    ),
    Patch(
        "attack.lua",
        "damage = damage * math.pow(2, value)",
        "damage = damage * 2 ^ value",
        "math.pow is not in Lua 5.4 without compat flags.",
    ),
    Patch(
        "attack.lua",
        'local dice, size = unpack(split(damage, " "))',
        'local dice, size = table.unpack(split(damage, " "))',
        "The global unpack is table.unpack in Lua 5.2+.",
    ),
    # --- clua API drift -------------------------------------------------------------
    Patch(
        "player.lua",
        "function max_strength()\n    return select(2, you.strength())\n",
        "function max_strength()\n"
        "    local cur, max = you.strength()\n"
        "    return max or cur\n",
        "you.strength() returns only the current value on 0.34 (it used to return "
        "current, max), so max_strength() was nil and skill choice crashed on turn 0 "
        "('attempt to compare nil with number'). Current strength stands in for max.",
    ),
    Patch(
        "player.lua",
        "function max_dexterity()\n    return select(2, you.dexterity())\n",
        "function max_dexterity()\n"
        "    local cur, max = you.dexterity()\n"
        "    return max or cur\n",
        "Same for you.dexterity().",
    ),
    Patch(
        "player.lua",
        "function base_mutation(str)\n",
        "function base_mutation(str)\n"
        "    if not ladder_mutation_exists(str) then\n"
        "        return 0\n"
        "    end\n",
        "Mutations 'berserk', 'deterioration', 'inability to drink after injury' and "
        "'inability to read after injury' no longer exist; you.mutation() raises "
        "\"No such mutation\" for them, which killed the item-use plans every turn "
        "once qw had a cure-mutation potion to consider. Unknown names count as 0.",
    ),
    Patch(
        "plans-emergency.lua",
        "    local dex, mdex = you.dexterity()\n",
        "    local dex, mdex = you.dexterity()\n"
        "    mstr, mint, mdex = mstr or str, mint or int, mdex or dex\n",
        "Same single-value stat functions in the purification check; without max "
        "values only the absolute 'stat below 3' tests remain meaningful.",
    ),
    Patch(
        "plans.lua",
        "pairs(you.ability_table())",
        "pairs(ladder_ability_table())",
        "you.ability_table() was removed from clua (0.33/0.34); ladder.lua rebuilds the "
        "letter->name table from you.ability_info(). Without it every ability use "
        "(Trog's Berserk included) raises a Lua error.",
    ),
    Patch(
        "plans-items.lua",
        "you.abilities()",
        "ladder_abilities()",
        "you.abilities() was removed; ladder.lua lists names from you.ability_info().",
        count=3,
    ),
    Patch(
        "monster-class.lua",
        "self.minfo:has_known_ranged_attack()",
        "self.minfo:range() > 1",
        "monster.info:has_known_ranged_attack() is gone. 0.34 has monster.info:range() "
        "(threat range from launchers, missiles, wands, spells and reach). Reach is "
        "subtracted by qw's own ignore_reach check that follows.",
    ),
    # Item identification: 0.34 has only full identification, exposed as
    # item.is_identified. item.fully_identified now reads as nil (unknown item
    # attributes return nothing), so qw treated every item as unidentified.
    Patch(
        "equipment.lua",
        "if item.fully_identified then",
        "if item.is_identified then",
        "item.fully_identified -> item.is_identified (0.34 name).",
    ),
    Patch(
        "items.lua",
        "and not item.fully_identified",
        "and not item.is_identified",
        "item.fully_identified -> item.is_identified (0.34 name).",
        count=2,
    ),
    Patch(
        "plans-items.lua",
        "and not it.fully_identified",
        "and not it.is_identified",
        "item.fully_identified -> item.is_identified (0.34 name).",
    ),
    Patch(
        "plans-items.lua",
        'item.class(true) == "scroll" and not item.fully_identified',
        'item.class(true) == "scroll" and not item.is_identified',
        "item.fully_identified -> item.is_identified (0.34 name).",
    ),
    Patch(
        "plans-items.lua",
        "and not item.fully_identified",
        "and not item.is_identified",
        "item.fully_identified -> item.is_identified (0.34 name).",
        count=2,
    ),
    Patch(
        "plans.lua",
        "magic(control('q') .. \"yes\\r\")",
        "magic(control('q') .. \"quit\\r\")",
        "0.34's quit prompt says '(Confirm with \"quit\".)'; qw typed 'yes', so its Quit "
        "goal (after QUIT_TURNS stuck turns, or max HP 1 from the Zot clock) never ended "
        "the game and qw retried forever ('quit failed despite returning true').",
    ),
    Patch(
        "plans-items.lua",
        '            magic("d" .. item_letter(item) .. "\\r")\n',
        "            item.drop()\n",
        "0.34 gives potions, scrolls and evocables their own inventory letters, so a "
        "letter can name both a gear item and a consumable. In the multi-select drop "
        "menu 'd<letter><Enter>' selects every item with that letter. qw logged "
        "'drop_items failed despite returning true'; item.drop() drops exactly this "
        "item.",
    ),
    Patch(
        "plans-items.lua",
        "        if want_drop_item(item) then\n",
        "        if want_drop_item(item) and not item.equipped then\n",
        "0.34 won't drop worn gear (neither the 'd' key nor item.drop()); qw asked to "
        "drop worn jewellery and armour it had outgrown and failed every turn. Taking it "
        "off first made qw take a ring off and put it back on every turn for 30,000 "
        "turns (the wear plan still wanted it), so worn items are left to qw's "
        "remove/upgrade plans and dropped once they are off.",
    ),
    # --- 0.33 equipment rework: the shield slot is now "Offhand" -----------------------
    Patch(
        "equipment.lua",
        'const.armour_equip_names = { shield="Shield",',
        'const.armour_equip_names = { shield="Offhand",',
        'items.equipped_at("Shield") returns nothing on 0.34: the slot is named '
        '"Offhand", so qw never saw its own shield.',
    ),
    Patch(
        "equipment.lua",
        'const.all_equip_names = { weapon="Weapon", shield="Shield",',
        'const.all_equip_names = { weapon="Weapon", shield="Offhand",',
        'Same "Shield" -> "Offhand" slot rename.',
    ),
    Patch(
        "equipment.lua",
        '    elseif class == "armour" then\n        return item.subtype()\n',
        '    elseif class == "armour" then\n'
        "        local sub = item.subtype()\n"
        '        return sub == "offhand" and "shield" or sub\n',
        'For armour, item.subtype() returns the slot name, which is "offhand" for '
        'shields on 0.34; qw\'s slot tables all say "shield".',
    ),
    # --- hooks for ladder.lua ------------------------------------------------------------
    Patch(
        "plans.lua",
        "                plan_turns[plan] = you.turns()\n"
        "                plan_result[plan] = result\n",
        "                plan_turns[plan] = you.turns()\n"
        "                plan_result[plan] = result\n"
        "                ladder_record_plan(plandata[2], result)\n",
        "Report each plan that acted to ladder.lua's per-action log (a no-op unless "
        "LADDER_ACTION_LOG is set).",
        kind="hook",
    ),
    Patch(
        "plans.lua",
        "            if qw.restart_cascade\n"
        "                    or you.turns() ~= plan_turns[plan]\n",
        "            if ladder_is_vetoed(plandata[2]) then\n"
        "                -- Skipped by a ladder override (veto); the next plan acts.\n"
        "            elseif qw.restart_cascade\n"
        "                    or you.turns() ~= plan_turns[plan]\n",
        "Veto overrides: skip named plans for one decision (always false without an "
        "override).",
        kind="hook",
    ),
    # --- stage zr: poison and the end of a rage (applied after the zk patches above) ----
    Patch(
        "plans-emergency.lua",
        "function plan_berserk()\n",
        "function plan_cure_lethal_poison()\n"
        "    if you.poison_survival() <= 0 and can_drink()\n"
        "            and drink_by_name(\"curing\") then\n"
        "        say(\"(to cure lethal poison before anything else)\")\n"
        "        return true\n"
        "    end\n"
        "\n"
        "    return false\n"
        "end\n"
        "\n"
        "function plan_berserk()\n",
        "Stage zr: defines plan_cure_lethal_poison(), the first emergency plan (next patch).",
        kind="bugfix",
        stage="zr",
    ),
    Patch(
        "plans-emergency.lua",
        "    plans.emergency = cascade {\n"
        "        {plan_stairdance_up, \"stairdance_up\"},\n",
        "    plans.emergency = cascade {\n"
        "        {plan_cure_lethal_poison, \"cure_lethal_poison\"},\n"
        "        {plan_stairdance_up, \"stairdance_up\"},\n",
        "Stage zr, the rage-end case. Nothing can be drunk, read or invoked in a rage, so "
        "when the rage's end leaves the poison lethal, the only fix the game allows is "
        "curing on the first action after it. zk's lethal-poison cure sits behind "
        "stairdance_up, teleport and five other emergency plans, and a teleport scroll "
        "read while lethally poisoned is 3-5 turns of poison with no cure (2 of zk's 8 "
        "poison deaths on training seeds 100000-100149 ended 'about to teleport'). "
        "Lethal poison with a potion of curing in the pack is now cured first.",
        kind="bugfix",
        stage="zr",
    ),
]
