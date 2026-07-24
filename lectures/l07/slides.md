---
marp: true
theme: course
paginate: true
header: "06-763 · L7"
footer: "Systems & Toolchains for AI in Engineering"
---

<!-- _class: title -->

# L7 · Features for time-series & physical data

## Week 4 · Data Systems

**Systems & Toolchains for AI in Engineering**

---

## Roadmap

1. Why this matters: where meaning gets lost
2. Time-series features from a per-unit trajectory
3. Physical and domain features
4. Scaling, encoding, and fitting on train only
5. A leakage-safe pipeline
6. Live demo: the leak a scaler can hide

<!-- 110 min. Budget roughly 15 / 20 / 15 / 20 / 10 / 20 demo, slack for questions.
     C-MAPSS FD001: 100 engines, run-to-failure, 21 sensors + 3 settings.
     If running long, cut the spectral-features slides, not the demo. -->

---

<!-- _class: section -->

# Why this matters

---

## A feature is a translation

Physical measurement in. A number a model
can multiply out.

Feels mechanical. That's exactly why it's
where meaning goes missing unnoticed.

---

## Nothing crashes when it goes wrong

Wrong units. A leaked statistic. A raw value
with no physical context.

The pipeline still runs. The model still trains.
Predictions look exactly as plausible.

---

## The clearest illustration isn't ML at all

Feature engineering has always meant turning
physical quantities into numbers a system consumes.

The consumer used to be a guidance algorithm.

---

## The second failure: leakage

Quieter. No units mismatch required.

A statistic computed to describe "training data"
quietly peeked at "data I'll be judged on."

---

## The question that decides everything

Every transform, a mean, a std, a category list,
is a statistic computed over **some set of rows**.

Which rows, is the whole question.

---

<!-- _class: section -->

# Time-series features
## from a per-unit trajectory

---

## This session's dataset

**NASA C-MAPSS**: simulated turbofan engines,
run-to-failure, one row per engine per cycle.

21 sensors + 3 operating settings.
Failure cycle known in train, withheld in test.

[Saxena et al., PHM 2008](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/)

---

## The structural rule

Every feature must respect: data is
**grouped by engine**, **ordered by cycle**.

Get the grouping wrong, and you fabricate
a feature without an error ever firing.

---

## The vocabulary: lag & difference

**Lag**: `sensor.shift(k)`, what was this doing
k steps ago.

**Difference**: `sensor.diff()`, how much did
it change since last cycle.

---

## The vocabulary: rolling & expanding

**Rolling** mean/std/min/max: smooths noise,
surfaces trend. Window length is a real choice.

**Expanding**: an all-history-so-far statistic,
no fixed length.

---

## The vocabulary: rate-of-change & time-since-event

**Rate-of-change**: a difference, normalized by
elapsed time.

**Time-since-event**: cycles since a condition
last held, exactly what an alarm model needs.

---

## Always inside a group

```python
g = df.groupby('unit', group_keys=False)
df['sensor4_roll_mean_5'] = (
    g['sensor4'].transform(lambda x: x.rolling(5).mean())
)
```

---

## The pitfall: forgetting to group

Roll across the boundary between engine 7's
last cycle and engine 8's first, and pandas
**will not complain.**

The feature just tells the model engine 8
started life mid-degradation. Borrowed from nowhere.

---

## Resampling irregular data

C-MAPSS is a clean, regular grid. Real sensors
often aren't: recall the Intel Lab motes (L3),
~31s cadence, unpredictable dropouts.

Resample to a fixed cadence; choose a policy
for the gap: forward-fill, interpolate, or leave null.

---

## The policy is itself a feature decision

Forward-filling a dropout invents continuity
that wasn't there.

A model that never sees the gap can't learn
that dropouts predict anything.

---

<!-- _class: section -->

# Physical and
## domain features

---

## Dimensionless groups

Ratios engineered to be independent of scale:
Reynolds number, power factor.

Collapse a nuisance dimension instead of asking
the model to learn it away from raw values.

---

## Energy & power features

Usually **derived**, not measured: kinetic energy
from shaft speed, specific power from pressure
ratio and mass flow.

Grounded in a known physical law, not a
coincidental correlation.

---

## Calibration corrections

A channel's raw output degrades over an
instrument's lifetime (L1's drift argument, again).

The correction belongs in the pipeline,
applied consistently, not patched in after.

---

## Unit consistency

The discipline tying all of this together.

Not a habit of careful people.
An engineering requirement.

---

## Case: a $327 million unit mismatch

**Mars Climate Orbiter**, lost 23 September 1999
entering Mars orbit.

Root cause: thruster impulse computed in
**pound-seconds**. Navigation expected **newton-seconds**.

---

## The conversion never happened

Not at any step. Not by any process.
For the entire cruise phase.

Small errors accumulated for months.

---

## The result

Planned altitude: 140–150 km.
Actual course: ~57 km.

Believed to have burned up or been ejected
into solar orbit.

[Mishap Investigation Board report](https://llis.nasa.gov/llis_lib/pdf/1009464main1_0641-mr.pdf)

---

## The mechanism is a feature engineering failure

A physical quantity, computed correctly in one
team's units, consumed by a system expecting another.

Nothing marked which convention the number was in.
Both are just a float.

---

## What a practitioner should take from this

Never let a column imply its own units.

`thrust_lbf`, not `thrust`. Assert the unit at
every interface between systems or teams.

---

## Spectral features

Vibration/acoustic data: the information isn't
in the level, it's in **which frequencies** carry energy.

**FFT** decomposes a windowed signal into
frequency components.

---

## Band energy

```python
def band_energy(signal, fs, f_lo, f_hi):
    freqs = np.fft.rfftfreq(len(signal), d=1/fs)
    spectrum = np.abs(np.fft.rfft(signal)) ** 2
    return spectrum[(freqs >= f_lo) & (freqs <= f_hi)].sum()
```

Which bands matter is a physical judgment
(bearing geometry, shaft speed). The transform is 3 lines.

---

<!-- _class: section -->

# Scaling, encoding, and
## fitting on train only

---

## Four ways to scale

| Method | Use when |
|---|---|
| Standardize | roughly symmetric, no natural bound |
| Min-max | need a fixed bounded range |
| Robust (median/IQR) | heavy-tailed outliers, fault spikes |
| Log / Box-Cox | naturally skewed physical quantities |

---

## Categorical encoding

One-hot or target encoding for an equipment ID
or an operating regime.

Same idea, non-numeric columns. The encoding
determines generalization to an unseen regime.

---

## Every transform is fit from data

A mean. A standard deviation. A Box-Cox lambda.
A category list.

Every one is a statistic. Every one can leak.

---

## The rule, stated once

> Fit every transform on the training split only.
> Apply the already-fitted transform to
> validation/test, unchanged.

A statistic computed with test rows included
has already seen something it shouldn't.

---

## Today's demo tests this directly

`StandardScaler` fit on **training engines only**
vs. the same scaler fit on **train + test combined**.

Compare RUL error.

---

## The honest result

The gap is often **small**. Sometimes near zero.

That's not a broken demo. It's the more
useful version of the lesson.

---

## Why the gap can be small

Plain linear regression is scale-**invariant**:
would show **zero** difference, always.

`Ridge` isn't (its penalty acts on coefficients),
so it shows a real, if modest, effect here.

---

## The pitfall: gap size isn't the point

Depends on your model's scale-sensitivity,
and on how different train/test really are.

Two samples of the same simulated regime
differ less than a real new deployment site will.

---

## Fit on train only, on principle

You cannot know in advance which model,
which dataset, which year, is the one
where the shortcut costs you.

---

<!-- _class: section -->

# A leakage-safe
## pipeline

---

## `Pipeline` and `ColumnTransformer`

Not for convenience. For making the rule
**structurally hard to break**.

`pipeline.fit(X_train, y_train)`: every step fits
using only what you handed it.

---

## No path back to the leak

```python
pipeline = Pipeline([
    ('scale', StandardScaler()),
    ('model', Ridge(alpha=10.0)),
]).fit(X_train, y_train)

pipeline.predict(X_test)   # only ever .transform()'d
```

No `.fit()` call anywhere has `X_test` in scope.

---

## Persist the whole pipeline

`joblib.dump(pipeline, ...)` saves weights **and**
every transform's fitted statistics, together.

Reload it a month later: exact same predictions.
Not a script's best attempt at reconstructing them.

---

## Feature stores (concept, not built here)

Centralize feature **definitions** so training
and serving compute the same feature the same way.

A well-built `Pipeline` already gives you this,
at the scale of one project.

---

<!-- _class: section -->

# Where this
## pushes back

---

## More features isn't more signal

A hundred engines, a few hundred generated
lag/rolling/delta columns: a recipe for
overfitting the training fleet.

---

## Automated extraction raises the stakes

[tsfresh](https://tsfresh.readthedocs.io/) can generate hundreds of
candidate features from one signal, one call.

Test enough candidates against one target,
some correlate **by chance alone**.

---

## A clipped RUL target is an assumption

Capping at 125 cycles assumes health is
roughly constant, then declines late.

Reasonable here. Not universal:
a sudden-fault mode would break it.

---

## Transforms complicate the number you report

Predict log-RUL, and RMSE in that space
isn't cycles until you exponentiate back.

Easy to report a wrong number that
looks exactly like a right one.

---

## A safe pipeline defends one leak, not every leak

Fitting on the training fold stops **this**
session's bug.

It does nothing about a row-level split
that puts cycle 150 in train, 151 in test.

---

## That's next session

No `Pipeline` catches a split-level leak:
the split happens before the pipeline
ever sees the data.

L8: the full leakage taxonomy, grouped
and temporal splits.

---

## What a practitioner should take from this

Fewer features you can explain physically >
many you generated and hope correlate.

Fit inside a `Pipeline`, on the training fold,
as a structural habit, not a remembered rule.

---

<!-- _class: demo -->

# Demo

## `l07-features.ipynb`

Rolling/delta/rate-of-change features on C-MAPSS FD001.
`Ridge` RUL model, two scalers.

---

## What to watch

- The gap between train-only and combined scaler fits
- Why `Ridge`, not plain linear regression, is doing the comparing
- The `Pipeline` saved with `joblib`, reloaded, reproduces itself exactly

---

## Recap

- A feature translates physical measurement into a model input, silently, if you let it
- Unit consistency is an engineering requirement (Mars Climate Orbiter: $327M)
- Every transform is a statistic; fit it on the training split only
- The leak's *size* isn't the lesson: fit-on-train-only is a principle, not a case-by-case check
- `Pipeline`/`ColumnTransformer` make the rule structural, not just remembered

---

## Next

**Assignment** A4 released today, due ~1 week
**Reading** scikit-learn Pipelines & preprocessing docs; Saxena et al. 2008
**L8** Same C-MAPSS fleet: the full leakage taxonomy, correct
grouped/temporal splits, and versioning the pipeline with DVC

Full notes, with all sources: `lectures/l07/notes.md`
