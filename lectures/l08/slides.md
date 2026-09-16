---
marp: true
theme: course
paginate: true
header: "06-763 / L8"
footer: "Systems and Toolchains for AI Engineers"
---

<!-- _class: title -->

# Lecture 8: The machine learning workflow I, time series

## Week 4, Machine learning and deep learning

**Systems and Toolchains for AI Engineers**

<!--
Budget, 90 minutes: opening 5, supervised 6, forecastable 10, baselines 11,
models 9, evaluation 10, demo 20, residuals 5, limitations 4, close 3. About 83.
Abort order if running long: window-features slide, look-ahead/survivorship slide,
the second residual slide.
-->

---

## What today is about

Lecture 7 built a table and fitted a model. **It never asked whether the model was any good.**

Today:

1. Time series as **supervised learning**, with a **horizon**
2. What makes a series **forecastable** at all
3. **Baselines**: better than what?
4. **Direct** and **recursive** forecasts
5. **Evaluating on time**, then the demo
6. **Residuals** as a detector, and the limits

---

## Why this matters

Fit a one-step model on reactor pressure: predictions hug the data, **R-squared near 0.99**.

- "nothing changes in 3 minutes" is already close to right (Lecture 7)
- most of that score belongs to the free guess
- an operator needs **30 to 60 minutes** of warning, not 3

A model is worth keeping only if it beats the free guesses, **at the horizon somebody needs, on data it never saw.**

---

## Why this matters, beyond the plant

| field | the forecast | the free guess that is hard to beat |
|---|---|---|
| process plant | pressure in 30 min | pressure now |
| electricity | load tomorrow at 6 PM | load today at 6 PM |
| finance | price tomorrow | price today |
| weather | temperature tomorrow | the seasonal average |

Same three questions everywhere: **how far ahead, better than what, scored how.**

---

<!-- _class: section -->

# Time series as supervised learning

---

## Supervised learning

<div class="definition">

**Supervised learning**: fit a function from **features** (what you know) to a **target** (what you want), using rows where both are known.

</div>

- Lecture 7 already did this: `lstsq` on a design matrix
- scikit-learn: every model has `fit(X, y)` and `predict(X)`
- linear model, random forest, boosting: **swap in one line**

---

## Supervised learning, two kinds of number

<div class="definition">

**Parameter**: chosen by the fit (the ARX `a` and `b`). **Hyperparameter**: chosen by you before the fit (how many lags, how much penalty).

</div>

- pick hyperparameters by peeking at test data, and **the test data has been used for fitting**
- **held-out score**: the error on rows the fit never saw. Lecture 7 never computed one.
- honest only if the held-out rows **look like the future the model will face**, which is the hard part for a time series

---

## Supervised learning, the horizon

<div class="definition">

**Forecast horizon** $h$: how many samples ahead the model predicts. At 3 minutes per sample, $h = 10$ is thirty minutes.

</div>

```python
cols = {f"y[t-{k}]": pl.col("xmeas_7").shift(k).over(RUN) for k in range(10)}
cols["target"] = pl.col("xmeas_7").shift(-h).over(RUN)   # the only new line
```

`.over(RUN)`: Lecture 7's run-boundary rule, still required.

---

## Supervised learning, what is known at time t

| known at $t$ | not known at $t$ |
|---|---|
| the channel's own past | its future (that is the target) |
| valve positions **now** | valve positions **later** |
| a written setpoint schedule | where the operator will move it |
| tomorrow's **weather forecast** | tomorrow's weather |

Anything in the right column is **leakage**, stretched across $h$ rows.

---

<!-- _class: section -->

# What makes a series forecastable

---

## Forecastability, autocorrelation

<div class="definition">

**Autocorrelation** at lag $k$: the correlation between a series and itself shifted by $k$ samples. Near 1, rows $k$ apart are nearly the same.

</div>

- plot it against $k$: the **ACF**
- tells you **before fitting** whether the past can help
- `statsmodels.graphics.tsaplots.plot_acf`, or three lines of numpy

---

## Forecastability, three kinds of series

![w:1020](figures/three-series.png)

<span class="source">Pressure and separator level: run 1, <a href="https://doi.org/10.7910/DVN/6C3JR1">Rieth et al. (2017)</a>. Random walk: simulated. <code>figures/make_figures.py</code></span>

<!--
speaker: ask the room to say, for each column, what they would guess for the next sample.
-->

---

## Forecastability, what each one calls for

| series | lag-1 ACF | best simple forecast |
|---|---|---|
| reactor pressure | 0.94, decays by ~75 min | recent past, then the mean |
| separator level | 0.02 | **the mean**: the controller removes every deviation |
| random walk (a price) | 0.98, stays high | **the last value** |
| its changes (returns) | -0.01 | nothing beats zero |

**7 of 22** continuous TEP channels look like separator level: **white noise**.

---

## Forecastability, stationarity

<div class="definition">

**Stationary**: mean, spread and autocorrelation do not change over time. A plant at an operating point is roughly stationary; a random walk is not.

</div>

- every model here assumes the future looks like the past
- fix for a drifting level: **differencing**, model `y[t] - y[t-1]`
- finance: prices to **returns**; the "I" in **ARIMA**

---

## Forecastability, trend and seasonality

- **Trend**: a sustained change in level (demand growing year on year)
- **Seasonality**: a repeating calendar pattern (load peaks every weekday evening)
- Standard fixes: seasonal differencing, calendar features

A plant at an operating point has **mostly neither**.
A daily cycle there usually has a measured cause (cooling water temperature): **put that column in the table, not the hour.**

<span class="source"><a href="https://otexts.com/fpp3/stationarity.html">Hyndman and Athanasopoulos, FPP3, section 9.1</a></span>

---

## Forecastability, a question

<div class="clicker" data-tag="l08-random-walk" data-seconds="45" data-answer="B" data-hint="Look at the random walk column on the table three slides back. What is its best simple forecast?" data-why="B. A random walk's changes are white noise, so the last value is already close to the best possible forecast. Losing to persistence there says the price is hard to predict, not that the code is wrong." data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**A stock price behaves like a random walk. On a held-out year, persistence beats your fitted model. What is the most likely explanation?**

<ol class="clicker-opts">
<li>The model has a bug</li>
<li>The price changes are close to unpredictable</li>
<li>The model needs more lags</li>
<li>Persistence is the wrong baseline for prices</li>
</ol>

</div>
<aside class="clicker-panel">
<img src="figures/clicker-qr.png" alt="QR code linking to the vote page">
<div class="clicker-url">clicker.f26-06763.workers.dev</div>
<button class="clicker-start">Start voting</button>
<div class="clicker-timer">45</div>
<div class="clicker-count">no votes yet</div>
</aside>
</div>

<!--
Tests whether a random walk is read as "persistence is near optimal". A tempts students
who assume a loss to a baseline means broken code; D tempts those who think the mean
should be used, which is useless on a drifting level.
-->

---

<!-- _class: section -->

# Baselines and skill

---

## Baselines

<div class="definition">

**Persistence** (the naive forecast): `y[t+h] = y[t]`. Lecture 7 used it without the name.

</div>

| baseline | forecast | where it is strong |
|---|---|---|
| persistence | the last value | short horizons, random walks |
| mean | the training average | long horizons, white noise |
| seasonal naive | the value one season ago | load, retail |
| drift | the average past change, extended | trending series |

<span class="source"><a href="https://otexts.com/fpp3/simple-methods.html">FPP3, section 5.2</a></span>

---

## Baselines, which one wins

For a stationary series with spread $\sigma$ and autocorrelation $\rho_h$:

$$\text{RMSE}_{\text{mean}} = \sigma \qquad \text{RMSE}_{\text{persistence}}(h) = \sigma\sqrt{2(1-\rho_h)}$$

- persistence wins **exactly when $\rho_h > 0.5$**
- white noise ($\rho_h = 0$): persistence is $\sqrt{2} = 1.41\times$ worse; separator level measures **1.415**
- negative $\rho_h$: persistence bets on the wrong side of the swing

<!--
speaker: the ACF you just looked at tells you the crossover before any fitting.
-->

---

## Baselines, reactor pressure

![w:880](figures/skill-horizon.png)

<span class="source">Train runs 1 to 300, test runs 401 to 500. Test standard deviation 7.51 kPa. <code>figures/make_figures.py</code></span>

---

## Baselines, reactor pressure, the numbers

| horizon | persistence | mean | direct model | skill |
|---|---|---|---|---|
| 3 min | **1.92** | 7.51 | 1.83 | 5 % |
| 30 min | 5.82 | 7.57 | 5.02 | 14 % |
| 45 min | 7.39 | 7.59 | 5.87 | **21 %** |
| 120 min | 12.29 | **7.65** | 7.17 | 6 % |

RMSE in kPa. The model earns most **where neither free guess is good**.

---

## Baselines, skill scores

<div class="definition">

**Skill score**: $1 - \text{RMSE}_{\text{model}} / \text{RMSE}_{\text{reference}}$. Zero is no better than the reference; negative is worse.

</div>

- reference = the **better** baseline at that horizon
- **MASE**: mean absolute error divided by the in-sample one-step naive error; below 1 beats naive, unitless, averages across series
- also report **kPa**: an operator can judge 5.0 kPa, not 0.14

<span class="source"><a href="https://robjhyndman.com/papers/mase.pdf">Hyndman and Koehler (2006)</a>, author's copy</span>

---

## Baselines, a question

<div class="clicker" data-tag="l08-r2-baseline" data-seconds="45" data-answer="C" data-hint="Which free forecast is strongest three minutes out?" data-why="C. At one step, persistence is already within 1.92 kPa on pressure, so an R-squared near 0.99 is mostly persistence. The model is only as good as its margin over that." data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**Your one-step pressure model scores R-squared 0.99 on held-out runs. What should you compare it with first?**

<ol class="clicker-opts">
<li>The R-squared on the training runs</li>
<li>A larger model with more lags</li>
<li>Persistence at the same horizon</li>
<li>The mean of the training runs</li>
</ol>

</div>
<aside class="clicker-panel">
<img src="figures/clicker-qr.png" alt="QR code linking to the vote page">
<div class="clicker-url">clicker.f26-06763.workers.dev</div>
<button class="clicker-start">Start voting</button>
<div class="clicker-timer">45</div>
<div class="clicker-count">no votes yet</div>
</aside>
</div>

<!--
D is a real baseline but the weak one at 3 minutes (7.51 against 1.92), which is the point.
-->

---

## Baselines, case study: Meese and Rogoff

Exchange-rate models of the 1970s (money supply, interest rates, trade balances):

- forecast 1 to 12 months ahead, re-fit with **rolling regressions** (only past data)
- reference: a **random walk**
- "a random walk model would have **outperformed all the other models**"
- also lost: univariate models, a VAR, optimal combinations of the forecasts

They fitted history well. **Only the baseline comparison showed they could not forecast.**

<span class="source"><a href="https://www.federalreserve.gov/pubs/ifdp/1981/184/ifdp184.pdf">Meese and Rogoff, Fed IFDP 184 (1981)</a>, the working paper of the 1983 J. Int. Econ. article</span>

---

## Baselines, case study: the M4 competition

100,000 real series, every team scored the same way. Benchmarks included **Naïve2** and **Comb** (three simple exponential smoothers).

- 12 of the 17 most accurate methods: combinations of mostly statistical methods
- the six pure ML methods: **none beat Comb, one beat Naïve2**
- best surprise: a statistical/ML **hybrid**, about 10 % better than Comb

<span class="source"><a href="https://econpapers.repec.org/RePEc:eee:intfor:v:34:y:2018:i:4:p:802-808">Makridakis, Spiliotis and Assimakopoulos (2018), IJF 34, abstract</a></span>

<!--
speaker, the takeaway for both case studies: report persistence and the mean at every
horizon you claim, beat the better one or say you did not, and if you did not, ship the
baseline. It is cheap, cannot overfit, and needs no maintenance.
-->

---

<!-- _class: section -->

# Model families and multi-step strategies

---

## Model families

| route | examples | strengths |
|---|---|---|
| statistics and control | AR, ARX, **ARIMA**, state space | small, well understood, standard errors |
| reduction to regression | lag table + ridge, forest, boosting | any regressor, many inputs, nonlinear |

- they meet at the linear model: ridge on 10 lags **is** an AR(10)
- `statsmodels` for the first route, scikit-learn and `skforecast` for the second

<span class="source"><a href="https://www.statsmodels.org/stable/tsa.html">statsmodels tsa</a> · <a href="https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html">scikit-learn lagged features</a></span>

---

## Model families, ridge and scaling

- lag columns are near-copies (0.996 on pressure, Lecture 7)
- **ridge** penalizes coefficient size, which stabilizes the fit
- the penalty is unit-dependent: **scaling now changes the answer**
- fit the scaler on training rows only, so put it in the pipeline

```python
model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
model.fit(X_train, y_train)     # scaler sees training rows only
```

---

## Multi-step strategies

<div class="definition">

**Direct**: one model per horizon, trained on `y[t+h]`. **Recursive**: one model for `y[t+1]`, applied $h$ times, feeding each prediction back in.

</div>

- recursive: one model, the whole path, **but it runs on its own guesses**
- errors compound: this is "running free" from Lecture 7
- recursive with valves needs **future** valve positions, which are not known

---

## Multi-step strategies, measured

| horizon | direct | recursive | mean |
|---|---|---|---|
| 3 min | 1.83 | 1.83 | 7.51 |
| 30 min | 5.02 | 5.19 | 7.57 |
| 60 min | 6.51 | 7.08 | 7.61 |
| 120 min | **7.17** | 8.11 | 7.65 |

Same 10 lags, same ridge. At two hours, **recursive is worse than the mean**.
Adding the 11 current valve positions to direct: 5.02 to **4.71** kPa at 30 min.

---

## Multi-step strategies, not a law

On the 111 series of the NN5 competition, **recursive beat direct**.

- best there: **multi-output** strategies that predict the whole horizon at once
- seasonal adjustment helped in 38 of 39 models
- so: **measure both on your data**

<span class="source"><a href="https://arxiv.org/abs/1108.3259">Taieb, Bontempi, Atiya and Sorjamaa (2012)</a>, arXiv preprint</span>

---

## Multi-step strategies, window features

Lecture 7 showed `rolling_mean`. The open question was the **window length**.

| window | follows | costs |
|---|---|---|
| short | the latest move | carries the noise |
| long | the level | lags behind a change |

The horizon is the criterion: try two or three lengths, **keep what lowers the held-out error at your $h$.**

<!-- speaker: first slide to cut if running long -->

---

<!-- _class: section -->

# Evaluating on time

---

## Evaluating on time, why shuffling leaks

- **K-fold**: shuffle rows, hold out a fifth, repeat
- neighbouring rows are near-copies (the ACF)
- shuffled, each test row has neighbours **before and after** it in training
- a flexible model recalls them

The score measures **how densely you sampled**, not how well you forecast. Lecture 7 named this **train-test contamination**.

---

## Evaluating on time, measured

![w:840](figures/leaky-split.png)

<span class="source">One run at a time, $h = 10$, pressure lags and valves, mean of runs 1 to 10. <code>figures/make_figures.py</code></span>

---

## Evaluating on time, what the bars say

- shuffled: forest **4.32**, ridge 4.82, both far below persistence (~6.1)
- time-ordered: forest **6.92**, ridge 6.67, **both worse than persistence**
- one says "ship it", the other says "don't"

**The boundary**: pooled over 200 independent runs, ridge scores 4.74 shuffled and 4.71 by run. K-fold is valid for a purely autoregressive model with uncorrelated errors.
Shuffling bites hardest on **one short series, a flexible model, correlated errors**.

<span class="source"><a href="https://robjhyndman.com/papers/cv-wp.pdf">Bergmeir, Hyndman and Koo (2018)</a>, author's copy</span>

---

## Evaluating on time, rolling origin

<div class="definition">

**Rolling origin** (forward chaining, backtesting): train up to a cutoff, test on the block after it, move the cutoff forward, repeat.

</div>

![w:860](figures/rolling-origin.png)

---

## Evaluating on time, the gap

- a row at $t$ has target `y[t+h]`
- the last training rows have targets **inside** the test block
- fix: skip at least $h$ samples

```python
from sklearn.model_selection import TimeSeriesSplit
cv = TimeSeriesSplit(n_splits=5, gap=h)
```

Many series (runs, meters, stocks): **hold whole series out**, as with runs 401 to 500.

<span class="source"><a href="https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html"><code>TimeSeriesSplit</code>, the <code>gap</code> parameter</a></span>

---

## Evaluating on time, a question

<div class="clicker" data-tag="l08-gap" data-seconds="60" data-answer="D" data-hint="Row t has target y[t+10]. Which t put that target at 301 or later?" data-why="D. A row at t has target y[t+10], which reaches sample 301 or later when t is at least 291. Those ten training targets sit inside the test block, so the gap must be at least h = 10." data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**Horizon $h = 10$. Training rows end at sample 300; test rows start at 301, with no gap. Which training rows have targets inside the test block?**

<ol class="clicker-opts">
<li>None of them</li>
<li>Only row 300</li>
<li>All of them</li>
<li>Rows 291 to 300</li>
</ol>

</div>
<aside class="clicker-panel">
<img src="figures/clicker-qr.png" alt="QR code linking to the vote page">
<div class="clicker-url">clicker.f26-06763.workers.dev</div>
<button class="clicker-start">Start voting</button>
<div class="clicker-timer">60</div>
<div class="clicker-count">no votes yet</div>
</aside>
</div>

<!--
B tempts students who picture h = 1. A tempts students who think a time-ordered split is
automatically clean.
-->

---

## Evaluating on time, names from finance

| bias | in a backtest | in a plant |
|---|---|---|
| **look-ahead** | using data not available on the decision date | a shuffled split, a future valve |
| **survivorship** | testing on today's index members only | keeping only the runs where nothing went wrong |

Both inflate the score. Neither raises an error.

<!-- speaker: second slide to cut if running long -->

---

<!-- _class: demo -->

# Demo

## `l08-forecasting.ipynb`

Reactor pressure, 500 runs. Build the horizon table, score persistence and the mean,
fit direct and recursive, then shuffle and don't.

<!--
20 minutes. Pause at "stop and predict" before the baseline table prints. The last
cell takes about 15 seconds.
-->

---

<!-- _class: section -->

# Residuals: diagnosis and detection

<!--
speaker, say this over the divider: a residual is measurement minus prediction. A good
forecaster leaves white noise, so plot the residual ACF. A spike at one lag means a missing
feature at that lag; a slow decay means a missing input. The notes carry the details.
-->

---

## Residuals, as a detector

<div class="definition">

**Anomaly detection**: flag observations that do not fit normal data. A residual detector alarms when the forecast error leaves its normal range.

</div>

1. fit on normal data
2. set the threshold on **other** normal data (99th percentile of the absolute residual)
3. alarm when a new residual exceeds it

Pressure, one step: residual sd **1.70 kPa**, threshold **4.38 kPa**. No fault examples needed.

---

## Residuals, false alarms

<div class="definition">

**False-alarm rate**: how often it fires on normal data. **Detection delay**: time from fault onset to first alarm. Lowering one raises the other.

</div>

- 99th percentile means **1 %** of normal samples exceed it
- 480 samples a day, so **4.8 false alarms a day**
- require 3 in a row: **0.01 a day**, at the cost of delay

---

## Residuals, one fault

![w:840](figures/residual-detector.png)

<span class="source">Fault 1 (A/C feed ratio step), run 1, faulty training file of <a href="https://doi.org/10.7910/DVN/6C3JR1">Rieth et al. (2017)</a>. 3-in-a-row alarm 45 min after onset.</span>

---

## Residuals, what the fault shows

- pressure swings **100 kPa**; the residual only 5 to 10: it reacts to **surprise**, not distance
- the residual returns to the band while the fault is **still there**: the controller compensated
- across 20 faults on this channel: alarm within an hour for **1, 7, 12**; never for **2, 3, 4, 9, 10, 11, 15, 16**

One channel sees only what that channel sees.

<!-- speaker: third cut if running long -->

---

## Limitations, when a forecaster fails

| failure | what happens | what helps |
|---|---|---|
| **regime change** | new grade, catalyst, market | watch residuals, retrain |
| **feedback** | controller (Lecture 7), traders acting on forecasts | log setpoints, retrain after retuning |
| **unseen faults** | extrapolation from a regime never trained on | detect, do not forecast through |
| **horizon ceiling** | pressure skill 6 % at two hours | the ACF shows it before fitting |

Each one returns a **confident number**, not an error.

---

## Recap

- A forecast is supervised learning with a **horizon**: features at $t$, target at $t+h$
- The **ACF** says whether the past can help; white noise and random walks have simple best forecasts
- Beat the **better** of persistence and the mean, at every $h$; persistence wins while $\rho_h > 0.5$
- **Direct** beat **recursive** on pressure; measure both
- **TimeSeriesSplit(gap=h)**, or split by series; a shuffled score flattered two models past persistence
- Residuals are a detector; the threshold sets the **false alarms**

---

## Standings

Nicknames only. Everyone who skipped one still counted in every bar you saw.

<div class="clicker-leaderboard"
     data-read="https://clicker.f26-06763.workers.dev"
     data-top="8"
     data-hours="6"
     data-title="Standings"></div>

---

## Next

**Assignment 4** is released today, due **2026-09-28**: an h-step forecaster for stripper temperature
**Practice module** for this session, for participation credit
**Reading** FPP3 chapter 5, <https://otexts.com/fpp3/toolbox.html>

Full notes, with all sources: `lectures/l08/notes.md`

<script src="clicker-slide.js"></script>
