# Case study · Searching 800,000 shape memory alloys with expected improvement

:::{admonition} At a glance
:class: tip
- **Field**: Materials science and engineering
- **Connects to**: [L15 · Bayesian optimization](../lectures/l15/notes.md), [L14 · Uncertainty quantification](../lectures/l14/notes.md), [L9 · Regression](../lectures/l09/notes.md)
- **Primary source**: Xue, Balachandran, Hogden, Theiler, Xue and Lookman (2016), *Nature Communications* 7, 11241
:::

## Why this matters

Alloy design poses the same problem as the reactor in [L15](../lectures/l15/notes.md):
every evaluation is expensive, the budget is a few dozen experiments, and there are far too
many candidates to test. The reactor has one or two knobs. An alloy with three substituted
elements, each adjustable in steps of 0.1%, has hundreds of thousands of candidate
compositions, and each one has to be melted, rolled, heat treated and measured.

Xue and colleagues at Los Alamos National Laboratory and Xi'an Jiaotong University ran
that search for nickel-titanium shape memory alloys with low thermal hysteresis. They
started from 22 measured alloys, used a regression model with an uncertainty estimate to
propose four new compositions at a time, synthesized them, and repeated. After nine rounds
and 36 new alloys, they had found 14 alloys better than anything in their starting data.
The paper is open access, and its design choices map closely onto the vocabulary of L14
and L15.

## The setting

A shape memory alloy changes crystal structure when it is heated or cooled through a
transformation temperature, between a high-temperature austenite phase and a
low-temperature martensite phase. The transformation on heating and the one on cooling do
not happen at the same temperature. The gap is the thermal hysteresis, written $\Delta T$.
The paper links hysteresis to fatigue, citing earlier work in which 60 heating and cooling
cycles shifted the transformation temperature of Ni$_{50}$Ti$_{50}$ by 25 K. The design goal was the
composition with the smallest $\Delta T$, so this is a minimization problem.

The authors restricted the search to one family, Ni$_{50-x-y-z}$Ti$_{50}$Cu$_x$Fe$_y$Pd$_z$.
Copper, iron and palladium replace part of the nickel, each in steps of 0.1%, subject to
limits on each element (at least 30% nickel, at most 20% copper, 5% iron and 20% palladium).
The paper counts $N = 797{,}504$ possible alloys in this space. The group had synthesized 22
of them under identical processing conditions, to keep processing and microstructure from
adding variation. The best of those 22 had $\Delta T = 3.15$ K. $\Delta T$ was measured by differential scanning calorimetry (DSC) as the difference between the
endothermic peak temperature on heating and the exothermic peak on cooling.

The model did not see compositions directly. Each alloy was described by six features drawn
from metallurgical knowledge, including Pauling electronegativity, the valence electron
number (VEN), the metallic radius and the Pettifor chemical scale. Each feature was computed
as a composition-weighted average over the elements present. The authors chose them from prior
work linking transformation temperatures to valence electron concentration and hysteresis
to the atomic size of the dopants.

## What happened

The loop ran for nine iterations, synthesizing four alloys per iteration, for 36 new
compositions in total. Fourteen of the 36 had $\Delta T$ below 3.15 K, the best value in the
starting set. The best was Ti$_{50.0}$Ni$_{46.7}$Cu$_{0.8}$Fe$_{2.3}$Pd$_{0.2}$, found in the
sixth iteration, with $\Delta T = 1.84$ K by DSC. The paper reports this as 42% better than
the best training alloy. Over 60 thermal cycles its transformation temperature shifted by
about 0.02 K.

The campaign did not improve steadily. In the first iteration one of the four proposed
alloys showed no martensitic transformation at all, while another gave the second-best
$\Delta T$, as the paper reports. The spread of measured $\Delta T$ was large in iterations 1 and 2,
narrowed through iterations 3 to 6, and widened again from iteration 7 on. Plotted against
the average VEN, the loop concentrated near a VEN of about 6.95 in the middle iterations and
then moved away from it. The authors state that after the sixth iteration their design
"drifts away from the apparent global minimum". They interpret the late spread as the
selection rule leaving a region it had already sampled to look for other minima, and they
note it could be misread as overfitting.

To check that the result was not luck, the authors compared the 36 designed alloys with the
22 original ones using a Mann-Whitney test and found the designed set significantly better
($P < 0.001$). They also computed that, if the designed alloys had been drawn from the same
distribution as the originals, the chance that 14 or more of the lowest $\Delta T$ values
would land in the designed set is $3.7 \times 10^{-4}$.

## Why it happened

The loop is the one in L15: fit a surrogate to everything measured so far, score every
unmeasured candidate with an acquisition function, run the best-scoring experiments, add
the results, and refit. Three choices adapted it to alloys.

**A surrogate that is not a Gaussian process.** The authors tried three regressors from
scikit-learn: a Gaussian process model, and support vector regression (SVR) with a radial
basis function kernel and with a linear kernel. They write that SVR predicted better on
their data, but SVR gives only a point prediction. To get an uncertainty they used the
bootstrap: resample the training alloys with replacement, refit, and use the spread. They
predicted $\Delta T$ for every alloy in the search space with 1,000 bootstrap samples and took
the mean as $\mu$ and the spread as $\sigma$.

**Expected improvement, written for a minimum.** The paper's EGO selector maximizes
$\sigma[\phi(z) + z\Phi(z)]$ with $z = (\mu^* - \mu)/\sigma$, where $\mu^*$ is the smallest
$\Delta T$ measured so far. They also tried a selector they call knowledge gradient (KG),
which is the same formula with $\mu^*$ replaced by the smaller of the best measured value and
the best predicted value anywhere in the unexplored space. A greedy selector (Min) picked the
lowest predicted $\Delta T$, and a Random selector ignored the model.

**A rule for picking the rule.** With 22 data points there is no way to know in advance which
regressor and selector pair will search well. The authors simulated the search inside their
training set. They gave each pair a few randomly chosen alloys, let it pick the rest one at a
time, and counted the picks needed to reach the best alloy, repeating this 2,000 times per
pair and starting size. Some pairs did worse than random picking. The greedy GP pair was best
when it started from 2 or 3 alloys and then fell behind. From 4 to 8 starting alloys, SVR with
the radial kernel did best under both KG and EGO, with nearly identical results, and the
authors chose SVR with KG.

Four alloys could be synthesized at a time, so the loop needed a batch. They built it with
the kriging believer heuristic: take the top candidate, add its predicted $\Delta T$ to the
data as though it had been measured, refit, pick the next, and repeat four times.

## Connections to the lectures

The section on the Bayesian optimization loop in [L15](../lectures/l15/notes.md) defines
the incumbent, the budget and the four-step loop, and all three appear here: the incumbent
starts at 3.15 K, the budget spent was 36 syntheses, and the loop ran nine times. The L15 section
on acquisition functions writes EI for a maximum as
$(\mu - f^*)\Phi(z) + \sigma\phi(z)$. The paper's form is the same expression for a minimum,
with the sign of the gap flipped. Its $\sigma z \Phi(z)$ term is the exploitation term and
its $\sigma\phi(z)$ term is the exploration term. The paper also describes the two limits
the way L15's section on exploration and exploitation does: as $\sigma \to 0$ the rule picks
the lowest predicted value, and as $\sigma$ grows it picks the most uncertain candidates. The
L15 subsection on Donald Jones and EGO is the paper's own reference 7.

The two problems also differ. The reactor's surrogate is a GP over one or two continuous
inputs. Here the inputs are six composition-weighted features, the candidates are a finite
list of 797,482 unmeasured alloys, and the surrogate predicts every one of them. The batch of
four matches L15's "Extensions engineers need", where a lab with four reactors chooses four
experiments at once; the kriging believer is one heuristic for that job. The 2,000-repeat
comparison against random picking follows L15's section on comparing optimizers over several
seeds, and the pairs that lost to random show why a baseline belongs in that comparison.
For the list in L15's section "Where Bayesian optimization is used", this is a materials
entry, and a reminder that the loop runs on any surrogate that supplies a $\mu$ and a
$\sigma$.

The uncertainty came from the section on bootstrap and ensembles in
[L14](../lectures/l14/notes.md), and that section's caveats apply directly. A bootstrap
spread estimates how much the fitted function would change with a new data set of the same
size. It is a confidence interval, so it leaves out measurement noise, and it can be small where the
model is biased, which L14 warns happens far outside the domain of the data. With 22
training alloys and nearly 800,000 candidates, most of the search space is outside that
domain. L14's limitations section adds that a design loop creates points unlike its
training data on purpose. The main text of the paper does not report a calibration check of
the bootstrap $\sigma$, so how well the spread tracked real error is not known from it.

[L9](../lectures/l09/notes.md) supplies two more pieces. SVR is not one of L9's four model
families, but L9's section on those families gives the reason for comparing several: no
model wins on every problem. The authors cite a no-free-lunch theorem for the same reason
(Wolpert and Macready's version for optimization, not the supervised-learning version in
L9). The six descriptors are feature engineering in the sense of L9's section on linear
regression, with knowledge of the system put into the features.

:::{admonition} What a practitioner should take from this
:class: note
- Any regressor can drive the loop if you can attach a $\sigma$ to it. A bootstrap over a
  model that predicts well on your data is a legitimate choice, but it measures variance
  only, so check it against held-out measurements before you trust it far from the data.
- Choose the surrogate and acquisition function by simulating the search on data you
  already have, with many random restarts and a random-picking baseline. Expect some
  combinations to lose to random.
- If you can run several experiments at once, plan the batch explicitly (kriging believer,
  or a batch acquisition such as qLogEI) rather than taking the top four EI scores, which
  can sit next to each other.
- Read a widening spread late in a campaign against your acquisition function before
  calling it overfitting. An EI-based rule is built to leave a region it has already
  exploited.
- Decide every property you need before the campaign. This loop optimized $\Delta T$ alone,
  and the paper reports that its alloys came out with relatively high transformation
  temperatures, which were not designed for.
- Report the incumbent at each iteration, the number of syntheses, and a test against the
  starting data, as this paper does, so a reader can tell search from luck.
:::

## Sources

- Xue, D., Balachandran, P. V., Hogden, J., Theiler, J., Xue, D. and Lookman, T. (2016).
  [Accelerated search for materials with targeted properties by adaptive design](https://www.nature.com/articles/ncomms11241).
  *Nature Communications* 7, 11241, [doi:10.1038/ncomms11241](https://doi.org/10.1038/ncomms11241).
  The primary source for every number on this page; open access, with the selector formulas
  and the selection-by-simulation procedure in Methods. Also in PubMed Central as
  [PMC4835535](https://pmc.ncbi.nlm.nih.gov/articles/PMC4835535/).
- Jones, D. R., Schonlau, M. and Welch, W. J. (1998).
  [Efficient global optimization of expensive black-box functions](https://www.stat.ubc.ca/~will/docs/JonSchWel1998_global_optimization.pdf).
  *Journal of Global Optimization* 13, 455 to 492. The EGO paper the alloy loop is built on,
  and the one L15 uses; this link is an author-hosted copy.
- Efron, B. (1979). [Bootstrap methods: another look at the jackknife](https://doi.org/10.1214/aos/1176344552).
  *Annals of Statistics* 7, 1 to 26. The origin of the resampling method that supplied the
  alloy model's $\sigma$; L14 discusses what it does and does not measure.
