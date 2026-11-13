"""The pacing variants of tools/qw/variants.py, run against stubs of the qw functions they wrap.

Needs a `lua` interpreter on PATH (skipped otherwise); qw itself is not involved.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "qw"))
import variants  # noqa: E402

LUA = shutil.which("lua") or shutil.which("lua5.4")

STUBS = r"""
LOG = {}
ROLLS = 0
crawl = {
    stderr = function(s) LOG[#LOG + 1] = s end,
    random2 = function(n) ROLLS = ROLLS + 1; return 0 end,
}
XL, TURNS, WHERE, HP, MHP, FEAT = 10, 1000, "D:11", 30, 30, "floor"
you = {
    xl = function() return XL end, turns = function() return TURNS end,
    where = function() return WHERE end, hp = function() return HP, MHP end,
    status = function() return false end,
    branch = function() return WHERE:match("^[^:]+") end,
}
ladder_qw = { enemy_list = {}, can_flee_upstairs = true, flee_positions = {} }
ladder_const = {}
c_persist = {}
EXPLORED = {}
DEPTH = { D = 15, Lair = 5, Vaults = 5, Spider = 4, Swamp = 4, Shoals = 4, Snake = 4 }
EXISTS = { Spider = true, Swamp = true }
function explored_level_range(r) return EXPLORED[r] == true end
function branch_depth(b) return DEPTH[b] end
function make_level_range(b, first, last)
    if last < 0 then last = DEPTH[b] + last end
    return b .. ":" .. first .. "-" .. last
end
function branch_end(b) return b .. ":" .. DEPTH[b] end
function next_branch(options, skip)
    skip = skip or 0
    for _, b in ipairs(options) do
        if EXISTS[b] then
            if skip == 0 then return b end
            skip = skip - 1
        end
    end
end
function lair_branch_order()
    if not c_persist.lair_branch_order then
        crawl.random2(2)
        c_persist.lair_branch_order = { "Snake", "Spider", "Swamp", "Shoals" }
    end
    return c_persist.lair_branch_order
end
NEXT = "Lair"
function goal_normal_next(final) return NEXT end
function ready_for_lair() return true end
function update_invis_monsters(pos) end
function c_message(text, channel) end
function plan_flail_at_invis() return "flail" end
function unable_to_use_stairs() return false end
function feature_is_upstairs(f) return f == "stone_stairs_up_i" end
view = { feature_at = function(x, y) return FEAT end }
WENT_UP, MOVED = false, false
function go_upstairs() WENT_UP = true end
function best_move_towards_positions(ps) if #ps > 0 then return { move = { x = 1, y = 0 } } end end
function move_to(m) MOVED = true; return true end
-- stuck-loop variants
DEST_STEPS = 0
function plan_move_towards_destination()
    if not ladder_qw.move_destination then return false end
    DEST_STEPS = DEST_STEPS + 1
    return true
end
SENT = {}
function send_travel(branch, depth) SENT[#SENT + 1] = branch .. ":" .. tostring(depth) end
ENTRANCES = { Lair = "enter_lair", Orc = "enter_orcish_mines" }
function branch_entrance(b)
    if not ENTRANCES[b] then error("Unknown branch: " .. tostring(b)) end
    return ENTRANCES[b]
end
FEATURE_POS = {}
function best_move_towards_features(feats)
    local dest = FEATURE_POS[feats[1]]
    if dest then return { move = { x = 1, y = 0 }, dest = dest } end
end
function move_towards_destination(pos, dest, reason)
    ladder_qw.move_destination, ladder_qw.move_reason = dest, reason
    MOVED = true
    return true
end
WENT_DOWN = false
function go_downstairs() WENT_DOWN = true end
function make_level(b, d) return b .. ":" .. d end
LEVEL_EXPLORED, RESETS, FINALIZED, GOAL_UPDATES = {}, 0, 0, 0
function explored_level(b, d) return LEVEL_EXPLORED[b .. ":" .. d] == true end
function autoexplored_level(b, d) return LEVEL_EXPLORED[b .. ":" .. d] == true end
function have_all_stairs(b, d, dir, state) return LEVEL_EXPLORED[b .. ":" .. d] == true end
function num_required_stairs(b, d, dir) return 3 end
function count_stairs(b, d, dir, state) return 1 end
function reset_stone_stairs(b, d, dir) RESETS = RESETS + 1 end
function finalize_travel_depth(result) FINALIZED = FINALIZED + 1 end
function update_goal() GOAL_UPDATES = GOAL_UPDATES + 1 end
function check(cond, msg) if not cond then error("FAILED: " .. msg, 2) end end
"""


def run_lua(spec: str, body: str) -> str:
    code = STUBS + "\n" + variants.lua(spec) + "\n" + body + '\nprint("OK")\n'
    r = subprocess.run([LUA, "-"], input=code, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().endswith("OK"), r.stdout
    return r.stdout


pytestmark = pytest.mark.skipif(LUA is None, reason="no lua interpreter on PATH")


def test_every_variant_composes():
    for name in variants.VARIANTS:
        assert name in variants.lua(name)
    joined = variants.on_top_of("-- combo: MiBe.mace\nlocal qw, const = ladder_qw, ladder_const\n",
                                "lair_xl12+sigmund_leave")
    assert joined.startswith("-- combo: MiBe.mace") and "sigmund_leave" in joined


def test_lair_xl12():
    run_lua("lair_xl12", r"""
XL = 11
check(ready_for_lair() == false, "early Lair held at XL 11")
check(goal_normal_next() == "D:12", "D:12 before the Lair")
EXPLORED["D:12"] = true
check(goal_normal_next() == "D:13", "then D:13")
for d = 13, 15 do EXPLORED["D:" .. d] = true end
check(goal_normal_next() == "Lair", "Lair once D is done, whatever the XL")
EXPLORED["D:12"] = nil
XL = 12
check(ready_for_lair() == true, "early Lair at XL 12")
check(goal_normal_next() == "Lair", "Lair at XL 12")
NEXT = "D:1-11"
XL = 9
check(goal_normal_next() == "D:1-11", "other goals untouched")
check(#LOG >= 2 and LOG[1]:find("^QWDBG\t1000\tpacing lair_xl12"), "logged")
""")


def test_vaults_late():
    run_lua("vaults_late", r"""
NEXT = "Vaults:1-4"
XL = 18
-- qw's order Snake, Spider, Swamp, Shoals; this game has Spider and Swamp: the second is Swamp.
check(goal_normal_next() == "Swamp:4", "second Lair rune before Vaults")
EXPLORED["Swamp:4"] = true
check(goal_normal_next() == "Vaults:1-4", "Vaults once the second rune is in")
EXPLORED["Swamp:4"] = nil
XL = 19
check(goal_normal_next() == "Vaults:1-4", "Vaults at XL 19")
NEXT = "Spider:4"
XL = 15
check(goal_normal_next() == "Spider:4", "other goals untouched")
""")


def test_sigmund_leave():
    run_lua("sigmund_leave", r"""
local sig = { name = function() return "Sigmund" end }
XL = 3
WHERE = "D:2"
ladder_qw.enemy_list = { sig }
update_invis_monsters(nil)
check(plan_flail_at_invis() == "flail", "Sigmund in view: qw's own plans")
ladder_qw.enemy_list = {}
TURNS = 1010
ladder_qw.flee_positions = { { x = 5, y = 5 } }
check(plan_flail_at_invis() == "flail", "Sigmund out of view, full HP: qw's own plans")
HP = 20
check(plan_flail_at_invis() == true and MOVED, "Sigmund out of view, hurt: walk to the stairs")
FEAT = "stone_stairs_up_i"
check(plan_flail_at_invis() == true and WENT_UP, "on the stairs: go up")
check(LOG[1]:find("sigmund_leave: up from D:2 at XL 3"), "logged")
WENT_UP, MOVED = false, false
WHERE = "D:1"
check(plan_flail_at_invis() == "flail", "another level: untouched")
WHERE = "D:2"
XL = 10
check(plan_flail_at_invis() == "flail", "XL 10: untouched")
XL = 3
c_message("You kill Sigmund!", "plain")
check(plan_flail_at_invis() == "flail", "dead: forgotten")
update_invis_monsters(nil)
ladder_qw.enemy_list = { sig }
update_invis_monsters(nil)
ladder_qw.enemy_list = {}
for i = 2, 10 do plan_flail_at_invis() end
WENT_UP = false
check(plan_flail_at_invis() == "flail" and not WENT_UP, "at most 10 retreats a level")
""")


def test_snake_last():
    out = run_lua("snake_last", r"""
local o = lair_branch_order()
check(table.concat(o, ",") == "Spider,Swamp,Shoals,Snake", "order")
check(ROLLS == 1, "one roll, as qw's random preference makes")
lair_branch_order()
check(ROLLS == 1, "chosen once")
EXISTS = { Snake = true, Shoals = true }
check(next_branch(o) == "Shoals" and next_branch(o, 1) == "Snake", "Snake second")
""")
    assert out


def test_dest_giveup():
    run_lua("dest_giveup", r"""
WHERE = "D:7"
ladder_qw.move_destination, ladder_qw.move_reason = { x = -13, y = -5 }, "safety"
for i = 1, 400 do check(plan_move_towards_destination() == true, "walks while under 400 moves") end
check(DEST_STEPS == 400, "qw's own plan made the moves")
check(plan_move_towards_destination() == false, "dropped after 400")
check(ladder_qw.move_destination == nil and ladder_qw.move_reason == nil, "destination cleared")
check(#LOG == 1 and LOG[1]:find("dest_giveup: dropped safety destination D:7@%-13,%-5 after 400"),
      "logged")
ladder_qw.move_destination = { x = -13, y = -5 }
check(plan_move_towards_destination() == false and ladder_qw.move_destination == nil,
      "the same square again on this level: dropped at once")
check(#LOG == 1, "logged once")
ladder_qw.move_destination = { x = 3, y = 4 }
check(plan_move_towards_destination() == true, "another square: walked")
ladder_qw.move_destination = nil
check(plan_move_towards_destination() == false, "no destination: qw's plan")
WHERE = "D:8"
ladder_qw.move_destination = { x = -13, y = -5 }
check(plan_move_towards_destination() == true, "another level: the ban is gone")
""")


def test_travel_walk():
    run_lua("travel_walk", r"""
WHERE = "D:10"
send_travel("Lair", 1)
check(#SENT == 1, "travel as usual before any failure")
c_message("Sorry, I don't know how to get there.", "plain")
FEATURE_POS.enter_lair = { x = 49, y = 7 }
send_travel("Lair", 1)
check(#SENT == 1 and MOVED, "failed here: walk to the entrance instead")
check(ladder_qw.move_reason == "goal" and ladder_qw.move_destination.x == 49, "towards the entrance")
check(#LOG == 1 and LOG[1]:find("travel_walk: travel to Lair failed on D:10"), "logged")
FEAT = "enter_lair"
send_travel("Lair", 1)
check(WENT_DOWN and #SENT == 1, "on the entrance: take it")
FEAT = "floor"
send_travel("Orc", 1)
check(#SENT == 2, "another branch: travel as usual")
WHERE = "D:9"
send_travel("Lair", 1)
check(#SENT == 3, "another level: travel as usual")
WHERE = "D:10"
FEATURE_POS.enter_lair = nil
send_travel("Lair", 1)
check(#SENT == 4, "entrance not on the map: travel as usual")
WHERE = "D:2"
send_travel("D", 1)
c_message("Sorry, I don't know how to get there.", "plain")
send_travel("D", 1)
check(#SENT == 6, "never for the Dungeon itself")
WHERE = "Lair:1"
c_message("Sorry, I don't know how to get there.", "plain")
send_travel("Lair", 2)
check(#SENT == 7, "inside the branch: travel as usual")
""")


def test_bounce_giveup():
    run_lua("bounce_giveup", r"""
local function hop(where, dt)
    WHERE = where
    TURNS = TURNS + dt
    update_goal()
end
WHERE = "D:7"
update_goal()
hop("D:8", 2)
for i = 1, 19 do hop("D:7", 2); hop("D:8", 2) end
hop("D:7", 2)
check(#LOG == 0, "39 hops back: not yet")
hop("D:8", 2)
check(#LOG == 1 and LOG[1]:find("bounce_giveup: 40 quick hops back and forth between D:7 and D:8"),
      "detected at 40")
check(GOAL_UPDATES == 42, "qw's update_goal still runs")
check(explored_level("D", 7) and explored_level("D", 8), "both counted explored")
check(autoexplored_level("D", 8) and have_all_stairs("D", 7, 1, 4), "autoexplored, all stairs")
check(count_stairs("D", 7, 1, 4) == 3 and count_stairs("D", 9, 1, 4) == 1, "stairs counted")
reset_stone_stairs("D", 7, 1)
reset_stone_stairs("D", 9, 1)
check(RESETS == 1, "their stairs are no longer reset")
finalize_travel_depth({ branch = "D", depth = 8 })
finalize_travel_depth({ branch = "D", depth = 9 })
check(FINALIZED == 1, "nor finalized")
check(not explored_level("D", 9), "other levels untouched")
-- Slow hops (a stay of 7 turns or more) never count.
WHERE = "Lair:1"
update_goal()
for i = 1, 30 do hop("Lair:2", 7); hop("Lair:1", 2) end
check(#LOG == 1 and not explored_level("Lair", 2), "slow hops are play")
-- Fewer than 40 hops back, then a third level, never count.
for i = 1, 19 do hop("Lair:2", 1); hop("Lair:1", 1) end
hop("Lair:3", 1)
for i = 1, 10 do hop("Lair:2", 1); hop("Lair:3", 1) end
check(#LOG == 1, "run broken by a third level")
""")


def test_stuck_variants_join():
    run_lua("dest_giveup+travel_walk+bounce_giveup", r"""
WHERE = "D:10"
check(plan_move_towards_destination() == false, "loaded together")
""")
