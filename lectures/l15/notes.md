# Lecture 15: Uncertainty quantification, Bayesian optimization and active learning

:::{admonition} At a glance
:class: tip

- **Session** Lecture 15, Week 7
- **Arc** Machine learning and deep learning
- **Slides** <a href="../../slides/l15/">Deck for this session</a>
- **Practice** <a href="../../game/#/l15">Practice module for this session</a>
- **Demo** [`l15-uq-bayesopt.ipynb`](l15-uq-bayesopt.ipynb), prediction intervals and their
  calibration on the concrete strength dataset, then a Bayesian optimization of a mix design
- **Tools** scikit-learn for the Gaussian process and the networks, Optuna for Bayesian
  optimization
:::

## Why this matters

A concrete cylinder is tested for strength after **28 days** of curing.

- Every new mix you want to try costs a month of waiting, plus the materials and the lab.
- [Lecture 9](../l09/notes.md) fitted a Gaussian process (GP) to the concrete strength dataset. It
  predicts a strength **and** an uncertainty for any mix.
- So the model can choose which mixes to cast next. Whether that works depends on whether its
  uncertainty is right.

Two numbers from this session:

- On the strongest mixes, held out from training, one popular method's "95%" intervals contain
  the true strength only **70%** of the time.
- An optimizer searching the GP's predictions finds a mix it scores at **91.6 ± 18.0 MPa**. The
  strongest specimen in the whole dataset is 82.6 MPa.

This session: measure uncertainty, check it, then spend it on choosing experiments.

## Learning objectives

By the end of this session you should be able to:

- Produce and calibrate predictive uncertainty, separating aleatoric from epistemic.
- Explain the Bayesian-optimization loop and the role of the surrogate + acquisition.
- Choose and compare acquisition functions for exploration vs. exploitation.
- Set up an active-learning loop that chooses the next expensive query.

## Two kinds of uncertainty

```{index} aleatoric uncertainty, epistemic uncertainty
```

:::{admonition} Definition: aleatoric and epistemic uncertainty
:class: tip
**Aleatoric** uncertainty is the scatter in the data itself, which no amount of data removes.
**Epistemic** uncertainty is what the model does not know yet, which more data in the right place
reduces.
:::

```{figure} figures/aleatoric-epistemic.png
:alt: A Gaussian process fitted to noisy points on a smooth curve, with data from 0 to 0.35 and from 0.7 to 1 and a gap between. A wide light-blue band shows the total uncertainty and a narrower orange band the epistemic part only. Near the data the orange band is thin and the blue band stays wide, labeled near data the noise (aleatoric) remains. In the gap the orange band swells, labeled no data, epistemic uncertainty grows.
:width: 100%

Total uncertainty (blue) is aleatoric plus epistemic (orange). Only the epistemic part shrinks
with more data.
```

On the concrete strength dataset:

- **Aleatoric**: 19 settings (the same mix at the same age) were tested more than once, 53 rows
  in all. Their strengths scatter by **5.0 MPa** (pooled standard deviation). No model predicts
  better than that.
- The GP of Lecture 9 estimates the same thing on its own: its noise term, fitted to the
  training mixes, is **3.9 MPa**.
- **Epistemic**: the rest of the GP's predictive standard deviation. On test mixes like the
  training mixes it averages **3.2 MPa**. On the strongest mixes, held out (below), it
  averages **10.8 MPa**.
- Why the split matters: epistemic uncertainty tells you **where new data would help**.
  Bayesian optimization and active learning both use it.

## Three ways to get a prediction interval

```{index} deep ensemble, conformal prediction, exchangeability
```

A **prediction interval** is a range that should contain the true value with a stated
probability, for example 95%.

### The Gaussian process

- Lecture 9's GP returns a mean $\mu(x)$ and a standard deviation $\sigma(x)$ at every input.
- The 95% interval is $\mu(x) \pm 1.96\,\sigma(x)$, assuming the error is Gaussian.
- $\sigma$ includes both parts: the noise term (aleatoric) and the posterior spread
  (epistemic).

### A deep ensemble

:::{admonition} Definition: deep ensemble
:class: tip
A **deep ensemble** trains several networks that differ only in their random starting weights,
and uses the spread of their predictions as the uncertainty.
:::

- Here: five copies of Lecture 9's network (one hidden layer of 16 tanh units), seeds 0 to 4.
- The mean of the five is the prediction; their standard deviation is the spread.
- Where the data pin the function down, the networks agree. Where they do not, the networks
  disagree. So the spread measures **epistemic** uncertainty only.
- [Lakshminarayanan, Pritzel and Blundell (2017)](https://arxiv.org/abs/1612.01474) introduced
  the method; they also train each network to predict its own noise, which adds the aleatoric
  part. The spread alone does not.

### Split conformal prediction

:::{admonition} Definition: split conformal prediction
:class: tip
**Split conformal prediction** sets the interval width from the errors the model makes on a
held-out calibration set, with no assumption about their distribution.
:::

1. Split the training data into a **fitting** set and a **calibration** set (here by mix: 625
   and 210 rows).
2. Fit any model on the fitting set. Here, the mean of the five networks.
3. On the calibration set, compute the absolute errors $s_i = |y_i - \hat y(x_i)|$, for
   $i = 1, \dots, n$.
4. Take $q$, the $\lceil (n+1)(1-\alpha) \rceil / n$ quantile of the $s_i$.
5. The interval for a new input is $\hat y(x) \pm q$.

- **The guarantee**: if the calibration and test points are **exchangeable** (their order does not
  matter: drawn the same way from the same population), the interval contains the truth with
  probability at least $1 - \alpha$.
- It works around any model, and it needs no Gaussian assumption.
- The interval has the same width everywhere: it does not grow where the model is unsure.
- [Angelopoulos and Bates](https://arxiv.org/abs/2107.07511) give a gentle introduction.

## Is the uncertainty right? Calibration

```{index} calibration, reliability diagram, prediction interval coverage probability
```
```{index} see: PICP; prediction interval coverage probability
```
```{index} pair: failure mode; conformal prediction under covariate shift
```

:::{admonition} Definition: calibration
:class: tip
An uncertainty is **calibrated** when its stated probabilities match what happens: 95% intervals
contain the truth 95% of the time.
:::

The check is the **prediction interval coverage probability** (PICP), the fraction of test
points whose interval contains the true value:

$$
\text{PICP} = \frac{1}{N}\sum_{i=1}^{N} \mathbf{1}\big[\, y_i \in [\,L(x_i),\, U(x_i)\,] \big]
$$

- $L$ and $U$ are the lower and upper ends of the interval; $\mathbf{1}[\cdot]$ is 1 when the
  condition holds, 0 otherwise.
- A **reliability diagram** plots the PICP against the nominal level (10%, 20%, ..., 95%). On
  the diagonal: calibrated. Below it: **overconfident** (intervals too narrow). Above:
  underconfident.
- Coverage alone is not enough. An interval from 0 to 100 MPa always covers. Report the
  **width** too: the narrowest intervals that still cover.

### Two test sets

- **Grouped split**: Lecture 9's split, 20% of the mixes held out at random (195 rows).
- **Extrapolation split**: the 20% of mixes with the lowest water/cement ratio held out (265
  rows). These are the strongest mixes: 49.5 MPa on average, against 31.1 MPa for the mixes
  kept. A design loop pushes a surrogate exactly here.

```{figure} figures/calibration.png
:alt: Two reliability diagrams of observed coverage against nominal coverage. Left, grouped split: the Gaussian process and split conformal lines run along the diagonal, while the ensemble spread line falls well below it, reaching 0.76 at 0.95. Right, extrapolation split: all three lines fall below the diagonal; the Gaussian process reaches 0.89 at 0.95, the ensemble 0.86, and split conformal only 0.70.
:width: 100%

Observed against nominal coverage. Below the dashed line: overconfident.
```

| 95% intervals | Grouped: coverage | Grouped: width | Extrapolation: coverage | Extrapolation: width |
|---|---|---|---|---|
| Gaussian process | 95% | 20.4 MPa | 89% | 43.8 MPa |
| Ensemble spread | **76%** | 12.1 MPa | 86% | 30.9 MPa |
| Split conformal | 96% | 26.9 MPa | **70%** | 18.1 MPa |

- **Grouped split**: the GP and conformal are calibrated. The ensemble's spread is
  overconfident: it measures epistemic uncertainty only, and misses the 5 MPa of scatter.
- **Extrapolation split**: every method is overconfident.
  - The GP comes closest (89%), because its $\sigma$ grows away from the data: its intervals
    double in width.
  - Conformal falls to **70%**. Its width was set on calibration mixes that look like the
    training mixes. The strongest mixes are not exchangeable with them, so the guarantee no
    longer holds, and its constant width does not grow.

Set the nominal level and watch which test mixes fall outside their interval:

<div class="cw" data-widget="coverage" data-source="l15"></div>

```{figure} figures/intervals.png
:alt: Two panels of predicted against measured strength with 95% Gaussian-process intervals. Left, grouped split, 95% covered: points cluster on the diagonal with a few red misses. Right, extrapolation split, 89% covered: the points scatter widely, the intervals are long, and the red misses sit mostly at high measured strength, where the model predicts too low.
:width: 100%

The GP's 95% intervals on each test set. Red: the interval misses the measured strength.
```

:::{admonition} What a practitioner should take from this
:class: tip
- Check coverage on a test set that looks like where the model will be **used**, not only like
  where it was trained.
- An ensemble's spread is epistemic only. Add an estimate of the noise before calling it an
  interval.
- Conformal's guarantee is real, and it needs exchangeability. A design loop breaks that on
  purpose.
:::

## Bayesian optimization

```{index} Bayesian optimization, acquisition function, surrogate model, black-box optimization
```

### The problem

- Find the input $x$ (a mix design) that maximizes an **expensive** function $f(x)$ (the 28-day
  strength).
- No formula, no gradient: you can only evaluate $f$, a few dozen times at most. That is
  **black-box optimization**.
- A grid is hopeless: 10 levels of 4 ingredients is 10,000 mixes, 770 years of 28-day tests
  run one after another.

:::{admonition} Definition: Bayesian optimization (BO)
:class: tip
**Bayesian optimization** fits a probabilistic surrogate to the evaluations so far and uses an
**acquisition function** of its mean and uncertainty to choose the next point to evaluate.
:::

The loop:

<div class="flow" style="display:flex;gap:.4em;flex-wrap:wrap;align-items:center;justify-content:center;margin:.8em 0">
<span style="border:2px solid #5c5c5c;border-radius:8px;padding:.3em .7em">1. Fit a GP to the data so far</span> →
<span style="border:2px solid #5c5c5c;border-radius:8px;padding:.3em .7em">2. Maximize the acquisition</span> →
<span style="border:2px solid #5c5c5c;border-radius:8px;padding:.3em .7em">3. Evaluate f there</span> →
<span style="border:2px solid #5c5c5c;border-radius:8px;padding:.3em .7em">4. Add the result, repeat</span>
</div>

### Acquisition functions

```{index} expected improvement, upper confidence bound, probability of improvement, Thompson sampling
```
```{index} exploration-exploitation trade-off
```

Each acquisition trades **exploitation** (sample where the mean is high) against **exploration**
(sample where the uncertainty is high). With $f^*$ the best value found so far:

**Expected improvement (EI)**: how much, on average, the new point beats $f^*$:

$$
\text{EI}(x) =
\underbrace{\big(\mu(x) - f^*\big)\,\Phi(z)}_{\text{exploit: mean above the best}}
+ \underbrace{\sigma(x)\,\phi(z)}_{\text{explore: room to be better}},
\qquad z = \frac{\mu(x) - f^*}{\sigma(x)}
$$

- $\Phi$ is the standard normal cumulative distribution; $\phi$ its density.
- Large when the mean is above $f^*$, or when $\sigma$ is large, or both.

**Probability of improvement (PI)**: $\Phi(z)$, the chance of beating $f^*$ at all, by any margin.
It favors small sure gains, so it tends to stay near the best point.

**Upper confidence bound (UCB)**: $\mu(x) + \kappa\,\sigma(x)$. The weight $\kappa$ sets the
trade-off directly: large $\kappa$ explores.

**Thompson sampling**: draw one random function from the GP posterior, and evaluate where that
draw is highest. The randomness of the draw does the exploring.

### The loop on a test function

The test function is $g(x) = -(6x - 2)^2 \sin(12x - 4)$ on $[0, 1]$, the
[Forrester et al. (2008)](https://www.wiley.com/en-us/Engineering+Design+via+Surrogate+Modelling%3A+A+Practical+Guide-p-9780470060681)
benchmark turned into a maximization. Its global maximum is 6.02 at $x = 0.758$, with a
smaller peak near $x = 0.15$. Four starting points (0, 0.33, 0.66 and 1) all miss the big peak.

<div class="cw" data-widget="bo-loop" data-source="l15"></div>

```{figure} figures/acquisitions.png
:alt: Top, a Gaussian process fitted to five points of a test function with two peaks, with its 95% band, and three dashed vertical lines. Bottom, three scaled acquisition curves. Expected improvement peaks at x = 0.73, near the true global maximum; probability of improvement peaks at 0.67, right next to the best point found; the upper confidence bound with kappa = 3 peaks at 0.17, in a wide-band region far from the data.
:width: 100%

One GP state, three acquisitions, three different next experiments.
```

After 8 picks from the same start:

| Acquisition | Picks | Best found (true max 6.02) |
|---|---|---|
| EI | 0.63, 0.73, 0.78, 0.18, 0.76, ... | 6.02 (from the 5th pick) |
| PI | 0.66, 0.67, 0.68, 0.68, 0.69, ... 0.72 | 5.26 |
| UCB, $\kappa = 3$ | 0.59, 0.18, 0.78, 0.45, 0.73, 0.76, ... | 6.02 |

- **PI** creeps uphill from its best point in tiny steps: it exploits.
- **UCB** with $\kappa = 3$ checks the far side first: it explores, then finds the peak.
- **EI** balances the two, and gets there fastest here.

### On the concrete strength dataset: BO against random search

```{index} pair: failure mode; single-seed Bayesian optimization
```

The "lab" is a GP fitted to all 1,030 rows, which plays the role of the 28-day test.

- **Design**: cement, slag, water and superplasticizer (kg/m³), each within the 5th to 95th
  percentile of the 28-day mixes; the other ingredients fixed at their medians.
- **Goal**: the strongest mix at 28 days.
- **BO**: 5 random mixes, then 20 chosen by EI (a GP refitted after every test). **Random
  search**: 25 random mixes. Each gets **30 seeds**, because one run of either is luck.

```{figure} figures/bo-vs-random.png
:alt: Best strength found so far against the number of mixes tested, from 1 to 25, with the median and the 25th to 75th percentile band over 30 seeds. Bayesian optimization in blue rises steeply after the five random starting mixes, passes 87 MPa by the 10th mix, and reaches the red dashed line at 91.4 MPa labeled the emulator's best. Random search in gray climbs slowly to about 81 MPa.
:width: 100%

Median and middle 50% over 30 seeds.
```

| After the same 25 tests | BO (EI) | Random search |
|---|---|---|
| Median best strength | **91.3 MPa** | 81.1 MPa |
| Seeds within 1 MPa of the emulator's best | **29 of 30** (median: 16 tests) | 0 of 30 |

**Now check that answer with the uncertainty.** The emulator's best mix (472 kg/m³ cement, 235
slag, 162 water, 11 superplasticizer) is predicted at **91.6 ± 18.0 MPa** (95%). The strongest
specimen in the data is **82.6 MPa**.

- The optimizer went where the emulator is most **optimistic**, at the corner of the design box,
  far from any mix ever tested. The ±18 MPa says so.
- This is BO on a fixed surrogate. In a real campaign, the next step is to cast that mix: the
  measurement updates the GP, and the loop continues.

### Bayesian optimization in Optuna

**Optuna** ([Lecture 10](../l10/notes.md)) ran the hyperparameter search with its default sampler,
TPE. It also has `GPSampler`, which runs Bayesian optimization with a GP surrogate
([documentation](https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.GPSampler.html)).

```python
import optuna

def objective(trial):
    mix = {
        "cement": trial.suggest_float("cement", 141, 475),
        "slag": trial.suggest_float("slag", 0, 237),
        "water": trial.suggest_float("water", 152, 216),
        "superplasticizer": trial.suggest_float("superplasticizer", 0, 16),
    }
    return lab(mix)                       # the 28-day strength of this mix

study = optuna.create_study(
    direction="maximize",
    sampler=optuna.samplers.GPSampler(seed=0, n_startup_trials=5),
)
study.optimize(objective, n_trials=25)
```

- `suggest_float(name, low, high)` lets the sampler choose a value in the range.
- `GPSampler(n_startup_trials=5)` samples 5 points at random, then lets the GP choose.
- `direction="maximize"`: higher strength is better.

### Case study: Bayesian optimization against fifty chemists

```{index} pair: case study; Bayesian reaction optimization
```

- [Shields and colleagues (2021)](https://b-shields.github.io/files/2021-02-03-Nature.pdf),
  in *Nature*, framed a palladium-catalyzed reaction as a black box: inputs were ligand, base,
  solvent, temperature and concentration; the output was yield; each evaluation was a real
  reaction.
- They ran a GP with expected improvement (their tool, EDBO) against fifty expert chemists and
  engineers playing the same optimization as a game.
- Bayesian optimization outperformed the experts in both average efficiency and consistency.
- Unaided search is inconsistent, and inconsistency is expensive when each trial is an
  experiment. The optimizer applies the same rule every time and never forgets a result.

## Active learning

```{index} active learning, uncertainty sampling, query-by-committee
```

:::{admonition} Definition: active learning
:class: tip
**Active learning** chooses which data points to label (measure) next, to make the model as
accurate as possible with as few labels as possible.
:::

- Bayesian optimization looks for **one** best point. Active learning wants a model that is good
  **everywhere** you will use it.
- **Uncertainty sampling**: label the point where the model is least sure, the largest GP
  $\sigma$. **Query-by-committee**: label where an ensemble disagrees most.

### On the concrete strength dataset

Start with 20 labeled rows of the training pool, then label 40 more, one at a time: where the GP
is least sure, or at random. Score each model on the grouped test mixes (median of 8 seeds).

```{figure} figures/active-learning.png
:alt: Test RMSE against the number of labeled rows, from 20 to 60. Querying at random, in gray, drops quickly from 14 to about 10 MPa by 22 rows and ends near 8.6. Querying where the GP is least sure, in blue, stays near 12 to 15 MPa until about 50 rows, then drops to about 8.7 at 60, labeled least-sure queries go to extreme mixes at the edges.
:width: 100%

Median test RMSE over 8 seeds.
```

| Test RMSE | 20 rows | 40 rows | 60 rows |
|---|---|---|---|
| Least-sure queries | 13.9 MPa | 12.7 MPa | 8.7 MPa |
| Random queries | 13.9 MPa | **9.5 MPa** | 8.6 MPa |

**Here, uncertainty sampling loses to random.** Why:

- The GP is least sure at the **edges** of the data: the most extreme mixes, ages and doses.
- Measured: 45% of the least-sure queries are at an age of 3 days or 180 days and more, against
  19% of the pool. The test mixes, like the pool, are mostly in the middle.
- Random queries cover where the test mixes are. The least-sure queries cover where nobody will
  predict.
- Active learning helps when the queries go where the model will be **used**: weight the
  uncertainty by how likely an input is, or restrict the pool to the operating region.

### Case study: an autonomous lab

```{index} pair: case study; A-Lab
```

- The A-Lab ([Szymanski and colleagues, 2023](https://pmc.ncbi.nlm.nih.gov/articles/PMC10700133/),
  *Nature*) plans syntheses of inorganic materials, runs them with robots, characterizes the
  products, and uses an active-learning loop to choose the next recipe when an attempt fails.
- The paper first reported 41 of 58 targets made in 17 days of continuous operation.
- Other researchers questioned how the products were identified and whether they were new. In a
  2026 [author correction](https://doi.org/10.1038/s41586-025-09992-y), a manual re-analysis
  confirmed 36 of the 40 reported successes and left 4 inconclusive, one target was removed
  because it was in the training data, and the materials were described as "new to the
  prediction platform, not necessarily new to science".
- An autonomous loop needs the same check as any other model: whether its measurements say
  what it concluded.

## Extensions engineers need

```{index} constrained Bayesian optimization, multi-objective optimization, Pareto front, batch Bayesian optimization, multi-fidelity optimization
```

- **Constrained BO**: a second GP models a constraint (cost, CO₂, slump), and the acquisition is
  multiplied by the probability that it holds.
- **Multi-objective BO**: strength **and** cost. The answer is a **Pareto front**, the set of
  mixes where no objective improves without another getting worse.
- **Batch BO**: choose several experiments at once, for a lab that casts eight cylinders a day.
- **Multi-fidelity BO**: mix cheap evaluations (a 7-day test, a coarse simulation) with
  expensive ones (a 28-day test, a fine simulation).
- [BoTorch](https://botorch.org/) and [Ax](https://ax.dev/) implement all four.

## Limitations and trade-offs

| | Gaussian process | Deep ensemble | Split conformal |
|---|---|---|---|
| Uncertainty it reports | aleatoric + epistemic | epistemic only | total, constant width |
| Guarantee | if the GP's assumptions hold | none | coverage, if exchangeable |
| Grows away from data | yes | yes | no |
| Scales to large data | poorly ($O(n^3)$ to fit) | yes | yes, wraps any model |

- **Bayesian optimization** works for a few dozen to a few hundred evaluations and up to about
  15 to 20 design variables; beyond that the GP and the acquisition search both struggle.
- It is **stochastic**: report several seeds and a random-search baseline, never one run.
- On a fixed surrogate it **exploits the surrogate's errors**. Its answer is a proposal to test,
  not a result.
- **Active learning** queries where the model is unsure, which may not be where it will be used.
- **Count the expensive evaluations**. A method that spent 10,000 surrogate calls is fine; one that
  spent 10,000 experiments is not.

## In-class demo

- [`l15-uq-bayesopt.ipynb`](l15-uq-bayesopt.ipynb): Lecture 9's GP, a five-network ensemble and
  split conformal on the concrete strength dataset; their coverage on the grouped and the
  extrapolation splits; then Bayesian optimization of the mix with expected improvement written
  out by hand, against random search, and the same search in Optuna's `GPSampler`.

## Summary

- **Aleatoric** uncertainty is the scatter in the data (5.0 MPa between replicate specimens);
  **epistemic** is what the model does not know yet, and shrinks with data.
- **Gaussian process** intervals carry both; an **ensemble's spread** carries only the epistemic
  part; **split conformal** intervals come with a coverage guarantee, if the test data are
  exchangeable with the calibration data.
- **Calibration** is checked with the PICP and a reliability diagram, on a test set like the one
  you will use the model on. On the strongest mixes, conformal's 95% covered 70%.
- **Bayesian optimization** fits a GP and maximizes an **acquisition function**: EI, PI, UCB or
  Thompson sampling, each trading exploration against exploitation differently.
- On a mix design, BO got within 1 MPa of the emulator's best in 29 of 30 seeds; random search in
  none. The emulator's best (91.6 ± 18.0 MPa) is a proposal to test.
- **Active learning** queries where the model is least sure. On the concrete strength dataset that
  meant the edges, and random queries did better.

## Resources

- [Lakshminarayanan, Pritzel and Blundell (2017), deep ensembles](https://arxiv.org/abs/1612.01474).
  The ensemble method, with the noise term that the spread alone lacks.
- [Angelopoulos and Bates, A Gentle Introduction to Conformal Prediction](https://arxiv.org/abs/2107.07511).
  Split conformal from scratch, with code and the exchangeability condition.
- [Frazier, A Tutorial on Bayesian Optimization](https://arxiv.org/abs/1807.02811). The loop,
  expected improvement and the extensions, in one readable tutorial.
- [Shahriari et al. (2016), Taking the Human Out of the Loop](https://www.cs.ox.ac.uk/people/nando.defreitas/publications/BayesOptLoop.pdf).
  The standard review of Bayesian optimization (author's copy).
- [Optuna's GPSampler](https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.GPSampler.html).
  Bayesian optimization with a GP, in the tool of Lecture 10.
- [Settles, Active Learning Literature Survey](https://burrsettles.com/pub/settles.activelearning.pdf).
  Query strategies and the settings they suit (author's copy).
- [Shields et al. (2021), Bayesian reaction optimization](https://b-shields.github.io/files/2021-02-03-Nature.pdf).
  The fifty-chemists contest (author's copy).
- [BoTorch](https://botorch.org/) and [Ax](https://ax.dev/). Production tooling for constrained,
  multi-objective, batch and multi-fidelity BO.

## Assignment

No assignment is released today.

## Practice module

<a href="../../game/#/l15"><strong>Practice module for this session</strong></a>, for
participation credit.
