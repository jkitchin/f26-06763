# Final project: an engineering question, answered with data and a model

**Released:** Lecture 17 (2026-10-28) · **Proposal due:** Wednesday 2026-11-04 · **Presented:** 2026-11-18 and 2026-11-23 · **Teams:** 4, randomly assigned · **Points:** 100 · **Weight:** 40% of the course grade

## Overview

Your team picks an engineering question, finds data that bears on it, and builds a model that
answers it. You then show how well the answer holds up. You have three weeks.

**Deliverables:**

- A **7-minute talk**, followed by 3 minutes of questions: the main deliverable.
- A short **written document**.
- A **zip file** with your data and code.

**The question is your choice.** It can come from process, mechanical, materials, energy,
environmental, biomedical, or manufacturing engineering, or from your own research.

**Components:**

- **Data component (required):** a real dataset you acquire, clean and validate.
- **Modeling component (required):** a model that answers something the raw data cannot.
- **The two must fit together:** your decisions about the data should visibly shape the model.
- **LLM component (optional):** a large language model (LLM), if it does a job your project
  needs. A project without an LLM can earn full marks. A project with one earns no credit for
  the LLM's presence alone.

## Learning outcomes

By the end of the project you should be able to:

- Turn an open engineering question into one a dataset and a model can answer in three weeks.
- Acquire, clean, and validate a dataset you did not receive from a course assignment, and report what you removed and why.
- Build a model, compare it against a trivial baseline on data it never saw, and defend the split.
- State the limits of your result, including at least one case where it fails.
- Explain what you built, how your team built it, and what it found, to a technical audience in seven minutes.

## What the project must contain

### The data component

Acquire a real dataset, clean it, validate it, and store it in a form someone else can query,
such as Parquet files or a DuckDB database. The habits from A2 and A3 apply. Report:

- How many records arrived, and how many survived.
- What was dropped, and why.
- Which values are measured, and which you filled in.

A reader should be able to reproduce every count you report.

**Course datasets** (the Tennessee Eastman plant, the bioreactor) are allowed as a starting
point. You must add either a new source of data or a question the course did not ask of them.

### The modeling component

Train a model and compare it against the trivial baseline for your problem: persistence, the
mean, a linear fit, or whatever the simplest answer is.

- **Held-out data:** make the comparison on data the model never saw.
- **The split:** choose one you can defend for your data. A shuffled split on a time series does
  not count, for the reasons A4 showed.
- **The model:** anything from the course or outside it: a regression, a classifier, a
  forecaster, a neural network, a scientific ML model, a surrogate inside a Bayesian
  optimization loop.
- **Uncertainty** on the predictions (Lecture 14) is encouraged but not required.

### How the two fit together

The engineering judgment in a project shows in the decisions you make along the way. For
example:

- A cleaning decision that changed the model's error, and you measured by how much.
- A feature that only exists because of how you aligned two sources.
- A split chosen because of how the data was collected.
- A model whose failures trace back to a gap in the data.

### The optional LLM component

If you use an LLM inside your system, it must do a specific job, and you must check how well it
does it. Three patterns cover most good uses:

- **Upstream, as a source of data.** The LLM extracts structured records from text such as
  papers, reports, datasheets, or logs, and your model is trained on the result. Check the
  extraction against a hand-labelled sample, and ask how its errors propagate into the model.
- **Downstream, as an interface.** Your model becomes a tool that an LLM calls, for example to
  turn a plain-language request into a query, a prediction, or an optimization. Check that the
  calls are correct and that the system refuses requests outside the model's valid range.
- **Alongside, for context.** Your model flags something, and the LLM retrieves documents that
  explain it, with citations. Check that the citations say what the answer claims.

**The deletion test.** Before you commit, ask: if you deleted the LLM, what specific thing would
your system no longer be able to do? "It explains the results in English" does not pass unless
the explanation is checked against something.

**A coding assistant is not this component.** That use falls under the course's generative-AI
policy (see AI use, below), and it does not belong on your architecture slide.

## Teams

- **Assignment:** teams of four, assigned at random and posted before Lecture 17. When enrollment
  is not a multiple of four, the extra students join teams of five.
- **First meeting:** at the end of Lecture 17.
- **Team agreement:** due **Friday 2026-10-30** on Canvas. One paragraph is enough: how you will
  communicate, when you will meet, and who leads which part.
- **Leads:** each part needs a lead, and everyone should be able to explain every part.

**Research data is welcome.** If a team member brings data from their own research:

1. The member needs permission from their advisor to share the data with the course staff,
   because it goes in the zip file.
2. The project stays a team project. The proposal names a different lead for each part, and the
   data owner does not lead all of them.

## Timeline

| Date                     | Milestone                                                                                  |
|--------------------------|--------------------------------------------------------------------------------------------|
| Wed 2026-10-28 (L17)     | Project released, teams posted, first team meeting in class                                |
| Fri 2026-10-30           | Team agreement due on Canvas                                                               |
| Wed 2026-11-04 (L19)     | **Proposal due**, one page, using the form below                                           |
| Fri 2026-11-06           | Proposal feedback returned: approved, or approved with changes                             |
| Wed 2026-11-11           | **Status check** posted on Canvas: data done, baseline number, model number, open problems |
| Tue 2026-11-17, 11:59 pm | **Slides due for every team**, whichever day you present                                   |
| Wed 2026-11-18           | Presentations, day 1; **day-1 feedback due at 11:59 pm**                                   |
| Mon 2026-11-23           | Presentations, day 2; **day-2 feedback due at 11:59 pm**                                   |
| Mon 2026-11-23, 11:59 pm | **Written document and zip file due** for every team                                       |

- **Slides** are due before the first presentation, so teams on day 2 do not get five extra days.
- **The document** is due at the end of day 2, so every team can address the questions it was
  asked.
- **The two biggest risks** in a three-week project are a dataset that turns out to be unusable
  and a team that starts building in week two. This is why the proposal asks for data you have
  already opened.

## The proposal

One page, submitted on Canvas by one member, with every member's name on it.

- **Grading:** complete or incomplete.
- **Purpose:** to get you useful feedback while there is still time to act on it.

```
Title:
Team members, and the lead for each part:

1. The question
   What engineering question are you answering, and who would use the answer?

2. The data
   Where it comes from, its license or permission, and its size.
   Proof you have it: the number of rows (or files) you loaded, and one thing
   you have already found wrong with it.

3. The model
   What you will predict or decide, the model you plan to try first,
   and the trivial baseline it has to beat. How you will split the data.

4. LLM (optional)
   The job the LLM does, and what your system would lose without it.
   How you will check it (for example: 30 hand-labelled cases).

5. Risk
   The thing most likely to go wrong, and your fallback if it does.
```

## The presentation

Each team has a 10-minute slot: 7 minutes of talk with a hard stop, then 3 minutes of questions.
The talk covers three things, in this order:

| Minutes | Content                                                                                                                                              |
|---------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| 2       | **What the project is.** The question, why an engineer would care about the answer, and the data and model you used to answer it                     |
| 2       | **How you went about it as a team.** How you split the work, the decisions that shaped the project, and what you changed when something did not work |
| 3       | **The results.** Your model against the baseline on held-out data, what the data did to the result, one case where it fails, and what that tells you |

**The middle section is about process.** A list of who did what does not cover it. Good material:

- The plan in your proposal against what you actually did.
- A dead end, and how you noticed it.
- How the data and model halves of the team handed work to each other.
- What you would do differently with another three weeks.

**Questions:**

- Expect one question to be "show us a case where it fails." Look for one before the talk.
- Everyone on the team should be able to answer questions about any part of the project. Not
  everyone has to speak during the talk.

## Feedback on other teams' presentations

Each presentation day has its own participation assignment on Canvas: **Presentation feedback,
day 1** and **Presentation feedback, day 2**. There are two because the order of talks is not
known in advance.

- **Who:** every team that presents that day, except your own.
- **Due:** 11:59 pm on that presentation day.
- **Counts toward:** participation.

For each team, record the **team number** and the **project title**, then answer three questions
in two or three sentences each:

1. **What question is this project answering, and why would an engineer care about the answer?**
   Put it in your own words. If you cannot, say what was missing from the talk.
2. **What was the main result, and what was it compared against?** Give the number if the team
   showed one, and say whether you found it convincing, and why.
3. **What is the weakest point in the project, and what would you check next to test it?** Name
   something specific: a choice in the data, the split, the model, or a claim the results do not
   yet support.

- **Take notes during the talks.** Several projects in one session are hard to tell apart by the
  evening.
- **Who reads it:** the instructors only. It is not shared with the teams, so say what you
  think.
- **Grading:** complete or incomplete. An answer that could apply to any project ("great talk,
  clear slides") does not count as complete.

## The written document

Three to four pages, as a PDF. It covers what the talk cannot fit:

- The question, the data, and the model.
- How the data and model fit together.
- The LLM, if used.
- The results and the limitations.
- The numbers behind every claim you make in the talk, and the figures you showed.

**Systems and toolchains section** (about half a page). Explain how the project demonstrates what
you learned in this course:

- Name the specific tools and practices you used, for example a reproducible `uv` environment,
  version control, a database or Parquet store, data validation, a defensible split, experiment
  tracking, uncertainty, an LLM.
- Say where in the project each one did real work.
- Give at least one place where a practice from the course changed a result or caught a mistake.

A list of tools with no account of what they did does not meet this.

**Contributions paragraph.** End with who led and who worked on each part. It does not count
toward the page limit.

## The zip file

One member uploads a single zip file to Canvas. It must let a grader check your numbers without
contacting you and without an API key. It contains:

- `README.md` with the exact commands to set up the environment and regenerate your results.
- `pyproject.toml` and `uv.lock`, so the environment is reproducible with `uv`.
- Your code, plus one notebook or script that regenerates the numbers and figures in your talk.
- `data/raw/` with the data as you received it, and `data/clean/` with the data your model was trained on.
- If you used an LLM: `llm/calls.jsonl` with every call behind a reported number (prompt, provider, exact model version, date, and raw response), and the hand-labelled cases you checked it against.

**Size:** keep the zip under 500 MB. If your raw data is larger, include a download script and a
`SHA256SUMS` file for the raw files instead of the files themselves, the way the course
distributes its own data.

**No secrets.** Do not include `.env` files, API keys, or tokens. A zip file containing a key loses
points under Reproducibility, and you should revoke the key at once.

## LLM access

If you use an LLM, you may use Gemini through your CMU account or any provider you pay for
yourself.

- **Calling an LLM from code needs an API key.** Chat subscriptions often do not include API
  access, which is usually set up and billed separately. Find out how you will get a key before
  the proposal.
- **Read your provider's data terms before sending it research data.** Some free tiers may use
  what you send them to improve their products. Unpublished or confidential data should not go
  there.
- **Report the provider, the exact model version, and the date of your runs.** An LLM result
  without those cannot be reproduced.

## Grading

The project is scored out of 100.

| Part                         | Points | What we look for                                                                                                                                                                            |
|------------------------------|--------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Data**                     | 25     | A real dataset acquired by the team; cleaning and validation with the losses counted and justified; measured and filled values kept apart; counts a reader can reproduce                    |
| **Model**                    | 25     | A model compared against a trivial baseline on held-out data; a split appropriate to the data; results reported with enough detail to reproduce                                             |
| **Integration and judgment** | 15     | Data decisions that visibly shape the model; a failure case shown and explained; limits stated plainly; if an LLM is used, a specific job that passes the deletion test, checked against labelled cases |
| **Presentation**             | 20     | What the project is, how the team went about it, and the results, in 7 minutes; clear figures; answers in questions that show the whole team understands the whole project                  |
| **Written document**         | 10     | The numbers behind every claim in the talk; a systems and toolchains section tied to real work in the project; clear writing; a contributions paragraph                                    |
| **Reproducibility**          | 5      | The zip regenerates the reported numbers from its README; no secrets                                                                                                                        |

- **Team score:** every member receives the team's score, which may be adjusted for an
  individual's contribution based on the contributions paragraph.
- **Required pieces:** the proposal, team agreement, and status check. A missing one costs 5
  points from the team score.
- **Claims:** a model that beats the baseline by a small margin, with a clear account of why the
  margin is not larger, is a good project. Claiming more than the results show costs more than a
  modest result measured well.
- **Late work:** projects are group work, and the course's automatic grace days do not apply.

## Starting points

These are to get a team thinking. Your own idea is welcome; you do not have to pick from this
list.

- **From the literature to a model.** Extract reported property or performance values from a set
  of open-access papers, check a sample by hand, and fit a model to them. Then ask whether the
  model's conclusions survive correcting the extraction errors.
- **An operator assistant for the Tennessee Eastman plant.** Start from a miniproject detector,
  and add a component that suggests which known fault an alarm most resembles, scored against the
  fault labels.
- **A design question over a surrogate.** Build a surrogate for a simulation or a set of
  experiments, and use Bayesian optimization to answer a design question under a fixed budget of
  evaluations, compared against random search on the same budget.
- **Public sensor data.** Air quality, weather, building energy, or river gauges: data with real
  gaps and real drift, and a forecasting or detection question someone would pay to have
  answered.
- **Your research.** Data from a member's lab, with a question the lab actually has.

## AI use

Generative AI is allowed and encouraged as an engineering tool, with the disclosure the syllabus
asks for.

- Say in the document where you used AI assistants.
- Every member must be able to explain the code they wrote and the team's results. The questions
  after the presentation test this.
