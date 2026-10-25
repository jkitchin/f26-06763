# Final project: an engineering question, answered with data and a model

**Released:** Lecture 17 (2026-10-28) · **Proposal due:** Wednesday 2026-11-04 · **Presented:** 2026-11-18 and 2026-11-23 · **Teams:** 4, randomly assigned · **Points:** 100 · **Weight:** 40 % of the course grade

## Overview

Your team picks an engineering question, finds data that bears on it, builds a model that answers
it, and shows honestly how well the answer holds up. You have three weeks. The main deliverable
is a 7-minute talk followed by 3 minutes of questions, backed by a short written document and a
zip file holding your data and code.

The question is yours to choose. It can come from process, mechanical, materials, energy,
environmental, biomedical, or manufacturing engineering, or from your own research. What it
must have is a real **data component** and a real **modeling component** that fit together: the
decisions you make about the data should visibly shape the model, and the model should answer
something the raw data cannot.

A large language model (LLM) is an **optional** third component. Use one if it does a job your
project needs. A project without an LLM can earn full marks, and a project with one earns no
credit for the LLM's presence alone.

## Learning outcomes

By the end of the project you should be able to:

- turn an open engineering question into one a dataset and a model can answer in three weeks;
- acquire, clean, and validate a dataset you did not receive from a course assignment, and report what you removed and why;
- build a model, compare it against a trivial baseline on data it never saw, and defend the split;
- state the limits of your result, including at least one case where it fails;
- explain what you built, how your team built it, and what it found, to a technical audience in seven minutes.

## What the project must contain

### The data component

You acquire a real dataset, clean it, validate it, and store it in a form someone else can
query, such as Parquet files or a DuckDB database. The habits from A2 and A3 apply. Say how many
records arrived and how many survived, what was dropped and why, and which values are measured
and which you filled in. A reader should be able to reproduce the counts you report.

Course datasets (the Tennessee Eastman plant, the bioreactor) are allowed as a starting point,
but you must add either a new source of data or a question the course did not ask of them.

### The modeling component

You train a model and compare it against the free answer: persistence, the mean, a linear fit,
or whatever the trivial baseline is for your problem. The comparison must be made on data the
model never saw, with a split you can defend for your data. A shuffled split on a time series
does not count, for the reasons A4 showed. The model can be anything from the course or outside
it: a regression, a classifier, a forecaster, a neural network, a scientific ML model, a
surrogate inside a Bayesian optimization loop. Uncertainty on the predictions (Lecture 14) is
encouraged but not required.

### How the two fit together

Most of the engineering judgment the project shows is in the decisions you make
in executing it. Examples of what that looks like: a cleaning decision that
changed the model's error, and you measured how much; a feature that only exists
because of how you aligned two sources; a split chosen because of how the data
was collected; a model whose failures trace back to a gap in the data.

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

Apply one test before you commit: **if you deleted the LLM, what specific thing would your system
no longer be able to do?** "It explains the results in English" does not pass unless the
explanation is checked against something.

An LLM used as a coding assistant is not this component. That use is covered by the course's
generative-AI policy below, and it does not belong on your architecture slide.

## Teams

Teams of four are assigned at random and posted before Lecture 17. When enrollment is not a
multiple of four, the extra students join teams of five. Use the end of Lecture 17 to meet.

By **Friday 2026-10-30**, submit a short **team agreement** on Canvas, one paragraph is enough:
how you will communicate, when you will meet, and who leads which part. Each part needs a lead,
but everyone should be able to explain every part.

**Research data is welcome.** If a team member brings data from their own research, two rules
apply. First, the member needs permission from their advisor to share the data with the course
staff, because it goes in the zip file. Second, the project must stay a team project: the
proposal names a different lead for each part, and the data owner does not lead all of them.

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

Slides are due before the first presentation so that teams on day 2 do not get five extra days.
The document is due after both days so every team can answer what it was asked in questions.

The two biggest risks in a three-week project are a dataset that turns out to be unusable and a
team that starts building in week two. Both are why the proposal asks for data you have
already opened.

## The proposal

One page, submitted on Canvas by one member, with every member's name on it. It is graded
complete or incomplete, and its purpose is to get you useful feedback while there is still time
to act on it.

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

The middle section is about process, not a list of who did what. Good material for it: the plan
in your proposal against what you actually did, a dead end and how you noticed it, how the data
and model halves of the team handed work to each other, and what you would do differently with
another three weeks.

Expect one question to be "show us a case where it fails." Teams that went looking for one will
have an easy answer.

Everyone on the team should be able to answer questions about any part of the project. Not
everyone has to speak during the talk.

## Feedback on other teams' presentations

Each presentation day has its own participation assignment on Canvas, **Presentation feedback,
day 1** and **Presentation feedback, day 2**, because the order of talks is not known in advance.
On each day, give feedback on every team that presents except your own. Each assignment is due
at 11:59 pm on its presentation day, and it counts toward participation.

For each team, record the **team number** and the **project title**, then answer three questions
in two or three sentences each:

1. **What question is this project answering, and why would an engineer care about the answer?**
   Put it in your own words. If you cannot, say what was missing from the talk.
2. **What was the main result, and what was it compared against?** Give the number if the team
   showed one, and say whether you found it convincing, and why.
3. **What is the weakest point in the project, and what would you check next to test it?** Name
   something specific: a choice in the data, the split, the model, or a claim the results do not
   yet support.

Take notes during the talks; ten projects run together by the evening. The feedback goes to the
instructors only and is not shared with the teams, so be candid. It is graded complete or incomplete, and an answer that
could apply to any project ("great talk, clear slides") does not count as complete.

## The written document

Three to four pages, as a PDF, covering what the talk cannot fit: the question, the data, the
model, how they fit together, the LLM if used, the results, and the limitations. Include the numbers
behind every claim you make in the talk, and the figures you showed.

End with a **contributions** paragraph saying who led and who worked on each part. It does not
count toward the page limit.

## The zip file

One member uploads a single zip file to Canvas. It must let a grader check your numbers without
contacting you and without an API key. It contains:

- `README.md` with the exact commands to set up the environment and regenerate your results;
- `pyproject.toml` and `uv.lock`, so the environment is reproducible with `uv`;
- your code, plus one notebook or script that regenerates the numbers and figures in your talk;
- `data/raw/` with the data as you received it, and `data/clean/` with the data your model was trained on;
- if you used an LLM: `llm/calls.jsonl` with every call behind a reported number (prompt, provider, exact model version, date, and raw response), and the hand-labelled cases you checked it against.

Keep the zip under 500 MB. If your raw data is larger, include a download script and a
`SHA256SUMS` file for the raw files instead of the files themselves, the way the course
distributes its own data.

**No secrets.** Do not include `.env` files, API keys, or tokens. A zip file containing a key loses
points under Reproducibility, and you should revoke the key at once.

## LLM access

If you use an LLM, you may use Gemini through your CMU account or any provider you pay for
yourself. Two practical points:

- **Calling an LLM from code needs an API key.** Chat subscriptions often do not include API
  access, which is usually set up and billed separately. Find out how you will get a key before
  the proposal.
- **Read your provider's data terms before sending it research data.** Some free tiers may use
  what you send them to improve their products. Unpublished or confidential data should not go
  there.

Report the provider, the exact model version, and the date of your runs, because an LLM result
without those cannot be reproduced.

## Grading

The project is scored out of 100.

| Part                         | Points | What we look for                                                                                                                                                                            |
|------------------------------|--------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Data**                     | 25     | A real dataset acquired by the team; cleaning and validation with the losses counted and justified; measured and filled values kept apart; counts a reader can reproduce                    |
| **Model**                    | 25     | A model compared against a trivial baseline on held-out data; a split appropriate to the data; results reported with enough detail to reproduce                                             |
| **Integration and judgment** | 15     | Data decisions that visibly shape the model; an honest failure case; limits stated plainly; if an LLM is used, a specific job that passes the deletion test, checked against labelled cases |
| **Presentation**             | 20     | What the project is, how the team went about it, and the results, in 7 minutes; clear figures; answers in questions that show the whole team understands the whole project                  |
| **Written document**         | 10     | The numbers behind every claim in the talk; clear writing; a contributions paragraph                                                                                                        |
| **Reproducibility**          | 5      | The zip regenerates the reported numbers from its README; no secrets                                                                                                                        |

Every member receives the team's score, which may be adjusted for an individual's contribution
based on the contributions paragraph. The proposal, team agreement,
and status check are required, and a missing one costs 5 points from the team score.

Over-claiming costs more than a modest result measured well. A model that beats the baseline by
a small margin, with an honest account of why it is not larger, is a good project.

Projects are group work, and the course's automatic grace days do not apply.

## Starting points

These are to get a team thinking. They are not a list to choose from, and your own idea is
welcome.

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
asks for. Say in the document where you used AI assistants. Every member must be able to explain
the code they wrote and the team's results, and questions in the presentation are where that
gets tested.
