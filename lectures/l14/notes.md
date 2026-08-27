# Lecture 14: Bayesian optimization and active learning for design

:::{admonition} Overview
:class: tip

- **Session** Lecture 14, Week 7
- **Arc** Machine learning and deep learning
- **Slides** <a href="../../slides/l14/">Deck for this session</a>
- **Practice** <a href="../../game/#/l14">Practice module for this session</a>
- **Demo** [`l14-bayesopt-design.ipynb`](l14-bayesopt-design.ipynb), a Bayesian optimizer built by hand, then the same loop in BoTorch, both raced against random search
- **Assignment** the miniproject (Assignment 7) is under way, launched Lecture 13 and due in Week 8
:::

## Why this matters

The previous session built a surrogate that does more than predict: it reports where it is unsure. A Gaussian process fitted to airfoil measurements returns a mean and a standard deviation at every operating point, and the standard deviation grows in the regions the training data never covered. That extra output looked like a nicety at the time. This session is about spending it.

Here is the situation it is for. You have an objective you can evaluate, but each evaluation is expensive: a finite-element sweep that ties up a cluster for hours, a wind-tunnel booking, a twenty-eight-day concrete cure, a materials synthesis followed by a day of characterization. You want the best design, which in principle means searching thousands of candidates, and your budget is perhaps a few dozen evaluations. The question is not "what is my model" any more. It is "given everything I have measured so far, which single experiment should I run next." Answer that well and a few dozen evaluations are enough. Answer it by habit, with a grid or a space-filling plan fixed before you saw any result, and you will spend the whole budget confirming things the first ten runs already implied.

Bayesian optimization is the answer this session develops. It keeps a probabilistic surrogate of the objective, and at each step it uses an **acquisition function** to turn the surrogate's mean and uncertainty into a single score for "how worth it is to evaluate here." It evaluates at the maximum of that score, folds the result back into the surrogate, and repeats. The surrogate proposes and the acquisition decides. Active learning, in the second half of the session, is the same machinery pointed at a different goal: instead of finding one optimum, it refines the surrogate everywhere, by querying wherever the model is most ignorant. That is where the epistemic uncertainty from Lecture 13 does its work, because epistemic uncertainty is the reducible kind, the part a well-chosen experiment can actually remove.

Two numbers frame the payoff. In this session's demonstration, a Gaussian-process emulator of the airfoil data stands in for the expensive experiment, and two strategies get the same budget of 22 evaluations to find a quiet operating point. Bayesian optimization lands within 1 dB of the best the emulator allows in a median of 16 evaluations and does so in 75% of 40 random seeds; random search, over the identical budget, manages it in 3%. The second number is from the literature and is more humbling. When [Shields and colleagues (2021)](https://b-shields.github.io/files/2021-02-03-Nature.pdf) had fifty expert chemists and engineers optimize a real palladium-catalyzed reaction by hand and pitted them against a Gaussian process with expected improvement, the optimizer beat the human experts on both average efficiency and consistency. Domain knowledge, it turns out, is not a substitute for asking the surrogate where to look.

## Learning objectives

By the end of this session you should be able to:

- Explain the Bayesian-optimization loop and the role of the surrogate + acquisition.
- Choose and compare acquisition functions for exploration vs. exploitation.
- Set up an active-learning loop that chooses the next expensive query.

## The expensive black-box problem

```{index} black-box optimization, evaluation budget
```
```{index} pair: failure mode; grid search in high dimensions
```

Start by naming the setting precisely, because it is what rules out the methods you already know. The objective is a **black box**: you can evaluate it at a point and read off a number, but you have no formula and no gradient, the number may be noisy, and each evaluation costs real time or money. A gradient-based optimizer is out because there is no gradient to follow, and even a numerical gradient would cost several evaluations per step for a direction that a stiff, multimodal design landscape will not reward. What is left is search, and the two reflexive choices both waste the budget.

A grid search fails first and fastest. Ten levels per variable is a coarse grid, and in the airfoil problem's four design variables that is already ten thousand evaluations, more than a hundred times the budget. The **curse of dimensionality** is not a slogan here, it is the arithmetic: the grid grows as levels to the power of dimensions, so every variable you add multiplies the cost. A space-filling design, a Latin hypercube or a Sobol sequence of the kind Lecture 13 used to train the surrogate in the first place, spreads the points more cleverly, but it shares the fatal property of the grid. It is fixed in advance. It commits the entire budget before the first result comes back, so it cannot spend evaluation forty in light of what evaluations one through thirty-nine revealed.

That leaves random search, and it deserves more respect than its name suggests. [Bergstra and Bengio (2012)](https://www.jmlr.org/papers/v13/bergstra12a.html) showed that random search over a hyperparameter space finds models as good or better than grid search in a small fraction of the computation, and their explanation generalizes well beyond hyperparameters. Most problems have low effective dimensionality: only a few of the variables really matter, but which few differs from problem to problem. A grid wastes its resolution testing many distinct values along axes that turn out not to matter, while random search, by never repeating a coordinate, effectively samples more distinct values of the variables that do. In their thirty-two-dimensional study, random search matched a careful manual-plus-grid effort on four of seven datasets and beat it on one. The lesson to carry into this session is defensive: random search is cheap, parallel, and surprisingly strong, so it is the baseline every claim about Bayesian optimization has to beat. If your clever optimizer cannot outrun random draws, it is not earning the surrogate it carries.

## The Bayesian optimization loop

```{index} Bayesian optimization, acquisition function, surrogate model
```
```{index} pair: case study; Bayesian reaction optimization
```

The loop itself is four steps, and it is worth stating plainly before adding any detail. Fit a probabilistic surrogate to the data collected so far. Maximize an acquisition function over the design space to choose the next point. Evaluate the true, expensive objective there. Add the new observation and repeat. The surrogate is almost always a Gaussian process, for the reason Lecture 13 gave: it returns a full predictive distribution, a mean $\mu(x)$ and a standard deviation $\sigma(x)$ at every candidate point, and those two quantities are exactly what an acquisition function needs to reason about.

```{figure} figures/bo-loop.png
:alt: Three rows, each showing on the left a Gaussian-process fit to the Forrester test function with its 95% band and evaluated points, and on the right the expected-improvement curve with a dashed line at its maximum. Across the three iterations the chosen points move from 0.62 to 0.73 to 0.77, converging on the true global minimum near 0.757.
:width: 100%

The loop on the Forrester one-dimensional test function, starting from a four-point space-filling design that misses the global minimum near $x = 0.757$. Each row fits a GP (left), maximizes expected improvement (right), and evaluates at the dashed line. In three iterations the proposals walk from 0.62 to 0.73 to 0.77 and the optimizer settles into the global basin.
```

The figure shows why the probabilistic surrogate is doing the work. After the four-point start the GP has no data near the true minimum, but it does have wide error bars there, and expected improvement reads those wide bars as opportunity. It proposes a point in the promising gap, the evaluation confirms the objective is low, the band tightens, and the next proposal refines. Nothing here required a gradient or a formula for the objective. The optimizer only ever asked the surrogate two questions, where do you predict low values and where are you unsure, and combined the answers.

### When a surrogate beat fifty chemists

The reaction-optimization study mentioned above is the cleanest demonstration that this loop earns its keep on a real problem. [Shields and colleagues (2021)](https://b-shields.github.io/files/2021-02-03-Nature.pdf), publishing in *Nature*, framed a palladium-catalyzed direct-arylation reaction as a black-box optimization: the inputs were the categorical and continuous choices a chemist makes (ligand, base, solvent, temperature, concentration) and the output was yield, with each evaluation being an actual reaction run in the lab. They built a Gaussian-process optimizer with expected improvement, packaged as a tool called EDBO, and ran a controlled contest. Fifty expert chemists and engineers from academia and industry played the same optimization as a game, choosing their next experiments by intuition and experience, and their trajectories were compared against the optimizer's. Bayesian optimization outperformed the human experts on both average efficiency and consistency.

:::{admonition} What a practitioner should take from this
:class: tip

The result is not that chemists are bad at chemistry. It is that unaided human search is inconsistent, and inconsistency is expensive when every trial is a real experiment. The optimizer's advantage is that it never forgets a result, never over-weights the last surprise, and balances exploration against exploitation by the same rule every time. When you frame your own design problem, the question to ask is whether a human is currently choosing the next experiment by feel. If so, a surrogate with an acquisition function is very often a better and more auditable chooser, and the study is your evidence for proposing it.
:::

## Acquisition functions and the exploration–exploitation trade-off

```{index} expected improvement, upper confidence bound, probability of improvement, Thompson sampling
```
```{index} exploration-exploitation trade-off
```

Everything interesting about Bayesian optimization lives in the acquisition function, because that is where a single decision, where to evaluate next, gets made from two competing instincts. The first instinct is to **exploit**: evaluate where the surrogate's mean is best, near the incumbent, to squeeze out a little more. The second is to **explore**: evaluate where the surrogate's uncertainty is high, to rule regions in or out. Pure exploitation gets stuck in whatever basin it started near, because it never checks the unexplored region that might hold something better. Pure exploration wastes the budget mapping the whole space when you only need the best corner of it. An acquisition function is a specific rule for trading the two off, and the standard rules differ mainly in how they strike that trade.

```{figure} figures/acquisitions.png
:alt: Top, one Gaussian-process fit to five points on the Forrester function, with four dashed vertical lines marking where four acquisition functions would sample next. Bottom, the four scaled acquisition curves. Expected improvement, probability of improvement, and the lower confidence bound with kappa=1 all propose near x=0.74 to 0.78 where the objective is lowest, while the lower confidence bound with kappa=3 proposes at x=0.56 in a higher-uncertainty region.
:width: 100%

One surrogate, four acquisition rules, four different next experiments. Three of the rules exploit the known-good basin near $x = 0.78$; raising the confidence-bound weight from $\kappa = 1$ to $\kappa = 3$ pushes the fourth out to $x = 0.56$ to reduce uncertainty instead. The rule you pick is a policy for how much to explore.
```

**Expected improvement** (EI) is the default for good reason: it needs no tuning knob and it balances the two instincts automatically. It scores a candidate by how much you expect it to beat the incumbent best. Writing $\tau$ for the best value seen so far and taking the case of minimization, its closed form is

$$
\mathrm{EI}(x) = (\tau - \mu(x))\,\Phi(Z) + \sigma(x)\,\phi(Z), \qquad Z = \frac{\tau - \mu(x)}{\sigma(x)},
$$

where $\Phi$ and $\phi$ are the standard-normal CDF and PDF. The first term rewards a low predicted mean and the second rewards high uncertainty, so a point is attractive either because it looks good or because it is unknown, and most attractive when it is both. EI is zero wherever $\sigma(x) = 0$, which is to say at points you have already evaluated, so the optimizer never wastes a run repeating itself.

**Upper confidence bound** (UCB), or its lower-confidence-bound twin for minimization, exposes the trade-off as an explicit dial: it scores a candidate as $\mu(x) \pm \kappa\,\sigma(x)$. A small $\kappa$ leans on the mean and exploits; a large $\kappa$ leans on the uncertainty and explores. The figure makes the dial visible, with $\kappa = 1$ staying in the good basin and $\kappa = 3$ striking out to the uncertain region. The honesty of UCB is that it forces you to own the trade-off by choosing $\kappa$ yourself, where EI hides the choice inside its expectation.

**Probability of improvement** (PI) scores the probability that a candidate beats the incumbent at all, $\Phi\big((\tau - \mu(x))/\sigma(x)\big)$ for minimization. It is the oldest of these rules and the greediest, because it treats a tiny improvement and a huge one as equally good, so without an added margin it clusters its proposals right next to the incumbent and under-explores. **Thompson sampling** takes a different route entirely: it draws one random function from the surrogate's posterior and evaluates at that draw's optimum. Because each step samples a fresh function, the randomness itself supplies the exploration, and the method needs no explicit acquisition value at all.

:::{admonition} The sign of the improvement is the bug you will actually hit
:class: warning

Every formula above is written for minimization, with the improvement as $\tau - \mu$. Half the libraries and most of the textbooks are written for maximization, with the improvement as $\mu - \tau$. Mixing the two conventions does not throw an error; it produces an optimizer that confidently walks uphill while you are trying to go down. Before you trust an acquisition, evaluate it by hand at two points, one clearly good and one clearly bad, and check that the good one scores higher. The other quiet trap is $\kappa$: the multiplier in $\mu \pm \kappa\sigma$ is not the same symbol as the $\beta_t$ in the original GP-UCB paper, which sits under a square root, so copying a schedule for $\beta_t$ straight into a $\kappa$ slot will over-explore by a lot.
:::

## Extensions engineers actually need

```{index} constrained Bayesian optimization, multi-objective optimization, Pareto front, batch Bayesian optimization, multi-fidelity optimization
```
```{index} BoTorch
```

The plain loop optimizes one unconstrained objective one evaluation at a time, and real design problems rarely arrive in that form. Four extensions cover most of the gap, and they are worth knowing by name because the tooling implements them directly.

**Constrained** optimization is the common case: maximize concrete strength subject to a cost ceiling and a carbon budget, where feasibility is itself something you can only estimate. The standard move is to fit a separate probabilistic model for each constraint and weight the acquisition by the predicted probability that a candidate is feasible, so the optimizer is drawn toward points that are both promising and likely to satisfy the limits. **Multi-objective** problems go further and give up on a single best point altogether. When you want high strength and low cost and low carbon at once, there is no single winner but a **Pareto front** of designs, each of which cannot be improved on one objective without sacrificing another, and the job of the optimizer is to map that front efficiently. The acquisition function that does this, expected hypervolume improvement (qEHVI and its noisy variant qNEHVI), scores a candidate by how much it would grow the volume dominated by the known front.

The last two extensions are about spending the budget in parallel and at different resolutions. **Batch** Bayesian optimization proposes several points at once, because if you have four autoclaves or a cluster you want to run four experiments this round, not one, and the batch acquisitions are built so the four proposals are diverse rather than four copies of the same greedy pick. **Multi-fidelity** optimization mixes cheap, coarse evaluations with expensive, accurate ones, a coarse mesh and a fine mesh, a short simulation and a converged one, and lets the optimizer spend many cheap queries to decide where the few expensive ones are worth it. In practice these are reached for through a library rather than coded from scratch. **BoTorch**, built on PyTorch and GPyTorch, provides Monte Carlo acquisition functions (the ones whose names start with `q`) and the GP models to go with them, and [Ax](https://ax.dev/docs/tutorials/quickstart/) wraps BoTorch in a higher-level campaign manager. One caution on the tooling: Ax reorganized its interface in its 1.0 release around a new top-level `Client`, and the older `AxClient` service API that most tutorials still show is deprecated and slated for removal, so check which version a tutorial targets before following it.

## Active learning

```{index} active learning, uncertainty sampling, query-by-committee
```
```{index} pair: case study; A-Lab
```

Active learning is the same loop with the goal moved. Bayesian optimization spends its budget to find one excellent point and is happy to leave most of the design space a blur. Active learning spends its budget to make the surrogate good everywhere, because sometimes the deliverable is the emulator itself, a model that will be queried thousands of times later in a design sweep or a control loop, and its worst region is what will bite. The question changes from "where is the objective best" to "where is my model most ignorant, so that one label there teaches it the most."

The simplest strategy follows directly from Lecture 13's uncertainty. **Uncertainty sampling** queries the point of highest posterior variance, on the argument that the model has the most to learn where it is least sure. This is exactly the epistemic uncertainty from the previous session put to use: epistemic uncertainty is the reducible kind, the part that more data removes, so aiming queries at it is aiming them where they will actually reduce error rather than at irreducible noise. **Query-by-committee** is the ensemble version, and it connects to Lecture 13's deep ensembles: train several models, and query where they disagree most, because disagreement among competent models marks a region the data has not yet pinned down.

```{figure} figures/active-learning.png
:alt: Two panels of a Gaussian process on the Forrester function. Left, before: five points on the left and one at 0.9 leave a wide gap between 0.44 and 0.9, with a red dashed line at the highest-uncertainty point near 0.69. Right, after querying there: the uncertainty band in that region has collapsed and the GP mean now tracks the true objective's dip.
:width: 100%

One active-learning step. The widest gap in the data sits between $x = 0.44$ and $x = 0.9$, so the highest posterior variance is there and the query goes to $x = 0.69$. Conditioning on that one point (at fixed hyperparameters) shrinks the total posterior standard deviation by 6.5% and lets the surrogate finally see the dip it had been blind to.
```

The distinction from Lecture 13 is worth stating carefully, because the figure above holds the GP hyperparameters fixed on purpose. At fixed hyperparameters, conditioning a GP on a new observation can only reduce its posterior variance, everywhere, which is the clean statement of why active learning works. In practice you refit the hyperparameters as data arrives, and a genuinely surprising observation can widen the bands before it narrows them, once the model realizes the world is rougher than it thought. That is not a failure of the method, it is the method learning, but it is why you evaluate active learning by held-out error after several rounds rather than by whether any single query made the bands smaller. [Settles' survey](https://burrsettles.com/pub/settles.activelearning.pdf) is the standard map of the strategies and the settings they suit.

### An autonomous lab, and a number worth checking

The most striking recent demonstration of active learning at scale is the A-Lab, reported by [Szymanski and colleagues (2023)](https://escholarship.org/uc/item/4w49b5cb) in *Nature*. It is an autonomous laboratory that plans syntheses, runs them on robotic equipment, characterizes the products, and uses an active-learning loop grounded in thermodynamics to decide which recipe to try next when the first attempt fails. Over seventeen days of continuous operation the system worked through fifty-eight target compounds and produced forty-one of them, a throughput no human lab matches, and it is a clean illustration of the closed loop this session describes: propose, evaluate, learn, propose again, with no human in the inner loop.

:::{admonition} What a practitioner should take from this
:class: tip

The headline figure that circulated was a 71% success rate, and this is a good place to practice the course's habit of checking a number against its source. The primary paper reports forty-one of fifty-eight targets over seventeen days, and 71% is simply that ratio, so the arithmetic is fine. The claim underneath it is what drew scrutiny. Materials scientists including Palgrave and Schoop published an analysis arguing that many of the "novel" compounds were ordered or substituted variants of already-known phases and that the automated crystal-structure refinements had misread the data, a critique the senior author answered by saying the goal had been to demonstrate autonomy rather than to produce publication-grade structure analysis. Both things are true at once: the autonomous active-learning campaign is real and impressive, and the specific count of genuinely new compounds is contested. When you cite a result like this, cite the throughput you can verify (forty-one of fifty-eight in seventeen days) and be honest that the novelty claim is disputed, rather than repeating the tidier headline.
:::

## Where this pushes back

```{index} pair: failure mode; single-seed Bayesian optimization
```
```{index} pair: metric; simple regret
```

Bayesian optimization is stochastic, and this is the first thing that will mislead you. The initial design is random, the GP hyperparameter fit has local optima, and the acquisition is itself optimized by a search with random restarts, so two runs from the same code find different answers. A single run that finds the optimum in twelve evaluations is a sample of size one, and the next run might take thirty. The only honest way to report Bayesian optimization is over multiple seeds, as a distribution of the metric against evaluation count, and always against a random-search baseline.

```{figure} figures/bo-vs-random.png
:alt: Best sound pressure level found versus number of expensive evaluations, for Bayesian optimization in red and random search in grey, each a median over 40 seeds with interquartile bands. Bayesian optimization drops faster and reaches a dotted line marking the emulator's achievable floor; random search lags well above it. 
:width: 100%

The honest comparison, and the reason it takes 40 seeds to draw. Bayesian optimization (red) and random search (grey) get the same 22-evaluation budget on the airfoil emulator; each curve is the median best-so-far over 40 seeds with its interquartile band. Bayesian optimization reaches within 1 dB of the emulator's floor in a median of 16 evaluations and in 75% of seeds, against 3% for random search. A single seed of either could have fallen anywhere in those bands.
```

The convergence metric worth naming is **simple regret**, the gap between the best value found so far and the true optimum, plotted against the number of evaluations spent; the figure above is a simple-regret curve in disguise, with the emulator's floor standing in for the true optimum. Reporting it as a median with a band across seeds is the difference between evidence and an anecdote.

Beyond stochasticity, the method has real limits. A Gaussian process costs $O(n^3)$ to fit in the number of observations, which is a non-issue in the few-dozen-to-few-hundred regime Bayesian optimization lives in and a wall beyond it, so BO is a tool for expensive objectives and small budgets, not for cheap objectives you could just evaluate a million times. It struggles in high dimensions, past roughly fifteen or twenty design variables, because the acquisition function is itself a global optimization over that space and the surrogate's uncertainty spreads too thin to guide it. And the greedy failure is always waiting: an acquisition tuned to exploit, or a $\kappa$ set too low, gets stuck in the first decent basin it finds and never checks the rest, which is precisely the trap the loop figure was constructed to escape. The discipline that keeps all of this honest is budget accounting. The entire justification for the surrogate is to avoid the expensive evaluation, so an optimizer that quietly made ten thousand oracle calls to tune itself has not saved anything, and you should count and report the expensive evaluations as the currency they are.

## In-class demo

The notebook [`l14-bayesopt-design.ipynb`](l14-bayesopt-design.ipynb) builds the loop twice. It opens on the Forrester function with a Gaussian process from scikit-learn and an expected-improvement function written out in a few lines, so the acquisition is visible rather than hidden in a library, and you can watch the proposals walk into the global basin exactly as the first figure shows. It then rebuilds the same loop in BoTorch on the airfoil emulator, the tool you would actually reach for, to show that the production version is the same four steps with the GP and the acquisition swapped for their scalable implementations. The honest-evaluation section races Bayesian optimization against random search over many seeds and plots the regret curves with bands, and the point to watch is how wide those bands are, because it is what makes a single-seed claim untrustworthy. The demo closes on one active-learning step, querying the highest-variance point and watching the uncertainty shrink. The two moments to catch are the sign check on the hand-written acquisition, where a flipped convention sends the optimizer the wrong way, and the seed sweep, where the same code gives visibly different single runs.

## Summary

The arc that began with expensive simulations and surrogates closes here with the design loop that surrogates were built for. Lecture 13 gave you a model that knows where it is uncertain; Lecture 14 spends that uncertainty, using an acquisition function to turn a mean and a standard deviation into a decision about the single most valuable next experiment. Bayesian optimization aims that decision at finding an optimum and active learning aims it at improving the model, but they are one mechanism, and the same GP and the same uncertainty drive both. The engineering payoff is concrete: when each evaluation is a cure, a run, or a synthesis, choosing the next one well turns a hopeless thousand-evaluation search into a feasible few-dozen one. Carry three habits out of the session. Always beat a random-search baseline, always report over multiple seeds, and always count the expensive evaluations, because they are the whole point.

## Resources

- [Frazier, "A Tutorial on Bayesian Optimization" (arXiv:1807.02811)](https://arxiv.org/abs/1807.02811). The cleanest single-author introduction; read it for the loop, expected improvement, and the extensions to parallel and multi-fidelity settings.
- [Shahriari et al., "Taking the Human Out of the Loop: A Review of Bayesian Optimization" (2016)](https://www.cs.ox.ac.uk/people/nando.defreitas/publications/BayesOptLoop.pdf). The standard survey; the reference for the taxonomy of acquisition functions and the closed forms used above (author's copy).
- [Bergstra & Bengio, "Random Search for Hyper-Parameter Optimization," JMLR 13 (2012)](https://www.jmlr.org/papers/v13/bergstra12a.html). Why random search is the baseline to beat, and the low-effective-dimensionality argument for why grid search wastes trials.
- [Settles, "Active Learning Literature Survey," UW-Madison TR 1648 (2009)](https://burrsettles.com/pub/settles.activelearning.pdf). The map of active-learning strategies and settings; author's hosted copy.
- [Shields et al., "Bayesian reaction optimization as a tool for chemical synthesis," Nature 590 (2021)](https://b-shields.github.io/files/2021-02-03-Nature.pdf). The fifty-chemists contest; the case for BO over unaided expert search on real experiments (author's copy).
- [Frazier & Wang, "Bayesian Optimization for Materials Design" (arXiv:1506.01349)](https://arxiv.org/abs/1506.01349). The engineering framing, with the knowledge-gradient acquisition for choosing experiments; assign the arXiv version, not the paywalled chapter.
- [BoTorch documentation](https://botorch.org/docs/introduction) and [Ax quickstart](https://ax.dev/docs/tutorials/quickstart/). The production tooling; note Ax's 1.0 `Client` API, which replaces the older service API most tutorials still show.

## Assignment

The miniproject (Assignment 7) is under way. It launched in Lecture 13 and runs through the dedicated Week 8 sessions, asking you to take an engineering dataset from raw data through a tracked, reproducible workflow to a surrogate model with honest uncertainty quantification, and the Bayesian-optimization and active-learning loops from this session are the natural way to demonstrate that the uncertainty is good for something. The full specification, including the deliverables and the grading breakdown, is in [`course/miniproject.md`](../../course/miniproject.md); this page does not restate it.

## Practice module

<a href="../../game/#/l14"><strong>Practice module for this session</strong></a>, about ten
minutes of questions drawn from this session's notes, slides and demo. It runs entirely in
your browser, the questions are selected from your Andrew ID, and it ends by producing a PDF
you upload for participation credit.
