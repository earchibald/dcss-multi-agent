"""The model file and its forward pass, in numpy. No torch at play time.

    s      = relu(self1 . norm(self))
    e_i    = relu(mon2 . relu(mon1 . [mon_i, s]))      shared weights, one per monster in view
    pool   = [mean_i e_i, max_i e_i]                    zeros when nothing is in view
    c      = relu(trunk . [s, pool])
    q      = head2 . relu(head1 . c)                    actions x outcome components
    danger = sigmoid(danger . c)                        P(a big HP loss soon)
    prior  = prior . c                                  logits: what the recorded player did here

train.py mirrors this exactly; its parity vectors are checked by `check_parity`.
Weights are float16, base64, in JSON.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np

from .features import ACTIONS, COMPONENTS, FEATURE_VERSION, MAX_MONS, MON_DIM, SELF_DIM

FORMAT = "dcss-trained-brain"
LAYERS = ("self1", "mon1", "mon2", "trunk", "head1", "head2", "danger", "prior")


class ModelMismatch(ValueError):
    pass


def contract() -> dict:
    return {"feature_version": FEATURE_VERSION, "self_dim": SELF_DIM, "mon_dim": MON_DIM,
            "max_mons": MAX_MONS, "actions": ACTIONS, "components": COMPONENTS}


class TrainedNet:
    def __init__(self, model: dict, name: str = "model"):
        if model.get("format") != FORMAT:
            raise ModelMismatch(f"{name} is not a {FORMAT} file")
        for key, want in contract().items():
            if model.get(key) != want:
                raise ModelMismatch(f"{name} was trained for another {key} ({model.get(key)!r}, code has {want!r}). Retrain.")
        self.name = name
        self.info = model.get("info", {})
        self.counts: dict[str, int] = model.get("action_counts", {})
        self.norm = {k: np.asarray(v, dtype=np.float32) for k, v in model["norm"].items()}
        dtype = np.float16 if model.get("dtype", "f16") == "f16" else np.float32
        self.w, self.b = {}, {}
        for layer in LAYERS:
            spec = model["layers"][layer]
            self.w[layer] = np.frombuffer(base64.b64decode(spec["w"]), dtype=dtype).astype(np.float32).reshape(spec["shape"])
            self.b[layer] = np.frombuffer(base64.b64decode(spec["b"]), dtype=dtype).astype(np.float32)

    @classmethod
    def load(cls, path: str | Path) -> "TrainedNet":
        path = Path(path)
        return cls(json.loads(path.read_text()), path.stem)

    def _lin(self, layer: str, x: np.ndarray) -> np.ndarray:
        return x @ self.w[layer].T + self.b[layer]

    def forward(self, s: np.ndarray, mons: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
        """One moment in: (q [actions, components], danger, prior logits [actions]) out."""
        relu = lambda x: np.maximum(x, 0)  # noqa: E731
        s = relu(self._lin("self1", (s - self.norm["self_mean"]) / self.norm["self_std"]))
        n = int(mask.sum())
        if n:
            m = (mons[:n] - self.norm["mon_mean"]) / self.norm["mon_std"]
            e = relu(self._lin("mon2", relu(self._lin("mon1", np.concatenate([m, np.tile(s, (n, 1))], 1)))))
            pool = np.concatenate([e.mean(0), e.max(0)])
        else:
            pool = np.zeros(2 * len(s), dtype=np.float32)
        c = relu(self._lin("trunk", np.concatenate([s, pool])))
        q = self._lin("head2", relu(self._lin("head1", c))).reshape(len(ACTIONS), len(COMPONENTS))
        danger = 1 / (1 + np.exp(-self._lin("danger", c)[0]))
        return q, float(danger), self._lin("prior", c)


def check_parity(model_path: str | Path, tol: float = 2e-3) -> float:
    """Largest difference between this forward pass and the vectors train.py saved beside the model."""
    model_path = Path(model_path)
    net = TrainedNet.load(model_path)
    p = json.loads(model_path.with_suffix(".parity.json").read_text())
    worst = 0.0
    for i in range(len(p["self"])):
        q, danger, prior = net.forward(np.asarray(p["self"][i], dtype=np.float32),
                                       np.asarray(p["mons"][i], dtype=np.float32).reshape(MAX_MONS, MON_DIM),
                                       np.asarray(p["mask"][i], dtype=np.float32))
        worst = max(worst, float(np.abs(q.ravel() - np.asarray(p["q"][i])).max()),
                    abs(danger - p["danger"][i]), float(np.abs(prior - np.asarray(p["prior"][i])).max()))
    if worst > tol:
        raise AssertionError(f"numpy and torch disagree by {worst:.5f} (limit {tol})")
    return worst
