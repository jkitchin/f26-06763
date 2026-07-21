# L1 · The AI-engineering landscape and the modern toolchain

:::{admonition} At a glance
:class: tip

- **Session** L1, Week 1 · **Arc** Foundations
- **Slides** <a href="../../slides/l01.html">Deck for this session</a>
- **Demo** `demo.ipynb`, the UCI Air Quality notebook that fails to reproduce
- **Assignment** A1 released at L2
:::

## Why this matters

In 2015 a group of Google engineers published a paper with an unusually blunt diagram. It
drew the components of a production machine learning system as boxes sized by the code each
one required. Configuration, data collection, feature extraction, serving infrastructure,
and monitoring were large. The box in the middle was small, and the caption said plainly:
"The box labeled 'ML Code' is actually tiny in proportion to the rest of the system."

That proportion is the subject of this course. You have almost certainly trained a model in
a notebook. You may not yet have had to answer the question a regulator, a safety reviewer,
or a colleague joining in eighteen months will ask: can you rebuild this exact result, and
can you show where the numbers came from. Those questions are not answered by a better
architecture. They are answered by infrastructure.

Engineering data makes the gap wider than it is in the domains where machine learning
methodology is usually taught. A sensor is not a static dataset. It drifts, it needs
recalibration, it samples irregularly, it reports in physical units that must be tracked or
the analysis is meaningless, and its output may end up in a safety case that has to be
defensible years later. A pipeline that quietly loses provenance is not merely untidy in
that setting. It is unusable, and occasionally it is dangerous.

:::{admonition} A note on the "10%" figure
:class: note

You will often see this paper cited as showing that "less than 10% of the code is the
model." That number does not appear in the paper. Sculley and colleagues say only that the
ML code box is "tiny in proportion to the rest of the system." The invented precision is a
small example of a habit this course will keep pushing against: check the claim against the
source, and cite what the source actually says.
:::

## Learning objectives

By the end of this session you should be able to:

- Map the end-to-end lifecycle of an engineering ML system and identify the standardized
  toolchain used throughout the semester.
- Contrast "a model in a notebook" with "a system," naming the data contracts, drift, and
  monitoring concerns that separate them.
- Explain why engineering data imposes provenance and traceability requirements that
  general-purpose ML tutorials ignore.
- Justify each component of the course toolchain in terms of the failure it prevents.

## The system view, and where the work actually is

Name the stages explicitly, because each one becomes a later arc of the course: data
acquisition, storage, pipelines, features, training, evaluation, deployment, and
monitoring. Read left to right that looks like a linear process, which is the first thing
to unlearn. Real systems iterate hard between features and evaluation, and the monitoring
stage feeds back into acquisition when drift appears in production.

The stages also tell you where failures cluster, and it is not where students expect. Very
few production incidents are caused by choosing the wrong model class. Most are caused by a
schema that changed upstream without warning, a feature computed one way in training and
another way in serving, or a source that silently started returning nulls. These are
integration failures, and cross-validation cannot see them.

### Case study: 15,841 cases that fell off the end of a spreadsheet

In late September 2020, Public Health England was moving COVID-19 test results from a
laboratory surveillance system into the national contact-tracing system. Commercial labs
submitted results as CSV files without difficulty. PHE's own tooling then consolidated
those results into Excel templates, and the developers had chosen the legacy `.xls` format,
which caps a worksheet at 65,536 rows. Because each test result occupied several rows, each
template in practice held about 1,400 cases. When a file hit the ceiling, the remaining
rows were not rejected with an error. They were simply absent.

The result was that 15,841 positive cases recorded between 25 September and 2 October 2020
were never passed to contact tracers, more than three quarters of them in the final three
days. People who tested positive were told their results. Their contacts were not traced.
By the following Monday, roughly half of the affected cases had still not been reached.

Nothing about this was a modelling failure. Every dashboard and epidemiological model
downstream was computing correctly on the data it received. The failure was that a format
decision made years earlier silently discarded records, and no process compared the count
of results sent by the labs against the count arriving in the tracing system. A model
cannot detect the absence of records it was never shown. That reconciliation check, the
least glamorous thing in the pipeline, was the missing control.

:::{admonition} What a practitioner should take from this
:class: tip

Put integrity checks at every system boundary, and make them count-based. "Did the number
of records I sent equal the number that arrived" catches an entire class of silent failure
that no amount of model sophistication will. Prefer formats that fail loudly over formats
that truncate quietly.
:::

Sculley and colleagues gave the general pattern a name, hidden technical debt, and their
specific mechanisms are worth carrying with you. **Glue code**, the connective tissue that
exists only to move data between systems, tends to dominate the codebase. **Pipeline
jungles** emerge when that glue accretes without anyone redesigning it. **Undeclared
consumers** are the most insidious: some downstream process depends on your output, you do
not know it exists, and you break it.

## Validating well is not evidence that a system works

This is the hardest lesson in the course to accept, because it contradicts the way machine
learning is usually taught and assessed. A model can be validated carefully, by a competent
team, using a protocol stricter than most production work receives, and still be wrong for
years in deployment.

### Case study: Google Flu Trends

Google Flu Trends launched in November 2008 with a genuinely attractive premise. Influenza
surveillance ran on a one to two week reporting lag, and search queries were available
almost immediately. If search behaviour tracked influenza prevalence, you could see the
epidemic sooner.

The validation was good. Screening 50 million candidate queries down to 45, fitting against
regional surveillance data, the published model reported a mean correlation of 0.97 across
nine regions on held-out data that had been excluded from every prior modelling step. That
is a more disciplined protocol than a great deal of deployed machine learning gets even
now.

In deployment it drifted badly. By the 2012 to 2013 season the system was estimating more
than double the CDC's figure for influenza-like illness. Across the 108 weeks from August
2011 to September 2013 it was too high in 100 of them. A retrospective in *Science*
identified two mechanisms.

The first they called **big data hubris**, the assumption that a large dataset substitutes
for rather than supplements careful measurement. In practice it showed up as overfitting:
searching 50 million terms for correlations against roughly a thousand data points is
nearly guaranteed to find seasonal patterns that have nothing to do with influenza. The
developers had already been manually removing terms like high school basketball that
correlated with flu season without being about flu, which should have been read as a
warning rather than a cleaning step. The authors' summary is the line worth remembering:
the initial system was "part flu detector, part winter detector." It failed exactly where
that description predicts, missing the non-seasonal 2009 H1N1 pandemic entirely.

The second they called **algorithm dynamics**, meaning that the data-generating process was
itself under continuous modification. Google's search team shipped 86 changes in June and
July of 2012 alone, including features that suggested related searches and surfaced
possible diagnoses for symptom queries. Each was an improvement to the search product. None
of the engineers involved knew that a flu model depended on the distribution of queries
they were changing. This is Sculley's undeclared consumer, appearing inside the same
company.

The detail that should bother you most is the failure signature. A hundred wrong weeks out
of 108, all in the same direction, is not a subtle statistical artifact. It was visible for
two years. A study had already shown that simply projecting forward from three-week-old
surveillance data outperformed the model. The real failure was not the model at all; it was
the absence of any continuous evaluation harness comparing it against a boring baseline.

:::{admonition} What a practitioner should take from this
:class: tip

Hold-out validation tells you about the distribution you sampled from, and nothing about
the distribution you will meet next year. Two habits follow. Always maintain a
stupid-but-honest baseline in production and keep comparing against it, because a model
that cannot beat a lagged average is a result you want to discover early. And check whether
anything upstream of your features is under active development by a team that does not know
you exist.
:::

## Why engineering data is different

Everything above applies to machine learning generally. Three properties of engineering
data sharpen it further.

**Units and calibration.** A model that ingests a raw sensor voltage and a model that
ingests a calibrated concentration are not the same model, even with identical weights, and
the difference will not appear in a validation metric. It appears when someone recalibrates
the instrument.

**Drift.** Physical sensors degrade. The dataset we use today is a case in point: a
metal-oxide gas sensor array deployed on an Italian roadside, recording hourly from March
2004 through February 2005, 9,358 instances in total. The documentation states explicitly
that both cross-sensitivities and concept and sensor drift are present. A model trained on
the first three months and validated on a random split of those same months will look
excellent and will be worthless by the following winter, because the random split let it
see the future.

**Provenance.** In a regulated or safety-relevant setting you may be required to
reconstruct which data, which code, and which parameters produced a specific number. If the
answer involves a notebook run out of order on a laptop that has since been reimaged, there
is no answer. This is why reproducibility is treated here as an engineering requirement
rather than as good hygiene.

### Case study: a single angle-of-attack sensor

The 737 MAX accidents are the sharpest available illustration that in engineering systems,
where a number comes from is part of the safety argument. The discussion here is limited to
what the accident investigations concluded.

MCAS was a control function that commanded nose-down stabilizer trim under certain flight
conditions. Each aircraft carried two angle-of-attack sensors. MCAS was designed to use one
of them at a time, alternating between flights, with no cross-comparison and no voting
between the two. A single faulty sensor was therefore sufficient to drive the function.

On Lion Air 610 the left sensor carried a bias of roughly 21 degrees. The Indonesian
investigation traced it to a replacement sensor that had been mis-calibrated during an
earlier repair, with the error undetected both at the repair and by the installation test.
That is a calibration provenance failure in the most literal sense: a physical measurement
channel whose correctness nobody had established, feeding a control law with authority over
a flight surface.

The compounding failure was in the analysis. Boeing's hazard assessment had evaluated
scenarios involving erroneous data from *both* air data channels and judged their combined
probability beyond extremely improbable. But the actual MCAS input path was vulnerable to a
*single* failure, so the analysis had modelled the wrong failure set. The residual risk was
absorbed by an assumption that the crew would respond correctly within a few seconds, an
assumption held even though the same underlying fault simultaneously produced stick shaker,
airspeed disagreement, and altitude disagreement, effects the certifying simulations never
reproduced because they injected the symptom rather than its cause.

The investigation's contributing factors state the causal order plainly: incorrect
assumptions about flight crew response, combined with an incomplete review of the
associated flight deck effects, were what made reliance on a single sensor appear
acceptable. Lion Air 610 killed 189 people in October 2018. Ethiopian Airlines 302 killed
157 in March 2019.

:::{admonition} What a practitioner should take from this
:class: tip

Ask three questions of every input your system treats as ground truth. Where did this
measurement come from, is it independently corroborated, and what happens downstream when
it is wrong. If the answer to the third is "an operator will notice and compensate," that
is a design decision requiring evidence, not an assumption you are entitled to make.
:::

## The standardized toolchain

We fix one toolchain for the semester so class time goes to concepts rather than tool
selection. Each choice exists to prevent a specific failure, and it is worth naming the
failure rather than the feature.

Python with `uv` handles environments and dependencies, because a lockfile plus a pinned
interpreter is what makes a rebuild deterministic rather than merely likely. MLflow tracks
experiments from Week 5, on the principle that one run should equal one reproducible fact,
which is the smallest unit of the provenance requirement above. PostgreSQL, DuckDB, and
Parquet cover storage from Week 2, with a vector store added when retrieval arrives in
Week 10; the PHE case is a reasonable argument for why the storage layer deserves a choice
rather than a default. pandas and Polars handle dataframes from Week 3. PyTorch covers deep
learning from Week 6.

The LLM and agent material in Weeks 9 through 11 is deliberately framework-agnostic and
provider-agnostic. That part of the ecosystem turns over faster than a semester, so the
course teaches the interfaces and the evaluation discipline rather than a specific vendor's
abstractions.

:::{admonition} Common pitfall
:class: warning

The most frequent reproducibility break is not an exotic dependency conflict. It is an
absolute file path, an unpinned random seed, or hidden notebook state from running cells
out of order. Get in the habit of "Restart and Run All" before you trust any notebook
result, including your own.
:::

## In-class demo

We walk a single notebook that ingests the UCI Air Quality data, plots a reference CO
measurement against the corresponding sensor response, and fits a naive train/test split.
It works, and it looks convincing.

Then we run the same notebook on a fresh checkout, where it breaks three times. Your job is
to diagnose each break before I do: a missing package version, an unpinned seed producing
different numbers, and an absolute path that existed only on my machine. Every one of these
is mundane. That is the point.

The runnable version is `demo.ipynb`.

## Summary

A model is a small component inside a system whose bulk is data infrastructure, evaluation,
and operations, and that is where both the engineering effort and the failures concentrate.
Three cases make the shape of it concrete. Public Health England lost 15,841 records to a
file format and a missing count check, with no model involved. Google Flu Trends validated
at a correlation of 0.97 and was then wrong in the same direction for a hundred weeks
because nobody was watching it against a baseline. MCAS treated one uncorroborated sensor
as ground truth, and the safety analysis had modelled a different failure than the one the
design was exposed to. Engineering data sharpens all of this by adding units, calibration,
drift, and traceability. The toolchain we standardize on is not arbitrary; each piece
answers a specific way that undisciplined work falls apart. Next session we build the
reproducible scaffold for real, from an empty directory to a tracked, rerunnable
experiment.

## Resources

- [Hidden Technical Debt in Machine Learning Systems](https://papers.nips.cc/paper_files/paper/2015/file/86df7dcfd896fcaf2674f757a2463eba-Paper.pdf). Sculley et al., NeurIPS 2015. The source of the framing above, and of glue code, pipeline jungles, and undeclared consumers. Nine pages, and worth reading in full.
- [The Parable of Google Flu: Traps in Big Data Analysis](https://gking.harvard.edu/files/gking/files/0314policyforumff.pdf). Lazer, Kennedy, King and Vespignani, *Science* 2014. Three pages, and the source of every GFT figure quoted above. This is a co-author's copy; the publisher's version sits behind a paywall.
- [Detecting influenza epidemics using search engine query data](https://static.googleusercontent.com/media/research.google.com/en//archive/papers/detecting-influenza-epidemics.pdf). Ginsberg et al., *Nature* 2009. Read this one *before* the Lazer critique, so you see how reasonable it looked at the time.
- [PHE statement on delayed reporting of COVID-19 cases](https://www.gov.uk/government/news/phe-statement-on-delayed-reporting-of-covid-19-cases). the official statement, for the 15,841 figure and the dates.
- [Excel: Why using Microsoft's tool caused Covid-19 results to be lost](https://www.bbc.co.uk/news/technology-54423988). BBC, for the technical mechanism. The clearest published account of how the truncation actually happened.
- [The Design, Development & Certification of the Boeing 737 MAX](https://www.govinfo.gov/content/pkg/GOVPUB-Y4_T68_2-PURL-gpo144993/pdf/GOVPUB-Y4_T68_2-PURL-gpo144993.pdf). US House Committee on Transportation and Infrastructure, September 2020. Long; the single-sensor discussion is around p. 106.
- [UCI Air Quality Data Set](https://archive.ics.uci.edu/dataset/360/air+quality). dataset description and citation. Read the note on cross-sensitivities and drift before Thursday.
- [uv documentation, Getting started](https://docs.astral.sh/uv/getting-started/). install it before L2, because we build live.
- [The Turing Way, Reproducible Research](https://book.the-turing-way.org/reproducible-research/reproducible-research). the broader case, if the motivation section left you unconvinced.

## Assignment

A1, the reproducible project scaffold, is released at L2 and due roughly one week later. It
asks you to stand up a `uv`-managed, git-tracked project that pulls an engineering dataset
and converts an exploratory notebook into a runnable module. The full spec and rubric are
in `course/assignments/a01.md`.
