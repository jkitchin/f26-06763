# L7 · Features for time-series and physical data

:::{admonition} At a glance
:class: tip

- **Session** L7, Week 4 · **Arc** Data Systems
- **Slides** <a href="../../slides/l07/">Deck for this session</a>
- **Demo** [`l07-features.ipynb`](l07-features.ipynb), a feature pipeline and the leak a scaler can hide
- **Assignment** A4 released this session
:::

## Why this matters

A feature is the point where a physical measurement stops being a physical measurement and
becomes a number a model can multiply. That translation step feels mechanical, a column of
floats in, a column of floats out, and it is precisely because it feels mechanical that it is
where meaning most often gets lost without anyone noticing. Get the units wrong, mix a
training statistic into a number the model will later be graded against, or hand a model a raw
sensor value it cannot place in physical context, and nothing crashes. The pipeline runs to
completion, the model trains, and it produces predictions that look exactly as plausible as
the ones from a pipeline that got every one of those steps right. This session is about the
layer of the stack where that silent failure lives, and it is arguably the most consequential
one in the whole course, because a mistake here does not announce itself the way a database
constraint violation or a build failure does.

The clearest illustration of what a units mistake costs is not a machine learning example at
all, and it does not need to be, because feature engineering has always been the discipline of
turning physical quantities into numbers a downstream system can consume; the fact that the
downstream consumer is now a gradient-boosted tree instead of a guidance algorithm changes
nothing about where the risk sits. It is worth carrying that history with you into this
session's more mundane-sounding topics, rolling means, delta features, categorical encodings,
because the discipline behind each of them is the same discipline that a spacecraft navigation
team failed to apply in 1999, at a cost of $327 million and an entire mission.

The second failure mode this session covers, leakage, is quieter still, because it does not
even require a units mismatch. It requires only that a statistic computed to describe "the
data I will train on" quietly absorbed a peek at "the data I will be judged on." Every
transform in a feature pipeline, a mean for imputation, a standard deviation for scaling, a
category list for one-hot encoding, is a summary statistic computed over some set of rows, and
the single question that determines whether your pipeline leaks is which rows. Get that
question wrong and your validation score stops measuring what your model will do in
deployment, and starts measuring how well it memorized information it was never supposed to
have. The module's own teaching note calls this the single most valuable lesson of the two
sessions on features and data quality, and this session is built to let you produce that bug
yourself and watch what it does, rather than take the warning on faith.

## Learning objectives

By the end of this session you should be able to:

- Construct lag, window, and frequency-domain features for sensor/simulation signals.
- Apply appropriate scaling and encoding while avoiding leakage.
- Assemble features into a reproducible feature pipeline with fitted transformers.

## Time-series features from a per-unit trajectory

The dataset for this session and next is NASA's C-MAPSS Turbofan Engine Degradation
Simulation, published by Saxena and colleagues at the 2008 Prognostics and Health Management
conference: run-to-failure sensor trajectories for fleets of simulated turbofan engines, one
row per engine per operating cycle, 21 sensor channels and three operational settings per row,
with the engine's failure cycle known exactly in the training data and deliberately withheld
in the test data. It is the standard benchmark for **Remaining Useful Life (RUL)** prediction,
and it earns its place here for a structural reason as much as a topical one: every feature
you build must respect that the data is **grouped by engine and ordered by cycle**, and getting
that grouping wrong is the fastest way to build a feature, or leak a label, without realizing
it.

The vocabulary of time-series features is short and worth having by name, because each entry
answers a different question about a trajectory. A **lag** feature answers "what was this
signal doing k steps ago," `sensor.shift(k)` in pandas, and it is the simplest way to hand a
model temporal context without requiring it to look backward on its own. A **difference**,
`sensor.diff()`, is a lag-1 feature's natural companion, answering "how much did this change
since last cycle" rather than "what was its value." **Rolling** statistics, a mean, a standard
deviation, a min or max computed over a trailing window, smooth out sensor noise and surface
trend, and the window length is a real modeling choice: too short and you are still fitting
noise, too long and you smear out the onset of degradation you are trying to detect.
**Expanding** windows are rolling windows with no fixed length, an all-history-so-far
statistic, useful when you want "this engine's mean sensor 4 reading to date" rather than a
fixed recent window. **Rate-of-change** and **time-since-event** round out the vocabulary:
the former is usually a difference normalized by elapsed time, and the latter answers "how
many cycles since the last time this condition held," which is exactly the shape of feature a
maintenance trigger or an alarm-state model needs.

```python
# Every one of these must be computed within a group, never across engines.
g = df.groupby('unit', group_keys=False)
df['sensor4_roll_mean_5'] = g['sensor4'].transform(lambda x: x.rolling(5).mean())
df['sensor4_delta0'] = g['sensor4'].transform(lambda x: x - x.iloc[0])
df['sensor4_roc'] = g['sensor4'].transform(lambda x: x.diff())
```

:::{admonition} Common pitfall
:class: warning

Compute a rolling or lag feature on a dataframe that has not been grouped, and pandas will
happily compute it, rolling right across the boundary between engine 7's last cycle and engine
8's first one. The result is not an error, it is a feature that quietly tells the model engine
8 started life mid-degradation, borrowed from whatever engine happened to sort just before it.
`groupby('unit')` before every one of these transforms is not a style preference, it is the
difference between a feature and a fabrication.
:::

C-MAPSS itself samples on a clean, regular grid, one row per cycle with no gaps, which makes
it a poor illustration of the last item on this topic's list: **resampling irregular sensor
data to a fixed grid**. For that, recall the Intel Berkeley Lab motes from [L3](../l03/notes.md),
which reported roughly every 31 seconds but dropped out unpredictably. Turning that irregular
stream into a feature matrix usually means resampling to a fixed cadence, `resample('1min')`
in pandas, choosing an aggregation for the rare cycle that contains more than one reading and
an explicit policy, forward-fill, interpolate, or leave null, for the far more common cycle
that contains none. That policy is itself a feature-engineering decision with consequences: a
forward-filled voltage reading during a real dropout invents data continuity that was not
there, and a model that never sees the resulting gap has no way to learn that dropouts predict
anything.

## Physical and domain features

Not every useful feature comes from a rolling window over a raw channel. **Dimensionless
groups**, ratios engineered specifically to be independent of a system's absolute scale, are
frequently more informative than any of the raw quantities they are built from. Engineers have
relied on quantities like the Reynolds number, the ratio of inertial to viscous forces in a
fluid, or the power factor in electrical systems, precisely because they let you compare a
small lab rig and a full-scale plant on the same axis, and a well-chosen ratio feature does the
same work for a model: it collapses a nuisance dimension (the engine's absolute size, the
sensor's specific gain) instead of asking the model to learn that dimension away from raw
values.

**Energy and power features** are usually derived rather than measured directly: a bearing's
kinetic energy from shaft speed, a compressor's specific power from a pressure ratio and mass
flow. Deriving them explicitly, rather than hoping a model will discover the same relationship
implicitly, gives you a feature grounded in a known physical law rather than a coincidental
correlation in one dataset. **Calibration corrections** belong here too, and they connect
directly back to the sensor drift you measured in [L1](../l01/notes.md): if a channel's raw
output degrades or shifts over an instrument's lifetime, the calibration curve that corrects
for it belongs in the feature pipeline, applied consistently to every row that channel touches,
not patched in ad hoc after the fact.

**Unit consistency** is the discipline that ties all of the above together, and it is worth
treating as a first-class engineering requirement rather than a habit of careful people,
because the cost of getting it wrong is not hypothetical.

### Case study: a $327 million unit mismatch

NASA's Mars Climate Orbiter launched in December 1998 to study the Martian atmosphere and
relay data from a companion lander. On 23 September 1999, it fired its main engine to enter
orbit around Mars and was never heard from again. The subsequent Mishap Investigation Board
found a single root cause: the ground software that Lockheed Martin built to calculate the
small trajectory corrections from the spacecraft's thrusters computed those forces in
pound-seconds, the English unit, while the navigation software at JPL that consumed those
values expected newton-seconds, the metric unit NASA's own interface specifications called
for. The conversion was never applied, at any step, by any process, for the entire
cruise phase. Small errors in the calculated trajectory accumulated over months, and by the
time of orbit insertion the spacecraft was on course to pass roughly 57 kilometers above the
Martian surface rather than the planned 140 to 150 kilometers, low enough that it is believed
to have either burned up or been ejected into an orbit around the sun.

The mechanism is a feature engineering failure in the most literal sense: a physical quantity,
thruster impulse, was computed correctly in the units one team used and consumed incorrectly
by a system that assumed a different unit, and the number that crossed that boundary carried
no marker of which convention it was in. Nothing in the file format, the interface, or the
data itself distinguished a pound-second from a newton-second; both are just a float. The
review board's central recommendation followed directly: verify the physical units of every
data interface between systems, explicitly and in writing, rather than assuming a shared
convention that was never actually specified anywhere both teams could check it.

:::{admonition} What a practitioner should take from this
:class: tip

Never let a numeric feature column imply its own units. Name the column with the unit
(`thrust_lbf`, not `thrust`), assert the unit at every system boundary where data crosses
from one codebase or one team to another, and treat a bare float crossing an interface with no
attached unit as an incomplete data contract, not a convenience.
:::

Once units are settled, **spectral features** are the tool for a class of physical signal
that a rolling mean cannot see: vibration and acoustic data, where the information is not in
the raw waveform's level but in *which frequencies* carry energy. The **Fast Fourier
Transform** decomposes a windowed signal into its frequency components, and a **band energy**
feature sums the squared magnitude of those components over a frequency range you choose for
a physical reason, for instance the characteristic frequency at which a specific bearing
defect (an outer-race fault, an inner-race fault) is known to show up given the bearing's
geometry and the shaft's rotation speed. The engineering judgment is in choosing which bands
matter for your physical system; the transform itself is a few lines.

```python
import numpy as np

def band_energy(signal, fs, f_lo, f_hi):
    """Energy in [f_lo, f_hi] Hz of a signal sampled at fs Hz."""
    freqs = np.fft.rfftfreq(len(signal), d=1 / fs)
    spectrum = np.abs(np.fft.rfft(signal)) ** 2
    band = (freqs >= f_lo) & (freqs <= f_hi)
    return spectrum[band].sum()
```

## Scaling, encoding, and fitting on train only

Most models, and nearly all linear ones, are sensitive to the scale of their inputs, so the
raw sensor and setting columns almost always need transforming before they reach a model.
**Standardization** (subtract the mean, divide by the standard deviation) is the default,
appropriate when a feature is roughly symmetric and you have no reason to bound it. **Min-max
scaling** compresses a feature to a fixed range, useful when a downstream algorithm
specifically expects bounded inputs, but it is fragile to outliers, since a single extreme
value stretches the whole range and compresses everything else toward zero. **Robust scaling**
(median and interquartile range instead of mean and standard deviation) is the answer when
your physical data has exactly the kind of heavy-tailed outliers a raw sensor produces during
a fault or a dropout, since the median barely moves for a handful of extreme readings where a
mean would not. **Log** and **Box-Cox** transforms address a different problem, skew: many
physical quantities (particle counts, chemical concentrations, time-to-event data) are
naturally log-distributed rather than normally distributed, and a model, or a metric like
RMSE, that implicitly assumes symmetric errors will be dominated by the long tail unless you
transform it away first. **Categorical encoding**, one-hot or target encoding for an
equipment ID or an operating regime, is the same idea applied to non-numeric columns: the
model needs a numeric representation, and the encoding you choose determines whether it can
generalize to a regime it has not seen in training.

Every single one of these transforms is fit from data, which means every one of them is a
place leakage can enter, and it is worth stating the general rule once, plainly, rather than
attaching it to each transform separately: **fit every transform on the training split only,
then apply the already-fitted transform to validation and test data unchanged.** A scaler's
mean and standard deviation, a Box-Cox transform's lambda, an encoder's category list, all of
these are statistics, and a statistic computed with test rows included has, by definition,
seen something about the test set before the model was evaluated against it.

This session's demo tests the sharpest version of that rule directly: fit a `StandardScaler`
on training engines only, versus fit the identical scaler on training and test engines
combined, and compare the resulting RUL error. The honest result, which the notebook walks
through rather than asserts, is that the gap this particular comparison produces is often
small, sometimes close to zero. That is not a failure of the lesson; it is the more useful
version of it. A linear least-squares fit is mathematically invariant to rescaling its
inputs, so a plain linear regression would show *no* difference at all regardless of how the
scaler was fit, which would make the demo look broken rather than instructive. A regularized
model like `Ridge` is not scale-invariant, because its penalty acts on the coefficients
directly, so it does show a real, measurable, if modest effect here, largely because C-MAPSS's
test engines are truncated before failure and therefore never reach the most degraded sensor
values that appear late in the training trajectories, giving the two scalers genuinely
different statistics to work from.

:::{admonition} Common pitfall
:class: warning

The size of a given leak is not evidence about whether leakage is a real risk. It depends on
how different your model is under a rescaling (an unregularized linear model will show
nothing; a distance-based or heavily regularized one can show a great deal), and on how
different your train and test distributions actually are (two samples of the same simulated
regime differ less than a training set and a genuinely new deployment site will). Fit on
train only every time, on principle, because you cannot know in advance which of your models,
datasets, or years will be the one where the shortcut costs you.
:::

## A leakage-safe pipeline, and what "safe" actually buys you

Scikit-learn's `Pipeline` and `ColumnTransformer` exist to make the fit-on-train-only rule
close to unbreakable rather than merely well understood. A `Pipeline` chains a sequence of
transforms and a final estimator into one object; call `.fit(X_train, y_train)` and every
step inside fits using only the rows you handed it, then call `.predict(X_test)` and every
step applies its already-fitted parameters, with no path in the API for `X_test` to influence
any of them. `ColumnTransformer` extends this across heterogeneous columns, a `StandardScaler`
on the numeric sensor features and a `OneHotEncoder` on a categorical regime column, fit and
applied together as one step. The benefit is not convenience; it is that the leak this
session's demo produces on purpose becomes structurally difficult to write by accident, because
there is no longer a `.fit()` call anywhere in the code that has `X_test` in scope.

```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge

pipeline = Pipeline([
    ('scale', StandardScaler()),
    ('model', Ridge(alpha=10.0)),
]).fit(X_train, y_train)          # every fitted statistic comes from X_train alone

pipeline.predict(X_test)          # X_test only ever gets .transform()'d, never .fit()
```

A fitted `Pipeline` is also the natural unit to **persist**. Saving it whole (with `joblib`,
in the demo) captures the model's weights and every transform's fitted statistics together, so
reloading it on a different machine, or a month later, reproduces the exact same predictions
rather than a script's best attempt at reconstructing them. That artifact is what A4 asks you
to save and what a **feature store** exists to manage at organizational scale: a system that
centralizes feature *definitions* so the same `sensor4_roll_mean_5` computed for training
matches, byte for byte, the one computed for serving, and so five teams building five models
on the same sensor fleet compute it once rather than five slightly different ways. This course
does not build one, because the discipline it enforces, one definition, one fitted transform,
applied consistently, is exactly what a well-built `Pipeline` already gives you at the scale of
a single project.

## Where this pushes back

Feature engineering rewards judgment more than volume, and every technique in this session has
a failure mode worth naming before you reach for it reflexively.

**More lags and windows is not more signal, it is more overfitting surface.** A hundred engines
and a few hundred generated lag/rolling/delta columns is a recipe for a model that fits noise
in the training fleet and generalizes poorly to a new one, especially once you add every window
length you can think of "just in case." Automated feature-generation tools like
[tsfresh](https://tsfresh.readthedocs.io/) can produce hundreds of candidate features from a
single signal in one call, and that scale is exactly the danger: test enough candidate
features against one target and some will correlate by chance alone, a multiple-comparisons
problem hiding inside a feature-engineering step that looks like due diligence.

**A clipped RUL target is a modeling assumption, not a fact about the engine.** Capping the
label at 125 cycles encodes a belief that health is roughly constant until late in life and
then declines, which is a reasonable prior for this dataset and not a universal truth; a
different failure mode, a sudden fault rather than gradual wear, would make the same
assumption actively wrong, and it is worth checking that assumption against your system rather
than inheriting it because it is what the literature does.

**Log and Box-Cox transforms complicate the number you eventually have to explain.** A model
trained to predict log-RUL requires you to exponentiate its output before an error metric or a
maintenance threshold means anything in the units an engineer actually thinks in, and it is
easy to report an RMSE computed in the transformed space as though it were cycles, which is a
quietly wrong number that looks exactly like a right one.

**A leakage-safe pipeline defends against one kind of leak, not every kind.** Fitting every
transform on the training fold closes off the specific bug this session's demo produces, but it
does nothing to stop a much larger one: a random, row-level train/test split that puts cycle
150 of an engine in training and cycle 151 of the same engine in test. The model then has
effectively seen the answer to a nearly identical question, and no `Pipeline` will catch it,
because the split happened before the pipeline ever saw the data. That is deliberately not this
session's demo. It is next session's central lesson, along with the full taxonomy of leakage
this feature layer only introduces.

:::{admonition} What a practitioner should take from this
:class: tip

Build fewer features you can each explain physically over many you generated automatically and
hope correlate. Fit every transform inside a `Pipeline` on the training fold only, as a
structural habit rather than a remembered rule, and treat the size of any one leakage
experiment's result as informative about that experiment, not as reassurance about your next
one.
:::

## In-class demo

We build the rolling-mean, rolling-std, delta-from-start, and rate-of-change features for
three sensor channels on the C-MAPSS FD001 data, fit a `Ridge` RUL model two ways, a
`StandardScaler` fit on training engines only versus the same scaler fit on training and test
combined, and compare RMSE against the true remaining life in `RUL_FD001.txt`. Watch for two
things: the gap between the two pipelines, which the notebook argues honestly may be small,
and why it is `Ridge` rather than plain linear regression doing the comparing, since an
unregularized fit would show no difference at all regardless of the leak. We close by saving
the correct pipeline with `joblib` and reloading it to confirm it reproduces its own
predictions exactly.

The runnable notebook is [`l07-features.ipynb`](l07-features.ipynb). It expects the three
FD001 files in `.cache/CMAPSS/`; the notebook's first cell links the NASA repository page and
names the files to place there.

## Summary

A feature is where a physical measurement is translated into a number a model can use, and
this session's argument is that both halves of that translation, getting the physical meaning
right and keeping the training statistics honest, fail silently rather than loudly when they
fail. Mars Climate Orbiter is what an unresolved unit mismatch costs when the "model" consuming
the number is a navigation system rather than a gradient-boosted tree; the mechanism, a bare
float crossing a system boundary with no enforced convention, is identical either way. Lags,
rolling statistics, deltas, and rate-of-change turn a per-unit trajectory into a feature matrix,
provided every one of them respects the grouping the data actually has, and scaling, encoding,
and spectral features extend the same vocabulary to skewed physical quantities, categorical
regimes, and vibration signals. Wrapping every one of those transforms in a scikit-learn
`Pipeline` fit on the training fold alone is what makes fit-on-train-only a structural property
of your code rather than a rule you have to remember, and this session's demo shows both that
the resulting gap can be modest for one comparison and why that is not permission to skip the
discipline. Next session picks up exactly where this one draws a line: the full taxonomy of
leakage, correct grouped and temporal splits, and dataset versioning, so that the pipeline this
session builds is not just correct today but reproducible from raw data a year from now.

## Resources

- [scikit-learn User Guide: Preprocessing data](https://scikit-learn.org/stable/modules/preprocessing.html).
  Standardization, min-max, robust scaling, and encoding, from the source.
- [scikit-learn User Guide: Pipelines and composite estimators](https://scikit-learn.org/stable/modules/compose.html).
  `Pipeline` and `ColumnTransformer`, and why fitting inside one closes off the leak this
  session demonstrates.
- [tsfresh documentation: Overview on extracted features](https://tsfresh.readthedocs.io/en/latest/text/list_of_features.html).
  A working vocabulary of time-series features, and a caution: read this alongside the
  multiple-comparisons risk of generating all of them at once.
- A. Saxena, K. Goebel, D. Simon, and N. Eklund, "Damage Propagation Modeling for Aircraft
  Engine Run-to-Failure Simulation," *International Conference on Prognostics and Health
  Management (PHM)*, 2008. The paper introducing C-MAPSS and the FD001-FD004 subsets used
  here and in A4.
- [NASA Prognostics Center of Excellence Data Set Repository](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/).
  Source of the C-MAPSS Turbofan Engine Degradation Simulation Data Set; download instructions
  are in the demo notebook.
- [Mars Climate Orbiter Mishap Investigation Board, Phase I Report](https://llis.nasa.gov/llis_lib/pdf/1009464main1_0641-mr.pdf),
  NASA, November 1999. The primary source for the units-mismatch case study above.
- [NASA press release: Mars Climate Orbiter Failure Board Releases Report](https://mars.nasa.gov/msp98/news/mco991110.html),
  10 November 1999. A shorter summary of the board's findings and the immediate cause.
- A. Ng, "A Chat with Andrew on MLOps: From Model-centric to Data-centric AI," DeepLearning.AI,
  2021. The talk that popularized "data-centric AI" as a name for iterating on data and labels
  rather than only on model architecture, which this arc's second session builds on directly.

## Assignment

A4, "Feature pipeline + dataset versioning," is released this session and due roughly one week
later. It asks you to engineer per-unit time-series features for C-MAPSS (or a documented
run-to-failure fallback), wrap scaling in a leakage-safe `Pipeline` fit on training units only,
and quantify the RMSE cost of a leaky variant against the correct one, before L8 adds dataset
versioning with DVC. The full spec and rubric are in `course/assignments/a04.md`; this
paragraph is a pointer, not the rubric.
