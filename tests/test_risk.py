"""The death-risk dataset's labels and censoring (tools/risk/dataset.py), and the model's Lua export for qw
(tools/risk/export_lua.py, tools/qw/policy_risk_alarm.lua)."""

import importlib.util
import json
import math
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "risk"))

import dataset  # noqa: E402
import export_lua  # noqa: E402
from dataset import label, labels, qw_died  # noqa: E402

LUA = shutil.which("lua") or shutil.which("lua5.4")
needs_lua = pytest.mark.skipif(LUA is None, reason="no lua interpreter (Lua 5.4+) on PATH")


def test_a_death_labels_every_row():
    turns = [0, 100, 149, 150, 199, 200]
    # died at turn 200: rows within 50 turns of it are 1, earlier rows are known 0
    assert label(turns, 200, True, 50).tolist() == [0, 0, 0, 1, 1, 1]


def test_a_censored_game_has_unknown_last_turns():
    turns = [0, 100, 149, 150, 151, 200]
    # quit, timed out or stopped at turn 200: alive then, so rows 50+ turns before it are 0, later unknown
    assert label(turns, 200, False, 50).tolist() == [0, 0, 0, 0, -1, -1]


def test_a_censored_game_is_never_a_death():
    for horizon in (1, 50, 200, 10_000):
        assert (label(np.arange(0, 1000, 7), 1000, False, horizon) != 1).all()


def test_vectorised_labels_match():
    rng = np.random.default_rng(0)
    turn = rng.integers(0, 5000, 2000).astype(np.float64)
    end = turn + rng.integers(0, 600, 2000)
    died = rng.random(2000) < 0.5
    meta = {"turn": turn, "end_turn": end, "died": died}
    for h in (50, 200):
        want = [label([t], e, d, h)[0] for t, e, d in zip(turn, end, died)]
        assert labels(meta, h).tolist() == want


def test_qw_endings():
    assert qw_died({"status": "done", "ktyp": "mon"})
    assert qw_died({"status": "done", "ktyp": "pois"})
    assert not qw_died({"status": "done", "ktyp": "quitting"})
    assert not qw_died({"status": "done", "ktyp": "winning"})
    assert not qw_died({"status": "stopped", "ktyp": None})       # a fork at its horizon
    assert not qw_died({"status": "timeout", "ktyp": None})
    assert not qw_died({"status": "error_loop", "ktyp": "mon"})   # the runner's word, not the game's


# ---------------------------------------------------------------------------------------------------
# the Lua export


def _fmt_value(v) -> str:
    """tools/qw/ladder.lua fmt_value: how the QWS line writes a state value."""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v:
            return "nan"
        if not math.isinf(v) and v == math.floor(v) and abs(v) < 1e15:
            return "%d" % v
        return "%.4g" % v
    if v is None:
        return ""
    return re.sub("[\t\n=]", " ", str(v))


def _logged(live: dict) -> dict:
    return dataset.parse_state([f"{k}={_fmt_value(v)}" for k, v in live.items()])


NAMES = ["goblin", "orc", "the Royal Jelly", "orc zombie", "spectral warrior", "dancing weapon",
         "larval weirdsting beast", "kobolds", "Grum the Hunter", "a hill giant", "unheard-of thing",
         "  Jackal ", "deep elf annihilator", "black mamba", "orc priest", "electric eel"]


def _live_states(n: int, seed: int = 0) -> list[dict]:
    """A game's worth of live-style qw states (booleans, full-precision floats), a few odd cases included."""
    rng = random.Random(seed)
    turn, out = 0, []
    for _ in range(n):
        turn += rng.choice([0, 1, 1, 2, 3, 7, 15, 40])
        mhp = rng.randint(15, 220)
        hp = mhp if rng.random() < 0.3 else rng.randint(0, mhp)
        s = {"turn": turn, "branch": rng.choice(["D", "Lair", "Orc", "Snake", "Zot", "Abyss", "Sewer", "Temple"]),
             "depth": rng.randint(1, 12), "xl": rng.randint(1, 27), "hp": hp, "mhp": mhp,
             "ac": rng.randint(-3, 40), "ev": rng.randint(0, 30), "sh": rng.randint(0, 20),
             "str": rng.randint(5, 40), "dex": rng.randint(3, 20), "god": rng.choice(["Trog", "Okawaru", ""]),
             "piety_rank": rng.randint(0, 6), "turns_on_level": rng.randint(0, 9000),
             "berserk": rng.random() < 0.2, "berserk_cooldown": rng.random() < 0.1,
             "exhausted": rng.random() < 0.1, "hasted": rng.random() < 0.1, "slowed": rng.random() < 0.1,
             "confused": rng.random() < 0.05, "poisoned": rng.random() < 0.2,
             "poison_survival": max(hp - rng.randint(0, 30), 0), "corrosion": rng.choice([0, 0, 4]),
             "mighty": rng.random() < 0.1, "teleporting": False, "caught": rng.random() < 0.05,
             "constricted": False, "threat": rng.choice([0, rng.uniform(0, 30)]),
             "ranged_threat": rng.uniform(0, 5), "enemy_count": rng.randint(0, 9),
             "enemy_move_delay": float("nan"), "scary_enemy": rng.random() < 0.2,
             "threat_avail": rng.uniform(0, 30), "high_threat_level": rng.choice([7, 10, 0.5, 2.25]),
             "danger_in_los": rng.random() < 0.5, "immediate_danger": rng.random() < 0.3,
             "position_is_safe": rng.random() < 0.5, "position_is_cloudy": rng.random() < 0.05}
        k = rng.randint(0, 5)
        for j in range(1, 6):
            if j <= k:
                s |= {f"e{j}_name": rng.choice(NAMES), f"e{j}_dist": rng.randint(1, 7),
                      f"e{j}_ranged": rng.random() < 0.3, f"e{j}_damage_level": rng.randint(0, 3),
                      f"e{j}_sleeping": rng.random() < 0.2, f"e{j}_hasted": rng.random() < 0.1}
            else:
                s[f"e{j}_name"] = ""
        s |= {"can_flee_upstairs": rng.random() < 0.5, "flee_dist": rng.choice([-1, 3, 12]),
              "on_upstairs": rng.random() < 0.1, "adjacent_floor": rng.randint(-1, 8), "allies_3": 0,
              "can_berserk": rng.random() < 0.5, "n_heal_wounds": rng.randint(0, 3), "n_curing": rng.randint(0, 3),
              "n_haste": rng.randint(0, 2), "n_might": rng.randint(0, 2), "n_teleport": rng.randint(0, 3),
              "unid_potion_stacks": rng.randint(0, 2), "unid_scroll_stacks": rng.randint(0, 2),
              "attack_damage": rng.choice([0, rng.uniform(1, 40), "err"]), "sk_fighting": rng.uniform(0, 27)}
        out.append(s)
    return out


def _run_lua(path: Path, tmp_path: Path) -> str:
    return subprocess.run([LUA, str(path)], capture_output=True, text=True, check=True, cwd=tmp_path).stdout


def _policy(tmp_path: Path, forest: dict, consts=None, threshold: float = 0.05) -> Path:
    model = export_lua.model_lua(forest, threshold=threshold, horizon=50, source="test", consts=consts)
    path = tmp_path / "policy.lua"
    path.write_text(export_lua.policy_lua(model))
    return path


def _risk_lines(out: str) -> tuple[dict, dict]:
    p, feats = {}, {}
    for line in out.splitlines():
        parts = line.split("\t")
        if parts[0] == "QWRISK":
            p[int(parts[1])] = (float(parts[3]), float(parts[4]), parts[5] == "1")
        elif parts[0] == "QWRISKF":
            feats[int(parts[1])] = np.array([float(v) for v in parts[2:]], dtype=np.float32)
        elif parts[0] == "QWRISKERR":
            raise AssertionError(line)
    return p, feats


TRIVIAL = {"trees": [{"leaf_value": -3.0}], "features": dataset.FEATURES, "sigmoid": 1.0}


@needs_lua
def test_lua_features_equal_dataset_from_the_live_state(tmp_path):
    """The policy's features from live values equal dataset.qw_row's from the QWS line those values log as."""
    live = _live_states(400)
    book, hist = dataset.MonsterBook(), dataset.History()
    want = [dataset.qw_row(_logged(s), book, hist)[0] for s in live]
    drv = tmp_path / "drive.lua"
    drv.write_text(export_lua.offline_driver(_policy(tmp_path, TRIVIAL), live, features=True))
    p, feats = _risk_lines(_run_lua(drv, tmp_path))
    assert sorted(feats) == list(range(len(live)))
    for i, row in enumerate(want):
        same = (feats[i] == row) | (np.isnan(feats[i]) & np.isnan(row))
        assert same.all(), (i, [(dataset.FEATURES[j], feats[i][j], row[j]) for j in np.flatnonzero(~same)])
    assert p[0][0] == 1 / (1 + math.exp(3.0))


@needs_lua
def test_lua_pysum_is_pythons_sum(tmp_path):
    rng = random.Random(1)
    cases = [[rng.choice([rng.randint(0, 50), rng.uniform(0, 100), rng.randint(1, 9) * 1.7 / 10])
              for _ in range(rng.randint(0, 6))] for _ in range(300)]
    drv = tmp_path / "sum.lua"
    drv.write_text(export_lua.offline_driver(_policy(tmp_path, TRIVIAL), []) + "\n".join(
        f"print(string.format('%.17g', ladder_risk.pysum({export_lua.lua_value(c)}, {len(c)})))" for c in cases))
    got = [float(x) for x in _run_lua(drv, tmp_path).split()]
    assert got == [float(sum(c)) for c in cases]


def _lightgbm(code: str, cwd: Path) -> None:
    """Run `code` with LightGBM in a child Python. LightGBM and torch each load their own OpenMP and abort
    in one process on macOS, and other tests in this suite load torch."""
    if importlib.util.find_spec("lightgbm") is None:
        pytest.skip("lightgbm is not installed (dependency group risk)")
    subprocess.run([sys.executable, "-c", "import json, numpy as np, lightgbm as lgb\n" + code],
                   cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    """A small booster on random rows with NaNs (both default directions) and integer ties:
    (its forest, the rows, LightGBM's raw scores and probabilities on the first 500)."""
    d = tmp_path_factory.mktemp("tiny")
    rng = np.random.default_rng(0)
    X = rng.normal(size=(4000, len(dataset.FEATURES))).astype(np.float32)
    X[rng.random(X.shape) < 0.1] = np.nan
    X[:, 1] = np.round(X[:, 1])
    y = ((np.nan_to_num(X[:, 1]) + np.nan_to_num(X[:, 3]) * 0.5 + rng.normal(size=len(X))) > 1).astype(int)
    np.save(d / "X.npy", X)
    np.save(d / "y.npy", y)
    _lightgbm(f"""
X, y = np.load("X.npy"), np.load("y.npy")
params = {{"objective": "binary", "num_leaves": 15, "min_data_in_leaf": 20, "verbose": -1, "seed": 1,
          "num_threads": 1}}
b = lgb.train(params, lgb.Dataset(X, y, feature_name={dataset.FEATURES!r}), num_boost_round=25)
json.dump(b.dump_model(), open("dump.json", "w"))
np.save("raw.npy", b.predict(X[:500], raw_score=True))
np.save("p.npy", b.predict(X[:500]))
""", d)
    forest = export_lua.forest_from_dump(json.loads((d / "dump.json").read_text()))
    return forest, X, np.load(d / "raw.npy"), np.load(d / "p.npy")


def test_python_tree_walk_equals_lightgbm(tiny):
    forest, X, raw, _ = tiny
    assert [export_lua.predict_raw(forest, r) for r in X[:500]] == pytest.approx(raw.tolist(), abs=1e-12)


def test_pruning_for_qw_rows_changes_nothing(tiny):
    forest, X, _, _ = tiny
    consts = export_lua.qw_constants()
    assert dataset.F_INDEX["b_threat_max"] in consts and dataset.F_INDEX["hp"] not in consts
    rows = X[:500].copy()
    for j, v in consts.items():
        rows[:, j] = v
    pruned = dict(forest, trees=[export_lua.prune(t, consts) for t in forest["trees"]])
    assert [export_lua.predict_raw(pruned, r) for r in rows] == [export_lua.predict_raw(forest, r) for r in rows]
    assert sum(map(export_lua.count_nodes, pruned["trees"])) < sum(map(export_lua.count_nodes, forest["trees"]))


@needs_lua
def test_lua_trees_equal_lightgbm(tiny, tmp_path):
    """The exported trees, run in Lua on float32 rows with NaNs, give LightGBM's probabilities."""
    forest, X, _, p = tiny
    rows = X[:400]
    model = export_lua.model_lua(forest, threshold=0.5, horizon=50, source="test", consts={})
    (tmp_path / "model.lua").write_text(model)
    drv = ["dofile('model.lua')", "local T = ladder_risk_model.trees", "local rows = {"]
    drv += ["{ " + ", ".join(export_lua.lua_num(float(v)) for v in r) + " }," for r in rows]
    drv += ["}", "for _, f in ipairs(rows) do local raw = 0.0",
            "for i = 1, #T do raw = raw + T[i](f) end",
            "print(string.format('%.17g', 1 / (1 + math.exp(-raw)))) end"]
    (tmp_path / "trees.lua").write_text("\n".join(drv))
    got = np.array([float(x) for x in _run_lua(tmp_path / "trees.lua", tmp_path).split()])
    assert np.abs(got - p[:400]).max() < 1e-15


@needs_lua
def test_policy_takes_no_action_and_fits_in_an_rc_block(tmp_path):
    policy = _policy(tmp_path, TRIVIAL, threshold=0.01)
    assert not [line for line in policy.read_text().splitlines() if export_lua.rc_block_ends(line)]
    assert export_lua.rc_block_ends("  x >") and not export_lua.rc_block_ends("if a > b then")
    drv = tmp_path / "choose.lua"
    drv.write_text(export_lua.offline_driver(policy, []) + "\n".join([
        'LADDER_OVERRIDES = { [3] = { force = "teleport" } }',
        "local s = { turn = 5, hp = 10, mhp = 20, e1_name = '' }",
        "for d = 0, 5 do local spec = ladder_choose(d, s)",
        "print(d, spec and spec.force or '-', ladder_risk.alarm_on, ladder_risk.decision) end",
        "print(ladder_choose(6, nil))"]))
    out = [line.split("\t") for line in _run_lua(drv, tmp_path).splitlines() if not line.startswith("QWRISK")]
    assert [o[1] for o in out[:6]] == ["-", "-", "-", "teleport", "-", "-"]
    assert all(o[2] == "true" for o in out[:6]) and out[5][3] == "5"
    assert out[6] == ["nil"]


# ---------------------------------------------------------------------------------------------------
# the stance: teleport on the alarm (TRIVIAL gives p = 1 / (1 + e^3) = 0.0474 at every decision)

P_TRIVIAL = 1 / (1 + math.exp(3.0))

# qw as ladder.lua sees it, stubbed: can_teleport() and teleport() are qw's, the teleport primitive is
# ladder.lua's (`can_teleport() and teleport() or false`), and step() does what plans.turn does with a spec.
QW_STUB = """
scrolls, can_read_now, reads = 0, true, 0
function can_teleport() return can_read_now and scrolls > 0 end
function teleport() scrolls = scrolls - 1; reads = reads + 1; return true end
ladder_primitives = { teleport = function() return can_teleport() and teleport() or false end,
                      reroll = function() return false end }
function step(d, s)
    local spec = ladder_choose(d, s)
    local acted = nil
    if spec and spec.force then acted = ladder_primitives[spec.force](spec, d) end
    print("STEP", d, spec and spec.force or "-", tostring(acted), scrolls)
end
function st(turn, n, extra)
    local s = { turn = turn, hp = 10, mhp = 20, e1_name = "", n_teleport = n, can_teleport = n > 0,
                teleporting = false }
    for k, v in pairs(extra or {}) do s[k] = v end
    return s
end
"""


def _stance_run(tmp_path: Path, body: str, policy: Path | None = None):
    """Run `body` after the policy and QW_STUB: (STEP lines, QWSTANCE lines, all lines), split on tabs."""
    policy = policy or _policy(tmp_path, TRIVIAL, threshold=0.01)
    drv = tmp_path / "stance.lua"
    drv.write_text(export_lua.offline_driver(policy, []) + QW_STUB + body)
    out = _run_lua(drv, tmp_path)
    assert "ERR" not in out, out
    lines = [line.split("\t") for line in out.splitlines()]
    return [x for x in lines if x[0] == "STEP"], [x for x in lines if x[0] == "QWSTANCE"], lines


@needs_lua
def test_stance_off_takes_no_action(tmp_path):
    """With LADDER_RISK_STANCE unset the alarm is on, scrolls are held, and nothing is forced or logged."""
    steps, stance, _ = _stance_run(tmp_path, """
scrolls = 3
for d = 0, 9 do step(d, st(100 + 30 * d, 3)) end
LADDER_RISK_STANCE_THRESHOLD = 0.01
for d = 10, 14 do step(d, st(100 + 30 * d, 3)) end
""")
    assert [s[2] for s in steps] == ["-"] * 15 and not stance


@needs_lua
def test_stance_reads_teleport_through_qw_and_keeps_its_cooldown(tmp_path):
    steps, stance, _ = _stance_run(tmp_path, """
LADDER_RISK_STANCE, LADDER_RISK_STANCE_THRESHOLD, LADDER_RISK_STANCE_COOLDOWN = "teleport", 0.04, 20
scrolls = 2
step(0, st(100, 2))                       -- fires: qw reads, 1 left
step(1, st(105, 1))                       -- cooldown
step(2, st(119, 1))                       -- cooldown (19 turns)
step(3, st(120, 1, { teleporting = true }))   -- already teleporting
step(4, st(121, 1, { can_teleport = false })) -- qw cannot read (berserk, confused, ...)
step(5, st(122, 1))                       -- fires: the last scroll
scrolls = 0
step(6, st(150, 0))                       -- none left
LADDER_OVERRIDES = { [7] = { force = "reroll" } }
scrolls = 1
step(7, st(200, 1))                       -- a fixed override comes first
LADDER_RISK_STANCE_THRESHOLD = 0.05
step(8, st(260, 1))                       -- p 0.047 is under the threshold
""")
    assert [(s[1], s[2], s[3], s[4]) for s in steps] == [
        ("0", "teleport", "true", "1"), ("1", "-", "nil", "1"), ("2", "-", "nil", "1"), ("3", "-", "nil", "1"),
        ("4", "-", "nil", "1"), ("5", "teleport", "true", "0"), ("6", "-", "nil", "0"),
        ("7", "reroll", "false", "1"), ("8", "-", "nil", "1")]
    assert [(s[1], s[2], s[4], s[5]) for s in stance] == [("0", "100", "teleport", "1"), ("5", "122", "teleport", "1")]
    assert float(stance[0][3]) == P_TRIVIAL


@needs_lua
def test_stance_that_cannot_act_logs_it_and_does_not_loop(tmp_path):
    """The state says a scroll can be read but qw's own check refuses: qw's cascade decides (acted 0), and the
    stance waits out its cooldown instead of firing at every decision of the same turn."""
    steps, stance, _ = _stance_run(tmp_path, """
LADDER_RISK_STANCE, LADDER_RISK_STANCE_THRESHOLD, LADDER_RISK_STANCE_COOLDOWN = "teleport", 0.04, 0
scrolls, can_read_now = 2, false
for d = 0, 5 do step(d, st(300, 2)) end   -- six decisions, no turn passes
step(6, st(301, 2))
""")
    assert [s[2] for s in steps] == ["teleport", "-", "-", "-", "-", "-", "teleport"]
    assert [s[3] for s in steps][:1] == ["false"]
    assert [(s[1], s[5]) for s in stance] == [("0", "0"), ("6", "0")]


@needs_lua
def test_stance_threshold_by_scrolls_held_and_reserve(tmp_path):
    steps, _, _ = _stance_run(tmp_path, """
LADDER_RISK_STANCE, LADDER_RISK_STANCE_COOLDOWN = "teleport", 20
LADDER_RISK_STANCE_THRESHOLD = { 0.05, 0.045, 0.04 }   -- with 1, 2, 3+ scrolls; p is 0.047
scrolls = 9
step(0, st(100, 1))     -- the last scroll needs 0.05
step(1, st(200, 2))     -- two need 0.045
step(2, st(300, 7))     -- 3+ need 0.04
LADDER_RISK_STANCE_RESERVE = 1
step(3, st(400, 2))     -- one above the reserve: 0.05
step(4, st(500, 3))     -- two above it: 0.045
step(5, st(600, 1))     -- only the reserve
""")
    assert [s[2] for s in steps] == ["-", "teleport", "teleport", "-", "teleport", "-"]


@needs_lua
def test_stance_variants_switch_the_stance_on(tmp_path):
    base = _policy(tmp_path, TRIVIAL, threshold=0.01).read_text()
    for name, stance in export_lua.STANCES.items():
        text = export_lua.stance_policy(base, name, stance)
        assert text.endswith(base) and not [x for x in text.splitlines() if export_lua.rc_block_ends(x)]
        path = tmp_path / export_lua.stance_name(name)
        path.write_text(text)
        _, _, lines = _stance_run(tmp_path, """
print("CFG", LADDER_RISK_STANCE, type(LADDER_RISK_STANCE_THRESHOLD), LADDER_RISK_STANCE_COOLDOWN,
      LADDER_RISK_STANCE_RESERVE)
""", policy=path)
        cfg = [x for x in lines if x[0] == "CFG"]
        want_type = "table" if isinstance(stance["threshold"], (list, tuple)) else "number"
        assert cfg == [["CFG", "teleport", want_type, str(stance["cooldown"]), str(stance["reserve"])]]


@needs_lua
def test_exported_model_matches_python_on_a_logged_game(tmp_path):
    """The real model on a real qw game's QWS lines (skipped without runs/risk/N50-zk and runs/qw/zk-train-400)."""
    repo = Path(__file__).resolve().parents[1]
    model_dir, game = repo / "runs/risk/N50-zk", repo / "runs/qw/zk-train-400/games/100098"
    if not (model_dir / "lgbm.txt").exists() or not game.exists():
        pytest.skip("no local model or game logs")
    states = [s for _, s in dataset._qw_states(game, 0) if s][-600:]
    book, hist = dataset.MonsterBook(), dataset.History()
    np.save(tmp_path / "X.npy", np.stack([dataset.qw_row(s, book, hist)[0] for s in states]))
    _lightgbm(f"""
b = lgb.Booster(model_file={str(model_dir / "lgbm.txt")!r})
np.save("p.npy", b.predict(np.load("X.npy")))
json.dump(b.dump_model(), open("dump.json", "w"))
""", tmp_path)
    want = np.load(tmp_path / "p.npy")
    forest = export_lua.forest_from_dump(json.loads((tmp_path / "dump.json").read_text()))
    model = export_lua.model_lua(forest, threshold=0.0365, horizon=50, source="test")
    (tmp_path / "policy.lua").write_text(export_lua.policy_lua(model))
    drv = tmp_path / "drive.lua"
    drv.write_text(export_lua.offline_driver(tmp_path / "policy.lua", states))
    p, _ = _risk_lines(_run_lua(drv, tmp_path))
    got = np.array([p[i][0] for i in range(len(states))])
    assert np.abs(got - want).max() < 1e-15
