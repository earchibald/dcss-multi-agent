"""Put the death-risk model inside qw: export a LightGBM model as a Lua policy, and check it against Python.

    uv run --group risk python tools/risk/export_lua.py export runs/risk/N50-zk
        # -> runs/risk/N50-zk/policy_risk_alarm.lua, for tools/qw/run.py --policy
    uv run --group risk python tools/risk/export_lua.py parity runs/qw/NAME --model runs/risk/N50-zk
        # the QWRISK probabilities a run logged against the model's own, from the same QWS lines

The policy is tools/qw/policy_risk_alarm.lua with its RISK_MODEL marker replaced by:

- the trees, one Lua function per tree, specialised to qw rows: a split on a feature that is constant
  for qw (is_qw, the brain's own fields, the statuses qw never logs) is decided here, so the
  function has only the splits a qw row can take both ways. Each split follows LightGBM's rule for
  its missing-value type, so a NaN would go where LightGBM sends it.
- the tables tools/risk/dataset.py computes the features with (the monster book, branch depths,
  feature order), written from dataset.py itself so the two cannot drift.

The policy computes the features from the live state, as dataset.qw_row does from the logged
state, and the probability as LightGBM does: the trees' outputs summed in order, then the sigmoid.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dataset  # noqa: E402

REPO = HERE.parents[1]
TEMPLATE = REPO / "tools" / "qw" / "policy_risk_alarm.lua"
MARKER = "-- @RISK_MODEL@"
POLICY_NAME = "policy_risk_alarm.lua"
K_ZERO = float(np.float32(1e-35))   # LightGBM's kZeroThreshold


# ---------------------------------------------------------------------------------------------------
# the forest


def load_forest(model_file: Path) -> dict:
    """The model as LightGBM dumps it: {"trees": [root node, ...], "features", "sigmoid"}."""
    import lightgbm as lgb

    return forest_from_dump(lgb.Booster(model_file=str(model_file)).dump_model())


def forest_from_dump(m: dict) -> dict:
    """load_forest from a Booster.dump_model() dict (no LightGBM needed)."""
    obj = m["objective"].split()
    if obj[0] != "binary" or m["num_class"] != 1:
        raise SystemExit(f"only binary models: {m['objective']}")
    sigmoid = float(next((o.split(":")[1] for o in obj[1:] if o.startswith("sigmoid:")), 1.0))
    return {"trees": [t["tree_structure"] for t in m["tree_info"]], "features": m["feature_names"],
            "sigmoid": sigmoid}


def go_left(node: dict, x: float) -> bool:
    """LightGBM's numerical decision (tree.h NumericalDecision) for one value."""
    if node["decision_type"] != "<=":
        raise SystemExit(f"unsupported split {node['decision_type']}")
    missing = node["missing_type"]
    if math.isnan(x) and missing != "NaN":
        x = 0.0
    if (missing == "Zero" and -K_ZERO <= x <= K_ZERO) or (missing == "NaN" and math.isnan(x)):
        return bool(node["default_left"])
    return x <= node["threshold"]


def predict_raw(forest: dict, row) -> float:
    """The raw score of one float32 row: the trees' leaf values summed in order."""
    raw = 0.0
    for node in forest["trees"]:
        while "leaf_value" not in node:
            x = float(row[node["split_feature"]])
            node = node["left_child"] if go_left(node, x) else node["right_child"]
        raw += node["leaf_value"]
    return raw


def sigmoid(forest: dict, raw: float) -> float:
    return 1.0 / (1.0 + math.exp(-forest["sigmoid"] * raw))


def qw_constants() -> dict[int, float]:
    """Features with one value on every qw row: is_qw, and those qw_row never sets (NaN)."""
    row, _ = dataset.qw_row({}, dataset.MonsterBook(), dataset.History())
    out = {i: float(v) for i, v in enumerate(row) if math.isnan(v)}
    out[dataset.F_INDEX["is_qw"]] = 1.0
    return out


def prune(node: dict, consts: dict[int, float]) -> dict:
    """The tree with every split on a constant feature decided."""
    while "leaf_value" not in node and node["split_feature"] in consts:
        node = node["left_child"] if go_left(node, consts[node["split_feature"]]) else node["right_child"]
    if "leaf_value" in node:
        return {"leaf_value": node["leaf_value"]}
    out = {k: node[k] for k in ("split_feature", "threshold", "decision_type", "missing_type", "default_left")}
    out["left_child"] = prune(node["left_child"], consts)
    out["right_child"] = prune(node["right_child"], consts)
    return out


def count_nodes(node: dict) -> int:
    return 0 if "leaf_value" in node else 1 + count_nodes(node["left_child"]) + count_nodes(node["right_child"])


# ---------------------------------------------------------------------------------------------------
# Lua


def lua_num(x) -> str:
    if isinstance(x, (bool, np.bool_)):
        return "true" if x else "false"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    x = float(x)
    if math.isnan(x):
        return "(0/0)"
    if math.isinf(x):
        return "math.huge" if x > 0 else "(-math.huge)"
    r = repr(x)
    return r if any(c in r for c in ".en") else r + ".0"


def lua_str(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if ch in '"\\':
            out.append("\\" + ch)
        elif 32 <= o < 127:
            out.append(ch)
        else:
            out.extend(f"\\{b:03d}" for b in ch.encode("utf-8"))
    return '"' + "".join(out) + '"'


def lua_value(v) -> str:
    if isinstance(v, str):
        return lua_str(v)
    if isinstance(v, dict):
        return "{ " + ", ".join(f"[{lua_value(k)}] = {lua_value(x)}" for k, x in v.items()) + " }"
    if isinstance(v, (list, tuple)):
        return "{ " + ", ".join(lua_value(x) for x in v) + " }"
    return lua_num(v)


def tree_lua(node: dict, depth: int = 1) -> list[str]:
    """One tree as nested ifs over the row f (1-based). Every split is `f <= t` or `not (f > t)`:
    the two agree on numbers, and the second sends NaN left, as LightGBM does for a NaN split that
    defaults left and for a no-missing split whose threshold is at least 0 (NaN is read as 0)."""
    pad = " " * depth
    if "leaf_value" in node:
        return [f"{pad}return {lua_num(node['leaf_value'])}"]
    if node["decision_type"] != "<=" or node["missing_type"] == "Zero":
        raise SystemExit(f"unsupported split: {node['decision_type']} missing {node['missing_type']}")
    nan_left = go_left(node, float("nan"))
    v, t = f"f[{node['split_feature'] + 1}]", lua_num(node["threshold"])
    cond = f"not ({v} > {t})" if nan_left else f"{v} <= {t}"
    return ([f"{pad}if {cond} then"] + tree_lua(node["left_child"], depth + 1) + [f"{pad}else"]
            + tree_lua(node["right_child"], depth + 1) + [f"{pad}end"])


def monsters_table(book: dataset.MonsterBook) -> list[str]:
    tags = set(dataset.MON_TAGS)
    lines = []
    for name, m in sorted(book.by_name.items()):
        t = sorted(tags & m["tags"])
        lines.append(f"    [{lua_str(name)}] = {{ hd = {lua_num(m['hd'])}, hp = {lua_num(float(m['hp']))}, "
                     f"speed = {lua_num(m['speed'])}, exp = {lua_num(m['exp'])}, dmg = {lua_num(m['dmg'])}, "
                     f"ranged = {lua_num(m['ranged'])}, tags = {{ {', '.join(f'[{lua_str(x)}] = true' for x in t)} }} }},")
    return lines


def model_lua(forest: dict, *, threshold: float, horizon: int, source: str, consts: dict[int, float] | None = None,
              book: dataset.MonsterBook | None = None) -> str:
    """The Lua that defines ladder_risk_model (the trees and dataset's tables)."""
    if list(forest["features"]) != dataset.FEATURES:
        raise SystemExit("the model's features are not dataset.FEATURES")
    consts = qw_constants() if consts is None else consts
    book = book or dataset.MonsterBook()
    trees = [prune(t, consts) for t in forest["trees"]]
    head = [
        f"-- generated by tools/risk/export_lua.py from {source}: {len(trees)} trees, "
        f"{sum(count_nodes(t) for t in trees)} splits for qw rows",
        "ladder_risk_model = {",
        f"    source = {lua_str(source)},",
        f"    horizon = {int(horizon)},",
        f"    threshold = {lua_num(float(threshold))},",
        f"    sigmoid = {lua_num(float(forest['sigmoid']))},",
        f"    features = {lua_value(dataset.FEATURES)},",
        f"    nearest = {dataset.NEAREST},",
        f"    player_speed = {dataset.PLAYER_SPEED},",
        f"    default_base = {dataset.DEFAULT_BASE},",
        f"    mon_tags = {lua_value(list(dataset.MON_TAGS))},",
        f"    place_short = {lua_value(dataset.PLACE_SHORT)},",
        f"    branch_base = {lua_value(dataset.BRANCH_BASE)},",
        f"    rune_branches = {lua_value({b: True for b in sorted(dataset.RUNE_BRANCHES)})},",
        "    trees = {},",
        "    monsters = {",
        *["    " + line for line in monsters_table(book)],
        "    },",
        "}",
        "do",
        "    local T = ladder_risk_model.trees",
    ]
    body = []
    for i, t in enumerate(trees, 1):
        body.append(f"    T[{i}] = function(f)")
        body += tree_lua(t, 2)
        body.append("    end")
    return "\n".join(head + body + ["end", ""])


def policy_lua(model: str, template: Path = TEMPLATE) -> str:
    text = template.read_text(encoding="utf-8")
    if text.count(MARKER) != 1:
        raise SystemExit(f"{template}: no single {MARKER!r} line")
    out = text.replace(MARKER, model.rstrip("\n"))
    bad = [line for line in out.splitlines() if rc_block_ends(line)]
    if bad:
        raise SystemExit(f"a line would end the rc's Lua block: {bad[0]!r}")
    return out


def rc_block_ends(line: str) -> bool:
    """Crawl's rc reader ends a `<` Lua block at a line whose first '>' is its last character."""
    s = line.strip()
    return bool(s) and s.find(">") == len(s) - 1


def offline_driver(policy: Path, states: list[dict], features: bool = False) -> str:
    """Lua that runs the policy outside crawl on states as decisions 0, 1, ..., printing its QWRISK (and with
    `features`, QWRISKF) lines. A state is a log.parse_state dict or a live-style one (booleans, full floats).
    For tests and timing with a stock `lua`."""
    lines = ["crawl = { stderr = function(s) io.write(s, '\\n') end }",
             f"LADDER_RISK_FEATURES = {'true' if features else 'false'}",
             f"dofile({lua_str(str(policy))})",
             "local states = {"]
    for s in states:
        items = [f"[{lua_str(k)}] = {lua_value(v)}" for k, v in s.items() if k != "enemies" and v is not None]
        lines.append("{ " + ", ".join(items) + " },")
    lines += ["}", "for i, s in ipairs(states) do ladder_choose(i - 1, s) end", ""]
    return "\n".join(lines)


def default_threshold(model_dir: Path) -> float | None:
    p = model_dir / "early_val_lgbm_fpr0.05.json"
    if p.exists():
        return float(json.loads(p.read_text())["qw"]["threshold"])
    return None


def cmd_export(args) -> None:
    model_dir = args.model_dir
    threshold = args.threshold if args.threshold is not None else default_threshold(model_dir)
    if threshold is None:
        raise SystemExit("no early_val_lgbm_fpr0.05.json in the model directory: pass --threshold")
    info = json.loads((model_dir / "train.json").read_text()) if (model_dir / "train.json").exists() else {}
    forest = load_forest(model_dir / "lgbm.txt")
    source = str((model_dir / "lgbm.txt").resolve().relative_to(REPO)) \
        if (model_dir / "lgbm.txt").resolve().is_relative_to(REPO) else str(model_dir / "lgbm.txt")
    model = model_lua(forest, threshold=threshold, horizon=int(info.get("horizon", args.horizon)), source=source)
    out = args.out or model_dir / POLICY_NAME
    out.write_text(policy_lua(model), encoding="utf-8")
    full = sum(count_nodes(t) for t in forest["trees"])
    kept = sum(count_nodes(prune(t, qw_constants())) for t in forest["trees"])
    print(f"wrote {out} ({out.stat().st_size // 1024} KB): {len(forest['trees'])} trees, "
          f"{kept} of {full} splits kept for qw rows, threshold {threshold:.6g}")


# ---------------------------------------------------------------------------------------------------
# parity: a run's QWRISK lines against Python on its QWS lines


def read_game(path: Path):
    """(Python feature rows, decisions, {decision: (p, raw, alarm)}, {decision: lua features}) of one game."""
    name = path / "stderr.log.gz" if (path / "stderr.log.gz").exists() else path / "stderr.log"
    opener = gzip.open if name.suffix == ".gz" else open
    book, hist = dataset.MonsterBook(), dataset.History()
    rows, decisions, lua, feats = [], [], {}, {}
    with opener(name, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            tag, _, rest = line.rstrip("\n").partition("\t")
            if tag == "QWS":
                idx, _, fields = rest.partition("\t")
                s = dataset.parse_state(fields.split("\t"))
                if not s:
                    continue
                row, _ = dataset.qw_row(s, book, hist)
                rows.append(row)
                decisions.append(int(idx))
            elif tag == "QWRISK":
                idx, _turn, p, raw, alarm = rest.split("\t")[:5]
                lua[int(idx)] = (float(p), float(raw), alarm == "1")
            elif tag == "QWRISKF":
                parts = rest.split("\t")
                feats[int(parts[0])] = np.array([float(v) for v in parts[1:]], dtype=np.float32)
    return (np.stack(rows) if rows else np.zeros((0, len(dataset.FEATURES)), np.float32)), decisions, lua, feats


def cmd_parity(args) -> None:
    import lightgbm as lgb

    booster = lgb.Booster(model_file=str(args.model / "lgbm.txt"))
    threshold = args.threshold if args.threshold is not None else default_threshold(args.model)
    games = sorted(p for p in (args.run / "games").iterdir() if p.is_dir())
    diffs, agree, n_states, n_lua, per_game, feat_bad = [], [], 0, 0, [], {}
    py_alarm, lua_alarm_list = [], []
    for g in games:
        X, decisions, lua, feats = read_game(g)
        n_states += len(decisions)
        n_lua += len(lua)
        if not len(decisions):
            continue
        p_py = booster.predict(X)
        both = [(i, d) for i, d in enumerate(decisions) if d in lua]
        d = np.array([abs(lua[dec][0] - p_py[i]) for i, dec in both])
        a = np.array([(lua[dec][0] >= threshold) == (p_py[i] >= threshold) for i, dec in both])
        diffs.append(d)
        agree.append(a)
        py_alarm += [p_py[i] >= threshold for i, _ in both]
        lua_alarm_list += [lua[dec][2] for _, dec in both]
        for i, dec in both:
            if dec in feats:
                for j in np.flatnonzero(~((feats[dec] == X[i]) | (np.isnan(feats[dec]) & np.isnan(X[i])))):
                    feat_bad[dataset.FEATURES[j]] = feat_bad.get(dataset.FEATURES[j], 0) + 1
        per_game.append({"game": g.name, "states": len(decisions), "qwrisk": len(lua), "matched": len(both),
                         "max_abs_diff": float(d.max()) if len(d) else None,
                         "alarms_python": int(sum(p_py >= threshold)),
                         "alarm_agree": float(a.mean()) if len(a) else None})
    d = np.concatenate(diffs) if diffs else np.zeros(0)
    a = np.concatenate(agree) if agree else np.zeros(0, bool)
    q = [0.5, 0.9, 0.99, 0.999, 1.0]
    res = {"run": str(args.run), "model": str(args.model), "threshold": threshold, "games": len(games),
           "states": n_states, "qwrisk_lines": n_lua, "matched": int(len(d)),
           "abs_diff": {"exactly_equal": int((d == 0).sum()), "max": float(d.max()) if len(d) else None,
                        "quantiles": dict(zip(map(str, q), np.quantile(d, q).tolist())) if len(d) else None,
                        "over_1e-12": int((d > 1e-12).sum()), "over_1e-6": int((d > 1e-6).sum())},
           "alarm_agree": {"agree": int(a.sum()), "of": int(len(a)), "fraction": float(a.mean()) if len(a) else None,
                           "logged_bit_equals_python": int(sum(x == y for x, y in zip(lua_alarm_list, py_alarm))),
                           "alarms_python": int(sum(py_alarm)), "alarms_lua": int(sum(lua_alarm_list))},
           "features_differing": feat_bad, "per_game": per_game}
    print(json.dumps(res, indent=1))
    if args.out:
        args.out.write_text(json.dumps(res, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="write <model dir>/policy_risk_alarm.lua")
    e.add_argument("model_dir", type=Path)
    e.add_argument("--threshold", type=float, default=None,
                   help="alarm threshold (default: qw's 5%%-false-alarm threshold from early_val_lgbm_fpr0.05.json)")
    e.add_argument("--horizon", type=int, default=50, help="if the directory has no train.json")
    e.add_argument("--out", type=Path, default=None)
    p = sub.add_parser("parity", help="a run's logged QWRISK probabilities against Python's")
    p.add_argument("run", type=Path, help="runs/qw/NAME (played with the exported policy and --state-log)")
    p.add_argument("--model", type=Path, required=True, help="the model directory the policy was exported from")
    p.add_argument("--threshold", type=float, default=None)
    p.add_argument("--out", type=Path, default=None, help="also write the result as JSON here")
    args = ap.parse_args()
    {"export": cmd_export, "parity": cmd_parity}[args.cmd](args)


if __name__ == "__main__":
    main()
