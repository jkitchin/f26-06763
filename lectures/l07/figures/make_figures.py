#!/usr/bin/env python3
"""Generate the L7 figures.

Run with:
    uv run --with pandas --with numpy --with matplotlib --with pyarrow python make_figures.py

Every number in the notes and the deck comes from this script or from the demo
notebook. Nothing is asserted.

ONE UNIT, TWO RECORDS
---------------------
The whole session runs on a single loop: the A and C feed of the Tennessee Eastman
plant, `xmv_4` (the valve) against `xmeas_4` (the flow). An earlier draft opened on
daily beer sales in Sao Paulo and then moved to a stirred tank, so the room met three
datasets before the first fit. It now meets one.

That loop has two records, and the difference between them is the session:

  * the record we make. The same loop, open loop, ramped and not waited on. This is
    the experiment operations will not let you run on a live unit, so we simulate it
    at the parameters measured FROM the archive (tau = 10.6 min, K = 0.130) at the
    archive's own operating point (valve 57.6 %, flow 8.79). Same loop, same units.
  * the record we have. The archive itself, 3-minute samples, under automatic control.

Two findings shaped this and are worth recording, because both contradicted a draft.

The archive CANNOT draw the loop. `xmv_4` is under closed-loop control and rattles
every sample, so flow against valve comes back as a cloud with a trend and the best
60-row window is a scribble. That is not a reason to avoid the archive. It is the
session's closing argument (closed-loop identification) arriving as a picture on slide
three, which is why `archive-cloud.png` exists and is shown next to the loop.

And the excitation failure cannot be shown with a step. A step recovers the true time
constant to three figures. It needs an input that genuinely never moves, which drops
the design matrix to rank 1 and returns a gain of exactly zero. That is a failure of
persistent excitation, not of the fit.

FIGURE SHAPES ARE CHOSEN FOR THE SLIDE
--------------------------------------
Every figure here lands on a 1280x720 MARP slide whose content box is 1140x620 after
the theme's padding, and MARP's `w:` sets width only. A near-square plot at a width
readable from the back of a room is taller than the whole content box, so the heading
and the closing line get clipped with no warning. Twelve L7 slides shipped that way
before anyone rendered the deck. Nothing here is taller than about 1.45:1, and after
changing any figsize run:

    node tools/check_slide_overflow.mjs _build/html/slides/l07/index.html

Outputs (committed alongside this script):
    feed-loop.png            wait at each valve position, or ramp: the curve and the loop
    archive-cloud.png        the same two columns from the real archive, which is a cloud
    feed-lag-plot.png        y[t] against y[t+1] is a straight line whose slope is a
    flat-channels.png        which channels are only repeating their last analyser result
    tep-flowsheet.png        the plant, with this session's channels marked on it

Raw data is cached in .cache/ and is gitignored. The archive figures read L5's cache of
the Tennessee Eastman archive (Rieth et al. 2017, CC0) and skip themselves if it is
absent, so the committed PNGs are the source of truth on a fresh clone.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
TEP_CACHE = HERE.parent.parent / "l05" / "figures" / ".cache" / "_bench_cols.parquet"

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
BLUE = "#1f5c99"

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

DT = 3.0
#: Measured from the archive itself in `archive_fit()`, then used to simulate the same
#: loop open loop. Quoting them here keeps the two records at the same parameters.
TAU_TRUE, K_TRUE = 10.6, 0.130
A_TRUE = np.exp(-DT / TAU_TRUE)
B_TRUE = K_TRUE * (1 - A_TRUE)
#: The archive's operating point, so the simulated record carries real units.
U0, Y0 = 57.6, 8.79
#: 25 samples up and 25 back down, so 75 minutes each way. Slower ramps close the loop
#: until it is invisible from the back of a room: 360 min up gives a gap of 0.08,
#: 75 min gives 0.40. Faster is not more honest, it is just more legible.
RAMP_N = 25


def load_run(fault=1, run=1):
    """One run of the archive, or None when L5's cache is not present."""
    if not TEP_CACHE.exists():
        return None
    df = pd.read_parquet(TEP_CACHE)
    g = df[(df.faultNumber == fault) & (df.simulationRun == run)]
    return g.sort_values("sample").reset_index(drop=True)


def fit_first_order(y, u, dt=DT):
    """Find a and b in y[t+1] = a*y[t] + b*u[t]. Returns (a, b, tau, K, rank)."""
    y = np.asarray(y, float); y = y - y.mean()
    u = np.asarray(u, float); u = u - u.mean()
    X = np.column_stack([y[:-1], u[:-1]])
    coef, *_ = np.linalg.lstsq(X, y[1:], rcond=None)
    a, b = coef
    return a, b, -dt / np.log(a), b / (1 - a), np.linalg.matrix_rank(X)


def simulate(u, noise=0.010, seed=7, settled=True):
    """The same loop, open loop. u is a deviation from the operating point.

    `settled` starts the loop already at rest for the first valve position. Without it
    the first twenty samples are a startup transient that reaches across the loop plot
    and reads, to a student, as part of the loop.
    """
    rng = np.random.default_rng(seed)
    y = np.zeros(len(u))
    if settled:
        y[0] = K_TRUE * u[0]
    for t in range(len(u) - 1):
        y[t + 1] = A_TRUE * y[t] + B_TRUE * u[t] + rng.normal(0, noise)
    return y


def fig_feed_loop():
    """Wait at each valve position and you get a line. Ramp and you get a loop."""
    u = np.concatenate([np.linspace(-5, 5, RAMP_N), np.linspace(5, -5, RAMP_N)])
    y = simulate(u, noise=0.0)
    i_up, i_dn = RAMP_N // 2, RAMP_N + RAMP_N // 2

    fig, ax = plt.subplots(1, 2, figsize=(10.5, 4.0), sharey=True)
    ax[0].plot(U0 + u, Y0 + K_TRUE * u, lw=2.2, color=MUTED)
    ax[0].set(xlabel="xmv_4, valve %", ylabel="xmeas_4, feed flow",
              title="set the valve, wait, write it down")

    ax[1].plot(U0 + u, Y0 + y, lw=2.0, color=CMU_RED)
    ax[1].plot(U0 + u, Y0 + K_TRUE * u, lw=1, ls="--", color=MUTED,
               label="if you had waited")
    ax[1].plot([U0 + u[i_up], U0 + u[i_dn]], [Y0 + y[i_up], Y0 + y[i_dn]],
               "o", color=INK, ms=7, zorder=5)
    ax[1].annotate("same valve,\ntwo flows", xy=(U0 + u[i_dn], Y0 + y[i_dn]),
                   xytext=(U0 - 5.0, Y0 + 0.28), fontsize=11, color=INK,
                   arrowprops=dict(arrowstyle="->", color=INK, lw=1.2))
    ax[1].set(xlabel="xmv_4, valve %", title="ramp it up and back down")
    ax[1].legend(frameon=False, fontsize=10, loc="lower right")
    fig.savefig(HERE / "feed-loop.png")
    plt.close(fig)
    print(f"wrote feed-loop.png   at valve {U0 + u[i_up]:.1f}%: "
          f"up {Y0 + y[i_up]:.3f}, down {Y0 + y[i_dn]:.3f}, "
          f"waited {Y0 + K_TRUE * u[i_up]:.3f}")


def fig_archive_cloud():
    """The same two columns from the archive. It is a cloud, and that is why."""
    g = load_run()
    if g is None:
        print("skipped archive-cloud.png (no TEP cache; run L5's make_figures first)")
        return
    u, y = g["xmv_4"].to_numpy(), g["xmeas_4"].to_numpy()

    fig, ax = plt.subplots(1, 2, figsize=(11, 4.0))
    ax[0].plot(g["sample"] * DT / 60, u, lw=0.8, color=BLUE)
    ax[0].set(xlabel="hours", ylabel="xmv_4, valve %",
              title="the valve, under automatic control")
    ax[1].plot(u, y, ".", ms=4, alpha=0.55, color=CMU_RED)
    ax[1].set(xlabel="xmv_4, valve %", ylabel="xmeas_4, feed flow",
              title="480 rows of archive: no loop, just a cloud")
    fig.savefig(HERE / "archive-cloud.png")
    plt.close(fig)
    print(f"wrote archive-cloud.png   valve std {u.std():.2f} %, "
          f"corr(u, y) = {np.corrcoef(u, y)[0, 1]:+.2f}")


def fig_feed_lag_plot():
    """y[t] against y[t+1]: a straight line whose slope is a. The derivation, drawn."""
    rng = np.random.default_rng(7)
    u = np.repeat(rng.choice([-3.0, 3.0], size=200), 2)[:400]
    y = simulate(u)
    keep = u[:-1] > 0            # hold the valve up so the line is visible
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    ax.plot(Y0 + y[:-1][keep], Y0 + y[1:][keep], ".", ms=5, color=CMU_RED, alpha=0.7)
    xs = np.linspace(Y0 + y.min(), Y0 + y.max(), 10)
    ax.plot(xs, A_TRUE * (xs - Y0) + B_TRUE * 3.0 + Y0, lw=1.6, color=INK,
            label=f"slope a = {A_TRUE:.3f}")
    ax.set(xlabel="flow now,  y[t]", ylabel="flow next sample,  y[t+1]",
           title="A lag plot, with the valve held open")
    ax.legend(frameon=False, fontsize=10)
    fig.savefig(HERE / "feed-lag-plot.png")
    plt.close(fig)
    print(f"wrote feed-lag-plot.png   a = {A_TRUE:.4f} -> tau = {-DT / np.log(A_TRUE):.1f} min")


def fig_flat_channels():
    """Which channels repeat their last value, and how often.

    A slow analyser reports on its own cycle and the historian holds the last result
    between cycles, which is a zero-order hold. On a 3-minute grid the channel is then
    flat on most rows. Downs and Vogel table 5 give the analyser cycles as 0.1 h for
    the feed and purge streams and 0.25 h for the product stream, which is 6 and 15
    minutes. The measured plateaus at 1/2 and 4/5 are exactly those two cycles on a
    3-minute grid, so the picture recovers the instrument from the data.
    """
    g = load_run()
    if g is None:
        print("skipped flat-channels.png (no TEP cache; run L5's make_figures first)")
        return
    cols = sorted((c for c in g.columns if c.startswith("xmeas_")),
                  key=lambda c: int(c.split("_")[1]))
    frac = np.array([float((g[c].diff() == 0).mean()) for c in cols])

    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.bar(range(len(cols)), frac, width=0.75,
           color=[CMU_RED if f > 0.4 else MUTED for f in frac])
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([c.split("_")[1] for c in cols], fontsize=8)
    for level, label in ((0.5, "a 6-minute analyser"), (0.8, "a 15-minute analyser")):
        ax.axhline(level, ls="--", lw=1, color=BLUE)
        ax.text(0.5, level + 0.02, f"{label} on a 3-minute grid", fontsize=10, color=BLUE)
    ax.set(xlabel="xmeas channel number", ylim=(0, 1.0),
           ylabel="fraction of rows equal\nto the row before",
           title="One run of the archive: which channels are only repeating themselves")
    fig.savefig(HERE / "flat-channels.png")
    plt.close(fig)
    print(f"wrote flat-channels.png   {int((frac > 0.4).sum())} of {len(cols)} channels "
          f"flat on more than 40% of rows")


def fig_tep_flowsheet():
    """The plant, with the three channel families this session touches marked on it.

    The base drawing is the course's own P&ID of the Tennessee Eastman process, the same
    one Lecture 5 uses. The annotation is what makes it an L7 figure: a room looking at a
    52-instrument flowsheet cannot find `xmv_4` unless somebody points at it, and the
    instructor should not have to do that with a cursor from the back of the hall.

    Coordinates are in pixels of L5's tep-screenshot.png (1908 x 1160) and were read off
    the drawing by hand, so they move if that PNG is ever regenerated.
    """
    # L5's committed P&ID, read in place. An earlier version kept a byte-identical
    # copy in this directory, which is a second 318 KB binary to keep in step with
    # the first for no benefit.
    raw = HERE.parent.parent / "l05" / "figures" / "tep-screenshot.png"
    if not raw.exists():
        print("skipped tep-flowsheet.png (L5's tep-screenshot.png not found)")
        return
    img = plt.imread(raw)
    h, w = img.shape[0], img.shape[1]

    fig, ax = plt.subplots(figsize=(13, 13 * h / w))
    ax.imshow(img)
    ax.set_axis_off()

    def callout(xy, xytext, text, color):
        ax.annotate(
            text, xy=xy, xytext=xytext, fontsize=15, color="white", weight="bold",
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.45", fc=color, ec="none", alpha=0.95),
            arrowprops=dict(arrowstyle="-|>", color=color, lw=3,
                            shrinkA=2, shrinkB=6, connectionstyle="arc3,rad=0.15"),
        )

    # Two callouts, not three. The room can absorb two arrows on a 52-instrument P&ID,
    # and reactor pressure no longer appears in the notes or the deck.
    #
    # The loop this whole session runs on: FC-4 on the A and C feed, bottom left.
    callout((555, 945), (300, 1105), "xmv_4  the valve\nxmeas_4  the flow", CMU_RED)
    # The composition analysers: the 0.500 and 0.800 plateaus in the channel screen.
    callout((1618, 520), (1380, 690), "xmeas_23-41\nthe slow analysers", "#2e7d32")

    fig.savefig(HERE / "tep-flowsheet.png")
    plt.close(fig)
    print(f"wrote tep-flowsheet.png  ({w}x{h} base)")


def archive_fit():
    """The numbers the simulator is set to. Printed so the two records stay in step."""
    g = load_run()
    if g is None:
        print("skipped archive fit (no TEP cache)")
        return
    a, b, tau, K, rank = fit_first_order(g["xmeas_4"], g["xmv_4"])
    print(f"archive fit, xmeas_4 ~ xmv_4: a = {a:.3f}, tau = {tau:.1f} min, "
          f"K = {K:+.4f}, rank {rank}")
    print(f"  operating point: valve {g['xmv_4'].mean():.1f} %, flow {g['xmeas_4'].mean():.2f}")


if __name__ == "__main__":
    archive_fit()
    fig_feed_loop()
    fig_archive_cloud()
    fig_feed_lag_plot()
    fig_flat_channels()
    fig_tep_flowsheet()
