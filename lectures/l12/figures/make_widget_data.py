#!/usr/bin/env python3
"""Write the data behind the L12 interactive figures to _static/l12-widget-data.js.

The widgets themselves live in _static/widgets.js and are generic; this script is
where their L12 numbers come from, so the same rule applies as to make_figures.py:
the figure is regenerated from the data, never hand-edited.

    python3 make_widget_data.py

Four things go into the file:

  - `series`: one real FD001 training engine, the sensor the convolution and
    recurrence widgets slide along, standardized with the training-set statistics
    that experiments.py uses. Sensor 11 is chosen because its drift toward failure
    is the clearest single channel in FD001, so a reader can see what a slope
    kernel or a leaky state is responding to.
  - `attention`: self-attention weights from a transformer trained exactly as in
    experiments.py (seed 0, all 100 training engines), read from both layers and
    averaged over the four heads, for two official test engines: one near failure
    and one far from it. These are the trained model's weights, not an
    illustration, so the widget shows what the model actually attends to.
  - `receptive`: the CNN geometry the widgets draw, copied from experiments.CNN so
    the two cannot silently disagree.
  - `training`: GRU learning curves run for the full epoch budget with early
    stopping off, five seeds, cosine schedule against a constant rate, plus the
    per-epoch gradient norms. The early-stopping and clipping widgets replay these,
    so a reader can move the patience and see where a run would have stopped.

Training the transformer takes about a minute on a laptop CPU; the training
curves take about ten more the first time and are cached after that.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

import experiments as ex

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "_static" / "l12-widget-data.js"
ENGINE = 1
SENSOR = "sensor11"
SEED = 0


@torch.no_grad()
def attention_maps(model: ex.Transformer, x: np.ndarray) -> list[list[list[int]]]:
    """Head-averaged attention of each encoder layer for one window, shape (T, T).

    Weights are stored as integers per mille (each row sums to about 1000), because
    this file loads on every page of the book and three decimals of float text is
    three times the bytes for no visible difference.

    The encoder's fused fast path does not return weights, so this replays the
    pre-norm layers by hand: norm1, self-attention with need_weights, residual,
    then the feed-forward block, exactly the order nn.TransformerEncoderLayer uses
    with norm_first=True.
    """
    model.eval()
    h = model.inp(torch.from_numpy(x.T[None])) + model.pos
    maps = []
    for layer in model.enc.layers:
        z = layer.norm1(h)
        out, w = layer.self_attn(z, z, z, need_weights=True, average_attn_weights=True)
        maps.append(np.rint(1000 * w[0].numpy()).astype(int).tolist())
        h = h + out
        h = h + layer._ff_block(layer.norm2(h))
    return maps


def training_curves(Xtr, ytr, gtr, seeds=range(5)) -> dict:
    """GRU learning curves with early stopping off, cosine versus constant rate.

    Every lecture run stops near epoch 25, which hides two things a reader needs
    to see: what the validation curve does after the best epoch, and how little
    the cosine schedule has decayed by then (T_max is the 60-epoch budget). So
    these runs go the full MAX_EPOCHS with patience disabled. Five seeds each,
    cached, because this is about ten minutes of CPU.
    """
    cache = ex.RESULTS / "training_curves.json"
    if cache.exists():
        return json.loads(cache.read_text())
    runs = {"cosine": [], "constant": []}
    for seed in seeds:
        fit, val = ex.inner_split(gtr, seed)
        for sched in runs:
            _, info = ex.train_net("gru", Xtr[fit], ytr[fit], Xtr[val], ytr[val], seed=seed,
                                   patience=ex.MAX_EPOCHS + 1, schedule=sched)
            runs[sched].append(info["history"])
            print(f"seed {seed} {sched}: best epoch {info['best_epoch']}, "
                  f"min val {min(h['val_rmse'] for h in info['history']):.2f}, {info['seconds']:.0f}s")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(runs))
    return runs


def training_block(runs: dict) -> dict:
    """Compact form of the training curves for the early-stopping and clipping widgets.

    Train and validation RMSE for every seed and schedule, the learning rate once
    per schedule (it does not depend on the seed), and the per-epoch gradient-norm
    summary for seed 0 with the cosine schedule, which is the lecture's own setup.
    """
    def r(v, d=2):
        return [round(float(x), d) for x in v]
    out = {"clip": ex.CLIP, "patience": ex.PATIENCE, "max_epochs": ex.MAX_EPOCHS, "runs": {}}
    for sched, hists in runs.items():
        out["runs"][sched] = {
            "train": [r([e["train_rmse"] for e in h]) for h in hists],
            "val": [r([e["val_rmse"] for e in h]) for h in hists],
            "lr": [float(f"{e['lr']:.3g}") for e in hists[0]],
        }
    h0 = runs["cosine"][0]
    out["grad"] = {"p50": r([e["grad_p50"] for e in h0], 3), "max": r([e["grad_max"] for e in h0], 3),
                   "clipped": r([e["clipped"] for e in h0], 4)}
    return out


def main() -> None:
    train = ex.add_rul(ex.load("train"))
    final = {i + 1: int(v) for i, v in enumerate(
        np.loadtxt(ex.DATA / "RUL_FD001.txt", dtype=int))}
    test = ex.add_rul(ex.load("test"), final)
    mu = train[ex.SENSORS].mean().to_numpy()
    sd = train[ex.SENSORS].std().to_numpy()

    col = ex.SENSORS.index(SENSOR)
    eng = train[train.unit == ENGINE]
    series = ((eng[SENSOR] - mu[col]) / sd[col]).round(2).tolist()

    Xtr, ytr, gtr, _ = ex.windows(train, mu, sd)
    fit, val = ex.inner_split(gtr, SEED)
    torch.set_num_threads(4)
    model, info = ex.train_net("transformer", Xtr[fit], ytr[fit], Xtr[val], ytr[val],
                               seed=SEED)
    print(f"transformer trained: {info['epochs']} epochs, {info['seconds']:.0f}s")

    Xte, yte, gte, _ = ex.windows(test, mu, sd, last_only=True)
    pred = ex.predict(model, Xte)
    true_raw = np.array([final[u] for u in gte])
    picks = {"near": int(np.argmin(true_raw)), "far": int(np.argmax(true_raw))}
    attention = {}
    for label, i in picks.items():
        attention[label] = {
            "engine": int(gte[i]), "true_rul": int(true_raw[i]),
            "predicted_rul": round(float(pred[i]), 1),
            "sensor": np.round(Xte[i][col], 2).tolist(),
            "layers": attention_maps(model, Xte[i]),
        }
        print(f"{label}: test engine {gte[i]}, true RUL {true_raw[i]}, "
              f"predicted {pred[i]:.1f}")

    training = training_block(training_curves(Xtr, ytr, gtr))

    data = {
        "source": "NASA C-MAPSS FD001, generated by lectures/l12/figures/make_widget_data.py",
        "series": {"engine": ENGINE, "sensor": SENSOR, "values": series,
                   "window": ex.WINDOW, "cap": ex.CAP},
        "attention": attention,
        "receptive": {"layers": 3, "kernel": 5, "window": ex.WINDOW},
        "training": training,
    }
    OUT.write_text(
        "/* Generated by lectures/l12/figures/make_widget_data.py. Do not edit. */\n"
        "window.COURSE_WIDGET_DATA = window.COURSE_WIDGET_DATA || {};\n"
        f"window.COURSE_WIDGET_DATA.l12 = {json.dumps(data, separators=(',', ':'))};\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
