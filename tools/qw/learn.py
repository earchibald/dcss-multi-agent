"""Learn, from forks of qw games, when doing something other than qw's choice pays, and write
the result as a Lua policy that qw loads (tools/qw/run.py --policy).

    uv run python tools/qw/learn.py --forks runs/qw/forks-r1 --jobs runs/qw/forks-r1-jobs.json \
        --out models/qw-policy-r1.lua

The model is a decision matrix: one row of weights per option (tools/qw/forks.py OPTIONS) over
the features below, giving the predicted gain of that option over what qw would do. At an
encounter's start, and when HP first falls under 70% and 40%, the policy takes the usable
option with the largest predicted gain if that gain clears a margin; otherwise qw decides.

Gain of a fork = (alive at the horizon) + 0.1 * (XL at the horizon), minus the same for the
base game at the same turn.

Every option was forked at every chosen moment, so a policy can be scored on held-out games
directly: the gain of the fork it would have picked (0 where it leaves qw alone).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from forks import CONTROLS, OPTIONS
from log import read_decisions

KINDS = ("start", "hp70", "hp40", "crowd")
XL_WEIGHT = 0.1

# name, Lua expression over the state table `s` and the helpers in LUA_HEAD. features()
# below must compute the same numbers.
FEATURES = [
    ("bias", "1"),
    ("kind_hp70", "(kind == 'hp70') and 1 or 0"),
    ("kind_hp40", "(kind == 'hp40') and 1 or 0"),
    ("hp_frac", "s.hp / math.max(1, s.mhp)"),
    ("xl", "s.xl / 10"),
    ("depth", "s.depth / 10"),
    ("in_dungeon", "(s.branch == 'D') and 1 or 0"),
    ("threat", "math.min(3, n(s.threat) / high)"),
    ("threat_avail", "math.min(3, n(s.threat_avail) / high)"),
    ("ranged_threat", "math.min(3, n(s.ranged_threat) / high)"),
    ("enemy_count", "math.min(8, n(s.enemy_count)) / 4"),
    ("scary", "n(s.scary_enemy)"),
    ("immediate", "n(s.immediate_danger)"),
    ("adjacent", "e.adjacent / 3"),
    ("nearest", "e.nearest / 7"),
    ("max_threat", "math.min(3, e.max_threat / high)"),
    ("any_ranged", "e.any_ranged"),
    ("any_fast", "e.any_fast"),
    ("has_flee", "(n(s.flee_dist) >= 0) and 1 or 0"),
    ("flee_dist", "(n(s.flee_dist) >= 0) and math.min(30, n(s.flee_dist)) / 30 or 1"),
    ("on_upstairs", "n(s.on_upstairs)"),
    ("open_ground", "n(s.adjacent_floor) / 8"),
    ("tired", "math.max(n(s.berserk_cooldown), n(s.exhausted))"),
    ("berserk", "n(s.berserk)"),
    ("has_heal", "(n(s.n_heal_wounds) > 0) and 1 or 0"),
    ("has_teleport", "(n(s.n_teleport) > 0) and 1 or 0"),
    ("piety", "n(s.piety_rank) / 6"),
    ("damage", "math.min(40, n(s.attack_damage)) / 20"),
    ("ac", "n(s.ac) / 20"),
    ("ev", "n(s.ev) / 20"),
    ("poisoned", "n(s.poisoned)"),
]


def num(v) -> float:
    if v is None or v == "":
        return 0.0
    return float(v)


def features(s: dict, kind: str) -> list[float]:
    high = max(1.0, num(s.get("high_threat_level")))
    en = s.get("enemies") or []
    adjacent = sum(1 for m in en if num(m["dist"]) <= 1)
    nearest = min((num(m["dist"]) for m in en), default=7.0)
    max_threat = max((num(m["threat"]) for m in en), default=0.0)
    any_ranged = 1.0 if any(num(m["ranged"]) for m in en) else 0.0
    any_fast = 1.0 if any(0 < num(m["move_delay"]) < 10 for m in en) else 0.0
    fd = num(s.get("flee_dist"))
    return [
        1.0, float(kind == "hp70"), float(kind == "hp40"),
        num(s["hp"]) / max(1.0, num(s["mhp"])), num(s["xl"]) / 10, num(s["depth"]) / 10,
        float(s.get("branch") == "D"),
        min(3.0, num(s["threat"]) / high), min(3.0, num(s["threat_avail"]) / high),
        min(3.0, num(s["ranged_threat"]) / high), min(8.0, num(s["enemy_count"])) / 4,
        num(s["scary_enemy"]), num(s["immediate_danger"]),
        adjacent / 3, nearest / 7, min(3.0, max_threat / high), any_ranged, any_fast,
        float(fd >= 0), min(30.0, fd) / 30 if fd >= 0 else 1.0,
        num(s["on_upstairs"]), num(s["adjacent_floor"]) / 8,
        max(num(s["berserk_cooldown"]), num(s["exhausted"])), num(s["berserk"]),
        float(num(s["n_heal_wounds"]) > 0), float(num(s["n_teleport"]) > 0),
        num(s["piety_rank"]) / 6, min(40.0, num(s["attack_damage"])) / 20,
        num(s["ac"]) / 20, num(s["ev"]) / 20, num(s["poisoned"]),
    ]


def load(forks: Path, jobs_path: Path) -> list[dict]:
    """One row per usable fork: seed, moment id, class, kind, option, x, gain."""
    jobs = {j["tag"]: j for j in json.loads(jobs_path.read_text())}
    results = json.loads((forks / "results.json").read_text())["games"]
    bases: dict[str, list[dict]] = {}
    rows, dropped = [], {"prefix": 0, "status": 0, "no_act": 0}
    for r in results:
        j = jobs.get(r["tag"])
        if j is None:
            continue
        if r.get("prefix_match") is False:
            dropped["prefix"] += 1
            continue
        if r["status"] not in ("done", "stopped"):
            dropped["status"] += 1
            continue
        if not r.get("overrides_acted") and j["option"] not in CONTROLS:
            dropped["no_act"] += 1  # the option could not act: the fork is the base game
            continue
        base = bases.get(j["base"])
        if base is None:
            base = bases[j["base"]] = [d for d in read_decisions(j["base"]) if d["state"]]
        at = next((d for d in base if d["decision"] == j["decision"]), None)
        if at is None:
            continue
        stop = j["stop_turn"]
        before = [d for d in base if d["state"]["turn"] <= stop]
        base_alive = float(base[-1]["state"]["turn"] > stop)
        base_xl = before[-1]["state"]["xl"]
        alive = float(r["status"] == "stopped")
        xl = r.get("xl") or at["state"]["xl"]
        rows.append({
            "seed": r["seed"], "moment": (r["seed"], j["decision"], j["kind"]), "class": j["class"],
            "kind": j["kind"], "option": j["option"], "x": features(at["state"], j["kind"]),
            "alive": alive, "base_alive": base_alive, "value": alive + XL_WEIGHT * xl,
            "base_value": base_alive + XL_WEIGHT * base_xl,
        })
    print(f"{forks}: {len(rows)} forks read; dropped {dropped}")
    return rows


def against_controls(rows: list[dict]) -> list[dict]:
    # Gain is measured against the control forks at the same moment (qw's own choice with the
    # dice re-rolled), not against the base game: see forks.CONTROLS.
    controls: dict[tuple, list[dict]] = {}
    for r in rows:
        if r["option"] in CONTROLS:
            controls.setdefault(r["moment"], []).append(r)
    kept = []
    for r in rows:
        c = controls.get(r["moment"])
        if r["option"] in CONTROLS or not c:
            continue
        r["gain"] = r["value"] - float(np.mean([x["value"] for x in c]))
        r["control_alive"] = float(np.mean([x["alive"] for x in c]))
        kept.append(r)
    print(f"{len(kept)} forks kept at {len({r['moment'] for r in kept})} moments with controls "
          f"({len(rows) - len(kept)} controls or forks without one)")
    return kept


def table(rows: list[dict]) -> None:
    print(f"{'class':9} {'kind':6} {'option':12} {'n':>5} {'alive':>6} {'base':>6} {'ctrl':>6} {'gain':>7} {'se':>5}")
    keys = sorted({(r["class"], r["kind"], r["option"]) for r in rows},
                  key=lambda k: (k[0], KINDS.index(k[1]), k[2]))
    for key in keys:
        g = [r for r in rows if (r["class"], r["kind"], r["option"]) == key]
        gains = np.array([r["gain"] for r in g])
        se = gains.std(ddof=1) / len(g) ** 0.5 if len(g) > 1 else 0.0
        print(f"{key[0]:9} {key[1]:6} {key[2]:12} {len(g):5} {np.mean([r['alive'] for r in g]):6.2f} "
              f"{np.mean([r['base_alive'] for r in g]):6.2f} {np.mean([r['control_alive'] for r in g]):6.2f} "
              f"{gains.mean():+7.3f} {se:5.3f}")


def fit(rows: list[dict], ridge: float) -> dict[str, np.ndarray]:
    weights = {}
    for opt in OPTIONS:
        g = [r for r in rows if r["option"] == opt]
        if len(g) < 30:
            continue
        x = np.array([r["x"] for r in g])
        y = np.array([r["gain"] for r in g])
        reg = ridge * np.eye(x.shape[1])
        reg[0, 0] = 0.0  # the bias is each option's average gain: leave it free
        weights[opt] = np.linalg.solve(x.T @ x + reg, x.T @ y)
    return weights


def policy_gain(rows: list[dict], weights: dict[str, np.ndarray], margin: float) -> tuple[float, float, int]:
    """Mean gain per moment of the option the policy would pick (0 where it picks none)."""
    by_moment: dict[tuple, list[dict]] = {}
    for r in rows:
        by_moment.setdefault(r["moment"], []).append(r)
    gains, picked = [], 0
    for forks in by_moment.values():
        best, best_pred = None, margin
        for r in forks:
            w = weights.get(r["option"])
            if w is None:
                continue
            pred = float(np.dot(w, r["x"]))
            if pred > best_pred:
                best, best_pred = r, pred
        gains.append(best["gain"] if best else 0.0)
        picked += best is not None
    g = np.array(gains)
    return float(g.mean()), float(g.std(ddof=1) / len(g) ** 0.5), picked


def cross_validate(rows: list[dict], ridge: float, margins: list[float], folds: int = 5) -> dict[float, tuple]:
    seeds = sorted({r["seed"] for r in rows})
    out = {}
    for margin in margins:
        per_moment: list[float] = []
        picked = 0
        for f in range(folds):
            held = set(seeds[f::folds])
            w = fit([r for r in rows if r["seed"] not in held], ridge)
            test = [r for r in rows if r["seed"] in held]
            mean, _, p = policy_gain(test, w, margin)
            n = len({r["moment"] for r in test})
            per_moment += [mean] * n
            picked += p
        out[margin] = (float(np.mean(per_moment)), picked, len(per_moment))
    return out


LUA_HEAD = """-- qw override policy learned from forks (tools/qw/learn.py). Generated: do not edit.
-- {note}
local MARGIN = {margin}
local GAP = 4
local function n(v)
    if v == true then return 1 end
    if v == nil or v == false or v == "" then return 0 end
    if type(v) ~= "number" or v ~= v then return 0 end
    return v
end
local function enemies(s)
    local e = {{ adjacent = 0, nearest = 7, max_threat = 0, any_ranged = 0, any_fast = 0 }}
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
"""

LUA_USABLE = {
    "berserk": "n(s.can_berserk) > 0 and n(s.berserk) == 0",
    "no_berserk": "n(s.can_berserk) > 0 and n(s.berserk) == 0",
    "teleport": "n(s.can_teleport) > 0 and n(s.teleporting) == 0",
    "heal_wounds": "n(s.n_heal_wounds) > 0 and n(s.can_drink) > 0 and s.hp < 0.7 * s.mhp",
    "flee": "n(s.can_flee_upstairs) > 0 and n(s.flee_positions) > 0 and n(s.berserk) == 0",
    "stairs_up": "n(s.on_upstairs) > 0 and n(s.can_flee_upstairs) > 0",
    "trogs_hand": "n(s.can_trogs_hand) > 0 and n(s.regenerating) == 0",
    "brothers": "n(s.can_brothers_in_arms) > 0",
    "retreat": "n(s.berserk) == 0",
    "no_melee": "n(s.berserk) == 0",
    "choke": "n(s.enemy_count) >= 2 and n(s.berserk) == 0",
    "stairs_fight": "n(s.enemy_count) >= 2 and n(s.berserk) == 0"
                    " and n(s.can_flee_upstairs) > 0 and n(s.flee_positions) > 0",
}


def lua_spec(spec: dict) -> str:
    parts = []
    if "force" in spec:
        parts.append(f'force = "{spec["force"]}"')
    if "veto" in spec:
        parts.append("veto = { " + ", ".join(f'"{v}"' for v in spec["veto"]) + " }")
    if "n" in spec:
        parts.append(f"n = {spec['n']}")
    return "{ " + ", ".join(parts) + " }"


def write_lua(path: Path, weights: dict[str, np.ndarray], margin: float, note: str) -> None:
    out = [LUA_HEAD.format(note=note, margin=repr(float(margin)))]
    out.append("local function features(s, kind)")
    out.append("    local high = math.max(1, n(s.high_threat_level))")
    out.append("    local e = enemies(s)")
    out.append("    return {")
    for name, expr in FEATURES:
        out.append(f"        {expr},  -- {name}")
    out.append("    }\nend\n")
    out.append("-- name, spec, usable(s), weights (one per feature, in order)")
    out.append("local OPTIONS = {")
    for opt in OPTIONS:  # a fixed order: ties and float sums are the same on every replay
        if opt not in weights:
            continue
        w = ", ".join(repr(round(float(v), 5)) for v in weights[opt])
        out.append(f'    {{ "{opt}", {lua_spec(OPTIONS[opt][0])},')
        out.append(f"      function(s) return {LUA_USABLE[opt]} end,")
        out.append(f"      {{ {w} }} }},")
    out.append("}\n")
    out.append("""local quiet, started, done70, done40 = 0, false, false, false

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
        crawl.stderr("QWPOL\\t" .. decision .. "\\t" .. kind .. "\\t" .. best[1] .. "\\t" ..
            string.format("%.3f", best_score))
        return best[2]
    end
    return nil
end
""")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--forks", type=Path, nargs="+", required=True, help="fork run directories")
    ap.add_argument("--jobs", type=Path, nargs="+", required=True, help="their jobs files, same order")
    ap.add_argument("--out", type=Path, help="write the Lua policy here")
    ap.add_argument("--ridge", type=float, default=10.0)
    ap.add_argument("--margin", type=float, default=None, help="default: the best cross-validated one")
    args = ap.parse_args()

    rows = []
    for f, j in zip(args.forks, args.jobs):
        rows += load(f, j)
    rows = against_controls(rows)
    table(rows)
    margins = [0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4]
    cv = cross_validate(rows, args.ridge, margins)
    print("\nheld-out gain per moment of the learned policy (qw alone = 0):")
    for m in margins:
        mean, picked, n = cv[m]
        print(f"  margin {m:4.2f}: {mean:+.4f}   overrides at {picked} of {n} moments")
    margin = args.margin if args.margin is not None else max(margins, key=lambda m: cv[m][0])
    weights = fit(rows, args.ridge)
    mean, se, picked = policy_gain(rows, weights, margin)
    print(f"\nchosen margin {margin}; on its own training forks: {mean:+.4f} (se {se:.4f}), {picked} overrides")
    if args.out:
        note = f"{len(rows)} forks, ridge {args.ridge}, margin {margin}, held-out gain {cv.get(margin, (float('nan'),))[0]:+.4f}"
        write_lua(args.out, weights, margin, note)
        print("wrote", args.out)


if __name__ == "__main__":
    main()
