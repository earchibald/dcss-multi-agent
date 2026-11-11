-- Example override policy for qw (tools/qw/ladder.lua), loaded with
--   uv run python tools/qw/run.py --seeds ... --policy tools/qw/policy_example.lua
-- run.py inlines this file into each game's rc after qw-ladder.rc, so this
-- ladder_choose() replaces the default one. It is called once per qw decision,
-- before qw's own cascade, with the decision index and the state table that
-- is also written as the QWS line (the same keys; flags are booleans here).
-- Return nil to let qw decide, or a spec:
--   { force = "teleport" }                   try a primitive first
--   { veto = { "melee", "berserk" }, n = 3 } skip plans for 3 decisions
--
-- This one is a linear score over a few state values, standing in for a
-- learned model: weights would come from training, here they are hand-set.

local W = {
    bias = -1.0,
    hp_frac = -6.0,       -- hp / mhp
    threat_ratio = 1.5,   -- threat / high_threat_level
    adjacent = 0.5,       -- enemies at distance 1
}

local function feature(state)
    local adj = 0
    for i = 1, 5 do
        if state["e" .. i .. "_name"] ~= "" and state["e" .. i .. "_dist"] == 1 then
            adj = adj + 1
        end
    end
    return {
        bias = 1,
        hp_frac = state.hp / math.max(1, state.mhp),
        threat_ratio = state.threat / math.max(1, state.high_threat_level),
        adjacent = adj,
    }
end

function ladder_choose(decision, state)
    local fixed = LADDER_OVERRIDES and LADDER_OVERRIDES[decision]
    if fixed or not state or not state.danger_in_los then
        return fixed
    end
    -- A fixed key order (not pairs()) keeps the float sum, and so the
    -- game, the same on every replay.
    local f, score = feature(state), 0
    for _, k in ipairs({ "bias", "hp_frac", "threat_ratio", "adjacent" }) do
        score = score + W[k] * f[k]
    end
    if score > 0 and state.can_teleport and not state.teleporting then
        return { force = "teleport" }
    end
    return nil
end
