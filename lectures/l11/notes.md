# L11 · Tensors, autodiff, training loops, and GPUs

:::{admonition} At a glance
:class: tip

- **Session** L11, Week 6 · **Arc** Machine learning & deep learning
- **Slides** <a href="../../slides/l11/">Deck for this session</a>
- **Demo** [`l11-tensors-autograd.ipynb`](l11-tensors-autograd.ipynb), a gradient by hand, a loop by hand, and three ways to break it
- **Assignment** A5 due, A6 released this session
:::

## Why this matters

For the last five weeks this course has been about the parts of a machine learning system that
are not the model. This session is the one where you finally write the model, and the reason it
comes this late is that a training loop is about fifteen lines of code and roughly six ways to
get it silently wrong.

That phrase should be familiar by now. A leaky scaler does not raise; a grouped split does not
raise; and a training loop with a missing `zero_grad()` does not raise either. It runs, it
prints a decreasing-looking loss for a while, and it hands you a model that has learned almost
nothing. This session's demo produces exactly that: **validation RMSE of 17.8 MPa against 6.0
for the same code with one line restored**, on a fold where predicting the training mean scores
19.2. The broken run recovered about **11% of the distance** between doing nothing at all and
training correctly, and nothing in the output said so.

The deeper reason to write the loop by hand, once, is that deep learning frameworks are unusual
among the tools in this course: they are the only ones that will happily compute a wrong answer
at full speed and full precision. A database rejects a malformed query. A schema check fails
loudly. But `loss.backward()` will differentiate whatever graph you built, including the one
you built by accident, and `optimizer.step()` will apply it. The framework has no opinion about
whether your graph means anything. That is the price of the generality that makes it useful,
and the only defence is understanding what the three lines actually do.

The session's second argument is about expectations. There is a widespread assumption that a
neural network is a strictly more powerful tool than a gradient-boosted tree, and that the
tabular datasets engineers actually have are simply too small to show it. The truth is more
interesting than that, and the measurement in these notes does not land where the received
wisdom says it should. Getting to the honest answer requires the split discipline from
[L9](../l09/notes.md), which is why this session comes after it and not before.

## Learning objectives

By the end of this session you should be able to:

- Build fluency with tensors, shapes/broadcasting, and device placement.
- Explain and implement a training loop and the role of `autograd` and the optimizer.
- Use GPUs correctly and diagnose the common failure modes.

## Tensors, and the dtype that will bite you

```{index} tensor, dtype, broadcasting
```

A PyTorch **tensor** is a NumPy array with three extra properties: it knows what **device** it
lives on, it optionally records the operations performed on it so they can be differentiated,
and it has a `dtype` that is not the one NumPy would have picked. The first two are the point
of the library. The third is where the first afternoon goes.

Shapes and broadcasting work as they do in NumPy, and the same mental model applies: an
operation between a `(N, 1)` and a `(N,)` tensor broadcasts into `(N, N)`, which is almost never
what you meant and is the single most common source of a loss that will not go down. Views and
copies also behave as in NumPy: `reshape` may return a view sharing storage, `clone` does not,
and mutating a view mutates the original. The autograd engine tracks this correctly, which
means an in-place operation on a tensor that is needed for the backward pass raises a genuinely
helpful error, one of the few places PyTorch does complain.

**The batch dimension comes first.** Every built-in module in PyTorch expects input shaped
`(N, ...)`, where `N` indexes examples: `(N, features)` for an MLP, `(N, channels, height,
width)` for a 2D convolution, `(N, channels, time)` for a 1D convolution over a sensor window.
This is a convention rather than a law, and it exists because it makes the batch the outermost,
contiguous axis, so a batch is a contiguous slab of memory that can be shipped to an accelerator
in one transfer. Learn to read a shape error as a sentence: `mat1 and mat2 shapes cannot be
multiplied (64x8 and 64x1)` is telling you the batch is 64, the features are 8, and something
downstream expected a different orientation.

### The dtype trap, measured

```{index} float32, float64
```
```{index} pair: failure mode; float32 precision loss
```

`torch.tensor(3.14)` gives you a **float32** tensor. `torch.tensor(np.float64(3.14))` gives you
float64. NumPy defaults to float64 and PyTorch defaults to float32, and when a float32 tensor
meets a float64 one, the result is float64, so every dtype you inspect *downstream* of the
mistake reads float64 and looks fine.

This is not hypothetical. The first version of this session's autodiff figure was written to
show that PyTorch and JAX both agree with a hand-derived gradient to machine precision. JAX did.
PyTorch disagreed at **7.5 × 10⁻⁸**, which is eight orders of magnitude worse than it should be
and looked, briefly, like a genuine difference between the two libraries.

It was not. Two scalars in the setup were Python floats, `1.234` and the output of a bare
`rng.normal()` call, and `torch.tensor` stored both as float32. The relative error that produced
was **1.25 × 10⁻⁷**, which is float32 epsilon to two figures. Declare those two scalars as
float64 and PyTorch's gradient matches the analytic one to 1.7 × 10⁻¹⁸.

:::{admonition} What a practitioner should take from this
:class: tip

Set the dtype explicitly at every boundary where data enters a tensor, and do not rely on the
default. `torch.tensor(x, dtype=torch.float32)` is four extra words that document an intent.

Then note the general shape of the bug, which is the L7 lesson again in a new costume: a
quantity crossed an interface, its type was silently converted, nothing raised, and every
diagnostic downstream reported the *promoted* type rather than the one that lost the
information. Checking `tensor.dtype` after the fact would not have found this. Checking it at
the boundary would have.
:::

## Automatic differentiation, demystified

```{index} automatic differentiation
```
```{index} single: automatic differentiation; reverse mode
```

The reason deep learning works at all is that you can compute the gradient of a scalar loss with
respect to millions of parameters for roughly the cost of two forward passes. That is not
obvious, and it is worth understanding rather than accepting.

Take a network small enough to differentiate by hand: one hidden layer, `tanh` activation, a
scalar output, and a squared-error loss on one example.

$$
z = Wx + b, \qquad a = \tanh(z), \qquad \hat{y} = v \cdot a + c, \qquad L = (\hat{y} - y)^2
$$

The chain rule gives every gradient in five lines, and the structure is worth noticing: each
step reuses the quantity computed by the step before it.

$$
\frac{\partial L}{\partial \hat{y}} = 2(\hat{y} - y), \quad
\frac{\partial L}{\partial v} = \frac{\partial L}{\partial \hat{y}} a, \quad
\frac{\partial L}{\partial z} = \left(\frac{\partial L}{\partial \hat{y}} v\right) \odot (1 - a^2), \quad
\frac{\partial L}{\partial W} = \frac{\partial L}{\partial z} x^{\top}
$$

That reuse is the whole trick. **Reverse-mode automatic differentiation** is exactly this
computation, organised: run the forward pass and remember each intermediate, then walk the
recorded operations backwards, multiplying by each local derivative. Because the loss is a
scalar, one backward walk produces the derivative with respect to every input at once.

The alternative is finite differences: perturb one parameter, recompute the loss, divide. It
needs two forward passes per parameter and it is not exact, because you are trading two errors
against each other. Too large a step and the difference quotient does not approximate the
derivative; too small and catastrophic cancellation in the subtraction destroys the precision
you were trying to buy.

```{figure} figures/autodiff-vs-fd.png
:alt: Left, log-log plot of gradient error against finite-difference step size, showing a V-shaped curve bottoming near 1e-12, with flat horizontal lines for PyTorch and JAX autodiff near 1e-17 and a much higher line for PyTorch with two stray Python floats near 1e-7. Right, log-log plot of model evaluations per gradient against parameter count, with finite differences rising linearly and backpropagation flat at 2.
:width: 100%

Left: the same gradient computed four ways. The V is the classic trade between truncation and
round-off; its best point, 1.4 × 10⁻¹², is four orders of magnitude worse than autodiff and
requires knowing the right step size in advance. The red line is what one careless dtype costs.
Right: why nobody uses finite differences for training. Generated by `figures/make_figures.py`.
```

The measured numbers: PyTorch's gradient differs from the hand-derived one by **1.7 × 10⁻¹⁸**,
JAX's by **4.4 × 10⁻¹⁶**, and the two agree with each other to 4.4 × 10⁻¹⁶, which is float64
epsilon. The best central difference, over forty step sizes, manages **1.4 × 10⁻¹²** at
*h* = 3 × 10⁻⁷, and you only know that was the best step because the exact answer was available
to compare against, which in a real problem it is not.

### Two designs for the same mathematics

The mathematics above is framework-independent, but the two major libraries express it very
differently, and the contrast explains a rule you would otherwise have to memorise.

**PyTorch records a tape.** Tensors with `requires_grad=True` cause every operation on them to
be appended to a graph. Calling `.backward()` walks that graph and **accumulates** the result
into each tensor's `.grad` attribute. Accumulates, not assigns:

```python
loss = loss_fn(model(x), y)
optimizer.zero_grad()     # .grad += is the semantics, so you must clear it first
loss.backward()           # walks the tape, adds into every .grad
optimizer.step()          # reads .grad, updates the parameters
```

**JAX transforms functions.** `jax.grad(f)` does not compute a gradient; it returns a *new
function* that computes one. There is no tape, no mutable `.grad`, and consequently nothing to
zero:

```python
import jax, jax.numpy as jnp

def loss(params, x, y):
    a = jnp.tanh(params["W"] @ x + params["b"])
    return (params["v"] @ a + params["c"] - y) ** 2

grads = jax.grad(loss)(params, x, y)     # same shape as params, no state touched
```

Both compute the same numbers, as measured above. But the accumulation in PyTorch is the reason
`zero_grad()` exists, and knowing that turns it from a rule into a consequence. It is not an
oversight: accumulation is what lets you split a batch too large for memory into several
micro-batches, call `backward()` on each, and step once on the sum. The API optimises for that
case, and the cost is that the common case needs an extra line.

:::{admonition} Common pitfall
:class: warning

`zero_grad()` is the line everyone omits exactly once. What it looks like when you do is not a
crash: the gradient at step *k* is the sum of the gradients from steps 1 through *k*, so the
effective step size grows without bound through the epoch, and the model wanders.

Measured on one fold of this session's data: **17.8 MPa validation RMSE without it, 6.0 MPa
with it**, against 19.2 for predicting the training mean. The broken run captured roughly a
tenth of what the working one did, and its loss curve oscillates rather than diverging cleanly,
so it reads as a hyperparameter problem rather than a bug.
:::

The other two pieces of the autograd API are small and worth naming. `torch.no_grad()` is a
context manager that stops the tape being recorded, which you want around every evaluation pass
because building a graph you will never differentiate wastes memory. And `model.eval()` is
*not* the same thing: it switches layers whose behaviour differs between training and
inference, dropout and batch normalization in particular, and forgetting it is a classic source
of a validation score that mysteriously differs from the test score computed by another script.

## The anatomy of a training loop

```{index} training loop, DataLoader, loss function, optimizer, Adam, AdamW
```

With the gradient understood, the loop is short. Four objects and five lines.

A **`Dataset`** answers two questions, `__len__` and `__getitem__`, and a **`DataLoader`**
wraps one to produce shuffled batches, optionally in parallel worker processes. For a table
that fits in memory, as this session's does, you can skip both and index tensors directly; the
`DataLoader` earns its place when examples must be read or decoded from disk, and `num_workers`
matters when that decoding is the bottleneck rather than the arithmetic.

An **`nn.Module`** holds parameters and defines `forward`. A **loss function** reduces
predictions and targets to a scalar: `MSELoss` for regression when large errors should hurt
quadratically, `L1Loss` when they should not, `CrossEntropyLoss` for classification, which
expects raw logits rather than probabilities and applies the softmax itself, a detail that
produces a lot of quietly mistrained classifiers.

An **optimizer** turns gradients into parameter updates. **SGD with momentum** is the classical
choice and is still what most published image models use. **Adam** and **AdamW** adapt a
per-parameter step size from a running estimate of the gradient's magnitude, which makes them
far more forgiving of a badly scaled problem, and this session measures exactly how forgiving.

```python
for epoch in range(n_epochs):
    model.train()
    for xb, yb in loader:
        xb, yb = xb.to(device), yb.to(device)
        loss = loss_fn(model(xb), yb)   # forward
        optimizer.zero_grad()           # clear the accumulator
        loss.backward()                 # backward
        optimizer.step()                # update
```

### JAX writes the same loop inside out

The batch dimension is a convention PyTorch asks you to honour in every module you write. JAX
takes the other route: write the function for **one** example and let `vmap` add the batch axis.

```python
def predict_one(params, x):                    # no batch dimension anywhere
    return params["v"] @ jnp.tanh(params["W"] @ x + params["b"]) + params["c"]

predict_batch = jax.vmap(predict_one, in_axes=(None, 0))   # params shared, x batched
```

That is worth seeing once even if you never write JAX, because it names what the batch dimension
*is*: an axis you are mapping over, not a property of the model. In the demo, `vmap` agrees with
an explicit Python loop over the same 256 examples to **2.2 × 10⁻¹⁵**, and it is faster, because
it becomes one batched kernel rather than 256 small ones.

The same framing explains `jax.jit`, which compiles a function through XLA and fuses what it
can into single kernels. What that is worth depends entirely on what you give it, and the demo
measures three cases rather than quoting one:

| workload | eager | jit | |
|---|---|---|---|
| one 512×512 matmul plus `tanh` | 2.8 ms | 3.6 ms | **0.8×** |
| a chain of elementwise ops on 2M floats | 16.8 ms | 14.6 ms | 1.2× |
| a 10-step iterative update via `lax.fori_loop` | 83.3 ms | 30.3 ms | **2.8×** |

Compiling a single large matrix multiply makes it *slower*: there is nothing to fuse, the eager
path was already one call into an optimised BLAS kernel, and the compiled version adds
dispatch. Compiling a loop of many small operations is worth 2.8×, because that is exactly what
fusion removes. An earlier draft of these notes reported a flat "3× speedup" from a badly timed
version of the first benchmark; it was measurement noise. The rule worth keeping is that
compilation pays when there are many small operations to collapse, which is the same argument
that decides whether a GPU pays, and that is the next section.

## Devices, and what an accelerator actually buys

```{index} GPU, device placement
```

Moving to a GPU is two lines: `model.to(device)` and `x.to(device)`. The rules are few. Model
and data must be on the same device or you get a clear error, which is the good case. Anything
you print, plot, or hand to NumPy must come back with `.cpu()`, and doing that inside the
training loop silently serialises the whole thing, because it forces the accelerator to finish
before the copy can start. Timing GPU code without an explicit synchronise measures how fast
you queued the work, not how fast it ran.

The part worth internalising is that **a GPU is a throughput device with a large fixed cost per
kernel launch.** It does not make operations faster; it makes wide operations cheaper per
element. If your operation is narrow, the launch overhead dominates and the accelerator loses.

```{figure} figures/device-crossover.png
:alt: Left, log-log plot of epoch time against hidden-layer width for CPU and Apple MPS, with the two lines crossing near 200 hidden units. Right, the ratio of CPU time to GPU time against width, below 1 for the smallest model and rising above 1 past a few hundred hidden units.
:width: 100%

Epoch time for a three-layer MLP on 8,192 synthetic rows, batch 1,024. Below roughly 200 hidden
units the CPU wins outright; the accelerator only pays once there is enough arithmetic behind
each launch. Measured on Apple MPS, because that is the accelerator this laptop has. Generated
by `figures/make_figures.py`.
```

This session's actual model, an MLP with two hidden layers of 64 units trained on 1,030 rows,
runs at **8.6 ms per epoch on the CPU and 21.1 ms on the GPU**. Moving it to the accelerator
makes it two and a half times slower. The crossover in the figure sits between 64 and 256
hidden units, and past it the accelerator wins by factors between 1.3 and 3 on this hardware.

Those timings are the least reproducible numbers in these notes, and it is worth saying why.
They are wall-clock measurements on a shared laptop, so an earlier run of the identical script
reported 11.2 ms and 33.9 ms for the same two configurations, because something else was
competing for the machine. The figures now report the *minimum* over repeated trials rather
than the mean, which is standard practice for microbenchmarks: interference can only ever make
a measurement slower, so the minimum is the stable estimate. Expect the ratios to move by tens
of percent on your hardware; expect the crossing to be there.

:::{admonition} A caveat about these numbers
:class: warning

These are Apple MPS measurements on a laptop, because that is the accelerator available where
these figures were generated. A datacentre CUDA card, which is what A6 gives you, has a much
higher ceiling: speedups of 10× to 50× on a large model are ordinary, not the 1.9× measured
here.

What transfers is the *shape*, not the magnitude. There is a fixed cost per kernel launch on
every accelerator, so the crossover exists on every accelerator; a bigger card moves it and
raises the plateau. The practical consequence is the same either way, and it is the one the
module's teaching notes give: **debug on CPU with a tiny subset, then launch the real run on
the GPU.** For a model the size of this session's, the CPU is the correct choice, not a
consolation prize.
:::

`torch.autocast` and `GradScaler` are worth knowing about but not worth using yet. Mixed
precision runs the bulk of the arithmetic in float16 or bfloat16 while keeping a float32 copy
of the weights, roughly halving memory and often doubling throughput on hardware with tensor
cores. `GradScaler` exists because float16 has a narrow exponent range and small gradients
underflow to zero, so the loss is multiplied up before the backward pass and the gradients
divided down after. Reach for it when a model does not fit or is too slow, not before.

## Does the net actually beat the tree?

The module chose this dataset deliberately. **Concrete compressive strength** is a canonical
engineering surrogate problem: 1,030 mixes from I-Cheng Yeh's 1998 study, eight inputs (cement,
blast-furnace slag, fly ash, water, superplasticizer, coarse and fine aggregate, and age in
days) predicting the result of a destructive test that takes 28 days and destroys the specimen.
That is exactly the trade a surrogate exists to make.

It is also small and tabular, which is where the received wisdom says deep learning loses.

### Look at the rows before you model them

Before any of that, apply [L9](../l09/notes.md)'s question: are these rows exchangeable? They
are not, and the structure is easy to miss because nothing in the file announces it.

Group the rows by their **seven mix components**, ignoring age, and the 1,030 rows collapse into
**428 distinct mixes**. Of those, 182 were tested at more than one age, and those multi-age
mixes account for **76% of all rows**. The same batch of concrete appears at 3 days, 7 days,
28 days and 90 days, as separate rows.

A random k-fold therefore puts the same mix on both sides of the split, and asks the model to
predict a curing curve it has already seen most of. That is precisely the airfoil frequency
sweep from [L9](../l09/notes.md), in a different material. The file also contains **25 exact
duplicate rows**, identical in all nine columns, which a random split will happily place in
train and test simultaneously.

:::{admonition} How much scatter is even there?
:class: note

The dataset contains just enough replication to prove there is irreducible noise, and nowhere
near enough to measure it well. Eight settings have the same mix and the same age measured
twice with different results, and those pairs differ by 0.89, 1.28, 1.48, 1.68, 1.97, 2.86,
3.44 and 6.60 MPa. Treating them as duplicate measurements gives a repeatability standard
deviation of about **2.2 MPa**, on **eight degrees of freedom**.

Take that as an order of magnitude and not a number. It is enough to say that a model reporting
an RMSE near 2 MPa on this dataset would be claiming to predict the test better than the test
can reproduce itself, and that is the useful thing to know.

One more group was excluded from that estimate: four rows with identical features at 7 days,
three of which report exactly 55.895819 MPa and the fourth 22.897498. That is not scatter, it
is one bad number, and averaging it into a repeatability estimate would have tripled it.
:::

### The comparison, run honestly

```{figure} figures/dl-vs-trees.png
:alt: Left, grouped bar chart of cross-validated RMSE for four models under a mix-grouped split and a random split; every model does better under the random split, and the gradient-boosting bar improves most. Right, the MLP-minus-tree difference under each scheme, showing plus 0.15 with an error bar that crosses zero for the honest split, and plus 0.49 with a small error bar for the leaky split.
:width: 100%

Five random seeds by five folds, so 25 measurements per bar. Everything gets better under the
random split; the question is which model gets better *faster*. Generated by
`figures/make_figures.py`.
```

Under a **random k-fold**, gradient boosting scores 4.46 MPa and the PyTorch MLP scores 4.88.
The tree wins by 0.41 ± 0.09 MPa, more than four standard errors, which is a real difference.
This is the result the received wisdom predicts, and it is what the module's teaching notes lead
you to expect.

Under a **`GroupKFold` on the mix**, gradient boosting scores 5.73 and the MLP 5.81. The gap is
0.09 ± 0.10 MPa. That is smaller than its own standard error: on this dataset, honestly
evaluated, **the two models tie**.

Both models get worse when the leak is closed, which is expected. What is not expected is that
the tree gets worse *faster*: it gains 1.27 MPa from the leaky split against the MLP's 0.94.
Gradient boosting is better at exploiting a near-duplicate row than a small MLP is, so a good
part of "trees beat nets on small tabular data" was, on this dataset, a statement about the
split rather than about the models.

That is a narrower claim than it may sound, and it is worth stating its limits plainly. One
dataset with 1,030 rows is not a refutation of anything. [Grinsztajn, Oyallon and
Varoquaux](https://arxiv.org/abs/2207.08815) benchmarked **45 datasets** with 20,000 compute
hours of hyperparameter search per learner and concluded that "tree-based models remain
state-of-the-art on medium-sized data (~10K samples)," and they identify three specific reasons
rooted in inductive bias: neural networks struggle to be "robust to uninformative features," to
"preserve the orientation of the data," and to "easily learn irregular functions." Nothing here
contradicts that. What the concrete measurement shows is narrower and still useful: **before you
attribute a model-family gap to inductive bias, check that it is not a split artefact.**

:::{admonition} What a practitioner should take from this
:class: tip

A single seed is not a result. The first version of this comparison ran one seed and showed the
MLP *beating* gradient boosting under the grouped split. Five seeds show a tie. Neural network
training is stochastic in initialisation, in batch order, and in dropout, and the spread across
seeds on this problem is comparable to the difference between model families. Report the mean
and spread over at least five seeds, or do not report a comparison.

And run the comparison on the honest split first. A model-selection conclusion drawn on a leaky
split can invert when the leak is closed, because different model families exploit leaks by
different amounts.
:::

## Three ways a first training loop dies

```{index} learning rate
```
```{index} pair: failure mode; forgetting zero_grad
```
```{index} pair: failure mode; unscaled inputs
```

The module's teaching notes name the failures that occupy the first lab session. Each is worth
seeing measured, because each looks different from what you would guess.

```{figure} figures/training-pathologies.png
:alt: Three panels of validation RMSE against epoch. Left, a run with zero_grad oscillating around 19 MPa while the correct run settles near 5.7. Middle, four SGD learning rates, three converging at different speeds and a note that the largest produced NaN from the first epoch. Right, Adam and SGD with scaled and raw inputs, with Adam on raw inputs settling near 10 and SGD on raw inputs diverging off scale.
:width: 100%

The same fold, the same architecture, one thing changed at a time. Generated by
`figures/make_figures.py`.
```

**Forgetting `zero_grad()`** produces the oscillation in the left panel: 17.8 MPa against 6.0,
where predicting the training mean scores 19.2 on this fold. Eleven per cent of the available
improvement, from code that runs to completion without a warning.

**The learning rate** behaves as expected until it does not. With plain SGD, 0.001 is too small
to converge in the budget (13.2 MPa after 120 epochs and still descending), 0.01 and 0.1 both
work at about 7.6, 1.0 diverges to 33.7, and **2.0 produces NaN from the first epoch onward**.
The failure at 2.0 is total rather than gradual: there is no partially-diverged run to diagnose,
just a column of `nan`.

The boundary is worth a sentence of its own, because it is fuzzier than the tidy version of this
lesson admits. At **lr = 1.0** the outcome depends on the seed: across six seed-and-loop
combinations tested it produced `nan` in three and diverged to somewhere between 90 and 170 MPa
in the others. A learning rate is not "stable" or "unstable"; it is stable *for this
initialisation*, and a single run that survived is not evidence that the next one will.

**Unscaled inputs** are the interesting one, because the outcome depends entirely on the
optimizer, which the usual advice does not mention. The concrete features span cement in the
hundreds of kg/m³ and superplasticizer in single digits, a range of roughly two orders of
magnitude. With **SGD** that produces `nan` within the first epoch. With **Adam** it does not
diverge at all: it trains to 9.7 MPa instead of 6.0, a model that works, is more than half again
as bad as it should be, and gives no indication that anything is wrong.

:::{admonition} What a practitioner should take from this
:class: tip

Adam's per-parameter step size makes it forgiving, and forgiveness is not always a
kindness. SGD tells you about a scaling bug by exploding; Adam absorbs the same bug and hands
you a mediocre model. If you have never scaled your inputs and your Adam-trained network is
merely disappointing, scale them before you touch the architecture.

Scale on the training split only, with the fitted transform applied to validation and test,
exactly as in [L7](../l07/notes.md). The habit does not change because the model is now a
neural network.
:::

## Reproducibility, and the seeds that actually matter

```{index} random seed
```

A deep learning run has more sources of randomness than a scikit-learn fit: parameter
initialisation, batch shuffling, dropout masks, and on GPU the non-deterministic reduction order
of some kernels. Seeding `torch`, NumPy and Python's `random` covers the first three;
`torch.use_deterministic_algorithms(True)` covers most of the fourth, at a speed cost.

The honest framing is that seeding makes a run *reproducible*, not *representative*. A single
seeded run is one draw from a distribution, and the width of that distribution is a property of
your problem that you need to know. On this session's data the seed-to-seed spread is large
enough to reverse a model-family comparison, which is why every number in these notes is a mean
over five seeds and five folds.

Log the seed to MLflow alongside everything else from L10, and log the
*number of seeds* too. "RMSE 5.81" is an anecdote; "5.81 ± 0.49 over 25 runs" is a measurement.

## Where this pushes back

**Deep learning is not the default, and this dataset is the argument.** A gradient-boosted tree
on concrete trains in under a second, has no learning rate to tune, no scaling requirement, no
device to place, and ties the neural network. Every hour spent on the MLP bought a model that is
harder to deploy and no more accurate. The reason to learn PyTorch is not that it wins here; it
is that it is the only option once the input has structure a tree cannot exploit, which is
L12's subject.

**The framework will compute a wrong answer at full speed.** This is worth repeating as a
limitation rather than a feature. Nothing in the stack checks that your graph means what you
intended, and the three measured pathologies above are all silent. The defences are external:
a baseline you have to beat, a held-out number you compute once, and a loss curve you actually
look at.

**Autodiff is exact but not free, and not universal.** Reverse mode stores every intermediate
from the forward pass, so memory scales with the depth of the graph, which is why very deep
models need gradient checkpointing. It also requires the graph to be differentiable: an
`argmax`, a hard threshold, or a discrete sampling step has zero or undefined gradient, and no
framework will warn you that the gradient it handed back is uninformative rather than small.

**JAX and PyTorch are not interchangeable, and this course teaches PyTorch for a reason.**
PyTorch's ecosystem for the things engineers actually need (pretrained vision and sequence
models, deployment tooling, the sheer volume of examples) is far deeper, and A6 assumes it.
JAX earns its place when the thing you want to differentiate is not a neural network: a
simulator, an ODE solve, a physical model with parameters to fit. Its functional design also
composes in ways PyTorch's does not, so `jax.grad(jax.grad(f))` for a Hessian, or
`jax.vmap(jax.grad(f))` for per-example gradients, are one-liners rather than projects. The
cost is real: everything must be pure, control flow that depends on values needs
`jax.lax.cond`, arrays are immutable, and the default is float32 unless you turn on x64, which
is exactly the trap this session's autodiff figure fell into from the other direction.

**And the GPU is a tool, not a virtue.** A model that runs four times slower on the accelerator
is not an unusual case; it is the normal case for tabular engineering data. Measure before you
migrate.

## In-class demo

The runnable notebook is [`l11-tensors-autograd.ipynb`](l11-tensors-autograd.ipynb). It fetches
and caches the UCI concrete file on first run, and it needs `xlrd`, because the canonical copy
of this dataset is still a 1997-vintage `.xls`.

We start with the hand-derived gradient, and check it against `loss.backward()` and against
`jax.grad`, then against central differences at a range of step sizes so the trade is visible
rather than asserted. Then we build the mix-level groups, look at how much of the dataset is
grouped, and lock a test split.

Then the loop, written by hand: forward, `zero_grad`, backward, step. We break it three times
on purpose, once per pathology above, and watch what each failure looks like. We move the same
code to the GPU, confirm it produces the same answer, and measure that it is slower.

We close by running the MLP against gradient boosting on the same folds under both split
schemes, which is where the session's central number comes from.

Come with a prediction for one thing: whether the neural network or the gradient-boosted tree
wins on 1,030 rows of concrete data, and whether your answer changes if the split changes.

## Summary

A tensor is a NumPy array that knows its device and remembers its history, and the dtype it
picks by default is not NumPy's, which is worth four extra words at every boundary. Reverse-mode
automatic differentiation computes the gradient with respect to every parameter for about the
cost of two forward passes, exactly, where finite differences would need two evaluations per
parameter and would still be four orders of magnitude less accurate at the best step size you
could have chosen. PyTorch expresses that by recording a tape and accumulating into a mutable
`.grad`, which is why `zero_grad()` exists and why omitting it costs more than the model is
worth; JAX expresses the same mathematics as a transformation of pure functions, which is worth
seeing because it makes the design choice visible rather than arbitrary. The training loop is
four objects and five lines, and it fails silently in at least three ways that this session
measures rather than describes. A GPU is a throughput device with a fixed cost per launch, so
the model in this session runs four times slower on one. And on 1,030 rows of concrete, the
neural network and the gradient-boosted tree tie once the split respects the mix structure,
which is a narrower and more useful claim than either "deep learning wins" or "trees win."
L12 picks up where the tie leaves off: architectures that match the structure
of the input, where a network can do something a tree genuinely cannot.

## Resources

- [PyTorch: Learn the Basics](https://docs.pytorch.org/tutorials/beginner/basics/intro.html).
  The official path from tensors through autograd to the optimization loop. Do the
  Tensors, Autograd and Optimization pages; they take about an hour together and they are the
  prerequisite for A6.
- [PyTorch: Datasets & DataLoaders](https://docs.pytorch.org/tutorials/beginner/basics/data_tutorial.html).
  The one page to read before writing a custom `Dataset`, which A6 will need for any
  windowed sensor problem.
- [PyTorch: A Gentle Introduction to `torch.autograd`](https://docs.pytorch.org/tutorials/beginner/blitz/autograd_tutorial.html).
  The tape, the graph, and why gradients accumulate, from the source. Read it alongside this
  session's hand-derived example rather than instead of it.
- [Daniel Bourke, *Learn PyTorch for Deep Learning*](https://www.learnpytorch.io/), sections
  00-03. Free, video-paired, and unusually good at the parts other tutorials skip, particularly
  device handling and the shape errors you will actually hit.
- L. Grinsztajn, E. Oyallon and G. Varoquaux, ["Why do tree-based models still outperform deep
  learning on typical tabular data?"](https://arxiv.org/abs/2207.08815), NeurIPS 2022
  Datasets and Benchmarks. 45 datasets, 20,000 compute hours of search per learner, and a
  careful answer rather than a slogan. The three inductive-bias findings in section 5 are the
  part to remember.
- I-C. Yeh, "Modeling of strength of high-performance concrete using artificial neural
  networks," *Cement and Concrete Research* 28(12), 1797-1808, 1998,
  [doi:10.1016/S0008-8846(98)00165-3](https://doi.org/10.1016/S0008-8846(98)00165-3). The
  origin of this session's dataset, and a reminder that applying neural networks to concrete is
  a 1998 idea rather than a new one.
- [UCI Machine Learning Repository: Concrete Compressive Strength](https://archive.ics.uci.edu/dataset/165/concrete+compressive+strength).
  The dataset page. Note that the download is an `.xls`, and that neither the page nor the
  readme mentions that three quarters of the rows share a mix with another row.
- [JAX: The Autodiff Cookbook](https://docs.jax.dev/en/latest/notebooks/autodiff_cookbook.html).
  If the functional view of gradients appeals, this is the best single document on it: `grad`,
  `jacfwd` and `jacrev`, and when to use which.
- [JAX: Sharp Bits](https://docs.jax.dev/en/latest/notebooks/Common_Gotchas_in_JAX.html).
  Read this *before* writing JAX, not after. Immutable arrays, explicit PRNG keys, float32 by
  default, and the out-of-bounds indexing that silently clamps instead of raising.
- [Goodfellow, Bengio & Courville, *Deep Learning*](https://www.deeplearningbook.org/), chapter
  6.5, "Back-Propagation and Other Differentiation Algorithms." Free online. The conceptual
  treatment behind this session's hand-derived example, including why reverse mode is the right
  choice when the output is a scalar.

## Assignment

A5 is due today. A6, "Train a PyTorch model on an engineering dataset," is released this session
(Wednesday 30 September 2026) and is due roughly one week later. It asks you to build, train and
honestly evaluate a deep model on a real engineering dataset, on a GPU, with MLflow tracking and
a comparison against a strong classical baseline on the same split. You must write the training
loop yourself; the point of the exercise is the debugging, and a high-level trainer removes it.

Three warnings drawn from this session's measurements.

**Report a mean and a spread over seeds, not a single run.** The seed-to-seed variation on a
small dataset can be as large as the difference between model families, and a single-seed
comparison is not evidence.

**Debug on CPU.** For anything the size of this session's model, the GPU is slower, and GPU
queue time is real. Get the loop correct on a subset of a few hundred rows and a handful of
epochs, then launch the full run.

**If your net loses to the baseline, say so and explain why.** The rubric rewards an honest
comparison, not a winning one. "The 1D-CNN scored 18.2 RMSE against the gradient-boosting
baseline's 17.4, and here is why the extra capacity did not help" is a better answer than a
tuned-until-it-wins number you cannot defend.

The full spec and rubric are in [A6](../../course/assignments/a06.md); this paragraph is a
pointer, not the rubric.
