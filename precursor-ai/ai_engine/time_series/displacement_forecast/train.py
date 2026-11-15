"""Training, baselines and evaluation on identical chronological splits."""
from __future__ import annotations

import time

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.linear_model import Ridge

from . import models as M
from .dataset import SampleSet, Scaler, crossing_labels

QUANTILES = torch.tensor([0.1, 0.5, 0.9])


def pinball(q, y):
    qs = QUANTILES.to(q.device)
    e = y[:, None] - q
    return torch.maximum(qs * e, (qs - 1) * e).mean()


def seed_all(seed):
    import random
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)


# ---------------------------------------------------------------- baselines
def baseline_predictions(ss: SampleSet) -> dict:
    """Non-learned forecasts in mm over the actual horizon h."""
    fi = {n: i for i, n in enumerate(ss.feat_names)}
    inc, dt, ok = ss.X[..., fi["inc_mm"]], ss.X[..., fi["dt_days"]], ss.X[..., fi["valid"]] > 0
    h = ss.h_days
    last_vel = inc[:, -1] / dt[:, -1]
    win_vel = (inc * ok).sum(1) / np.maximum((dt * ok).sum(1), 1e-6)
    return {
        "zero_motion": np.zeros_like(h),
        "persistence_last_interval": last_vel * h,
        "constant_velocity_window": win_vel * h,
    }


def ridge_baseline(tr: SampleSet, te: SampleSet, sc: Scaler, alpha=1.0):
    Xtr, Str = sc.tx(tr)
    Xte, Ste = sc.tx(te)
    m = Ridge(alpha=alpha).fit(np.concatenate([Xtr.reshape(len(tr), -1), Str], 1), sc.ty(tr.y))
    return sc.iy(m.predict(np.concatenate([Xte.reshape(len(te), -1), Ste], 1)))


# ---------------------------------------------------------------- DL
def _tensors(ss, sc, device):
    X, S = sc.tx(ss)
    return (torch.from_numpy(X).to(device), torch.from_numpy(S).to(device),
            torch.from_numpy(sc.ty(ss.y)).to(device))


def fit_model(name: str, tr: SampleSet, va: SampleSet, sc: Scaler, *, feat_idx=None, multitask=False,
              tau=None, seed=0, hidden=64, dropout=0.1, lr=1e-3, wd=1e-4, batch=4096, max_epochs=40, patience=5,
              w_huber=1.0, w_q=1.0, w_cls=0.5, device="cuda", verbose=False):
    """Masked-by-construction training (invalid samples were dropped at build time)."""
    seed_all(seed)
    Xtr, Str, ytr = _tensors(tr, sc, device)
    Xva, Sva, yva = _tensors(va, sc, device)
    if feat_idx is not None:
        Xtr, Xva = Xtr[..., feat_idx], Xva[..., feat_idx]
    ctr = cva = None
    pos_weight = None
    if multitask:
        ctr = torch.from_numpy(crossing_labels(tr, tau)).to(device)
        cva = torch.from_numpy(crossing_labels(va, tau)).to(device)
        npos = float(ctr.sum())
        pos_weight = torch.tensor((len(ctr) - npos) / max(npos, 1.0), device=device)  # train prevalence
    model = M.build(name, Xtr.shape[1], Xtr.shape[2], Str.shape[1], multitask, hidden, dropout).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)

    def loss_fn(q, c, y, lab):
        L = w_huber * F.huber_loss(q[:, 1], y, delta=1.0) + w_q * pinball(q, y)
        if multitask:
            L = L + w_cls * F.binary_cross_entropy_with_logits(c, lab, pos_weight=pos_weight)
        return L

    best, best_state, bad, hist = np.inf, None, 0, []
    t0 = time.time()
    n = len(ytr)
    g = torch.Generator(device="cpu").manual_seed(seed)
    for ep in range(max_epochs):
        model.train()
        perm = torch.randperm(n, generator=g).to(device)
        tl = 0.0
        for i in range(0, n, batch):
            b = perm[i:i + batch]
            q, c = model(Xtr[b], Str[b])
            L = loss_fn(q, c, ytr[b], ctr[b] if multitask else None)
            opt.zero_grad(set_to_none=True)
            L.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tl += float(L.detach()) * len(b)
        model.eval()
        with torch.no_grad():
            vl, m_ = 0.0, len(yva)
            for i in range(0, m_, 65536):
                q, c = model(Xva[i:i + 65536], Sva[i:i + 65536])
                vl += float(loss_fn(q, c, yva[i:i + 65536], cva[i:i + 65536] if multitask else None)) * len(q)
            vl /= max(m_, 1)
        hist.append((tl / n, vl))
        if verbose:
            print(f"  ep{ep:02d} train {tl / n:.4f} val {vl:.4f}")
        if vl < best - 1e-5:
            best, bad = vl, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    model.load_state_dict(best_state)
    return model, {"history": hist, "epochs": len(hist), "best_val_loss": best,
                   "train_seconds": time.time() - t0, "n_params": M.n_params(model),
                   "pos_weight": float(pos_weight) if pos_weight is not None else None}


@torch.no_grad()
def predict(model, ss: SampleSet, sc: Scaler, feat_idx=None, device="cuda"):
    model.eval()
    X, S = sc.tx(ss)
    X, S = torch.from_numpy(X).to(device), torch.from_numpy(S).to(device)
    if feat_idx is not None:
        X = X[..., feat_idx]
    qs, cs = [], []
    t0 = time.time()
    for i in range(0, len(X), 65536):
        q, c = model(X[i:i + 65536], S[i:i + 65536])
        qs.append(q.cpu()); cs.append(torch.sigmoid(c).cpu())
    lat = (time.time() - t0) / max(len(X), 1) * 1e6
    q = sc.iy(torch.cat(qs).numpy())
    return q, torch.cat(cs).numpy(), lat


# ---------------------------------------------------------------- metrics
def regression_metrics(y, p):
    e = p - y
    return {"MAE_mm": float(np.mean(np.abs(e))), "RMSE_mm": float(np.sqrt(np.mean(e ** 2))),
            "MedAE_mm": float(np.median(np.abs(e))), "n": int(len(y))}


def interval_metrics(y, q):
    return {"cov_q10_q90": float(np.mean((y >= q[:, 0]) & (y <= q[:, 2]))),
            "width_q10_q90_mm": float(np.mean(q[:, 2] - q[:, 0]))}


def crossing_metrics(true_lab, pred_lab, score=None):
    from sklearn.metrics import average_precision_score
    tp = int(((true_lab == 1) & (pred_lab == 1)).sum())
    fp = int(((true_lab == 0) & (pred_lab == 1)).sum())
    fn = int(((true_lab == 1) & (pred_lab == 0)).sum())
    P = tp / (tp + fp) if tp + fp else 0.0
    R = tp / (tp + fn) if tp + fn else 0.0
    out = {"precision": P, "recall": R, "F1": 2 * P * R / (P + R) if P + R else 0.0,
           "TP": tp, "FP": fp, "FN": fn, "positives": int(true_lab.sum()), "prevalence": float(true_lab.mean())}
    if score is not None and true_lab.sum() > 0:
        out["PR_AUC"] = float(average_precision_score(true_lab, score))
    return out


def stratified(y, p, groups: dict):
    return {g: regression_metrics(y[m], p[m]) for g, m in groups.items() if m.sum() > 0}
