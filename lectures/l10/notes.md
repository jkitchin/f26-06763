# Lecture 10: Experiment tracking and hyperparameter search

:::{admonition} Overview
:class: tip

- **Session** Lecture 10, Week 5
- **Arc** Machine learning and deep learning
- **Slides** <a href="../../slides/l10/">Deck for this session</a>
- **Practice** <a href="../../game/#/l10">Practice module for this session</a>
- **Demo** [`l10-tracking-search.ipynb`](l10-tracking-search.ipynb), an Optuna study wrapped in MLflow, from search to a registered model
- **Assignment 5**, released at Lecture 9; this session is its tracking and search half
:::

## Why this matters

By the end of a real model-selection study you will have run the training script hundreds of times: different features, different model families, different hyperparameters, different seeds. A week later a colleague asks which run produced the 3.2 MW error in your slide, and whether they can reproduce it. If your answer is a folder of timestamped files and your memory, the honest answer is no.

[Lecture 9](../l09/notes.md) built the workflow that produces those runs: baselines, cross-validation, metrics, and the discipline of touching the test set once. This session is about keeping the record of that work, and about searching the hyperparameter space without fooling yourself. The two are the same problem seen twice. A hyperparameter search is a machine for generating hundreds of runs and picking the best one, and picking the best one is exactly where an unrecorded, unexamined study quietly lies to you. So we log every run with enough detail to rebuild it, we search with a strategy rather than by hand, and we read the results knowing that the best validation score is an optimistic number by construction.

The dataset stays the same as Lecture 9: the UCI Combined Cycle Power Plant (CCPP) set, 9,568 hourly records of four ambient measurements (temperature, exhaust vacuum, pressure, humidity) predicting net electrical output in megawatts. It is a steady-state surrogate problem, the kind that recurs for pump curves and engine maps, and it is small and clean enough that a full search runs in class.

## Learning objectives

By the end of this session you should be able to:

- Instrument a training script so every run is logged, comparable, and reproducible.
- Run grid, random, and Bayesian hyperparameter search and interpret the results honestly.
- Register a selected model with its metrics, params, and data lineage.

## What every run has to record

```{index} experiment tracking, run metadata, data lineage
```

The purpose of tracking is to answer one question after the fact: which run produced this number, and can I produce it again? A run that logs only its score cannot answer it. A run answers it when it records everything needed to rebuild itself.

That list is specific, and it ties this session back to the rest of the course. Log the **hyperparameters** and the **metrics** (per fold, not just the average, so you can see the variance). Log the **git commit SHA** (secure hash algorithm) of the code, so the exact program is recoverable. Log the **dataset version or content hash** from [Lecture 8](../l08/notes.md), so the exact inputs are pinned. Log the **random seed** and the **environment**, which is the `uv.lock` from [Lecture 2](../l02/notes.md). And log the **artifacts**: the fitted pipeline, the plots, the feature importances. The rule from Lecture 2 returns with more force here, because a search multiplies the number of runs by a hundred: one run equals one fact you can reproduce, and a run you cannot rebuild is a number you cannot defend.

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
    mlflow.log_param("data_md5", data_hash)         # lineage, from Lecture 8
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

We wrap the Week-5 power-plant models in MLflow, using the local SQLite store. An Optuna study searches gradient-boosting hyperparameters with each trial logged as a nested MLflow run, so the whole search is visible in the UI. We open the tracking UI, sort by validation RMSE, and read the parallel-coordinates and contour plots to see which hyperparameters actually mattered. Then we register the winning model, load it back by its `models:/` URI for a fresh prediction, and compute the single held-out test score that is the number we would actually report. The moment to watch is the gap between the best validation score in the sorted list and that final test number: the search optimizes the first, and honesty reports the second. The runnable notebook is [`l10-tracking-search.ipynb`](l10-tracking-search.ipynb).

## Summary

Experiment tracking exists to answer which run produced a number and whether it can be reproduced, and it answers that only if each run records its hyperparameters, metrics, code SHA, data hash, seed, and environment. MLflow gives you experiments, runs, autologging, nested runs, and a Model Registry with loadable model URIs, backed locally by a SQLite store now that the bare file store is deprecated. Hyperparameter search should prefer random or Bayesian strategies over grid, because most hyperparameters do not matter and a grid wastes its budget on the ones that do not; Optuna's TPE finds good configurations in fewer trials, though on an easy problem like the power plant the sampler barely beats random. The catch is statistical: a search reports the best of many trials, and the best validation score is optimistic by construction, so report the distribution, select with the one-standard-error rule, and compute the test score once.

## Resources

- [MLflow Tracking documentation](https://mlflow.org/docs/latest/ml/tracking/). Experiments, runs, `log_param`/`log_metric`/`log_artifact`, and nested runs, from the source.
- [MLflow autologging](https://mlflow.org/docs/latest/ml/tracking/autolog/). What `mlflow.autolog` records for scikit-learn, including the parent-plus-nested-child run structure a search produces.
- [MLflow Model Registry](https://mlflow.org/docs/latest/ml/model-registry/). Registering a model, versions and aliases, and loading back by `models:/` URI.
- [Optuna documentation](https://optuna.readthedocs.io/en/stable/). The study and trial model, define-by-run search spaces, the default TPE sampler, and the median and successive-halving pruners.
- [Bergstra and Bengio, "Random Search for Hyper-Parameter Optimization," JMLR 2012](https://www.jmlr.org/papers/v13/bergstra12a.html). Why random beats grid, and the low-effective-dimensionality argument behind it.
- [Li et al., "Hyperband: A Novel Bandit-Based Approach to Hyperparameter Optimization," JMLR 2018](https://arxiv.org/abs/1603.06560). Adaptive resource allocation and early stopping for large searches.
- [Hastie, Tibshirani, and Friedman, *The Elements of Statistical Learning*, ch. 7](https://hastie.su.domains/ElemStatLearn/). Section 7.10 states the one-standard-error rule and the model-assessment framing this session rests on.
- [Cawley and Talbot, "On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation," JMLR 2010](https://www.jmlr.org/papers/v11/cawley10a.html). The formal case for why selecting and reporting on the same data biases the estimate.
- [Raschka, "Model Evaluation, Model Selection, and Algorithm Selection in Machine Learning" (arXiv:1811.12808)](https://arxiv.org/abs/1811.12808). A readable walkthrough of nested cross-validation and honest reporting.
- [UCI Combined Cycle Power Plant dataset](https://archive.ics.uci.edu/dataset/294/combined+cycle+power+plant). The 9,568-record set (Tüfekci 2014) used here and in Lecture 9.

## Assignment

Assignment 5, "Model-selection study with tracked experiments," was released at [Lecture 9](../l09/notes.md) and is due about a week later. This session is its second half: take one engineering regression dataset from data to a defended model choice, with every run tracked in MLflow, a systematic hyperparameter search, and a single honest test estimate reported at the end. This paragraph is a pointer, not the rubric.

## Practice module

<a href="../../game/#/l10"><strong>Practice module for this session</strong></a>, about ten
minutes of questions drawn from this session's notes, slides and demo. It runs entirely in
your browser, the questions are selected from your Andrew ID, and it ends by producing a PDF
you upload for participation credit.
