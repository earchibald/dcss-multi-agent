------------------------------------------------------------------------------
-- Ladder additions to qw, appended by tools/qw/build.py after qw's own files,
-- inside the same Lua chunk (so qw's chunk-level locals such as `qw` and
-- `plans` are visible here). This file is ours, not part of qw.
--
-- 1. 0.34 compatibility shims for clua functions that no longer exist.
-- 2. Unattended running: Lua errors and panics are written to stderr and qw
--    carries on instead of stopping and waiting for a human.
-- 3. Optional per-decision logs on stderr: the action (LADDER_ACTION_LOG) and
--    the state qw decided from (LADDER_STATE_LOG, implies the action log).
-- 4. Overrides: ladder_choose(decision, state) may veto plans or force a
--    primitive for one or more decisions (LADDER_OVERRIDES in the rc).
--
-- Every stderr line starts with a tag and is tab-separated:
--   QWSTART <turn> <place> <qw version>
--   QWERR   <turn> <place> <error text>
--   QWPANIC <turn> <place> <message>
--   QWMSG   <turn> <channel: game message>     (the last 8, after each panic)
--   QWPLACE <turn> <place> <xl>               (each time qw acts on a new level)
--   QWS     <decision> key=value ...          (before the cascade)
--   QWOVR   <decision> <spec> <acted 0/1>     (when an override applies)
--   QWACT   <decision> <turn> <place> <hp> <mhp> <plan path, outermost first>
--           (turn/place/hp after the action; path "" if nothing acted)
--   QWSTALL <decision> <turn> <place>         (500 decisions with no turn passing)

---------------------------------------
-- Deterministic pairs()
--
-- Crawl's Lua 5.4 seeds its string hash per process, so pairs() visits the
-- keys of a string-keyed table in a different order in every crawl process
-- (and table keys follow memory addresses). qw iterates such tables when it
-- chooses between equal options, so the same seed occasionally played out
-- differently from one process to the next (seen: 1 game in 6). From here on
-- pairs() visits number keys in ascending order, then string keys in
-- ascending order, then booleans, then any other keys; values removed during
-- the loop are skipped, as with the real pairs().
local raw_pairs, raw_next = pairs, next
local key_rank = { number = 1, string = 2, boolean = 3 }

local function key_less(a, b)
    local ta, tb = type(a), type(b)
    if ta ~= tb then
        return (key_rank[ta] or 4) < (key_rank[tb] or 4)
    end
    if ta == "number" or ta == "string" then
        return a < b
    end
    if ta == "boolean" then
        return not a and b
    end
    return false
end

function pairs(t)
    local mt = getmetatable(t)
    if type(t) ~= "table" or mt and mt.__pairs then
        return raw_pairs(t)
    end
    local keys = {}
    for k in raw_next, t do
        keys[#keys + 1] = k
    end
    if #keys > 1 then
        table.sort(keys, key_less)
    end
    local i = 0
    return function()
        while true do
            i = i + 1
            local k = keys[i]
            if k == nil then
                return nil
            end
            local v = rawget(t, k)
            if v ~= nil then
                return k, v
            end
        end
    end, t, nil
end

local function ladder_emit(tag, ...)
    local parts = { tag }
    for i = 1, select("#", ...) do
        local v = tostring(select(i, ...))
        parts[#parts + 1] = (v:gsub("[\t\n]", " "))
    end
    crawl.stderr(table.concat(parts, "\t"))
end

---------------------------------------
-- 0.34 shims

-- you.ability_table() (letter -> name) and you.abilities() (list of names)
-- were removed; you.ability_info() returns { {name, usable, hotkey}, ... }.
function ladder_ability_table()
    local t = {}
    for _, a in ipairs(you.ability_info() or {}) do
        t[a[3]] = a[1]
    end
    return t
end

function ladder_abilities()
    local t = {}
    for _, a in ipairs(you.ability_info() or {}) do
        t[#t + 1] = a[1]
    end
    return t
end

-- you.mutation(name) raises an error for a name crawl doesn't know; some
-- mutations qw asks about were removed by 0.34.
local ladder_known_mutations = {}
function ladder_mutation_exists(name)
    local known = ladder_known_mutations[name]
    if known == nil then
        known = pcall(you.mutation, name)
        ladder_known_mutations[name] = known
    end
    return known
end

-- Prompts new since qw's version. qw only changes equipment when it sees no
-- danger, but 0.34 also asks when a monster it ignores is merely nearby;
-- qw's own answer to that (no prompt existed) was to go ahead.
local ladder_orig_answer_prompt = c_answer_prompt
function c_answer_prompt(prompt)
    if prompt:find("Spend multiple turns changing equipment") then
        return true
    end
    -- 0.34 words the old "Really wear/put on/wield ...?" warnings (which qw
    -- answers yes) as "Really equip ...?".
    if prompt:find("Really equip") then
        return true
    end
    return ladder_orig_answer_prompt(prompt)
end

---------------------------------------
-- Error, panic and action reporting

local ladder_errors = 0
local ladder_plan_path = nil
local ladder_last_place = nil

-- Called from qw's cascade() (see patches.py) for every plan that acted
-- (result true) or asked to be rerun (nil). Inner cascades finish first, so
-- names arrive innermost first.
function ladder_record_plan(name, result)
    if ladder_plan_path and result ~= false then
        table.insert(ladder_plan_path, 1, name)
    end
end

---------------------------------------
-- Decisions: state, overrides, action
--
-- A decision is one call of qw's turn cascade (plans.turn). Decisions are
-- numbered from 0 in each game; the numbering is the same on every replay of
-- a seed, so a fork can name the decision it changes.

local ladder_decision = -1
local ladder_veto = nil      -- set of plan names cascade() skips, or nil
local ladder_veto_hit = false
local ladder_active = nil    -- { spec = ..., left = n } carried across decisions
local ladder_stall_turn = -1
local ladder_stall_count = 0

-- Called from qw's cascade() (see patches.py) before each plan.
function ladder_is_vetoed(name)
    if ladder_veto and ladder_veto[name] then
        ladder_veto_hit = true
        return true
    end
    return false
end

---------------------------------------
-- Holding a fight: the choke and stairs_fight primitives
--
-- qw only looks for a choke point (move-retreat.lua) when it uses a ranged
-- weapon. These two primitives give a melee character the classic answer to
-- being outnumbered: get to a square where few enemies can reach you, or onto
-- an upstairs, and fight there. They only run when forced, so qw's own play
-- is unchanged otherwise.
--
-- A forced spec stays active for n decisions. The primitive plans once, on
-- its first decision (a target square, and for choke the path to it), then
-- walks there and holds: qw's emergency plans run first (heal, berserk,
-- Trog's Hand, teleport, stairdance), minus the two that would step off the
-- spot (flee, tactical_step); then it attacks an adjacent enemy, otherwise
-- waits for the enemies to come. It releases the spec (and returns false, so
-- qw's cascade decides) when the fight is over, when nothing is coming, or
-- when only ranged enemies are left to hit it.

local ladder_hold = nil      -- { kind, spec, target, path, attackers_choke, ... }
local ladder_ovr_extra = nil -- extra QWOVR fields from the last primitive

local ladder_last_hold = nil  -- for the QWOVR fields after a release

local function ladder_release()
    ladder_active = nil
    ladder_last_hold = ladder_hold
    ladder_hold = nil
    return false
end

local function enemy_coming(e)
    return not e:is_stationary() and not e:is_unalert()
        and (e:can_melee_player()
            or e:melee_move_distance(const.origin) < const.inf_dist)
end

-- What the hold should do about the enemies in view: "fight" (someone can hit
-- us in melee now), "wait" (someone is coming), "ranged" (nobody in melee
-- reach, a ranged enemy is in view), "none" (nothing to fight).
local function fight_situation()
    if not qw.danger_in_los or #qw.enemy_list == 0 then
        return "none"
    end
    local coming, ranged, outreached = false, false, false
    for _, e in ipairs(qw.enemy_list) do
        if e:can_melee_player() and e:player_can_melee() then
            return "fight"
        end
        if e:can_melee_player() then
            -- A reach weapon (a gnoll sergeant's spear) hits us from where
            -- we can't hit back: waiting for it is the worst choice.
            outreached = true
        end
        if enemy_coming(e) then
            coming = true
        end
        if e:is_ranged(true) then
            ranged = true
        end
    end
    if outreached then
        return "ranged"
    end
    -- Many melee monsters also carry something to throw, so a ranged enemy
    -- only ends the hold when nothing is coming; hold() also gives up when it
    -- keeps losing HP while waiting (shot from out of reach).
    if coming then
        return "wait"
    end
    return ranged and "ranged" or "none"
end

local function attack_adjacent()
    if unable_to_melee() or dangerous_to_melee() then
        return false
    end
    if plan_melee() then
        return true
    end
    -- plan_melee() gives up when its preferred target is not in reach, even
    -- if another enemy is; hit whichever adjacent enemy comes first.
    for _, e in ipairs(qw.enemy_list) do
        if e:distance() == 1 and e:player_can_melee() then
            do_melee_attack(e:pos())
            return true
        end
    end
    return false
end

-- qw's emergency cascade without the plans that leave the spot.
local function emergency_in_place()
    local saved_veto, saved_hit = ladder_veto, ladder_veto_hit
    ladder_veto = { flee = true, tactical_step = true }
    local result = plans.emergency()
    ladder_veto, ladder_veto_hit = saved_veto, saved_hit
    return result ~= false
end

local function hold(on_stairs)
    if emergency_in_place() then
        ladder_hold.phase = "hold-emergency"
        return true
    end
    local situation = fight_situation()
    -- HP lost over two of our waits, with nobody in reach: being shot or cast
    -- at, so holding is not working.
    local hp = you.hp()
    if ladder_hold.waited and hp < ladder_hold.waited then
        ladder_hold.shot = (ladder_hold.shot or 0) + 1
    end
    ladder_hold.waited = nil
    if situation == "wait" and (ladder_hold.shot or 0) >= 2 then
        situation = "ranged"
    end
    if situation == "fight" and attack_adjacent() then
        ladder_hold.phase = "hold-attack"
        return true
    elseif situation == "wait" then
        ladder_hold.phase = "hold-wait"
        ladder_hold.waited = hp
        wait_one_turn()
        return true
    elseif situation == "ranged" and on_stairs and qw.can_flee_upstairs
            and not unable_to_use_stairs() then
        -- Being shot with nobody to hit back: leave by the stairs; only
        -- adjacent enemies follow.
        ladder_hold.phase = "hold-upstairs"
        go_upstairs(you.status("spiked"))
        ladder_release()
        return true
    end
    ladder_hold.phase = "release-" .. situation
    return ladder_release()
end

-- The map positions from (not including) the player's to target, along the
-- path assess_retreat_position() walked, or nil.
local function retreat_path(target)
    local dmap = get_distance_map(qw.map_pos)
    local cells, cur = {}, target
    while not positions_equal(cur, qw.map_pos) do
        table.insert(cells, 1, cur)
        local prev = reverse_retreat_move_to(cur, dmap)
        if not prev then
            return nil
        end
        cur = prev
    end
    return cells
end

-- Best choke position within reach: fewer enemies able to attack there than
-- here, reachable before any enemy not already on us gets into reach of it,
-- no blocking monsters, and no step into reach of an enemy that can't reach
-- us now. Returns result, attackers here.
local function best_choke()
    local here = attacking_monster_count_at(const.origin)
    if here <= 1 or not map_is_unexcluded_at(qw.map_pos) then
        return nil, here
    end
    local radius = qw.los_radius
    local my_delay = player_move_delay()
    local best, best_path
    local why = { cells = 0, open = 0, worse = 0, blocked = 0, late = 0,
        through_reach = 0, ok = 0 }
    local i = 1
    for pos in radius_iter(qw.map_pos, radius) do
        if qw.coroutine_throttle and i % 1000 == 0 then
            qw.throttle = true
            coroutine.yield()
        end
        i = i + 1
        if supdist(position_difference(pos, qw.map_pos)) <= radius
                and map_is_reachable_at(pos) then
            why.cells = why.cells + 1
        end
        if supdist(position_difference(pos, qw.map_pos)) > radius
                or not map_is_reachable_at(pos) then
            -- out of reach
        elseif adjacent_floor_map[pos.x][pos.y] >= 6
                or map_has_adjacent_unseen_at(pos) then
            why.open = why.open + 1
        else
            local r = assess_retreat_position(pos, here - 1, radius)
            if not r then
                why.worse = why.worse + 1
            elseif r.num_blocking > 0 then
                why.blocked = why.blocked + 1
            elseif not best or r.num_attacking < best.num_attacking
                    or r.num_attacking == best.num_attacking
                        and r.dist < best.dist then
                local ok = true
                local arrive = r.dist * my_delay
                for _, e in ipairs(qw.enemy_list) do
                    if not e:can_melee_player() and enemy_coming(e)
                            and e:melee_move_distance(r.pos) * e:move_delay()
                                < arrive then
                        ok = false
                        break
                    end
                end
                local path = ok and retreat_path(r.map_pos)
                if not ok then
                    why.late = why.late + 1
                elseif path then
                    for k = 1, #path - 1 do
                        local los = position_difference(path[k], qw.map_pos)
                        for _, e in ipairs(qw.enemy_list) do
                            if e:can_melee_at(los) and not e:can_melee_player() then
                                path = nil
                                break
                            end
                        end
                        if not path then
                            why.through_reach = why.through_reach + 1
                            break
                        end
                    end
                end
                if path then
                    why.ok = why.ok + 1
                    best, best_path = r, path
                end
            end
        end
    end
    if LADDER_HOLD_DEBUG then
        local parts = {}
        for _, k in ipairs({ "cells", "open", "worse", "blocked", "late",
                "through_reach", "ok" }) do
            parts[#parts + 1] = k .. "=" .. why[k]
        end
        ladder_emit("QWDBG", you.turns(), "choke here=" .. here .. " "
            .. table.concat(parts, " "))
    end
    return best, here, best_path
end

local function hold_extra(here)
    local h = ladder_hold or ladder_last_hold
    local dist = -1
    if h and h.target then
        dist = positions_equal(qw.map_pos, h.target) and 0 or (h.left or -1)
    end
    ladder_ovr_extra = "phase=" .. tostring(h and h.phase or "none")
        .. " attackers_here=" .. tostring(here)
        .. " attackers_choke=" .. tostring(h and h.attackers_choke or -1)
        .. " choke_dist=" .. tostring(dist)
end

-- One step on the way to the target (move is a los position or nil). qw's
-- emergency plans come first, as they do in its own cascade. If the way is
-- blocked, fight where we stand; blocked three decisions running, hand the
-- fight back to qw (and its whole repertoire) rather than stand in the open.
local function en_route(move, here)
    local h = ladder_hold
    if emergency_in_place() then
        h.phase = "move-emergency"
        hold_extra(here)
        return true
    end
    if move and not unable_to_move() and not dangerous_to_move()
            and move_to(move) then
        h.phase = "move"
        h.blocked = 0
        hold_extra(here)
        return true
    end
    h.blocked = (h.blocked or 0) + 1
    h.phase = "blocked"
    if h.blocked <= 3 and fight_situation() == "fight" and attack_adjacent() then
        hold_extra(here)
        return true
    end
    h.phase = "release-blocked"
    hold_extra(here)
    return ladder_release()
end

local function choke(spec)
    if not ladder_hold or ladder_hold.spec ~= spec then
        ladder_hold = { kind = "choke", spec = spec, phase = "plan" }
        if fight_situation() == "none" or unable_to_move() or dangerous_to_move() then
            ladder_hold.phase = "release-none"
            hold_extra(-1)
            return ladder_release()
        end
        local best, here, path = best_choke()
        if not best then
            ladder_hold.phase = "release-nogain"
            hold_extra(here)
            return ladder_release()
        end
        ladder_hold.target = best.map_pos
        ladder_hold.path = path
        ladder_hold.attackers_choke = best.num_attacking
        ladder_hold.where = you.where()
    end
    local h = ladder_hold
    if you.where() ~= h.where then
        -- Left the level (stairdance, a shaft): the plan was for the old one.
        h.phase = "release-level"
        hold_extra(-1)
        return ladder_release()
    end
    local here = attacking_monster_count_at(const.origin)
    if not positions_equal(qw.map_pos, h.target) then
        -- Still worth the walk? Enemies move and more arrive; if the target
        -- is now no better than where we stand, hold here instead.
        local there = attacking_monster_count_at(
            position_difference(h.target, qw.map_pos))
        h.attackers_choke = there
        if here <= there then
            h.target = util.copy_table(qw.map_pos)
            h.path = {}
        end
    end
    if positions_equal(qw.map_pos, h.target) then
        local acted = hold(false)
        hold_extra(here)
        return acted
    end
    local situation = fight_situation()
    if situation == "none" then
        h.phase = "release-none"
        hold_extra(here)
        return ladder_release()
    end
    -- Walk the planned path; if pushed off it, head for the target directly.
    local next_pos
    for k, cell in ipairs(h.path) do
        if positions_equal(cell, qw.map_pos) then
            next_pos = h.path[k + 1]
            h.left = #h.path - k
        end
    end
    if not next_pos and h.path[1]
            and supdist(position_difference(h.path[1], qw.map_pos)) == 1 then
        next_pos = h.path[1]
        h.left = #h.path
    end
    if not next_pos then
        local r = best_move_towards(h.target)
        next_pos = r and position_sum(qw.map_pos, r.move)
        h.left = r and r.dist or -1
    end
    return en_route(next_pos and position_difference(next_pos, qw.map_pos), here)
end

local function stairs_ahead()
    local my_delay = player_move_delay()
    local best
    local why = { positions = #(qw.flee_positions or {}), nopath = 0, late = 0 }
    for _, pos in ipairs(qw.flee_positions or {}) do
        local r = best_move_towards(pos)
        if not r then
            why.nopath = why.nopath + 1
        else
            -- r.dist counts from the square the move leads to.
            local arrive = (r.dist + 1) * my_delay
            local los = position_difference(pos, qw.map_pos)
            local ok = true
            for _, e in ipairs(qw.enemy_list) do
                if not e:can_melee_player() and enemy_coming(e)
                        and e:melee_move_distance(los) * e:move_delay() < arrive then
                    ok = false
                    break
                end
            end
            if not ok then
                why.late = why.late + 1
            elseif not best or r.dist < best.dist then
                best = r
            end
        end
    end
    if LADDER_HOLD_DEBUG then
        ladder_emit("QWDBG", you.turns(), "stairs positions=" .. why.positions
            .. " nopath=" .. why.nopath .. " late=" .. why.late
            .. " ok=" .. tostring(best ~= nil))
    end
    return best
end

local function stairs_fight(spec)
    local on_stairs = qw.can_flee_upstairs
        and feature_is_upstairs(view.feature_at(0, 0))
    if not ladder_hold or ladder_hold.spec ~= spec then
        ladder_hold = { kind = "stairs_fight", spec = spec, phase = "plan" }
        if fight_situation() == "none" then
            ladder_hold.phase = "release-none"
            hold_extra(-1)
            return ladder_release()
        end
        if on_stairs then
            ladder_hold.target = util.copy_table(qw.map_pos)
        else
            if not qw.can_flee_upstairs or unable_to_move()
                    or dangerous_to_move() then
                ladder_hold.phase = "release-cantmove"
                hold_extra(-1)
                return ladder_release()
            end
            -- qw's own choice of stairs it can flee to; failing that (qw
            -- refuses any flee an enemy could catch up with), the nearest
            -- stairs we reach before any enemy not already on us gets into
            -- reach of them.
            local r = get_flee_move() or stairs_ahead()
            if not r then
                ladder_hold.phase = "release-nostairs"
                hold_extra(-1)
                return ladder_release()
            end
            ladder_hold.target = r.dest
        end
        ladder_hold.attackers_choke = attacking_monster_count_at(
            position_difference(ladder_hold.target, qw.map_pos))
        ladder_hold.where = you.where()
    end
    local h = ladder_hold
    if you.where() ~= h.where then
        -- Took the stairs (stairdance, or leaving ranged attackers behind):
        -- qw handles the new level, and its stairdance brings it back.
        h.phase = "release-level"
        hold_extra(-1)
        return ladder_release()
    end
    local here = attacking_monster_count_at(const.origin)
    if on_stairs then
        local acted = hold(true)
        hold_extra(here)
        return acted
    end
    if fight_situation() == "none" then
        h.phase = "release-none"
        hold_extra(here)
        return ladder_release()
    end
    local r = best_move_towards(h.target) or get_flee_move()
    if r then
        h.left = r.dist
    end
    return en_route(r and r.move, here)
end

-- Forceable primitives. Each respects qw's can_* checks (not its want_*
-- gates) and returns true only if it took an action. They get the spec and
-- the decision index.
ladder_primitives = {
    -- Controls for forks: draw from the game's random numbers and do nothing,
    -- so qw makes its own choice but the dice after it fall differently.
    reroll = function()
        crawl.random2(1000)
        return false
    end,
    reroll2 = function()
        crawl.random2(1000)
        crawl.random2(1000)
        return false
    end,
    berserk = function()
        return can_berserk() and use_ability("Berserk") or false
    end,
    trogs_hand = function()
        return can_trogs_hand() and use_ability("Trog's Hand") or false
    end,
    brothers_in_arms = function()
        return can_brothers_in_arms() and use_ability("Brothers in Arms")
            or false
    end,
    teleport = function()
        return can_teleport() and teleport() or false
    end,
    heal_wounds = function()
        return can_drink_heal_wounds() and drink_by_name("heal wounds") or false
    end,
    flee = function()
        if unable_to_move() or dangerous_to_move() then
            return false
        end
        local result = get_flee_move()
            or best_move_towards_positions(qw.flee_positions, true)
        return result and move_to(result.move) or false
    end,
    stairs_up = function()
        -- qw.can_flee_upstairs is false on D:1 (leaving = ending the game),
        -- in portals, the Abyss, Pan and the Hells.
        if not qw.can_flee_upstairs or unable_to_use_stairs()
                or not feature_is_upstairs(view.feature_at(0, 0)) then
            return false
        end
        go_upstairs(you.status("spiked"))
        return true
    end,
    rest = function()
        if qw.danger_in_los then
            wait_one_turn()
        else
            long_rest()
        end
        return true
    end,
    attack = function()
        return plan_melee() or plan_move_towards_enemy() or false
    end,
    retreat_step = function()
        return plan_tactical_step() or false
    end,
    throw = function()
        return plan_throw() or false
    end,
    choke = choke,
    stairs_fight = stairs_fight,
}

-- The override callback. Replace this function (e.g. from an rc include)
-- with a policy; it gets the decision index and the state table that is
-- also written as the QWS line (nil unless LADDER_STATE_LOG or
-- LADDER_POLICY_STATE is set), and returns nil or a spec:
--   { force = "<primitive>", n = 1 }  or  { veto = { "melee", ... }, n = 1 }
-- The default reads LADDER_OVERRIDES = { [decision] = spec, ... } from the rc.
function ladder_choose(decision, state)
    return LADDER_OVERRIDES and LADDER_OVERRIDES[decision]
end

local function spec_string(spec)
    local parts = {}
    if spec.force then
        parts[#parts + 1] = "force=" .. tostring(spec.force)
    end
    if spec.veto then
        parts[#parts + 1] = "veto=" .. table.concat(spec.veto, ",")
    end
    parts[#parts + 1] = "n=" .. tostring(spec.n or 1)
    return table.concat(parts, " ")
end

local function fmt_value(v)
    local t = type(v)
    if t == "boolean" then
        return v and "1" or "0"
    elseif t == "number" then
        if v ~= v then
            return "nan"
        elseif math.type(v) == "integer" then
            return tostring(v)
        elseif v == math.floor(v) and math.abs(v) < 1e15 then
            return string.format("%d", v)
        end
        return string.format("%.4g", v)
    elseif v == nil then
        return ""
    end
    return (tostring(v):gsub("[\t\n=]", " "))
end

local function inventory_counts()
    local unid_potions, unid_scrolls, throwables = 0, 0, 0
    for item in inventory_iter() do
        local class = item.class(true)
        if class == "potion" and not item.is_identified then
            unid_potions = unid_potions + 1
        elseif class == "scroll" and not item.is_identified then
            unid_scrolls = unid_scrolls + 1
        end
        if item.is_throwable then
            throwables = throwables + item.quantity
        end
    end
    return unid_potions, unid_scrolls, throwables
end

local function flee_distance()
    -- Read only distance maps qw already has: building new ones here would
    -- change qw's own map cache (and with it, play).
    local best = -1
    for _, pos in ipairs(qw.flee_positions or {}) do
        local dmap = distance_maps[hash_position(pos)]
        local d = dmap and dmap.excluded_map
            and dmap.excluded_map[qw.map_pos.x][qw.map_pos.y]
        if d and (best < 0 or d < best) then
            best = d
        end
    end
    return best
end

-- Build the state table. keys is the output order. Every value comes from
-- qw's per-turn data or from pure (memoised or read-only) qw functions, so
-- building it does not change what qw does; run.py checks this by comparing
-- QWACT lines with and without --state-log.
function ladder_build_state()
    local s, keys = {}, {}
    local function put(k, v)
        keys[#keys + 1] = k
        s[k] = v
    end
    local function try(k, f)
        local ok, v = pcall(f)
        put(k, ok and v or "err")
    end

    local hp, mhp = you.hp()
    local mp = you.mp()
    put("turn", you.turns())
    put("branch", you.branch())
    put("depth", you.depth())
    put("xl", you.xl())
    put("hp", hp)
    put("mhp", mhp)
    put("mp", mp)
    put("ac", you.ac())
    put("ev", you.ev())
    put("sh", you.sh())
    put("str", (you.strength()))
    put("dex", (you.dexterity()))
    put("god", you.god())
    put("piety_rank", you.piety_rank())
    put("gold", you.gold())
    put("turns_on_level", you.turns_on_level())

    put("berserk", you.berserk())
    put("berserk_cooldown", you.status("on berserk cooldown"))
    put("exhausted", you.exhausted())
    put("hasted", you.hasted())
    put("slowed", you.slowed())
    put("confused", you.confused())
    put("poisoned", you.poisoned())
    put("poison_survival", you.poison_survival())
    put("corrosion", you.corrosion())
    put("mighty", you.mighty())
    put("regenerating", you.regenerating())
    put("teleporting", you.teleporting())
    put("caught", you.caught() and true or false)
    put("constricted", you.constricted() and true or false)

    -- Threat as qw sees it. nil duration level is what have_*_threat() and
    -- want_to_flee() use; "available" is what want_to_berserk() and
    -- want_to_teleport() use; ignore_buffs is the kiting assessment.
    local a = assess_enemies()
    put("threat", a.threat)
    put("ranged_threat", a.ranged_threat)
    put("enemy_count", a.count)
    put("enemy_move_delay", a.move_delay)
    put("scary_enemy", a.scary_enemy ~= nil)
    local av = assess_enemies(const.duration.available)
    put("threat_avail", av.threat)
    put("scary_enemy_avail", av.scary_enemy ~= nil)
    put("threat_nobuffs", assess_enemies(const.duration.ignore_buffs).threat)
    put("moderate_threat_level", moderate_threat_level())
    put("high_threat_level", high_threat_level())
    put("extreme_threat_level", extreme_threat_level())
    put("danger_in_los", qw.danger_in_los)
    put("immediate_danger", qw.immediate_danger)
    put("position_is_safe", qw.position_is_safe)
    put("position_is_cloudy", qw.position_is_cloudy)

    for i = 1, 5 do
        local e = qw.enemy_list[i]
        local p = "e" .. i .. "_"
        if e then
            put(p .. "name", e:short_name())
            put(p .. "dist", e:distance())
            put(p .. "threat", e:threat())
            put(p .. "ranged", e:is_ranged(true))
            put(p .. "move_delay", e:move_delay())
            put(p .. "damage_level", e:damage_level())
            put(p .. "sleeping", e:is("sleeping") or e:is("dormant"))
            put(p .. "wandering", e:is("wandering"))
            put(p .. "summoned", e:is_summoned())
            put(p .. "hasted", e:is("hasted"))
            put(p .. "berserk", e:is("berserk"))
        else
            put(p .. "name", "")
        end
    end

    put("can_flee_upstairs", qw.can_flee_upstairs)
    put("flee_positions", #(qw.flee_positions or {}))
    put("flee_dist", flee_distance())
    put("on_upstairs", feature_is_upstairs(view.feature_at(0, 0)) and true
        or false)
    put("tactical_reason", qw.tactical_reason or "")
    put("adjacent_floor", adjacent_floor_map
        and adjacent_floor_map[qw.map_pos.x]
        and adjacent_floor_map[qw.map_pos.x][qw.map_pos.y] or -1)
    put("allies_3", check_allies(3))

    put("can_berserk", can_berserk())
    put("can_trogs_hand", can_trogs_hand())
    put("can_brothers_in_arms", can_brothers_in_arms())
    put("can_teleport", can_teleport() and true or false)
    put("can_drink", can_drink())
    put("can_read", can_read())
    put("n_heal_wounds", count_item("potion", "heal wounds"))
    put("n_curing", count_item("potion", "curing"))
    put("n_haste", count_item("potion", "haste"))
    put("n_might", count_item("potion", "might"))
    put("n_teleport", count_item("scroll", "teleportation"))
    put("n_blink", count_item("scroll", "blinking"))
    local up, us, th = inventory_counts()
    put("unid_potion_stacks", up)
    put("unid_scroll_stacks", us)
    put("throwables", th)

    local target = qw.enemy_list[1]
    try("attack_damage", function()
        return target and target:player_attack_damage(1) or 0
    end)
    try("attack_delay", function() return player_attack_delay(1) end)
    put("move_delay", player_move_delay())

    put("explored_level", explored_level(where_branch, where_depth))
    put("goal_status", goal_status or "")
    put("goal_branch", goal_branch or "")
    put("goal_depth", goal_depth or "")
    put("turns_since_full_hp", qw.full_hp_turn and qw.full_hp_turn >= 0
        and you.turns() - qw.full_hp_turn or -1)
    put("weapon_skill_name", c_persist.weapon_skill or "")
    put("sk_weapon", c_persist.weapon_skill
        and you.skill(c_persist.weapon_skill) or 0)
    put("sk_fighting", you.skill("Fighting"))
    put("sk_armour", you.skill("Armour"))
    put("sk_dodging", you.skill("Dodging"))
    put("sk_shields", you.skill("Shields"))

    s._keys = keys
    return s
end

-- qw memoises per turn (qw.turn_memos, qw.attacks, ...) and per monster
-- (Monster.props). Values computed for the state line must not land in those
-- caches: a cached value can outlive a zero-time action within the same turn
-- where qw itself would have recomputed it. So the state is built against
-- empty caches, and qw's own caches are put back afterwards.
local ladder_cache_fields = { "turn_memos", "attacks", "best_equip",
    "want_to_kite", "want_to_kite_step" }

-- Hit chances. qw gets them from monster.info:target_weapon/throw/evoke,
-- which build a crawl attack object, and building one rolls crawl's gameplay
-- RNG (attack::init_attack calls calc_to_hit(true)). Any extra call would
-- change the rest of the game, so the state line never makes one: every hit
-- chance qw itself computes is remembered here (by monster name and item
-- name), and the state uses the latest remembered value instead. A chance qw
-- has not computed yet in this game falls back to the latest one for that
-- item against any monster, else 1; state field acc_exact says whether every
-- lookup found its monster.
local ladder_acc = {}        -- [kind|item|monster] = chance
local ladder_acc_item = {}   -- [kind|item] = latest chance against anything
local ladder_acc_exact = true

for _, kind in ipairs({ "weapon", "throw", "evoke" }) do
    local method = kind .. "_accuracy"
    local orig = Monster[method]
    Monster[method] = function(self, item)
        local v = orig(self, item)
        if item then
            local ik = kind .. "|" .. item.name()
            ladder_acc[ik .. "|" .. self:name()] = v
            ladder_acc_item[ik] = v
        end
        return v
    end
end

local function acc_lookup(kind)
    return function(self, item)
        if not item then
            return 1
        end
        local ik = kind .. "|" .. item.name()
        local v = ladder_acc[ik .. "|" .. self:name()]
        if v then
            return v
        end
        ladder_acc_exact = false
        return ladder_acc_item[ik] or 1
    end
end

local ladder_acc_lookups = {
    weapon_accuracy = acc_lookup("weapon"),
    throw_accuracy = acc_lookup("throw"),
    evoke_accuracy = acc_lookup("evoke"),
}

-- you.status() is also impure in one case: standing in a cloud, its cloud
-- status check rolls crawl's gameplay RNG. Every answer qw gets is
-- remembered; in a cloud the state uses the remembered answer (from this turn
-- if qw asked, else the latest one), and status_exact says whether all were
-- from this turn.
local real_status = you.status
local ladder_status_seen = {}  -- [name] = { turn = t, value = v }
local ladder_status_exact = true
you.status = function(name)
    local v = real_status(name)
    ladder_status_seen[name or ""] = { turn = you.turns(), value = v }
    return v
end

local function safe_status(name)
    if view.cloud_at(0, 0) == nil then
        return real_status(name)
    end
    local seen = ladder_status_seen[name or ""]
    if seen and seen.turn == you.turns() then
        return seen.value
    end
    ladder_status_exact = false
    if seen then
        return seen.value
    end
    return name and false or ""
end

local function with_isolated_caches(f)
    local live_status = you.status
    you.status = safe_status
    ladder_status_exact = true
    local live_acc = {}
    for method, lookup in pairs(ladder_acc_lookups) do
        live_acc[method] = Monster[method]
        Monster[method] = lookup
    end
    ladder_acc_exact = true
    local saved = {}
    for _, k in ipairs(ladder_cache_fields) do
        saved[k] = qw[k]
        qw[k] = nil
    end
    qw.turn_memos = {}
    local monsters = {}
    local r = qw.los_radius or 8
    for x = -r, r do
        local col = qw.monster_map and qw.monster_map[x]
        if col then
            for y = -r, r do
                local m = col[y]
                if m and m.props then
                    monsters[#monsters + 1] = { m, m.props }
                    m.props = {}
                end
            end
        end
    end

    local ok, res = pcall(f)

    for _, entry in ipairs(monsters) do
        entry[1].props = entry[2]
    end
    for _, k in ipairs(ladder_cache_fields) do
        qw[k] = saved[k]
    end
    for method, fn in pairs(live_acc) do
        Monster[method] = fn
    end
    you.status = live_status
    if ok and type(res) == "table" then
        res.acc_exact = ladder_acc_exact
        res._keys[#res._keys + 1] = "acc_exact"
        res.status_exact = ladder_status_exact
        res._keys[#res._keys + 1] = "status_exact"
    end
    if not ok then
        error(res)
    end
    return res
end

local function emit_state(decision, s)
    local parts = { "QWS", tostring(decision) }
    for _, k in ipairs(s._keys) do
        parts[#parts + 1] = k .. "=" .. fmt_value(s[k])
    end
    crawl.stderr(table.concat(parts, "\t"))
end

local ladder_orig_init_cascades = initialize_plan_cascades
function initialize_plan_cascades()
    ladder_orig_init_cascades()
    local turn_cascade = plans.turn
    plans.turn = function()
        -- Cheap progress marker, always on: one line per new level, so a
        -- game that is cut off still shows how deep it got.
        local place = you.where()
        if place ~= ladder_last_place then
            ladder_last_place = place
            ladder_emit("QWPLACE", you.turns(), place, you.xl())
        end

        ladder_decision = ladder_decision + 1
        local decision = ladder_decision

        local state
        if LADDER_STATE_LOG or LADDER_POLICY_STATE then
            state = with_isolated_caches(ladder_build_state)
            if LADDER_STATE_LOG then
                emit_state(decision, state)
            end
        end

        -- A new spec replaces one still running from an earlier decision.
        local spec = ladder_choose(decision, state)
        if spec then
            ladder_active = { spec = spec, left = spec.n or 1 }
        end
        if ladder_active then
            spec = ladder_active.spec
            ladder_active.left = ladder_active.left - 1
            if ladder_active.left <= 0 then
                ladder_active = nil
            end
        end

        local log = LADDER_ACTION_LOG or LADDER_STATE_LOG
        ladder_plan_path = log and {} or nil

        local result, forced
        if spec and spec.force then
            local prim = ladder_primitives[spec.force]
            ladder_ovr_extra = nil
            forced = prim and prim(spec, decision) or false
            if ladder_ovr_extra then
                ladder_emit("QWOVR", decision, spec_string(spec), forced and 1 or 0,
                    ladder_ovr_extra)
            else
                ladder_emit("QWOVR", decision, spec_string(spec), forced and 1 or 0)
            end
            if forced then
                -- Keep any plans the primitive ran through qw's cascades
                -- (choke and stairs_fight run the emergency cascade).
                if ladder_plan_path then
                    local h = ladder_hold or ladder_last_hold
                    if ladder_ovr_extra and h then
                        table.insert(ladder_plan_path, 1, h.phase)
                    end
                    table.insert(ladder_plan_path, 1, "force:" .. spec.force)
                end
                result = true
            elseif ladder_plan_path then
                ladder_plan_path = {}
            end
        end

        if not forced then
            if spec and spec.veto then
                ladder_veto = {}
                for _, name in ipairs(spec.veto) do
                    ladder_veto[name] = true
                end
                ladder_veto_hit = false
            end
            result = turn_cascade()
            if ladder_veto then
                ladder_emit("QWOVR", decision, spec_string(spec),
                    ladder_veto_hit and 1 or 0)
                ladder_veto = nil
            end
        end

        if ladder_plan_path then
            local hp, mhp = you.hp()
            ladder_emit("QWACT", decision, you.turns(), you.where(), hp, mhp,
                table.concat(ladder_plan_path, ">"))
        end
        ladder_plan_path = nil

        -- Stall marker: many decisions without a turn passing means qw is
        -- stuck where its own stuck counter (which counts turns) never fires;
        -- crawl soon stops calling ready() and the game spins until killed.
        -- run.py ends the game when it sees QWSTALL.
        local turns = you.turns()
        if turns ~= ladder_stall_turn then
            ladder_stall_turn = turns
            ladder_stall_count = 0
        else
            ladder_stall_count = ladder_stall_count + 1
            if ladder_stall_count == (LADDER_STALL_DECISIONS or 500) then
                ladder_emit("QWSTALL", decision, turns, you.where())
            end
        end
        return result
    end
end

local ladder_orig_initialize = initialize
function initialize()
    ladder_orig_initialize()
    ladder_emit("QWSTART", you.turns(), you.where(), qw.version)
end

-- The last few game messages, written out with a panic so it can be read
-- without the game (QWMSG lines).
local ladder_messages = {}
local ladder_orig_c_message = c_message
function c_message(text, channel)
    table.insert(ladder_messages, channel .. ": " .. text)
    if #ladder_messages > 8 then
        table.remove(ladder_messages, 1)
    end
    return ladder_orig_c_message(text, channel)
end

function panic(msg)
    ladder_emit("QWPANIC", you.turns(), you.where(), msg)
    for _, m in ipairs(ladder_messages) do
        ladder_emit("QWMSG", you.turns(), m)
    end
    crawl.mpr("<lightred>" .. msg .. "</lightred>")
    if not LADDER_RESUME_ON_PANIC then
        stop()
    end
end

local ladder_orig_ready = ready
function ready()
    local ok, err = pcall(ladder_orig_ready)
    if not ok then
        ladder_errors = ladder_errors + 1
        ladder_emit("QWERR", you.turns(), you.where(), err)
        -- What a person watching would do: drop the dead coroutine and let
        -- qw start a fresh turn (see reset_coroutine() in docs/debugging.md).
        qw.update_coroutine = nil
        qw.abort = false
        -- An error inside turn_update() leaves this turn's state half built;
        -- make the next call redo the whole per-turn update.
        qw.turn_count = -1
        qw.do_dummy_action = nil
        crawl.process_keys(":" .. string.char(27) .. string.char(27))
    end
end
