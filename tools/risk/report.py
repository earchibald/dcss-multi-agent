"""Read the death-risk models' predictions: scores by source and slice, calibration, early warning,
feature importance and leakage checks.

    uv run --group risk python tools/risk/report.py scores --dir runs/risk/N50 --split val
    uv run --group risk python tools/risk/report.py early --dir runs/risk/N50 --split test --fpr 0.05
    uv run --group risk python tools/risk/report.py importance --dir runs/risk/N50
    uv run --group risk python tools/risk/report.py leakage --horizon 50

`--split test` reads preds_test.npz, which train.py writes only with --final.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset import F_INDEX, HOLDOUT_SEED, OUT, labels  # noqa: E402
from metrics import auroc, calibration, scores  # noqa: E402
from train import load, splits  # noqa: E402

MODELS = ("baseline", "lgbm", "mlp")
SOURCES = {"brain": 0, "qw": 1}
EPISODE_GAP = 10    # turns without an alarm that end an alarm episode


def _preds(directory: Path, split: str) -> dict:
    return dict(np.load(directory / f"preds_{split}.npz"))


def slices(d: dict, idx: np.ndarray) -> dict[str, np.ndarray]:
    src, deep = d["source"][idx], d["deep"][idx]
    out = {}
    for name, s in SOURCES.items():
        out[f"{name} all"] = src == s
        out[f"{name} deep"] = (src == s) & deep
    out["all"] = np.ones(len(idx), dtype=bool)
    return out


def cmd_scores(d: dict, directory: Path, split: str) -> dict:
    p = _preds(directory, split)
    idx, y = p["idx"], p["y"].astype(np.int8)
    games = d["game"][idx]
    res = {}
    print(f"{'slice':12s} {'model':8s} {'games':>6s} {'deaths':>6s} {'rows':>8s} {'pos':>6s} {'base':>7s} "
          f"{'AUROC':>6s} {'AP':>6s} {'Brier':>8s} {'logloss':>8s} {'ECE':>7s} {'mean p':>7s}")
    for sl, m in slices(d, idx).items():
        if m.sum() == 0:
            continue
        n_games = len(np.unique(games[m]))
        n_deaths = len(np.unique(games[m & (y == 1)]))
        for model in MODELS:
            if model not in p:
                continue
            s = scores(y[m], p[model][m])
            s.update(games=n_games, deaths=n_deaths)
            res[f"{sl}|{model}"] = s
            print(f"{sl:12s} {model:8s} {n_games:6d} {n_deaths:6d} {s['n']:8d} {s['pos']:6d} {s['base']:7.4f} "
                  f"{s['auroc']:6.3f} {s['ap']:6.3f} {s['brier']:8.5f} {s['logloss']:8.5f} {s['ece']:7.4f} "
                  f"{s['mean_pred']:7.4f}")
    print("\ncalibration (rows, mean predicted -> observed)")
    for name, s in SOURCES.items():
        m = d["source"][idx] == s
        for model in MODELS:
            if model not in p:
                continue
            cal = calibration(y[m], p[model][m])
            res[f"cal|{name}|{model}"] = cal
            cells = "  ".join(f"[{c['lo']:.3g},{c['hi']:.3g}) n={c['n']} {c['pred']:.3f}->{c['obs']:.3f}" for c in cal)
            print(f"{name:6s} {model:8s} {cells}")
    (directory / f"scores_{split}.json").write_text(json.dumps(res, indent=1))
    return res


def cmd_bootstrap(d: dict, directory: Path, split: str, n_boot: int = 100) -> dict:
    """AUROC per model with a 90% interval from resampling whole games, and the trees' gain over HP."""
    p = _preds(directory, split)
    idx, y = p["idx"], p["y"].astype(np.int8)
    games = d["game"][idx]
    rng = np.random.default_rng(0)
    res = {}
    for sl, m in slices(d, idx).items():
        if sl.startswith("brain deep") or m.sum() == 0:
            continue
        g_ids = np.unique(games[m])
        rows_of = {g: np.flatnonzero(m & (games == g)) for g in g_ids}
        draws = {k: [] for k in MODELS if k in p}
        for _ in range(n_boot):
            pick = np.concatenate([rows_of[g] for g in rng.choice(g_ids, len(g_ids))])
            for k in draws:
                draws[k].append(auroc(y[pick], p[k][pick]))
        gain = np.asarray(draws["lgbm"]) - np.asarray(draws["baseline"])
        res[sl] = {k: [float(np.quantile(v, 0.05)), float(np.quantile(v, 0.95))] for k, v in draws.items()}
        res[sl]["lgbm_minus_baseline"] = [float(np.quantile(gain, 0.05)), float(np.quantile(gain, 0.95))]
        print(sl, json.dumps(res[sl]))
    (directory / f"bootstrap_{split}.json").write_text(json.dumps(res, indent=1))
    return res


def threshold_for(p0: np.ndarray, fpr: float) -> float:
    """The risk above which `fpr` of the non-death moments `p0` would raise an alarm."""
    return float(np.quantile(p0, 1 - fpr))


def cmd_early(d: dict, directory: Path, split: str, fpr: float, model: str) -> dict:
    """For games that end in death: how long before the death the risk crosses an alarm threshold.

    The threshold is set per source on the validation moments labelled 0 (alive N turns later) so that
    `fpr` of them would alarm, then applied to `split` unchanged.
    """
    pv, p = _preds(directory, "val"), _preds(directory, split)
    res = {}
    for name, s in SOURCES.items():
        mv = d["source"][pv["idx"]] == s
        thr = threshold_for(pv[model][mv & (pv["y"] == 0)], fpr)
        m = d["source"][p["idx"]] == s
        idx, risk, y = p["idx"][m], p[model][m], p["y"][m]
        fpr_here = float(np.mean(risk[y == 0] >= thr))
        tpr_here = float(np.mean(risk[y == 1] >= thr))
        games = d["game"][idx]
        first_200, final_ep, at_end = [], [], 0
        ahead = {k: 0 for k in (5, 10, 20, 50, 100)}
        n_deaths = 0
        for g in np.unique(games[d["died"][idx]]):
            gm = games == g
            t = d["turn"][idx[gm]]
            order = np.argsort(t, kind="mergesort")
            t, r = t[order], risk[gm][order]
            left = d["end_turn"][idx[gm]][order] - t
            n_deaths += 1
            on = r >= thr
            at_end += bool(on[-1])
            # an alarm at least k turns before the death (and no more than 200)
            for k in ahead:
                ahead[k] += bool(np.any(on & (left >= k) & (left <= 200)))
            w = on & (left <= 200)
            first_200.append(float(left[np.argmax(w)]) if w.any() else -1.0)
            # the final alarm episode: alarmed moments no more than EPISODE_GAP turns apart, reaching
            # within EPISODE_GAP turns of the death; its start is the warning's lead
            lead = -1.0
            on_left = left[on]
            if len(on_left) and on_left[-1] <= EPISODE_GAP:
                k = len(on_left) - 1
                while k > 0 and on_left[k - 1] - on_left[k] <= EPISODE_GAP:
                    k -= 1
                lead = float(on_left[k])
            final_ep.append(lead)
        fe, f2 = np.asarray(final_ep), np.asarray(first_200)
        q = lambda a: {f"p{int(x * 100)}": float(np.quantile(a, x)) for x in (0.1, 0.25, 0.5, 0.75, 0.9)} if len(a) else {}  # noqa: E731
        res[name] = {"threshold": thr, "fpr_val": fpr, f"fpr_{split}": fpr_here, f"recall_{split}": tpr_here,
                     "deaths": n_deaths, "alarm_at_last_moment": at_end,
                     "alarm_k_to_200_turns_before": ahead,
                     "final_episode_lead_turns": q(fe[fe >= 0]), "deaths_with_final_episode": int((fe >= 0).sum()),
                     "first_alarm_in_last_200_turns": q(f2[f2 >= 0])}
        print(f"{name}: threshold {thr:.4f} (val FPR {fpr}); {split} FPR {fpr_here:.3f}, recall {tpr_here:.3f}; "
              f"{n_deaths} deaths, alarm on at the last logged moment in {at_end}")
        print("   deaths with an alarm k..200 turns before: " + ", ".join(f"k={k}: {v}" for k, v in ahead.items()))
        print(f"   final alarm episode ({int((fe >= 0).sum())} deaths), lead in turns: {res[name]['final_episode_lead_turns']}")
        print(f"   first alarm in the last 200 turns, turns before death: {res[name]['first_alarm_in_last_200_turns']}")
    (directory / f"early_{split}_{model}_fpr{fpr}.json").write_text(json.dumps(res, indent=1))
    return res


def cmd_importance(directory: Path, top: int) -> list:
    import lightgbm as lgb

    b = lgb.Booster(model_file=str(directory / "lgbm.txt"))
    gain = b.feature_importance("gain")
    split = b.feature_importance("split")
    names = b.feature_name()
    order = np.argsort(-gain)
    total = gain.sum()
    out = []
    for i in order[:top]:
        out.append({"feature": names[i], "gain_share": float(gain[i] / total), "splits": int(split[i])})
        print(f"{names[i]:24s} {gain[i] / total:6.3f} {split[i]:6d}")
    (directory / "importance.json").write_text(json.dumps(out, indent=1))
    return out


def cmd_leakage(d: dict, horizon: int) -> dict:
    """Checks that the label can't be read off the row in a way play couldn't.

    1. Structural: no row after its game's end, no row at 0 HP, test seeds never in train or validation.
    2. Every feature alone (AUROC on validation, either direction): anything near 1 would be suspect.
    3. The clock: trees on the game turn alone, and the full model with the turn added (it is left out).
    """
    import lightgbm as lgb

    from train import LGB_PARAMS

    y = labels(d, horizon)
    sp = splits(d, y, 1.0)
    X = d["X"]
    res = {"rows_after_end": int((d["turn"] > d["end_turn"]).sum()),
           "rows_at_zero_hp": int((X[:, F_INDEX["hp"]] <= 0).sum()),
           "test_seeds_in_train_or_val": int(np.isin(d["seed"][sp["train"] | sp["val"]],
                                                     d["seed"][d["seed"] >= HOLDOUT_SEED]).sum())}
    va, tr = sp["val"], sp["train"]
    single = {}
    for j, f in enumerate(d["features"]):
        for name, s in SOURCES.items():
            m = va & (d["source"] == s)
            x = np.nan_to_num(X[m, j], nan=0.0)
            a = auroc(y[m], x)
            single[f"{f}|{name}"] = max(a, 1 - a) if a == a else float("nan")
    res["single_feature_auroc_top"] = dict(sorted(single.items(), key=lambda kv: -np.nan_to_num(kv[1]))[:15])
    params = dict(LGB_PARAMS)
    for name, s in SOURCES.items():
        mt, mv = tr & (d["source"] == s), va & (d["source"] == s)
        t = lgb.Dataset(d["turn"][mt, None], y[mt])
        b = lgb.train(params, t, num_boost_round=200)
        res[f"turn_only_auroc|{name}"] = auroc(y[mv], b.predict(d["turn"][mv, None]))
    # the full model with and without the game turn as a feature, same rounds, scored per source
    for with_turn in (False, True):
        Xt = np.c_[X[tr], d["turn"][tr]] if with_turn else X[tr]
        Xv = np.c_[X[va], d["turn"][va]] if with_turn else X[va]
        b = lgb.train(params, lgb.Dataset(Xt, y[tr]), num_boost_round=400)
        pv = b.predict(Xv)
        for name, s in SOURCES.items():
            m = d["source"][va] == s
            res[f"full_model_auroc|{'with' if with_turn else 'without'}_turn|{name}"] = auroc(y[va][m], pv[m])
    for k, v in res.items():
        print(k, json.dumps(v, indent=1) if isinstance(v, dict) else v)
    (OUT / f"leakage_N{horizon}.json").write_text(json.dumps(res, indent=1))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scores", "early", "importance", "bootstrap"):
        p = sub.add_parser(name)
        p.add_argument("--dir", type=Path, default=OUT / "N50")
        p.add_argument("--split", default="val", choices=("val", "test"))
        p.add_argument("--fpr", type=float, default=0.05)
        p.add_argument("--model", default="lgbm")
        p.add_argument("--top", type=int, default=20)
    p = sub.add_parser("leakage")
    p.add_argument("--horizon", type=int, default=50)
    args = ap.parse_args()
    if args.cmd == "importance":
        cmd_importance(args.dir, args.top)
        return
    d = load()
    if args.cmd == "scores":
        cmd_scores(d, args.dir, args.split)
    elif args.cmd == "bootstrap":
        cmd_bootstrap(d, args.dir, args.split)
    elif args.cmd == "early":
        cmd_early(d, args.dir, args.split, args.fpr, args.model)
    else:
        cmd_leakage(d, args.horizon)


if __name__ == "__main__":
    main()
