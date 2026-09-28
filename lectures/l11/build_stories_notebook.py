#!/usr/bin/env python3
"""Generate lectures/l11/l11-four-models.ipynb.

The four stories from the notes' "Four models that looked fine" section, each rerun from the
code that produced its numbers so a student can dig into it:

  1. the target shape: a (N,) target against a (N, 1) prediction, 17.7 MPa, fixed 5.5
  2. the leaky split: random KFold says gradient boosting beats the MLP, GroupKFold says tie
  3. the missing zero_grad(): 23.2 MPa, worse than predicting the mean, fixed 5.5
  4. Adam on raw inputs: 8.3 MPa and a smooth curve, fixed 5.5; SGD on the same inputs is NaN

Each story has the same four parts: the code as it was written, the number that looked fine,
a "dig in" cell that exposes the cause, and the fix.

Design notes:
  - `train()` is copied from figures/make_figures.py with the same defaults, fold, seeds and
    DataLoader path, so the notebook reproduces the numbers in the notes and slides. It adds a
    per-epoch training-loss record, which reads `loss.item()` and changes nothing else.
    Wall-clock and library versions can move the last digit.
  - Deliberately broken on purpose: every broken run is labelled as such in the markdown
    before it, and none of them raises. The shape bug emits a UserWarning per batch; the
    loop records them rather than letting 1,560 copies reach the page.
  - The dtype story is not here. It is Part 2 of l11-tensors-autograd.ipynb.
  - The leaky-split story trains 50 networks and takes a few minutes on a laptop CPU. N_SEEDS at the top of
    that section trades time for the error bar.

Kept in a generator for deterministic cell ids and no hand-edited JSON. The committed
.ipynb carries no outputs and must run top to bottom.

    python3 lectures/l11/build_stories_notebook.py
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "l11-four-models.ipynb"

_n = 0


def _next_id(kind):
    global _n
    _n += 1
    return f"{kind}-{_n:02d}"


def _src(text):
    lines = text.strip("\n").split("\n")
    return [ln + "\n" for ln in lines[:-1]] + [lines[-1]]


def md(text):
    return {"cell_type": "markdown", "id": _next_id("md"),
            "metadata": {}, "source": _src(text)}


def code(text):
    return {"cell_type": "code", "id": _next_id("code"), "execution_count": None,
            "metadata": {}, "outputs": [], "source": _src(text)}


cells = [
    md("""
# L11: four models that looked fine

Each of these models trained without an error, produced a plausible number, and was wrong. The
notes and the slides tell the stories; this notebook reruns them from the code that produced
the numbers, so you can take each one apart yourself.

Every story has the same four parts:

1. **As written.** The code as someone would actually write it, with the bug in it.
2. **How it looked.** The number it produced, and why that number seemed fine.
3. **Dig in.** The check that exposes the cause.
4. **Fixed.** The one-line change, and the number after it.

The bugs are deliberate. None of them raises an exception, which is why they are worth studying.
The dtype story is not repeated here: it is Part 2 of `l11-tensors-autograd.ipynb`.
"""),

    md("""
## The data, the fold and the baseline

The UCI **Concrete Compressive Strength** set: 1,030 rows, eight inputs (seven mix components
and the curing age in days) and the crush strength in MPa. Many mixes were tested at
several ages, so rows are grouped by mix. Every story uses fold 0 of a `GroupKFold` by mix, the
honest split from Lecture 9, except the leaky-split story, whose whole point is the split.

The number to keep in view is the **baseline**: predict the training mean for every validation
row. Any model that is learning anything should beat it by a wide margin.
"""),

    code("""
import io
import urllib.request
import warnings
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold, KFold
from sklearn.preprocessing import StandardScaler

CACHE = Path('.cache')
CACHE.mkdir(exist_ok=True)
LOCAL = CACHE / 'Concrete_Data.xls'
URL = ('https://archive.ics.uci.edu/static/public/165/'
       'concrete+compressive+strength.zip')
if not LOCAL.exists():
    print('downloading', URL)
    with urllib.request.urlopen(URL) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    LOCAL.write_bytes(archive.read('Concrete_Data.xls'))

COLUMNS = ['cement', 'slag', 'fly_ash', 'water', 'superplasticizer',
           'coarse_agg', 'fine_agg', 'age_days', 'strength_mpa']
FEATURES = COLUMNS[:8]
MIX = COLUMNS[:7]            # the recipe; age is what varies within a mix
SEED = 0

concrete = pd.read_excel(LOCAL)   # needs xlrd for .xls
concrete.columns = COLUMNS
groups = concrete.groupby(MIX, sort=False).ngroup().to_numpy()
X = concrete[FEATURES].to_numpy(np.float32)
y = concrete['strength_mpa'].to_numpy(np.float32)

tr, va = next(iter(GroupKFold(5).split(X, y, groups)))
baseline = float(np.sqrt(np.mean((y[va] - y[tr].mean()) ** 2)))
print(f'{len(concrete)} rows, {groups.max() + 1} distinct mixes')
print(f'fold 0: {len(tr)} training rows, {len(va)} validation rows')
print(f'baseline, predict the training mean: {baseline:.1f} MPa')
print(f'spread of the validation targets:     {y[va].std():.1f} MPa')
"""),

    md("""
## The training loop

This is the loop from the notes, with three switches that turn a bug on: `target_2d=False`,
`zero_grad=False` and `scale=False`. Everything else is fixed, including the seed, so a run with
every switch left alone is the working model. It returns the validation RMSE in MPa, the
validation RMSE after every epoch, the mean training loss after every epoch, and a few
diagnostics: the spread of the predictions and how many warnings the loop raised.
"""),

    code("""
def mlp(width=64, depth=2, d_in=8):
    layers, d = [], d_in
    for _ in range(depth):
        layers += [nn.Linear(d, width), nn.ReLU()]
        d = width
    return nn.Sequential(*layers, nn.Linear(d, 1))


def train(X_tr, y_tr, X_va, y_va, *, lr=1e-3, epochs=400, batch=64, seed=SEED,
          optimizer='adam', zero_grad=True, scale=True, target_2d=True):
    torch.manual_seed(seed)
    if scale:
        scaler = StandardScaler().fit(X_tr)            # fitted on training rows only
        X_tr = scaler.transform(X_tr).astype(np.float32)
        X_va = scaler.transform(X_va).astype(np.float32)
    y_mean, y_std = y_tr.mean(), y_tr.std()

    y_t = torch.tensor((y_tr - y_mean) / y_std)
    if target_2d:
        y_t = y_t[:, None]                             # (N, 1), to match the model's output
    loader = DataLoader(TensorDataset(torch.tensor(X_tr), y_t),
                        batch_size=batch, shuffle=True)
    xv, yv = torch.tensor(X_va), torch.tensor(y_va)[:, None]

    model = mlp(d_in=X_tr.shape[1])
    opt = (torch.optim.Adam(model.parameters(), lr=lr) if optimizer == 'adam'
           else torch.optim.SGD(model.parameters(), lr=lr))
    loss_fn = nn.MSELoss()
    val_rmse, train_loss = [], []

    with warnings.catch_warnings(record=True) as log:
        warnings.simplefilter('always')
        for _ in range(epochs):
            model.train()
            total = 0.0
            for xb, yb in loader:
                loss = loss_fn(model(xb), yb)
                if zero_grad:
                    opt.zero_grad()
                loss.backward()
                opt.step()
                total += loss.item()
            train_loss.append(total / len(loader))
            model.eval()
            with torch.no_grad():
                val_rmse.append(float(torch.sqrt(torch.mean(
                    (model(xv) * y_std + y_mean - yv) ** 2))))
    with torch.no_grad():
        pred = model(xv) * y_std + y_mean
    info = {'pred_std': float(pred.std()), 'warnings': len(log),
            'first_warning': str(log[0].message) if log else '',
            'model': model, 'loader': loader}
    return val_rmse[-1], val_rmse, train_loss, info


rmse, _, _, _ = train(X[tr], y[tr], X[va], y[va], epochs=120)
print(f'working model, 120 epochs: {rmse:.1f} MPa against a {baseline:.1f} MPa baseline')
"""),

    md("""
## The loss went down, and the model learned a constant

**As written.** One character is missing. The targets are left as a flat vector of shape
`(N,)`, while the model returns `(N, 1)`. That is `target_2d=False` below.
"""),

    code("""
rmse, val_hist, loss_hist, info = train(X[tr], y[tr], X[va], y[va], epochs=120,
                                        target_2d=False)

fig, ax = plt.subplots(figsize=(6, 3.5))
ax.plot(loss_hist, color='#1f5c99')
ax.set_xlabel('epoch')
ax.set_ylabel('mean training loss')
ax.set_title('The curve everyone checks first')
plt.show()
print(f'validation RMSE: {rmse:.1f} MPa')
"""),

    md("""
**How it looked.** The training loss fell steadily for 120 epochs, no exception was raised, and
the validation RMSE is a plausible number for a first attempt. With nothing to compare it with,
it looks like a model that needs tuning.

**Dig in.** Compare it with the baseline, then look at what the model actually predicts, then
look at the shapes going into the loss.
"""),

    code("""
print(f'baseline {baseline:.1f} MPa, model {rmse:.1f} MPa: '
      f'{100 * (1 - rmse / baseline):.0f}% better than predicting the mean')
print(f'spread of the predictions: {info["pred_std"]:.2f} MPa, '
      f'spread of the targets: {y[va].std():.1f} MPa')
print(f'warnings raised during training: {info["warnings"]}')
print('the first one:', info['first_warning'][:120])

xb, yb = next(iter(info['loader']))
out = info['model'](xb)
print()
print('model output', tuple(out.shape), '| target', tuple(yb.shape),
      '| output - target', tuple((out - yb).shape))
"""),

    md("""
The model is barely better than predicting the mean, and its predictions hardly vary. The last
line shows why. A `(64, 1)` column minus a `(64,)` row **broadcasts** to a `(64, 64)` matrix:
every prediction minus every target in the batch. The mean of that matrix is smallest when every
prediction equals the batch mean, so the optimizer did exactly what it was asked, and the loss
really did go down. PyTorch warned once per batch, which in a notebook shows up as a single
warning that is easy to scroll past.

**Fixed.** Make the target `(N, 1)`, which is `target_2d=True`, the default.
"""),

    code("""
rmse_fixed, _, _, info_fixed = train(X[tr], y[tr], X[va], y[va], epochs=120)
print(f'fixed: {rmse_fixed:.1f} MPa, predictions spread {info_fixed["pred_std"]:.1f} MPa, '
      f'{info_fixed["warnings"]} warnings')
"""),

    md("""
**Try it.** Add `assert out.shape == yb.shape` inside the training loop and rerun the broken
version. One line turns a silent failure into a loud one.

## The tree that won on a leaky split

**As written.** A careful comparison: five seeds, five folds, gradient boosting against the MLP.
The folds come from `KFold(5, shuffle=True)`, which splits rows at random.

This cell trains 50 networks and takes a few minutes. Lower `N_SEEDS` to go faster, at the cost
of a wider error bar.
"""),

    code("""
N_SEEDS = 5

SCHEMES = {
    'KFold, random rows': list(KFold(5, shuffle=True, random_state=SEED).split(X)),
    'GroupKFold, by mix': list(GroupKFold(5).split(X, y, groups)),
}


def rmse_of(pred, idx):
    return float(np.sqrt(np.mean((y[idx] - pred) ** 2)))


results = {}
for name, folds in SCHEMES.items():
    tree, net = [], []
    for seed in range(N_SEEDS):
        for f_tr, f_va in folds:
            gb = HistGradientBoostingRegressor(random_state=seed).fit(X[f_tr], y[f_tr])
            tree.append(rmse_of(gb.predict(X[f_va]), f_va))
            net.append(train(X[f_tr], y[f_tr], X[f_va], y[f_va], seed=seed)[0])
    tree, net = np.array(tree), np.array(net)
    gap = net - tree
    results[name] = (tree, net, gap)
    print(f'{name:20s} gradient boosting {tree.mean():.2f}, MLP {net.mean():.2f}, '
          f'MLP minus tree {gap.mean():+.2f} +/- {gap.std() / np.sqrt(len(gap)):.2f} '
          f'(n={len(gap)})')
"""),

    md("""
**How it looked.** Read only the first line. Under random `KFold` the tree wins by nearly five
standard errors, the protocol used several seeds, and the conclusion matches the received wisdom
that trees beat networks on small tabular data.

**Dig in.** Ask Lecture 9's question: are these rows exchangeable? Count how many validation
rows share a mix with some training row.
"""),

    code("""
for name, folds in SCHEMES.items():
    shared = [np.isin(groups[f_va], groups[f_tr]).mean() for f_tr, f_va in folds]
    print(f'{name:20s} validation rows whose mix is also in training: '
          f'{100 * np.mean(shared):.0f}%')

counts = pd.Series(groups).value_counts()
mix = counts.index[0]
print()
print(f'mix {mix} appears {counts.iloc[0]} times, at these ages:')
print(concrete.loc[groups == mix, ['age_days', 'strength_mpa']].to_string(index=False))
"""),

    md("""
Under the random split three quarters of the validation rows have a sibling in training: the
same concrete, cured for a different number of days. Predicting a mix you have already seen at another age is
much easier than predicting a new recipe, and a tree, which can carve out a region around each
training mix, profits from that more than the network does. The second line of the results is
the honest comparison: both models get worse, the tree gets worse by more, and the gap is within
two standard errors of zero. **The two models tie.**

**Fixed.** Split by mix with `GroupKFold`. Nothing about either model changed.
"""),

    code("""
for name, (tree, net, gap) in results.items():
    print(f'{name:20s} tree {tree.mean():.2f}  MLP {net.mean():.2f}')
leak_tree = results['GroupKFold, by mix'][0].mean() - results['KFold, random rows'][0].mean()
leak_net = results['GroupKFold, by mix'][1].mean() - results['KFold, random rows'][1].mean()
print(f'what the leak was worth: tree {leak_tree:.2f} MPa, MLP {leak_net:.2f} MPa')
"""),

    md("""
### And the leaky scaler?

The bug people warn about most is fitting the `StandardScaler` on every row before splitting.
Here it is, measured on the honest folds with three seeds. On this dataset it moves the score by
less than its own noise: eight means and eight standard deviations estimated from 1,030 rows
barely change when you add the validation rows. It is still a bug, and on a smaller or shifted
dataset it would matter. The leak that changed the conclusion above was the split.
"""),

    code("""
X_all = StandardScaler().fit_transform(X).astype(np.float32)   # fitted on every row: the leak
honest, leaky = [], []
for seed in range(3):
    for f_tr, f_va in SCHEMES['GroupKFold, by mix']:
        honest.append(train(X[f_tr], y[f_tr], X[f_va], y[f_va], seed=seed, epochs=200)[0])
        leaky.append(train(X_all[f_tr], y[f_tr], X_all[f_va], y[f_va], seed=seed,
                           epochs=200, scale=False)[0])
d = np.array(leaky) - np.array(honest)
print(f'scaler on training rows {np.mean(honest):.2f}, on all rows {np.mean(leaky):.2f} MPa, '
      f'difference {d.mean():+.2f} +/- {d.std(ddof=1) / np.sqrt(len(d)):.2f}')
"""),

    md("""
## The loop that forgot `zero_grad()`

**As written.** The same loop, with `opt.zero_grad()` left out. That is `zero_grad=False`.
"""),

    code("""
rmse, val_hist, _, _ = train(X[tr], y[tr], X[va], y[va], epochs=120, zero_grad=False)
rmse_ok, val_ok, _, _ = train(X[tr], y[tr], X[va], y[va], epochs=120)

fig, ax = plt.subplots(figsize=(7, 3.8))
ax.plot(val_hist, color='#c41230', label='zero_grad() omitted')
ax.axhline(baseline, color='gray', ls='--', label='predict the mean')
ax.set_xlabel('epoch')
ax.set_ylabel('validation RMSE, MPa')
ax.set_ylim(0, 30)
ax.legend(frameon=False)
plt.show()
print(f'final validation RMSE: {rmse:.1f} MPa')
"""),

    md("""
**How it looked.** No NaN, no exception, and for most of the run the validation error sits below
the baseline, so the model is clearly learning something. A noisy curve like this reads as a
learning rate that is a bit too high. Where it ends depends on where you stop.

**Dig in.** PyTorch **adds** each new gradient into `.grad` rather than replacing it. Watch the
size of `.grad` on one layer over a few steps, with and without zeroing.
"""),

    code("""
def grad_norms(zero, steps=8):
    torch.manual_seed(SEED)
    Xs = StandardScaler().fit(X[tr]).transform(X[tr]).astype(np.float32)
    ys = ((y[tr] - y[tr].mean()) / y[tr].std())[:, None]
    loader = DataLoader(TensorDataset(torch.tensor(Xs), torch.tensor(ys)),
                        batch_size=64, shuffle=True)
    model = mlp()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    norms = []
    for step, (xb, yb) in enumerate(loader):
        if step == steps:
            break
        if zero:
            opt.zero_grad()
        nn.MSELoss()(model(xb), yb).backward()
        opt.step()
        norms.append(float(model[0].weight.grad.norm()))
    return norms


print('step          ', '  '.join(f'{i:5d}' for i in range(1, 9)))
print('with zero_grad', '  '.join(f'{v:5.2f}' for v in grad_norms(True)))
print('without       ', '  '.join(f'{v:5.2f}' for v in grad_norms(False)))
"""),

    md("""
With zeroing, the gradient's size stays roughly level. Without it, each step's `.grad` is the sum
of every gradient so far, so the step Adam takes follows the running sum of the history rather
than the current batch. The model keeps being pushed along directions that stopped being
right many steps ago.

**Fixed.** Put `opt.zero_grad()` back before `loss.backward()`.
"""),

    code("""
print(f'without zero_grad {rmse:.1f} MPa, baseline {baseline:.1f} MPa, '
      f'fixed {rmse_ok:.1f} MPa')
"""),

    md("""
## Adam on raw inputs

**As written.** The scaler step is forgotten, so the network sees the inputs in their own units.
That is `scale=False`.
"""),

    code("""
rmse_raw, hist_raw, _, _ = train(X[tr], y[tr], X[va], y[va], epochs=120, scale=False)
rmse_scaled, hist_scaled, _, _ = train(X[tr], y[tr], X[va], y[va], epochs=120)

fig, ax = plt.subplots(figsize=(7, 3.8))
ax.plot(hist_raw, color='#c41230', ls=':', label='Adam, raw inputs')
ax.axhline(baseline, color='gray', ls='--', label='predict the mean')
ax.set_xlabel('epoch')
ax.set_ylabel('validation RMSE, MPa')
ax.set_ylim(0, 30)
ax.legend(frameon=False)
plt.show()
print(f'Adam, raw inputs: {rmse_raw:.1f} MPa')
"""),

    md("""
**How it looked.** A textbook curve: fast at first, then flattening, ending at half the
baseline. The usual warning says unscaled inputs make training diverge, and this did not diverge,
so it is easy to conclude the warning did not apply.

**Dig in.** Look at the scales of the inputs, then try the same inputs with plain SGD.
"""),

    code("""
print(concrete[FEATURES].std().round(1).to_string())

rmse_sgd_raw, _, _, _ = train(X[tr], y[tr], X[va], y[va], epochs=120, scale=False,
                              optimizer='sgd')
print()
print(f'SGD, raw inputs: {rmse_sgd_raw} MPa')
"""),

    md("""
The raw inputs differ in size by more than two orders of magnitude: coarse aggregate averages
about 970 kg/m³ and superplasticizer about 6. A first-layer weight's gradient is proportional to
its input, so those gradients differ by the same factor. Plain SGD takes a step proportional to the gradient and blows up in the first epoch.
Adam divides each parameter's step by a running estimate of that parameter's own gradient size,
so every weight moves at about the learning rate no matter how its input is scaled. That rescuing
is what hid the bug: Adam absorbed it into a model that trains smoothly and is mediocre.

**Fixed.** Standardize the inputs, with the scaler fitted on the training rows.
"""),

    code("""
print(f'Adam raw {rmse_raw:.1f} MPa, Adam scaled {rmse_scaled:.1f} MPa, '
      f'baseline {baseline:.1f} MPa')
"""),

    md("""
## What caught each one

| story | looked like | caught by |
|---|---|---|
| target shape | a weak first model | the mean baseline, and the spread of the predictions |
| leaky split | trees beat nets | a split grouped by mix |
| no `zero_grad()` | a noisy learning rate | reading the loop, and the size of `.grad` |
| raw inputs with Adam | a respectable model | the input scales, or trying SGD |

None of them raised an error. Each was caught by comparing the result with something outside the
model: a baseline, a different split, a different optimizer, or the code itself.
"""),
]

# The Colab bootstrap cell, injected from the notebook's own imports.
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
