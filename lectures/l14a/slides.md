---
marp: true
theme: course
paginate: true
header: "06-763 · L14a"
footer: "Systems and Toolchains for AI Engineers"
---

<style>
/* a figure alone in its paragraph is centered, and so is every table */
section p:has(> img:only-child) { text-align: center; }
section table { margin-left: auto; margin-right: auto; font-size: 0.78em; }
.cols { display: grid; gap: 1.1em; align-items: center; }
.cols-even { grid-template-columns: 1fr 1fr; }
.cols-lc { grid-template-columns: 1.25fr 1fr; }
.small { font-size: 0.72em; }
.source { font-size: 0.6em; color: #5c5c5c; }
.red { color: #c41230; }
/* widgets here carry two rows of controls, so give the plot a little less height */
section .cw.compact svg { max-height: 350px; }
section p.takeaway { text-align: center; font-weight: 700; font-size: 0.82em; margin: 0.5em 0 0; }
</style>

<!-- _class: title -->

# Lecture 14a: Uncertainty quantification in machine learning

## Week 7, Machine learning and deep learning

**Systems and Toolchains for AI Engineers**

<!--
Why 6, what UQ is 12, calibration 10, GPs 17, ensembles 14, conformal 13, pycse 7, close 5.
About 84 minutes, then the notebook and questions.
-->

---

## Roadmap

1. **Why**: calibrated intervals that covered 26% on new chemistry
2. **What UQ is**: aleatoric, epistemic, and three kinds of interval
3. **Calibration**: how to check any uncertainty, before choosing a method
4. **Gaussian processes**: what the band promises, and three ways it fails
5. **Bootstrap and ensembles**: what the spread measures, and a worked recalibration
6. **Conformal prediction**: a guarantee, and the one condition it needs
7. **Models with uncertainty built in**: pycse

---

<!-- _class: section -->

# Why this matters

---

## Intervals that held, until the chemistry changed

- Neural-network force fields: DFT-quality energies, far cheaper
- Useful only if you know when to trust them
- Conformal prediction + distances in the network's latent space
- In distribution: **calibrated and sharp**; calibration takes minutes against ~11,000 GPU-hours of training
- Trained on QM9 **without fluorine**, tested **with** it: 90% intervals covered **26%**

<p class="source"><a href="https://arxiv.org/abs/2208.08337">Hu, Musielewicz, Ulissi &amp; Medford, MLST 2022</a> (CMU ChemE co-authors)</p>

<!--
Nothing in the method broke. Its one condition, that test structures resemble calibration
structures, was not met. Come back to this case in the conformal section.
-->

---

## Three numbers from today

| Method | Claimed | Measured |
|---|---|---|
| GP on 5 points, settings by maximum likelihood | 95% | **78%** (median of 200 data sets) |
| Five-network ensemble, concrete strength | 90% | **79%**, then **90%** after one scale factor |
| Split conformal, strongest mixes held out | 90% | **56%** |

All from `lectures/l14a/figures/make_figures.py`

---

<!-- _class: section -->

# What uncertainty quantification is

---

<!-- _class: definition -->

## Uncertainty quantification

<div class="definition">

**Uncertainty quantification**: attaching to each prediction a distribution or an interval, together with a claim about how often the truth falls inside it.

</div>

- "42 ± 6 MPa" says nothing on its own
- "... and intervals stated this way contain the measured strength 90% of the time" can be checked

---

## Aleatoric and epistemic

<div class="definition">

**Aleatoric**: scatter in the data itself, which more data does not remove. **Epistemic**: what the model does not know yet, which more data in the right place reduces.

</div>

- Practical test: epistemic if the modeler "sees a possibility to reduce" it
- From structural reliability, carried into ML as reducible against irreducible

<p class="source"><a href="https://doi.org/10.1016/j.strusafe.2008.06.020">Der Kiureghian &amp; Ditlevsen, Struct. Saf. 2009</a> (paywalled) · <a href="https://arxiv.org/abs/1910.09457">Hüllermeier &amp; Waegeman, Mach. Learn. 2021</a></p>

---

## Aleatoric and epistemic, live

<div class="cw compact" data-widget="uq-sources"><img src="figures/widget-uq-sources.png" alt="A Gaussian process band split into a noise part and a model part, with sliders for noise and number of points"></div>

<!--
Push points up: the dark band collapses, the light band does not. Then push noise up.
Point at the gray region: no data, the dark band returns to the prior.
-->

---

## Aleatoric and epistemic, the split depends on the model

- Concrete strength scatters at fixed proportions, partly from **curing temperature**
- No temperature input: that scatter is noise (aleatoric)
- Temperature as an input: the same scatter is learnable (epistemic)
- Two more sources for a surrogate:
  - **Model inadequacy**: "No model is perfect"
  - **Code uncertainty**: the simulator was not run at this input

<p class="source"><a href="https://arxiv.org/abs/1910.09457">Hüllermeier &amp; Waegeman sec. 2.3</a> · <a href="https://www.asc.ohio-state.edu/statistics/comp_exp/jour.club/kennedy01.pdf">Kennedy &amp; O'Hagan 2001</a>, sec. 2.1, six sources</p>

---

## Three kinds of interval

| Interval | Covers | Meaning |
|---|---|---|
| Confidence | the function $f(x)$ | the procedure covers in repeated use |
| Credible | the function $f(x)$ | posterior probability |
| **Prediction** | a new measurement $f(x) + \varepsilon$ | includes the noise |

- "A prediction interval necessarily encloses the corresponding confidence interval"
- A specimen tested against a 40 MPa spec is a **new measurement**
- Every coverage number today is for prediction intervals

<p class="source"><a href="https://proceedings.neurips.cc/paper/1996/hash/7940ab47468396569a906f75ff3f20ef-Abstract.html">Heskes, NIPS 1996</a> · <a href="https://sites.stat.columbia.edu/gelman/book/">Gelman et al., BDA3 sec. 1.1</a></p>

---

## Why ML makes this hard

- **Training residuals are too small**: maximum likelihood "systematically underestimates σ²"
- **Big networks are overconfident**: ResNet confidence "substantially higher than its accuracy"
- **ReLU networks extrapolate in straight lines**: proved for classifiers, Theorem 3.1
- **No data describes the region without data**: every method substitutes an assumption

<p class="source"><a href="https://proceedings.mlr.press/v121/laves20a.html">Laves et al., MIDL 2020</a> · <a href="https://arxiv.org/abs/1706.04599">Guo et al., ICML 2017</a> · <a href="https://arxiv.org/abs/1812.05720">Hein et al., CVPR 2019</a></p>

---

## Aleatoric and epistemic, a question

<div class="clicker" data-tag="l14a-more-data" data-seconds="40" data-answer="C" data-hint="Think about what happens to the light band and the dark band when the n slider goes up." data-why="C. Repeating measurements at the same conditions pins down f there, so the model's own uncertainty shrinks. The scatter between repeats is the noise, and no number of repeats removes it." data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**You re-test 50 more cylinders of mixes you already tested. Which uncertainty in the strength prediction for those mixes goes down?**

<ol class="clicker-opts">
<li>Aleatoric only</li>
<li>Both, equally</li>
<li>Epistemic only</li>
<li>Neither, since the mixes are not new</li>
</ol>

</div>
<aside class="clicker-panel">
<img src="figures/clicker-qr.png" alt="QR code linking to the vote page">
<div class="clicker-url">clicker.f26-06763.workers.dev</div>
<button class="clicker-start">Start voting</button>
<div class="clicker-timer">40</div>
<div class="clicker-count">no votes yet</div>
</aside>
</div>

<!--
Common wrong answer: D, from students who think only new inputs help. Repeats sharpen f at
those inputs. Second most common: B, confusing a better estimate of the noise with less noise.
-->

---

<!-- _class: section -->

# Calibration: checking an uncertainty

---

## Calibration

<div class="definition">

**Calibrated**: stated probabilities match what happens; 90% intervals contain the measured value 90% of the time.

</div>

- **Coverage**: fraction of held-out points inside their interval
- **Reliability diagram**: observed against nominal coverage at several levels
- Below the diagonal: **overconfident**, intervals too narrow

<p class="source"><a href="https://arxiv.org/abs/1807.00263">Kuleshov, Fenner &amp; Ermon, ICML 2018</a>, Eq. 3</p>

---

## Calibration, sharpness

<div class="definition">

**Sharpness**: how narrow the predictive distributions are, a property of the forecasts alone.

</div>

- Goal: "maximizing the sharpness ... subject to calibration"
- **Climatological forecaster**: ignore the inputs, always issue the long-run spread

| Concrete, 90% intervals | Coverage | Width |
|---|---|---|
| Climatology (training 5% to 95% quantiles) | 91% | 55.9 MPa |
| Rescaled ensemble (this lecture) | 90% | 22.2 MPa |

<p class="source"><a href="https://www.stat.washington.edu/raftery/Research/PDF/Gneiting2007jrssb.pdf">Gneiting, Balabdaoui &amp; Raftery, JRSS B 2007</a> (author's copy)</p>

---

## Calibration, proper scoring rules

- **Proper**: the expected score is best when the forecast is the true distribution
- **NLL**: $\tfrac12\log(2\pi\sigma^2) + \tfrac{(y-\mu)^2}{2\sigma^2}$; punishes a confident miss; unbounded
- **CRPS**: distance between predicted CDF and a step at $y$; "generalizes the absolute error"
- Report one of them **with** coverage and width

<p class="source"><a href="https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jasa.pdf">Gneiting &amp; Raftery, JASA 2007</a> (author's copy)</p>

---

## Calibration, on average and locally

- 90% overall can be 100% on easy points and 70% on hard ones
- **Consistency**: calibrated given the predicted σ
- **Adaptivity**: calibrated given the input $x$
- Good consistency "does not imply a good adaptivity"
- A held-out **region** of input space is an adaptivity check

<p class="source"><a href="https://arxiv.org/abs/2309.06240">Pernot, APL Mach. Learn. 2023</a> · <a href="https://arxiv.org/abs/1905.11659">Levi et al., Sensors 2022</a></p>

---

## Calibration, recalibration and its limit

- **Scaling**: multiply every σ by one factor $s$ fitted on held-out data
- **Isotonic**: a monotone map from predicted to observed probability
- Both assume future data resemble the held-out data
  - Kuleshov: needs "enough i.i.d. data"
  - Ovadia: temperature-scaling error "increases significantly as the shift increases"
- Catalysis example: several metrics side by side ([Tran et al. 2020](https://arxiv.org/abs/1912.10066), CMU ChemE)

<p class="source"><a href="https://proceedings.mlr.press/v121/laves20a.html">Laves 2020</a> · <a href="https://arxiv.org/abs/1807.00263">Kuleshov 2018</a> · <a href="https://arxiv.org/abs/1906.02530">Ovadia et al., NeurIPS 2019</a></p>

---

<!-- _class: section -->

# Gaussian processes

---

## Gaussian processes

<div class="definition">

**Gaussian process**: a probability distribution over functions, set by a kernel that says how strongly values at two inputs are correlated.

</div>

![w:820](figures/gp-prior-posterior.png)

<p class="source">After <a href="https://gaussianprocess.org/gpml/">Rasmussen &amp; Williams 2006</a>, Fig. 2.2 (free online)</p>

---

## Gaussian processes, the predictive variance

$$
\sigma^2(x_*) = k(x_*, x_*) - k_*^\top (K + \sigma_n^2 I)^{-1} k_*
$$

- Far from data, $k_* \to 0$: the band returns to the **prior**
- No $y$ in it: depends "only on the inputs" (R&W p. 18)
- At fixed settings, a bad fit gets the **same band** as a good one
- Fitted settings bring $y$ in "implicitly" ([Deringer et al. 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8391963/))

---

## Gaussian processes, fitting the settings

<div class="cw compact" data-widget="gp-explorer" data-source="l14a" data-mode="smooth"><img src="figures/widget-gp-explorer-smooth.png" alt="A Gaussian process fitted to 12 noisy points of a sine curve, with sliders for length scale, signal and noise"></div>

<!--
Press Fit. Noise comes out 0.044 against a true 0.1: 66% coverage inside, 96% beyond.
Overconfident where there is data, honest where there is none. Click to add points and refit.
-->

---

## Gaussian processes, failure 1: noise that grows

<div class="cw compact" data-widget="gp-explorer" data-source="l14a" data-mode="hetero"><img src="figures/widget-gp-explorer-hetero.png" alt="A Gaussian process with one noise level fitted to data whose scatter grows with x"></div>

<!--
Noise sd 0.02 + 0.3x. Overall 95% looks fine; by third 100%, 98%, 88%. Then switch to
"noise learned per point".
-->

---

## Gaussian processes, fixing heteroscedastic noise

![w:740](figures/gp-hetero-fix.png)

- Fixes: second GP on the log noise ([Goldberg et al. 1998](https://proceedings.neurips.cc/paper/1997/hash/afe434653a898da20044041262b3ac74-Abstract.html)); a cheap alternation ([Kersting et al. 2007](https://doi.org/10.1145/1273496.1273546)); variational ([Lázaro-Gredilla &amp; Titsias 2011](https://icml.cc/2011/papers/456_icmlpaper.pdf))
- Surprise: $\mathbb{E}[\log\varepsilon^2] = \log\sigma^2 - 1.27$, so the first try learned noise 0.7× too small

---

## Gaussian processes, a scikit-learn trap

- `alpha=array` sets a noise variance **per training point**
- It does not give the GP a noise model at new inputs
- `WhiteKernel` estimates "the global noise level"
- Input-dependent noise at prediction time needs a **model** of the noise

<p class="source"><a href="https://scikit-learn.org/stable/modules/gaussian_process.html">scikit-learn user guide, Gaussian processes</a></p>

---

## Gaussian processes, failure 2: the wrong kernel

<div class="cw compact" data-widget="gp-explorer" data-source="l14a" data-mode="step"><img src="figures/widget-gp-explorer-step.png" alt="A smooth-kernel Gaussian process fitted to a function with a step"></div>

<!--
98% away from the step, 72% within 0.1 of it. Note the fitted length scale: 0.05.
-->

---

## Gaussian processes, the shrinking length scale

<div class="cols cols-lc">
<div>

![w:620](figures/gp-lengthscale.png)

</div>
<div class="small">

- Smooth truth: about 0.2 to 0.4 at every size
- Step: 0.088 at 10 points, 0.025 at 320
- A length scale that "never stops becoming smaller as you add more data" is "a classic sign of model misspecification"
- GPs "can be miscalibrated in practice"

</div>
</div>

<p class="source"><a href="https://www.cs.toronto.edu/~duvenaud/cookbook/">Duvenaud, kernel cookbook</a> · <a href="https://arxiv.org/abs/2302.11961">Capone, Pleiss &amp; Hirche, NeurIPS 2023</a></p>

---

## Gaussian processes, failure 3: five points

<div class="cw compact" data-widget="gp-explorer" data-source="l14a" data-mode="few"><img src="figures/widget-gp-explorer-few.png" alt="A Gaussian process fitted to five noisy points of a sine curve"></div>

---

## Gaussian processes, how often five points mislead

| Training points | Median 95% coverage | Below 80% | Below 50% |
|---|---|---|---|
| 5 | 78% | 52% | **26%** |
| 12 | 92% | 21% | 1% |
| 40 | 95% | 0% | 0% |

- 200 data sets each, settings by maximum likelihood, exact coverage
- Little data: "both short and long lengthscales explain the data consistently"
- GP error bars are Bayesian, not frequentist guarantees

<p class="source"><a href="https://arxiv.org/abs/2109.02606">Capone, Lederer &amp; Hirche, ICML 2022</a> · <a href="https://arxiv.org/abs/2105.02796">Fiedler, Scherer &amp; Trimpe, AAAI 2021</a> · R&amp;W sec. 5.4.1</p>

---

## Gaussian processes, cost and a case

- Exact inference $O(n^3)$; inducing points: "from $O(n^3)$ to $O(nm^2)$" ([Titsias 2009](https://proceedings.mlr.press/v5/titsias09a.html))
- High dimension: the prior "simply says too little" ([Binois &amp; Wycoff 2022](https://arxiv.org/abs/2111.05040))
- **Case**: a silicon GP potential's predicted error "rises notably" on a path to a defect, and it still misses a minimum DFT finds

<p class="source"><a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC8391963/">Deringer et al., Chem. Rev. 2021</a>, sec. 5.2, Fig. 24 (open access)</p>

---

## Gaussian processes, what to do

- Look at the fitted noise; compare with replicate measurements
- Check coverage **by region**, not only overall
- Watch the length scale as data arrive
- Under about a dozen points: a rough guide, not a 95% statement

---

<!-- _class: section -->

# Bootstrap and ensembles

---

## Bootstrap

<div class="definition">

**Bootstrap**: resample the training data with replacement, refit, and use the spread of the refitted models.

</div>

- Estimates the **variance** of the fit ([Efron 1979](https://doi.org/10.1214/aos/1176344552))
- Misses the **noise**: a confidence interval, not a prediction interval
- Misses the **bias**: "the bias component ... is negligible" is an assumption ([Heskes 1997](https://proceedings.neurips.cc/paper_files/paper/1996/file/7940ab47468396569a906f75ff3f20ef-Paper.pdf))
- "May ... fail entirely when bias is a dominant source of error" ([Palmer et al. 2022](https://www.nature.com/articles/s41524-022-00794-8))

---

## Deep ensembles

<div class="definition">

**Deep ensemble**: several networks that differ only in random starting weights and data order, with their predictions combined.

</div>

- Each sees **all** the data: "bagging deteriorated performance"
- Each predicts a mean **and a variance**, trained on Gaussian NLL
- The spread alone is the epistemic part only
- Different starts land in different modes of the loss surface

<p class="source"><a href="https://arxiv.org/abs/1612.01474">Lakshminarayanan, Pritzel &amp; Blundell, NeurIPS 2017</a> · <a href="https://arxiv.org/abs/1912.02757">Fort, Hu &amp; Lakshminarayanan 2019</a></p>

---

## Ensembles, what the spread measures

<div class="cw compact" data-widget="ensemble-members" data-source="l14a"><img src="figures/widget-ensemble-members.png" alt="Ten networks trained on a sine curve from 0 to 1, fanning out beyond 1"></div>

<!--
Spread only, inside: 29%. Toggle the noise estimate: 93%. Beyond the data the members fan out
here, 85%. Say clearly that fanning out is not guaranteed.
-->

---

## Ensembles, the toy results

| 95% intervals | Inside the data | Beyond the data |
|---|---|---|
| Seeds, spread only | **29%** | 85% |
| Seeds, spread + noise | 93% | 93% |
| Bootstrap, spread only | 52% | 81% |
| Bootstrap, spread + noise | 94% | 87% |

- Inside: members agree to 0.021; the noise is 0.1
- Beyond: spread 0.63 against error 0.61, in **this** 1-D example

---

## Ensembles, the evidence

- **Best baseline**: "deep ensembles seem to perform the best across most metrics" ([Ovadia 2019](https://arxiv.org/abs/1906.02530)); [Scalia 2020](https://arxiv.org/abs/1910.03127), [Tan 2023](https://arxiv.org/abs/2305.01754) agree for molecules
- **Overconfident in level**: "consistently underestimates uncertainty" ([Hirschfeld 2020](https://arxiv.org/abs/2005.10036)); "require to be calibrated for each system" ([Kahle &amp; Zipoli 2022](https://arxiv.org/abs/2108.05748))
- **Weakest where it matters**: scaffold-split coverage "always underestimated" (Scalia)
- **Cost**: $M$ times one model

<p class="takeaway">A useful relative signal; not an interval until it has noise and a check.</p>

---

## Ensembles, a question

<div class="clicker" data-tag="l14a-members-agree" data-seconds="45" data-answer="D" data-hint="What would the members have to share for all of them to be wrong the same way?" data-why="D. Agreement measures only how much the members differ from each other. Members with the same architecture, data and features can extrapolate the same wrong way, so agreement beyond the data is evidence of a shared assumption, not of accuracy." data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**Five ensemble members agree to three decimals at an input far outside the training data. What does that tell you?**

<ol class="clicker-opts">
<li>The prediction is accurate there</li>
<li>The noise is small there</li>
<li>The model has seen similar inputs</li>
<li>Only that the members extrapolate alike</li>
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
A is the popular wrong answer. Tie it back to Palmer: when bias dominates, the spread can be small
and the error large.
-->

---

## Ensembles, recalibrating on concrete

- Concrete strength, Lecture 9's network, five seeds
- **Grouped split**: random 20% of mixes held out
- **Extrapolation split**: lowest water/cement 20% of mixes held out
- A quarter of the training mixes set aside to **calibrate**

$$
z_i = \frac{y_i - \mu_i}{\sigma_i}, \qquad \text{NLL}(s) = \frac1n\sum_i \Big[\log(s\sigma_i) + \frac{z_i^2}{2s^2}\Big] \;\Rightarrow\; s^2 = \overline{z^2}
$$

<p class="source">Same fix four times: σ scaling (Laves), STD scaling (Levi), <a href="https://arxiv.org/abs/1809.07653">Musil et al. 2019</a>, <a href="https://arxiv.org/abs/2402.16621">Kellner &amp; Ceriotti 2024</a> Eq. 8</p>

---

## Ensembles, recalibrating on concrete, live

<div class="cw compact" data-widget="sigma-scale" data-source="l14a"><img src="figures/widget-sigma-scale.png" alt="Negative log likelihood against the scale factor, and a reliability diagram for the concrete ensemble"></div>

<!--
Start at s = 1, press Fit: 1.66. Then switch to the extrapolation split and fit again.
-->

---

## Ensembles, recalibrating on concrete, results

| 90% intervals | Grouped raw | Grouped × 1.66 | Extrap. raw | Extrap. × 1.44 |
|---|---|---|---|---|
| Coverage | 79% | **90%** | 89% | 96% |
| Width (MPa) | 13.4 | 22.2 | 35.3 | 50.9 |
| NLL | 3.72 | **3.22** | 3.74 | 3.81 |

- Grouped: most of $s$ is the missing noise (replicate scatter 5.0 MPa)
- Extrapolation: spread already large; the factor **over**-widens
- Rank correlation of error with spread: 0.29 and 0.17

---

## Ensembles, what to do

- Never report the spread alone as an interval
- Recalibration costs a **third** data split
- Fit $s$ on data like where the model will be used
- Otherwise report coverage on a held-out region, and expect error in either direction

---

<!-- _class: section -->

# Conformal prediction

---

## Split conformal prediction

<div class="definition">

**Split conformal prediction**: set the interval width from the model's errors on a held-out calibration set, so it covers a new point with a stated probability.

</div>

1. Fit any model on the fitting set
2. Scores on $n$ calibration points: $s_i = |y_i - \hat\mu(x_i)|$
3. $\hat q$ = the $\lceil (n+1)(1-\alpha) \rceil$-th smallest score
4. Interval: $\hat\mu(x) \pm \hat q$

<p class="source"><a href="https://arxiv.org/abs/1604.04173">Lei et al., JASA 2018</a> (CMU) · <a href="https://arxiv.org/abs/2107.07511">Angelopoulos &amp; Bates</a></p>

---

## Split conformal prediction, the guarantee

<div class="definition">

**Exchangeable**: the joint distribution does not change if the points are reordered; calibration and test points were generated the same way.

</div>

$$
1 - \alpha \;\le\; P\big(y_{\text{new}} \in \hat\mu(x_{\text{new}}) \pm \hat q\big) \;\le\; 1 - \alpha + \tfrac{1}{n+1}
$$

- Any model, any distribution, any finite $n$
- At $\alpha = 0.1$ you need $n \ge 9$, or the interval is infinite

---

## Split conformal prediction, live

<div class="cw compact" data-widget="conformal" data-source="l14a"><img src="figures/widget-conformal.png" alt="A conformal band on a toy problem with noise growing in x, and a histogram of calibration scores"></div>

<!--
Drop n below 9 at alpha 0.1. Then show the thirds: 100, 95, 82. Toggle the normalized score.
Leave the window slide for the out-of-domain slide.
-->

---

## Conformal prediction, marginal not conditional

- Split conformal: "the width is exactly constant over x" (Lei sec. 5.2)
- Toy, 90% target: **100%, 95%, 82%** by third
- Exact conditional coverage cannot be had without assumptions ([Vovk 2012](https://arxiv.org/abs/1209.2673); [Foygel Barber et al. 2021](https://arxiv.org/abs/1903.04684))
- **Normalized scores** $|y - \hat\mu| / \hat\rho(x)$: 94%, 91%, 90%
- **CQR**: conformalize quantile regressions, "fully adaptive to heteroscedasticity" ([Romano et al. 2019](https://arxiv.org/abs/1905.03222))

---

## Jackknife+ and CV+

- Split conformal spends data on calibration
- **Jackknife+**: leave each point out, refit, record $R_i$
  - Interval from the quantiles of $\hat\mu_{-i}(x) \mp R_i$
- **CV+**: the same with $K$ folds
- Guarantee $1 - 2\alpha$, and the 2 is tight; "in practice" about $1 - \alpha$
- Plain jackknife: coverage "may actually vanish"
- Cost: $n$ or $K$ fits. Small data, cheap model: CV+. Otherwise split

<p class="source"><a href="https://arxiv.org/abs/1905.02928">Barber, Candès, Ramdas &amp; Tibshirani, Ann. Stat. 2021</a></p>

---

## Conformal prediction on concrete

| 90% intervals | Grouped | Width | Extrapolation | Width |
|---|---|---|---|---|
| Split conformal | 94% | 20.9 | **56%** | 13.9 |
| Normalized by ensemble spread | 90% | 22.0 | 95% | 49.4 |
| CV+ | 98% | 23.0 | 74% | 20.1 |
| Climatology | 91% | 55.9 | 54% | 43.7 |

- Grouped: every conformal method meets 90%, as guaranteed
- Extrapolation: split conformal **56%**; widths in MPa

---

## Conformal prediction, out of domain

- Strongest mixes are **not** exchangeable with calibration mixes: held out because different
- The guarantee did not fail; its condition was not met
- Toy, window sliding out: 99%, 94%, 86%, 56%, **16%**
- Normalizing rescued concrete only because the spread grew there; toy: 23%
- The fluorine case from the opening is this failure
- Weighted conformal needs the likelihood ratio and overlapping support ([Tibshirani et al. 2019](https://arxiv.org/abs/1904.06019)); beyond exchangeability, a bound you cannot compute ([Barber et al. 2023](https://arxiv.org/abs/2202.13415))

---

## Conformal prediction in code, MAPIE

```python
from mapie.regression import SplitConformalRegressor, CrossConformalRegressor

split = SplitConformalRegressor(model, confidence_level=0.9, prefit=True)
split.conformalize(X_cal, y_cal)
y_pred, y_int = split.predict_interval(X_test)

cvplus = CrossConformalRegressor(model, confidence_level=0.9,
                                 method="plus", cv=GroupKFold(10))
cvplus.fit_conformalize(X_train, y_train, groups=groups_train)
```

- Version 1 renamed `MapieRegressor` and `alpha`; most tutorials use the old names

<p class="source"><a href="https://mapie.readthedocs.io/en/stable/content/conformal-prediction/regression/">MAPIE docs</a> · <a href="https://arxiv.org/abs/2207.12274">Taquet et al. 2022</a></p>

---

## Conformal prediction, a question

<div class="clicker" data-tag="l14a-conformal-condition" data-seconds="45" data-answer="B" data-hint="The guarantee holds for any model and any noise distribution. What is left that it could depend on?" data-why="B. Split conformal needs nothing about the model or the noise, only that calibration and test points are exchangeable. A design loop picks test points because they differ from the data, which breaks exactly that." data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**An optimizer proposes mixes using a conformal surrogate. Which condition of the 90% guarantee does that break?**

<ol class="clicker-opts">
<li>The noise must be Gaussian</li>
<li>Test points must be exchangeable with calibration points</li>
<li>The model must be calibrated first</li>
<li>The calibration set must exceed 1,000 points</li>
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

---

<!-- _class: section -->

# UQ built into models: pycse

---

## pycse, the last-layer idea

- Treat the network's last layer as a **linear model on learned features**
- Use linear regression's uncertainty there; `predict(X, return_std=True)`
- Bishop's warning: with localized features the model "becomes very confident ... when extrapolating"

| Model | Idea | Source |
|---|---|---|
| `LinearRegressionUQ` | $s^2 + x_*^\top(X^\top X)^{-1}x_*\,s^2$ | Bishop Eq. 3.59 |
| `NeuralNetworkBLR` | Bayesian regression on last hidden layer | [Snoek et al. 2015](https://proceedings.mlr.press/v37/snoek15.html) |
| `DPOSE` | shallow ensemble, spread fitted | [Kellner &amp; Ceriotti 2024](https://arxiv.org/abs/2402.16621) |
| `LLPRRegressor` | prediction rigidity, after training | [Bigi et al. 2024](https://arxiv.org/abs/2403.02251) |

---

## pycse, inside and beyond the data

<div class="cols cols-lc">
<div>

![w:640](figures/pycse-compare.png)

</div>
<div class="small">

| 95%, 5 seeds | Inside | Beyond |
|---|---|---|
| `LinearRegressionUQ` | 94% | **2%** |
| `NeuralNetworkBLR` | 95% | 40% |
| `DPOSE` | 93% | 63% |
| `LLPRRegressor` | 93% | 84%, band 5× wider |

- `NeuralNetworkBLR` printed "✓ Model is well-calibrated" each time: checked on $[0, 1]$

</div>
</div>

---

## pycse, an import trap

```python
from pycse.sklearn import NNBR            # ImportError in pycse 2.11.1

from pycse.sklearn.nnbr import NeuralNetworkBLR
from pycse.sklearn.llpr_regressor import LLPRRegressor
from pycse.sklearn.dpose import DPOSE
from pycse.sklearn.lr_uq import LinearRegressionUQ
```

---

<!-- _class: section -->

# Trade-offs

---

## Trade-offs

| Method | Assumes | Guarantee | Beyond the data | Cost |
|---|---|---|---|---|
| GP | data look like the prior; one noise | Bayesian | back to the prior | $O(n^3)$ |
| Ensemble spread | members disagree where wrong | none | sometimes fans out | $M$ models |
| Rescaled spread | calibration data like use | empirical | factor does not transfer | a data split |
| Split conformal | exchangeable | finite-sample, marginal | none | a data split |
| CV+ | exchangeable | $\ge 1 - 2\alpha$ | none | $K$ fits |
| Last layer (pycse) | features stay informative | none | often overconfident | one model |

---

<!-- _class: demo -->

# Worked example

## `l14a-uq.ipynb`

- The concrete ensemble, its raw coverage, and the scale factor
- Split conformal and CV+ by hand, then with MAPIE
- Four pycse regressors inside and beyond their data

Watch for 79% becoming 90%, and 90% becoming 56%.

---

## Recap

- UQ is a claim about coverage; check it on held-out data, with width and a proper score
- GP: honest about missing data only if the prior is right; fails with varying noise, the wrong kernel, few points
- Ensembles: the best common baseline; add noise, then rescale
- Conformal: an exact guarantee that needs exchangeability
- No method checks itself outside the range where it was checked

---

## Standings

Nicknames only. Everyone who skipped one still counted in every bar you saw.

<div class="clicker-leaderboard"
     data-read="https://clicker.f26-06763.workers.dev"
     data-top="8"
     data-hours="6"
     data-title="Standings"></div>

---

## Before next time

* **Reading**: [Angelopoulos &amp; Bates](https://arxiv.org/abs/2107.07511), sections 1 and 2; [Palmer et al. 2022](https://www.nature.com/articles/s41524-022-00794-8)
* **Practice module** for this session: on the course site
* **Run** `l14a-uq.ipynb`; it installs MAPIE and pycse

Notes for this lecture: `lectures/l14a/notes.md`

<script src="clicker-slide.js"></script>
<script src="l14a-widget-data.js"></script>
<script src="widgets.js"></script>
