#!/usr/bin/env python3
"""Measure the L12 model comparison on NASA C-MAPSS FD001 turbofan RUL.

Every number the L12 notes and slides quote about the five models comes from here.
make_figures.py reads the results this writes (.cache/results/*.json) rather than
retraining, so figures can be redrawn without an hour of CPU.

    python3 experiments.py cv          # 5 seeds x 5 engine-grouped folds, every model
    python3 experiments.py test        # train on all 100 engines, score the official test set
    python3 experiments.py cv --models cnn gru --seeds 0 1
    python3 experiments.py order       # does each sequence model use the order of cycles?

Design, and the choices a reader should know about:

  - Channels: the 14 sensors that vary in FD001 (2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15,
    17, 20, 21). The three operating settings and sensors 1, 5, 6, 10, 16, 18, 19 are
    constant or nearly so, because FD001 has a single operating condition.
  - Windows of 30 cycles, one per end cycle, never crossing an engine.
  - Target: piecewise-linear RUL, min(cycles to failure, 125). The cap is a labelling
    assumption from the benchmark literature, not a property of the engines.
  - Scaling: per-channel mean and std fitted on the training engines of each fold only.
    The target is divided by the cap, so every network regresses a number in [0, 1].
  - Splits: GroupKFold(5) by engine. Early stopping never sees the scoring fold: 15% of
    the *training* engines are held out as an inner validation set, and the checkpoint
    with the best inner-validation loss is the one scored.
  - One training recipe for every network, so the comparison is between architectures
    rather than between amounts of tuning: Adam, lr 1e-3, weight decay 1e-4, batch 256,
    cosine schedule over at most 60 epochs, patience 10, gradient norm clipped at 1.0.
  - Scored two ways. `cv` gives the RMSE over every window of the held-out engines. `test`
    uses the benchmark's own protocol: the 100 test engines are cut off before failure, and
    each gets one prediction at its last observed cycle, scored against RUL_FD001.txt. (The
    last window of a *training* engine is its failure cycle, RUL 0, so a last-window score
    inside the CV would be trivially small and is not reported.)
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold

HERE = Path(__file__).parent
DATA = HERE / ".cache" / "CMAPSS"
RESULTS = HERE / ".cache" / "results"
COLS = (["unit", "cycle"] + [f"setting{i+1}" for i in range(3)]
        + [f"sensor{i+1}" for i in range(21)])
SENSORS = [f"sensor{i}" for i in (2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17, 20, 21)]
WINDOW = 30
CAP = 125
N_FOLDS = 5
INNER_FRAC = 0.15
MAX_EPOCHS = 60
PATIENCE = 10
BATCH = 256
LR = 1e-3
WEIGHT_DECAY = 1e-4
CLIP = 1.0

NETS = ("mlp", "cnn", "gru", "transformer", "cnn_last", "cnn_flat", "transformer_last")
ALL_MODELS = ("mean", "boost") + NETS


# ----------------------------------------------------------------------------- data

def load(split: str) -> pd.DataFrame:
    df = pd.read_csv(DATA / f"{split}_FD001.txt", sep=r"\s+", header=None, names=COLS)
    df[["unit", "cycle"]] = df[["unit", "cycle"]].astype(int)
    return df.sort_values(["unit", "cycle"]).reset_index(drop=True)


def add_rul(df: pd.DataFrame, final_rul: dict[int, int] | None = None) -> pd.DataFrame:
    """Cycles to failure at each row, capped. Test engines stop before failure, so their
    RUL at the last observed cycle comes from RUL_FD001.txt."""
    df = df.copy()
    last = df.groupby("unit")["cycle"].transform("max")
    extra = df["unit"].map(final_rul).fillna(0) if final_rul else 0
    df["rul"] = np.minimum(last - df["cycle"] + extra, CAP).astype(np.float32)
    return df


def windows(df: pd.DataFrame, mu, sd, last_only=False):
    """X (n, channels, time), y (n,), engine (n,), is_last (n,)."""
    Xs, ys, gs, ls = [], [], [], []
    for unit, g in df.groupby("unit", sort=True):
        arr = ((g[SENSORS].to_numpy() - mu) / sd).astype(np.float32)
        rul = g["rul"].to_numpy()
        ends = [len(g)] if last_only else range(WINDOW, len(g) + 1)
        for end in ends:
            Xs.append(arr[end - WINDOW:end].T)
            ys.append(rul[end - 1])
            gs.append(unit)
            ls.append(end == len(g))
    return (np.stack(Xs), np.asarray(ys, np.float32), np.asarray(gs), np.asarray(ls))


def summary_features(X: np.ndarray) -> np.ndarray:
    """Per channel: mean, std, last value, and least-squares slope over the window."""
    t = np.arange(X.shape[2], dtype=np.float32)
    t = (t - t.mean()) / ((t - t.mean()) ** 2).sum()
    return np.concatenate([X.mean(2), X.std(2), X[:, :, -1], (X * t).sum(2)], axis=1)


# ----------------------------------------------------------------------------- models

class MLP(nn.Module):
    """The NARX way: flatten the window, every (channel, lag) gets its own weight."""
    def __init__(self, c, t, width=64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Flatten(), nn.Linear(c * t, width), nn.ReLU(),
            nn.Linear(width, width), nn.ReLU(), nn.Linear(width, 1))

    def forward(self, x):
        return self.net(x).squeeze(-1)


class CNN(nn.Module):
    """Small filters slid along time, shared across the window, then pooled."""
    def __init__(self, c, t, width=32, k=5):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(c, width, k, padding=k // 2), nn.ReLU(),
            nn.Conv1d(width, width, k, padding=k // 2), nn.ReLU(),
            nn.Conv1d(width, width, k, padding=k // 2), nn.ReLU(),
            nn.AdaptiveAvgPool1d(1), nn.Flatten(),
            nn.Linear(width, width), nn.ReLU(), nn.Linear(width, 1))

    def forward(self, x):
        return self.net(x).squeeze(-1)


class CNNLast(nn.Module):
    """The same convolutions, read out at the last time step instead of averaged over the
    window, so the model keeps *where* a pattern sits (the most recent cycles)."""
    def __init__(self, c, t, width=32, k=5):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(c, width, k, padding=k // 2), nn.ReLU(),
            nn.Conv1d(width, width, k, padding=k // 2), nn.ReLU(),
            nn.Conv1d(width, width, k, padding=k // 2), nn.ReLU())
        self.head = nn.Sequential(nn.Linear(width, width), nn.ReLU(), nn.Linear(width, 1))

    def forward(self, x):
        return self.head(self.conv(x)[:, :, -1]).squeeze(-1)


class CNNFlat(nn.Module):
    """The same convolutions, flattened into the head, so every position keeps its weight."""
    def __init__(self, c, t, width=32, k=5):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(c, width, k, padding=k // 2), nn.ReLU(),
            nn.Conv1d(width, width, k, padding=k // 2), nn.ReLU(),
            nn.Conv1d(width, width, k, padding=k // 2), nn.ReLU())
        self.head = nn.Sequential(nn.Flatten(), nn.Linear(width * t, width), nn.ReLU(),
                                  nn.Linear(width, 1))

    def forward(self, x):
        return self.head(self.conv(x)).squeeze(-1)


class TransformerLast(nn.Module):
    """The transformer read out at the last cycle rather than averaged over the window."""
    def __init__(self, c, t, **kw):
        super().__init__()
        self.m = Transformer(c, t, **kw)

    def forward(self, x):
        m = self.m
        h = m.enc(m.inp(x.transpose(1, 2)) + m.pos)
        return m.head(h[:, -1]).squeeze(-1)


class GRU(nn.Module):
    """A learned nonlinear state carried along the window; read out at the last step."""
    def __init__(self, c, t, hidden=64):
        super().__init__()
        self.gru = nn.GRU(c, hidden, batch_first=True)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x):
        out, _ = self.gru(x.transpose(1, 2))       # (N, T, C) in, (N, T, H) out
        return self.head(out[:, -1]).squeeze(-1)


class Transformer(nn.Module):
    """Every cycle attends to every other; a learned position embedding puts order back."""
    def __init__(self, c, t, d=32, heads=4, layers=2):
        super().__init__()
        self.inp = nn.Linear(c, d)
        self.pos = nn.Parameter(torch.zeros(1, t, d))
        nn.init.normal_(self.pos, std=0.02)
        layer = nn.TransformerEncoderLayer(d, heads, dim_feedforward=2 * d, dropout=0.1,
                                           batch_first=True, norm_first=True)
        self.enc = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.head = nn.Linear(d, 1)

    def forward(self, x):
        h = self.enc(self.inp(x.transpose(1, 2)) + self.pos)
        return self.head(h.mean(1)).squeeze(-1)


class TransformerNoPos(Transformer):
    """The same transformer with the position embedding frozen at zero.

    With mean pooling and no positional signal, the model is exactly invariant to the
    order of the cycles in its window: shuffle them and the prediction does not move.
    run_order() uses it to show what the position embedding is for.
    """
    def __init__(self, c, t, **kw):
        super().__init__(c, t, **kw)
        self.pos.data.zero_()
        self.pos.requires_grad_(False)


BUILD = {"mlp": MLP, "cnn": CNN, "gru": GRU, "transformer": Transformer,
         "cnn_last": CNNLast, "cnn_flat": CNNFlat, "transformer_last": TransformerLast,
         "transformer_nopos": TransformerNoPos}


def n_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


# ----------------------------------------------------------------------------- training

def train_net(name, Xtr, ytr, Xva, yva, *, seed, clip=CLIP, device="cpu",
              max_epochs=MAX_EPOCHS, patience=PATIENCE, schedule="cosine"):
    """Train on (Xtr, ytr), early-stop on (Xva, yva). Targets arrive in cycles.

    schedule is "cosine" (annealed over max_epochs, the lecture's recipe) or
    "constant"; make_widget_data.py compares the two with early stopping off.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = BUILD[name](Xtr.shape[1], Xtr.shape[2]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    sched = (torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max_epochs)
             if schedule == "cosine" else None)
    lossf = nn.MSELoss()
    Xtr_t = torch.from_numpy(Xtr).to(device)
    ytr_t = torch.from_numpy(ytr / CAP).to(device)
    Xva_t = torch.from_numpy(Xva).to(device)
    yva_t = torch.from_numpy(yva / CAP).to(device)
    gen = torch.Generator().manual_seed(seed)

    best, best_state, since, hist = math.inf, None, 0, []
    grad_norms = []
    t0 = time.perf_counter()
    for epoch in range(max_epochs):
        model.train()
        perm = torch.randperm(len(Xtr_t), generator=gen).to(device)
        tr_loss, nb, first = 0.0, 0, len(grad_norms)
        lr_now = opt.param_groups[0]["lr"]
        for i in range(0, len(perm), BATCH):
            idx = perm[i:i + BATCH]
            loss = lossf(model(Xtr_t[idx]), ytr_t[idx])
            opt.zero_grad()
            loss.backward()
            g = torch.nn.utils.clip_grad_norm_(model.parameters(),
                                               clip if clip else float("inf"))
            grad_norms.append(float(g))
            opt.step()
            tr_loss += loss.item()
            nb += 1
        if sched is not None:
            sched.step()
        va = evaluate(model, Xva_t, yva_t)
        g_ep = np.array(grad_norms[first:])
        hist.append({"epoch": epoch + 1, "train_rmse": CAP * math.sqrt(tr_loss / nb),
                     "val_rmse": va, "lr": lr_now,
                     "grad_p50": float(np.median(g_ep)), "grad_max": float(g_ep.max()),
                     "clipped": float(np.mean(g_ep > clip)) if clip else 0.0})
        if not math.isfinite(va):
            break
        if va < best - 1e-4:
            best, since = va, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            since += 1
            if since >= patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    info = {"epochs": len(hist), "best_epoch": int(np.argmin([h["val_rmse"] for h in hist])) + 1
            if hist else 0, "seconds": time.perf_counter() - t0, "params": n_params(model),
            "history": hist, "grad_norm_p50": float(np.median(grad_norms)),
            "grad_norm_max": float(np.max(grad_norms))}
    return model, info


@torch.no_grad()
def evaluate(model, X_t, y_t) -> float:
    """RMSE in cycles."""
    model.eval()
    pred = torch.cat([model(X_t[i:i + 4096]) for i in range(0, len(X_t), 4096)])
    return float(CAP * torch.sqrt(torch.mean((pred - y_t) ** 2)))


@torch.no_grad()
def predict(model, X, device="cpu") -> np.ndarray:
    model.eval()
    X_t = torch.from_numpy(X).to(device)
    return CAP * torch.cat([model(X_t[i:i + 4096]) for i in range(0, len(X_t), 4096)]).cpu().numpy()


def inner_split(units: np.ndarray, seed: int):
    rng = np.random.default_rng(seed)
    u = np.unique(units)
    val = rng.choice(u, size=max(1, round(INNER_FRAC * len(u))), replace=False)
    return ~np.isin(units, val), np.isin(units, val)


def fit_predict(name, Xtr, ytr, gtr, Xte, seed):
    """Fit one model on training windows, return predictions on Xte and an info dict."""
    if name == "mean":
        return np.full(len(Xte), ytr.mean(), np.float32), {"params": 1}
    if name == "boost":
        t0 = time.perf_counter()
        m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                          early_stopping=True, validation_fraction=0.15,
                                          random_state=seed)
        m.fit(summary_features(Xtr), ytr)
        return m.predict(summary_features(Xte)), {"seconds": time.perf_counter() - t0,
                                                  "iters": int(m.n_iter_)}
    fit, val = inner_split(gtr, seed)
    model, info = train_net(name, Xtr[fit], ytr[fit], Xtr[val], ytr[val], seed=seed)
    return predict(model, Xte), info


def rmse(a, b) -> float:
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def phm_score(pred, true) -> float:
    """The PHM08 challenge score (Saxena et al. 2008): exponential, and harsher on late
    predictions (d > 0, the engine fails before you said it would) than early ones."""
    d = np.asarray(pred) - np.asarray(true)
    return float(np.sum(np.where(d < 0, np.exp(-d / 13) - 1, np.exp(d / 10) - 1)))


# ----------------------------------------------------------------------------- runs

def run_cv(models, seeds):
    df = add_rul(load("train"))
    units = df["unit"].to_numpy()
    RESULTS.mkdir(parents=True, exist_ok=True)
    engines = np.unique(units)
    folds = list(GroupKFold(N_FOLDS).split(engines, groups=engines))
    for name in models:
        out = RESULTS / f"cv_{name}.json"
        rows = json.loads(out.read_text()) if out.exists() else []
        done = {(r["seed"], r["fold"]) for r in rows}
        for seed in seeds:
            for k, (tr_i, te_i) in enumerate(folds):
                if (seed, k) in done:
                    continue
                tr_units, te_units = engines[tr_i], engines[te_i]
                tr = df[df.unit.isin(tr_units)]
                te = df[df.unit.isin(te_units)]
                mu = tr[SENSORS].mean().to_numpy()
                sd = tr[SENSORS].std().to_numpy()
                Xtr, ytr, gtr, _ = windows(tr, mu, sd)
                Xte, yte, _, _ = windows(te, mu, sd)
                pred, info = fit_predict(name, Xtr, ytr, gtr, Xte, seed)
                if k:
                    info.pop("history", None)      # keep one loss curve per seed
                row = {"model": name, "seed": seed, "fold": k, "rmse_all": rmse(pred, yte),
                       **info}
                rows.append(row)
                out.write_text(json.dumps(rows, indent=1))
                print(f"{name:12s} seed {seed} fold {k}: rmse {row['rmse_all']:6.2f}  "
                      f"({info.get('seconds', 0):.0f}s, {info.get('epochs', '-')} ep)", flush=True)


def run_test(models, seeds):
    train = add_rul(load("train"))
    final = {i + 1: int(v) for i, v in enumerate(
        np.loadtxt(DATA / "RUL_FD001.txt", dtype=int))}
    test = add_rul(load("test"), final)
    mu = train[SENSORS].mean().to_numpy()
    sd = train[SENSORS].std().to_numpy()
    Xtr, ytr, gtr, _ = windows(train, mu, sd)
    Xte, yte, _, _ = windows(test, mu, sd, last_only=True)
    true_raw = np.array([final[u] for u in sorted(final)], np.float32)
    RESULTS.mkdir(parents=True, exist_ok=True)
    for name in models:
        out = RESULTS / f"test_{name}.json"
        rows = json.loads(out.read_text()) if out.exists() else []
        done = {r["seed"] for r in rows}
        for seed in seeds:
            if seed in done:
                continue
            pred, info = fit_predict(name, Xtr, ytr, gtr, Xte, seed)
            info.pop("history", None)
            row = {"model": name, "seed": seed, "rmse_capped": rmse(pred, yte),
                   "rmse_raw": rmse(pred, true_raw), "score_capped": phm_score(pred, yte),
                   "pred": [float(p) for p in pred], **info}
            rows.append(row)
            out.write_text(json.dumps(rows, indent=1))
            print(f"{name:12s} seed {seed} test: rmse {row['rmse_capped']:6.2f} "
                  f"(raw {row['rmse_raw']:6.2f})  score {row['score_capped']:8.0f}", flush=True)


def run_order(seed=0):
    """Does each sequence model use the order of the cycles in its window?

    Train the transformer with and without its position embedding, and the GRU, on
    each of the five engine-grouped folds (one seed), then score every model on the
    held-out windows three ways: as recorded, reversed in time, and with the 30 cycles
    shuffled by one fixed permutation. A model that ignores order scores the same on
    all three. Weight decay also touches the frozen zero embedding, which stays zero.
    """
    df = add_rul(load("train"))
    engines = np.unique(df["unit"].to_numpy())
    folds = list(GroupKFold(N_FOLDS).split(engines, groups=engines))
    perm = np.random.default_rng(0).permutation(WINDOW)
    out = RESULTS / "order.json"
    rows = json.loads(out.read_text()) if out.exists() else []
    done = {(r["model"], r["fold"]) for r in rows}
    for k, (tr_i, te_i) in enumerate(folds):
        tr = df[df.unit.isin(engines[tr_i])]
        te = df[df.unit.isin(engines[te_i])]
        mu = tr[SENSORS].mean().to_numpy()
        sd = tr[SENSORS].std().to_numpy()
        Xtr, ytr, gtr, _ = windows(tr, mu, sd)
        Xte, yte, _, _ = windows(te, mu, sd)
        views = {"recorded": Xte, "reversed": np.ascontiguousarray(Xte[:, :, ::-1]),
                 "shuffled": np.ascontiguousarray(Xte[:, :, perm])}
        for name in ("transformer", "transformer_nopos", "gru"):
            if (name, k) in done:
                continue
            fit, val = inner_split(gtr, seed)
            model, info = train_net(name, Xtr[fit], ytr[fit], Xtr[val], ytr[val], seed=seed)
            row = {"model": name, "seed": seed, "fold": k, "epochs": info["epochs"],
                   "best_epoch": info["best_epoch"],
                   **{v: rmse(predict(model, X), yte) for v, X in views.items()}}
            rows.append(row)
            out.write_text(json.dumps(rows, indent=1))
            print(f"{name:18s} fold {k}: " + "  ".join(f"{v} {row[v]:6.2f}" for v in views),
                  flush=True)


def summary(models):
    """One row per model: CV over every (seed, fold), then the official test set."""
    print(f"{'model':16s} {'n':>3s} {'cv rmse':>14s} {'test rmse':>14s} "
          f"{'raw':>7s} {'phm score':>10s} {'params':>7s} {'sec/fit':>8s}")
    for name in models:
        cv_path, te_path = RESULTS / f"cv_{name}.json", RESULTS / f"test_{name}.json"
        if not cv_path.exists():
            continue
        cv = json.loads(cv_path.read_text())
        te = json.loads(te_path.read_text()) if te_path.exists() else []
        a = np.array([r["rmse_all"] for r in cv])
        line = f"{name:16s} {len(a):3d} {a.mean():7.2f} ± {a.std():4.2f}"
        if te:
            t = np.array([r["rmse_capped"] for r in te])
            line += (f" {t.mean():7.2f} ± {t.std():4.2f}"
                     f" {np.mean([r['rmse_raw'] for r in te]):7.2f}"
                     f" {np.mean([r['score_capped'] for r in te]):10.0f}")
        else:
            line += " " * 41
        params = cv[0].get("params")
        line += f" {params or '':>7} {np.mean([r.get('seconds', 0) for r in cv]):8.1f}"
        print(line)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["cv", "test", "summary", "order"])
    ap.add_argument("--models", nargs="+", default=list(ALL_MODELS), choices=ALL_MODELS)
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    a = ap.parse_args()
    torch.set_num_threads(4)
    if a.what == "summary":
        summary(a.models)
    elif a.what == "order":
        run_order()
    else:
        (run_cv if a.what == "cv" else run_test)(a.models, a.seeds)
