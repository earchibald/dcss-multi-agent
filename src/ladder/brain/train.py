"""Train the brain from a corpus (corpus.py) and write the model file net.py plays from.

Needs torch (`uv sync --group train`); nothing else in the ladder does. The network is the one in
net.py's docstring. Losses:
  - outcomes: squared error on the action that was taken, each component scaled to unit variance;
              rows from forks (forks.py) count `fork_weight` times
  - danger:   cross-entropy on "lost DANGER_DROP of max HP within SOON_TURNS"
  - prior:    cross-entropy on the action taken, on a person's rows when the corpus has any
              (otherwise on every row, which makes it a model of the behaviour that made the data)
One game in five is held out (corpus.VAL_FOLD), so validation rows come from unseen games, and the
weights kept are those of the epoch that did best on them.
"""

from __future__ import annotations

import base64
import json
import math
import time
from pathlib import Path

import numpy as np

from .corpus import DANGER_DROP
from .features import ACTIONS, COMPONENTS
from .net import FORMAT, LAYERS, contract
from .policy import Style


def auc(score: np.ndarray, label: np.ndarray) -> float:
    order = np.argsort(score)
    ranks = np.empty(len(score))
    ranks[order] = np.arange(1, len(score) + 1)
    pos = label > 0.5
    npos, nneg = int(pos.sum()), int((~pos).sum())
    if not npos or not nneg:
        return float("nan")
    return float((ranks[pos].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def fork_regret(group: np.ndarray, fork: np.ndarray, true: np.ndarray, pred: np.ndarray) -> dict:
    """At forked moments, how much value is lost by taking the action the network rates highest?

    `true` and `pred` are the default style's value of what happened and of what was predicted, per row.
    Regret is against the best action tried at that moment; `random` and `recorded` (what the game
    actually did there) are the same loss for those two ways of choosing.
    """
    forked = np.unique(group[(fork > 0) & (group >= 0)])
    regret, rand, recorded, top = [], [], [], []
    for g in forked:
        rows = np.flatnonzero(group == g)
        if len(rows) < 2:
            continue
        best = true[rows].max()
        pick = rows[pred[rows].argmax()]
        regret.append(best - true[pick])
        rand.append(best - true[rows].mean())
        orig = rows[fork[rows] == 0]
        if len(orig):
            recorded.append(best - true[orig[0]])
        top.append(float(true[pick] == best))
    if not regret:
        return {"moments": 0}
    return {"moments": len(regret), "regret": round(float(np.mean(regret)), 4), "random": round(float(np.mean(rand)), 4),
            "recorded": round(float(np.mean(recorded)), 4) if recorded else None, "top1": round(float(np.mean(top)), 3)}


def train(corpus: str | Path, out: str | Path, *, hidden: int = 64, epochs: int = 20, batch: int = 512,
          lr: float = 1e-3, wd: float = 1e-2, dropout: float = 0.2, danger_weight: float = 0.15, prior_weight: float = 0.1, fork_weight: float = 20.0,
          seed: int = 0, note: str = "", log=print, strict: bool = True, save_val: str | Path | None = None) -> dict:
    """Train on `corpus` and write the model to `out`.

    `strict=False` trains on a corpus whose inputs are not this code's contract (a subset of the columns,
    for comparing inputs offline); the model then records the corpus's contract and can't be played.
    `save_val` writes the validation rows' predictions (.npz) for comparisons across models.
    """
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    torch.manual_seed(seed)
    data = np.load(corpus)
    meta = json.loads(Path(f"{corpus}.meta.json").read_text())
    want_contract = contract() if strict else {k: meta.get(k) for k in contract()}
    for key, want in contract().items():
        if strict and meta.get(key) != want:
            raise ValueError(f"corpus was built for another {key}; rebuild it")
    val = data["val"]
    if not val.any() or val.all():                   # too few games to hold any out
        val = np.zeros(len(val), dtype=bool)
        val[::5] = True
    S, MD, A, K = data["self"].shape[1], data["mons"].shape[2], len(ACTIONS), len(COMPONENTS)
    tr = ~val

    self_mean, self_std = data["self"][tr].mean(0), np.maximum(data["self"][tr].std(0), 0.05)
    real = data["mons"][tr][data["mask"][tr] > 0]
    if len(real):
        mon_mean, mon_std = real.mean(0), np.maximum(real.std(0), 0.05)
    else:
        mon_mean, mon_std = np.zeros(MD, dtype=np.float32), np.ones(MD, dtype=np.float32)
    comp_std = np.maximum(data["q"][tr].std(0), 1e-3)
    danger = (data["q"][:, COMPONENTS.index("hp_lost")] >= DANGER_DROP).astype(np.float32)
    humans = bool(data["human"][tr].sum())
    prior_rows = data["human"] if humans else np.ones(len(val), dtype=np.float32)

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            H = hidden
            self.self1 = nn.Linear(S, H)
            self.mon1 = nn.Linear(MD + H, H)
            self.mon2 = nn.Linear(H, H)
            self.trunk = nn.Linear(3 * H, H)
            self.head1 = nn.Linear(H, H)
            self.head2 = nn.Linear(H, A * K)
            self.danger = nn.Linear(H, 1)
            self.prior = nn.Linear(H, A)

        def forward(self, s, mons, mask):
            B, MM = mons.shape[0], mons.shape[1]
            s = F.relu(self.self1(s))
            e = F.relu(self.mon2(F.relu(self.mon1(torch.cat([mons, s[:, None, :].expand(B, MM, hidden)], -1)))))
            m = mask[:, :, None]
            mean = (e * m).sum(1) / m.sum(1).clamp(min=1)
            mx = torch.where(m > 0, e, torch.full_like(e, -1e9)).max(1).values
            mx = torch.where(mask.sum(1, keepdim=True) > 0, mx, torch.zeros_like(mx))
            c = F.dropout(F.relu(self.trunk(torch.cat([s, mean, mx], -1))), dropout, self.training)
            return self.head2(F.relu(self.head1(c))).view(B, A, K), self.danger(c)[:, 0], self.prior(c)

    def tensors(idx):
        return dict(
            s=torch.tensor((data["self"][idx] - self_mean) / self_std),
            mons=torch.tensor((data["mons"][idx] - mon_mean) / mon_std * data["mask"][idx][:, :, None]),
            mask=torch.tensor(data["mask"][idx]), avail=torch.tensor(data["avail"][idx]),
            action=torch.tensor(data["action"][idx]), q=torch.tensor(data["q"][idx]),
            danger=torch.tensor(danger[idx]), prior=torch.tensor(prior_rows[idx]),
            # a fork row is the one place an action's outcome is known against another's from the same state
            w=torch.tensor(1 + fork_weight * data["fork"][idx]))

    T, V = tensors(tr), tensors(val)
    cs = torch.tensor(comp_std)
    net = Net()
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=wd)
    N = int(tr.sum())
    steps = epochs * math.ceil(N / batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=0.1)

    def losses(D, idx):
        q, d, p = net(D["s"][idx], D["mons"][idx], D["mask"][idx])
        taken = q[torch.arange(len(idx)), D["action"][idx]]
        w_q = D["w"][idx]
        lq = ((((taken - D["q"][idx]) / cs) ** 2).mean(-1) * w_q).sum() / w_q.sum()
        ld = F.binary_cross_entropy_with_logits(d, D["danger"][idx])
        logp = F.log_softmax(p.masked_fill(D["avail"][idx] <= 0, -1e9), -1)
        w = D["prior"][idx]
        lp = -(logp[torch.arange(len(idx)), D["action"][idx]] * w).sum() / w.sum().clamp(min=1)
        return lq, ld, lp, taken, d, logp

    @torch.no_grad()
    def validate():
        net.train(False)
        idx = torch.arange(len(V["s"]))
        lq, ld, lp, taken, d, logp = losses(V, idx)
        net.train(True)
        true, pred = V["q"].numpy(), taken.numpy()
        r2 = 1 - ((pred - true) ** 2).mean(0) / true.var(0).clip(1e-9)
        w = V["prior"].numpy() > 0
        hit = (logp.argmax(-1) == V["action"]).numpy()
        w_style = Style().weights()
        forks = fork_regret(data["group"][val], data["fork"][val], true @ w_style, pred @ w_style)
        validate.last = {"pred": pred, "danger": torch.sigmoid(d).numpy()}
        return {"q_loss": float(lq), "danger_bce": float(ld), "prior_ce": float(lp), "forks": forks,
                "danger_auc": auc(torch.sigmoid(d).numpy(), V["danger"].numpy()),
                "danger_rate": float(V["danger"].mean()),
                "prior_top1": float(hit[w].mean()) if w.any() else float("nan"),
                "r2": {c: round(float(x), 3) for c, x in zip(COMPONENTS, r2)}}

    # Rows from one game are much alike and each label is one noisy playthrough, so the network starts
    # memorising games within a few epochs. Keep the weights from the epoch that did best on unseen games.
    t0 = time.time()
    best_loss, best_state, best_epoch = float("inf"), None, 0
    for ep in range(epochs):
        perm = torch.randperm(N)
        total = 0.0
        for i in range(0, N, batch):
            idx = perm[i:i + batch]
            lq, ld, lp, *_ = losses(T, idx)
            loss = lq + danger_weight * ld + prior_weight * lp
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            total += loss.item() * len(idx)
        ev = validate()
        score = ev["q_loss"] + danger_weight * ev["danger_bce"]
        if score < best_loss:
            best_loss, best_epoch = score, ep + 1
            best_state = {k: v.clone() for k, v in net.state_dict().items()}
        if ep % 5 == 4 or ep == epochs - 1:
            log(f"epoch {ep + 1:3d}  train {total / N:.4f}  val q {ev['q_loss']:.4f}  danger auc {ev['danger_auc']:.3f}  "
                f"prior top1 {ev['prior_top1']:.3f}  [{time.time() - t0:.0f}s]")
    net.load_state_dict(best_state)
    ev = validate()
    log(f"kept epoch {best_epoch} of {epochs}")
    if save_val:
        np.savez_compressed(save_val, rows=np.flatnonzero(val), pred=validate.last["pred"],
                            danger=validate.last["danger"])

    def b64(t):
        return base64.b64encode(t.detach().numpy().astype(np.float16).tobytes()).decode()

    layers = {name: {"shape": list(getattr(net, name).weight.shape), "w": b64(getattr(net, name).weight),
                     "b": b64(getattr(net, name).bias)} for name in LAYERS}
    nparams = sum(p.numel() for p in net.parameters())
    model = {
        "format": FORMAT, "version": 1, **want_contract, "hidden": hidden, "dtype": "f16",
        "norm": {"self_mean": self_mean.round(5).tolist(), "self_std": self_std.round(5).tolist(),
                 "mon_mean": mon_mean.round(5).tolist(), "mon_std": mon_std.round(5).tolist()},
        # the policy only trusts an action's predictions once it has seen enough of that action
        "action_counts": {a: int((data["action"][tr] == i).sum()) for i, a in enumerate(ACTIONS)},
        "layers": layers,
        "info": {"trained_at": time.strftime("%Y-%m-%d %H:%M"), "corpus": str(corpus), "rows": N,
                 "val_rows": int(val.sum()), "games": meta.get("games"), "deaths": meta.get("deaths"),
                 "by_source": meta.get("by_source"), "human_prior": humans, "params": int(nparams),
                 "epochs": best_epoch, "note": note, "val": ev},
    }
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model))

    # Parity vectors: raw inputs and the float16-rounded network's outputs, for net.check_parity.
    with torch.no_grad():
        for name in LAYERS:
            L = getattr(net, name)
            L.weight.copy_(L.weight.half().float())
            L.bias.copy_(L.bias.half().float())
        net.train(False)
        rows = np.flatnonzero(val)
        pick = np.random.RandomState(1).choice(rows, min(16, len(rows)), replace=False)
        norm = model["norm"]
        s = (data["self"][pick] - np.float32(norm["self_mean"])) / np.float32(norm["self_std"])
        m = (data["mons"][pick] - np.float32(norm["mon_mean"])) / np.float32(norm["mon_std"]) * data["mask"][pick][:, :, None]
        q, d, p = net(torch.tensor(s), torch.tensor(m.astype(np.float32)), torch.tensor(data["mask"][pick]))
        parity = {"self": data["self"][pick].tolist(), "mons": data["mons"][pick].reshape(len(pick), -1).tolist(),
                  "mask": data["mask"][pick].tolist(), "q": q.numpy().reshape(len(pick), -1).tolist(),
                  "danger": torch.sigmoid(d).numpy().tolist(), "prior": p.numpy().tolist()}
    out.with_suffix(".parity.json").write_text(json.dumps(parity))
    log(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB, {nparams} weights)  val {json.dumps(ev)}")
    return model["info"]
