#!/usr/bin/env python3
"""Generate the L8 figures, and print every number the notes quote.

Run from this directory with:
    uv run --with numpy --with polars --with pyarrow --with pyreadr \
        --with scikit-learn --with matplotlib python make_figures.py

Nothing in the notes or the deck is asserted without coming from this script or from
the demo notebook. The printed block at the end is the record.

DATA
----
Rieth et al. (2017), Tennessee Eastman simulation data, CC0,
https://doi.org/10.7910/DVN/6C3JR1. Two files are downloaded into .cache/ (gitignored):

  * fault-free training, 500 runs x 500 samples at 3 minutes (25 MB). Everything
    except the detector figure uses this file only.
  * faulty training (about 500 MB), for one run of one fault in the detector figure.
    If it is absent the detector figure is skipped and the committed PNG stands.

Train on runs 1-300, test on runs 401-500. Runs are independent simulations, so a
split by run is the honest split across series.

FOUR FINDINGS THAT SHAPED THE SESSION
-------------------------------------
Scouting all 22 continuous channels (2026-09-16) settled the channel and the story.

1. Reactor pressure `xmeas_7` is the teaching channel. Persistence beats the mean by a
   factor of four one step ahead and loses to it between 30 and 60 minutes out, and
   a ridge model beats the better of the two at every horizon, most near the
   crossover. Stripper temperature `xmeas_18` shows the most skill of any channel
   (up to 47 %) and is kept for A4 so the assignment is not a copy of the demo.
2. Seven channels (`xmeas_5, 6, 9, 12, 14, 15, 17`) are white noise around a
   setpoint: persistence is about sqrt(2) = 1.41 times worse than the mean at h = 1
   and h = 20, and no model finds skill. That is the shape of an asset's returns, so the finance
   contrast comes out of our own plant.
3. Direct beats recursive, and the gap grows with the horizon. At h = 40 the
   recursive forecast is worse than the mean.
4. A shuffled split does NOT inflate ridge or gradient boosting when the table pools
   hundreds of independent runs (a first draft of the plan assumed it would): with
   that much data a random test row has almost no near-copies to lean on. The leak
   appears on a single series, which is also the shape of one stock or one meter,
   and there it inflates ridge as well as a random forest. So the leak figure works
   one run at a time, and the notes say plainly that the pooled ridge barely moved.

FIGURE SHAPES
-------------
Every figure lands on a 1280x720 MARP slide. Nothing here is taller than about
1.45:1 width to height. After changing any figsize, render the deck and run
    node tools/check_slide_overflow.mjs _build/html/slides/l08/index.html

Outputs (committed alongside this script):
    three-series.png     pressure, a white-noise channel and a random walk, with ACFs
    skill-horizon.png    RMSE against horizon: persistence, mean, direct, recursive
    rolling-origin.png   the rolling-origin split, with the gap drawn in
    leaky-split.png      shuffled KFold against TimeSeriesSplit on single runs
    residual-detector.png  a one-step residual on a fault run, with its threshold
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
CACHE.mkdir(exist_ok=True)

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
BLUE = "#1f5c99"
GOLD = "#b07d12"

plt.rcParams.update({
    "font.size": 12,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": MUTED,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.dpi": 160,
    "savefig.bbox": "tight",
})

DT = 3.0  # minutes per sample
CH = "xmeas_7"  # reactor pressure, kPa gauge
UNIT = "kPa"
P = 10  # lags of the channel's own past
XMV = [f"xmv_{i}" for i in range(1, 12)]
TRAIN = range(1, 301)
TEST = range(401, 501)
HORIZONS = [1, 2, 3, 5, 7, 10, 15, 20, 25, 30, 40]
RECORD: list[str] = []


def note(msg: str) -> None:
    RECORD.append(msg)
    print(msg)


def fetch(dest: Path, obj: str) -> pl.DataFrame | None:
    """Download a Rieth .RData file once and cache it as Parquet."""
    pq = dest.with_suffix(".parquet")
    if pq.exists():
        return pl.read_parquet(pq)
    if not dest.exists():
        return None
    import pyreadr

    pdf = pyreadr.read_r(str(dest))[obj]
    for c in ("faultNumber", "simulationRun", "sample"):
        pdf[c] = pdf[c].astype(int)
    out = pl.from_pandas(pdf.reset_index(drop=True))
    out.write_parquet(pq)
    return out


def ensure_fault_free() -> pl.DataFrame:
    raw = CACHE / "tep_fault_free_training.RData"
    if not raw.exists() and not raw.with_suffix(".parquet").exists():
        import shutil
        import urllib.request

        url = "https://dataverse.harvard.edu/api/access/datafile/3031241"
        print(f"fetching {url} (one time, 25 MB)")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as r, open(raw, "wb") as f:
            shutil.copyfileobj(r, f)
    return fetch(raw, "fault_free_training")


def runs_of(df: pl.DataFrame) -> dict[int, pl.DataFrame]:
    return {r: g.sort("sample") for (r,), g in df.group_by("simulationRun")}


def table(runs, data, h, exo=False, ch=CH):
    """Rows of [y[t], ..., y[t-P+1], (u[t])] with target y[t+h], built inside each run."""
    Ps, ys, last = [], [], []
    for r in runs:
        y = data[r][ch].to_numpy()
        idx = np.arange(P - 1, len(y) - h)
        cols = [y[idx - k] for k in range(P)]
        if exo:
            U = data[r].select(XMV).to_numpy()
            cols += [U[idx, j] for j in range(U.shape[1])]
        Ps.append(np.column_stack(cols))
        ys.append(y[idx + h])
        last.append(y[idx])
    return np.vstack(Ps), np.concatenate(ys), np.concatenate(last)


class Ridge:
    """Standardized ridge with an unpenalized intercept. Same answer as scikit-learn's
    Ridge in a Pipeline with StandardScaler, written out so the script has one fewer
    moving part."""

    def __init__(self, lam=1e-3):
        self.lam = lam

    def fit(self, A, b):
        self.mu, self.sd = A.mean(0), A.std(0) + 1e-12
        Z = np.column_stack([np.ones(len(A)), (A - self.mu) / self.sd])
        reg = self.lam * len(A) * np.eye(Z.shape[1])
        reg[0, 0] = 0
        self.w = np.linalg.solve(Z.T @ Z + reg, Z.T @ b)
        return self

    def predict(self, A):
        return np.column_stack([np.ones(len(A)), (A - self.mu) / self.sd]) @ self.w


def rmse(e):
    return float(np.sqrt(np.mean(np.square(e))))


def acf(x, nlags):
    x = x - x.mean()
    d = np.dot(x, x)
    return np.array([1.0] + [np.dot(x[:-k], x[k:]) / d for k in range(1, nlags + 1)])


# ---------------------------------------------------------------------------------
def fig_three_series(data):
    """Three kinds of series, and what persistence and the mean are worth on each."""
    rng = np.random.default_rng(8)
    walk = 100 + np.cumsum(rng.normal(0, 1, 500))
    series = [
        (data[1][CH].to_numpy(), "Reactor pressure (xmeas_7)", f"{UNIT}", CMU_RED),
        (data[1]["xmeas_12"].to_numpy(), "Separator level (xmeas_12)", "%", MUTED),
        (walk, "Simulated random walk (a price)", "price", BLUE),
    ]
    fig, ax = plt.subplots(2, 3, figsize=(12, 5.6))
    t = np.arange(500) * DT / 60
    lags = np.arange(41)
    for j, (y, title, unit, c) in enumerate(series):
        ax[0, j].plot(t, y, lw=0.9, color=c)
        ax[0, j].set_title(title, fontsize=12)
        ax[0, j].set_xlabel("hours")
        ax[0, j].set_ylabel(unit)
        ax[1, j].bar(lags * DT, acf(y, 40), width=2.2, color=c)
        ax[1, j].axhline(0, color=MUTED, lw=0.8)
        ax[1, j].set_ylim(-0.45, 1.05)
        ax[1, j].set_xlabel("lag, minutes")
        ax[1, j].set_ylabel("autocorrelation")
    fig.tight_layout()
    fig.savefig(HERE / "three-series.png")
    plt.close(fig)

    note(f"three-series: lag-1 ACF pressure {acf(series[0][0], 1)[1]:.3f}, "
         f"separator level {acf(series[1][0], 1)[1]:.3f}, random walk {acf(walk, 1)[1]:.3f}, "
         f"random-walk returns {acf(np.diff(walk), 1)[1]:.3f}")
    # persistence / mean on every continuous channel, test runs, h=1 and h=20
    white = []
    for i in range(1, 23):
        ch = f"xmeas_{i}"
        ratios = []
        for h in (1, 20):
            _, b, last = table(TRAIN, data, h, ch=ch)
            _, bt, lt = table(TEST, data, h, ch=ch)
            ratios.append(rmse(bt - lt) / rmse(bt - b.mean()))
        if min(ratios) > 1.35:
            white.append(ch)
        if ch in (CH, "xmeas_12", "xmeas_18"):
            note(f"  {ch}: persistence/mean RMSE ratio h=1 {ratios[0]:.3f}, h=20 {ratios[1]:.3f}")
    note(f"  white-noise channels (ratio > 1.35 at h=1 and h=20): {white}")


def fig_skill_horizon(data):
    one = Ridge().fit(*table(TRAIN, data, 1)[:2])
    rows = []
    for h in HORIZONS:
        A, b, _ = table(TRAIN, data, h)
        At, bt, lt = table(TEST, data, h)
        Ax, bx, _ = table(TRAIN, data, h, exo=True)
        Axt, _, _ = table(TEST, data, h, exo=True)
        direct = Ridge().fit(A, b).predict(At)
        arx = Ridge().fit(Ax, bx).predict(Axt)
        Z = At.copy()
        for _ in range(h):
            nxt = one.predict(Z)
            Z = np.column_stack([nxt, Z[:, :-1]])
        rows.append(dict(h=h, persistence=rmse(bt - lt), mean=rmse(bt - b.mean()),
                         direct=rmse(bt - direct), recursive=rmse(bt - nxt),
                         arx=rmse(bt - arx)))
    res = pl.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    m = res["h"].to_numpy() * DT
    ax.plot(m, res["persistence"], "o-", color=MUTED, label="persistence  y[t+h] = y[t]")
    ax.plot(m, res["mean"], "s--", color=GOLD, label="mean of the training runs")
    ax.plot(m, res["recursive"], "^-", color=BLUE, label="recursive AR(10)")
    ax.plot(m, res["direct"], "o-", color=CMU_RED, lw=2.2, label="direct AR(10), one model per h")
    ax.set_xlabel("forecast horizon, minutes")
    ax.set_ylabel(f"test RMSE, {UNIT}")
    ax.set_ylim(0, None)
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(HERE / "skill-horizon.png")
    plt.close(fig)
    res = res.with_columns(
        skill=1 - pl.col("direct") / pl.min_horizontal("persistence", "mean"),
        skill_arx=1 - pl.col("arx") / pl.min_horizontal("persistence", "mean"))
    note("skill-horizon (reactor pressure, test runs 401-500, RMSE in kPa):")
    for r in res.iter_rows(named=True):
        note(f"  h={r['h']:2d} ({r['h']*3:3d} min) persistence {r['persistence']:.2f} "
             f"mean {r['mean']:.2f} direct {r['direct']:.2f} recursive {r['recursive']:.2f} "
             f"arx {r['arx']:.2f} skill {r['skill']:.3f} skill_arx {r['skill_arx']:.3f}")
    _, b, _ = table(TRAIN, data, 1)
    note(f"  test-run standard deviation of pressure {table(TEST, data, 1)[1].std():.2f} kPa, "
         f"training mean {b.mean():.1f} kPa")


def fig_rolling_origin():
    fig, ax = plt.subplots(figsize=(10, 3.9))
    n, k, gap, test = 40, 5, 3, 5
    for f in range(k):
        y = k - f
        end = 12 + f * 5
        ax.barh(y, end, left=0, color=BLUE, height=0.6)
        ax.barh(y, gap, left=end, color="white", edgecolor=MUTED, hatch="///", height=0.6)
        ax.barh(y, test, left=end + gap, color=CMU_RED, height=0.6)
        ax.barh(y, n - end - gap - test, left=end + gap + test, color="#e6e6e6", height=0.6)
        ax.text(-0.6, y, f"fold {f + 1}", ha="right", va="center", fontsize=11)
    ax.set_xlim(-5, n)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_xlabel("time  →")
    ax.spines["left"].set_visible(False)
    from matplotlib.patches import Patch

    ax.legend(handles=[Patch(color=BLUE, label="train"),
                       Patch(facecolor="white", edgecolor=MUTED, hatch="///", label="gap (at least h)"),
                       Patch(color=CMU_RED, label="test"),
                       Patch(color="#e6e6e6", label="not used yet")],
              ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.18))
    fig.tight_layout()
    fig.savefig(HERE / "rolling-origin.png")
    plt.close(fig)


def fig_leaky_split(data):
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import Ridge as SkRidge
    from sklearn.model_selection import KFold, TimeSeriesSplit
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    h = 10
    schemes = [("shuffled KFold", lambda: KFold(5, shuffle=True, random_state=0)),
               ("TimeSeriesSplit", lambda: TimeSeriesSplit(5)),
               (f"TimeSeriesSplit, gap={h}", lambda: TimeSeriesSplit(5, gap=h))]
    models = [("random forest", lambda: RandomForestRegressor(200, n_jobs=-1, random_state=0)),
              ("ridge", lambda: make_pipeline(StandardScaler(), SkRidge(1e-3)))]
    runs = list(range(1, 11))
    score = {(s, m): [] for s, _ in schemes for m, _ in models}
    pers = {s: [] for s, _ in schemes}
    for r in runs:
        A, b, last = table([r], data, h, exo=True)
        for s, cv in schemes:
            folds = list(cv().split(A))
            pers[s].append(np.mean([rmse(b[te] - last[te]) for _, te in folds]))
            for m, mk in models:
                score[(s, m)].append(np.mean(
                    [rmse(b[te] - mk().fit(A[tr], b[tr]).predict(A[te])) for tr, te in folds]))
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    x = np.arange(len(schemes))
    w = 0.36
    for j, ((m, _), c) in enumerate(zip(models, [CMU_RED, BLUE])):
        vals = [np.mean(score[(s, m)]) for s, _ in schemes]
        ax.bar(x + (j - 0.5) * w, vals, width=w, color=c, label=m)
        for xi, v in zip(x, vals):
            ax.text(xi + (j - 0.5) * w, v + 0.08, f"{v:.2f}", ha="center", fontsize=10)
    p = np.mean(pers[schemes[1][0]])
    ax.axhline(p, ls="--", color=MUTED, lw=1.2)
    ax.text(-0.55, p - 0.35, f"persistence {p:.2f}", ha="left", color=MUTED, fontsize=10)
    ax.set_xticks(x, [s for s, _ in schemes])
    ax.set_ylabel(f"cross-validated RMSE, {UNIT}")
    ax.set_title(f"One run at a time, h = {h} (30 minutes), mean over runs 1-10", fontsize=12)
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(HERE / "leaky-split.png")
    plt.close(fig)
    note(f"leaky-split (h={h}, single runs 1-10, ARX(10) features, mean CV RMSE kPa):")
    for s, _ in schemes:
        note(f"  {s:24s} forest {np.mean(score[(s, 'random forest')]):.2f} "
             f"ridge {np.mean(score[(s, 'ridge')]):.2f} persistence {np.mean(pers[s]):.2f}")

    # the same comparison across runs, where ridge barely moves
    A, b, _ = table(list(TRAIN)[:100] + list(TEST), data, h, exo=True)
    grp = np.repeat(list(TRAIN)[:100] + list(TEST), 500 - P + 1 - h)
    rand = np.random.default_rng(0).random(len(b)) < 0.5
    byrun = np.isin(grp, list(TRAIN)[:100])
    out = []
    for msk in (rand, byrun):
        mdl = Ridge().fit(A[msk], b[msk])
        out.append(rmse(b[~msk] - mdl.predict(A[~msk])))
    note(f"  across 200 runs, ridge: random-row split {out[0]:.2f}, split by run {out[1]:.2f}")


def fig_residual_detector(data):
    raw = CACHE / "tep_faulty_training.RData"
    faulty = fetch(raw, "faulty_training")
    if faulty is None:
        print("faulty file absent, skipping residual-detector.png")
        return
    model = Ridge().fit(*table(TRAIN, data, 1, exo=True)[:2])
    At, bt, _ = table(TEST, data, 1, exo=True)
    res_ok = bt - model.predict(At)
    thr = float(np.quantile(np.abs(res_ok), 0.99))
    note(f"residual-detector: one-step ARX residual, fault-free test sd {res_ok.std():.3f} kPa, "
         f"99th percentile of |residual| {thr:.3f} kPa")
    note(f"  per-sample false-alarm rate on fault-free test runs {np.mean(np.abs(res_ok) > thr):.4f}, "
         f"= {np.mean(np.abs(res_ok) > thr) * 480:.1f} alarms per plant day")
    # three in a row, on the same fault-free runs
    def consec(flags, n=3):
        c = np.convolve(flags.astype(int), np.ones(n, int), "valid") >= n
        return c
    runs_ok = data
    fa3 = []
    for r in TEST:
        Ar, br, _ = table([r], runs_ok, 1, exo=True)
        fa3.append(consec(np.abs(br - model.predict(Ar)) > thr).mean())
    note(f"  requiring 3 consecutive exceedances: false-alarm rate {np.mean(fa3):.5f} per sample "
         f"= {np.mean(fa3) * 480:.2f} per plant day")
    by_fault = {f: g.sort("sample") for (f,), g in faulty.filter(pl.col("simulationRun") == 1)
                .group_by("faultNumber")}
    onset = 20  # Rieth: faults enter one hour into the training runs
    rows = []
    for f, g in sorted(by_fault.items()):
        Ar, br, _ = table([f], {f: g}, 1, exo=True)
        s = g["sample"].to_numpy()[P - 1:len(g) - 1] + 1  # sample index of each target
        e = np.abs(br - model.predict(Ar))
        after = s > onset
        flag3 = np.r_[np.zeros(2, bool), consec(e > thr)]
        hit = np.nonzero(after & flag3)[0]
        rows.append((f, float(np.mean(e[after] > thr)),
                     (int(s[hit[0]]) - onset) * DT if len(hit) else None))
    for f, rate, delay in rows:
        note(f"  fault {f:2d} run 1: exceedance rate after onset {rate:.3f}, "
             f"first 3-in-a-row alarm {'none' if delay is None else f'{delay:.0f} min'} after onset")
    FAULT = 1
    g = by_fault[FAULT]
    Ar, br, _ = table([FAULT], {FAULT: g}, 1, exo=True)
    s = g["sample"].to_numpy()[P - 1:len(g) - 1] + 1
    e = br - model.predict(Ar)
    fig, ax = plt.subplots(2, 1, figsize=(10, 5.2), sharex=True)
    hrs = s * DT / 60
    ax[0].plot(hrs, br, color=INK, lw=1)
    ax[0].set_ylabel(f"pressure, {UNIT}")
    ax[1].plot(hrs, e, color=CMU_RED, lw=1)
    for a in ax:
        a.axvline(onset * DT / 60, color=BLUE, ls="--", lw=1.2)
    ax[1].axhspan(-thr, thr, color="#e6e6e6", zorder=0)
    ax[1].set_ylabel(f"one-step residual, {UNIT}")
    ax[1].set_xlabel("hours into run 1 (fault enters at the dashed line)")
    ax[0].set_title(f"Fault {FAULT}, with the band set on fault-free runs "
                    f"(99th percentile, ±{thr:.2f} {UNIT})", fontsize=12)
    fig.tight_layout()
    fig.savefig(HERE / "residual-detector.png")
    plt.close(fig)


def main():
    df = ensure_fault_free()
    data = runs_of(df)
    note(f"fault-free training: {df.height} rows, {len(data)} runs, "
         f"{df.group_by('simulationRun').len()['len'].unique().to_list()} samples per run")
    fig_three_series(data)
    fig_skill_horizon(data)
    fig_rolling_origin()
    fig_leaky_split(data)
    fig_residual_detector(data)
    (CACHE / "numbers.txt").write_text("\n".join(RECORD) + "\n")


if __name__ == "__main__":
    main()
