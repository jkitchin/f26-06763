# L13 · Surrogate modeling, physics-informed models, and uncertainty quantification

:::{admonition} At a glance
:class: tip

- **Session** L13, Week 7 · **Arc** Machine learning & deep learning
- **Slides** <a href="../../slides/l13/">Deck for this session</a>
- **Demo** [`l13-surrogates-uq.ipynb`](l13-surrogates-uq.ipynb), two surrogates, and whether their uncertainty means anything
- **Assignment** A6 due, the miniproject (A7) launches this session
:::

## Why this matters

Everything in this course so far has been about building a model that is accurate. This
session is about the moment that stops being enough.

Here is the situation. You have a simulation or an experiment that is expensive: a CFD run
that takes six hours on a cluster, a finite-element sweep, a DFT calculation, a
twenty-eight-day concrete cure, a wind-tunnel campaign that needs a technician and a
booking. You want to search a design space, which means thousands of evaluations, and you
have budget for perhaps a hundred. So you train a model on the hundred you can afford and
use it to answer the thousands you cannot. That model is a **surrogate**, and in this
session's measurement it answers a question about 33,000 times faster than the solver it
replaces.

The trouble arrives immediately afterwards. An optimizer handed a surrogate does not sample
the design space evenly. It goes exactly where the surrogate says the answer is best, which
is to say exactly where the surrogate is most likely to be wrong, because the largest
predictions of a model fitted to noisy sparse data are disproportionately the ones that got
lucky. Every design loop is therefore an adversarial search against your own model's
optimism. If the surrogate cannot say "I do not know about this region," the loop will find
that region and spend your budget there.

That is why this session is about uncertainty and not only about accuracy. The
demonstration to hold onto: two surrogates in these notes score 2.07 dB and 2.61 dB of RMSE
on the same held-out data, against 6.75 dB for predicting the training mean, and the *worse*
one reports the **narrower** error bar. Its 95% interval contains 80% of the held-out points
where the other's contains 91%. If you compared them on accuracy, as every previous session
in this course has done, you would notice a modest gap and move on. In a design loop the
difference that matters is the one accuracy does not show.

## Learning objectives

By the end of this session you should be able to:

- Design a surrogate: sampling plan, model family, and validation for extrapolation.
- Add physics to a model via soft penalties or hard constraints, and evaluate the payoff.
- Produce and calibrate predictive uncertainty, separating aleatoric from epistemic.

## What a surrogate is, and when it pays for itself

```{index} surrogate model, response surface
```
```{index} see: emulator; surrogate model
```

A **surrogate model** (also **emulator**, **response surface**, or **metamodel**) is a
cheap function fitted to the input-output behaviour of an expensive one. The expensive
thing can be a simulation, a physical experiment, or an entire multi-stage pipeline; the
surrogate does not care, because it sees only the design variables going in and the
quantity of interest coming out.

The word "cheap" is doing specific work. A surrogate is not a better model of the physics;
it is almost always a worse one. What it is, is a model whose evaluation cost is unrelated
to the cost of the thing it imitates. That decoupling is the entire value proposition, and
it earns its keep in four situations: an **optimization inner loop** that needs thousands
of objective evaluations, **real-time or embedded control**, where the solver's latency is
disqualifying regardless of budget, **design sweeps and sensitivity analysis**, where you
want derivatives or Sobol indices that would otherwise cost a factorial number of runs, and
**uncertainty propagation**, where you need to push an input distribution through the model
by Monte Carlo.

### The economics, measured

To make the trade concrete rather than rhetorical, these notes carry a small
"expensive" simulation: steady heat conduction on the unit square with a spatially varying
conductivity, $-\nabla\cdot(k\nabla T) = q$, discretised on a 129 × 129 grid and solved
directly. The design variables are the source position and the two conductivity gradients,
four in total, and the quantity of interest is the peak temperature.

```{figure} figures/surrogate-economics.png
:alt: Three panels. Left, a temperature field from the finite-volume solver, annotated 49 milliseconds. Middle, a parity plot of surrogate against solver on 300 held-out designs, tightly on the diagonal, RMSE 0.002. Right, a log-log plot of total wall-clock against number of design evaluations, with a straight rising line for solving every time and a nearly flat line for training a surrogate first, crossing at 148 queries.
:width: 100%

One solve costs 49 ms; one surrogate prediction costs 1.5 µs. The break-even is not the
speedup, it is where the two total-cost curves cross. Generated by `figures/make_figures.py`.
```

One solve costs **49 ms**. A Gaussian process trained on 128 solves predicts in **1.5 µs
per point**, which is **33,000 times faster**, and it reproduces the solver to an RMSE of
**0.0018 decades** of peak temperature over a response that spans three and a half decades.
That is a surrogate accurate to about half a percent, built from six seconds of computing.

But the speedup is the wrong number to plan with, and this is the practitioner's point of
the section. What matters is the **break-even**: the surrogate costs 128 solves plus a
fitting step *before* it answers anything. Solving directly costs $N \times 49$ ms for $N$
queries; the surrogate route costs $128 \times 49$ ms plus 0.7 s of fitting plus
$N \times 1.5$ µs. Those cross at **148 queries**. Below that, building the surrogate was
strictly a waste of time.

:::{admonition} What a practitioner should take from this
:class: tip

Before you build a surrogate, write down how many times you will query it. If the answer is
"a few dozen," run the solver. The break-even is roughly the size of your training set,
because the surrogate has to pay back the simulations it consumed before it earns anything,
and that is true regardless of how large the speedup factor is.

The corollary matters more. The reason to build a surrogate is almost never a single sweep;
it is that you will query it thousands of times inside an optimizer or a Monte Carlo loop.
If you cannot name the loop, you are probably building the wrong thing.
:::

### The surrogate lifecycle

```{index} design of experiments
```

The sequence is worth naming because each stage has a failure mode:

**Design of experiments** decides where to spend the simulation budget, and this is the
stage with the largest leverage and the least attention paid to it (the next section is
entirely about it). **Train** fits the emulator. **Validate** is where this course's
splitting discipline from [L9](../l09/notes.md) reappears in a harsher form, because a
surrogate is not validated by a random hold-out; it is validated by asking it questions
outside the region it was fitted on. **Deploy** puts it in the loop. **Refine** adds
points where the surrogate is worst, which is active learning, and closes the loop back to
the first stage. That last arrow is next session's subject.

## Spending a simulation budget

```{index} curse of dimensionality, space-filling design, Latin hypercube sampling, Sobol sequence
```

You have a hundred runs. Where do you put them?

The instinct is a **full factorial grid**: pick a few levels of each variable and cross
them. In one or two dimensions this is excellent and you should do it. In four it is
already a disaster, and the arithmetic is the whole argument. A grid with $L$ levels in $d$
dimensions costs $L^d$ runs, so a budget of $N$ affords $L = \lfloor N^{1/d}\rfloor$ levels
per variable. With 100 runs: 10 levels in one dimension, 4 in three, **2 in five**, and 1
in seven. Two levels per variable means you can fit a plane and interactions and nothing
else. This is the **curse of dimensionality** in its most practical form, and note that it
bites at the number of dimensions engineering problems actually have.

The fix is a **space-filling design**: choose points that cover the space without insisting
they line up. The two you should know are:

**Latin hypercube sampling** (McKay, Beckman and Conover, 1979) divides each variable's
range into $N$ equal bins and places exactly one point in each bin of each variable, then
pairs the bins up at random. The guarantee is one-dimensional: every variable's marginal is
perfectly stratified no matter what the others do. That is why an LHS design projected onto
any single axis looks uniform while a grid projected onto any single axis collapses onto
$L$ repeated values.

**Sobol sequences** and other **low-discrepancy** (quasi-Monte Carlo) sequences take a
different route, filling the space in a deterministic order that keeps the **discrepancy**,
a measure of how unevenly points are distributed, as low as possible. Their practical
advantage is that they are *extensible*: you can add points later and the design remains
good, which matters when the campaign gets extended.

```{figure} figures/sampling-designs.png
:alt: Four small scatter plots of 16 points in two dimensions with tick marks showing the one-dimensional projection: full grid occupies 4 of 16 bins in x, uniform random 9, Latin hypercube and Sobol 16 each. A middle panel plots levels per variable that a full grid affords against dimension, falling to two by five dimensions. A right panel plots surrogate RMSE against simulation budget for the four designs, with the grid an order of magnitude worse at every budget.
:width: 100%

Left, the same 16 points four ways, with the one-dimensional projection under each. Right,
what that costs: a GP surrogate for the heat problem, trained on each design and scored on
the same 300 held-out configurations. Generated by `figures/make_figures.py`.
```

Measured on the heat problem, at three budgets that a full grid can actually hit
($2^4$, $3^4$ and $4^4$), the surrogate RMSE in decades of peak temperature is:

| budget | full grid | uniform random | Latin hypercube | Sobol |
|---|---|---|---|---|
| 16 | 0.526 | 0.143 | 0.122 | **0.076** |
| 81 | 0.030 | 0.0035 | 0.0029 | **0.0025** |
| 256 | 0.0090 | 0.0009 | 0.0008 | **0.0007** |

The grid is **ten times worse than random sampling at every budget**, and about an order of
magnitude worse than Sobol. That gap is larger than any modelling choice made later in this
session. It is also entirely free to fix: `scipy.stats.qmc` generates all of these in one
line.

The gap between random, LHS and Sobol is real but much smaller, and it narrows as the
budget grows. Be honest about the size of that effect when you report it. At 16 points
Sobol is roughly twice as good as random and the spread across repeats is large enough that
a single comparison would not have shown it; at 256 they are within 20% of each other.

:::{admonition} Common pitfall
:class: warning

**Sobol sequences want a power-of-two sample size.** The construction's balance properties
hold exactly at $n = 2^m$, and asking for an arbitrary $n$ silently gives you a worse
design. Measured here, mean discrepancy over eight scrambles: $n = 64$ gives
$1.04\times10^{-3}$, $n = 81$ gives $1.17\times10^{-3}$, and $n = 128$ gives
$3.52\times10^{-4}$.

Read that middle number twice. **Adding 17 points made the design measurably worse.** SciPy
warns about this and the warning is easy to click past; the cost is a design you paid 81
simulations for that performs like one you paid fewer than 64 for.
:::

### Interpolation, extrapolation, and how to validate a surrogate

A surrogate's error is not one number. Inside the convex hull of the training points it is
doing interpolation, which is the easy case, and outside it the error can be arbitrarily
large with no warning from any random-split cross-validation.

That distinction is the reason surrogate validation looks different from ordinary model
validation. **Hold out a region of the design space, not a random sample of rows.** If your
design variable is free-stream velocity and you have four velocities, train on three and
predict the fourth. If it is a geometry parameter, hold out the largest. Then report the
extrapolation error *separately*, because averaging it into an overall number hides exactly
the failure a design loop will find.

This session's dataset makes the point cleanly. The **NASA airfoil self-noise** set from
[L9](../l09/notes.md) is 1,503 one-third-octave measurements from an anechoic wind tunnel,
taken from Brooks, Pope and Marcolini's 1989 report, with five inputs and a scaled sound
pressure level in decibels. On a random row split a GP gets 1.97 dB. On held-out
configurations, 2.07 dB. On a held-out free-stream velocity, 3.04 dB. Same model, same
data, error growing by half as the question gets more honest.

:::{admonition} How the held-out-configuration split is defined, and why it is not `GroupKFold`
:class: warning

Every held-out-configuration number in these notes comes from a split written out
explicitly in `figures/make_figures.py`: sort the configuration ids and hold out every
fifth one. That is what `GroupKFold` is for, and it is not what these notes use, because
**scikit-learn 1.8 and 1.9 assign groups to folds by different rules**, with the same
signature and the same `shuffle=False`, and nothing warns you.

The first draft of these notes used `GroupKFold` and the figures disagreed with the demo
notebook: **2.08 dB against 1.50 dB, and 91% coverage against 94%**, on what was supposed to
be the same split. The gap between the two library versions was larger than most of the
effects this session sets out to measure.

This is [L1](../l01/notes.md)'s `np.trapz` lesson in a new costume, and the fix is the same
one. A number your conclusion depends on should not be inherited from a library default that
is free to change.
:::

:::{admonition} Count your knobs, not your columns
:class: note

The airfoil file has five feature columns, and it has **four independent design variables**.
The suction-side displacement thickness is not something the operator sets; it is the
boundary layer that results, and it takes exactly one value in **106 out of 106**
configurations once angle of attack, chord and velocity are fixed.

This matters for the sampling discussion in a way that is easy to miss. If you treat the
five columns as five axes and generate a Latin hypercube over them, most of your design
points describe a wind tunnel that cannot exist, and a surrogate will answer questions
about them with a straight face. **The design space is the set of things you can actually
set.** Derived quantities are outputs wearing an input's clothes.
:::

## Choosing a surrogate family

```{index} Gaussian process regression, radial basis function, polynomial chaos expansion, neural operator
```
```{index} see: kriging; Gaussian process regression
```

There are four families worth knowing, and the choice is mostly determined by the dimension
of the design space and the shape of the output.

**Gaussian process regression**, called **kriging** in the geostatistics and engineering
design literature after Danie Krige's ore-grade work and Georges Matheron's formalisation
of it, is the default for smooth, low-dimensional, expensive problems and has been since
the 1980s. A GP places a prior over functions, conditions it on the data, and returns a
posterior that is again Gaussian: a mean and a variance, at every point, from the same
algebra. That last property is the reason it dominates surrogate modelling. The uncertainty
is not bolted on; it falls out.

The **kernel** is the modelling assumption. `Matern(nu=2.5)` assumes the response is twice
differentiable, which is weaker and usually safer than the RBF kernel's assumption of
infinite smoothness. A separate length scale per input (**automatic relevance
determination**) lets the fit tell you which variables matter, and reading those length
scales afterwards is one of the cheapest diagnostics in this course: a length scale pinned
at its upper bound is the model saying that input does nothing.

The cost is cubic in the number of training points, $O(n^3)$ to fit and $O(n^2)$ per
prediction, which caps a plain GP at a few thousand points. That is usually fine, because if
you had a hundred thousand runs you would not need a surrogate.

**Radial basis function** interpolants are the same idea with the probabilistic
interpretation removed: a weighted sum of kernels centred on the data points. They are
faster and simpler, they interpolate exactly, and they give you no uncertainty, which in
this session's framing is a serious loss.

**Polynomial chaos expansion** expands the response in polynomials orthogonal with respect
to the *input distribution*. It is the tool of choice when the question is uncertainty
propagation rather than optimization, because the expansion coefficients give you moments
and Sobol sensitivity indices analytically instead of by sampling.

**Neural surrogates** win where the others run out: high-dimensional inputs, large training
sets, and structured outputs. An MLP for a scalar quantity of interest is the simple case.
The interesting case is **field-to-field** emulation, where a CNN or U-Net maps an input
field (a geometry, a source distribution, a boundary condition) to an output field (a
pressure, a temperature, a stress), which is what L12's convolutional
architectures were building toward. Beyond that lie **neural operators**, which learn
mappings between function spaces rather than between vectors, so a single trained model
handles any discretisation: [DeepONet](https://arxiv.org/abs/1910.03193) and the
[Fourier Neural Operator](https://arxiv.org/abs/2010.08895) are the two to know, the latter
claiming up to three orders of magnitude over traditional solvers on parametric PDEs.

### Two surrogates on the same held-out sweep

The demo builds a GP and a **deep ensemble**, five small PyTorch networks each predicting a
mean *and* a variance, trained by Gaussian negative log-likelihood instead of squared error.
Both are fitted on the same held-out-configuration split.

```{figure} figures/gp-vs-ensemble.png
:alt: Left, sound pressure level against frequency for one held-out wind-tunnel configuration, with the GP and the deep ensemble both tracking the measured points closely and both showing 95% bands, the GP's noticeably wider. Right, bar chart of mean predicted sigma for the two models under a held-out-configuration split and a held-out-velocity split, annotated with the coverage each achieved: GP 91% then 94%, ensemble 80% then 78%.
:width: 100%

The point predictions are close. The intervals are not, and the coverage is not.
Generated by `figures/make_figures.py`.
```

On the honest split the GP scores **2.07 dB** and the ensemble **2.61 dB**, against 6.75 dB
for predicting the training mean. Both are good models, the GP a little better, and by the
standards of every previous session that is where the comparison ends.

Now look at the intervals, and note that they run the other way. The GP's mean posterior
$\sigma$ is 1.50 dB and its 95% interval covers **91.0%** of the held-out points. The
ensemble is the less accurate model and reports the **narrower** interval, mean $\sigma$
1.15 dB, and it covers **79.9%**. One point in five falls outside an interval that was
supposed to miss one in twenty. The ensemble is both less accurate and more
confident than it has earned, which is the combination that does damage.

Move to the held-out velocity and both models get worse and both widen, by almost exactly
the same factor: $\sigma$ grows **1.83×** for the GP and **1.84×** for the ensemble. That
symmetry is the point. Growing the interval is not the hard part, and a growth factor is not
a diagnostic. The GP ends at 3.04 dB error with $\sigma$ = 2.74 dB and **93.8%** coverage;
the ensemble at 3.55 dB with $\sigma$ = 2.12 dB and **77.6%**. Identical responsiveness,
opposite outcomes, because only one of them was calibrated before it started widening.

The mechanism behind the GP's behaviour is worth understanding rather than memorising. A
stationary kernel has a finite correlation length, so far from any training point the
posterior has nothing to condition on and relaxes back to the prior: prior mean, prior
variance. **The GP's uncertainty grows away from data by construction, not by cleverness.**
That property makes it the default surrogate inside a Bayesian optimization loop,
which is next session's subject, and it is also why a GP is *conservative* rather than
*correct* outside the training envelope. It will tell you it does not know. It will not tell
you the right answer.

## Putting physics into the model

The phrase "physics-informed machine learning" covers a wide range, from a change of
variables to a full PDE solver expressed as a loss function. It is worth separating them,
because they cost very different amounts and they buy different things.

### The cheapest version: use the right coordinates

Trailing-edge noise does not depend on frequency and velocity separately. It depends,
to a first approximation, on the **Strouhal number** $St = f\delta^*/U$, the dimensionless
group formed from frequency, boundary-layer displacement thickness and free-stream
velocity. That is a statement that three of your five columns are not three independent
axes.

Re-expressing the features in those coordinates adds no information and removes none. It is
a change of variables, done before the model sees anything. It is also, measured here, worth
more than most of the modelling decisions in this session.

```{figure} figures/physics-features.png
:alt: Left, four spectra at different free-stream velocities plotted against frequency, clearly separated. Middle, the same four spectra plotted against Strouhal number, collapsing onto each other above the peak. Right, a bar chart of GP RMSE with raw columns against physics coordinates for four hold-out schemes, showing improvements of 12 and 51 percent on the velocity and chord hold-outs and degradations of 8 and 10 percent on the configuration and near-stall hold-outs.
:width: 100%

The same five numbers per row, in two coordinate systems. Spread is the RMS pointwise
difference between the four velocity curves on their common support. Generated by
`figures/make_figures.py`.
```

For the largest chord at zero incidence, the four velocity curves have an RMS spread of
**2.26 dB** against frequency and **1.47 dB** against Strouhal number, and the high-frequency
roll-off collapses onto a single line. Across all 33 settings with more than one velocity,
the mean spread falls from **2.91 dB to 2.34 dB**, and Strouhal is the tighter coordinate in
**20 of 33** settings.

Twenty of thirty-three, not thirty-three of thirty-three. The collapse is dramatic where the
trailing-edge mechanism dominates (at 22.2° on the smallest chord it goes from 6.45 dB to
1.55 dB) and it is actively *worse* at low incidence on the same small chord (2.10 dB to
3.46 dB). Brooks, Pope and Marcolini's model has separate terms for suction-side,
pressure-side and separation noise, each with its own scaling; one dimensionless group
cannot carry three mechanisms.

The GP results follow that structure exactly, and they are not a uniform win:

| hold-out | raw columns | Strouhal / Mach | |
|---|---|---|---|
| held-out configurations | 2.07 dB | 2.24 dB | +8% |
| held-out velocity, 71.3 m/s | 3.04 dB | 2.68 dB | **−12%** |
| held-out chord, 0.3048 m | 4.37 dB | **2.15 dB** | **−51%** |
| held-out stall, $\alpha \geq 15.4°$ | 4.84 dB | 5.31 dB | **+10%** |

Physics coordinates halve the error when extrapolating over chord, because chord is one of
the variables the Strouhal number involves, so an unseen chord becomes an interpolation
problem in the new coordinates. They help on velocity for the same reason. They *hurt* when
extrapolating into stall, where the physics they encode is not the physics that is
happening, and they hurt slightly on plain interpolation too, where there was no
extrapolation for them to rescue and the reparameterisation only cost the GP a coordinate
system its kernel was already fitting well.

Read the pattern rather than the average. The physics pays exactly where it is doing work,
which is when the model is being asked about a region it has not seen along an axis the
physics describes. Everywhere else it is a constraint with no upside.

:::{admonition} What a practitioner should take from this
:class: tip

A physics-informed feature is a **claim**, not a free improvement. It says "these variables
combine this way," and the model will believe you. When the claim holds you get a large,
cheap win, and when it does not you have hard-coded an error that no amount of data will
argue you out of.

So state the claim before you use it, name the regime where you expect it to hold, and test
inside and outside that regime separately. Averaging over the four rows of that table gives
roughly no effect at all, which is the least informative summary available. "Chord
extrapolation improved by 51% and stall extrapolation degraded by 10%, which is what the
underlying noise model predicts" is the sentence worth writing.
:::

### Check the physics is actually in your data

A cautionary measurement, and it changed what this session says. Trailing-edge noise
intensity is supposed to scale roughly as the fifth power of the free-stream velocity, so
the overall level should rise like $50\log_{10}U$. Fitting that exponent from the data, over
the settings that have three or more velocities, gives a median of **0.31** rather than 5.

The likely reason is in the dataset documentation rather than in the physics: the UCI column
is described as "**scaled** sound pressure level," and the spectra appear to have had the
amplitude scaling removed, leaving the spectral shape. The Strouhal collapse of the *shape*
is clearly present, as the figure shows; the level scaling is not.

The point is not about aeroacoustics. It is that a physics prior you were about to impose as
a hard constraint was, in this dataset, **false**, and nothing except a five-line check
would have told you. Before you constrain a model, measure the constraint on the training
data. If it is not there, either your understanding of the physics is wrong or your
understanding of the dataset is, and both are worth finding out before you build on it.

### Soft penalties: physics-informed neural networks

```{index} physics-informed neural network, collocation point
```

The strongest version of physics-informed modelling puts the governing equation into the
loss. [Raissi, Perdikaris and Karniadakis](https://doi.org/10.1016/j.jcp.2018.10.045)
formalised this as the **physics-informed neural network**: represent the solution field by
a network $T_\theta(x)$, and train on

$$
\mathcal{L} = \underbrace{\frac{1}{N}\sum_i \left(T_\theta(x_i) - T_i\right)^2}_{\text{data}}
+ \lambda \underbrace{\frac{1}{M}\sum_j \mathcal{R}\!\left[T_\theta\right](x_j)^2}_{\text{PDE residual}}
+ \underbrace{\text{boundary terms}}_{\text{}}
$$

where $\mathcal{R}$ is the differential operator, evaluated by automatic differentiation at
**collocation points** where no measurement exists. This is [L11](../l11/notes.md)'s
autodiff doing something other than training: the derivatives being taken are with respect
to the *inputs*, not the parameters, and they are part of the loss rather than of the
optimizer.

One implementation detail that is not a detail: **use `tanh`, not ReLU**. The loss
differentiates the network twice, and the second derivative of a ReLU network is zero almost
everywhere, so a PINN built on ReLU has a residual term it structurally cannot reduce.

:::{admonition} If you know the equation, the boundary conditions and the source, you do not need data at all
:class: note

This is worth stating plainly because it determines when a PINN is the right tool. For a
**forward** problem with everything specified, the physics loss alone determines the
solution, and the network is a (usually slower, usually less accurate) alternative to a
finite-element solver.

The engineering case where a PINN genuinely earns its place is the **inverse** or
partially-specified one: the operator is known, a material property or a boundary flux is
not, and the measurements are few, noisy and in the wrong places. Then the physics
regularises a problem that data alone cannot resolve, and it identifies the unknown
parameter as a by-product.
:::

The demonstration in these notes is therefore the inverse problem. One-dimensional steady
conduction, $-k\,T'' = q(x)$ with a known source and unknown conductivity, a handful of
noisy temperature measurements, and $k$ treated as a learnable scalar alongside the network
weights.

```{figure} figures/soft-physics.png
:alt: Three panels. Left, the true temperature field with eight noisy measurements and four fits: data-only, soft PDE penalty, soft PDE with hard boundary conditions, and a penalty using a mis-specified source, which is badly wrong. Middle, log-log RMSE against number of measurements, with the physics variants roughly half the data-only error and the mis-specified variant an order of magnitude worse and flat. Right, recovered conductivity against number of measurements, converging on the true value of 2.5 for the correct physics and sitting near 0.7 for the mis-specified one.
:width: 100%

The same eight measurements, four ways. Five random data draws per point in the right-hand
panels. Generated by `figures/make_figures.py`.
```

**Physics roughly halves the field error at every budget**, and the data-efficiency reading
is the more useful one: with 4 measurements the penalised network reaches an RMSE of 0.070,
which the data-only network needs about **21 measurements** to match. On this problem the
governing equation is worth about a factor of five in experiments.

It also **recovers the conductivity**, 2.38 at four measurements and within a few per cent of
the true 2.5 thereafter, which is a material property identified from four noisy
temperatures. That is the part that tends to convert sceptics.

Now the failure. Give the same penalty a source term that omits the localised hot spot, a
plausible modelling oversight, and the field error is **0.505 at four points and 0.359 at
sixty-four**: three to eleven times worse than using no physics at all, and essentially flat
in the amount of data. The recovered conductivity settles near 0.7 against a true 2.5. A
wrong physics prior does not average out. It is a systematic error that the optimizer will
defend against the evidence, because you told it the equation is true.

### Soft against hard constraints

```{index} hard constraint
```

The boundary condition in the demo can be imposed two ways. **Softly**, as another penalty
term, which is what the loss above does. Or **hard**, by construction: write

$$T_\theta(x) = x(1-x)\,N_\theta(x)$$

and $T(0) = T(1) = 0$ holds identically for every possible value of the weights.

Measured, the two give the same field accuracy on this problem (0.049 against 0.049 at eight
points), and they do not give the same guarantee. The mean boundary violation is
$1.0\times10^{-2}$ for the soft version and **exactly zero** for the hard one. When the
constraint is easy to satisfy, that difference is cosmetic. When a downstream calculation
divides by the constraint, or a certification requires it, or the constraint is what keeps
the solution physical, it is the entire point.

The same trick covers most of the constraints engineers actually need. **Positivity**:
predict $\log y$, or pass the output through a softplus, and no configuration of weights can
produce a negative concentration, a negative temperature or a negative variance. The heat
surrogate earlier in these notes predicts $\log_{10}T_{\max}$ for exactly this reason, and
the mean-variance networks pass their variance head through a softplus.
**Monotonicity**: use a monotone architecture, or add a penalty on the sign of the gradient.
**Conservation**: predict a potential and take its curl, so that the divergence-free
condition is structural.

The rule of thumb: **prefer hard constraints, because they cost nothing at run time and
cannot be traded away by the optimizer.** A soft penalty has a weight $\lambda$, and that
weight is a hyperparameter that competes with your data term. Getting it wrong is the single
most common reason a PINN fails to train, which
[Wang, Teng and Perdikaris](https://arxiv.org/abs/2001.04536) trace to unbalanced
back-propagated gradients between the loss terms.

## Uncertainty, and whether yours is any good

Everything above produces a prediction and a number attached to it. This section is about
what that number means and how to find out whether it is true.

### Aleatoric and epistemic

```{index} aleatoric uncertainty, epistemic uncertainty
```

The distinction is the conceptual crux of the week, and it is not vocabulary.

**Aleatoric** uncertainty is scatter in the process itself: sensor noise, batch-to-batch
variation, turbulence, the fact that two nominally identical specimens do not fail at the
same load. It is a property of the world you are measuring. More data gives you a better
*estimate* of it and does not reduce it. If you want it smaller you need a better
instrument or a better-controlled experiment, not a better model.

**Epistemic** uncertainty is the model's ignorance: regions of the design space where too
few points constrain the fit. It is a property of your model and your dataset, and it is
exactly what more data removes. It is also what a design loop should chase, because a point
with large epistemic uncertainty is a point where an experiment would teach you something.

A deep ensemble separates them by the **law of total variance**. Each member $m$ predicts a
mean $\mu_m(x)$ and a variance $\sigma_m^2(x)$; then

$$
\underbrace{\mathrm{Var}[y \mid x]}_{\text{total}}
= \underbrace{\mathbb{E}_m\!\left[\sigma_m^2(x)\right]}_{\text{aleatoric}}
+ \underbrace{\mathrm{Var}_m\!\left[\mu_m(x)\right]}_{\text{epistemic}}
$$

The average of what the members think the noise is, plus how much the members disagree. A
GP gives the same split more directly: the learned `WhiteKernel` level is the aleatoric part
and the rest of the posterior variance is epistemic.

```{figure} figures/calibration.png
:alt: Three panels. Left, a reliability diagram for four methods on the held-out-configuration split, with the deep ensemble well below the diagonal. Middle, a grouped bar chart of coverage of the nominal 95 percent interval for five methods under three splits, with a dashed line at 95 percent, showing most methods near the line for random rows and well below it for the held-out velocity. Right, a log-log plot of predicted sigma against training points on a synthetic problem, with epistemic falling steeply and aleatoric flattening onto a line marking the noise actually present.
:width: 100%

Right-hand panel is synthetic on purpose: the airfoil file contains **zero** repeated
settings, so nothing in it can tell you how much of the scatter is noise. Generated by
`figures/make_figures.py`.
```

On a synthetic problem where the true noise is known, the split behaves as advertised: the
epistemic term falls steadily with training-set size while the aleatoric term flattens onto
the noise that is actually there.

:::{admonition} The split is a property of the model, not of the data
:class: warning

Run the same decomposition on the airfoil data and you get something less comfortable. As
the training set grows from 58 rows to 1,179, the GP's epistemic term falls from **3.39 dB
to 1.24 dB**, which is the behaviour the synthetic problem predicts. The term it calls
irreducible noise goes **0.88, then 1.23, then 0.78 dB**: no trend, and a spread as large as
the quantity itself.

That number is not a measurement of the wind tunnel's repeatability. It is whatever the
kernel could not explain, relabelled, and it moves when the kernel's job gets easier or
harder.

There is no way to check it from this file, because it contains **no repeated settings at
all**: 1,503 rows, 1,503 distinct input combinations. **Without replicates you cannot
separate noise from model error**, and any aleatoric estimate is a statement about your
model rather than about your instrument. If irreducible scatter matters to your conclusion,
budget for repeat measurements. Three replicates at a handful of settings will tell you more
about your error bars than another hundred unique runs.
:::

### Five ways to get an interval

```{index} deep ensemble, MC-dropout, quantile regression, conformal prediction
```

**GP posterior variance** comes free with the fit and is the most trustworthy of these on
small, smooth problems, at the cost of cubic scaling and a kernel you have to choose.

**Deep ensembles** ([Lakshminarayanan, Pritzel and Blundell,
2017](https://arxiv.org/abs/1612.01474)) train $M$ networks from different initialisations
and combine them as above. Simple, parallel, and the strongest of the neural options in
independent benchmarks, though the paper's claim of being "as good or better than
approximate Bayesian NNs" is a relative statement and not a claim of calibration.

**MC-dropout** ([Gal and Ghahramani, 2016](https://arxiv.org/abs/1506.02142)) leaves dropout
switched on at prediction time and treats the resulting sample of predictions as a posterior,
justified by an equivalence to approximate inference in a deep Gaussian process. It is by
far the cheapest option, requiring one trained model, and its quality depends heavily on the
dropout rate, which is now doing double duty as a prior.

**Quantile regression** fits the conditional 2.5th and 97.5th percentiles directly by
minimising the pinball loss, giving asymmetric intervals for free. It says nothing about
where the uncertainty comes from.

**Conformal prediction** ([Angelopoulos and Bates](https://arxiv.org/abs/2107.07511)) takes
any model's heuristic uncertainty and converts it into an interval with a guarantee. In its
split form: hold out a calibration set, compute the absolute residuals, take the
$\lceil (n+1)(1-\alpha)\rceil / n$ empirical quantile, and use it as the interval half-width.
The guarantee is finite-sample and two-sided,

$$1 - \alpha \le \mathbb{P}\!\left(Y_{\text{test}} \in \mathcal{C}(X_{\text{test}})\right) \le 1 - \alpha + \frac{1}{n+1}$$

and it holds for **any** model and **any** data distribution.

### Checking it: coverage and sharpness

```{index} reliability diagram
```
```{index} pair: metric; PICP
```
```{index} pair: metric; CRPS
```

Two numbers, and you need both.

**PICP**, the prediction-interval coverage probability, is the fraction of held-out points
that fall inside the nominal interval. **Width** is how wide that interval is on average.
Either alone is trivially gamed: an interval of $\pm\infty$ has perfect coverage and no
content, and an interval of zero width is maximally sharp and always wrong.

The formulation to remember is [Gneiting, Balabdaoui and
Raftery's](https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jrssb.pdf):
**maximise the sharpness of the predictive distribution subject to calibration.** Get the
coverage right first; then make the interval as narrow as you can. A **reliability diagram**
checks coverage at every nominal level at once rather than only at 95%, and proper scoring
rules (**negative log-likelihood**, **CRPS**) roll both properties into a single number that
you can actually optimize.

Here is every method above, on the same data, under the three splits, at a nominal 95%:

| method | random rows | held-out configurations | held-out velocity |
|---|---|---|---|
| Gaussian process | 93.4% (5.5 dB) | 91.0% (5.9 dB) | **93.8%** (10.7 dB) |
| deep ensemble | 92.7% (4.2 dB) | **79.9%** (4.5 dB) | **77.6%** (8.3 dB) |
| MC-dropout | 98.7% (7.7 dB) | 94.8% (7.1 dB) | **73.1%** (7.0 dB) |
| split conformal | 96.7% (9.3 dB) | 95.7% (8.4 dB) | **82.2%** (7.1 dB) |
| quantile GBM | 88.0% (13.4 dB) | 89.2% (13.7 dB) | 85.8% (14.5 dB) |

Three things in that table are worth more than the rest of this section.

**On a random row split, almost everything looks fine.** Four of five methods land between
92% and 99%. If your validation is a random split, you will conclude that uncertainty
quantification is a solved problem and ship an overconfident model.

**The ensemble is the one that fails first, and it fails where the data still looks
familiar.** 79.9% coverage on held-out configurations, from a method whose paper's title
contains the words "predictive uncertainty," on a split that is only mildly harder than
random rows and that every other method here handles. Five members is not many, and the
disagreement between five networks systematically understates the disagreement between all
the networks you might have trained. This is consistent with [Ovadia et al.'s
benchmark](https://arxiv.org/abs/1906.02530), which found ensembles the most robust of the
methods it tested under dataset shift, and also found all of them degrading.

**Under extrapolation, two of the intervals got narrower.** MC-dropout goes from 7.08 dB to
6.98 dB and split conformal from 8.41 dB to 7.12 dB, while the actual error rose by half.
That is the worst possible failure mode: the model became more wrong and more confident at
the same time, and reported nothing unusual. Only the GP widened enough to keep up, and it
nearly doubled its interval to do it.

### Why conformal prediction breaks, and why that is instructive

```{index} exchangeability
```
```{index} pair: failure mode; conformal prediction under covariate shift
```

Conformal's guarantee is real, and this is worth demonstrating rather than asserting. Fix
the model, then repeatedly re-partition a pool of held-out rows into calibration and test
sets at random, so that exchangeability holds by construction. Over 400 such draws with 451
calibration points, mean coverage is **95.4%** against the guaranteed band of 95.0% to
95.2%. The theory works.

Now stop re-partitioning at random. Draw the calibration set from the training rows, as the
recipe says, and change what the test set is. Holding out whole tunnel configurations, the
guarantee survives: **95.7%**, because one configuration is much like another and
exchangeability is approximately intact. Holding out a whole free-stream velocity, it
collapses to **82.2%**.

Nothing failed except an assumption. The guarantee requires the calibration points and the
test points to be **exchangeable**, and holding out a design region is precisely a
declaration that they are not. Note where the boundary fell: a grouped split was fine and a
design-region split was not, and the difference between them is not visible in any diagnostic
the method computes.

Worse, the failure is silent and it runs the wrong way. The calibration residuals come from
the easy interpolation regime, so they are small, so the interval is narrow, so a model
facing harder questions issues more confident answers. Conformal's interval on the
extrapolation split is **1.3 dB narrower** than on the split where it worked.

That is the general shape of every uncertainty failure in this session, and it is the shape
of the leakage failures in [L7](../l07/notes.md) and [L9](../l09/notes.md) too. The method
is fine. The claim it makes is conditional on a property of your data, and the property is
almost always the same one: that the rows you calibrated on and the rows you will predict
came from the same place. Angelopoulos and Bates devote sections 4.5 and 4.6 to covariate
shift and distribution drift precisely because this is the failure everyone hits.

## Where this pushes back

```{index} model discrepancy
```

**A surrogate is a model of your simulator, not of reality.** Every error your solver makes,
the surrogate faithfully reproduces, and then adds its own on top. If the CFD is 8% off from
the wind tunnel and the surrogate is 2% off from the CFD, you have a 10% model that reports
2%. The literature on this is the **model discrepancy** or **model-form uncertainty**
problem, and Kennedy and O'Hagan's Bayesian calibration framework is the standard treatment.
The practical version: validate the surrogate against the simulator and the simulator
against reality, and report them separately.

**Gaussian processes do not scale, in two different directions.** The $O(n^3)$ fit is the
one everyone quotes and the easier of the two, since sparse and inducing-point approximations
handle it and GPyTorch runs them on a GPU. The harder limit is *input* dimension: a
stationary kernel in twenty dimensions has essentially no interpolation power, because
everything is far from everything else. Past a few dozen inputs, GPs stop being the default.

**Deep ensembles are five times the training cost for uncertainty you then have to check.**
This session's measurement should temper the enthusiasm: five members gave 80% coverage
where 95% was claimed, on a split every other method here handled. More members help, and
they cost linearly. If the uncertainty is what you need and the problem is small, a GP does
it better and cheaper.

**PINNs are seductive and finicky.** They are elegant, they read beautifully in a paper, and
for a two-week miniproject they are a way to spend all of it debugging a loss weight. The
loss has competing terms with wildly different gradient scales, stiff PDEs make it much
worse, and the failure mode is a network that converges to something smooth and wrong. For
this course's timeline, **a soft penalty on a simple constraint or a hard positivity or
monotonicity constraint on a standard network is the safer physics-informed choice**, and it
captures most of the benefit.

**Calibration is not transferable.** A model calibrated on one operating regime is not
calibrated on the next, and re-calibrating requires labelled data from the new regime, which
in an extrapolating design loop is exactly what you do not have. There is no method in this
session that solves this. What you can do is detect it: monitor the input distribution
against the training distribution, and treat a query far outside it as a request for a real
experiment rather than a prediction.

**And the honest limit on all of it: a confident wrong surrogate is worse than no
surrogate.** Without a surrogate you would have run the experiment. With an overconfident
one you run the wrong experiment and believe the result. Every number in this session's
calibration table is an argument for reporting coverage next to accuracy, every time, from
the first run.

## In-class demo

The runnable notebook is [`l13-surrogates-uq.ipynb`](l13-surrogates-uq.ipynb). It fetches
and caches the NASA airfoil file on first run and needs `mlflow` for the last section.

We start by counting the knobs: 106 configurations, five columns, four independent design
variables, and a displacement thickness that is an output pretending to be an input. Then
three splits, in increasing order of honesty, with the do-nothing baseline for each.

Then the two surrogates. We fit the GP, read its learned length scales as a sampling plan
for the next campaign, and build the five-member ensemble by hand so the mean-variance head
and the negative log-likelihood loss are visible rather than imported. We plot both on a
held-out sweep, which is the slide everyone remembers, and then compute the coverage, which
is the number that changes the decision.

The last third is the part to pay attention to. We put split conformal prediction under
three splits in increasing order of realism and watch a guarantee that is mathematically
airtight produce 96.7%, then 95.7%, then 82.2%. Then we refit in Strouhal coordinates and
find the physics paying for itself on velocity and chord and costing us on stall.

Come with a prediction for one thing: which of the GP and the five-net ensemble will have
the narrower 95% interval, and which will actually contain the data 95% of the time.

## Summary

A surrogate replaces an expensive evaluation with a cheap one, and the number that decides
whether to build one is not the speedup but the break-even, which sits at roughly the size
of your training set. Where you put those training points matters more than almost anything
you do afterwards: a full factorial grid was ten times worse than plain random sampling at
every budget measured here, because a budget of $N$ runs in $d$ dimensions affords only
$N^{1/d}$ levels per variable, and Latin hypercube or Sobol designs fix that for free.
Gaussian processes remain the default surrogate for small, smooth, expensive problems, not
because they are the most accurate but because the uncertainty falls out of the same algebra
as the prediction, and that uncertainty grows away from the data by construction. Physics
helps in three increasingly expensive forms: a change of coordinates, which halved the chord
extrapolation error here and raised the stall error; a hard constraint, which costs nothing
and cannot be traded away; and a soft PDE residual penalty, which was worth about a factor
of five in measurements and became worse than useless when the source term was
mis-specified. And every uncertainty in this session is a conditional claim: on a random row
split almost every method looks calibrated, on a held-out configuration split a five-member
deep ensemble covers 80% of a nominal 95% interval while reporting the narrowest error bar
of any model in the comparison, and under a held-out velocity two of the five methods
responded to a 50% rise in error by making their intervals *narrower*. L14 takes the one
property that survived, the GP posterior variance that grows where data is sparse, and turns
it into a rule for choosing the next experiment.

## Resources

- [UCI Machine Learning Repository: Airfoil Self-Noise](https://archive.ics.uci.edu/dataset/291/airfoil+self+noise).
  The dataset page. Note the exact wording of the target, "scaled sound pressure level," and
  that nothing on the page mentions that the displacement thickness is determined by the
  other three inputs.
- T. F. Brooks, D. S. Pope and M. A. Marcolini, ["Airfoil self-noise and
  prediction"](https://ntrs.nasa.gov/citations/19890016302), NASA RP-1218, 1989. The primary
  source, free from NTRS, and the origin of both the data and the Strouhal scaling used in
  these notes. Chapter 4 is where the separate suction-side, pressure-side and separation
  terms are, which is why one dimensionless group does not collapse everything.
- C. E. Rasmussen and C. K. I. Williams, [*Gaussian Processes for Machine
  Learning*](https://gaussianprocess.org/gpml/chapters/RW.pdf), MIT Press, 2006. Free, and
  the standard reference. Chapters 1 and 2 for the regression mechanics, chapter 5 for
  choosing and fitting kernels. If you read one thing from this list, read chapter 2.
- A. Forrester, A. Sóbester and A. Keane, [*Engineering Design via Surrogate
  Modelling*](https://www.wiley.com/en-us/Engineering+Design+via+Surrogate+Modelling%3A+A+Practical+Guide-p-9780470060681),
  Wiley, 2008. The engineering-design view rather than the machine-learning one, and the
  chapters on sampling plans and on kriging are the ones this session leans on. This one is
  a book to borrow rather than a link to open; the library has it.
- [scikit-learn: Gaussian Processes](https://scikit-learn.org/stable/modules/gaussian_process.html).
  The API you will actually use, including the kernel algebra and the note that fitting
  scales cubically in the number of samples.
- [`scipy.stats.qmc`](https://docs.scipy.org/doc/scipy/reference/stats.qmc.html). Latin
  hypercube, Sobol, Halton and Poisson-disk sampling, plus `discrepancy` for scoring a
  design. Read the section on why Sobol wants a power-of-two sample size before you pick a
  budget.
- M. Raissi, P. Perdikaris and G. E. Karniadakis, ["Physics-informed neural
  networks"](https://doi.org/10.1016/j.jcp.2018.10.045), *J. Comp. Physics* 378, 686-707,
  2019. The paper that named the field. The [project
  page](https://maziarraissi.github.io/PINNs/) has worked examples and code, and the arXiv
  preprints ([Part I](https://arxiv.org/abs/1711.10561),
  [Part II](https://arxiv.org/abs/1711.10566)) are open if the journal version is not.
- S. Wang, Y. Teng and P. Perdikaris, ["Understanding and mitigating gradient pathologies in
  physics-informed neural networks"](https://arxiv.org/abs/2001.04536), 2020. Read this
  before your first PINN rather than after it: it explains why the loss weights fight each
  other and what to do about it.
- B. Lakshminarayanan, A. Pritzel and C. Blundell, ["Simple and Scalable Predictive
  Uncertainty Estimation using Deep Ensembles"](https://arxiv.org/abs/1612.01474), NeurIPS
  2017. Five networks and a negative log-likelihood loss. Short, practical, and the method
  most miniprojects will use.
- Y. Gal and Z. Ghahramani, ["Dropout as a Bayesian
  Approximation"](https://arxiv.org/abs/1506.02142), ICML 2016. The cheapest uncertainty
  there is, and the argument for why leaving dropout on is not a hack.
- Y. Ovadia et al., ["Can You Trust Your Model's Uncertainty? Evaluating Predictive
  Uncertainty Under Dataset Shift"](https://arxiv.org/abs/1906.02530), NeurIPS 2019. The
  large-scale benchmark behind this session's central warning. Every method degrades under
  shift; ensembles degrade least.
- A. N. Angelopoulos and S. Bates, ["A Gentle Introduction to Conformal Prediction and
  Distribution-Free Uncertainty Quantification"](https://arxiv.org/abs/2107.07511). Genuinely
  gentle, and the algorithm is five lines. Sections 4.5 and 4.6, on covariate shift and
  distribution drift, are the ones that matter for a design loop.
- T. Gneiting, F. Balabdaoui and A. E. Raftery, ["Probabilistic forecasts, calibration and
  sharpness"](https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jrssb.pdf),
  *J. R. Statist. Soc. B* 69(2), 243-268, 2007. Where "maximise sharpness subject to
  calibration" comes from, with the diagnostics to do it.
- L. Lu, P. Jin and G. E. Karniadakis, ["DeepONet"](https://arxiv.org/abs/1910.03193), 2019,
  and Z. Li et al., ["Fourier Neural Operator for Parametric Partial Differential
  Equations"](https://arxiv.org/abs/2010.08895), 2020. Operator learning, for when the
  surrogate's output is a field rather than a number.
- [Virtual Library of Simulation Experiments](https://www.sfu.ca/~ssurjano/borehole.html).
  Analytic test functions with known behaviour, including the borehole function, for
  debugging a surrogate pipeline before you spend real simulation time on it.

## Assignment

A6 is due today. The **miniproject (A7)** launches this session, Wednesday 7 October 2026,
and is due at the end of Week 8. It asks you to take an engineering dataset from raw data
through to a **surrogate or predictive model with quantified uncertainty**, tracked in
MLflow, with a short report and a recorded walkthrough. It replaces a weekly assignment and
is worth 15% of the course grade.

Four warnings drawn from this session's measurements.

**Report coverage next to accuracy, from the first run.** An MLflow experiment where every
run logs RMSE and none logs PICP will let you select a model that is accurate and
overconfident, which is the worst combination for a design loop. Log `picp_95` and the mean
interval width alongside the error.

**Hold out a region, not a random sample.** Choose a slice of the design space you would
plausibly be asked to extrapolate into, hold it out entirely, and report its error and
coverage separately from the interpolation numbers. If both are the same, you have not
tested extrapolation.

**Prefer a hard constraint to a full PINN.** Positivity through a log transform,
monotonicity through architecture, a conservation law through the output parameterisation:
these are an afternoon each and they cannot be traded away. A PDE-residual PINN is a
two-week project on its own, and the mis-specified-source result above is what it looks like
when it goes wrong quietly.

**Count and report your simulation or experiment budget.** The point of a surrogate is to
avoid expensive evaluations, so a report that does not say how many it consumed has not made
its own case.

The full spec and rubric are in [the miniproject](../../course/miniproject.md); this
paragraph is a pointer, not the rubric.
