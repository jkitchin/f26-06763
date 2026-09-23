# Lecture 10: The machine learning workflow III, classification, experiment tracking and hyperparameter search

:::{admonition} At a glance
:class: tip

- **Session** Lecture 10, Week 5
- **Arc** Machine learning and deep learning
- **Slides** <a href="../../slides/l10/">Deck for this session</a>
- **Practice** <a href="../../game/#/l10">Practice module for this session</a>
- **Demo** [`l10-classification.ipynb`](l10-classification.ipynb), four classifiers on the moons and a fault classifier for the Tennessee Eastman plant; [`l10-tracking-search.ipynb`](l10-tracking-search.ipynb), an Optuna study wrapped in MLflow, from search to a registered model
- **Tools** scikit-learn for the classifiers, MLflow for tracking, Optuna for the search
- **Assignment 5** is released today
:::

## Why this matters

A chemical plant runs normally almost all the time, and that one fact breaks the most natural way
to score a fault detector. On the Tennessee Eastman test data of this session, 85.4% of the
samples are normal. A "detector" that ignores its inputs and answers "normal" every time is
therefore right 85.4% of the time, and it never finds a single fault. Accuracy, the fraction of
correct answers, cannot tell that detector from a useful one, and a team that reports accuracy
alone will ship it. The metrics this session introduces, precision and recall, are the ones that
expose it.

The second failure is quieter. A neural network trained on nine of the plant's faults catches 96%
of the faulty samples from those nine. Shown eight faults it was never trained on, its recall
ranges from 0.92 on one to 0.001 on another. Nothing in its training or validation scores warned
of that, because a supervised classifier can only recognize the classes it was shown. This session carries [Lecture 9](../l09/notes.md)'s four model families over from numbers to categories, and it ends its first half on exactly that limit.

The second half answers the question Lecture 9 left open. By the end of a real model-selection study you will have run the
training script hundreds of times: different features, different model families, different
hyperparameters, different seeds. A week later a colleague asks which run produced the 3.2 MW
error in your slide, and whether they can reproduce it. If your answer is a folder of timestamped
files and your memory, the honest answer is no.

Lecture 9 built the workflow that produces those runs: the split, cross-validation, the metrics,
and the discipline of touching the test set once. The second half of this session is about keeping
the record of that work, and about searching the hyperparameter space without fooling yourself.
The two are the same problem seen twice. A hyperparameter search is a machine for generating
hundreds of runs and picking the best one, and picking the best one is exactly where an
unrecorded, unexamined study quietly lies to you. So we log every run with enough detail to
rebuild it, we search with a strategy rather than by hand, and we read the results knowing that
the best validation score is an optimistic number by construction.

## Learning objectives

By the end of this session you should be able to:

- Fit and compare logistic regression, decision tree, neural network and Gaussian process
  classifiers, and say what each one minimizes.
- Choose metrics that match the cost of an error, including precision and recall when one class
  is rare.
- Use stratified k-fold when one class is rare, and test a classifier on classes it was not
  trained on.
- Instrument a training script so every run is logged, comparable, and reproducible.
- Run grid, random, and Bayesian hyperparameter search and interpret the results honestly.
- Register a selected model with its metrics, params, and data lineage.

## The examples in this session

Three datasets carry this session. The first two are for classification and the third is for
the hyperparameter search. Each is introduced here once, so the sections after it can use it
without stopping.

### The moons

The moons dataset is a synthetic classification problem that scikit-learn generates with
`make_moons`, which its documentation describes as "two interleaving half circles", with a noise
parameter that sets the "standard deviation of Gaussian noise added to the data" ([scikit-learn,
`make_moons`](https://scikit-learn.org/stable/modules/generated/sklearn.datasets.make_moons.html)).
Each half-circle is one class, and Gaussian noise scatters the
points around it, so the two classes overlap a little at their tips. It is a toy, used here for two reasons. It has two inputs, so the whole plane can be colored by
what a model predicts and its decision boundary can be seen. And no straight line separates the
two classes, so it shows at once which models can bend.

```python
from sklearn.datasets import make_moons
from sklearn.model_selection import train_test_split

X, y = make_moons(
    n_samples=300,       # 300 points, 150 per class
    noise=0.25,          # standard deviation of the noise added to each point
    random_state=0,      # the same points every run
)
Xtr, Xte, ytr, yte = train_test_split(
    X, y,
    test_size=0.3,       # 210 points to train on, 90 to test
    random_state=42,
)
```

```{figure} figures/moons-data.png
:alt: Three hundred points in the plane, x1 from about minus 1.5 to 2.5 and x2 from about minus 1 to 1.5, in two colors. One class forms an upper half-circle, the other a lower half-circle shifted to the right, interleaved so that the tip of each sits inside the curve of the other.
:width: 60%

The moons: 300 points in two interleaving half-circles, one class each.
```


### The Tennessee Eastman process, normal or faulty

Lecture 9 used the simulated plant of [Lecture 5](../l05/notes.md) and Lecture 8 ([Downs and
Vogel, 1993](https://doi.org/10.1016/0098-1354(93)80018-I)) to forecast a pressure. This session
asks it a classification question instead: is this three-minute sample normal, or is the plant
running under a fault? The data is the miniproject's two files from [Rieth et al.
(2017)](https://doi.org/10.7910/DVN/6C3JR1): fault-free runs, and faulty runs for faults 1 to 20,
with 52 channels (41 measurements and 11 valve positions) sampled every three minutes. In every
faulty training run the fault starts one hour in, so a sample is labeled faulty when it comes from
a faulty run after that hour. The rows are three-minute samples of a run, so the training and test
sets are split by run, as in Lecture 8. Faults 3, 9 and 15 never appear here: the miniproject
checks that you find those three for yourself.

```{figure} figures/tep-data.png
:alt: Reactor pressure xmeas_7 in kPa over 25 hours for fault-free training run 1, in gray, and for fault 1, run 1, in red. Both sit near 2,705 kPa for the first hour. After a dashed line at 1 hour marking the start of the fault, the faulty run swings between about 2,650 and 2,810 kPa in oscillations that decay, and it is back near 2,705 kPa by about 20 hours.
:width: 100%

Reactor pressure in a fault-free run and in a run of fault 1 (a step in the A/C feed ratio), from
the miniproject's training files. The fault starts one hour in, as it does in every faulty
training run of Rieth et al. (2017). A classifier sees one sample at a time: all 52 channels at one
three-minute step.
```

### The combined cycle power plant

The hyperparameter search uses the UCI Combined Cycle Power Plant (CCPP) set, 9,568 hourly
records of four ambient measurements (temperature, exhaust vacuum, pressure, humidity) predicting
net electrical output in megawatts. It is a steady-state surrogate problem, the kind that recurs
for pump curves and engine maps, and it is small and clean enough that a full search runs in class.

## Classification

```{index} logistic regression
```

[Lecture 9](../l09/notes.md) defined the two supervised tasks and fitted four model families to
numbers. Regression predicts a **number** (a pressure, a viscosity, a strength), and its typical
loss is the sum of squared errors. Classification predicts a **category** (stable against
unstable, normal against faulty), and its typical training criterion depends on the model:
impurity for trees, cross-entropy for neural networks and logistic regression, likelihood for Gaussian processes (GPs). All four families have classification versions, and scikit-learn names them the way you
would guess: `LogisticRegression`, `DecisionTreeClassifier`, `MLPClassifier` and
`GaussianProcessClassifier`.

### Logistic regression

:::{admonition} Definition: logistic regression
:class: tip

**Logistic regression** is the linear model for classification. It computes a weighted sum of
the features, $z = w^\top x + b$, and passes it through the logistic function
$\sigma(z) = 1/(1+e^{-z})$ to get the probability of the positive class,
$p(y=1\mid x) = \sigma(w^\top x + b)$.
:::

It predicts class 1 when that probability is above 0.5, which happens exactly when
$w^\top x + b > 0$. So its **decision boundary**, the line between the two predicted classes, is
a straight line in two dimensions and a flat plane in more. Its weights are fitted by minimizing
the cross-entropy defined below. It plays the role for classification that linear regression
plays for regression: it is cheap and interpretable, and it is the floor every other classifier
has to beat. Despite its name, it is a classifier.

```{figure} figures/logistic-moons.png
:alt: Left, the logistic function rising from 0 to 1 as an S-shaped curve against z, crossing 0.5 at z equal to 0, with the region above 0.5 marked as predict class 1. Right, the moons data with the plane shaded by the probability logistic regression predicts, and its 0.5 boundary drawn as one straight line across the moons.
:width: 100%

Left: the logistic function turns the weighted sum $z = w^\top x + b$ into a probability, and the
prediction switches class where it crosses 0.5, at $z = 0$. Right: logistic regression on the
moons. The boundary is the straight line $w^\top x + b = 0$, and it scores 0.867 accuracy on
the 90 test points.
```

### Decision trees for classification

```{index} Gini impurity
```

The idea is conceptually simple. We partition the feature space with simple questions (is
$x_1 < 0.3$?) so that each region, each **leaf**, is as **pure** as possible, meaning that it
mostly contains one class. Trees grow by recursively choosing the splits that reduce a measure
of impurity. One of the two common measures is the **Gini impurity**. With $p_k$ the fraction of
samples of class $k$ in a node,

$$ G = 1 - \sum_k p_k^2. $$

It is 0 when a node is pure (all one class), and it increases as the node becomes mixed. If you
randomly pick a label from the node according to its class proportions, the chance you're wrong
is exactly the Gini impurity, so a lower Gini means fewer mistakes. For example, suppose a node
has 5 samples: 4 blue and 1 red. Then $p_{\text{blue}} = 0.8$, $p_{\text{red}} = 0.2$, and
$G = 1 - (0.8^2 + 0.2^2) = 1 - (0.64 + 0.04) = 0.32$. A split that separates the red from the
blues drops the impurity, which makes it a good split. (The example is inspired by [Victor
Zhou's explanation of Gini impurity](https://victorzhou.com/blog/gini-impurity/).)

At each node, the algorithm searches over candidate (feature, threshold) pairs and takes the one
with the largest impurity decrease. This is the only difference from regression trees. A
regression tree splits to reduce the squared error within its leaves and predicts an average
number. A classification tree splits to reduce the impurity and predicts a class, or a class
probability.

### Neural networks for classification

```{index} softmax, cross-entropy
```

Lecture 9's regression network produced a **number** (a linear output, trained with the squared error).
For classification, we want **probabilities** over classes. If the last layer outputs scores
(logits) $z_1,\dots,z_K$, the **softmax** turns them into probabilities:

$$ \text{softmax}(z_j) = \frac{e^{z_j}}{\sum_{k=1}^{K} e^{z_k}}. $$

The softmax outputs are nonnegative and sum to 1, so they are a valid probability distribution.
The softmax amplifies differences, since larger logits get disproportionately higher
probabilities through $e^{z}$, and adding the same constant to all the logits doesn't change the
probabilities. The network is trained with the **cross-entropy**, which rewards a high
probability on the correct class:

$$ \text{CE}(y,\hat{p}) = -\sum_{j=1}^K y_j \log \hat{p}_j. $$

So a regression network has a linear output and a squared-error loss, and a classification
network has a softmax output and a cross-entropy loss. In both, the hidden layers (tanh or ReLU) make the model flexible: a curved fit for regression, a bent decision boundary for classification. With two classes the softmax reduces to the logistic
function, so logistic regression is a network with no hidden layer.

### Gaussian processes for classification

In regression, a GP places a distribution over functions and predicts a **number**, with an
uncertainty. In classification, we need a **probability** for each class. We get one by
introducing a **latent function** $f(x)$ with a GP prior, $f(x)\sim\mathcal{GP}(m,k)$, a smooth
random function controlled by the kernel, and a **link function** that maps any real number to
the interval $[0, 1]$. For two classes a common choice is the logistic function, so
$p(y=1\mid x)=\sigma(f(x))$ and $p(y=0\mid x)=1-p(y=1\mid x)$. The interpretation is the
following: near the data, the posterior over $f(x)$ is more confident, so the probabilities are
close to 0 or 1. Far from the data, the model is unsure.

### What each family minimizes, regression against classification

Lecture 9's optimization view carries over, with a different objective in every row. Each family keeps
its structure and changes what it minimizes, because the output is now a class, or a probability
of one, instead of a number.

| Family | Regression minimizes | Classification minimizes |
|---|---|---|
| Linear | The squared error, with a linear output | The cross-entropy, with a logistic output (logistic regression) |
| Decision tree | The squared error within the leaves; a leaf predicts an average | The Gini impurity within the leaves; a leaf predicts a class |
| Neural network | The squared error, with a linear output | The cross-entropy, with a softmax output |
| Gaussian process | The negative log marginal likelihood | The negative log marginal likelihood of the labels, with a latent GP and a link, Laplace-approximated |

Minimizing the cross-entropy is the same as maximizing the likelihood of the observed labels; the
[log loss page](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.log_loss.html)
of scikit-learn calls it "Log loss, aka logistic loss or cross-entropy loss". For
logistic regression that problem is convex, with one minimum; for a network it is not. A GP
classifier's labels follow a Bernoulli likelihood, which makes the posterior over the latent
function non-Gaussian, so scikit-learn approximates that posterior with a Gaussian (the Laplace
approximation).

### Decision regions on the moons data

Because the moons have only two features, we can color the whole plane by what each model
predicts and see its decision boundary.

```{figure} figures/moons-regions.png
:alt: Four panels of the moons data, purple and yellow points, with the plane colored by each model's predicted probability and the 0.5 boundary drawn in black. Logistic regression draws a straight diagonal line. The depth-3 tree draws rectangles. The neural network with five ReLU units draws a boundary made of a few straight segments that bends around the moons. The Gaussian process draws a smooth S-shaped boundary, with the color fading away from the data.
:width: 100%

Four classifiers on the same 210 training points, scored on the other 90. The black line is
where each model's predicted probability crosses 0.5.
```

Logistic regression can only draw a straight line, and it scores 0.867 accuracy on the 90 test
points. The depth-3 tree cuts the plane into rectangles and scores 0.911. The network with five
ReLU units bends the boundary out of a few straight pieces and scores 0.933. The GP draws a
smooth curve, scores 0.967, and its probability fades away from the data.

### A fault a straight line cannot see

The moons are a toy. Here is the same thing on the Tennessee Eastman plant from the examples
section. Take fault 14, a sticking
reactor cooling water valve, and train a classifier to label each sample of the 52 channels as
normal or faulty. It learns from 300 fault-free runs and 10 faulty runs, and it is tested on 100
other fault-free runs and 10 other faulty runs.

A logistic regression catches 0% of the faulty samples. A decision tree of depth 8 catches
99.7%, with one false alarm in 10,000 normal samples. The histogram shows why.

```{figure} figures/tep-fault14.png
:alt: Histogram of xmv_10, the reactor cooling water flow, on a logarithmic density axis. Normal operation is a narrow gray peak at about 41 percent. Under fault 14 the red histogram is spread wide, from about 29 to 54 percent, on both sides of the gray peak. Two dashed vertical lines, at 39.13 and 43.05, mark the tree's two cuts on either side of the normal peak.
:width: 100%

The reactor cooling water flow `xmv_10` in normal operation and under fault 14, on a log scale.
The dashed lines are the first two splits of a depth-2 tree trained to detect the fault.
```

With the valve sticking, the reactor cooling water flow `xmv_10` swings to both sides of its
normal value. Its mean barely moves (41.16% under the fault against 41.10% in normal operation),
while its standard deviation grows from 0.54 to 7.44. 45% of the faulty samples fall below the
normal band (the normal mean minus three standard deviations), and another 45% fall above it. A
straight boundary can only cut off one side, and because the mean did not move, the best line
cuts off neither. The tree's first two splits are both on `xmv_10`, at 39.13 and 43.05, which is
a band around normal: one split catches 44% of the fault and two catch 88%. A linear model needs
the two classes on opposite sides of a plane, and here the faulty samples surround the normal
ones.

### Classification metrics

```{index} confusion matrix
```
```{index} pair: metric; precision
```
```{index} pair: metric; recall
```
```{index} pair: metric; F1
```

The simplest classification metric is **accuracy**, the fraction of correct predictions:

$$ \text{Accuracy} = \frac{\text{number of correct predictions}}{\text{number of total predictions}} $$

:::{admonition} Definition: accuracy
:class: tip

**Accuracy** is the fraction of a classifier's predictions that are correct.
:::

Accuracy is intuitive and fine for **balanced** datasets, like the moons. When there is an
imbalanced distribution (an unequal number of data points across the categories), we need to be
extra careful, and fault detection is almost always imbalanced, because a plant runs normally
almost all the time.

Here is the Tennessee Eastman plant again, with one classifier for many faults. It is trained on
300 fault-free runs plus five runs of each of nine faults (1, 2, 4, 5, 6, 7, 8, 12 and 13):
172,500 samples, of which 12.5% are faulty. It is tested on 100 other fault-free runs plus two
other runs (11 and 12) of each of the nine faults: 59,000 samples, 14.6% faulty. No run appears on both
sides, which is Lecture 8's split by run. A "classifier" that always answers "normal" scores
**85.4% accuracy**, and never finds a single fault. It is a **baseline**, the classification
counterpart of predicting the mean: it ignores every input and always predicts the most common
class, and its accuracy is 85.4% only because 85.4% of the test samples are normal.

:::{admonition} Definition: confusion matrix, precision and recall
:class: tip

A **confusion matrix** counts predictions by their true class and their predicted class. With
"fault" as the positive class, a **true positive** (TP) is a fault flagged as a fault, a **false
positive** (FP) is a normal sample flagged as a fault, a **false negative** (FN) is a fault that
was missed, and a **true negative** (TN) is a normal sample left alone. **Precision** is TP / (TP + FP): of the alarms raised, the fraction that were
real. **Recall** is TP / (TP + FN): of the real faults, the fraction that were caught.
:::

Laid out as the matrix, with the actual class down the side and the prediction across the top:

| | Predicted faulty (alarm) | Predicted normal (no alarm) |
|---|---|---|
| **Actually faulty** | TP: a fault, caught | FN: a fault, missed |
| **Actually normal** | FP: a false alarm | TN: normal, left alone |

Precision reads down the first column, and recall reads along the first row. Neither uses TN,
which is why a detector cannot look good on them by piling up normal samples.

```{figure} figures/tep-confusion.png
:alt: Two confusion matrices with the faulty class first: rows actually faulty and actually normal, columns predicted faulty and predicted normal, each cell labeled with its name and count. Baseline, always normal: TP 0, FN 8,640, FP 0, TN 50,360. Neural network: TP 8,300, FN 340, FP 13, TN 50,347.
:width: 85%

The same 59,000 test samples, classified by the baseline that always says "normal" and by a
neural network with 32 ReLU units.
```

| Classifier | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| Baseline: always normal | 0.854 | 0 | 0 | 0 |
| Logistic regression | 0.970 | 0.993 | 0.803 | 0.888 |
| Decision tree (depth 8) | 0.977 | 0.988 | 0.855 | 0.917 |
| Neural network (32 ReLU units) | 0.994 | 0.998 | 0.961 | 0.979 |

The **F1 score** is the harmonic mean of precision and recall, $F_1 = 2PR/(P+R)$, or, from the counts, $2\,\text{TP}/(2\,\text{TP} + \text{FP} + \text{FN})$, and it is zero when either of them is. The baseline shows why the count form is the safer one to remember: it raises no alarms, so its precision is 0/0, which scikit-learn reports as 0, while its F1 from the counts is $0/(0 + 0 + 8{,}640) = 0$ with no convention needed. It is the single number to watch when you care about both. Between the
first row and the last, accuracy moved from 0.854 to 0.994, which reads like a modest
improvement. Recall moved from 0 to 0.961: the baseline catches no faults, and the network catches
96% of them.

A false positive is Lecture 8's **false alarm**. The network raised 13 of them on 50,360 normal
samples. At the plant's 480 samples a day, 50,360 samples are about 105 days of normal
operation, so 13 false alarms is about one every eight days. Which metric to push depends on
what an error costs. When a missed fault is expensive (a runaway reaction, a damaged catalyst),
push recall and accept more alarms. When false alarms cost the operators' trust, push precision.
When you need both, watch F1, and in every case report the confusion matrix, since all three
come from it.

### Stratified k-fold

```{index} StratifiedKFold
```

In classification, a fold can also get its class balance wrong. The **class fractions** of a
dataset are the share of samples in each class: 12.5% faulty and 87.5% normal in the Tennessee
Eastman training data. A plain k-fold split ignores the labels, so on a small dataset with a rare
class some folds can end up with far fewer of the rare class than the data as a whole, or with
none at all.

:::{admonition} Definition: stratified k-fold
:class: tip

**Stratified k-fold** (`StratifiedKFold` in scikit-learn) builds each fold with the same
fraction of each class as the full dataset.
:::

It does that by splitting each class into $k$ parts separately and then putting one part of each
class into each fold. It matters when the data is small and one class is rare. With 50 samples of
which 5 are faulty, a shuffled five-fold split leaves at least one fold with no faulty sample in
95% of shuffles, and the recall on that fold is undefined. `StratifiedKFold` puts exactly one
faulty sample in each fold.

```{figure} figures/cv-stratified.png
:alt: Two panels of five rows, one row per fold, each row the fold's 10 validation samples drawn as squares, red for faulty and light gray for normal. Left, KFold: the folds hold 2, 0, 1, 1 and 1 faulty samples, and the 0 for fold 2 is marked in red. Right, StratifiedKFold: every fold holds exactly one faulty sample.
:width: 100%

Fifty samples, five of them faulty, split five ways. A plain shuffled `KFold` (left, one of its
shuffles) can leave a fold with no faulty sample; `StratifiedKFold` (right) cannot.
```

It matters much less on a large table: on the 172,500 Tennessee Eastman training samples, a plain shuffled `KFold` already puts between 12.4% and 12.7% faulty samples in every fold (a split you would not use on these rows, which must be split by run; it only shows how the class fractions behave at this size). When the rows
are both grouped and imbalanced, `StratifiedGroupKFold` does both at once.

### A classifier only knows the faults it was trained on

```{index} pair: failure mode; a class missing from the training data
```

The last limitation matters most for fault detection. The neural network from the classification
metrics above catches 96% of the faulty samples from the nine faults it was trained on. Here is the
same network on eight faults it never saw in training (their runs 11 and 12, the same test runs
as above, after each fault starts):

```{figure} figures/tep-unseen.png
:alt: Bar chart of recall. The first bar, for the nine faults the classifier learned (scored on test runs 11 and 12), is 0.961. The other eight bars are for faults it never saw: fault 10 0.155, fault 11 0.248, fault 14 0.686, fault 16 0.021, fault 17 0.696, fault 18 0.924, fault 19 0.001, fault 20 0.105.
:width: 100%

Recall of one neural network classifier on the faults it was trained on (blue) and on eight
faults that were not in its training data (gray).
```

Its recall on the new faults ranges from 0.001 on fault 19 to 0.92 on fault 18, and nothing
about the classifier tells you in advance which kind of fault you will get. The next fault a
plant has is often one nobody has labeled. A supervised detector answers the question "does
this look like a fault I have seen?", and a plant needs an answer to "does this still look like
normal operation?". The miniproject, released with Lecture 9, builds two detectors that answer the second
question, trained on fault-free data only.

:::{admonition} What a practitioner should take from this
:class: note

Before you trust a classifier's recall, ask which classes were in its training data, and test it
on a class that was held out entirely. If the class you care about is "anything new", a
supervised model is the wrong tool on its own: model normal operation instead, and flag the
departures from it.
:::

## What every run has to record

```{index} experiment tracking, run metadata, data lineage
```

Lecture 9 ended on a question it left open, and every classifier above leaves it open too: a depth of 3, five ReLU units, a depth of 8 and 32 units were all chosen by hand. Choosing them well is an optimization problem with a training problem inside it:

$$
\begin{aligned}
\min_{\lambda} \quad & L_{\text{val}}\big(\theta^*(\lambda)\big) \\
\text{s.t.} \quad & \theta^*(\lambda) = \arg\min_{\theta} \; L_{\text{train}}(\theta; \lambda)
\end{aligned}
$$

Every evaluation of the outer objective trains a model, and every one of those trainings is a run
somebody may later need to rebuild. So before searching, record.

The purpose of tracking is to answer one question after the fact: which run produced this number, and can I produce it again? A run that logs only its score cannot answer it. A run answers it when it records everything needed to rebuild itself.

That list is specific, and it ties this session back to the rest of the course. Log the **hyperparameters** and the **metrics** (per fold, not just the average, so you can see the variance). Log the **git commit SHA** (secure hash algorithm) of the code, so the exact program is recoverable. Log the **dataset version or content hash** from [Lecture 2](../l02/notes.md), so the exact inputs are pinned. Log the **random seed** and the **environment**, which is the `uv.lock` from [Lecture 2](../l02/notes.md). And log the **artifacts**: the fitted pipeline, the plots, the feature importances. The rule from Lecture 2 returns with more force here, because a search multiplies the number of runs by a hundred: one run equals one fact you can reproduce, and a run you cannot rebuild is a number you cannot defend.

## MLflow: experiments, runs, and the registry

```{index} MLflow, MLflow run, autologging, model registry, model URI
```

**MLflow** is the tracking tool this course uses, introduced in Lecture 2 and used in earnest here. Its two core objects are simple. A **run** is one execution of your training code. An **experiment** groups the runs for one task, so a search's hundred runs live together and sort against each other. Inside a run you call `mlflow.log_param`, `mlflow.log_metric`, and `mlflow.log_artifact` to record what you chose, what you measured, and what you produced.

:::{admonition} Definition: experiment and run
:class: tip

In MLflow, a **run** is a single execution of training code, for example one `python train.py`. An **experiment** groups related runs so they can be compared. Parameters and metrics logged to a run are what the tracking UI sorts and plots; artifacts are the files (a model, a figure) attached to it.
:::

Three features matter for a search. **Autologging** (`mlflow.autolog()`, or a per-flavor call like `mlflow.sklearn.autolog()`) records parameters, metrics, and the model without explicit log statements, and for a scikit-learn search estimator it creates a parent run with one nested child run per candidate. **Nested runs** (`mlflow.start_run(nested=True)`) let you structure that yourself: a parent run for the study, a child run per trial or per cross-validation fold. And the **Model Registry** is where a chosen model goes to be found again.

:::{admonition} Definition: the Model Registry and model URIs
:class: tip

The MLflow **Model Registry** is, in its docs' words, "a centralized model store, set of APIs and a UI designed to collaboratively manage the full lifecycle of a machine learning model." You register a model under a name and version, then load it back by a **model URI**: `models:/<name>/<version>` for a fixed version, or `models:/<name>@<alias>` for a moving label like `@champion`.
:::

The interface is small, and the whole loop fits in a few lines:

```python
import mlflow

mlflow.set_tracking_uri("sqlite:///mlflow.db")     # local store, no server
mlflow.set_experiment("ccpp-search")
with mlflow.start_run(run_name="hgb-trial-7"):
    mlflow.log_params(params)
    mlflow.log_param("data_md5", data_hash)         # lineage, from Lecture 2
    mlflow.log_metric("val_rmse", rmse)
    mlflow.sklearn.log_model(model, name="model")
```

:::{admonition} Common pitfall
:class: warning

Recent MLflow versions put the bare local **file store** (a `./mlruns` directory) into maintenance mode and default the local backend to a **SQLite** database, `sqlite:///mlflow.db`. Existing `mlruns` folders still work, but set the SQLite URI explicitly so a demo does not stop on a deprecation warning mid-class. The tracking UI is `mlflow ui` on older versions and `mlflow server` on current ones; both serve the same runs from the same store. A local store is enough for this course; do not spend class time standing up a tracking server.
:::

## Searching the hyperparameter space

```{index} hyperparameter search, grid search, random search, Bayesian optimization, Optuna, TPE
```

Once training is instrumented, the search becomes a loop that proposes a configuration, trains, and logs the result. The question is how to propose. Three strategies, in increasing sophistication.

**Grid search** tries every combination of a fixed set of values per hyperparameter. It is exhaustive and it is the wrong default, because its cost is the product of the axes and most of that cost is wasted. **Random search** samples each hyperparameter from a range. Bergstra and Bengio showed in 2012 that "randomly chosen trials are more efficient for hyper-parameter optimization than trials on a grid," and the reason is that "for most data sets only a few of the hyper-parameters really matter, but that different hyper-parameters are important on different data sets." A grid spends its budget trying many values of parameters that do not matter; random search, with the same budget, tries many distinct values of the one that does.

```{figure} figures/grid_vs_random.png
:alt: Two panels, each with nine trial points over two hyperparameters. The grid panel places points on a 3 by 3 lattice, so only three distinct values of the important (horizontal) parameter are tried. The random panel scatters nine points, trying nine distinct values of the important parameter.
:width: 100%

Nine trials each. If only the horizontal hyperparameter matters, grid search tries three distinct values of it and random search tries nine, because the grid spends the other six trials repeating those three values against an axis that does not change the score. Redrawn after Bergstra and Bengio (2012).
```

**Bayesian optimization** goes further: it builds a model of the score as a function of the hyperparameters from the trials so far, and proposes the next trial where that model expects improvement. **Optuna** is the library this course uses for it. Its default sampler is the **Tree-structured Parzen Estimator (TPE)**, which models the good and bad regions of the space and samples toward the good. You write the search space define-by-run, suggesting each value inside the objective:

```python
import optuna

def objective(trial):
    params = dict(
        learning_rate=trial.suggest_float("learning_rate", 0.01, 0.5, log=True),
        max_leaf_nodes=trial.suggest_int("max_leaf_nodes", 8, 128, log=True),
        max_iter=trial.suggest_int("max_iter", 50, 250),
    )
    return cross_val_rmse(params)          # minimize

study = optuna.create_study(direction="minimize")
study.optimize(objective, n_trials=30)
```

On the power-plant data this converges fast, and it shows both the promise and the honest limit of clever search.

```{figure} figures/optuna_search.png
:alt: Best validation RMSE so far against trial number, for random sampling and for Optuna's TPE. Both fall quickly and end within a few thousandths of each other, TPE slightly lower.
:width: 80%
:align: center

Best validation root mean squared error (RMSE) so far, over 30 trials of a gradient-boosting model on CCPP. TPE reaches a good configuration in fewer trials than random sampling, but both finish close: 3.326 MW for TPE against 3.335 MW for random. On an easy problem the sampler matters less than the fact that you searched at all.
```

Two more ideas make a large search affordable. **Pruning** stops a trial early once its intermediate scores look hopeless; Optuna's median and successive-halving pruners do this. And **Hyperband** (Li et al., 2018) formalizes the idea, speeding up random search "through adaptive resource allocation and early-stopping" so that promising configurations get more budget and bad ones are cut off quickly. Every trial, pruned or not, gets logged to MLflow as a nested run, so the search itself is auditable rather than a black box that emits one winner.

## The statistics of selection

```{index} selection bias, one-standard-error rule, nested cross-validation
```

A search is a machine for running many trials and reporting the best one, and that is exactly the operation that biases a score. With enough trials, some configuration wins on the validation data by luck, and its validation score is then an optimistic estimate of what it will do in deployment. This is **selection bias**, and Cawley and Talbot (2010) put the general warning plainly: common evaluation practices "are susceptible to a form of selection bias as a result of this form of over-fitting and hence are unreliable."

Three habits keep it honest. First, **report the validation distribution, not just its minimum**: the spread across folds and trials tells you whether the winner is meaningfully better or just lucky. Second, **touch the test set once**, at the very end, on the single model you selected, exactly as Lecture 9 insisted. The best validation score is not the number you report; the held-out test score is.

Third, prefer the simplest model that is nearly as good, using the **one-standard-error rule**.

:::{admonition} Definition: the one-standard-error rule
:class: tip

The **one-standard-error rule**, from the CART book and *The Elements of Statistical Learning* (section 7.10), says to "choose the most parsimonious model whose error is no more than one standard error above the error of the best model." It trades a statistically indistinguishable amount of accuracy for a simpler, more robust choice, and it resists the reflex that the biggest model always wins.

:::

The honest surprise is how small this bias is when the data is plentiful. Measured on this power-plant set over a 36-candidate grid, the optimism of reporting the best validation score instead of the honest test score is **+0.19 MW at a training size of 80 rows, inside the fold-to-fold noise by about 320 rows, and −0.003 MW on all 9,568 rows**. Selection bias is a small-data problem, and the quantity that decides it is the ratio of candidates to rows. **Nested cross-validation**, which wraps the whole selection procedure inside an outer cross-validation loop to estimate its performance without bias, is the tool when you must both select and report on limited data. It is insurance you buy when data is scarce, not a tax you pay on every study.

## Where this pushes back

Tracking and search are easy to over-apply, and each has a limit worth naming.

### A tracking system you do not read is just overhead

MLflow will faithfully log ten thousand runs, and ten thousand runs nobody compares is a slower way to lose the same information. Autologging in particular makes it trivial to record everything and examine nothing, so the discipline is to log the few things that let you rebuild a run, and to actually open the UI and sort. The value is in the reading, not the writing.

### Search can overfit the validation set

A large enough search, scored against one fixed validation split, eventually finds a configuration tuned to that split's noise, which is the selection bias above turned into a workflow. Cap the trial budget, keep a locked test set you touch once, and apply the one-standard-error rule so that "run more trials" does not silently become "overfit the validation set more thoroughly."

### The sampler matters less than the search, and the search less than the data

The power-plant result is the caution: TPE beat random by 0.009 MW, a difference smaller than the fold noise. Bayesian optimization earns its complexity on expensive objectives with many interacting hyperparameters, such as a deep network that takes hours to train. For a fast model on a clean tabular problem, random search with a sensible budget is usually enough, and a better feature or a cleaner label from [Lecture 7](../l07/notes.md) and [Lecture 8](../l08/notes.md) will move the score more than any sampler.

### The registry records a decision; it does not make a good one

Registering a model gives it a name, a version, and a URI, which solves the problem of finding the model you chose. It does nothing to check that the choice was sound. A model registered from a leaky split or an optimistic validation score is a well-organized mistake, which is why the registry belongs at the end of the honest workflow, not in place of it.

:::{admonition} What a practitioner should take from this
:class: tip

Instrument the training script so that every run records the hyperparameters, the metrics per fold, the code SHA, the data hash, the seed, and the environment, because a run you cannot rebuild is a number you cannot defend. Prefer random or Bayesian search to grid, but remember that on an easy problem the search strategy matters far less than searching at all. Report the validation distribution, select with the one-standard-error rule, and compute the single test number at the very end. Then register the winner with its lineage, so the record of what you tried and why is a deliverable, not an afterthought.
:::

## In-class demo

There are two notebooks, one for each half. The first,
[`l10-classification.ipynb`](l10-classification.ipynb), downloads the miniproject's two Tennessee
Eastman files (45 MB) on its first run and works in the order of these notes:

1. **Moons.** The four classifiers and their decision regions.
2. **Tennessee Eastman.** The normal-against-fault classifier split by run, the baseline, its
   confusion matrix, precision, recall and F1.
3. **Faults it never saw.** The same network's recall on eight faults outside its training data.

The second is the search. We fit gradient-boosting models to the power-plant data and wrap every fit in MLflow, using the local SQLite store. An Optuna study searches gradient-boosting hyperparameters with each trial logged as a nested MLflow run, so the whole search is visible in the UI. We open the tracking UI, sort by validation RMSE, and read the parallel-coordinates and contour plots to see which hyperparameters actually mattered. Then we register the winning model, load it back by its `models:/` URI for a fresh prediction, and compute the single held-out test score that is the number we would actually report. The moment to watch is the gap between the best validation score in the sorted list and that final test number: the search optimizes the first, and honesty reports the second. The runnable notebook is [`l10-tracking-search.ipynb`](l10-tracking-search.ipynb).

## Summary

Lecture 9's four families carry over to classification with a change of objective: cross-entropy
for logistic regression and networks, Gini impurity for trees, and the likelihood of the labels
through a latent function for a Gaussian process. Which family wins still depends on the problem.
On the moons a straight boundary loses, and on the plant a straight boundary catches none of a fault that swings a valve both ways, while a two-cut tree catches 88% of it and a depth-8 tree 99.7%. The metric
decides as much as the model. A baseline that never raises an alarm scores 85.4% accuracy and
catches nothing, so a detector is scored with the confusion matrix, precision and recall, and
with stratified folds when the rare class is small. And a classifier knows only the classes it was
shown: the network that caught 96% of the faults it learned caught almost none of some it had
never seen.

Experiment tracking exists to answer which run produced a number and whether it can be reproduced, and it answers that only if each run records its hyperparameters, metrics, code SHA, data hash, seed, and environment. MLflow gives you experiments, runs, autologging, nested runs, and a Model Registry with loadable model URIs, backed locally by a SQLite store now that the bare file store is deprecated. Hyperparameter search should prefer random or Bayesian strategies over grid, because most hyperparameters do not matter and a grid wastes its budget on the ones that do not; Optuna's TPE finds good configurations in fewer trials, though on an easy problem like the power plant the sampler barely beats random. The catch is statistical: a search reports the best of many trials, and the best validation score is optimistic by construction, so report the distribution, select with the one-standard-error rule, and compute the test score once.

## Resources

- Victor Alves, [06-325 Numerical Methods and Machine Learning for Chemical
  Engineers](https://victor-alves.com/06325-Numerical-Methods-and-ML-for-ChemE/09-ml-3.html)
  (Fall 2025), lecture 9, "Introduction to classification". The undergraduate version of the first
  half of this session: Gini impurity, softmax and cross-entropy, a GP classifier, and the moons.
- scikit-learn User Guide, [classification metrics](https://scikit-learn.org/stable/modules/model_evaluation.html#classification-metrics).
  The confusion matrix, precision, recall and F1, with the averaging options for more than two
  classes.
- scikit-learn, [`log_loss`](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.log_loss.html).
  The cross-entropy that logistic regression and classification networks minimize, defined as a
  negative log-likelihood.
- scikit-learn, [`StratifiedKFold`](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedKFold.html).
  Folds that preserve the percentage of samples of each class.
- Victor Zhou, [A Simple Explanation of Gini Impurity](https://victorzhou.com/blog/gini-impurity/).
  The source of the four-blue-one-red example.
- Rasmussen and Williams, [*Gaussian Processes for Machine Learning*](https://gaussianprocess.org/gpml/),
  chapter 3. Classification with a latent function and a link, and the Laplace approximation that
  scikit-learn's `GaussianProcessClassifier` uses.
- Rieth, Amsel, Tran and Cook (2017), [Additional Tennessee Eastman process simulation
  data](https://doi.org/10.7910/DVN/6C3JR1). The source of both plant files; the 20 disturbances are
  listed in the header of Downs and Vogel's [original simulation
  code](https://depts.washington.edu/control/LARRY/TE/download.html).

- [MLflow Tracking documentation](https://mlflow.org/docs/latest/ml/tracking/). Experiments, runs, `log_param`/`log_metric`/`log_artifact`, and nested runs, from the source.
- [MLflow autologging](https://mlflow.org/docs/latest/ml/tracking/autolog/). What `mlflow.autolog` records for scikit-learn, including the parent-plus-nested-child run structure a search produces.
- [MLflow Model Registry](https://mlflow.org/docs/latest/ml/model-registry/). Registering a model, versions and aliases, and loading back by `models:/` URI.
- [Optuna documentation](https://optuna.readthedocs.io/en/stable/). The study and trial model, define-by-run search spaces, the default TPE sampler, and the median and successive-halving pruners.
- [Bergstra and Bengio, "Random Search for Hyper-Parameter Optimization," JMLR 2012](https://www.jmlr.org/papers/v13/bergstra12a.html). Why random beats grid, and the low-effective-dimensionality argument behind it.
- [Li et al., "Hyperband: A Novel Bandit-Based Approach to Hyperparameter Optimization," JMLR 2018](https://arxiv.org/abs/1603.06560). Adaptive resource allocation and early stopping for large searches.
- [Hastie, Tibshirani, and Friedman, *The Elements of Statistical Learning*, ch. 7](https://hastie.su.domains/ElemStatLearn/). Section 7.10 states the one-standard-error rule and the model-assessment framing this session rests on.
- [Cawley and Talbot, "On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation," JMLR 2010](https://www.jmlr.org/papers/v11/cawley10a.html). The formal case for why selecting and reporting on the same data biases the estimate.
- [Raschka, "Model Evaluation, Model Selection, and Algorithm Selection in Machine Learning" (arXiv:1811.12808)](https://arxiv.org/abs/1811.12808). A readable walkthrough of nested cross-validation and honest reporting.
- [UCI Combined Cycle Power Plant dataset](https://archive.ics.uci.edu/dataset/294/combined+cycle+power+plant). The 9,568-record set (Tüfekci 2014) that the hyperparameter search uses.

## Assignment

Assignment 5, "Model-selection study with tracked experiments," is released today and is due about a week later. It asks you to take one engineering regression dataset from data to a defended model choice, with every run tracked in MLflow, a systematic hyperparameter search, and a single honest test estimate reported at the end. This paragraph is a pointer, not the rubric.

## Practice module

<a href="../../game/#/l10"><strong>Practice module for this session</strong></a>, about ten
minutes of questions drawn from this session's notes, slides and demo. It runs entirely in
your browser, the questions are selected from your Andrew ID, and it ends by producing a PDF
you upload for participation credit.
