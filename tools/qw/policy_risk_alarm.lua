-- Death-risk alarm for qw: a template for tools/qw/run.py --policy. Unless its stance is
-- switched on (LADDER_RISK_STANCE, at the end), it takes no action.
--
-- At every qw decision it computes the chance that the character dies within N game turns
-- (docs/risk-model.md), from the state qw decided from, writes it to stderr as a QWRISK line
-- (in the game's state log) and keeps it in ladder_risk for the stance rule. With the stance off,
-- ladder_choose returns only the rc's fixed overrides (LADDER_OVERRIDES), exactly as ladder.lua's
-- default does, so qw plays as it would without this file.
--
-- tools/risk/export_lua.py fills in the model: it replaces the RISK_MODEL marker line below with
-- the trees of a LightGBM model and the tables of tools/risk/dataset.py, and writes a runnable
-- policy, e.g. runs/risk/N50-zk/policy_risk_alarm.lua. This file alone has no model.
--
-- The features are tools/risk/dataset.py's qw_row, computed from the values as the QWS state
-- line logs them (floats to 4 significant digits, flags as 0/1) and rounded to float32 as the
-- dataset stores them, so the probability here equals the one Python computes from the log.
--
-- Lines on stderr (tab-separated):
--   QWRISK  decision turn probability raw-score alarm(0/1)
--   QWRISKF decision feature values in dataset order   (only with LADDER_RISK_FEATURES = true)
--   QWRISKERR decision error                           (the computation failed; qw carries on)
--
-- For a stance rule: ladder_risk.p, ladder_risk.raw, ladder_risk.alarm_on (p >= threshold),
-- ladder_risk.decision, ladder_risk.threshold. Set ladder_risk.threshold to move the alarm.
-- Cost: about 13,000 Lua VM instructions (0.05 ms) a decision; crawl's Lua throttle is off
-- outside DGAMELAUNCH builds, and would allow 50,000 between sleeps.
--
-- The stance (the end of this file) is off unless LADDER_RISK_STANCE is set: then the policy acts
-- on the probability (see there). export_lua.py --stance writes variants that set it.
-- (The rc ends a Lua block at a line whose first '>' is its last character: no line here may.)

-- @RISK_MODEL@

do
    local M = ladder_risk_model
    local FEATURES = M.features
    local NF = #FEATURES
    local F = {}
    for i, name in ipairs(FEATURES) do
        F[name] = i
    end
    local nan = 0 / 0
    local huge = math.huge
    local mtype = math.type

    -- float32 rounding, as numpy stores a row
    local spack, sunpack = string.pack, string.unpack
    local function f32(x)
        return (sunpack("f", spack("f", x)))
    end

    -- A state value as tools/qw/log.py reads it back from the QWS line (ladder.lua fmt_value,
    -- then log._value): nil for no value or NaN, a number, or a string.
    local function logged(v)
        local t = type(v)
        if t == "boolean" then
            return v and 1 or 0
        elseif t == "number" then
            if v ~= v then
                return nil
            elseif mtype(v) == "integer" or v == huge or v == -huge then
                return v
            elseif v == math.floor(v) and math.abs(v) < 1e15 then
                return v
            end
            return tonumber(string.format("%.4g", v))
        elseif v == nil then
            return nil
        end
        local s = tostring(v):gsub("[\t\n=]", " ")
        if s == "" then
            return nil
        end
        return s
    end

    -- dataset._num: a number, else the default
    local function num(v, default)
        v = logged(v)
        if type(v) == "number" then
            return v
        elseif type(v) == "string" and v:match("^%s*[-+]?%d+%.?%d*%s*$") then
            return tonumber(v)
        end
        return default or 0.0
    end

    -- Python 3.12's sum() from 0: integers add exactly up to the first float, then floats use
    -- Neumaier's compensated sum (and integers after it add plainly).
    local function pysum(xs, n)
        local isum, fsum, c, float = 0, 0.0, 0.0, false
        for i = 1, n do
            local x = xs[i]
            if not float then
                if mtype(x) == "integer" then
                    isum = isum + x
                else
                    fsum = isum + x
                    float = true
                end
            elseif mtype(x) == "float" then
                local t = fsum + x
                if math.abs(fsum) >= math.abs(x) then
                    c = c + ((fsum - t) + x)
                else
                    c = c + ((x - t) + fsum)
                end
                fsum = t
            else
                fsum = fsum + x
            end
        end
        if not float then
            return isum
        end
        if c ~= 0 and c == c and c ~= huge and c ~= -huge then
            fsum = fsum + c
        end
        return fsum
    end

    ---------------------------------------
    -- dataset.MonsterBook

    local book = M.monsters
    local DERIVED = { zombie = true, skeleton = true, simulacrum = true }
    local cache = {}

    local function join(words, i, j)
        return table.concat(words, " ", i, j)
    end

    local function strip_prefix(s, p)
        if s:sub(1, #p) == p then
            return s:sub(#p + 1)
        end
        return s
    end

    local function find(key)
        for _, k in ipairs({ key, strip_prefix(key, "the "), strip_prefix(key, "a "),
                strip_prefix(key, "an ") }) do
            if book[k] then
                return book[k]
            end
        end
        local words = {}
        for w in key:gmatch("%S+") do
            words[#words + 1] = w
        end
        local n = #words
        if n > 0 and words[1] == "dancing" then
            return book["dancing weapon"]
        end
        if n > 1 and words[n] == "beast" then
            return book["mutant beast"]
        end
        if n > 0 and words[1] == "spectral" and book[join(words, 2, n)] then
            return book[join(words, 2, n)]
        end
        if n > 0 and DERIVED[words[n]] and book[join(words, 1, n - 1)] then
            return book[join(words, 1, n - 1)]
        end
        for i = 2, n do
            local k = join(words, i, n)
            if book[k] then
                return book[k]
            end
        end
        for i = n - 1, 1, -1 do
            local k = join(words, 1, i)
            if book[k] then
                return book[k]
            end
        end
        if key:sub(-1) == "s" and book[key:sub(1, -2)] then
            return book[key:sub(1, -2)]
        end
        return nil
    end

    local function lookup(name)
        local key = (name or ""):gsub("^%s+", ""):gsub("%s+$", ""):lower()
        local hit = cache[key]
        if hit == nil then
            hit = find(key) or false
            cache[key] = hit
        end
        return hit or nil
    end

    ---------------------------------------
    -- dataset.qw_row

    local function put(row, name, v)
        if v == true then
            v = 1
        elseif v == false then
            v = 0
        end
        row[F[name]] = v
    end

    local function monster_features(row, mons, hp, player_speed)
        -- mons: { {name, dist}, ... } in the state's order; a stable sort by distance
        for i = 2, #mons do
            local m, j = mons[i], i - 1
            while j >= 1 and mons[j][2] > m[2] do
                mons[j + 1] = mons[j]
                j = j - 1
            end
            mons[j + 1] = m
        end
        while #mons > M.nearest do
            mons[#mons] = nil
        end
        local unknown, ks = 0, {}
        for _, m in ipairs(mons) do
            local k = lookup(m[1])
            if k then
                ks[#ks + 1] = { k, m[2] }
            else
                unknown = unknown + 1
            end
        end
        local nk = #ks
        local exp, hd, hps, rate, near = {}, {}, {}, {}, {}
        local exp_max, hd_max, rate_max = 0, 0, 0
        local fast, faster, ranged = 0, 0, 0
        local tags = {}
        for i, kd in ipairs(ks) do
            local k, d = kd[1], kd[2]
            exp[i], hd[i], hps[i] = k.exp, k.hd, k.hp
            rate[i] = k.dmg * k.speed / 10
            if d <= 2 then
                near[#near + 1] = rate[i]
            end
            if i == 1 or k.exp > exp_max then
                exp_max = k.exp
            end
            if i == 1 or k.hd > hd_max then
                hd_max = k.hd
            end
            if i == 1 or rate[i] > rate_max then
                rate_max = rate[i]
            end
            if k.speed > M.player_speed then
                fast = fast + 1
            end
            if k.speed > player_speed then
                faster = faster + 1
            end
            if k.ranged then
                ranged = ranged + 1
            end
            for t in pairs(k.tags) do
                tags[t] = (tags[t] or 0) + 1
            end
        end
        local adjacent, within2, nearest = 0, 0, 9
        for i, m in ipairs(mons) do
            if m[2] <= 1 then
                adjacent = adjacent + 1
            end
            if m[2] <= 2 then
                within2 = within2 + 1
            end
            if i == 1 or m[2] < nearest then
                nearest = m[2]
            end
        end
        local hp_sum = pysum(hps, nk)
        local near_sum = pysum(near, #near)
        local hp1 = hp >= 1 and hp or 1
        put(row, "mon_n", #mons)
        put(row, "mon_unknown", unknown)
        put(row, "mon_exp_sum", pysum(exp, nk))
        put(row, "mon_exp_max", exp_max)
        put(row, "mon_hd_sum", pysum(hd, nk))
        put(row, "mon_hd_max", hd_max)
        put(row, "mon_hp_sum", hp_sum)
        put(row, "mon_dmg_sum", pysum(rate, nk))
        put(row, "mon_dmg_max", rate_max)
        put(row, "mon_dmg_near", near_sum)
        put(row, "mon_dmg_near_over_hp", near_sum / hp1)
        -- dataset divides the float32 sum already stored in the row
        put(row, "mon_hp_over_hp", f32(hp_sum) / hp1)
        put(row, "mon_adjacent", adjacent)
        put(row, "mon_within2", within2)
        put(row, "mon_nearest", nearest)
        put(row, "mon_fast", fast)
        put(row, "mon_faster_eff", faster)
        for _, t in ipairs(M.mon_tags) do
            put(row, "mon_" .. t:gsub(" ", "_"), tags[t] or 0)
        end
        put(row, "mon_ranged_spells", ranged)
    end

    local function place_features(row, branch, depth)
        local br = M.place_short[branch] or branch
        local absdepth = (M.branch_base[br] or M.default_base) + depth
        put(row, "absdepth", absdepth)
        local dungeon, lair, rune = br == "D", br == "Lair", M.rune_branches[br] == true
        local orc = br == "Orc" or br == "Elf"
        local late = br == "Depths" or br == "Crypt" or br == "Tomb" or br == "Zot"
        local abyss = br == "Abyss"
        put(row, "br_dungeon", dungeon)
        put(row, "br_lair", lair)
        put(row, "br_rune", rune)
        put(row, "br_orc", orc)
        put(row, "br_late", late)
        put(row, "br_abyss", abyss)
        put(row, "br_other", not (dungeon or lair or rune or orc or late or abyss))
        return absdepth, rune
    end

    local function character(row, hp, mhp, ps, berserk)
        hp = logged(hp) or 0
        hp = hp + 0.0
        mhp = logged(mhp) or 1
        mhp = (mhp >= 1 and mhp or 1) + 0.0
        ps = logged(ps)
        ps = ps == nil and hp or ps + 0.0
        put(row, "hp", hp)
        put(row, "mhp", mhp)
        put(row, "hp_frac", hp / mhp)
        put(row, "mhp_log", math.log(1 + mhp))
        local base = berserk and mhp * 2 / 3 or mhp
        put(row, "poison_frac", math.max(hp - ps, 0) / base)
        put(row, "poison_survival_frac", ps / base)
        put(row, "after_rage_frac", (berserk and ps - hp / 3 or ps) / base)
    end

    -- dataset.History: past-only features from this game's earlier decisions
    local hist = { t = {}, h = {}, first = 1, last = 0, last_full = nil }

    local function history(row, turn, hp_frac)
        local H = hist
        while H.first <= H.last and H.t[H.first] < turn - 20 do
            H.t[H.first], H.h[H.first] = nil, nil
            H.first = H.first + 1
        end
        local n = H.last - H.first + 1
        if n > 0 then
            put(row, "hist_dhp", f32(hp_frac - H.h[H.last]))
            put(row, "hist_dt", math.min(turn - H.t[H.last], 1000))
        else
            put(row, "hist_dhp", 0.0)
            put(row, "hist_dt", 1000)
        end
        local lo, hi = hp_frac, nil
        for i = H.first, H.last do
            local h = H.h[i]
            if h < lo then
                lo = h
            end
            if H.t[i] >= turn - 10 and (hi == nil or h > hi) then
                hi = h
            end
        end
        put(row, "hist_min_hp_20", lo)
        put(row, "hist_drop_10", math.max(f32((hi or hp_frac) - hp_frac), 0.0))
        put(row, "hist_rows_20", n)
        if hp_frac >= 0.999 then
            H.last_full = turn
        end
        put(row, "hist_since_full", H.last_full and math.min(turn - H.last_full, 1000) or 1000)
        H.last = H.last + 1
        H.t[H.last], H.h[H.last] = turn, hp_frac
    end

    local function on(s, k)
        return num(s[k]) > 0
    end

    -- The feature row (1-based, dataset order), NaN where qw has no value.
    local function qw_row(s)
        local row = {}
        for i = 1, NF do
            row[i] = nan
        end
        local berserk = on(s, "berserk")
        put(row, "is_qw", 1)
        character(row, s.hp, s.mhp, s.poison_survival, berserk)
        for _, k in ipairs({ "xl", "ac", "ev", "sh", "str", "dex" }) do
            put(row, k, num(s[k]))
        end
        local branch = logged(s.branch)
        if type(branch) ~= "string" then
            branch = "D"
        end
        local depth = num(s.depth)
        depth = depth >= 0 and math.floor(depth) or math.ceil(depth)
        local absdepth = place_features(row, branch, depth)
        put(row, "xl_minus_depth", num(s.xl) - absdepth)
        local slowed, hasted = on(s, "slowed"), on(s, "hasted")
        put(row, "st_berserk", berserk)
        put(row, "st_berserk_after", on(s, "berserk_cooldown") or on(s, "exhausted"))
        put(row, "st_slowed", slowed)
        put(row, "st_hasted", hasted)
        put(row, "st_confused", on(s, "confused"))
        put(row, "st_poisoned", on(s, "poisoned"))
        put(row, "st_corroded", on(s, "corrosion"))
        put(row, "st_might", on(s, "mighty"))
        put(row, "st_held", on(s, "caught"))
        put(row, "st_constricted", on(s, "constricted"))
        put(row, "st_teleporting", on(s, "teleporting"))
        put(row, "heal_potions", num(s.n_heal_wounds) + num(s.n_curing))
        put(row, "teleports", num(s.n_teleport))
        put(row, "has_unknown_potion", on(s, "unid_potion_stacks"))
        put(row, "has_unknown_scroll", on(s, "unid_scroll_stacks"))
        put(row, "trog", logged(s.god) == "Trog")
        put(row, "piety", num(s.piety_rank))
        put(row, "level_turns", num(s.turns_on_level))
        put(row, "on_upstairs", num(s.on_upstairs))
        put(row, "open_neighbors", num(s.adjacent_floor))
        put(row, "n_hostiles", num(s.enemy_count))

        -- the enemies as log.parse_state gathers them: e1.. up to the first without a name
        local mons, sleeping, ranged, hastedm, dlevel = {}, 0, 0, 0, 0
        for i = 1, 5 do
            local p = "e" .. i .. "_"
            local name = logged(s[p .. "name"])
            if type(name) ~= "string" then
                break
            end
            mons[#mons + 1] = { name, num(s[p .. "dist"]) }
            if on(s, p .. "sleeping") then
                sleeping = sleeping + 1
            end
            if on(s, p .. "ranged") then
                ranged = ranged + 1
            end
            if on(s, p .. "hasted") then
                hastedm = hastedm + 1
            end
            local dl = num(s[p .. "damage_level"])
            if i == 1 or dl > dlevel then
                dlevel = dl
            end
        end
        local speed = M.player_speed * ((hasted or berserk) and 1.5 or 1)
            * (slowed and 2 / 3 or 1)
        local hp = num(s.hp)
        monster_features(row, mons, hp, speed)

        local high = math.max(num(s.high_threat_level), 1.0)
        put(row, "q_threat", num(s.threat))
        put(row, "q_threat_rel", num(s.threat) / high)
        put(row, "q_ranged_threat", num(s.ranged_threat))
        put(row, "q_threat_avail_rel", num(s.threat_avail) / high)
        put(row, "q_scary", num(s.scary_enemy))
        put(row, "q_immediate", num(s.immediate_danger))
        put(row, "q_safe", num(s.position_is_safe))
        put(row, "q_cloudy", num(s.position_is_cloudy))
        put(row, "q_danger_los", num(s.danger_in_los))
        put(row, "q_attack_damage", num(s.attack_damage))
        local fd = num(s.flee_dist, -1)
        put(row, "q_flee_dist", fd >= 0 and fd or 99)
        put(row, "q_can_flee_up", num(s.can_flee_upstairs))
        put(row, "q_allies", num(s.allies_3))
        put(row, "q_sk_fighting", num(s.sk_fighting))
        put(row, "q_n_haste", num(s.n_haste))
        put(row, "q_n_might", num(s.n_might))
        put(row, "q_can_berserk", num(s.can_berserk))
        put(row, "q_mon_sleeping", sleeping)
        put(row, "q_mon_ranged", ranged)
        put(row, "q_mon_hasted", hastedm)
        put(row, "q_mon_damage_level", dlevel)
        for i = 1, NF do
            row[i] = f32(row[i])
        end
        history(row, num(s.turn), row[F.hp_frac])
        return row
    end

    ---------------------------------------
    -- the trees (LightGBM: raw score = the trees' sum in order, p = sigmoid)

    local trees = M.trees
    local function score(row)
        local raw = 0.0
        for i = 1, #trees do
            raw = raw + trees[i](row)
        end
        return raw, 1 / (1 + math.exp(-M.sigmoid * raw))
    end

    ---------------------------------------
    -- the policy

    local function fmt(v)
        if v ~= v then
            return "nan"
        end
        return string.format("%.9g", v)
    end

    ladder_risk = {
        model = M.source,
        horizon = M.horizon,
        threshold = M.threshold,
        p = nil,
        raw = nil,
        alarm_on = false,
        decision = nil,
        qw_row = qw_row,
        score = score,
        pysum = pysum,
    }

    function ladder_risk.step(decision, state)
        local row = qw_row(state)
        local raw, p = score(row)
        local R = ladder_risk
        R.p, R.raw, R.decision = p, raw, decision
        R.alarm_on = p >= R.threshold
        crawl.stderr(string.format("QWRISK\t%d\t%s\t%.17g\t%.17g\t%d", decision,
            tostring(num(state.turn)), p, raw, R.alarm_on and 1 or 0))
        if LADDER_RISK_FEATURES then
            local parts = { "QWRISKF", tostring(decision) }
            for i = 1, NF do
                parts[#parts + 1] = fmt(row[i])
            end
            crawl.stderr(table.concat(parts, "\t"))
        end
        return p
    end

    ---------------------------------------
    -- The stance: off unless LADDER_RISK_STANCE is set. With it off, ladder_choose below returns
    -- exactly what it returns without this section.
    --
    -- LADDER_RISK_STANCE = "teleport" forces ladder.lua's teleport primitive, qw's own
    -- `can_teleport() and teleport()` (read a scroll of teleportation, with qw's checks), through
    -- the override mechanism fork runs use, at a decision where all of these hold:
    --   - p >= the stance threshold for the scrolls held. LADDER_RISK_STANCE_THRESHOLD is a number,
    --     or a list { with 1 scroll, with 2, with 3 or more } (counted above the reserve); unset,
    --     it is the alarm threshold.
    --   - the state says a scroll can be read now: can_teleport, not already teleporting, and more
    --     than LADDER_RISK_STANCE_RESERVE (default 0) scrolls of teleportation held.
    --   - at least LADDER_RISK_STANCE_COOLDOWN game turns (default 20, at least 1) have passed since
    --     the stance last fired, whether or not that read happened.
    -- A fixed override for the decision (LADDER_OVERRIDES) comes first. If the primitive cannot
    -- act, qw's own cascade decides that decision, as for any forced spec.
    -- Each firing writes, once the primitive has run:
    --   QWSTANCE decision turn probability action acted(0/1)

    local stance = { last_turn = nil, fired = 0, acted = 0, wrapped = false }
    ladder_risk.stance = stance

    local function stance_threshold(n)
        local t = LADDER_RISK_STANCE_THRESHOLD
        if type(t) == "table" then
            return t[math.max(1, math.min(n, #t))]
        end
        return t or ladder_risk.threshold
    end

    local function stance_log(s, acted)
        crawl.stderr(string.format("QWSTANCE\t%d\t%s\t%.17g\t%s\t%s", s.decision, tostring(s.turn),
            s.p, s.action, acted))
    end

    -- Wrap the primitive once, so that a firing is logged with what it did; any other spec
    -- (a fork's override) passes through unchanged.
    local function stance_wrap(action)
        if stance.wrapped or type(ladder_primitives) ~= "table"
                or type(ladder_primitives[action]) ~= "function" then
            return stance.wrapped
        end
        local prim = ladder_primitives[action]
        ladder_primitives[action] = function(spec, decision)
            local acted = prim(spec, decision)
            if type(spec) == "table" and spec.stance then
                if acted then
                    stance.acted = stance.acted + 1
                end
                stance_log(spec.stance, acted and 1 or 0)
            end
            return acted
        end
        stance.wrapped = true
        return true
    end

    function ladder_risk.stance_choose(decision, state)
        local action = LADDER_RISK_STANCE
        if action ~= "teleport" then
            return nil
        end
        local R = ladder_risk
        if R.p == nil or R.decision ~= decision then
            return nil
        end
        local reserve = LADDER_RISK_STANCE_RESERVE or 0
        local n = num(state.n_teleport)
        if n <= reserve or num(state.can_teleport) <= 0 or num(state.teleporting) > 0 then
            return nil
        end
        if R.p < stance_threshold(n - reserve) then
            return nil
        end
        local turn = num(state.turn)
        local cooldown = math.max(LADDER_RISK_STANCE_COOLDOWN or 20, 1)
        if stance.last_turn and turn - stance.last_turn < cooldown then
            return nil
        end
        stance.last_turn = turn
        stance.fired = stance.fired + 1
        local s = { decision = decision, turn = turn, p = R.p, action = action }
        if not stance_wrap(action) then
            stance_log(s, "-")   -- no ladder.lua primitives to wrap (outside qw)
        end
        return { force = action, n = 1, stance = s }
    end

    function ladder_choose(decision, state)
        local fixed = LADDER_OVERRIDES and LADDER_OVERRIDES[decision]
        if state then
            local ok, err = pcall(ladder_risk.step, decision, state)
            if not ok then
                ladder_risk.p, ladder_risk.alarm_on = nil, false
                crawl.stderr("QWRISKERR\t" .. tostring(decision) .. "\t"
                    .. tostring(err):gsub("[\t\n]", " "))
            elseif LADDER_RISK_STANCE and not fixed then
                local ok2, spec = pcall(ladder_risk.stance_choose, decision, state)
                if not ok2 then
                    crawl.stderr("QWSTANCEERR\t" .. tostring(decision) .. "\t"
                        .. tostring(spec):gsub("[\t\n]", " "))
                elseif spec then
                    return spec
                end
            end
        end
        return fixed
    end
end
