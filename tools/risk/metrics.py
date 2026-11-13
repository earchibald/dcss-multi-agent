"""Scores for a probability against 0/1 labels, in numpy: AUROC, average precision, Brier, log loss, calibration."""

from __future__ import annotations

import numpy as np

CAL_BINS = (0.0, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0001)


def auroc(y: np.ndarray, p: np.ndarray) -> float:
    """Area under the ROC curve, ties counted half (the Mann-Whitney statistic)."""
    y = np.asarray(y).astype(bool)
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(p, kind="mergesort")
    ps = np.asarray(p)[order]
    ranks = np.empty(len(ps), dtype=np.float64)
    # average ranks over ties
    _, start, counts = np.unique(ps, return_index=True, return_counts=True)
    avg = start + (counts - 1) / 2.0 + 1
    ranks[order] = np.repeat(avg, counts)
    return float((ranks[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def average_precision(y: np.ndarray, p: np.ndarray) -> float:
    """Sum over positives of precision at their rank (step-wise, as scikit-learn computes it)."""
    y = np.asarray(y).astype(bool)
    if y.sum() == 0:
        return float("nan")
    order = np.argsort(-np.asarray(p), kind="mergesort")
    ps, ys = np.asarray(p)[order], y[order]
    tp = np.cumsum(ys)
    fp = np.cumsum(~ys)
    # evaluate only at the last index of each tied score
    last = np.r_[ps[1:] != ps[:-1], True]
    tp, fp = tp[last], fp[last]
    precision = tp / (tp + fp)
    recall = tp / y.sum()
    return float(np.sum(np.diff(np.r_[0.0, recall]) * precision))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, dtype=np.float64) - y) ** 2))


def logloss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(np.asarray(p, dtype=np.float64), 1e-7, 1 - 1e-7)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def calibration(y: np.ndarray, p: np.ndarray, bins=CAL_BINS) -> list[dict]:
    """Per bin of predicted risk: rows, mean predicted, observed rate."""
    idx = np.digitize(p, bins[1:-1])
    out = []
    for b in range(len(bins) - 1):
        m = idx == b
        if m.sum() == 0:
            continue
        out.append({"lo": bins[b], "hi": min(bins[b + 1], 1.0), "n": int(m.sum()),
                    "pred": float(np.mean(p[m])), "obs": float(np.mean(y[m]))})
    return out


def ece(y: np.ndarray, p: np.ndarray, bins=CAL_BINS) -> float:
    """Expected calibration error over the bins above, weighted by rows."""
    cal = calibration(y, p, bins)
    n = sum(c["n"] for c in cal)
    return float(sum(c["n"] * abs(c["pred"] - c["obs"]) for c in cal) / max(n, 1))


def scores(y: np.ndarray, p: np.ndarray) -> dict:
    return {"n": int(len(y)), "pos": int(np.sum(y)), "base": float(np.mean(y)) if len(y) else float("nan"),
            "auroc": auroc(y, p), "ap": average_precision(y, p), "brier": brier(y, p), "logloss": logloss(y, p),
            "ece": ece(y, p), "mean_pred": float(np.mean(p)) if len(p) else float("nan")}
