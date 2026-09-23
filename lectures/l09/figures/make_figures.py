#!/usr/bin/env python3
"""Generate the L9 figures, and print every number the notes and the deck quote.

Run from this directory with:
    uv run --no-project --with numpy --with pandas --with xlrd --with pyarrow \
        --with scikit-learn --with matplotlib --with scipy python make_figures.py

Name groups to regenerate only those: `... make_figures.py water concrete`. With no names,
every group runs. The groups, and what each writes:
    examples    surfactant-data, tep-data, and the five dataset-card thumbnails card-water,
                card-surfactant, card-concrete, card-tep, card-cuberoot
    schematics  ml-workflow, nn-diagram, nn-hyperparameters, gp-likelihood (the surfactant
                length-scale sweep)
    water       water-hook, water-polynomial, lasso-alphas, tree-water, extrapolation
    optim       opt-paths (four optimizers on one least-squares fit to the water data)
    nn          nn-data, nn-terms, nn-tanh, nn-restarts, nn-scaling
    gp          gp-surfactant, gp-idea, gp-posterior, gp-kernel
    cv          cv-splitters, concrete-grouping (real mixes in random and grouped folds)
    concrete    concrete-data, concrete-cv, concrete-depth, concrete-learning,
                concrete-parity
    narx        narx-schematic (one row of Lecture 8's table, on a real run), narx-forecast
    widgets     no figure: prints the constants the two interactive slides embed (the
                ReLU network's weights and training points; the surfactant GP's
                variances and data), so the deck's JavaScript can be checked against it

The classification figures (the moons, stratified k-fold and the Tennessee Eastman fault
classifier) moved to Lecture 10 with that material, and lectures/l10/figures/make_figures.py
draws them now. tep-data.png is drawn by both scripts, since both lectures show it.

Nothing in the notes or the deck is asserted without coming from this script or from
the demo notebook. The printed block is the record. A full run takes a few minutes,
most of it Gaussian process fits.

WHERE THE MATERIAL COMES FROM
-----------------------------
Most of the figures below are Victor Alves's own, from his F25 06-325 lectures 6 to 10
(https://github.com/victoraalves/06-325-Numerical-Methods-And-Machine-Learning-for-ChemE-Fall-2025),
regenerated here from the same code so they can be checked: the water polynomial, the
lasso sweep, the depth-2 tree, the three-tanh network, the scaling parity plot, the
surfactant GP and the k-fold picture. His hand-drawn network from
lecture 7 is redrawn here as the left panel of nn-diagram.png. Titles are plainer
than the originals and the water axis now reads MPa, which is what the NIST file holds.

Three images are NOT generated and are committed as files:
    xkcd-machine-learning.png  xkcd 1838 "Machine Learning", Randall Munroe,
                               https://xkcd.com/1838/, CC BY-NC 2.5
    ml-types.png               Peng, Jury, Donnes and Ciurtin (2021), Front. Pharmacol.
                               12:720694, https://doi.org/10.3389/fphar.2021.720694,
                               CC BY 4.0 (the same image Victor's F25 lecture 6 uses)
    neuron.png                 Wikimedia Commons File:Neuron3.png, Egm4313.s12
                               (Prof. Loc Vu-Quoc), CC BY-SA 3.0

DATA (downloaded into .cache/, gitignored)
------------------------------------------
  * NIST Chemistry WebBook, isochoric water at 1000 kg/m3, 0.01 to 100.01 C in 5 C
    steps. The query below returns the same 21 rows as Victor's fluid.txt.
  * logzsv.csv, zero-shear viscosity of a surfactant solution against concentration
    (Rehage and Hoffmann 1988), from Victor's public F25 repository.
  * UCI Concrete Compressive Strength (Yeh 1998), CC BY 4.0,
    https://doi.org/10.24432/C5PK67.
  * The miniproject's two Tennessee Eastman files (Rieth et al. 2017, CC0), 25 MB and
    20 MB, from the course data host.

A FINDING THAT SHAPED THE SESSION
---------------------------------
Concrete is grouped. 1,030 rows are 428 mixes; 182 mixes were tested at several ages and
they hold 76% of the rows. A random KFold ranks a full-depth tree above a straight line
with two physics features; GroupKFold on the mix ranks it far below.

Faults 3, 9 and 15 are deliberately absent from every L9 figure: the miniproject's
evidence script checks that students find them.

FIGURE SHAPES
-------------
Every figure lands on a 1280x720 MARP slide. After changing a figsize, render the
deck and run
    node tools/check_slide_overflow.mjs _build/html/slides/l09/index.html
Each figure's size and fonts are chosen together so that its smallest text lands at 16 px
or more at the width the deck shows it (the comment on each rc_context gives that width,
and fonts() gives the arithmetic). Mathtext superscripts, such as the 2 in R^2, render at
0.7 of their line's size.
The card-*.png thumbnails are the exception to the tight bounding box every other figure
uses: they are saved at exactly 3.4 x 2.3 inches with fixed margins, so that the cards on
the datasets slide come out the same size whatever their tick labels are. The synthetic
one, card-cuberoot, is shown 96 px tall and carries no axes.

WHEN A TEP FAULT STARTS
-----------------------
Rieth et al. sample every 3 minutes, 500 samples (25 hours) per training run, and their
dataset description says the faults are introduced 1 hour into the faulty training runs.
The data agree: faulty run r of every fault is identical to fault-free run r, channel for
channel, through sample 20 (1.0 hours) at least. Fault 1, the one tep-data.png plots,
first differs at sample 21 in all twenty runs; slower faults reach the 52 channels a few
samples later. tep_onset() finds the first differing sample for each run, and this script
plots time as sample x 3 minutes, so the fault line sits at 1.0 hours.

THE OPTIMIZER COUNTS
--------------------
opt-paths.png counts, for each method, the first iteration from which the loss stays within
a relative 1e-6 of the least-squares optimum for the rest of the run (cap 2,000). "Stays"
matters for a stochastic method, whose noisy loss can dip below the line by chance
without settling there. One iteration is one parameter update: a full-batch gradient for
gradient descent, Adam and L-BFGS (whose line search spends extra evaluations, printed),
and one mini-batch of 4 rows for stochastic gradient descent.
"""
from __future__ import annotations

import io
import time
import urllib.request
import warnings
import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.legend_handler import HandlerTuple
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.compose import TransformedTargetRegressor
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, Matern, WhiteKernel
from sklearn.linear_model import Lasso, LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import (GroupKFold, GroupShuffleSplit, KFold,
                                     cross_validate, learning_curve,
                                     train_test_split, validation_curve)
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from sklearn.tree import DecisionTreeRegressor, plot_tree

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
CACHE.mkdir(exist_ok=True)

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
BLUE = "#1f5c99"
GOLD = "#b07d12"
GREEN = "#2e7d32"
# The three hidden units of the F25 network, in nn-terms.png and nn-diagram.png alike, with a
# light fill for each node.
UNIT_COLORS = [BLUE, GOLD, GREEN]
UNIT_FILLS = ["#dce8f5", "#f5ebd5", "#e6f2e6"]

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
    "legend.frameon": False,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
})


def fonts(size):
    """rcParams for plt.rc_context that set every text in a figure to `size` pt.

    A figure saved Wsave px wide and shown W px wide on the 1280x720 slide renders an f pt
    font at f * (150 / 72) * (W / Wsave) px. Each figure below is sized so that its
    smallest text lands at 16 px or more at the width the deck shows it.
    """
    return {
        "font.size": size,
        "axes.labelsize": size,
        "axes.titlesize": size,
        "xtick.labelsize": size,
        "ytick.labelsize": size,
        "legend.fontsize": size,
    }


def save(fig, name):
    fig.savefig(HERE / name)
    plt.close(fig)
    print(f"  wrote {name}")


def fetch(url, local):
    path = CACHE / local
    if not path.exists():
        print(f"  downloading {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        path.write_bytes(urllib.request.urlopen(req).read())
    return path


# --------------------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------------------
NIST = ("https://webbook.nist.gov/cgi/fluid.cgi?Action=Data&Wide=on&ID=C7732185"
        "&Type=IsoChor&Digits=5&D=1000&TLow=0.01&THigh=100.01&TInc=5&RefState=DEF"
        "&TUnit=C&PUnit=MPa&DUnit=kg%2Fm3&HUnit=kJ%2Fmol&WUnit=m%2Fs&VisUnit=uPa*s"
        "&STUnit=N%2Fm")
F25 = ("https://raw.githubusercontent.com/victoraalves/"
       "06-325-Numerical-Methods-And-Machine-Learning-for-ChemE-Fall-2025/main/Datasets/")
UCI_CONCRETE = ("https://archive.ics.uci.edu/static/public/165/"
                "concrete+compressive+strength.zip")
TEP_HOST = "https://kitchin-services.cheme.cmu.edu/f26-06763/data/"


def load_water():
    T, P = np.loadtxt(fetch(NIST, "fluid.txt"), delimiter="\t", skiprows=1,
                      usecols=(0, 1), unpack=True)
    return T, P


def load_water_truth():
    """The same isochore from NIST out to 300 C, which the models never see."""
    url = NIST.replace("THigh=100.01&TInc=5", "THigh=300.01&TInc=10")
    return np.loadtxt(fetch(url, "nist-isochore-300C.txt"), delimiter="\t", skiprows=1,
                      usecols=(0, 1), unpack=True)


def load_logzsv():
    return pd.read_csv(fetch(F25 + "logzsv.csv", "logzsv.csv"), index_col=0)


COLUMNS = ["cement", "slag", "fly_ash", "water", "superplasticizer",
           "coarse_agg", "fine_agg", "age_days", "strength_mpa"]
FEATURES, MIX = COLUMNS[:8], COLUMNS[:7]


def load_concrete():
    path = CACHE / "Concrete_Data.xls"
    if not path.exists():
        z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(UCI_CONCRETE).read()))
        path.write_bytes(z.read("Concrete_Data.xls"))
    df = pd.read_excel(path)
    df.columns = COLUMNS
    return df


CH = [f"xmeas_{i}" for i in range(1, 42)] + [f"xmv_{i}" for i in range(1, 12)]
SEEN = [1, 2, 4, 5, 6, 7, 8, 12, 13]           # never 3, 9 or 15 (see the docstring)


def load_tep():
    ff = pd.read_parquet(fetch(TEP_HOST + "tep_fault_free_training.parquet",
                               "tep_fault_free_training.parquet"))
    fa = pd.read_parquet(fetch(TEP_HOST + "tep_faulty_training_runs01-20.parquet",
                               "tep_faulty_training_runs01-20.parquet"))
    return ff, fa


def cuberoot_data():
    """y = x^(1/3) + noise: 120 points on [0, 1], split 80/20 as in Victor's F25 lecture 7."""
    rng = np.random.default_rng(0)
    X = np.linspace(0, 1, 120).reshape(-1, 1)
    y = X**(1 / 3) + rng.normal(0, 0.03, size=X.shape)
    split = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
    )
    return X, y, *split


# --------------------------------------------------------------------------------------
# The datasets, introduced: one plot of each, and a thumbnail for the datasets slide
# --------------------------------------------------------------------------------------
TEP_FAULT, TEP_RUN = 1, 1      # IDV(1), A/C feed ratio step; in SEEN, never 3, 9 or 15


def tep_onset(ff, fa, fault, runs):
    """First sample at which faulty run r of `fault` differs from fault-free run r.

    Rieth et al. seeded each faulty run like the fault-free run with the same number, so
    the two are identical until the fault is switched on. Returns one sample per run.
    """
    firsts = []
    for r in runs:
        a = fa[(fa.faultNumber == fault) & (fa.simulationRun == r)].sort_values("sample")
        z = ff[ff.simulationRun == r].sort_values("sample")
        same = np.all(a[CH].to_numpy() == z[CH].to_numpy(), axis=1)
        k = int(np.argmin(same))
        assert same[:k].all() and not same[k], "runs differ from the start"
        firsts.append(int(a["sample"].iloc[k]))
    return firsts


def tep_trace(frame):
    """Hours and reactor pressure for one run, with sample k at k x 3 minutes."""
    frame = frame.sort_values("sample")
    return frame["sample"].to_numpy() * 3 / 60, frame["xmeas_7"].to_numpy()


def card(name, draw, xticks, yticks, xlabel, ylabel, xscale="linear"):
    """A dataset thumbnail: exactly 3.4 x 2.3 inches, 15 pt text, no title."""
    style = {
        "font.size": 15,
        "axes.labelsize": 15,
        "xtick.labelsize": 15,
        "ytick.labelsize": 15,
        "savefig.bbox": "standard",
    }
    with plt.rc_context(style):
        fig = plt.figure(figsize=(3.4, 2.3))
        ax = fig.add_axes([0.285, 0.305, 0.675, 0.655])
        draw(ax)
        ax.set_xscale(xscale)
        ax.set_xticks(xticks, [f"{t:g}".replace("-", "\u2212") for t in xticks])
        ax.set_yticks(yticks, [f"{t:g}".replace("-", "\u2212") for t in yticks])
        ax.minorticks_off()
        ax.set_xlabel(xlabel, labelpad=2)
        ax.set_ylabel(ylabel, labelpad=6)
        ax.tick_params(
            length=3,
            pad=2,
        )
        save(fig, name)


def bare_card(name, draw):
    """A thumbnail with no axes, ticks or labels, the same 3.4 x 2.3 inches as card().

    The synthetic set is shown 96 px tall beside a line of text, where tick labels would
    be too small to read, so it carries only the points.
    """
    with plt.rc_context({"savefig.bbox": "standard"}):
        fig = plt.figure(figsize=(3.4, 2.3))
        ax = fig.add_axes([0.03, 0.04, 0.94, 0.92])
        draw(ax)
        ax.axis("off")
        save(fig, name)


def example_figures():
    print("\n=== The four datasets, introduced ===")
    df = load_logzsv()
    lc, lz = df["log-conc"].to_numpy(), df["log-zsv"].to_numpy()
    print(f"  surfactant: {len(df)} experiments, log concentration {lc.min():.2f} to {lc.max():.2f},"
          f" viscosity from {np.exp(lz).min():.2f} to {np.exp(lz).max():.1f} ({np.exp(lz).max() / np.exp(lz).min():.0f}x)")
    with plt.rc_context(fonts(14)):             # shown at w:560
        fig, ax = plt.subplots(figsize=(5.9, 2.7))
        ax.scatter(
            lc,
            lz,
            s=45,
            color=BLUE,
            edgecolor="white",
            linewidth=0.6,
            zorder=3,
        )
        ax.set(
            xlabel="Log concentration",
            ylabel="Log zero-shear\nviscosity",
        )
        save(fig, "surfactant-data.png")

    ff, fa = load_tep()
    firsts = tep_onset(ff, fa, TEP_FAULT, range(1, 21))
    print(f"  TEP fault {TEP_FAULT}, runs 1-20: each identical to the fault-free run of the same number through"
          f" sample {min(firsts) - 1} and first different at sample {sorted(set(firsts))}")
    others = sorted({s for f in SEEN for s in tep_onset(ff, fa, f, range(1, 4))})
    print(f"  every fault in SEEN, runs 1-3: identical through sample 20 at least, first differences at samples"
          f" {others} (a slow fault takes longer to reach the 52 channels)")
    onset = (min(firsts) - 1) * 3 / 60
    print(f"  so the fault starts after sample {min(firsts) - 1}, at {onset:.2f} hours (samples every 3 minutes)")
    t0, p0 = tep_trace(ff[ff.simulationRun == TEP_RUN])
    t1, p1 = tep_trace(fa[(fa.faultNumber == TEP_FAULT) & (fa.simulationRun == TEP_RUN)])
    print(f"  run {TEP_RUN}: fault-free pressure {p0.min():.0f} to {p0.max():.0f} kPa;"
          f" fault {TEP_FAULT} pressure {p1.min():.0f} to {p1.max():.0f} kPa")
    with plt.rc_context(fonts(14)):             # shown at w:700
        fig, ax = plt.subplots(figsize=(7.7, 2.75))
        ax.plot(
            t0,
            p0,
            color="0.55",
            lw=1.1,
            label=f"Fault-free run {TEP_RUN}",
        )
        ax.plot(
            t1,
            p1,
            color=CMU_RED,
            lw=1.3,
            label=f"Fault {TEP_FAULT}, run {TEP_RUN} (A/C feed ratio step)",
        )
        ax.axvline(
            onset,
            color=INK,
            ls="--",
            lw=1.1,
        )
        ax.text(
            onset + 0.3,
            2585,
            f"Fault {TEP_FAULT} starts at {onset:.0f} hour",
            color=INK,
            va="bottom",
        )
        ax.set(
            xlabel="Time (hours)",
            ylabel="Reactor pressure,\nxmeas_7 (kPa)",
            xlim=(0, 25),
            ylim=(2580, 2850),
            yticks=[2600, 2700, 2800],
        )
        ax.legend(
            loc="upper right",
            handlelength=1.5,
            borderaxespad=0.2,
        )
        save(fig, "tep-data.png")

    print("  dataset cards, 3.4 x 2.3 in each")
    T, P = load_water()

    def points(xs, ys):
        return lambda ax: ax.plot(
            xs,
            ys,
            "o",
            color=BLUE,
            ms=5,
        )

    card(
        "card-water.png",
        points(T, P),
        xticks=[0, 50, 100],
        yticks=[0, 50, 100],
        xlabel="T (C)",
        ylabel="P (MPa)",
    )
    card(
        "card-surfactant.png",
        points(lc, lz),
        xticks=[2, 4, 6],
        yticks=[0, 3, 6],
        xlabel="Log conc.",
        ylabel="Log visc.",
    )
    con = load_concrete()

    # The same gray dots as concrete-data.png, and the mix it follows for a year.
    year, year_color = example_mixes(con)[1]

    def concrete_card(ax):
        ax.scatter(
            con.age_days,
            con.strength_mpa,
            s=5,
            color="0.78",
            linewidths=0,
        )
        ax.plot(
            year.age_days,
            year.strength_mpa,
            "o-",
            color=year_color,
            lw=1.8,
            ms=4.5,
        )

    card(
        "card-concrete.png",
        concrete_card,
        xticks=[1, 10, 100],
        yticks=[0, 40, 80],
        xlabel="Age (days)",
        ylabel="Strength (MPa)",
        xscale="log",
    )

    def tep_card(ax):
        ax.plot(
            t1,
            p1,
            color=CMU_RED,
            lw=1.1,
        )
        ax.axvline(
            onset,
            color=INK,
            ls="--",
            lw=1,
        )

    card(
        "card-tep.png",
        tep_card,
        xticks=[0, 10, 20],
        yticks=[2650, 2750],
        xlabel="Hours",
        ylabel="P (kPa)",
    )
    X, y, Xtr, _, ytr, _ = cuberoot_data()

    def cuberoot_card(ax):
        xs = np.linspace(0, 1, 200)
        ax.plot(
            Xtr[:, 0],
            ytr[:, 0],
            "o",
            ms=5,
            color=BLUE,
            alpha=0.7,
            markeredgewidth=0,
        )
        ax.plot(
            xs,
            xs ** (1 / 3),
            color=INK,
            lw=2.4,
        )

    bare_card("card-cuberoot.png", cuberoot_card)


# --------------------------------------------------------------------------------------
# Victor's F25 figures, regenerated
# --------------------------------------------------------------------------------------
def water_figures():
    print("\n=== Water, NIST isochoric at 1000 kg/m3 (Victor's F25 lecture 6) ===")
    T, P = load_water()
    print(f"  {len(T)} rows, T {T.min():.2f} to {T.max():.2f} C, P {P.min():.3f} to {P.max():.2f} MPa")
    X = np.array([T**3, T**2, T, T**0]).T
    Xtr, Xte, ytr, yte = train_test_split(X, P, test_size=0.2, shuffle=True, random_state=42)
    model = LinearRegression().fit(Xtr, ytr)
    print(f"  third-degree polynomial: train R2 {model.score(Xtr, ytr):.7f}, test R2 {model.score(Xte, yte):.7f}")
    print(f"  coefficients {model.coef_}")
    Tex = np.linspace(-50, 300)
    Xex = np.array([Tex**3, Tex**2, Tex, Tex**0]).T
    print(f"  extrapolated P at -50 C {model.predict(Xex)[0]:.1f} MPa, at 300 C {model.predict(Xex)[-1]:.1f} MPa")

    Tt, Pt = load_water_truth()
    print(f"  NIST truth at 300 C: {Pt[-1]:.1f} MPa (the polynomial says {model.predict(Xex)[-1]:.1f})")
    with plt.rc_context(fonts(13)):             # shown at w:1000
        fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4))
        a.plot(
            T,
            P,
            "-",
            color=INK,
            label="Data",
        )
        a.plot(
            Xtr[:, 2],
            model.predict(Xtr),
            "o",
            color=CMU_RED,
            label="Train",
        )
        a.plot(
            Xte[:, 2],
            model.predict(Xte),
            "s",
            color=BLUE,
            label="Test",
        )
        a.set(
            xlabel="Temperature (C)",
            ylabel="Pressure (MPa)",
            title="Inside the data: a good fit",
        )
        a.legend()
        b.plot(
            Tt,
            Pt,
            "--",
            color=INK,
            lw=1.2,
            label="NIST, not in the data",
        )
        b.plot(
            T,
            P,
            "o",
            color=INK,
            label="Data",
        )
        b.plot(
            Tex,
            model.predict(Xex),
            "-",
            color=CMU_RED,
            label="Third-degree polynomial",
        )
        b.axvspan(
            T.min(),
            T.max(),
            color="0.92",
            zorder=0,
            label="Range of the data",
        )
        b.set(
            xlabel="Temperature (C)",
            ylabel="Pressure (MPa)",
            title="Outside the data: no physics",
        )
        b.legend(loc="upper left")
        save(fig, "water-polynomial.png")

    # The same polynomial, alone, from 0 to 300 C: the hook on which the lecture opens.
    Th = np.linspace(0, 300, 301)
    Ph = model.predict(np.array([Th**3, Th**2, Th, Th**0]).T)
    print(f"  water-hook: at {Th[-1]:.0f} C the polynomial says {Ph[-1]:.1f} MPa and NIST {Pt[-1]:.1f} MPa"
          f" (at {Tt[-1]:.2f} C), {Ph[-1] / Pt[-1]:.0%} of the true pressure;"
          f" the polynomial peaks at {Ph.max():.0f} MPa at {Th[np.argmax(Ph)]:.0f} C and then falls")
    with plt.rc_context(fonts(14)):             # shown at w:760
        fig, ax = plt.subplots(figsize=(7.0, 3.9))
        ax.axvspan(
            T.min(),
            T.max(),
            color="0.92",
            lw=0,
            zorder=0,
        )
        ax.text(
            (T.min() + T.max()) / 2,
            560,
            "Data",
            ha="center",
            va="top",
            color=MUTED,
        )
        ax.plot(
            Tt,
            Pt,
            "--",
            color=INK,
            lw=1.3,
            zorder=2,
        )
        ax.plot(
            Th,
            Ph,
            color=CMU_RED,
            lw=2.2,
            zorder=3,
        )
        ax.plot(
            T,
            P,
            "o",
            color=INK,
            ms=5,
            zorder=4,
        )
        # The NIST label sits left of its marker; the polynomial's sits under its marker,
        # below the curve, which peaks (printed above) and turns down before 300 C.
        for value, col, text, offset, va in [
            (Pt[-1], INK, f"NIST: {Pt[-1]:.1f} MPa", (-12, 0), "center"),
            (Ph[-1], CMU_RED, f"Polynomial: {Ph[-1]:.0f} MPa", (0, -14), "top"),
        ]:
            ax.plot(
                300,
                value,
                "o",
                color=col,
                ms=9,
                zorder=5,
                clip_on=False,
            )
            ax.annotate(
                text,
                (300, value),
                xytext=offset,
                textcoords="offset points",
                ha="right",
                va=va,
                color=col,
            )
        ax.set(
            xlabel="Temperature (°C)",
            ylabel="Pressure (MPa)",
            xlim=(0, 300),
            ylim=(-15, 570),
            xticks=[0, 100, 200, 300],
            yticks=[0, 200, 400],
        )
        save(fig, "water-hook.png")

    print("  lasso sweep (alpha, coefficients T^3 T^2 T 1, train R2):")
    alphas = np.logspace(-15, 4, 10)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(T, P, "bo", label="Data")
    for alpha in alphas:
        m = Lasso(alpha=alpha, max_iter=50000).fit(Xtr, ytr)
        print(f"    {alpha:8.1e}  {np.array2string(m.coef_, precision=6)}  {m.score(Xtr, ytr):.7f}")
        x, y = Xtr[:, 2], m.predict(Xtr)
        i = np.argsort(x)
        ax.plot(x[i], y[i], "-", label=f"{alpha:.1e}")     # as the notes' table writes it
    ax.set(xlabel="Temperature (C)", ylabel="Pressure (MPa)", title="Lasso, from alpha = 1e-15 to 1e4")
    ax.legend(ncol=2, fontsize=9, loc="upper left")
    save(fig, "lasso-alphas.png")

    # The tree is fitted on T alone. On the four polynomial columns it split on whichever of
    # T^3, T^2 and T it drew first among equally good cuts, so the drawn thresholds changed
    # from run to run and did not read as temperatures. On 0 to 100 C the three columns
    # order the rows the same way, so the regions and the leaf values are the same.
    tree = DecisionTreeRegressor(
        max_depth=2,
        random_state=0,
    ).fit(Xtr[:, [2]], ytr)
    print(f"  depth-2 tree: test R2 {tree.score(Xte[:, [2]], yte):.4f}")
    t_ = tree.tree_
    leaf = t_.children_left == -1
    print(f"  depth-2 tree on T alone: splits T <= {[round(float(c), 2) for c in t_.threshold[~leaf]]} (root first);"
          f" leaves {[int(n) for n in t_.n_node_samples[leaf]]} samples,"
          f" values {[round(float(v), 2) for v in t_.value[leaf, 0, 0]]} MPa")
    with plt.rc_context(fonts(14)):             # shown at w:820
        fig, (a, b) = plt.subplots(
            1,
            2,
            figsize=(10.4, 3.55),
            gridspec_kw={"width_ratios": [1, 1.2], "wspace": 0.05},
        )
        Td = np.linspace(T.min(), T.max(), 800)
        a.scatter(
            T,
            P,
            color=BLUE,
            label="Data",
        )
        a.plot(
            Td,
            tree.predict(Td.reshape(-1, 1)),
            color=GREEN,
            lw=2,
            label="Depth-2 tree",
        )
        a.set(
            xlabel="Temperature (C)",
            ylabel="Pressure (MPa)",
            title="Four leaves, four constant values",
        )
        a.legend(loc="upper left")
        boxes = plot_tree(
            tree,
            feature_names=["T"],
            label="root",
            filled=False,
            rounded=True,
            impurity=False,
            ax=b,
            fontsize=14,
            precision=2,
        )
        for box in boxes:
            patch = box.get_bbox_patch()
            if patch is not None:
                patch.set(
                    facecolor="#e6f2e6",
                    edgecolor=GREEN,
                )
        # plot_tree writes True and False on the baseline, halfway between the root and its
        # children, so at 14 pt they run into the root box; center them in the gap instead.
        for box in boxes:
            if box.get_text().strip() in ("True", "False"):
                box.set_verticalalignment("center")
        b.set_title("The same tree, drawn")
        save(fig, "tree-water.png")
    return T, P


def nn_figures():
    print("\n=== Neural network on y = x^(1/3) + noise (Victor's F25 lecture 7) ===")
    X, y, Xtr, Xte, ytr, yte = cuberoot_data()

    def model(x, *p):
        b1, w10, w00, b00, w11, w01, b01, w12, w02, b02 = p
        return (b1 + w10 * np.tanh(w00 * x + b00) + w11 * np.tanh(w01 * x + b01)
                + w12 * np.tanh(w02 * x + b02))

    def loss(p, X, y):
        return np.sum((y - model(X, *p)) ** 2)

    sol = minimize(loss, np.random.default_rng(1).normal(size=10), args=(Xtr, ytr), tol=1e-5)
    r2_min = r2_score(yte, model(Xte, *sol.x))
    nn = MLPRegressor(hidden_layer_sizes=(3,), activation="tanh", solver="lbfgs",
                      alpha=0.0, max_iter=5000, random_state=0).fit(Xtr, ytr.ravel())
    r2_nn = r2_score(yte, nn.predict(Xte))
    print(f"  scipy.optimize.minimize, 10 parameters: SSE {sol.fun:.4f}, test R2 {r2_min:.3f}")
    print(f"  MLPRegressor(3, tanh, lbfgs):            test R2 {r2_nn:.3f}")

    # The data alone, as Victor's F25 lecture 7 opens.
    print(f"  nn-data: {len(X)} points, {len(Xtr)} training and {len(Xte)} test (80/20, random_state=42)")
    x01 = np.linspace(0, 1, 400)
    with plt.rc_context(fonts(14)):             # shown at w:720 (w:600 in an earlier layout)
        fig, ax = plt.subplots(figsize=(6.4, 3.0))
        ax.plot(
            x01,
            x01 ** (1 / 3),
            color="0.6",
            lw=1.2,
            zorder=1,
            label="True curve $y = x^{1/3}$",
        )
        ax.scatter(
            Xtr[:, 0],
            ytr,
            s=20,
            color=BLUE,
            zorder=2,
            label=f"Training ({len(Xtr)} points)",
        )
        ax.scatter(
            Xte[:, 0],
            yte,
            s=20,
            color=GOLD,
            zorder=3,
            label=f"Test ({len(Xte)} points)",
        )
        ax.set(
            xlabel="x",
            ylabel="y",
            yticks=[0, 0.5, 1],
        )
        # 16 pt, so that the superscript 1/3, at 0.7 of the line, stays readable.
        ax.set_title(
            "Data: $y = x^{1/3} + \\varepsilon$",
            fontsize=16,
        )
        ax.legend(
            loc="lower right",
            handlelength=1.5,
        )
        save(fig, "nn-data.png")

    # How the equation builds the fit: each unit's term, then the sum. The minimize solution
    # has large terms that nearly cancel, so each term gets its own axis with the same
    # vertical span; the shapes, and how much each moves over [0, 1], are then comparable.
    b1 = sol.x[0]
    units = [sol.x[1 + 3 * k:4 + 3 * k] for k in range(3)]          # (w1k, w0k, b0k)
    names = ["b1", "w10", "w00", "b00", "w11", "w01", "b01", "w12", "w02", "b02"]
    print("  nn-terms, the minimize solution: " + ", ".join(f"{n} {v:.4f}" for n, v in zip(names, sol.x)))
    terms = [w1 * np.tanh(w0 * x01 + b0) for w1, w0, b0 in units]
    for k, t in enumerate(terms):
        print(f"    unit {k}: w1{k} tanh(w0{k} x + b0{k}) from {t[0]:.3f} at x = 0 to {t[-1]:.3f} at x = 1,"
              f" a range of {t.max() - t.min():.3f}")
    fit = b1 + sum(terms)
    print(f"    b1 plus the three: {fit[0]:.3f} at x = 0, {fit[-1]:.3f} at x = 1"
          f" (the model gives {model(0.0, *sol.x):.3f} and {model(1.0, *sol.x):.3f})")
    with plt.rc_context(fonts(13)):             # shown at w:1080
        # The fitted terms are large and nearly cancel (offsets near -37, -23 and +64), so each
        # is drawn shifted to zero at x = 0: the shapes are what add up, and the three shifts and
        # b1 fold into one constant.
        fig, (left, right) = plt.subplots(
            1,
            2,
            figsize=(11.2, 3.9),
        )
        for k, (t, col) in enumerate(zip(terms, UNIT_COLORS)):
            left.plot(
                x01,
                t - t[0],
                color=col,
                lw=2.6,
                label=f"Unit {k + 1}: $w_{{1{k}}}\\tanh(w_{{0{k}}}x + b_{{0{k}}})$",
            )
        # The terms stay under 0.45; the headroom above them holds the three-row legend.
        left.set(
            xlim=(0, 1),
            ylim=(-0.03, 0.74),
            yticks=[0, 0.2, 0.4],
            xlabel="x",
            ylabel="Change from x = 0",
            title="Each unit's term, shifted to start at 0",
        )
        left.legend(
            loc="upper left",
            fontsize=12,
            borderaxespad=0.2,
        )
        right.scatter(
            Xtr[:, 0],
            ytr,
            s=16,
            color="0.7",
            label="Training points",
        )
        right.plot(
            x01,
            fit,
            color=CMU_RED,
            lw=3,
            label="$f(x)$",
        )
        right.set(
            xlabel="x",
            ylabel="y",
            xlim=(0, 1),
            title="Their sum plus $b_1$: the fit",
        )
        right.legend(loc="lower right")
        save(fig, "nn-terms.png")


    xx = np.linspace(0, 1.1, 400)
    with plt.rc_context(fonts(13)):             # shown at w:880
        fig, (a, b) = plt.subplots(
            1,
            2,
            figsize=(11, 3.8),
            sharey=True,
        )
        panels = [
            (a, model(xx, *sol.x), f"Written out, fitted with minimize\nTest $R^2$ = {r2_min:.2f}"),
            (b, nn.predict(xx.reshape(-1, 1)), f"MLPRegressor, 3 tanh units\nTest $R^2$ = {r2_nn:.2f}"),
        ]
        for ax, yhat, title in panels:
            ax.scatter(
                Xtr[:, 0],
                ytr,
                s=16,
                color=BLUE,
                label="Train",
                alpha=0.8,
            )
            ax.scatter(
                Xte[:, 0],
                yte,
                s=16,
                color=GOLD,
                label="Test",
                alpha=0.8,
            )
            ax.plot(
                xx,
                yhat,
                color=CMU_RED,
                lw=2,
                label="Model",
            )
            ax.set(
                xlabel="x",
                title=title,
            )
        a.set_ylabel("y")
        a.legend(loc="lower right")
        save(fig, "nn-tanh.png")

    # Ten random starting points for the same network: a non-convex problem.
    fits = []
    for s in range(10):
        m = MLPRegressor(hidden_layer_sizes=(3,), activation="tanh", solver="lbfgs",
                         alpha=0.0, max_iter=5000, random_state=s).fit(Xtr, ytr.ravel())
        sse = float(np.sum((ytr.ravel() - m.predict(Xtr)) ** 2))
        fits.append((s, sse, r2_score(yte, m.predict(Xte)), m))
    sses = np.array([f[1] for f in fits])
    print("  ten random starts, 3 tanh units, L-BFGS (seed, training SSE, test R2):")
    for s, sse, r2, _ in fits:
        print(f"    {s}: {sse:.4f}  {r2:.3f}")
    print(f"  training SSE from {sses.min():.4f} to {sses.max():.4f} ({sses.max() / sses.min():.2f}x);"
          f" test R2 from {min(f[2] for f in fits):.3f} to {max(f[2] for f in fits):.3f}")
    good = sses < 0.09
    with plt.rc_context(fonts(13)):             # shown at w:860
        fig, (a, b) = plt.subplots(
            1,
            2,
            figsize=(9.8, 3.45),
            gridspec_kw={"width_ratios": [1.4, 1]},
        )
        a.scatter(
            Xtr[:, 0],
            ytr,
            s=12,
            color="0.6",
            label="Train",
        )
        for (s, sse, _, m), ok in zip(fits, good):
            a.plot(
                xx,
                m.predict(xx.reshape(-1, 1)),
                color=BLUE if ok else CMU_RED,
                lw=1.2,
                alpha=0.8,
            )
        a.plot(
            [],
            [],
            color=BLUE,
            label="Ends near SSE 0.080",
        )
        a.plot(
            [],
            [],
            color=CMU_RED,
            label="Ends at SSE 0.107 to 0.118",
        )
        a.set(
            xlabel="x",
            ylabel="y",
            title="Same network, ten random starting weights",
        )
        a.legend(loc="lower right")
        order = np.argsort(sses)
        b.bar(range(10), sses[order], color=[BLUE if good[i] else CMU_RED for i in order])
        b.set_xticks(range(10), [str(i) for i in order])
        b.set(
            xlabel="random_state",
            ylabel="Training SSE",
            ylim=(0, 0.13),
            yticks=[0, 0.04, 0.08, 0.12],
            title="Where each start stopped",
        )
        save(fig, "nn-restarts.png")

    np.random.seed(0)
    N = 300
    x1 = np.random.rand(N, 1)
    x2 = 1e6 * np.random.rand(N, 1)
    X = np.hstack([x1, x2])
    y = 0.7 * np.sin(2 * np.pi * x1[:, 0]) + 0.3 * (x2[:, 0] / 1e6)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=42)
    mlp = lambda: MLPRegressor(hidden_layer_sizes=(20,), activation="tanh", solver="lbfgs",
                               max_iter=3000, random_state=0)
    no = mlp().fit(Xtr, ytr)
    yes = make_pipeline(StandardScaler(), mlp()).fit(Xtr, ytr)
    r2_no, r2_yes = r2_score(yte, no.predict(Xte)), r2_score(yte, yes.predict(Xte))
    print(f"  scaling: R2 without {r2_no:.5f}, with StandardScaler {r2_yes:.5f}")
    with plt.rc_context(fonts(13)):             # shown at w:800
        fig, axes = plt.subplots(
            1,
            2,
            figsize=(8.6, 3.4),
            sharey=True,
        )
        panels = [
            (axes[0], no, f"Without scaling ($R^2 = {r2_no:.3f}$)"),
            (axes[1], yes, f"With scaling ($R^2 = {r2_yes:.4f}$)"),
        ]
        for ax, m, title in panels:
            yh = m.predict(Xte)
            ax.scatter(
                yte,
                yh,
                color=BLUE,
                alpha=0.7,
            )
            lims = [min(yte.min(), yh.min()), max(yte.max(), yh.max())]
            ax.plot(
                lims,
                lims,
                "--",
                color=INK,
                lw=1,
            )
            ax.set(
                xlabel="True y",
                title=title,
            )
            ax.xaxis.set_major_locator(MaxNLocator(4))
            ax.yaxis.set_major_locator(MaxNLocator(4))
        axes[0].set_ylabel("Predicted y")
        save(fig, "nn-scaling.png")


def gp_figure():
    print("\n=== Gaussian process on the surfactant data (Victor's F25 lecture 8) ===")
    df = load_logzsv()
    X = np.array(df["log-conc"])[:, None]
    y = np.array(df["log-zsv"])
    print(f"  {len(df)} experiments")
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)
    sc = StandardScaler().fit(Xtr)
    gpr = GaussianProcessRegressor(alpha=0.1, kernel=RBF(1.0, (1e-3, 1e3)), normalize_y=True,
                                   random_state=0, n_restarts_optimizer=5).fit(sc.transform(Xtr), ytr)
    mat = GaussianProcessRegressor(
        kernel=ConstantKernel(1.0, (1e-3, 1e3)) * Matern(1.0, (1e-3, 1e3), nu=1.5)
        + WhiteKernel(1e-2, (1e-9, 1e1)),
        normalize_y=True, random_state=0, n_restarts_optimizer=5).fit(sc.transform(Xtr), ytr)
    print(f"  RBF kernel {gpr.kernel_}, test R2 {r2_score(yte, gpr.predict(sc.transform(Xte))):.3f}")
    print(f"  Matern kernel {mat.kernel_}, test R2 {r2_score(yte, mat.predict(sc.transform(Xte))):.3f}")
    xx = np.linspace(X.min(), X.max(), 400)[:, None]
    with plt.rc_context(fonts(13)):             # shown at w:900
        fig, axes = plt.subplots(
            1,
            2,
            figsize=(11, 3.45),
            sharey=True,
        )
        panels = [
            (axes[0], gpr, "RBF kernel"),
            (axes[1], mat, "Matérn kernel ($\\nu$ = 3/2)"),
        ]
        for ax, m, title in panels:
            mu, sd = m.predict(sc.transform(xx), return_std=True)
            ax.fill_between(
                xx[:, 0],
                mu - 2 * sd,
                mu + 2 * sd,
                color=CMU_RED,
                alpha=0.15,
                lw=0,
                label="Mean +/- 2 std",
            )
            ax.plot(
                xx[:, 0],
                mu,
                color=CMU_RED,
                lw=2,
                label="Mean",
            )
            ax.scatter(
                Xtr[:, 0],
                ytr,
                s=22,
                color=BLUE,
                zorder=3,
                label="Train",
            )
            ax.scatter(
                Xte[:, 0],
                yte,
                s=22,
                color=GOLD,
                zorder=3,
                label="Test",
            )
            ax.set(
                xlabel="Log concentration",
                title=title,
            )
        axes[0].set_ylabel("Log zero-shear viscosity")
        # Above both panels, where it covers no band and no data.
        handles, labels = axes[0].get_legend_handles_labels()
        order = [2, 3, 1, 0]                    # Train, Test, Mean, band
        fig.legend(
            [handles[i] for i in order],
            [labels[i] for i in order],
            loc="lower center",
            bbox_to_anchor=(0.5, 0.97),
            ncol=4,
            handlelength=1.5,
            columnspacing=1.6,
        )
        save(fig, "gp-surfactant.png")


def rbf(a, b, ell, sf2=1.0):
    """The squared exponential (RBF) kernel between two 1-D arrays of inputs."""
    return sf2 * np.exp(-(a[:, None] - b[None, :]) ** 2 / (2 * ell**2))


def instructor_f(u):
    """The test function of the instructor's GP slides, on u in [0.5, 10]."""
    return np.sin(u) + np.log(u) - np.exp(-0.1 * u**2)


def gp_intro_figures():
    """What a GP is: a distribution over functions, conditioned on data, set by its kernel."""
    print("\n=== A Gaussian process, introduced: prior, posterior and kernel ===")
    rng = np.random.default_rng(0)
    draws = rng.normal(size=15)
    xs = np.linspace(0, 1, 200)
    ell = 0.3
    fs = rng.multivariate_normal(
        np.zeros(xs.size),
        rbf(xs, xs, ell),
        size=5,
        method="eigh",
    )
    print(f"  gp-idea: 15 draws from N(0, 1), mean {draws.mean():.2f}, std {draws.std(ddof=1):.2f};"
          f" five functions from a GP prior, mean 0, RBF kernel with length scale {ell} on [0, 1], seed 0")
    with plt.rc_context(fonts(14)):             # shown at w:1080 (w:980 in an earlier layout)
        fig, (a, b) = plt.subplots(
            1,
            2,
            figsize=(11, 3.1),
            gridspec_kw={"width_ratios": [1, 1.3], "wspace": 0.22},
        )
        z = np.linspace(-3.5, 3.5, 300)
        a.fill_between(
            z,
            np.exp(-z**2 / 2) / np.sqrt(2 * np.pi),
            color=BLUE,
            alpha=0.12,
            lw=0,
        )
        a.plot(
            z,
            np.exp(-z**2 / 2) / np.sqrt(2 * np.pi),
            color=BLUE,
            lw=2,
        )
        a.plot(
            draws,
            np.full_like(draws, 0.025),
            "|",
            color=INK,
            ms=16,
            mew=2,
            label="15 sampled\nvalues",
        )
        a.set(
            xlabel="Value",
            ylabel="Probability density",
            xlim=(-3.5, 3.5),
            ylim=(0, 0.45),
            yticks=[0, 0.2, 0.4],
            title="A distribution of numbers",
        )
        a.legend(
            loc="upper left",
            handlelength=1,
            markerscale=0.7,
            borderaxespad=0.1,
        )
        b.fill_between(
            xs,
            -2 * np.ones_like(xs),
            2 * np.ones_like(xs),
            color="0.92",
            lw=0,
            label="Mean +/- 2 std",
        )
        b.axhline(
            0,
            color=INK,
            lw=1.4,
            ls="--",
            label="Mean",
        )
        sample_lines = []
        for f, col in zip(fs, [BLUE, GOLD, GREEN, CMU_RED, MUTED]):
            (line,) = b.plot(
                xs,
                f,
                color=col,
                lw=1.8,
            )
            sample_lines.append(line)
        # Headroom above the samples, which stay under 2.6, for a one-row legend.
        b.set(
            xlabel="x",
            ylabel="f(x)",
            xlim=(0, 1),
            ylim=(-3, 4.4),
            yticks=[-2, 0, 2],
            title="A distribution of functions",
        )
        # One legend entry for the five samples, its handle showing all five colors.
        handles, labels = b.get_legend_handles_labels()
        b.legend(
            [tuple(sample_lines), handles[labels.index("Mean")], handles[labels.index("Mean +/- 2 std")]],
            ["Five samples", "Mean", "Mean +/- 2 std"],
            handler_map={tuple: HandlerTuple(ndivide=None, pad=0)},
            loc="upper center",
            ncol=3,
            handlelength=2.0,
            handletextpad=0.5,
            columnspacing=0.8,
            borderaxespad=0.1,
        )
        save(fig, "gp-idea.png")

    # Prior to posterior on the instructor's function. The hyperparameters are fitted once, on
    # all 20 points, and then held fixed, so that only the data change from panel to panel.
    rng = np.random.default_rng(1)
    noise = 0.1
    u = rng.uniform(0.5, 10, 20)
    yu = instructor_f(u) + rng.normal(0, noise, u.size)
    fit = GaussianProcessRegressor(
        kernel=ConstantKernel(1.0, (1e-2, 1e2)) * RBF(1.0, (1e-2, 1e2)) + WhiteKernel(1e-2, (1e-6, 1e0)),
        n_restarts_optimizer=5,
        random_state=0,
    ).fit(u[:, None], yu)
    sf2 = fit.kernel_.k1.k1.constant_value
    ell_u = fit.kernel_.k1.k2.length_scale
    sn2 = fit.kernel_.k2.noise_level
    print(f"  gp-posterior: f(u) = sin(u) + log(u) - exp(-0.1 u^2), 20 points uniform on [0.5, 10], noise std {noise},"
          f" seed 1; first five u {np.round(u[:5], 2).tolist()}")
    print(f"    kernel fitted once on the 20 points: {fit.kernel_} (signal std {np.sqrt(sf2):.2f},"
          f" length scale {ell_u:.2f}, noise std {np.sqrt(sn2):.3f}); prior mean 0")
    uu = np.linspace(0.5, 10, 400)
    truth = instructor_f(uu)
    panels = [(0, "Prior"), (2, "After 2 points"), (5, "After 5 points"), (20, "After 20 points")]
    with plt.rc_context(fonts(14)):             # shown at w:1100
        fig, axes = plt.subplots(
            1,
            4,
            figsize=(12.4, 3.2),
            sharey=True,
            gridspec_kw={"wspace": 0.08},
        )
        for ax, (n, title) in zip(axes, panels):
            if n == 0:
                mu, var = np.zeros_like(uu), np.full_like(uu, sf2)
            else:
                K = rbf(u[:n], u[:n], ell_u, sf2) + sn2 * np.eye(n)
                ks = rbf(uu, u[:n], ell_u, sf2)
                mu = ks @ np.linalg.solve(K, yu[:n])
                var = sf2 - np.sum(ks * np.linalg.solve(K, ks.T).T, axis=1)
            sd = np.sqrt(np.maximum(var, 0))
            rmse = np.sqrt(np.mean((mu - truth) ** 2))
            print(f"    {title:15s}: RMSE of the mean against f {rmse:.3f}; 95% band half-width"
                  f" {1.96 * sd.mean():.2f} on average, {1.96 * sd.max():.2f} at most")
            ax.fill_between(
                uu,
                mu - 1.96 * sd,
                mu + 1.96 * sd,
                color=CMU_RED,
                alpha=0.15,
                lw=0,
                label="95% band",
            )
            ax.plot(
                uu,
                truth,
                color="0.55",
                lw=1.2,
                label="True function",
            )
            ax.plot(
                uu,
                mu,
                color=CMU_RED,
                lw=2,
                label="Mean",
            )
            if n:
                ax.plot(
                    u[:n],
                    yu[:n],
                    "o",
                    color=INK,
                    ms=5,
                    zorder=4,
                    label="Observations",
                )
            ax.set(
                xlabel="u",
                title=title,
                xlim=(0.5, 10),
                xticks=[2, 6, 10],
            )
        axes[0].set(
            ylabel="f(u)",
            ylim=(-4.4, 4.4),
            yticks=[-4, 0, 4],
        )
        handles, labels = axes[-1].get_legend_handles_labels()
        order = [1, 2, 0, 3]                    # True function, Mean, band, Observations
        fig.legend(
            [handles[i] for i in order],
            [labels[i] for i in order],
            loc="lower center",
            bbox_to_anchor=(0.5, 0.98),
            ncol=4,
            handlelength=1.5,
            columnspacing=1.6,
        )
        save(fig, "gp-posterior.png")

    # The kernel itself, the instructor's "squared exponential" picture, at three length scales.
    d = np.linspace(-8, 8, 801)
    ells = [0.3, 1, 3]
    print("  gp-kernel: k = exp(-(x - x')^2 / (2 l^2)); similarity at distance 1: "
          + ", ".join(f"l = {e:g}: {np.exp(-1 / (2 * e**2)):.3f}" for e in ells))
    with plt.rc_context(fonts(14)):             # shown at w:760 (w:540 in an earlier layout)
        fig, ax = plt.subplots(figsize=(5.8, 3.4))
        for e, col in zip(ells, [CMU_RED, GOLD, BLUE]):
            ax.plot(
                d,
                np.exp(-d**2 / (2 * e**2)),
                color=col,
                lw=2.2,
                label=f"$\\ell$ = {e:g}",
            )
        ax.set(
            xlabel="Distance $x - x'$",
            ylabel="Similarity $k(x, x')$",
            xlim=(-8, 8),
            ylim=(0, 1.15),
            xticks=[-8, -4, 0, 4, 8],
            yticks=[0, 0.5, 1],
        )
        # Upper right, where even the longest length scale has fallen below 0.55.
        ax.legend(
            title="Length scale",
            loc="upper right",
            handlelength=1.5,
            borderaxespad=0.1,
        )
        save(fig, "gp-kernel.png")


def cv_picture():
    print("\n=== k-fold and grouped k-fold, drawn ===")
    n, k = 30, 5
    groups = np.repeat(np.arange(10), 3)
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True)
    for ax, cv, title, kw in [(a, KFold(k, shuffle=True, random_state=0), "KFold (shuffled rows)", {}),
                              (b, GroupKFold(k), "GroupKFold (groups of 3 rows)", {"groups": groups})]:
        for i, (tr, te) in enumerate(cv.split(np.zeros(n), **kw)):
            ax.scatter(tr, [i] * len(tr), marker="s", s=60, color="0.8", linewidths=0)
            ax.scatter(te, [i] * len(te), marker="s", s=60, color=CMU_RED, linewidths=0)
        if ax is b:
            for g in range(3, n, 3):
                ax.axvline(g - 0.5, color="0.6", lw=0.6)
        ax.set(xlabel="Sample index", title=title, yticks=range(k),
               yticklabels=[f"Fold {i + 1}" for i in range(k)])
    a.set_ylim(k - 0.5, -0.5)
    a.scatter([], [], marker="s", color="0.8", label="Training")
    a.scatter([], [], marker="s", color=CMU_RED, label="Validation")
    fig.legend(loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.07))
    save(fig, "cv-splitters.png")


def concrete_grouping_figure():
    """Real concrete mixes in random and in grouped folds: one row per mix, one cell per test."""
    print("\n=== Six concrete mixes in KFold and GroupKFold, drawn ===")
    df = load_concrete()
    # The first six mixes in the file tested at exactly 3, 7, 28 and 90 days: a full grid.
    ages = (3, 7, 28, 90)
    mixes = [g.sort_values("age_days") for _, g in df.groupby(MIX, sort=False)
             if tuple(sorted(g.age_days)) == ages][:6]
    rows = pd.concat(mixes)
    mix_id = np.repeat(np.arange(len(mixes)), len(ages))
    k = 3
    shuffled = KFold(
        k,
        shuffle=True,
        random_state=0,
    )
    schemes = [
        (shuffled, None, "Random folds: one mix in several folds"),
        (GroupKFold(k), mix_id, "Grouped folds: one mix, one fold"),
    ]
    folds = []
    for cv, groups, _ in schemes:
        fold = np.empty(len(rows), int)
        for f, (_, te) in enumerate(cv.split(rows, groups=groups)):
            fold[te] = f
        folds.append(fold.reshape(len(mixes), len(ages)))
    print("  six mixes, first in the file tested at 3, 7, 28 and 90 days"
          " (kg/m3: cement, slag, fly ash, water, superplasticizer, coarse, fine; strengths in MPa):")
    for i, g in enumerate(mixes):
        print(f"    Mix {i + 1}: {', '.join(f'{v:g}' for v in g[MIX].iloc[0])};"
              f" {', '.join(f'{v:.1f}' for v in g.strength_mpa)};"
              f" KFold folds {(folds[0][i] + 1).tolist()}, GroupKFold fold {folds[1][i, 0] + 1}")
    spread = sum(len(set(r)) > 1 for r in folds[0])
    print(f"  KFold(3, shuffle=True, random_state=0) puts {spread} of the 6 mixes in more than one fold;"
          f" GroupKFold(3) puts every mix in one fold ({all(len(set(r)) == 1 for r in folds[1])})")
    colors = UNIT_COLORS                        # fold 1, 2, 3
    with plt.rc_context(fonts(14)):             # shown at w:1000 (w:900 in an earlier layout)
        fig, axes = plt.subplots(
            1,
            2,
            figsize=(9.6, 3.1),
            gridspec_kw={"wspace": 0.12},
        )
        for ax, fold, (_, _, title) in zip(axes, folds, schemes):
            for i in range(len(mixes)):
                for j in range(len(ages)):
                    ax.add_patch(Rectangle(
                        (j + 0.04, i + 0.06),
                        0.92,
                        0.88,
                        fc=colors[fold[i, j]],
                        ec="none",
                    ))
                    ax.text(
                        j + 0.5,
                        i + 0.5,
                        str(fold[i, j] + 1),
                        ha="center",
                        va="center",
                        color="white",
                        weight="bold",
                    )
            ax.set_xlim(0, len(ages))
            ax.set_ylim(len(mixes), 0)
            ax.set_xticks(np.arange(len(ages)) + 0.5, [str(a) for a in ages])
            ax.set_yticks(np.arange(len(mixes)) + 0.5, [f"Mix {i + 1}" for i in range(len(mixes))])
            ax.tick_params(
                length=0,
                pad=4,
            )
            for side in ("left", "bottom"):
                ax.spines[side].set_visible(False)
            ax.set(
                xlabel="Test age (days)",
                title=title,
            )
        axes[1].tick_params(labelleft=False)
        # At the right, so that the figure stays short above the slide's definition box.
        swatches = [
            Patch(
                color=c,
                label=f"Fold {f + 1}",
            )
            for f, c in enumerate(colors)
        ]
        axes[1].legend(
            handles=swatches,
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            handlelength=1.2,
        )
        save(fig, "concrete-grouping.png")


def extrapolation_figure(T, P):
    print("\n=== Four families on the water data, asked about temperatures they never saw ===")
    Tx = T.reshape(-1, 1)
    Tex = np.linspace(-50, 300, 400).reshape(-1, 1)
    models = [
        ("Polynomial, degree 3", make_pipeline(FunctionTransformer(lambda t: np.hstack([t**3, t**2, t])), LinearRegression())),
        ("Decision tree", DecisionTreeRegressor(random_state=0)),
        ("Neural network (3 tanh)", make_pipeline(StandardScaler(), MLPRegressor((3,), activation="tanh", solver="lbfgs", max_iter=5000, random_state=0))),
        ("Gaussian process (RBF)", make_pipeline(StandardScaler(), GaussianProcessRegressor(ConstantKernel() * RBF(1.0) + WhiteKernel(1e-3), normalize_y=True, random_state=0, n_restarts_optimizer=3))),
    ]
    Tt, Pt = load_water_truth()
    print(f"  NIST truth: {Pt[-1]:.1f} MPa at 300 C; models are fitted on all {len(T)} points from 0 to 100 C")
    with plt.rc_context(fonts(13)):             # shown at w:1120
        fig, axes = plt.subplots(
            1,
            4,
            figsize=(12.9, 3.0),
            sharey=True,
            gridspec_kw={"wspace": 0.12},
        )
        for ax, (name, m) in zip(axes, models):
            m.fit(Tx, P)
            ax.axvspan(
                T.min(),
                T.max(),
                color="0.92",
                zorder=0,
            )
            if name.startswith("Gaussian"):
                mu, sd = m.predict(Tex, return_std=True)
                ax.fill_between(
                    Tex[:, 0],
                    mu - 2 * sd,
                    mu + 2 * sd,
                    color=BLUE,
                    alpha=0.2,
                )
                ax.plot(Tex[:, 0], mu, color=BLUE)
                print(f"  GP at 300 C: {mu[-1]:.1f} +/- {2 * sd[-1]:.1f} MPa (band {mu[-1] - 2 * sd[-1]:.0f} to {mu[-1] + 2 * sd[-1]:.0f})")
            else:
                yh = m.predict(Tex)
                ax.plot(Tex[:, 0], yh, color=CMU_RED)
                print(f"  {name:24s} at 300 C: {yh[-1]:9.1f} MPa   at -50 C: {yh[0]:9.1f} MPa")
            ax.plot(
                Tt,
                Pt,
                "--",
                color=INK,
                lw=1.2,
            )
            ax.plot(
                T,
                P,
                "o",
                color=INK,
                ms=3,
            )
            ax.set(
                title=name,
                xlabel="Temperature (C)",
                xticks=[0, 100, 200, 300],
            )
        axes[0].set_ylabel("Pressure (MPa)")
        axes[0].set_ylim(-100, 560)
        axes[0].text(
            -45,
            535,
            "Dashed: NIST",
            color=MUTED,
            va="top",
        )
        save(fig, "extrapolation.png")


def optimizer_figure():
    """Four optimizers on one two-parameter least-squares problem, from one starting point."""
    print("\n=== Four optimizers on one fit: P = a + b (T / 20 C), mean squared error, water data ===")
    T, P = load_water()
    # T is divided by 20 C and not centered, so the intercept and the slope are correlated and
    # the loss valley is long and narrow, without being so narrow that gradient descent stalls.
    X = np.column_stack([np.ones_like(T), T / 20])
    N = len(P)
    hess = 2 / N * X.T @ X                    # the loss is quadratic, so this is exact
    eig = np.linalg.eigvalsh(hess)
    L = eig.max()
    w_opt = np.linalg.lstsq(X, P, rcond=None)[0]

    def loss(w):
        return float(np.mean((X @ w - P) ** 2))

    def grad(w, rows=slice(None)):
        Xb, Pb = X[rows], P[rows]
        return 2 / len(Pb) * Xb.T @ (Xb @ w - Pb)

    loss_opt = loss(w_opt)
    print(f"  Hessian eigenvalues {eig[0]:.4f} and {eig[1]:.4f}: condition number {eig[1] / eig[0]:.1f}")
    print(f"  optimum a = {w_opt[0]:.3f} MPa, b = {w_opt[1]:.3f} MPa per 20 C, loss {loss_opt:.3f} MPa^2")
    w0, cap, tol = np.array([30.0, -10.0]), 2000, 1e-6
    sgd_step, batch, adam_lr = 0.5 / L, 4, 1.0
    print(f"  start ({w0[0]:.0f}, {w0[1]:.0f}); cap {cap} iterations; target relative loss gap {tol:g}")

    paths = {}
    w = w0.copy()
    paths["gd"] = [w.copy()]
    for _ in range(cap):
        w = w - grad(w) / L
        paths["gd"].append(w.copy())

    rng = np.random.default_rng(0)
    w = w0.copy()
    paths["sgd"] = [w.copy()]
    while len(paths["sgd"]) <= cap:
        order = rng.permutation(N)                # 5 batches of 4 rows per pass, 1 row left out
        for j in range(0, N - batch + 1, batch):
            if len(paths["sgd"]) > cap:
                break
            w = w - sgd_step * grad(w, order[j:j + batch])
            paths["sgd"].append(w.copy())

    # Adam (Kingma and Ba 2015, Algorithm 1), on the full-batch gradient so that the only
    # difference from gradient descent is the update rule.
    b1, b2, eps = 0.9, 0.999, 1e-8
    w, m, v = w0.copy(), np.zeros(2), np.zeros(2)
    paths["adam"] = [w.copy()]
    for t in range(1, cap + 1):
        g = grad(w)
        m = b1 * m + (1 - b1) * g
        v = b2 * v + (1 - b2) * g * g
        w = w - adam_lr * (m / (1 - b1**t)) / (np.sqrt(v / (1 - b2**t)) + eps)
        paths["adam"].append(w.copy())

    paths["lbfgs"] = [w0.copy()]
    res = minimize(
        loss,
        w0,
        jac=grad,
        method="L-BFGS-B",
        callback=lambda wk: paths["lbfgs"].append(np.copy(wk)),
        options={"maxiter": cap, "ftol": 1e-15, "gtol": 1e-12},
    )

    def reached(gaps):
        """The first iteration from which the relative gap stays below tol, or None."""
        above = np.nonzero(gaps >= tol)[0]
        k = 0 if len(above) == 0 else above[-1] + 1
        return int(k) if k < len(gaps) else None

    methods = [
        ("gd", "Gradient descent", BLUE),
        ("sgd", f"Stochastic gradient descent, batches of {batch}", GOLD),
        ("adam", "Adam", GREEN),
        ("lbfgs", "L-BFGS", CMU_RED),
    ]
    # The legend names what each run was: Adam here uses the full-batch gradient.
    legend_names = {"adam": "Adam, full batch"}
    labels, gaps = {}, {}
    print(f"  steps: gradient descent 1/L = {1 / L:.4f}; SGD {sgd_step:.4f} (0.5/L, fixed, seed 0);"
          f" Adam learning rate {adam_lr:g}, beta1 {b1}, beta2 {b2}, eps {eps:g}")
    for key, name, _ in methods:
        paths[key] = np.array(paths[key])
        gaps[key] = np.array([loss(w) - loss_opt for w in paths[key]])
        k = reached(gaps[key] / loss_opt)
        n = len(paths[key]) - 1
        if k is None:
            last = gaps[key][-n // 4:] / loss_opt
            print(f"    {name:44s} did not stay below {tol:g} in {n} iterations;"
                  f" relative gap over the last quarter {last.min():.1e} to {last.max():.1e}")
            labels[key] = f"{legend_names.get(key, name)}\n(still jittering after {cap:,})"
        else:
            print(f"    {name:44s} {k:5d} iterations to stay below {tol:g}")
            labels[key] = f"{legend_names.get(key, name)} ({k:,} steps)"
    print(f"    L-BFGS: {res.nit} iterations, {res.nfev} loss and gradient evaluations, final a {res.x[0]:.3f}, b {res.x[1]:.3f}")

    # One panel, alone on its slide at w:1000; 15 pt so that it also reads at h:420.
    with plt.rc_context(fonts(15)):
        fig, a = plt.subplots(figsize=(9.5, 5.4))
        everything = np.vstack(list(paths.values()))
        lo, hi = everything.min(0), everything.max(0)
        pad = 0.12 * (hi - lo)
        A, B = np.meshgrid(
            np.linspace(lo[0] - pad[0], hi[0] + pad[0], 300),
            np.linspace(lo[1] - pad[1], hi[1] + pad[1], 300),
        )
        W = np.stack([A.ravel(), B.ravel()], axis=1)
        Z = np.mean((W @ X.T - P) ** 2, axis=1).reshape(A.shape) - loss_opt
        a.contour(
            A,
            B,
            Z,
            levels=loss_opt * np.logspace(-2, 2.5, 10),
            colors="0.78",
            linewidths=0.8,
        )
        path_style = {
            "gd": {"lw": 2.2, "zorder": 3},
            "sgd": {"lw": 0.8, "alpha": 0.9, "zorder": 2},
            "adam": {"lw": 2.2, "zorder": 3},
            "lbfgs": {"lw": 2, "marker": "o", "ms": 6, "zorder": 4},
        }
        colors = {key: col for key, _, col in methods}
        for key in ["lbfgs", "gd", "adam", "sgd"]:        # the legend's order
            a.plot(
                paths[key][:, 0],
                paths[key][:, 1],
                color=colors[key],
                label=labels[key],
                **path_style[key],
            )
        for point, marker, size in [(w0, "o", 9), (w_opt, "*", 18)]:
            a.plot(
                *point,
                marker,
                color=INK,
                ms=size,
                zorder=5,
            )
        a.annotate(
            "Start",
            w0,
            xytext=(10, -4),
            textcoords="offset points",
            va="center",
        )
        a.annotate(
            "Optimum",
            w_opt,
            xytext=(0, 13),
            textcoords="offset points",
            ha="center",
            va="bottom",
        )
        a.set(
            xlabel="Intercept a (MPa)",
            ylabel="Slope b (MPa per 20 C)",
        )
        # Lower left, where no path runs; a white box hides the contours behind the text.
        a.legend(
            loc="lower left",
            handlelength=1.8,
            borderaxespad=0.3,
            frameon=True,
            facecolor="white",
            edgecolor="none",
            framealpha=0.9,
        )
        save(fig, "opt-paths.png")


# --------------------------------------------------------------------------------------
# Concrete: the measured comparison
# --------------------------------------------------------------------------------------
def engineered(X):
    """log(age) and the water/cement ratio (Abrams 1918) next to the raw columns."""
    X = np.asarray(X, float)
    return np.column_stack([X[:, :7], np.log(X[:, 7]), X[:, 3] / X[:, 0]])


MEAN = "Baseline: predict the mean"
PHYSICS = "Linear, with physics features"     # log(age) and w/c next to the raw columns
SHORT = {                                     # tick labels that fit under their bars at 13 pt
    MEAN: "Baseline:\nthe mean",
    PHYSICS: "Linear with\nphysics",
    "Decision tree": "Decision\ntree",
    "Neural network": "Neural\nnetwork",
    "Gaussian process": "Gaussian\nprocess",
}


def concrete_models():
    return {
        MEAN: DummyRegressor(),
        "Linear": make_pipeline(StandardScaler(), LinearRegression()),
        PHYSICS: make_pipeline(FunctionTransformer(engineered), StandardScaler(), LinearRegression()),
        "Decision tree": DecisionTreeRegressor(random_state=0),
        "Neural network": make_pipeline(StandardScaler(), MLPRegressor(hidden_layer_sizes=(16,), activation="tanh",
                                                                       solver="lbfgs", max_iter=5000, random_state=0)),
        "Gaussian process": make_pipeline(StandardScaler(), GaussianProcessRegressor(
            kernel=ConstantKernel(1.0) * RBF(np.ones(8), (1e-2, 1e3)) + WhiteKernel(1e-1, (1e-5, 1e1)),
            normalize_y=True, random_state=0, n_restarts_optimizer=2)),
    }


def concrete_figures():
    print("\n=== Concrete compressive strength (Yeh 1998) ===")
    df = load_concrete()
    X, y = df[FEATURES].to_numpy(), df.strength_mpa.to_numpy()
    groups = df.groupby(MIX).ngroup().to_numpy()
    sizes = df.groupby(MIX).size()
    multi = sizes[sizes > 1]
    print(f"  {len(df)} rows, {groups.max() + 1} distinct mixes; {len(multi)} mixes tested more than once,"
          f" holding {multi.sum()} rows ({multi.sum() / len(df):.1%}); {df.duplicated().sum()} exact duplicate rows")
    print(f"  strength {y.min():.2f} to {y.max():.2f} MPa, mean {y.mean():.2f}, std {y.std():.2f}")
    same = df.groupby(FEATURES).strength_mpa.agg(["size", "min", "max", "std"])
    rep = same[same["size"] > 1]
    print(f"  {len(rep)} input settings (mix and age) appear more than once; {(rep['max'] > rep['min']).sum()} of them"
          f" with different measured strengths, spread up to {(rep['max'] - rep['min']).max():.2f} MPa;"
          f" pooled within-setting std {np.sqrt((rep['std']**2 * (rep['size'] - 1)).sum() / (rep['size'] - 1).sum()):.2f} MPa")
    by_age = df.groupby("age_days").strength_mpa.mean()
    print("  mean strength by age (days: MPa):", {int(k): round(v, 1) for k, v in by_age.loc[[3, 7, 28, 90, 365]].items()})

    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(X, y, groups))
    Xtr, ytr, gtr, Xte, yte = X[tr], y[tr], groups[tr], X[te], y[te]
    print(f"  test set: {len(te)} rows from {len(set(groups[te]))} mixes; training: {len(tr)} rows, {len(set(gtr))} mixes")

    rows = []
    scoring = {"rmse": "neg_root_mean_squared_error", "mae": "neg_mean_absolute_error", "r2": "r2"}
    for name, m in concrete_models().items():
        for cvname, cv, g in [("KFold", KFold(5, shuffle=True, random_state=0), None),
                              ("GroupKFold", GroupKFold(5), gtr)]:
            r = cross_validate(m, Xtr, ytr, cv=cv, groups=g, scoring=scoring, return_train_score=True)
            rows.append(dict(model=name, cv=cvname, rmse=-r["test_rmse"].mean(), sd=r["test_rmse"].std(),
                             mae=-r["test_mae"].mean(), r2=r["test_r2"].mean(), train_rmse=-r["train_rmse"].mean()))
    res = pd.DataFrame(rows)
    print(res.round(3).to_string(index=False))

    names = list(concrete_models())
    k = res[res.cv == "KFold"].set_index("model").loc[names]
    g = res[res.cv == "GroupKFold"].set_index("model").loc[names]
    with plt.rc_context(fonts(13)):             # shown at w:760
        fig, ax = plt.subplots(figsize=(9, 3.3))
        i = np.arange(len(names))
        ax.bar(
            i - 0.21,
            k.rmse,
            0.42,
            yerr=k.sd,
            color="0.7",
            label="KFold (random rows)",
            capsize=3,
        )
        ax.bar(
            i + 0.21,
            g.rmse,
            0.42,
            yerr=g.sd,
            color=CMU_RED,
            label="GroupKFold (whole mixes)",
            capsize=3,
        )
        for j in i:
            ax.text(
                j - 0.21,
                k.rmse.iloc[j] + k.sd.iloc[j] + 0.3,
                f"{k.rmse.iloc[j]:.1f}",
                ha="center",
                color=MUTED,
            )
            ax.text(
                j + 0.21,
                g.rmse.iloc[j] + g.sd.iloc[j] + 0.3,
                f"{g.rmse.iloc[j]:.1f}",
                ha="center",
                color=CMU_RED,
            )
        ax.set_xticks(i, [SHORT.get(n, n) for n in names])
        ax.tick_params(
            axis="x",
            length=0,
        )
        ax.set(
            ylabel="5-fold CV RMSE (MPa)",
            ylim=(0, 21),
            yticks=[0, 5, 10, 15, 20],
        )
        ax.legend(loc="upper right")
        save(fig, "concrete-cv.png")

    depths = list(range(1, 21))
    trs, vag = validation_curve(DecisionTreeRegressor(random_state=0), Xtr, ytr, param_name="max_depth",
                                param_range=depths, cv=GroupKFold(5), groups=gtr,
                                scoring="neg_root_mean_squared_error")
    _, vak = validation_curve(DecisionTreeRegressor(random_state=0), Xtr, ytr, param_name="max_depth",
                              param_range=depths, cv=KFold(5, shuffle=True, random_state=0),
                              scoring="neg_root_mean_squared_error")
    trs, vag, vak = -trs.mean(1), -vag.mean(1), -vak.mean(1)
    print("  tree depth: train / validation (GroupKFold) / validation (KFold)")
    for d, a_, b_, c_ in zip(depths, trs, vag, vak):
        print(f"    {d:2d}  {a_:6.2f}  {b_:6.2f}  {c_:6.2f}")
    print(f"  best validation (GroupKFold) at depth {depths[int(np.argmin(vag))]}: {vag.min():.2f} MPa")
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(depths, trs, "o-", color=INK, label="Training")
    ax.plot(depths, vak, "s-", color="0.6", label="Validation, KFold (random rows)")
    ax.plot(depths, vag, "s-", color=CMU_RED, label="Validation, GroupKFold (whole mixes)")
    ax.set(xlabel="Tree max_depth (model capacity)", ylabel="RMSE (MPa)", xticks=[1, 5, 10, 15, 20])
    ax.legend(loc="upper right")
    save(fig, "concrete-depth.png")

    sizes_ = np.linspace(0.1, 1.0, 8)
    # "High" needs a reference. Gradient-boosted trees on the same engineered features, scored
    # on the same grouped folds, are a model with more capacity than the line; if they reach a
    # lower validation error, the line's converged error is bias it could lose, not noise.
    # (The replicate scatter is no floor to measure against: the repeated settings come from
    # three mixes, and 25 of the rows are exact copies with no scatter at all.)
    flexible = make_pipeline(
        FunctionTransformer(engineered),
        HistGradientBoostingRegressor(random_state=0),
    )
    ref = cross_validate(
        flexible,
        Xtr,
        ytr,
        cv=GroupKFold(5),
        groups=gtr,
        scoring="neg_root_mean_squared_error",
    )
    ref_rmse = -ref["test_score"]
    line_rmse = -cross_validate(
        concrete_models()[PHYSICS],
        Xtr,
        ytr,
        cv=GroupKFold(5),
        groups=gtr,
        scoring="neg_root_mean_squared_error",
    )["test_score"]
    gp_rmse = -cross_validate(
        concrete_models()["Gaussian process"],
        Xtr,
        ytr,
        cv=GroupKFold(5),
        groups=gtr,
        scoring="neg_root_mean_squared_error",
    )["test_score"]
    print(f"  reference for the learning curve: gradient-boosted trees on the physics features,"
          f" GroupKFold RMSE {ref_rmse.mean():.2f} (fold std {ref_rmse.std():.2f}); the line is worse on"
          f" {(line_rmse > ref_rmse).sum()} of 5 folds, by {(line_rmse - ref_rmse).min():.2f} to"
          f" {(line_rmse - ref_rmse).max():.2f} MPa; the GP is worse on {(gp_rmse > ref_rmse).sum()} of 5,"
          f" by {(gp_rmse - ref_rmse).min():.2f} to {(gp_rmse - ref_rmse).max():.2f} MPa")
    # The panels carry the evidence (the gap and the reference) and the table under the figure
    # on the slide carries the diagnosis. learning_curve does not shuffle by default, so each
    # smaller training set would be the first rows of the fold in file order; on this file that
    # alone put a 3.5 MPa step into the tree's curve. So every curve is the mean over ten random
    # orderings of the training rows. Both readings are checked against the printed curves: the
    # line's two curves close to 0.3 MPa apart and meet above the reference; the tree's gap is
    # 8.5 MPa and its validation RMSE is flat near 9.4 from about 400 samples on.
    # Shown at h:250 on the slide, about 560 px wide.
    panels = [
        (PHYSICS, "Linear, physics features"),
        ("Decision tree", "Tree, no depth limit"),
    ]
    with plt.rc_context(fonts(16)):             # shown at h:250, about 580 px wide
        fig, axes = plt.subplots(
            1,
            2,
            figsize=(8.6, 3.0),
            sharey=True,
            gridspec_kw={"wspace": 0.08},
        )
        for ax, (name, title) in zip(axes, panels):
            runs = [learning_curve(
                concrete_models()[name],
                Xtr,
                ytr,
                train_sizes=sizes_,
                cv=GroupKFold(5),
                groups=gtr,
                scoring="neg_root_mean_squared_error",
                shuffle=True,
                random_state=rs,
            ) for rs in range(10)]
            n = runs[0][0]
            a_ = -np.mean([r[1].mean(1) for r in runs], axis=0)
            b_ = -np.mean([r[2].mean(1) for r in runs], axis=0)
            print(f"  learning curve {name}: n {list(n)}\n    train {a_.round(2)}\n    valid {b_.round(2)}")
            ax.plot(
                n,
                a_,
                "o-",
                color=INK,
                label="Training",
            )
            ax.plot(
                n,
                b_,
                "s-",
                color=CMU_RED,
                label="Validation\n(GroupKFold)",
            )
            # The gap at the largest training set, just right of it: a bracket when it is too
            # small for arrowheads, a double arrow when it is not.
            xg = n[-1] + 38
            gap = b_[-1] - a_[-1]
            ax.annotate(
                "",
                xy=(xg, b_[-1]),
                xytext=(xg, a_[-1]),
                arrowprops={
                    "arrowstyle": "|-|, widthA=0.5, widthB=0.5" if gap < 2 else "<->",
                    "color": MUTED,
                    "lw": 1.6,
                    "shrinkA": 0,
                    "shrinkB": 0,
                },
            )
            ax.text(
                xg - 14,
                b_[-1] + 0.7 if gap < 2 else (a_[-1] + b_[-1]) / 2,
                f"gap {gap:.1f}",
                ha="right",
                va="bottom" if gap < 2 else "center",
                color=MUTED,
                fontsize=16,
            )
            ax.set(
                xlabel="Training samples",
                title=title,
                xlim=(20, n[-1] + 60),
                xticks=[200, 400, 600],
            )
        axes[0].axhline(
            ref_rmse.mean(),
            color=MUTED,
            ls=":",
            lw=1.8,
        )
        axes[0].text(
            n[-1] + 20,
            ref_rmse.mean() - 0.35,
            f"More capacity: {ref_rmse.mean():.1f}",
            ha="right",
            va="top",
            color=MUTED,
            fontsize=16,
        )
        axes[0].set(
            ylabel="RMSE (MPa)",
            ylim=(0, 17),
            yticks=[0, 5, 10, 15],
        )
        axes[0].legend(
            loc="upper right",
            handlelength=1.4,
            borderaxespad=0.2,
        )
        save(fig, "concrete-learning.png")

    gp = concrete_models()["Gaussian process"].fit(Xtr, ytr)
    mu, sd = gp.predict(Xte, return_std=True)
    inside = np.mean(np.abs(yte - mu) < 2 * sd)
    print(f"  TEST ONCE, Gaussian process: RMSE {root_mean_squared_error(yte, mu):.2f}, MAE {mean_absolute_error(yte, mu):.2f},"
          f" R2 {r2_score(yte, mu):.3f}; mean predicted std {sd.mean():.2f} MPa; {inside:.1%} of test points within 2 std")
    print(f"  fitted kernel: {gp[-1].kernel_}")
    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    ax.errorbar(yte, mu, yerr=2 * sd, fmt="o", ms=4, color=BLUE, ecolor="0.75", elinewidth=1, alpha=0.9)
    ax.plot([0, 85], [0, 85], "k--", lw=1)
    ax.set(xlabel="Measured strength (MPa)", ylabel="Predicted strength (MPa)",
           title=f"GP on 86 held-out mixes: RMSE {root_mean_squared_error(yte, mu):.1f} MPa")
    ax.title.set_fontsize(11)
    save(fig, "concrete-parity.png")

    print("  test RMSE across ten different test draws of whole mixes (GP, engineered linear):")
    spread = []
    for s in range(10):
        a_, b_ = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=s).split(X, y, groups))
        e = [root_mean_squared_error(y[b_], concrete_models()[n].fit(X[a_], y[a_]).predict(X[b_]))
             for n in ["Gaussian process", PHYSICS]]
        spread.append(e)
        print(f"    seed {s}: {len(b_)} rows  GP {e[0]:.2f}  linear {e[1]:.2f}")
    spread = np.array(spread)
    print(f"  GP {spread[:, 0].min():.2f} to {spread[:, 0].max():.2f}; linear {spread[:, 1].min():.2f} to {spread[:, 1].max():.2f}")


# --------------------------------------------------------------------------------------
# Schematics and teaching figures (no data beyond what is named)
# --------------------------------------------------------------------------------------
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Patch, Rectangle


def workflow_figure():
    """The four steps of Victor's F25 'ML pipeline', drawn as one schematic."""
    print("\n=== The machine learning workflow, drawn ===")
    fig, ax = plt.subplots(figsize=(13.4, 4.9))
    ax.set_xlim(0, 13.4)
    ax.set_ylim(0, 4.9)
    ax.axis("off")
    steps = [
        (BLUE, "1", "Feature engineering", "Select or transform the\ninputs X: powers, logs, lags"),
        (GREEN, "2", "Data splitting", "Training, validation\nand test sets"),
        (GOLD, "3", "Model selection", "Linear, tree,\nneural network, GP"),
        (CMU_RED, "4", "Model validation", "Score on validation\ndata, compare"),
    ]
    x0, w, gap, y0, h = 0.12, 3.06, 0.3, 1.1, 3.35
    for k, (col, num, title, desc) in enumerate(steps):
        x = x0 + k * (w + gap)
        ax.add_patch(FancyBboxPatch((x, y0), w, h, boxstyle="round,pad=0.02,rounding_size=0.18",
                                    fc="white", ec=col, lw=2.2))
        ax.add_patch(FancyBboxPatch((x, y0 + h - 0.72), w, 0.72, boxstyle="round,pad=0.02,rounding_size=0.18",
                                    fc=col, ec=col, lw=2.2))
        ax.add_patch(Circle(
            (x + 0.34, y0 + h - 0.36),
            0.21,
            fc="white",
            ec="white",
        ))
        ax.text(
            x + 0.34,
            y0 + h - 0.37,
            num,
            ha="center",
            va="center",
            fontsize=13,
            weight="bold",
            color=col,
        )
        ax.text(
            x + 0.62,
            y0 + h - 0.37,
            title,
            ha="left",
            va="center",
            fontsize=11.5,
            weight="bold",
            color="white",
        )
        ax.text(
            x + w / 2,
            y0 + 0.5,
            desc,
            ha="center",
            va="center",
            fontsize=12,
            color=INK,
            linespacing=1.3,
        )
        cx, cy = x + w / 2, y0 + 1.72     # center of the glyph area
        if num == "1":
            # Two examples: powers of one input (the water fit), and lagged columns of a time
            # series (the NARX table), which are feature engineering too.
            # Box widths are set by the 11.5 pt labels, the smallest that land at 16 px.
            rows = [
                (cy + 0.42, 0.64, "$T$", 22, ["$T^3$", "$T^2$", "$T$", "$1$"], [0.34] * 4, 12),
                (cy - 0.52, 0.5, "$y(t)$\n$u(t)$", 11.5, ["$y(t{-}1)$", "$y(t{-}2)$", "$u(t)$"], [0.74, 0.74, 0.5], 11.5),
            ]
            for ry, bh, src, size, cols, widths, fsize in rows:
                ax.text(
                    x + 0.32,
                    ry,
                    src,
                    fontsize=size,
                    ha="center",
                    va="center",
                    color=INK,
                    linespacing=1.15,
                )
                ax.add_patch(FancyArrowPatch(
                    (x + 0.61, ry),
                    (x + 0.85, ry),
                    arrowstyle="-|>",
                    mutation_scale=12,
                    color=MUTED,
                    lw=1.5,
                ))
                bx = x + 0.88
                for lab, bw in zip(cols, widths):
                    ax.add_patch(FancyBboxPatch(
                        (bx, ry - bh / 2),
                        bw,
                        bh,
                        boxstyle="round,pad=0.01,rounding_size=0.05",
                        fc="#e8f0f8",
                        ec=col,
                        lw=1,
                    ))
                    ax.text(
                        bx + bw / 2,
                        ry,
                        lab,
                        fontsize=fsize,
                        ha="center",
                        va="center",
                    )
                    bx += bw + 0.04
        elif num == "2":
            # 56/22/22 rather than 60/20/20, so that "Valid." fits its segment at 11.5 pt.
            parts = [(0.56, "Training", "#cfe6d1"), (0.22, "Valid.", "#f3e3b8"), (0.22, "Test", "#f4c7cf")]
            xx = cx - 1.45
            for frac, lab, fc in parts:
                ax.add_patch(FancyBboxPatch(
                    (xx, cy - 0.3),
                    2.9 * frac - 0.04,
                    0.6,
                    boxstyle="round,pad=0.0,rounding_size=0.06",
                    fc=fc,
                    ec="white",
                ))
                ax.text(
                    xx + (2.9 * frac - 0.04) / 2,
                    cy,
                    lab,
                    fontsize=11.5,
                    ha="center",
                    va="center",
                )
                xx += 2.9 * frac
            ax.text(
                cx + 1.41,
                cy - 0.58,
                "Used once",
                fontsize=11.5,
                ha="right",
                color=CMU_RED,
                style="italic",
            )
        elif num == "3":
            xs = np.linspace(0, 1, 30)
            for j, kind in enumerate(["line", "tree", "nn", "gp"]):
                gx, gy = cx - 1.1 + j * 0.57, cy - 0.3
                ax.add_patch(FancyBboxPatch((gx, gy), 0.5, 0.6, boxstyle="round,pad=0.0,rounding_size=0.05",
                                            fc="#fbf4e3", ec=col, lw=1))
                if kind == "line":
                    ax.plot(gx + 0.05 + 0.4 * xs, gy + 0.1 + 0.4 * xs, color=INK, lw=1.3)
                elif kind == "tree":
                    ax.step(gx + 0.05 + 0.4 * xs, gy + 0.1 + 0.4 * np.floor(xs * 4) / 3, color=INK, lw=1.3)
                elif kind == "nn":
                    for a in (0.15, 0.3, 0.45):
                        ax.plot([gx + 0.1, gx + 0.25], [gy + 0.3, gy + a], color=INK, lw=0.8)
                        ax.plot([gx + 0.25, gx + 0.4], [gy + a, gy + 0.3], color=INK, lw=0.8)
                        ax.add_patch(Circle((gx + 0.25, gy + a), 0.035, fc=INK))
                    ax.add_patch(Circle((gx + 0.1, gy + 0.3), 0.035, fc=INK))
                    ax.add_patch(Circle((gx + 0.4, gy + 0.3), 0.035, fc=INK))
                else:
                    m = gy + 0.3 + 0.12 * np.sin(6 * xs)
                    ax.fill_between(gx + 0.05 + 0.4 * xs, m - 0.1 - 0.05 * xs, m + 0.1 + 0.05 * xs,
                                    color=BLUE, alpha=0.25, lw=0)
                    ax.plot(gx + 0.05 + 0.4 * xs, m, color=INK, lw=1.2)
        else:
            vals = [0.9, 0.55, 0.7, 0.45]
            for j, v in enumerate(vals):
                ax.add_patch(FancyBboxPatch((cx - 0.95 + j * 0.5, cy - 0.45), 0.34, 0.9 * v,
                                            boxstyle="round,pad=0.0,rounding_size=0.03",
                                            fc=CMU_RED if j == 3 else "#e6b3bb", ec="none"))
            ax.text(
                cx + 1.0,
                cy + 0.4,
                "Lowest\nerror",
                fontsize=11.5,
                ha="center",
                va="center",
                color=CMU_RED,
                style="italic",
            )
            ax.text(
                cx - 0.2,
                cy - 0.68,
                "RMSE on validation",
                fontsize=11.5,
                ha="center",
                color=MUTED,
            )
        if k < 3:
            ax.add_patch(FancyArrowPatch((x + w + 0.03, y0 + h / 2), (x + w + gap - 0.03, y0 + h / 2),
                                         arrowstyle="-|>", mutation_scale=22, color=MUTED, lw=2))
    # the loop back, and the test set used once
    x4 = x0 + 3 * (w + gap)
    ax.add_patch(FancyArrowPatch((x4 + w / 2, y0 - 0.05), (x0 + 2 * (w + gap) + w / 2, y0 - 0.05),
                                 connectionstyle="arc3,rad=-0.3", arrowstyle="-|>", mutation_scale=18,
                                 color=GOLD, lw=1.8))
    x3c = x0 + 2 * (w + gap) + w / 2
    ax.text(
        x3c - 0.35,
        0.22,
        "Iterate on the validation data",
        fontsize=12,
        ha="center",
        color=GOLD,
        style="italic",
    )
    ax.add_patch(FancyBboxPatch((x4 + 0.7, 0.08), w - 0.75, 0.55, boxstyle="round,pad=0.02,rounding_size=0.25",
                                fc=CMU_RED, ec=CMU_RED))
    ax.text(
        x4 + 0.7 + (w - 0.75) / 2,
        0.355,
        "Then: test once",
        fontsize=12,
        ha="center",
        va="center",
        color="white",
        weight="bold",
    )
    ax.text(
        x0 + 0.05,
        0.72,
        "Transforms fitted to data, such as scaling, are fitted on the training rows only",
        fontsize=11.5,
        ha="left",
        va="center",
        color=MUTED,
    )
    save(fig, "ml-workflow.png")


def nn_diagram():
    """The three-unit network from the F25 lecture, redrawn, next to a deep one."""
    print("\n=== The three-unit network, and a deep one, drawn ===")
    fig, (ax, deep) = plt.subplots(
        1,
        2,
        figsize=(13.5, 4.8),
        gridspec_kw={"width_ratios": [1.45, 1], "wspace": 0.06},
    )
    for a in (ax, deep):
        a.set_aspect("equal")
        a.axis("off")
        a.set_ylim(-1.2, 5.1)
    fills = {"in": ("#dce8f5", BLUE), "hidden": ("#e6f2e6", GREEN), "out": ("#f7dde1", CMU_RED)}

    def node(a, x, y, r, kind, lw):
        a.add_patch(Circle(
            (x, y),
            r,
            fc=fills[kind][0],
            ec=fills[kind][1],
            lw=lw,
            zorder=2,
        ))

    def label(x, y, text, size, color=INK, va="center"):
        ax.text(
            x,
            y,
            text,
            fontsize=size,
            ha="center",
            va=va,
            color=color,
            zorder=3,
        )

    # Left: one input, three tanh units, one linear output, every weight and bias named.
    # Each hidden unit, and the connection that carries its term to the output, has the color
    # its term has in nn-terms.png.
    ax.set_xlim(0.2, 10.2)
    r = 0.45
    xin, xh, xout = 1.0, 5.0, 9.0
    hy = [3.8, 2.1, 0.4]
    yin = yout = 2.1
    for k, y in enumerate(hy):
        for (xa, ya, xb, yb, lab, col, lw) in [(xin, yin, xh, y, f"$w_{{0{k}}}$", "0.6", 1.6),
                                               (xh, y, xout, yout, f"$w_{{1{k}}}$", UNIT_COLORS[k], 2.4)]:
            ax.plot(
                [xa + r, xb - r],
                [ya, yb],
                color=col,
                lw=lw,
                zorder=1,
            )
            label((xa + xb) / 2, (ya + yb) / 2 + 0.12, lab, 13, va="bottom")
    node(ax, xin, yin, r, "in", 2.2)
    label(xin, yin, "$x$", 20)
    s_ = np.linspace(-1, 1, 40)
    for k, y in enumerate(hy):
        ax.add_patch(Circle(
            (xh, y),
            r,
            fc=UNIT_FILLS[k],
            ec=UNIT_COLORS[k],
            lw=2.2,
            zorder=2,
        ))
        ax.plot(
            xh + 0.3 * s_,
            y + 0.22 * np.tanh(3 * s_),
            color=UNIT_COLORS[k],
            lw=2,
            zorder=3,
        )
        # The bias sits directly under its node, where no connection runs.
        label(
            xh,
            y - r - 0.06,
            f"$+b_{{0{k}}}$",
            12,
            color=MUTED,
            va="top",
        )
    node(ax, xout, yout, r, "out", 2.2)
    label(xout, yout, "$y$", 20)
    label(
        xout,
        yout - r - 0.06,
        "$+b_1$",
        12,
        color=MUTED,
        va="top",
    )
    for xx, lab, col in [(xin, "Input layer", BLUE), (xh, "Hidden layer\n(tanh)", GREEN),
                         (xout, "Output layer\n(linear)", CMU_RED)]:
        ax.text(
            xx,
            5.05,
            lab,
            fontsize=12.5,
            ha="center",
            va="top",
            color=col,
            weight="bold",
            linespacing=1.2,
        )

    # Right: the same parts stacked deeper, with nothing named.
    sizes = [3, 5, 5, 5, 1]
    kinds = ["in", "hidden", "hidden", "hidden", "out"]
    xs = np.arange(len(sizes)) * 1.4
    rd, dy = 0.28, 0.9
    layers = [2.1 + dy * (np.arange(n) - (n - 1) / 2) for n in sizes]
    # 6.9 units wide against the left panel's 10, the ratio of the two panel widths, so the
    # two panels share one scale and their captions line up.
    deep.set_xlim(xs[0] - 0.65, xs[-1] + 0.65)
    for j in range(len(sizes) - 1):
        for ya in layers[j]:
            for yb in layers[j + 1]:
                deep.plot(
                    [xs[j], xs[j + 1]],
                    [ya, yb],
                    color="0.72",
                    lw=0.7,
                    zorder=1,
                )
    for x, ys, kind in zip(xs, layers, kinds):
        for y in ys:
            node(deep, x, y, rd, kind, 1.8)

    for a, caption in [(ax, "One hidden layer, 3 tanh units"), (deep, "Deep: several hidden layers")]:
        a.text(
            sum(a.get_xlim()) / 2,
            -0.9,
            caption,
            fontsize=13.5,
            ha="center",
            va="center",
            color=INK,
        )
    save(fig, "nn-diagram.png")


NODE_STYLE = {"in": ("#dce8f5", BLUE), "hidden": ("#e6f2e6", GREEN), "out": ("#f7dde1", CMU_RED)}


def draw_network(ax, sizes, x0, dx, dy, r, yc=0.0):
    """Nodes and connections of a fully connected network, input left, in nn-diagram's colors."""
    kinds = ["in"] + ["hidden"] * (len(sizes) - 2) + ["out"]
    xs = x0 + dx * np.arange(len(sizes))
    layers = [yc + dy * (np.arange(n) - (n - 1) / 2) for n in sizes]
    for j in range(len(sizes) - 1):
        for ya in layers[j]:
            for yb in layers[j + 1]:
                ax.plot(
                    [xs[j], xs[j + 1]],
                    [ya, yb],
                    color="0.72",
                    lw=0.8,
                    zorder=1,
                )
    for x, ys, kind in zip(xs, layers, kinds):
        for y in ys:
            ax.add_patch(Circle(
                (x, y),
                r,
                fc=NODE_STYLE[kind][0],
                ec=NODE_STYLE[kind][1],
                lw=1.6,
                zorder=2,
            ))
    return xs


def nn_hyperparameters_figure():
    """The choices MLPRegressor leaves open: the activation, and the layers and their units."""
    print("\n=== Neural network hyperparameters, drawn ===")
    z = np.linspace(-3, 3, 400)
    with plt.rc_context(fonts(14)):             # shown at w:1080 (w:1000 in an earlier layout)
        fig, (a, b) = plt.subplots(
            1,
            2,
            figsize=(11.2, 3.4),
            gridspec_kw={"width_ratios": [1, 1.7], "wspace": 0.1},
        )
        for curve, col, lab in [(np.tanh(z), BLUE, "Tanh"),
                                (1 / (1 + np.exp(-z)), GOLD, "Logistic sigmoid"),
                                (np.maximum(z, 0), CMU_RED, "ReLU")]:
            a.plot(
                z,
                curve,
                color=col,
                lw=2.4,
                label=lab,
            )
        a.axhline(
            0,
            color="0.85",
            lw=0.8,
            zorder=0,
        )
        a.set(
            xlabel="z",
            ylabel="Activation",
            xlim=(-3, 3),
            ylim=(-1.25, 3.1),
            xticks=[-3, 0, 3],
            yticks=[-1, 0, 1, 2, 3],
            title="Activation functions",
        )
        a.legend(
            loc="upper left",
            handlelength=1.5,
        )
        # The right panel is drawn in inches: its data limits are its own size, so circles
        # stay round and the captions can be spaced by their printed width.
        b.axis("off")
        box = b.get_position()
        wb, hb = box.width * fig.get_figwidth(), box.height * fig.get_figheight()
        b.set_xlim(0, wb)
        b.set_ylim(0, hb)
        nets = [
            ([1, 3, 1], "1 hidden layer,\n3 units", 0.13),
            ([1, 8, 1], "1 hidden layer,\n8 units", 0.45),
            ([1, 5, 5, 5, 1], "3 hidden layers,\n5 units each", 0.8),
        ]
        dx, dy, r = 0.42, 0.25, 0.085
        yc = hb - 0.15 - 3.5 * dy - r                 # the 8-unit column's top just under the title
        for sizes, caption, center in nets:
            xs = draw_network(b, sizes, center * wb - dx * (len(sizes) - 1) / 2, dx, dy, r, yc)
            b.text(
                xs.mean(),
                yc - 3.5 * dy - r - 0.12,
                caption,
                ha="center",
                va="top",
                color=INK,
                linespacing=1.2,
            )
        b.set_title("Hidden layers and units")
        save(fig, "nn-hyperparameters.png")


def gp_likelihood_figure():
    """What GP training minimizes, on the surfactant data: misfit plus complexity, against ell.

    A slide widget reuses these numbers, so the recipe is fixed: x is log concentration in
    raw units, yc is log viscosity minus its mean, sf2 and sn2 come from one sklearn fit and
    are then held fixed while the length scale ell is swept.
    """
    print("\n=== GP training on the surfactant data: misfit against complexity, as ell varies ===")
    df = load_logzsv()
    x = df["log-conc"].to_numpy()
    y = df["log-zsv"].to_numpy()
    yc = y - y.mean()
    sx = x.std()                                  # population std, as StandardScaler uses
    kernel = (ConstantKernel(1.0, (1e-3, 1e3)) * RBF(1.0, (1e-3, 1e3))
              + WhiteKernel(1e-2, (1e-6, 1e1)))
    gp = GaussianProcessRegressor(
        kernel=kernel,
        n_restarts_optimizer=10,
        random_state=0,
    ).fit(((x - x.mean()) / sx)[:, None], yc)
    sf2 = gp.kernel_.k1.k1.constant_value
    ell_std = gp.kernel_.k1.k2.length_scale
    sn2 = gp.kernel_.k2.noise_level
    print(f"  sklearn fit on standardized x: {gp.kernel_}")
    print(f"  sf2 {sf2:.4f}, sn2 {sn2:.6f}, length scale {ell_std:.4f} standardized"
          f" = {ell_std * sx:.4f} in log concentration (std of x {sx:.4f})")

    def gram(a, b, ell):
        return sf2 * np.exp(-(a[:, None] - b[None, :]) ** 2 / (2 * ell**2))

    def terms(ell):
        L = np.linalg.cholesky(gram(x, x, ell) + sn2 * np.eye(x.size))
        alpha = np.linalg.solve(L.T, np.linalg.solve(L, yc))
        return 0.5 * yc @ alpha, np.sum(np.log(np.diag(L)))

    ells = np.logspace(np.log10(0.02), np.log10(3), 400)
    misfit, cplx = np.array([terms(e) for e in ells]).T
    total = misfit + cplx
    best = ells[np.argmin(total)]
    print(f"  sweep of ell from {ells[0]:g} to {ells[-1]:g} (400 log-spaced values): best ell {best:.4f};"
          f" objective {total.min():.3f} (plus N/2 log 2 pi = {x.size / 2 * np.log(2 * np.pi):.3f}"
          f" gives -log marginal likelihood {total.min() + x.size / 2 * np.log(2 * np.pi):.3f};"
          f" sklearn's fit {-gp.log_marginal_likelihood_value_:.3f})")
    chosen = [(0.05, GOLD, "Short"), (best, CMU_RED, "Best"), (1.5, BLUE, "Long")]
    for ell, _, lab in chosen:
        m_, c_ = terms(ell)
        print(f"    {lab:5s} ell {ell:.4f}: misfit {m_:9.3f}  complexity {c_:8.3f}  sum {m_ + c_:9.3f}")

    fig, (a, b) = plt.subplots(
        1,
        2,
        figsize=(12, 4.2),
        gridspec_kw={"width_ratios": [1, 1.05]},
    )
    xx = np.linspace(x.min() - 0.15, x.max() + 0.15, 500)
    for ell, col, lab in chosen:
        K = gram(x, x, ell) + sn2 * np.eye(x.size)
        ks = gram(xx, x, ell)
        mu = y.mean() + ks @ np.linalg.solve(K, yc)
        if lab == "Best":
            var = sf2 - np.sum(ks * np.linalg.solve(K, ks.T).T, axis=1)
            sd = np.sqrt(np.maximum(var, 0))
            a.fill_between(
                xx,
                mu - 2 * sd,
                mu + 2 * sd,
                color=col,
                alpha=0.13,
                lw=0,
            )
        a.plot(
            xx,
            mu,
            color=col,
            lw=2 if lab == "Best" else 1.5,
            label=f"{lab}: $\\ell$ = {ell:.2f}",
        )
    a.scatter(
        x,
        y,
        color=INK,
        s=22,
        zorder=4,
        label="Data",
    )
    a.set(
        xlabel="Log concentration",
        ylabel="Log zero-shear viscosity",
        title="The GP mean at three length scales",
    )
    a.legend(
        loc="upper right",
        fontsize=10,
    )

    for curve, col, width, lab in [
        (misfit, BLUE, 2, "Misfit: how poorly this\nkernel explains the data"),
        (cplx, GOLD, 2, "Complexity penalty"),
        (total, INK, 2.4, "Sum: what training minimizes"),
    ]:
        b.plot(
            ells,
            curve,
            color=col,
            lw=width,
            label=lab,
        )
    top = 40
    for ell, col, lab in chosen:
        m_, c_ = terms(ell)
        if m_ + c_ < top:
            b.plot(
                ell,
                m_ + c_,
                "o",
                color=col,
                ms=8,
                zorder=5,
                markeredgecolor="white",
            )
        else:                                     # the long length scale is far off the top
            b.plot(
                ell,
                top,
                "^",
                color=col,
                ms=9,
                zorder=5,
                clip_on=False,
            )
            b.annotate(
                f"{lab}, $\\ell$ = {ell:.1f}:\nsum {m_ + c_:,.0f},\noff the scale",
                (ell, top),
                xytext=(0, -12),
                textcoords="offset points",
                ha="center",
                va="top",
                fontsize=10.5,
                color=col,
            )
    b.annotate(
        f"Best $\\ell$ = {best:.2f}",
        (best, total.min()),
        xytext=(0.75, 3),
        textcoords="data",
        ha="left",
        va="center",
        fontsize=11,
        color=CMU_RED,
        arrowprops={
            "arrowstyle": "-",
            "color": CMU_RED,
            "lw": 1,
            "shrinkA": 2,
            "shrinkB": 5,
        },
    )
    b.set(
        xscale="log",
        ylim=(cplx.min() - 4, top),
        xlabel="Length scale $\\ell$ (log concentration)",
        ylabel="Objective term",
        title="Misfit, complexity and their sum",
    )
    b.axhline(
        0,
        color="0.85",
        lw=0.8,
        zorder=0,
    )
    b.legend(
        loc="lower left",
        fontsize=10,
    )
    save(fig, "gp-likelihood.png")


def example_mixes(df):
    """Three real mixes tested at several ages, for concrete-data.png and card-concrete.png.

    Chosen for spread, one per testing schedule, so that no two legend entries read alike: the
    strongest mix tested at 3, 7, 28, 56 and 91 days (it holds the data's highest strength),
    the first mix in the file followed from 7 days to a year, and the weakest mix tested at
    3, 7, 28 and 90 days. Returns (rows, color) pairs, strongest first.
    """
    mixes = [g.sort_values("age_days") for _, g in df.groupby(MIX, sort=False)]
    by_ages = {}
    for g in mixes:
        by_ages.setdefault(tuple(g.age_days), []).append(g)
    strong = max(by_ages[(3, 7, 28, 56, 91)], key=lambda g: g.strength_mpa.iloc[-1])
    year = by_ages[(7, 28, 90, 180, 270, 365)][0]
    weak = min(by_ages[(3, 7, 28, 90)], key=lambda g: g.strength_mpa.iloc[-1])
    return [(strong, CMU_RED), (year, BLUE), (weak, GREEN)]


def tested_at(ages):
    """'3, 7, 28 and 90' from the ages of one mix."""
    ages = [str(int(a)) for a in ages]
    return ", ".join(ages[:-1]) + " and " + ages[-1]


def concrete_data_figure():
    """Introduce the concrete data: every test as a gray dot, and three mixes followed."""
    print("\n=== The concrete data, drawn ===")
    df = load_concrete()
    ages = [1, 3, 7, 28, 90, 365]
    chosen = example_mixes(df)
    print("  three example mixes (kg/m3: cement, slag, fly ash, water, superplasticizer, coarse, fine):")
    for g, _ in chosen:
        mix = g[MIX].iloc[0]
        print(f"    {', '.join(f'{v:g}' for v in mix)}; w/c {mix.water / mix.cement:.2f};"
              f" tested at {tested_at(g.age_days)} days: {', '.join(f'{v:.1f}' for v in g.strength_mpa)} MPa")
    with plt.rc_context(fonts(14)):             # shown at w:560, and at w:540 later
        fig, ax = plt.subplots(figsize=(6.2, 3.0))
        ax.scatter(
            df.age_days,
            df.strength_mpa,
            s=12,
            color="0.8",
            linewidths=0,
            zorder=1,
        )
        for g, col in chosen:
            ax.plot(
                g.age_days,
                g.strength_mpa,
                "o-",
                color=col,
                lw=2,
                ms=6,
                zorder=3,
                label=f"One mix, tested at {tested_at(g.age_days)} days",
            )
        ax.set(
            xscale="log",
            xlabel="Age (days)",
            ylabel="Strength (MPa)",
            xticks=ages,
            xticklabels=ages,
            yticks=[0, 40, 80],
        )
        ax.minorticks_off()
        ax.set_title("Each dot is one specimen; a line follows one mix")
        ax.legend(
            loc="upper center",
            bbox_to_anchor=(0.45, -0.25),
            handlelength=1.6,
            borderaxespad=0,
        )
        save(fig, "concrete-data.png")


# --------------------------------------------------------------------------------------
# NARX with a network and a GP, on Lecture 8's forecasting table
# --------------------------------------------------------------------------------------
XMV = [f"xmv_{i}" for i in range(1, 12)]
LAGS, H = 10, 10          # Lecture 8: ten lags of pressure, 30 minutes ahead


def narx_table(runs, rs):
    """Rows [y[t], ..., y[t-9], u[t]] and target y[t+10], built inside each run."""
    A, b, last = [], [], []
    for r in rs:
        y = runs[r]["xmeas_7"].to_numpy()
        U = runs[r][XMV].to_numpy()
        idx = np.arange(LAGS - 1, len(y) - H)
        A.append(np.column_stack([y[idx - k] for k in range(LAGS)] + [U[idx, j] for j in range(11)]))
        b.append(y[idx + H])
        last.append(y[idx])
    return np.vstack(A), np.concatenate(b), np.concatenate(last)


def narx_gp():
    return make_pipeline(StandardScaler(), GaussianProcessRegressor(
        kernel=ConstantKernel(1.0) * RBF(np.ones(21), (1e-2, 1e3)) + WhiteKernel(1e-1, (1e-5, 1e1)),
        normalize_y=True, random_state=0, n_restarts_optimizer=0))


def narx_schematic():
    """One row of Lecture 8's direct NARX table, drawn on the first test run."""
    print("\n=== One NARX row, drawn on fault-free test run 401 ===")
    ff, _ = load_tep()
    run = ff[ff.simulationRun == 401].sort_values("sample")
    hours, p = tep_trace(run)
    t = 30                                    # the sample the row is built at: 1.5 hours
    k = int(np.nonzero(run["sample"].to_numpy() == t)[0][0])
    inputs = slice(k - LAGS + 1, k + 1)       # y[t-9], ..., y[t], as narx_table() builds them
    target = k + H                            # y[t+10], 30 minutes later
    print(f"  t = sample {t} ({hours[k]:.2f} h); inputs samples {t - LAGS + 1} to {t},"
          f" pressures {p[inputs].min():.1f} to {p[inputs].max():.1f} kPa, y(t) {p[k]:.1f} kPa;"
          f" target sample {t + H} ({hours[target]:.2f} h), {p[target]:.1f} kPa"
          f" ({p[target] - p[k]:+.1f} kPa from y(t))")
    show = hours <= 3
    dt = 3 / 60                               # hours per sample
    with plt.rc_context(fonts(14)):             # shown at w:1080 (w:880 in an earlier layout)
        fig, ax = plt.subplots(figsize=(9.6, 3.2))
        ax.axvspan(
            hours[inputs][0] - dt / 2,
            hours[k] + dt / 2,
            color=BLUE,
            alpha=0.12,
            lw=0,
        )
        ax.plot(
            hours[show],
            p[show],
            "o-",
            color="0.65",
            lw=1,
            ms=3.5,
            zorder=1,
        )
        ax.plot(
            hours[inputs],
            p[inputs],
            "o",
            color=BLUE,
            ms=7,
            zorder=3,
        )
        ax.plot(
            hours[target],
            p[target],
            "o",
            color=CMU_RED,
            ms=10,
            zorder=3,
        )
        ax.axvline(
            hours[k],
            color=INK,
            ls=":",
            lw=1.2,
            zorder=2,
        )
        lo, hi = p[show].min(), p[show].max()
        top = hi + 0.55 * (hi - lo)
        ax.text(
            hours[k] - 0.02,
            lo - 0.12 * (hi - lo),
            "t",
            ha="right",
            va="center",
            color=INK,
        )
        # The horizon, from t to the target, under the trace, labeled at its end.
        ax.annotate(
            "",
            (hours[target], lo - 0.12 * (hi - lo)),
            xytext=(hours[k], lo - 0.12 * (hi - lo)),
            arrowprops={
                "arrowstyle": "->",
                "color": MUTED,
                "lw": 1.2,
                "shrinkA": 0,
                "shrinkB": 0,
            },
        )
        ax.text(
            hours[target] + 0.04,
            lo - 0.12 * (hi - lo),
            "30 min ahead",
            ha="left",
            va="center",
            color=MUTED,
        )
        ax.annotate(
            "Inputs: the last 10 pressures (30 min)\nand the 11 valve positions at t",
            (hours[inputs].mean(), p[inputs].max() + 0.4),
            xytext=(hours[inputs][0] - 0.95, top - 0.05 * (hi - lo)),
            textcoords="data",
            ha="left",
            va="top",
            color=BLUE,
            linespacing=1.25,
            arrowprops={
                "arrowstyle": "-",
                "color": BLUE,
                "lw": 1,
                "shrinkA": 2,
                "shrinkB": 4,
            },
        )
        ax.annotate(
            "Target: the pressure\n30 min later",
            (hours[target], p[target]),
            xytext=(hours[target] + 0.1, top - 0.05 * (hi - lo)),
            textcoords="data",
            ha="left",
            va="top",
            color=CMU_RED,
            linespacing=1.25,
            arrowprops={
                "arrowstyle": "-",
                "color": CMU_RED,
                "lw": 1,
                "shrinkA": 2,
                "shrinkB": 6,
            },
        )
        ax.set(
            xlabel="Time (hours)",
            ylabel="Reactor pressure (kPa)",
            xlim=(0, 3),
            ylim=(lo - 0.24 * (hi - lo), top),
            xticks=[0, 1, 2, 3],
        )
        ax.yaxis.set_major_locator(MaxNLocator(3))
        save(fig, "narx-schematic.png")


def narx_figures():
    print("\n=== NARX on reactor pressure, 30 minutes ahead (Lecture 8's table) ===")
    ff, _ = load_tep()
    runs = {r: g.sort_values("sample") for r, g in ff.groupby("simulationRun")}
    A, b, _ = narx_table(runs, range(1, 301))
    At, bt, lt = narx_table(runs, range(401, 501))
    print(f"  training rows {len(b)} (runs 1-300), test rows {len(bt)} (runs 401-500)")
    print(f"  pressure: mean {b.mean():.1f} kPa, standard deviation {b.std():.2f} kPa")
    print(f"  persistence {root_mean_squared_error(bt, lt):.2f}, Baseline: predict the mean {root_mean_squared_error(bt, np.full_like(bt, b.mean())):.2f}")
    arx = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(A, b)
    print(f"  ARX (ridge): {root_mean_squared_error(bt, arx.predict(At)):.2f} kPa")
    mlp = lambda: make_pipeline(StandardScaler(), MLPRegressor(hidden_layer_sizes=(32,), activation="tanh",
                                                               solver="adam", max_iter=500, early_stopping=True,
                                                               random_state=0))
    for scaled in (False, True):
        t0 = time.time()
        m = TransformedTargetRegressor(regressor=mlp(), transformer=StandardScaler()) if scaled else mlp()
        m.fit(A, b)
        print(f"  NN-NARX (32 tanh, Adam), target scaled={scaled}: {root_mean_squared_error(bt, m.predict(At)):.2f} kPa"
              f" ({time.time() - t0:.0f} s on all rows)")
        if scaled:
            nn = m
    rng = np.random.default_rng(0)
    for n in (1000, 4000):
        i = rng.choice(len(b), n, replace=False)
        t0 = time.time()
        gp = narx_gp().fit(A[i], b[i])
        mu, sd = gp.predict(At, return_std=True)
        dt = time.time() - t0
        same = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(A[i], b[i])
        print(f"  GP-NARX on {n} training rows: {root_mean_squared_error(bt, mu):.2f} kPa, {np.mean(np.abs(bt - mu) < 2 * sd):.1%}"
              f" within 2 std, {dt:.0f} s; ARX on the same rows {root_mean_squared_error(bt, same.predict(At)):.2f}")
        if n == 1000:
            gp1000 = gp
    print(f"  a GP on all {len(b)} rows: a {len(b)} x {len(b)} kernel matrix, {len(b) ** 2 * 8 / 1e9:.0f} GB in double precision")

    r = 401
    Ar, br, _ = narx_table(runs, [r])
    hours = (np.arange(len(br)) + LAGS - 1 + H) * 3 / 60
    mu, sd = gp1000.predict(Ar, return_std=True)
    with plt.rc_context(fonts(13)):             # shown at w:1000
        fig, ax = plt.subplots(figsize=(11, 3.9))
        ax.fill_between(
            hours,
            mu - 2 * sd,
            mu + 2 * sd,
            color=BLUE,
            alpha=0.18,
            label="GP-NARX, mean +/- 2 std",
        )
        ax.plot(
            hours,
            br,
            color=INK,
            lw=1.3,
            label="Measured",
        )
        ax.plot(
            hours,
            arx.predict(Ar),
            color=CMU_RED,
            lw=1.0,
            ls="--",
            label="ARX (ridge)",
        )
        ax.plot(
            hours,
            nn.predict(Ar),
            color=GOLD,
            lw=1.0,
            label="NN-NARX",
        )
        ax.plot(
            hours,
            mu,
            color=BLUE,
            lw=1.0,
            label="GP-NARX mean",
        )
        ax.set(
            xlabel="Hours into test run 401",
            ylabel="Reactor pressure (kPa)",
            title="Forecasts made 30 minutes ahead, on a run none of the models saw",
        )
        lo, hi = ax.get_ylim()
        ax.set_ylim(lo, hi + 0.34 * (hi - lo))    # headroom, so the legend sits above the band
        ax.legend(
            ncol=3,
            loc="upper left",
            handlelength=1.6,
            columnspacing=1.4,
            borderaxespad=0.2,
        )
        save(fig, "narx-forecast.png")


# --------------------------------------------------------------------------------------
# The numbers the two interactive slides embed. The deck's "why neural" and "length scale"
# slides compute everything in the browser from these constants, so they are printed here
# rather than typed by hand.
RELU_SEED = 970  # no seed in 0..2999 puts all five kinks inside (0, 1); at most four do,
                 # in seeds 91, 970, 1551, 1686, 2503 and 2718, and 970 has the best test R2


def widget_numbers():
    print("\n=== Slide widget: five ReLU units on y = x^(1/3) + noise ===")
    rng = np.random.default_rng(0)
    X = np.linspace(0, 1, 120).reshape(-1, 1)
    y = X**(1 / 3) + rng.normal(0, 0.03, size=X.shape)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)
    m = MLPRegressor(
        hidden_layer_sizes=(5,),
        activation="relu",
        solver="lbfgs",
        max_iter=5000,
        alpha=0.0,
        random_state=RELU_SEED,
    ).fit(Xtr, ytr.ravel())
    w1, b1 = m.coefs_[0][0], m.intercepts_[0]
    w2, b2 = m.coefs_[1][:, 0], m.intercepts_[1][0]
    print(f"  seed {RELU_SEED}, test R2 {r2_score(yte, m.predict(Xte)):.4f}")
    print(f"  W1 {np.round(w1, 6).tolist()}")
    print(f"  B1 {np.round(b1, 6).tolist()}")
    print(f"  W2 {np.round(w2, 6).tolist()}")
    print(f"  B2 {round(float(b2), 6)}")
    print(f"  kinks -b1/w1 {np.round(-b1 / w1, 5).tolist()}")
    order = np.argsort(Xtr[:, 0])
    print("  PTS " + str([[round(float(a), 4), round(float(b), 4)]
                          for a, b in zip(Xtr[order, 0], ytr[order, 0])]))

    print("\n=== Slide widget: GP length scale on the surfactant data ===")
    df = load_logzsv()
    x, yv = df["log-conc"].to_numpy(), df["log-zsv"].to_numpy()
    yc = yv - yv.mean()
    z = ((x - x.mean()) / x.std()).reshape(-1, 1)
    g = GaussianProcessRegressor(
        kernel=ConstantKernel(1.0, (1e-3, 1e3)) * RBF(1.0, (1e-3, 1e3)) + WhiteKernel(1e-2, (1e-6, 1e1)),
        n_restarts_optimizer=10,
        random_state=0,
    ).fit(z, yc)
    k = g.kernel_
    print(f"  SF2 {k.k1.k1.constant_value:.6f}, SN2 {k.k2.noise_level:.6f}, mean log-zsv {yv.mean():.6f}")
    print(f"  fitted length scale {k.k1.k2.length_scale * x.std():.4f} (log concentration)")
    print("  DATA " + str([[round(float(a), 6), round(float(b), 6)] for a, b in zip(x, yv)]))


if __name__ == "__main__":
    import sys

    # `python make_figures.py water concrete` regenerates only those groups.
    groups = {"examples", "schematics", "water", "optim", "nn", "gp", "cv", "concrete", "narx", "widgets"}
    want = set(sys.argv[1:]) or groups
    unknown = want - groups
    if unknown:
        sys.exit(f"unknown group(s) {sorted(unknown)}; the groups are {sorted(groups)}")
    if "examples" in want:
        example_figures()
    if "schematics" in want:
        workflow_figure()
        nn_diagram()
        nn_hyperparameters_figure()
        gp_likelihood_figure()
    if "water" in want:
        T, P = water_figures()
        extrapolation_figure(T, P)
    if "optim" in want:
        optimizer_figure()
    if "nn" in want:
        nn_figures()
    if "gp" in want:
        gp_figure()
        gp_intro_figures()
    if "cv" in want:
        cv_picture()
        concrete_grouping_figure()
    if "concrete" in want:
        concrete_data_figure()
        concrete_figures()
    if "narx" in want:
        narx_schematic()
        narx_figures()
    if "widgets" in want:
        widget_numbers()
