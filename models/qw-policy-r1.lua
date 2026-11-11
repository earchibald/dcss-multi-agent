-- qw override policy learned from forks (tools/qw/learn.py). Generated: do not edit.
-- 2897 forks, ridge 10.0, margin 0.1, held-out gain +0.0446
local MARGIN = 0.1
local GAP = 4
local function n(v)
    if v == true then return 1 end
    if v == nil or v == false or v == "" then return 0 end
    if type(v) ~= "number" or v ~= v then return 0 end
    return v
end
local function enemies(s)
    local e = { adjacent = 0, nearest = 7, max_threat = 0, any_ranged = 0, any_fast = 0 }
    for i = 1, 5 do
        local name = s["e" .. i .. "_name"]
        if name ~= nil and name ~= "" then
            local d = n(s["e" .. i .. "_dist"])
            if d <= 1 then e.adjacent = e.adjacent + 1 end
            if d < e.nearest then e.nearest = d end
            e.max_threat = math.max(e.max_threat, n(s["e" .. i .. "_threat"]))
            if n(s["e" .. i .. "_ranged"]) > 0 then e.any_ranged = 1 end
            local md = n(s["e" .. i .. "_move_delay"])
            if md > 0 and md < 10 then e.any_fast = 1 end
        end
    end
    return e
end

local function features(s, kind)
    local high = math.max(1, n(s.high_threat_level))
    local e = enemies(s)
    return {
        1,  -- bias
        (kind == 'hp70') and 1 or 0,  -- kind_hp70
        (kind == 'hp40') and 1 or 0,  -- kind_hp40
        s.hp / math.max(1, s.mhp),  -- hp_frac
        s.xl / 10,  -- xl
        s.depth / 10,  -- depth
        (s.branch == 'D') and 1 or 0,  -- in_dungeon
        math.min(3, n(s.threat) / high),  -- threat
        math.min(3, n(s.threat_avail) / high),  -- threat_avail
        math.min(3, n(s.ranged_threat) / high),  -- ranged_threat
        math.min(8, n(s.enemy_count)) / 4,  -- enemy_count
        n(s.scary_enemy),  -- scary
        n(s.immediate_danger),  -- immediate
        e.adjacent / 3,  -- adjacent
        e.nearest / 7,  -- nearest
        math.min(3, e.max_threat / high),  -- max_threat
        e.any_ranged,  -- any_ranged
        e.any_fast,  -- any_fast
        (n(s.flee_dist) >= 0) and 1 or 0,  -- has_flee
        (n(s.flee_dist) >= 0) and math.min(30, n(s.flee_dist)) / 30 or 1,  -- flee_dist
        n(s.on_upstairs),  -- on_upstairs
        n(s.adjacent_floor) / 8,  -- open_ground
        math.max(n(s.berserk_cooldown), n(s.exhausted)),  -- tired
        n(s.berserk),  -- berserk
        (n(s.n_heal_wounds) > 0) and 1 or 0,  -- has_heal
        (n(s.n_teleport) > 0) and 1 or 0,  -- has_teleport
        n(s.piety_rank) / 6,  -- piety
        math.min(40, n(s.attack_damage)) / 20,  -- damage
        n(s.ac) / 20,  -- ac
        n(s.ev) / 20,  -- ev
        n(s.poisoned),  -- poisoned
    }
end

-- name, spec, usable(s), weights (one per feature, in order)
local OPTIONS = {
    { "berserk", { force = "berserk" },
      function(s) return n(s.can_berserk) > 0 and n(s.berserk) == 0 end,
      { -0.28611, 0.04339, -0.07103, 0.17121, 0.1091, 0.05089, -0.11534, -0.07507, 0.00637, -0.03919, 0.05178, 0.07484, 0.05562, -0.03996, -0.03894, -0.03966, 0.03866, -0.03598, 0.10904, -0.01831, -0.0074, 0.07727, 0.0, 0.0, 0.09608, -0.05014, -0.04642, -0.05031, 0.08007, 0.02566, 0.06531 } },
    { "no_berserk", { veto = { "berserk" }, n = 8 },
      function(s) return n(s.can_berserk) > 0 and n(s.berserk) == 0 end,
      { 0.13372, 0.05252, 0.08054, -0.02517, 0.0704, -0.01363, -0.04883, -0.13007, -0.05359, -0.08162, 0.04907, 0.21962, -0.04316, -0.17949, -0.06317, -0.12649, -0.02299, 0.01213, -0.01298, -0.16999, -0.10154, 0.14665, 0.0, 0.0, 0.06469, -0.30506, -0.03619, -0.01658, 0.05794, 0.00046, 0.00911 } },
    { "teleport", { force = "teleport" },
      function(s) return n(s.can_teleport) > 0 and n(s.teleporting) == 0 end,
      { 0.08278, -0.00206, -0.06102, 0.08183, -0.04839, 0.00209, 0.00216, -0.05037, -0.02084, 0.00928, -0.01665, 0.11949, -0.07345, 0.09855, 0.05426, -0.00819, -0.00259, -0.08904, -0.00882, -0.05069, -0.01985, -0.01763, 0.0, 0.0, -0.03918, 0.0, -0.08682, 0.00245, 0.04661, 0.00562, -0.03854 } },
    { "heal_wounds", { force = "heal_wounds" },
      function(s) return n(s.n_heal_wounds) > 0 and n(s.can_drink) > 0 and s.hp < 0.7 * s.mhp end,
      { 0.15842, 0.19553, -0.19553, 0.07978, -0.04011, -0.02261, 0.0, -0.09445, -0.02871, -0.12247, 0.02498, 0.05505, 0.0, -0.12092, -0.0, 0.01204, -0.03022, -0.02446, -0.07915, -0.04517, 0.05802, 0.06543, 0.0, 0.0, 0.0, -0.17422, -0.04974, -0.00541, -0.02219, 0.01217, -0.0972 } },
    { "flee", { force = "flee", n = 12 },
      function(s) return n(s.can_flee_upstairs) > 0 and n(s.flee_positions) > 0 and n(s.berserk) == 0 end,
      { -0.27358, 0.07137, 0.03182, 0.00473, -0.08352, -0.04902, -0.0, -0.10112, 0.0015, -0.17291, 0.35075, 0.05949, -0.07363, -0.18955, 0.1063, -0.1514, 0.05616, 0.13634, 0.20357, -0.01679, 0.04312, 0.14586, -0.00976, 0.0, -0.04036, 0.04285, -0.06849, -0.07015, -0.02205, -0.01376, -0.09609 } },
    { "stairs_up", { force = "stairs_up" },
      function(s) return n(s.on_upstairs) > 0 and n(s.can_flee_upstairs) > 0 end,
      { -0.02279, 0.09295, -0.02089, -0.00553, -0.09398, -0.02447, 0.0, -0.01642, -0.00168, 0.0322, 0.1145, 0.14512, -0.00994, -0.06398, 0.11519, 0.01396, 0.14793, 0.03829, -0.05307, 0.05307, 0.0, 0.0244, 0.0, 0.00988, -0.06061, -0.03051, -0.00845, -0.00517, -0.03522, -0.01005, 0.00988 } },
    { "trogs_hand", { force = "trogs_hand" },
      function(s) return n(s.can_trogs_hand) > 0 and n(s.regenerating) == 0 end,
      { 0.11095, 0.05911, -0.05016, 0.00155, -0.05104, -0.03626, 0.0015, -0.06974, -0.01679, -0.0626, 0.11363, 0.16383, -0.09536, -0.06377, 0.05856, -0.08504, 0.05371, -0.08612, 0.08033, -0.04591, -0.07745, 0.03486, 0.01539, 0.0, 0.03935, -0.07761, 0.03213, -0.02178, -0.00473, 0.04589, -0.10131 } },
    { "retreat", { force = "retreat_step", n = 3 },
      function(s) return n(s.berserk) == 0 end,
      { -0.25631, 0.02655, 0.11412, -0.09548, 0.195, 0.18358, 0.01815, 0.10037, 0.04719, 0.0516, -0.00138, 0.05057, -0.09883, -0.11005, -0.02533, 0.04089, 0.0455, 0.028, 0.02481, 0.02023, 0.11559, 0.04509, 0.00712, 0.0, 0.14123, -0.13303, 0.11263, -0.08075, 0.16463, -0.0336, 0.11788 } },
    { "no_melee", { veto = { "melee" }, n = 3 },
      function(s) return n(s.berserk) == 0 end,
      { -0.31418, -0.0454, 0.0011, 0.05204, 0.10819, 0.10721, -0.00424, -0.08232, -0.05687, 0.17876, -0.02815, 0.01723, 0.09904, -0.04714, -0.30167, -0.10278, -0.02657, -0.01257, 0.09335, 0.11177, 0.00285, 0.1839, 0.00921, 0.0, -0.10654, -0.04614, 0.08339, -0.08406, 0.05782, -0.16528, -0.00657 } },
}

local quiet, started, done70, done40 = 0, false, false, false

local function moment(s)
    if n(s.danger_in_los) == 0 then
        quiet = quiet + 1
        if quiet > GAP then started, done70, done40 = false, false, false end
        return nil
    end
    quiet = 0
    if not (n(s.threat) > 0 or n(s.immediate_danger) > 0) then return nil end
    local frac = s.hp / math.max(1, s.mhp)
    local kind = nil
    if not started then
        kind, started = "start", true
        if frac < 0.7 then done70 = true end
        if frac < 0.4 then done40 = true end
    elseif not done70 and frac < 0.7 then
        kind, done70 = "hp70", true
        if frac < 0.4 then done40 = true end
    elseif not done40 and frac < 0.4 then
        kind, done40 = "hp40", true
    end
    return kind
end

function ladder_choose(decision, s)
    local fixed = LADDER_OVERRIDES and LADDER_OVERRIDES[decision]
    if fixed or not s then return fixed end
    local kind = moment(s)
    if not kind then return nil end
    local x = features(s, kind)
    local best, best_score = nil, MARGIN
    for _, opt in ipairs(OPTIONS) do
        if opt[3](s) then
            local score = 0
            for i = 1, #x do score = score + opt[4][i] * x[i] end
            if score > best_score then best, best_score = opt, score end
        end
    end
    if best then
        crawl.stderr("QWPOL\t" .. decision .. "\t" .. kind .. "\t" .. best[1] .. "\t" ..
            string.format("%.3f", best_score))
        return best[2]
    end
    return nil
end
