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
layer of the stack where that silent failure lives: a mistake here does not announce itself
the way a database constraint violation or a build failure does.

The clearest illustration of what a units mistake costs is not a machine learning example at
all, and it does not need to be, because feature engineering has always been the discipline of
turning physical quantities into numbers a downstream system can consume; the fact that the
downstream consumer is now a gradient-boosted tree instead of a guidance algorithm changes
nothing about where the risk sits. It is worth carrying that history with you into this
session's more mundane-sounding topics, rolling means, delta features, categorical encodings,
because the discipline behind each of them is the same discipline that a spacecraft navigation
team failed to apply in 1999, at the cost of an entire mission.

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

```{index} remaining useful life, lag feature, rolling window feature, expanding window feature
```

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
8's first one. No error fires. The result is a feature that quietly tells the model engine 8
started life mid-degradation, borrowed from whatever engine happened to sort just before it.
`groupby('unit')` before every one of these transforms is the difference between a feature
and a fabrication.
:::

The figure below is that pitfall, measured rather than described. It plots a five-cycle rolling
mean of one sensor across the boundary between engine 1 and engine 2, computed both ways.

```{figure} figures/grouped-vs-not.png
:alt: A rolling mean of a sensor plotted across the boundary between two engines. The grouped version drops immediately at the boundary; the ungrouped version decays gradually across four rows, carrying the previous engine's higher values into the new engine's first cycles.
:width: 100%

A five-cycle rolling mean either side of an engine boundary. The grouped version starts fresh at
engine 2's first cycle. The ungrouped version spends four rows blending in engine 1's
end-of-life readings, with a peak error of about 1.0 on a channel whose entire range across the
fleet is about 1.7. Every engine boundary in the file has its own copy of this defect, and with
a longer window it is proportionally worse. Generated by `figures/make_figures.py`.
```

The contamination is worst at the *start* of each engine's trajectory, where the model is being
asked to predict a long remaining life, and it always drags those early features in the direction
of the previous engine's *end* of life. The bias it introduces has the same shape as the signal
you are trying to learn, which makes it more dangerous than random noise.

### Which channels are worth featurizing

Before building any of this, look at what you have. Of FD001's 21 sensor channels, **six hold a
single constant value in all 20,631 training rows**, and several more carry almost nothing. The
demo notebook screens for this, because a rolling mean of a constant is a constant, its rolling
standard deviation is zero, and its delta-from-first-cycle is zero: four columns of nothing, per
dead channel, all of which a scaler will then dutifully attempt to standardize.

```{figure} figures/sensor-degradation.png
:alt: Left, a bar chart ranking all 21 FD001 sensor channels by absolute correlation with clipped RUL, with six channels at zero. Right, three stacked panels showing sensor 11 and sensor 4 trending upward over cycles for three engines while sensor 1 stays perfectly flat.
:width: 100%

Left: every channel ranked by association with the target. Six are flat, and the informative
ones top out around 0.78. Right: three engines, three channels, each on its own scale. Sensors
11 and 4 climb as the engines degrade, and the trajectories are visibly noisy, which is what the
rolling window is for. Sensor 1 does nothing at all, for any engine, ever. Generated by
`figures/make_figures.py`.
```

:::{admonition} A caveat that cost me an hour
:class: warning

[L5](../l05/notes.md) offers a neat shortcut for finding constant columns: a numeric column is
constant exactly when its standard deviation is zero, and `std` is far cheaper to compute than a
distinct-value count. On this dataset that test **silently fails on two of the six** dead
channels.

The reason is floating point. Sensor 5 holds the value `14.62` in every row and sensor 16 holds
`0.03`, so both have a true variance of zero, but variance is computed from sums of squared
deviations rather than looked up, and the rounding leaves `std()` returning `5.3e-15` and
`3.5e-18` instead of `0.0`. A literal `spread == 0` test therefore declares them varying and
keeps them, and you carry eight columns of noise-free nothing into your model.

Use `nunique() <= 1` when you can afford the pass, or `std() < 1e-12` when you cannot. The
general lesson is worth more than the fix: an equality test against zero on a computed
floating-point quantity is a bug waiting for the right input, and "the right input" here is
something as ordinary as a sensor that reads a round number.
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

```{index} domain feature, spectral feature, band energy, unit consistency
```

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
for it belongs in the feature pipeline, applied consistently to every row that channel touches
rather than patched in ad hoc after the fact.

**Unit consistency** is the discipline that ties all of the above together, and it is worth
treating as a first-class engineering requirement rather than a habit of careful people,
because the cost of getting it wrong is not hypothetical.

### Case study: a $327 million unit mismatch

```{index} pair: case study; Mars Climate Orbiter
```

NASA's Mars Climate Orbiter launched on 11 December 1998 to study the Martian atmosphere and
relay data from a companion lander. On 23 September 1999 it fired its main engine to enter
orbit around Mars, and its signal was lost at 09:04:52 UTC, forty-nine seconds earlier than
the predicted start of occultation. It was never heard from again.

The [Mishap Investigation Board](https://llis.nasa.gov/llis_lib/pdf/1009464main1_0641-mr.pdf)
identified exactly one root cause, and stated it in terms any engineer who has passed data
between two programs will recognize. A piece of Lockheed Martin ground software called
`SM_FORCES` computed the impulse delivered by the spacecraft's thrusters. A project **Software
Interface Specification** required its output, written to a file named AMD (Angular Momentum
Desaturation), to be in metric newton-seconds. The software wrote English pound-seconds
instead. In the Board's words, "The SIS, which was not followed, defines both the format and
units of the AMD file."

That single unconverted number produced a specific, quantifiable error: the navigation
software "underestimated the effect on the spacecraft trajectory by a factor of 4.45, which is
the required conversion factor from force in pounds to Newtons." One pound-force is 4.45
newtons, so every thruster firing was modeled as though it were roughly four and a half times
weaker than it actually was.

Two details explain why an error in a file called "small forces" was fatal rather than
negligible. First, those firings were far more frequent than anyone had budgeted for: because
the orbiter's solar array was asymmetric, unlike Mars Global Surveyor's, solar pressure built
up angular momentum faster, and desaturation events "occurred 10-14 times more often than was
expected by the operations navigation team." A 4.45× error, applied ten to fourteen times more
often than planned, over a nine-month cruise, is no longer small. Second, nothing corrected it
along the way.

The numbers at Mars are worth stating precisely, because they are widely misquoted. The final
trajectory correction maneuver was computed on 8 September 1999 to put the first periapsis,
the closest approach, at **226 km**. During the week that followed, orbit determination showed
that figure sliding to 150-170 km. About an hour before orbit insertion, better tracking data
put it as low as **110 km**. The minimum altitude the Board records as survivable for this
spacecraft was **80 km**. Reconstructed afterwards with the small-forces error corrected, the
actual first periapsis was **57 km**, which the Board judged "too low for spacecraft
survival." The orbiter was either destroyed in the atmosphere or thrown back out into
heliocentric space.

### The part that should worry you more than the units

The units bug is the memorable half of this story. The half that generalizes is what happened
to the evidence.

The discrepancy was visible for months. The Board records that "throughout spring and summer
of 1999, concerns existed at the working level regarding discrepancies observed between
navigation solutions," and that residuals between the expected and observed Doppler signature
of those frequent desaturation events "was noted but only informally reported." As the
spacecraft approached Mars, three independent orbit determination schemes were run, and "the
Doppler-only solutions consistently indicated a flight path insertion closer to the planet."
The Board's assessment of that fact is one sentence long: "These discrepancies were not
resolved."

The root cause was not identified until **29 September 1999**, six days after the spacecraft
was lost. The Board is explicit that this was a process failure rather than a competence
failure: "The Board recognizes that mistakes occur on spacecraft projects. However, sufficient
processes are usually in place on projects to catch these mistakes before they become critical
to mission success. Unfortunately for MCO, the root cause was not caught by the processes
in-place in the MCO project."

This is the same shape as the ninety-seven ignored "Power Peg disabled" emails in
[L5](../l05/notes.md)'s Knight Capital case: a system emitting a true signal that no process
was obliged to act on. An anomaly that is "noted informally" is not monitoring.

:::{admonition} A note on the \$327 million
:class: note

You will see this failure attributed to a cost of "\$327 million," and it is worth being
careful with the figure, because the Board's report does not contain it. The report never
mentions cost at all. The \$327.6 million figure is the total for the **Mars Surveyor '98
program**, which funded two spacecraft: this orbiter and the Mars Polar Lander, which was lost
separately in December 1999 for unrelated reasons. Published breakdowns put the orbiter
spacecraft itself nearer \$125 million.

So "a units bug cost \$327 million" attributes a two-mission program budget to one mission's
navigation error. The verified facts are quite damning enough without it: a specification was
written, ignored, and never checked, and a spacecraft that worked correctly in every other
respect was flown into a planet.
:::

The mechanism is a feature engineering failure in the most literal sense. A physical quantity,
thruster impulse, was computed correctly in the units one team used and consumed incorrectly by
a system that assumed a different unit, and the number that crossed that boundary carried no
marker of which convention it was in. Nothing in the file format, the interface, or the data
itself distinguished a pound-second from a newton-second. Both are just a float. Note that a
specification did exist and did say newton-seconds; writing it down was not enough, because
nothing verified compliance. The Board's recommendations to the surviving lander mission
followed directly: "verify the consistent use of units throughout the MPL spacecraft design and
operation," and conduct "a software audit for SIS compliance on all data transferred between
the JPL operations navigation team and the spacecraft operations team."

:::{admonition} What a practitioner should take from this
:class: tip

Never let a numeric feature column imply its own units. Name the column with the unit
(`thrust_lbf`, not `thrust`), assert the unit at every system boundary where data crosses
from one codebase or one team to another, and treat a bare float crossing an interface with no
attached unit as an incomplete data contract.

Then note the harder half: MCO *had* a written specification requiring newton-seconds, and it
did not help, because nothing checked compliance. A data contract that is documented but not
executed is a comment. This is the argument for the pandera schemas from
L6's successor applied to units: a range assertion on
`thrust_lbf` that fails loudly when someone hands it newtons is worth more than a paragraph in
an interface document that both teams believe they are following.

A diagnostic that disagrees with your model of the world for months deserves escalation.
"Noted but only informally reported" is how this one went unaddressed until the spacecraft
was lost.
:::

Once units are settled, **spectral features** are the tool for a class of physical signal
that a rolling mean cannot see: vibration and acoustic data, where the information lives in
*which frequencies* carry energy rather than in the raw waveform's level. The **Fast Fourier
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

```{index} standardization, robust scaling, Box-Cox transform, one-hot encoding
```

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
combined, and compare the resulting RUL error. The result is worth stating up front, because it
is not the one a cautionary tale would script. **The gap is about 0.002 cycles on an RMSE of
roughly 19.** Two thousandths of a cycle. If you were looking for a scare number, this demo
does not have one.

Now hold that next to a second measurement from the same notebook. The two scalers, the honest
one and the leaky one, disagree about where a feature is centred by **up to 23%**, and about its
spread by up to 9%. So the leak unambiguously happened, it changed the transform substantially,
and the metric reported almost nothing.

A common shorthand says leakage inflates your score. This experiment shows something narrower and
more useful: your validation metric is not a leak detector. Whether a leak shows up in it depends
on the model you happen to be using, and the notebook demonstrates this by running the identical
leak past four:

```{figure} figures/leakage-by-model.png
:alt: Bar chart of the RMSE penalty caused by an identical scaler leak under four models. LinearRegression shows zero, Ridge with a mild penalty shows almost zero, Ridge with a strong penalty shows a negative bar meaning the leak helped, and a nearest-neighbours model shows a clearly positive bar.
:width: 100%

The identical leak, scored four ways. Nothing changes between bars except the model. The
transform was equally contaminated in all four cases. Generated by `figures/make_figures.py`.
```

| model | gap in RMSE | why |
|---|---|---|
| `LinearRegression` | exactly 0 | least squares is invariant to input rescaling |
| `Ridge(alpha=10)` | +0.002 | the penalty barely bites at this strength |
| `Ridge(alpha=1e4)` | **-0.14** | penalty dominates, and the leak *helps* |
| `KNeighbors(k=5)` | **+0.35** | every prediction is a distance, and distance is scale |

Read the third row again. Under a strong penalty the leaky pipeline scores *better* than the
honest one. A leak makes your number meaningless rather than reliably inflating it, and it can
just as easily flatter you as punish you. The nearest-neighbours row is the counterweight: change
nothing but the model, and the same leak becomes impossible to miss.

Two structural features of C-MAPSS keep the effect small in the linear cases. The test engines
are truncated before failure, so they never reach the most degraded sensor values that appear
late in the training trajectories, which is exactly why the scalers differ at all. But train and
test are still the same simulated fleet under the same operating condition, so the differences
are modest by the standards of a real deployment, where the new site has a different ambient
temperature, a different sensor vendor, and a different duty cycle.

:::{admonition} Common pitfall
:class: warning

The size of a given leak is not evidence about whether leakage is a real risk. It depends on how
sensitive your model is to a rescaling (an unregularized linear model will show nothing; a
distance-based one can show a great deal), and on how different your train and test
distributions actually are (two samples of the same simulated regime differ less than a training
set and a genuinely new deployment site will).

The practical consequence is that you cannot audit for this leak by looking at your metrics. You
have to audit the code: find every `.fit()` call and check what was in scope when it ran. Fit on
train only every time, on principle, because you cannot know in advance which of your models,
datasets, or years will be the one where the shortcut costs you, and by then the run that
established your baseline is months old.
:::

## A leakage-safe pipeline, and what "safe" actually buys you

```{index} data leakage, scikit-learn pipeline, feature store
```
```{index} pair: failure mode; fitting a scaler before the split
```

Scikit-learn's `Pipeline` and `ColumnTransformer` exist to make the fit-on-train-only rule
close to unbreakable rather than merely well understood. A `Pipeline` chains a sequence of
transforms and a final estimator into one object; call `.fit(X_train, y_train)` and every
step inside fits using only the rows you handed it, then call `.predict(X_test)` and every
step applies its already-fitted parameters, with no path in the API for `X_test` to influence
any of them. `ColumnTransformer` extends this across heterogeneous columns, a `StandardScaler`
on the numeric sensor features and a `OneHotEncoder` on a categorical regime column, fit and
applied together as one step. The benefit is that the leak this session's demo produces on
purpose becomes structurally difficult to write by accident: there is no longer a `.fit()` call
anywhere in the code that has `X_test` in scope.

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

**More lags and windows adds overfitting surface faster than it adds signal.** A hundred engines
and a few hundred generated lag/rolling/delta columns is a recipe for a model that fits noise
in the training fleet and generalizes poorly to a new one, especially once you add every window
length you can think of "just in case." Automated feature-generation tools like
[tsfresh](https://tsfresh.readthedocs.io/) can produce hundreds of candidate features from a
single signal in one call, and that scale is exactly the danger: test enough candidate
features against one target and some will correlate by chance alone, a multiple-comparisons
problem hiding inside a feature-engineering step that looks like due diligence.

**A clipped RUL target encodes a modeling assumption about how this engine degrades.** Capping
the label at 125 cycles encodes a belief that health is roughly constant until late in life and
then declines, a reasonable prior for this dataset but a specific one rather than a universal
truth; a different failure mode, a sudden fault rather than gradual wear, would make the same
assumption actively wrong, and it is worth checking that assumption against your system rather
than inheriting it because it is what the literature does.

**Log and Box-Cox transforms complicate the number you eventually have to explain.** A model
trained to predict log-RUL requires you to exponentiate its output before an error metric or a
maintenance threshold means anything in the units an engineer actually thinks in, and it is
easy to report an RMSE computed in the transformed space as though it were cycles, which is a
quietly wrong number that looks exactly like a right one.

**A leakage-safe pipeline defends against only one kind of leak.** Fitting every
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

We screen all 21 FD001 channels for the dead ones, build rolling-mean, rolling-std,
delta-from-start, and rate-of-change features for the three most informative survivors, then fit
an RUL model two ways: a `StandardScaler` fit on training engines only, versus the same scaler
fit on training and test combined. RMSE is scored against the true remaining life in
`RUL_FD001.txt`.

Watch for four things, in order of how much they should change how you work.

The **scaler statistics diverge by up to 23%** between the two fits: the leak was real before
any model entered the picture. The **`Ridge` gap is only 0.002 cycles**, small enough that a real
leak can be invisible in a metric. The **four-model comparison** shows the same leak reading as
zero, negligible, negative, and clearly positive depending only on the estimator, so scores alone
cannot tell you whether a leak occurred. And two **silent bugs that were in this notebook until
it was checked** are documented in place: a constant sensor promoted to a "key degradation
channel," and a `startswith('sensor2')` filter that quietly swept in `sensor20` and `sensor21`.

We close by saving the correct pipeline with `joblib` and reloading it to confirm it reproduces
its own predictions exactly.

The runnable notebook is [`l07-features.ipynb`](l07-features.ipynb). It downloads and caches the
C-MAPSS archive itself on first run, so it needs no manual setup; if NASA moves the file again,
the first cell explains where to put the three FD001 text files by hand.

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
`Pipeline` fit on the training fold alone turns fit-on-train-only into a structural property
of your code instead of a rule you have to remember, and this session's demo shows both that
the resulting gap can be modest for one comparison and why that is not permission to skip the
discipline. Next session picks up exactly where this one draws a line: the full taxonomy of
leakage, correct grouped and temporal splits, and dataset versioning, so that the pipeline this
session builds stays correct today and reproducible from raw data a year from now.

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
  NASA, 10 November 1999. The primary source for every figure in the case study above, and only
  48 pages. Read the Executive Summary and section 2, "MCO Mishap," which together take about
  fifteen minutes and are a model of how to write up a failure. Note that popular retellings of
  this incident routinely garble the altitudes and attach a cost figure the report never states.
- [NASA JPL: Mars Climate Orbiter mission page](https://www.jpl.nasa.gov/missions/mars-climate-orbiter/).
  Mission background and dates. Included deliberately in place of the 1999 press release that
  most write-ups cite: that URL still returns HTTP 200 but now serves an unrelated modern NASA
  page, which is the L1 lesson about link rot arriving on schedule.
- A. Ng, "A Chat with Andrew on MLOps: From Model-centric to Data-centric AI," DeepLearning.AI,
  2021. The talk that popularized "data-centric AI" as a name for iterating on data and labels
  rather than only on model architecture, which this arc's second session builds on directly.
- [scikit-learn: Common pitfalls and recommended practices](https://scikit-learn.org/stable/common_pitfalls.html).
  The library's own writeup of data leakage, including the "how to avoid it" section on fitting
  inside a pipeline. Short, and it names the exact mistake this session's demo commits on purpose.
- [pandas User Guide: Windowing operations](https://pandas.pydata.org/docs/user_guide/window.html).
  `rolling`, `expanding`, and the `groupby().rolling()` form that keeps a window inside a unit,
  which is the difference between a feature and a fabrication.
- [`numpy.fft` reference](https://numpy.org/doc/stable/reference/routines.fft.html). What
  `rfft` and `rfftfreq` actually return, worth reading once before you trust a band-energy
  number, particularly the normalization conventions.
- [NIST/SEMATECH e-Handbook: Box-Cox transformations](https://www.itl.nist.gov/div898/handbook/eda/section3/eda336.htm).
  A careful treatment of the skew transforms named above, including how to choose lambda and what
  the transformed units mean, which is the part people skip.

## Assignment

A4, "Feature pipeline + dataset versioning," is released this session (Wednesday 16 September
2026) and is due roughly one week later. It asks you to engineer per-unit time-series features
for C-MAPSS (or a documented run-to-failure fallback), wrap scaling in a leakage-safe `Pipeline`
fit on training units only, and quantify the RMSE cost of a leaky variant against the correct
one, before L8 adds dataset versioning with DVC.

One warning drawn directly from this session's demo, since the assignment asks you to quantify a
leak: **do not treat a small measured gap as a failed experiment.** Report what you measure,
including a gap of zero, and say which model you measured it with and why that model would or
would not be sensitive to it. A report that says "the leak cost 0.002 cycles under Ridge, and
0.35 under k-nearest-neighbours, because the latter is a pure distance computation" is a better
answer than one that hunts for a configuration where the number looks alarming.

The full spec and rubric are in [A4](../../course/assignments/a04.md); this paragraph is a
pointer, not the rubric.
