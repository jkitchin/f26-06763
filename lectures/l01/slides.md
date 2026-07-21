---
marp: true
theme: course
paginate: true
header: "06-763 · L1"
footer: "Systems & Toolchains for AI in Engineering"
---

<!-- _class: title -->

# L1 · The system view

## Week 1 · Foundations

**Systems & Toolchains for AI in Engineering**

---

## Roadmap

1. Why the model is the small box
2. Three failures that were not modelling failures
3. What makes engineering data different
4. The toolchain we standardize on

<!-- Timing: 10 / 30 / 15 / 10, leaving 15 for questions.
     The three case studies are the spine of the lecture. If you are running
     long, cut the toolchain section, not a case study. -->

---

## The picture that started this course

Sculley et al., NeurIPS 2015

Boxes sized by the code each requires:

- config, data collection, feature extraction
- serving infrastructure, monitoring

> "The box labeled 'ML Code' is actually tiny
> in proportion to the rest of the system."

---

## An aside on that claim

You will see this cited as **"less than 10% is ML code."**

That number is **not in the paper.**

- The paper says "tiny in proportion"
- The 10% is invented precision, spread by repetition

<!-- Worth 60 seconds. Sets the tone for citation discipline all semester
     and previews the Resources convention in the notes. -->

---

## The stages

**data → storage → pipelines → features → training → evaluation → deployment → monitoring**

- Each stage is a later arc of this course
- Reading it as linear is the first thing to unlearn
- Monitoring feeds back into acquisition

---

## Where failures actually cluster

Not in the model class. In the joints:

- Upstream schema changed, nobody told you
- Feature computed one way in training, another in serving
- A source silently starts returning nulls

**Integration failures.** Cross-validation cannot see them.

---

<!-- _class: section -->

# Case 1
## The model was not involved

---

## Public Health England, September 2020

Pipeline: commercial labs → PHE → contact tracing

- Labs sent **CSV**, no problem
- PHE consolidated into Excel templates
- Developers picked legacy **`.xls`**

`.xls` caps a sheet at **65,536 rows**

---

## What that meant in practice

- Several rows per test result
- So ~**1,400 cases** per template
- Hit the ceiling → remaining rows **silently absent**

No error. No rejection. Just gone.

---

## The cost

**15,841** positive cases, 25 Sep to 2 Oct 2020

- Never passed to contact tracers
- >75% of them in the final three days
- Patients told their results; **contacts never traced**
- By Monday, ~half still not reached

---

## Read the failure carefully

Every model downstream computed **correctly**
on the data it received.

The missing control was the least glamorous
thing in the pipeline:

> Did the number of records I sent
> equal the number that arrived?

---

## Three names worth carrying

- **Glue code**: connective tissue that only moves data; dominates the codebase
- **Pipeline jungles**: glue accreting without redesign
- **Undeclared consumers**: someone depends on your output, you do not know they exist

Hold onto the third one.

---

<!-- _class: section -->

# Case 2
## It validated beautifully

---

## Google Flu Trends, 2008

The premise was good:

- Flu surveillance ran on a **1 to 2 week lag**
- Search queries are available immediately

See the epidemic sooner.

---

## The validation was good too

- 50M candidate queries screened to **45**
- Held-out data, excluded from every prior step
- Mean correlation **0.97** across nine regions

Stricter than most deployed ML gets today.

---

## Then

- **2012-13 season:** more than **double** the CDC figure
- Too high in **100 of 108 weeks** (Aug 2011 to Sep 2013)

Wrong, in the same direction, for two years.

---

## Cause 1: big data hubris

Search 50M terms against ~1,000 points
→ you *will* find winter.

They were already deleting terms like
*high school basketball* by hand.

> "part flu detector, part winter detector"

Missed the non-seasonal **2009 H1N1** entirely.

---

## Cause 2: algorithm dynamics

Google shipped **86 search changes** in Jun-Jul 2012

- Suggested related searches
- Surfaced diagnoses for symptom queries

Every one an improvement to *search*.
None of those engineers knew a flu model
consumed their output.

**The undeclared consumer, in-house.**

---

## The part that should bother you

100 wrong weeks out of 108, same direction.

- Visible for two years
- 3-week-old CDC data already beat it

The failure was not the model.
It was the **absence of a baseline comparison** in production.

---

<!-- _class: section -->

# Engineering data is different

---

## Units and calibration

Raw sensor voltage ≠ calibrated concentration

- Same weights, different model
- Your validation metric **will not** tell you

Surfaces when someone recalibrates.

---

## Drift

UCI Air Quality: metal-oxide sensors,
Italian roadside, **Mar 2004 to Feb 2005**, 9,358 hourly records

Documentation says so explicitly:
cross-sensitivities, **concept and sensor drift**

Train on months 1-3, random-split validate → excellent.
Next winter → worthless. The split let it see the future.

---

## Provenance

> Which data, which code, which parameters
> produced this number?

If the answer is "a notebook run out of order
on a laptop that has been reimaged,"
there is no answer.

---

<!-- _class: section -->

# Case 3
## When provenance is safety-critical

---

## MCAS

Control function commanding nose-down stabilizer trim.

- Aircraft carried **two** angle-of-attack sensors
- MCAS used **one at a time**, alternating by flight
- No cross-comparison. No voting.

One bad sensor was sufficient.

---

## Lion Air 610

Left AoA sensor biased by **~21°**

Traced to a replacement sensor
**mis-calibrated during an earlier repair**

- Undetected at the repair
- Undetected by the installation test

A measurement channel nobody had validated,
driving a flight control surface.

---

## The analysis modelled the wrong failure

Boeing's hazard assessment evaluated
erroneous data from **both** air data channels
→ "beyond extremely improbable"

But the MCAS path was exposed to a **single** failure.

Residual risk absorbed by an assumption
about crew response time.

---

## What the investigations concluded

Incorrect assumptions about flight crew response,
plus incomplete review of flight deck effects,
are what made single-sensor reliance **appear acceptable**.

JT610, Oct 2018: 189 killed.
ET302, Mar 2019: 157 killed.

---

## Three questions for any input you trust

1. Where did this measurement come from?
2. Is it independently corroborated?
3. What happens downstream when it is wrong?

If (3) is "an operator will compensate,"
that needs **evidence**, not assumption.

---

<!-- _class: section -->

# The toolchain

---

## One stack, all semester

| Concern | Tool | Prevents |
|---|---|---|
| Environments | Python + `uv` | non-deterministic rebuilds |
| Tracking | MLflow | unattributable results |
| Storage | Postgres / DuckDB / Parquet | the PHE failure mode |
| Dataframes | pandas / Polars | (Wk 3) |
| Deep learning | PyTorch | (Wk 6) |

---

## Deliberately not standardized

**LLM and agent frameworks** (Wks 9-11)

- That ecosystem turns over faster than a semester
- We teach interfaces and evaluation discipline
- Not a vendor's abstractions

---

<!-- _class: demo -->

# Demo

## `demo.ipynb`

UCI Air Quality → plot → naive split → fresh checkout

**Diagnose each break before I do.**

---

## What broke

1. Missing package version
2. Unpinned seed, different numbers
3. Absolute path that existed only on my machine

Every one of these is mundane. **That is the point.**

---

## Recap

- The model is a small component; the system is the work
- PHE: infrastructure, not modelling
- GFT: validation is not evidence
- MCAS: provenance is part of the safety case

---

## Next

**Install before L2** `git`, Python 3.11+, `uv`
**Assignment** A1 released next session
**L2** Reproducible environments, notebook → script → package

Notes: `lectures/l01/notes.md`
