"""Train the death-risk models on runs/risk/rows.npz: HP-fraction logistic, gradient-boosted trees, small MLP.

    uv run --group train --group risk python tools/risk/train.py --horizon 50            # validation only
    uv run --group train --group risk python tools/risk/train.py --horizon 50 --final    # + held-out test

Splits are by dungeon seed, never by row:

- test: seeds >= 500000 (the held-out dungeons). Predicted only with --final, once the choices are made.
- validation: training seeds with crc32(seed) % VAL_FOLD == 0, original games only (no forks), for early
  stopping and every choice made before the test.
- train: the other training seeds, with their forks at weight --fork-weight (0 leaves them out).

Writes runs/risk/N<h>[-tag]/: lgbm.txt, mlp.pt, baseline.json, preds_val.npz (and preds_test.npz).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset import HOLDOUT_SEED, OUT, labels  # noqa: E402
from metrics import scores  # noqa: E402

VAL_FOLD = 6
LGB_PARAMS = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 1000,
              "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
              "verbose": -1, "num_threads": 14, "seed": 1}
MLP = {"lr": 5e-4, "dropout": 0.2, "wd": 1e-3}


def load(path: Path = OUT / "rows.npz") -> dict:
    return dict(np.load(path))


def val_seeds(seed: np.ndarray) -> np.ndarray:
    """Which rows' seeds are validation seeds (a fixed hash of the seed)."""
    uniq = np.unique(seed)
    pick = np.array([zlib.crc32(str(int(s)).encode()) % VAL_FOLD == 0 for s in uniq])
    return np.isin(seed, uniq[pick])


def splits(d: dict, y: np.ndarray, fork_weight: float) -> dict[str, np.ndarray]:
    seed = d["seed"]
    is_val = val_seeds(seed)
    train_pool = (seed >= 0) & (seed < HOLDOUT_SEED)
    known = y >= 0
    out = {
        "train": train_pool & ~is_val & known & (~d["fork"] | (fork_weight > 0)),
        "val": train_pool & is_val & ~d["fork"] & known,
        "test": (seed >= HOLDOUT_SEED) & known,
    }
    # the held-out dungeons never reach training or validation
    assert not np.isin(seed[out["train"] | out["val"]], seed[out["test"]]).any()
    assert (seed[out["train"] | out["val"]] < HOLDOUT_SEED).all()
    assert not np.isin(seed[out["train"]], seed[out["val"]]).any()
    return out


# --- baseline: logistic on HP fraction, one fit per source -------------------------------------------


def fit_logistic(x: np.ndarray, y: np.ndarray, iters: int = 30) -> np.ndarray:
    A = np.c_[np.ones(len(x)), x].astype(np.float64)
    w = np.zeros(A.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-A @ w))
        g = A.T @ (y - p)
        H = (A * (p * (1 - p))[:, None]).T @ A + 1e-6 * np.eye(A.shape[1])
        step = np.linalg.solve(H, g)
        w += step
        if np.abs(step).max() < 1e-8:
            break
    return w


def baseline_predict(coef: dict, hp_frac: np.ndarray, source: np.ndarray) -> np.ndarray:
    p = np.zeros(len(hp_frac))
    for s, w in coef.items():
        m = source == int(s)
        p[m] = 1 / (1 + np.exp(-(w[0] + w[1] * hp_frac[m])))
    return p


# --- MLP -----------------------------------------------------------------------------------------------


class Prep:
    """Signed log1p on heavy-tailed columns, then standardise; NaN (a field this source lacks) -> 0."""

    def __init__(self, X: np.ndarray):
        mx = np.nanmax(np.abs(X), axis=0)
        self.log = np.nan_to_num(mx, nan=0.0) > 10
        Z = self._tail(X)
        self.mu = np.nan_to_num(np.nanmean(Z, axis=0))
        self.sd = np.nan_to_num(np.nanstd(Z, axis=0), nan=1.0)
        self.sd[self.sd < 1e-6] = 1.0

    def _tail(self, X: np.ndarray) -> np.ndarray:
        Z = X.astype(np.float32, copy=True)
        Z[:, self.log] = np.sign(Z[:, self.log]) * np.log1p(np.abs(Z[:, self.log]))
        return Z

    def __call__(self, X: np.ndarray) -> np.ndarray:
        Z = (self._tail(X) - self.mu) / self.sd
        return np.clip(np.nan_to_num(Z, nan=0.0), -6, 6).astype(np.float32)

    def state(self) -> dict:
        return {"log": self.log.tolist(), "mu": self.mu.tolist(), "sd": self.sd.tolist()}


def train_mlp(Xtr, ytr, wtr, Xva, yva, epochs: int = 12, seed: int = 1):
    import torch
    from torch import nn

    torch.manual_seed(seed)
    torch.set_num_threads(14)
    net = nn.Sequential(nn.Linear(Xtr.shape[1], 256), nn.ReLU(), nn.Dropout(MLP["dropout"]),
                        nn.Linear(256, 128), nn.ReLU(), nn.Dropout(MLP["dropout"]), nn.Linear(128, 1))
    opt = torch.optim.AdamW(net.parameters(), lr=MLP["lr"], weight_decay=MLP["wd"])
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    Xt = torch.from_numpy(Xtr)
    yt = torch.from_numpy(ytr.astype(np.float32))
    wt = torch.from_numpy(wtr.astype(np.float32))
    Xv = torch.from_numpy(Xva)
    loss_fn = nn.BCEWithLogitsLoss(reduction="none")
    best, best_state, bad = np.inf, None, 0
    rng = np.random.default_rng(seed)
    for ep in range(epochs):
        net.train(True)
        perm = torch.from_numpy(rng.permutation(len(Xt)))
        for i in range(0, len(perm), 8192):
            b = perm[i:i + 8192]
            opt.zero_grad()
            loss = (loss_fn(net(Xt[b]).squeeze(1), yt[b]) * wt[b]).sum() / wt[b].sum()
            loss.backward()
            opt.step()
        sched.step()
        pv = predict_mlp(net, Xv)
        vl = scores(yva, pv)["logloss"]
        print(f"  mlp epoch {ep + 1}: val logloss {vl:.5f}", flush=True)
        if vl < best - 1e-5:
            best, bad = vl, 0
            best_state = {k: v.clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= 3:
                break
    net.load_state_dict(best_state)
    return net


def predict_mlp(net, X) -> np.ndarray:
    import torch

    net.train(False)
    X = X if isinstance(X, torch.Tensor) else torch.from_numpy(X)
    out = []
    with torch.no_grad():
        for i in range(0, len(X), 65536):
            out.append(torch.sigmoid(net(X[i:i + 65536]).squeeze(1)).numpy())
    return np.concatenate(out) if out else np.zeros(0)


# --- main ----------------------------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--horizon", type=int, default=50)
    ap.add_argument("--fork-weight", type=float, default=1.0, help="weight of fork rows (0 leaves them out)")
    ap.add_argument("--tag", default="", help="suffix for the output directory")
    ap.add_argument("--models", default="baseline,lgbm",
                    help="baseline,lgbm and/or mlp. LightGBM and torch each load their own OpenMP and can't "
                         "share a process on macOS, so run mlp as a second invocation")
    ap.add_argument("--final", action="store_true", help="also predict the held-out test seeds")
    ap.add_argument("--lgb", nargs="*", default=[], help="LightGBM overrides, key=value")
    ap.add_argument("--mlp", nargs="*", default=[], help="MLP overrides (lr, dropout, wd), key=value")
    ap.add_argument("--drop", default="", help="ablation: blank the features starting with these prefixes")
    args = ap.parse_args()
    for kv in args.lgb:
        k, _, v = kv.partition("=")
        LGB_PARAMS[k] = type(LGB_PARAMS.get(k, 1.0))(v)
    for kv in args.mlp:
        k, _, v = kv.partition("=")
        MLP[k] = float(v)
    models = args.models.split(",")

    d = load()
    X, names = d["X"], [str(f) for f in d["features"]]
    if args.drop:
        gone = [i for i, f in enumerate(names) if any(f.startswith(p) for p in args.drop.split(","))]
        X[:, gone] = np.nan                    # an ablation: these columns say nothing
        print(f"dropped {len(gone)} features: {', '.join(names[i] for i in gone)}")
    y = labels(d, args.horizon)
    sp = splits(d, y, args.fork_weight)
    w = np.where(d["fork"], args.fork_weight, 1.0)
    out = OUT / (f"N{args.horizon}" + (f"-{args.tag}" if args.tag else ""))
    out.mkdir(parents=True, exist_ok=True)
    tr, va, te = sp["train"], sp["val"], sp["test"]
    print(f"rows train {tr.sum()} val {va.sum()} test {te.sum()}; base rate train {y[tr].mean():.4f} "
          f"val {y[va].mean():.4f}", flush=True)
    info_path = out / "train.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    info.update({"horizon": args.horizon, "fork_weight": args.fork_weight,
                 "rows": {k: int(v.sum()) for k, v in sp.items()},
                 "games": {k: int(len(np.unique(d["game"][v]))) for k, v in sp.items()}})
    predictors = {}

    if "baseline" in models:
        coef = {str(s): fit_logistic(d["hp_frac"][tr & (d["source"] == s)], y[tr & (d["source"] == s)]).tolist()
                for s in (0, 1)}
        (out / "baseline.json").write_text(json.dumps(coef))
        info["baseline_coef"] = coef
        predictors["baseline"] = lambda m: baseline_predict(coef, d["hp_frac"][m], d["source"][m])

    if "lgbm" in models:
        import lightgbm as lgb

        t0 = time.time()
        dtr = lgb.Dataset(X[tr], y[tr], weight=w[tr], feature_name=names, free_raw_data=True)
        dva = lgb.Dataset(X[va], y[va], reference=dtr)
        booster = lgb.train(LGB_PARAMS, dtr, num_boost_round=3000, valid_sets=[dva], valid_names=["val"],
                            callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(200)])
        booster.save_model(str(out / "lgbm.txt"), num_iteration=booster.best_iteration)
        info["lgbm_params"] = LGB_PARAMS
        info["lgbm_best_iteration"] = booster.best_iteration
        info["lgbm_seconds"] = round(time.time() - t0)
        print(f"lgbm: {booster.best_iteration} rounds in {info['lgbm_seconds']} s", flush=True)
        predictors["lgbm"] = lambda m: booster.predict(X[m], num_iteration=booster.best_iteration)

    if "mlp" in models:
        import torch

        t0 = time.time()
        prep = Prep(X[tr])
        net = train_mlp(prep(X[tr]), y[tr], w[tr], prep(X[va]), y[va])
        torch.save({"state": net.state_dict(), "prep": prep.state(), "features": names}, out / "mlp.pt")
        info["mlp_seconds"] = round(time.time() - t0)
        predictors["mlp"] = lambda m: predict_mlp(net, prep(X[m]))

    def save(split: str, mask: np.ndarray) -> dict:
        """Add this run's models' predictions to preds_<split>.npz (other models' columns are kept)."""
        path = out / f"preds_{split}.npz"
        p = dict(np.load(path)) if path.exists() else {}
        if "idx" in p and not np.array_equal(p["idx"], np.flatnonzero(mask)):
            p = {}                             # rows changed (a rebuilt dataset): start again
        p.update(idx=np.flatnonzero(mask), y=y[mask])
        p.update({k: f(mask).astype(np.float32) for k, f in predictors.items()})
        np.savez(path, **p)
        return p

    pv = save("val", va)
    info.setdefault("val", {}).update({m: scores(pv["y"], pv[m]) for m in predictors})
    for m in predictors:
        s = info["val"][m]
        print(f"val {m:8s} auroc {s['auroc']:.4f} ap {s['ap']:.4f} brier {s['brier']:.5f} "
              f"logloss {s['logloss']:.5f} ece {s['ece']:.5f}")
    if args.final:
        save("test", te)
        info.setdefault("test_predicted", []).extend(m for m in predictors)
    info_path.write_text(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
