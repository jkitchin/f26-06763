# Lecture 8: Data quality, versioning, and leakage-free splits

:::{admonition} Overview
:class: tip

- **Session** Lecture 8, Week 4
- **Arc** Data Systems
- **Slides** <a href="../../slides/l08/">Deck for this session</a>
- **Demo** [`l08-splits-versioning.ipynb`](l08-splits-versioning.ipynb), the split that inflates a score, then versioning and tracking
- **Assignment 4**, released at Lecture 7; its dataset-versioning half is this session's material
:::

## Why this matters

[Lecture 7](../l07/notes.md) ended on a leak so small you could miss it. Fitting a scaler on the test data instead of the training data changed the reported error by about 0.002 cycles, because an unregularized linear model barely cares how its inputs are scaled. This session opens with the opposite: a leak from the same dataset that makes a model look **37% better than it really is**, and that you would ship without noticing, because the number it produces looks good.

The leak is in the **split**. On the C-MAPSS turbofan data from Lecture 7, we build ordinary per-engine features and predict remaining useful life with one model, then score it two ways that differ only in how the rows are divided into training and test. A random split of the rows reports a root-mean-square error of **12.2 cycles**. A split that keeps each engine wholly in training or wholly in test reports **16.7 cycles**. Same features, same model, same data. The first number is a fiction: because consecutive cycles of one engine are almost identical, a random split drops cycle 150 of an engine into training and cycle 151 into test, so the model is graded on rows nearly identical to ones it has already seen. The 12.2 is the score on a problem the model will never face. The 16.7 is the score on the problem it will.

This is the most consequential mistake in the whole data arc, because it does not fail loudly. The pipeline runs, the metric improves, the plot looks clean, and the model is quietly worthless on the first engine it has never met. This session is about the three habits that keep it honest: splitting the data so the evaluation measures deployment, versioning the data so a result can be reproduced from its raw inputs, and iterating on the data itself rather than only on the model.

## Learning objectives

By the end of this session you should be able to:

- Design leakage-free splits for temporal and grouped data and detect leakage empirically.
- Version datasets and feature sets so results are reproducible from raw inputs.
- Run a data-centric improvement loop and attribute gains to data changes.

## Splits done right

```{index} train/test split, grouped split, GroupKFold, temporal split, TimeSeriesSplit, nested cross-validation
```

A train/test split has one job: to make the test set a fair stand-in for the data the model will see in deployment. Every splitting rule in this section follows from that one requirement, and the default tool most people reach for, a random shuffle, violates it for the two kinds of data engineering produces most often: grouped data and time-series data.

The C-MAPSS data is both. It is **grouped** because every row belongs to one of 100 engines, and the deployment question is always about a *new* engine, not a new cycle of an engine you have already watched fail. It is **temporal** because within an engine the rows are ordered by cycle, and the deployment question is always about the *future*, not a cycle wedged between two you have already seen. A random shuffle ignores both facts. It splits at the level of the row, so the same engine lands in both halves, and it splits without regard to time, so the model trains on cycle 151 and is tested on cycle 150.

The fix for grouped data is a **grouped split**: assign whole groups to training or test, so no group is in both.

:::{admonition} Definition: grouped split
:class: tip

A **grouped split** divides the data by an entity, such as an engine, a patient, or a site, so that all rows from one entity fall entirely in training or entirely in test. In scikit-learn, `GroupKFold` "ensures that the same group is not represented in both testing and training sets," and `GroupShuffleSplit` holds out a random subset of groups. Use them whenever rows from the same entity are correlated.
:::

The fix for time-series data is a **temporal split**: train on the past and test on the future, never the reverse.

:::{admonition} Definition: temporal split
:class: tip

A **temporal split** trains on earlier data and tests on later data, so the model is never evaluated on a time it could have learned from. scikit-learn's `TimeSeriesSplit` does this across several folds, and its "successive training sets are supersets of those that come before them," growing the training window forward through time.
:::

The two concerns can compound, and a serious evaluation respects both. If you want a model that generalizes to a new engine *and* forecasts forward in time, you hold out whole engines and, within the training engines, respect cycle order. When you also need to tune hyperparameters, the honest structure is **nested cross-validation**: an outer split that estimates performance and an inner split, carved only from the outer training data, that selects the model. Collapsing the two, tuning on the same data you report, is a milder cousin of the same leak this session is about, because the reported number then reflects a configuration chosen with the test set in view.

The measured cost of getting this wrong is the figure below. It is the same RandomForest on the same 46 features; only the split changes.

```{figure} figures/leakage.png
:alt: Two bars of remaining-useful-life error. A random row split reports RMSE 12.2 cycles; a per-unit GroupKFold split reports 16.7 cycles, about 1.37 times higher.
:width: 80%
:align: center

The same model and features scored two ways. A random row split reports 12.2 cycles of error because adjacent cycles of one engine leak across the split; the honest per-unit split reports 16.7. The leak makes the model look about 1.37 times better than it is on a new engine.
```

The schematic makes the mechanism visible. Under a random split every engine contributes rows to both training and test; under a grouped split, whole engines are held out.

```{figure} figures/splits.png
:alt: Two panels showing six engines as rows of cycle cells. On the left, a random split colors cells train or test at random so every engine has both; on the right, a grouped split colors whole engines either train or test.
:width: 100%

The same fleet, split two ways. Left: a random row split scatters every engine across both sets, so the model is tested on near-duplicates of its training rows. Right: a per-unit split holds out whole engines, which is the question deployment actually asks.
```

## A taxonomy of leakage

```{index} data leakage, target leakage, temporal leakage, group leakage
```

Leakage is the general fault the split above is one instance of. The definition worth memorizing comes from Kaufman and colleagues, who call it "one of the top ten data mining mistakes."

:::{admonition} Definition: leakage
:class: tip

**Leakage** is, in the words of [Kaufman et al. (2012)](https://www.cs.umb.edu/~ding/history/470_670_fall_2011/papers/cs670_Tran_PreferredPaper_LeakingInDataMining.pdf), "the introduction of information about the target of a data mining problem, which should not be legitimately available to mine from." A model that learns from leaked information reports a score it cannot reproduce in deployment, because the leaked information will not be there.
:::

Leakage arrives in four recognizable shapes, and a good audit checks for each by hand, because no metric will announce them.

**Target leakage** is a feature that encodes the label, often through the way the data was recorded. A "number of late-payment reminders sent" column predicts default almost perfectly, because it is filled in *after* the customer defaults. On a sensor feed the equivalent is a maintenance-action flag that a technician sets once a failure is already visible. Audit it by asking, of every feature, whether its value would actually be known at the moment you need a prediction.

**Train/test contamination** is a statistic computed over all the data before the split, which is the Lecture 7 scaler leak: a mean, a standard deviation, an imputation value, or a category list fit on rows that include the test set. Audit it by finding every `.fit()` call and confirming the test rows were not in scope when it ran, which is exactly what a scikit-learn `Pipeline` fit inside the split guarantees.

**Temporal leakage** is using the future to predict the past: a rolling feature that reaches forward, a target defined over a window that overlaps the features, or simply a random split of time-ordered data. Audit it by checking that every feature at time *t* depends only on data from time *t* or earlier.

**Group leakage** is the split from the previous section: rows from the same entity in both training and test. Audit it by confirming your split key is the entity, not the row.

The reason leakage deserves its own vocabulary is that it defeats the instrument you would normally trust. Your validation score is supposed to tell you whether the model works. When the data leaks, the score tells you how well the model exploited information it will not have, and a higher score is then worse news, not better. You cannot find leakage by looking at the metric; you find it by reasoning about where each number came from.

## Versioning data and features

```{index} data versioning, DVC, content hash, dvc.yaml
```

Reproducibility, from [Lecture 2](../l02/notes.md), is the ability to take your data and your code and get your numbers back. Lecture 2 versioned the code with git and kept the raw data out of git behind a content hash. This session closes the remaining gap: a tool that versions the data and the derived feature sets *by content*, and ties a specific data version to the code version and the experiment that used it.

That tool is **DVC** (Data Version Control). Its model is simple and worth understanding before the commands. When you run `dvc add features.parquet`, DVC computes a content hash of the file, moves the file into a local cache, and writes a small text file next to it.

:::{admonition} Definition: DVC and the `.dvc` file
:class: tip

**DVC** versions large data and model files alongside code in git. For each tracked file it writes a small `.dvc` metafile that, in the [DVC docs'](https://dvc.org/doc/start/data-management/data-versioning) words, "acts as a placeholder for the original data for the purpose of Git tracking." The metafile holds the content hash and path (for example `md5: 22a1a29...` and `path: features.parquet`); git tracks the metafile, and the raw bytes go to a cache and a remote. A DVC "remote" can be "just a directory in the local file system," so you need no cloud account to use it.
:::

Because git now tracks the hash and the code together, checking out an old commit gives you the exact code *and* a pointer to the exact data that went with it; `dvc checkout` then restores that data from the cache. The version of the data is pinned as precisely as the version of the code.

DVC also records the pipeline that produced a feature set, so the derivation is reproducible and not only the file. A `dvc.yaml` file lists **stages**, each of which "wraps around an executable shell command and specifies any file-based dependencies as well as outputs" through `deps:` and `outs:`. Running `dvc repro` re-executes only the stages whose inputs changed, skipping the rest, which turns "rebuild the feature matrix from raw data" into one command that is guaranteed to match what a commit describes.

The habit that makes this pay off is to log the data version next to the run that used it. When you train a model, record the DVC hash of the input data as a parameter in your experiment tracker, so an [MLflow](../l02/notes.md) run carries the git SHA of the code, the DVC hash of the data, and the seed together. Recreate those three and you recreate the result, from raw inputs to reported number.

## Documenting a dataset

A hash tells you *that* a dataset is a particular version; it says nothing about what is in it, how it was collected, or what it is safe to use for. That description is the job of a **datasheet**, and writing one is the difference between a dataset a colleague can use correctly and one they will misuse in good faith.

:::{admonition} Definition: datasheet for a dataset
:class: tip

A **datasheet** is a structured document, proposed by [Gebru et al. (2021)](https://arxiv.org/abs/1803.09010), that records a dataset's "motivation, composition, collection process, recommended uses, and so on." The paper gives 57 questions across seven sections, from why the data was collected to how it should be maintained, by analogy with the datasheet that accompanies an electronic component.
:::

For engineering data the high-value entries are provenance and known issues: which instrument and firmware produced the readings, the units and sample rate of each channel, the calibration state, and the defects you already know about. C-MAPSS is a clean example to document, because it has surprises worth writing down. Six of its 21 sensor channels are constant and carry no information, the remaining-useful-life target in the training set is the true cycle count while the test set withholds it, and the "operating condition" is fixed for FD001 but varies in the other three subsets. A one-page card that states those facts saves the next person the hour it costs to rediscover them, and it is the natural home for the pitfalls this arc has surfaced: the dying-battery motes from [Lecture 6](../l06/notes.md), the constant channels from Lecture 7, the units convention on every column.

## Data-centric iteration

```{index} datasheet, data-centric iteration
```

The reflex when a model underperforms is to change the model: a bigger network, a different algorithm, more hyperparameter search. **Data-centric iteration** inverts that reflex. You hold the model fixed and improve the data, then measure whether the data change helped.

:::{admonition} Definition: data-centric iteration
:class: tip

**Data-centric iteration** improves a model by improving its data, labels, and features while holding the model and its hyperparameters fixed, so any change in the score is attributable to the data. The phrasing "data-centric AI" was popularized informally by Andrew Ng in 2021; for a structured treatment see the [MIT Introduction to Data-Centric AI](https://dcai.csail.mit.edu/) course.
:::

The discipline is in the measurement. Fix the model and the split, change one thing about the data (drop the six dead sensor channels, correct a mislabeled failure cycle, add a physically motivated feature, remove the readings from a mote that was below its trustworthy voltage), and log the before and after as two runs in MLflow tagged with the two data versions. The score difference is then a clean attribution to that specific data change, which is a stronger claim than "the model got better after we changed some things." Because the split is held fixed and honest, and the data version is recorded, the improvement is reproducible and defensible in a way that a lucky hyperparameter is not.

## Where this pushes back

Each habit in this session has a limit, and the mature version of this knowledge is knowing where each one stops helping.

### A leakage-free split does not fix distribution shift

A grouped, temporal split makes the test set a fair sample of the *same* data-generating process. It does nothing about a new process. C-MAPSS FD001 is one simulated operating condition, so even the honest 16.7-cycle score is optimistic for a real engine at a new site with a different ambient temperature, a different sensor vendor, and a different duty cycle. An honest split protects you from grading yourself on near-duplicates; it does not promise the world will resemble your training set.

### Grouped and temporal splits cost you data

Holding out whole engines means fewer distinct training entities, and a strict temporal split throws away the most recent data by construction. On a fleet of 100 engines this is affordable; on a study with eight patients it can leave you unable to both train and evaluate. The split still has to be honest, so the answer is usually to collect more entities rather than to relax the split, but the cost is real and worth naming when you plan a data collection.

### Versioning is bookkeeping, not understanding

DVC will faithfully version a corrupt dataset, and a `.dvc` hash proves two runs used identical bytes without saying whether those bytes were any good. Versioning makes a result reproducible and auditable; it is the precondition for catching a data problem, in the same way reproducibility was the precondition for catching a code problem in Lecture 2, and it is no substitute for the validation from Lecture 6 or the physical reasoning from Lecture 7.

### A datasheet is only as honest as its author

A datasheet is unenforced prose. It can be out of date, optimistic, or silent about the defect that matters most, and nothing checks it against the data the way a pandera schema checks a feed. Treat it as documentation that lowers the cost of using data correctly, not as a guarantee that the data is correct.

### Data-centric iteration can overfit the validation set

Running many data changes against one fixed validation split, and keeping the ones that improve it, eventually tunes the data to that split, which is the multiple-comparisons trap from Lecture 7 wearing new clothes. A held-back test set that you touch rarely, and honestly, is what keeps a season of data-centric tweaks from quietly becoming a slow leak.

:::{admonition} What a practitioner should take from this
:class: tip

Choose the split before you choose the model, and choose it to match the deployment question: hold out whole entities when rows are grouped, and train on the past when data is ordered in time. Audit for leakage by reasoning about where each feature's value comes from and when it is known, because your metric will not warn you. Version the data with the same seriousness you version code, and log the data hash, the code SHA, and the seed together so a number can be rebuilt from raw inputs. Then improve the data against a fixed model, and measure the change, so you can say what helped and prove it.
:::

## In-class demo

We take the C-MAPSS feature set from Lecture 7 and score one RandomForest two ways: a random row split and a per-unit `GroupKFold`. The random split reports about 12 cycles of error and the grouped split about 17, and we confirm the mechanism directly by counting how many engines appear in both halves of the random split. We then compute a content hash of the feature file, which is the value a `.dvc` metafile would store, and narrate the DVC workflow (`dvc add`, a `dvc.yaml` stage, a local-directory remote) without needing DVC installed. Finally we log both runs to MLflow tagged with the data hash, so the honest and leaky scores sit side by side as reproducible facts, and we run one data-centric change against the fixed model to show the score move attributed to the data.

The moment to watch is the two scores. The leaky split gives the lower error, so it is the one a careless review would ship. The runnable notebook is [`l08-splits-versioning.ipynb`](l08-splits-versioning.ipynb).

## Summary

A train/test split has to make the test set a fair stand-in for deployment, and a random shuffle fails that for the grouped and time-ordered data engineering produces most often. On C-MAPSS the failure is measurable: a random row split reports 12.2 cycles of error and an honest per-unit split reports 16.7, a 37% illusion from nothing but the split. Grouped splits hold out whole entities, temporal splits train on the past, and nested cross-validation keeps tuning out of the reported number. Leakage is the general fault, in four shapes, target, contamination, temporal, and group, and it is found by reasoning about each feature rather than by reading the metric it corrupts. DVC versions the data and the feature pipeline by content, so a run's data can be pinned as precisely as its code and logged beside the git SHA and seed in MLflow. A datasheet records what a hash cannot: provenance, units, and known issues. And data-centric iteration improves the data against a fixed model so the gain is attributable and reproducible. An honest split is the ground the rest of these habits stand on.

## Resources

- [scikit-learn User Guide: Cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html). `GroupKFold`, `GroupShuffleSplit`, and `TimeSeriesSplit`, from the source; the section that turns "split correctly" into specific tools.
- [scikit-learn: Common pitfalls and recommended practices](https://scikit-learn.org/stable/common_pitfalls.html). The library's own writeup of leakage and how fitting inside a pipeline avoids the contamination kind.
- [Kaufman, Rosset, Perlich, Stitelman, "Leakage in Data Mining"](https://www.cs.umb.edu/~ding/history/470_670_fall_2011/papers/cs670_Tran_PreferredPaper_LeakingInDataMining.pdf) (KDD 2011; ACM TKDD 2012, [DOI](https://doi.org/10.1145/2382577.2382579)). The formal definition and taxonomy, and the "learn-predict separation" fix.
- [DVC: Data Versioning](https://dvc.org/doc/start/data-management/data-versioning). What `dvc add` does, what a `.dvc` file contains, and the local-directory remote used in the assignment.
- [DVC: Pipelines](https://dvc.org/doc/user-guide/pipelines). `dvc.yaml` stages with `deps` and `outs`, and `dvc repro` to rebuild only what changed.
- [Gebru et al., "Datasheets for Datasets"](https://arxiv.org/abs/1803.09010) (CACM 2021, [DOI](https://doi.org/10.1145/3458723)). The 57 questions and seven sections; read the Composition and Collection sections first.
- [MIT: Introduction to Data-Centric AI](https://dcai.csail.mit.edu/). A structured course on iterating the data rather than the model; a better anchor than the informal talks that named the idea.
- A. Saxena, K. Goebel, D. Simon, and N. Eklund, "Damage Propagation Modeling for Aircraft Engine Run-to-Failure Simulation," *PHM* 2008 ([NASA NTRS copy](https://ntrs.nasa.gov/citations/20090029214), titled "...Prognostics"). The C-MAPSS methodology and provenance. The four subsets FD001 to FD004 are a property of the [NASA PCoE data set distribution](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/), not of this paper.

## Assignment

Assignment 4, "Feature pipeline and dataset versioning," was released at [Lecture 7](../l07/notes.md) and is due about a week later. Its second half is this session's material: put the C-MAPSS feature set under DVC with a local remote, implement a correct grouped or temporal split, quantify the cost of a leaky split against the honest one, and log both runs to MLflow tagged with the DVC data version. This is a pointer, not the rubric.
