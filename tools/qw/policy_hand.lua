-- Rule policy for qw (tools/qw/run.py --policy): use Trog's Hand at the start of every
-- serious fight, not only against qw's list of casters. The first round of forks
-- (tools/qw/learn.py) found this the one option that beat qw's own choice.

local GAP = 4
local quiet, started = 0, false

local function on(v)
    return v == true or (type(v) == "number" and v > 0)
end

function ladder_choose(decision, s)
    local fixed = LADDER_OVERRIDES and LADDER_OVERRIDES[decision]
    if fixed or not s then return fixed end
    if not on(s.danger_in_los) then
        quiet = quiet + 1
        if quiet > GAP then started = false end
        return nil
    end
    quiet = 0
    if started or not (on(s.threat) or on(s.immediate_danger)) then return nil end
    started = true
    if on(s.can_trogs_hand) and not on(s.regenerating) then
        return { force = "trogs_hand" }
    end
    return nil
end
