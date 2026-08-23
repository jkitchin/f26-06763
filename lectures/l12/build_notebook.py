#!/usr/bin/env python3
"""Generate lectures/l12/l12-cnn-rul.ipynb.

The L12 demo builds a 1D-CNN for turbofan remaining-useful-life on C-MAPSS FD001
and holds it to an honest standard:

  1. Sliding 30-cycle windows per engine, a piecewise-linear RUL target, and a
     grouped split by engine so no engine leaks across it (the L8 lesson).
  2. A small 1D-CNN in PyTorch, trained with a cosine learning-rate schedule and
     early stopping, logging per-epoch train/val RMSE to MLflow and saving the
     best checkpoint as an artifact.
  3. A gradient-boosting baseline on hand-crafted window features, on the same
     split, so the deep model has something real to beat.

The point is the comparison: on this small, well-summarized benchmark the quick
sequence model does not automatically beat the baseline, and the grouped split
is what keeps that honest.

Design notes:
  - CPU by default (faster than MPS on a model this size, per L11).
  - Same window/target logic as figures/make_figures.py.
  - Runs top to bottom; seeds fixed; C-MAPSS cached under data/, mlflow.db
    gitignored.
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "l12-cnn-rul.ipynb"

_n = 0


def _next_id(kind):
    global _n
    _n += 1
    return f"{kind}-{_n:02d}"


def md(*lines):
    return {"cell_type": "markdown", "id": _next_id("md"),
            "metadata": {}, "source": list(lines)}


def code(*lines):
    return {"cell_type": "code", "id": _next_id("code"), "execution_count": None,
            "metadata": {}, "outputs": [], "source": list(lines)}


cells = [
    md("# L12 demo: a 1D-CNN for turbofan remaining-useful-life\n",
       "\n",
       "We predict remaining useful life (RUL) for NASA C-MAPSS FD001 engines from their sensor\n",
       "history, the same dataset as L8. The architecture is the point: a sensor stream is a\n",
       "sequence, so we use a 1D convolutional network over sliding windows rather than an MLP on\n",
       "a flat vector. And we hold it honest, with a grouped split by engine and a real baseline.\n",
       "\n",
       "> Data: [C-MAPSS FD001](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/),\n",
       "> 100 run-to-failure engines, carried over from L8."),

    md("## 1. Windows, a piecewise-linear target, and a grouped split\n",
       "\n",
       "Each engine's run becomes overlapping windows of 30 cycles across the sensor channels.\n",
       "The target is RUL, clipped at 125 cycles: health is roughly flat early in life, so the\n",
       "label is held constant and then decreases linearly. We split by **engine**, so no\n",
       "engine's windows appear in both train and validation."),

    code("import io\n",
         "import urllib.request\n",
         "import zipfile\n",
         "from pathlib import Path\n",
         "\n",
         "import numpy as np\n",
         "import pandas as pd\n",
         "from sklearn.model_selection import GroupShuffleSplit\n",
         "\n",
         "CACHE = Path('data/CMAPSS')\n",
         "CACHE.mkdir(parents=True, exist_ok=True)\n",
         "URL = ('https://phm-datasets.s3.amazonaws.com/NASA/'\n",
         "       '6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip')\n",
         "COLS = (['unit', 'cycle'] + [f'setting{i+1}' for i in range(3)]\n",
         "        + [f'sensor{i+1}' for i in range(21)])\n",
         "WINDOW, RUL_CAP, SEED = 30, 125, 0\n",
         "\n",
         "path = CACHE / 'train_FD001.txt'\n",
         "if not path.exists():\n",
         "    print('downloading', URL)\n",
         "    with urllib.request.urlopen(URL) as r:\n",
         "        outer = zipfile.ZipFile(io.BytesIO(r.read()))\n",
         "    inner_name = next(n for n in outer.namelist() if n.lower().endswith('.zip'))\n",
         "    inner = zipfile.ZipFile(io.BytesIO(outer.read(inner_name)))\n",
         "    for name in ['train_FD001.txt', 'test_FD001.txt', 'RUL_FD001.txt']:\n",
         "        (CACHE / name).write_bytes(inner.read(name))\n",
         "df = pd.read_csv(path, sep=r'\\s+', header=None, names=COLS)\n",
         "df = df.sort_values(['unit', 'cycle']).reset_index(drop=True)\n",
         "\n",
         "live = [c for c in df.columns if c.startswith(('sensor', 'setting')) and df[c].nunique() > 1]\n",
         "mu, sd = df[live].mean().to_numpy(), df[live].std().replace(0, 1).to_numpy()\n",
         "\n",
         "\n",
         "def windows(frame):\n",
         "    Xs, ys, gs = [], [], []\n",
         "    for unit, g in frame.groupby('unit'):\n",
         "        arr = ((g[live].to_numpy() - mu) / sd).astype(np.float32)\n",
         "        life, cyc = g['cycle'].max(), g['cycle'].to_numpy()\n",
         "        for end in range(WINDOW, len(g) + 1):\n",
         "            Xs.append(arr[end - WINDOW:end].T)\n",
         "            ys.append(float(min(life - cyc[end - 1], RUL_CAP)))\n",
         "            gs.append(unit)\n",
         "    return np.stack(Xs), np.array(ys, np.float32), np.array(gs)\n",
         "\n",
         "X, y, groups = windows(df)\n",
         "tr, va = next(GroupShuffleSplit(1, test_size=0.25, random_state=SEED).split(X, y, groups))\n",
         "print(f'{X.shape[0]} windows, {X.shape[1]} channels x {X.shape[2]} cycles')\n",
         "print(f'{len(set(groups[tr]))} train engines, {len(set(groups[va]))} held-out; '\n",
         "      f'{len(set(groups[tr]) & set(groups[va]))} shared')"),

    md("## 2. A small 1D-CNN\n",
       "\n",
       "Two 1D convolutions over time build local temporal features, a global pool summarizes\n",
       "the window, and a small head regresses RUL. The channels are the sensors; the kernel\n",
       "slides along cycles."),

    code("import torch\n",
         "import torch.nn as nn\n",
         "\n",
         "torch.manual_seed(SEED)\n",
         "\n",
         "\n",
         "class TinyCNN(nn.Module):\n",
         "    def __init__(self, channels):\n",
         "        super().__init__()\n",
         "        self.net = nn.Sequential(\n",
         "            nn.Conv1d(channels, 32, 5, padding=2), nn.ReLU(),\n",
         "            nn.Conv1d(32, 32, 5, padding=2), nn.ReLU(),\n",
         "            nn.AdaptiveAvgPool1d(1), nn.Flatten(),\n",
         "            nn.Linear(32, 32), nn.ReLU(), nn.Dropout(0.2), nn.Linear(32, 1))\n",
         "\n",
         "    def forward(self, x):\n",
         "        return self.net(x).squeeze(-1)\n",
         "\n",
         "\n",
         "print(TinyCNN(X.shape[1]))"),

    md("## 3. Train, with a schedule, early stopping, and MLflow\n",
       "\n",
       "The training loop is L11's, plus three things this session added: a **cosine**\n",
       "learning-rate schedule, **early stopping** on validation RMSE (keep the best epoch), and\n",
       "**MLflow** logging of per-epoch train/val loss with the best checkpoint saved as an\n",
       "artifact. Everything runs on CPU."),

    code("import mlflow\n",
         "\n",
         "device = 'cpu'\n",
         "mlflow.set_tracking_uri('sqlite:///mlflow.db')\n",
         "mlflow.set_experiment('cmapss-rul')\n",
         "\n",
         "Xtr = torch.tensor(X[tr]); ytr = torch.tensor(y[tr])\n",
         "Xva = torch.tensor(X[va]); yva = torch.tensor(y[va])\n",
         "\n",
         "\n",
         "def rmse(pred, true):\n",
         "    return float(torch.sqrt(nn.functional.mse_loss(pred, true)))\n",
         "\n",
         "\n",
         "model = TinyCNN(X.shape[1]).to(device)\n",
         "opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)\n",
         "sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=60)\n",
         "lossf = nn.MSELoss()\n",
         "\n",
         "best_rmse, best_state, patience, wait = float('inf'), None, 10, 0\n",
         "with mlflow.start_run(run_name='1d-cnn'):\n",
         "    mlflow.log_params({'window': WINDOW, 'rul_cap': RUL_CAP, 'arch': '1d-cnn', 'seed': SEED})\n",
         "    for epoch in range(60):\n",
         "        model.train()\n",
         "        perm = torch.randperm(len(Xtr))\n",
         "        for i in range(0, len(Xtr), 256):\n",
         "            idx = perm[i:i + 256]\n",
         "            opt.zero_grad()\n",
         "            lossf(model(Xtr[idx]), ytr[idx]).backward()\n",
         "            opt.step()\n",
         "        sched.step()\n",
         "        model.eval()\n",
         "        with torch.no_grad():\n",
         "            tr_rmse, va_rmse = rmse(model(Xtr), ytr), rmse(model(Xva), yva)\n",
         "        mlflow.log_metrics({'train_rmse': tr_rmse, 'val_rmse': va_rmse}, step=epoch)\n",
         "        if va_rmse < best_rmse:\n",
         "            best_rmse, best_state, wait = va_rmse, {k: v.clone() for k, v in model.state_dict().items()}, 0\n",
         "        else:\n",
         "            wait += 1\n",
         "            if wait >= patience:\n",
         "                print(f'early stop at epoch {epoch}')\n",
         "                break\n",
         "    torch.save(best_state, 'best_cnn.pt')\n",
         "    mlflow.log_artifact('best_cnn.pt')\n",
         "    mlflow.log_metric('best_val_rmse', best_rmse)\n",
         "cnn_rmse = best_rmse\n",
         "print(f'1D-CNN best held-out RUL RMSE: {cnn_rmse:.2f} cycles')"),

    md("## 4. A baseline that has to be beaten\n",
       "\n",
       "The tabular baseline from the ML arc: hand-crafted summary features of each window (the\n",
       "per-sensor mean, standard deviation, and last value) into gradient boosting, on the same\n",
       "grouped split. If the CNN cannot beat this, the raw signal is not buying anything here."),

    code("from sklearn.ensemble import HistGradientBoostingRegressor\n",
         "from sklearn.metrics import root_mean_squared_error\n",
         "\n",
         "\n",
         "def feats(W):\n",
         "    return np.concatenate([W.mean(2), W.std(2), W[:, :, -1]], axis=1)\n",
         "\n",
         "base = HistGradientBoostingRegressor(random_state=SEED).fit(feats(X[tr]), y[tr])\n",
         "base_rmse = root_mean_squared_error(y[va], base.predict(feats(X[va])))\n",
         "print(f'gradient-boosting baseline held-out RUL RMSE: {base_rmse:.2f} cycles')"),

    md("## 5. The honest comparison\n",
       "\n",
       "On this single grouped split the two land close together, and the sequence model does\n",
       "not automatically win. This is one split; the figure in the notes repeats it over four\n",
       "engine-grouped folds with error bars, and the ordering holds. The lesson is L11's and\n",
       "Grinsztajn's: a deep architecture is not a default, and a strong classical baseline on a\n",
       "small, well-summarized benchmark is the model to beat."),

    code("print(f'1D-CNN (raw windows)          : {cnn_rmse:5.2f} cycles')\n",
         "print(f'gradient boosting (features)   : {base_rmse:5.2f} cycles')\n",
         "verdict = 'the CNN wins' if cnn_rmse < base_rmse else 'the baseline wins'\n",
         "print(f'on this grouped split, {verdict} by {abs(cnn_rmse - base_rmse):.2f} cycles')"),

    md("---\n",
       "\n",
       "## Takeaway\n",
       "\n",
       "We matched the architecture to the data, a 1D-CNN for a sensor sequence, trained it with\n",
       "a schedule and early stopping, and tracked every epoch and the best checkpoint in MLflow.\n",
       "Then we did the thing that keeps deep learning honest: a grouped split so no engine leaks,\n",
       "and a strong tabular baseline to beat. On this small benchmark the CNN does not run away\n",
       "with it, which is the point. Assignment **A6** has you build, train, and honestly evaluate\n",
       "a deep model against a real baseline on a GPU, so it starts here."),
]

# The Colab bootstrap cell, injected from the notebook's own imports so this
# generator does not carry a second copy of the requirement list. See
# tools/colab_setup.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from colab_setup import with_colab_cell  # noqa: E402

cells = with_colab_cell(cells, OUT)

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(nb, indent=1) + "\n")
print(f"wrote {OUT} ({len(cells)} cells)")
