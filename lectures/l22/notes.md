# Lecture 22: Course overview and how this course was built

:::{admonition} At a glance
:class: tip

- **Session** Lecture 22, Week 12
- **Arc** Course wrap-up
- **Slides** <a href="../../slides/l22/">Deck for this session</a>
- **Demo** [`l22-git-history.ipynb`](l22-git-history.ipynb), which reads the history of any git
  repository; run it on your own final-project repository. Every number below about this course's
  history comes from [`figures/make_figures.py`](figures/make_figures.py), which reads this
  repository's git log up to 2026-11-04
- **Practice** No practice module for this session. Every earlier module stays open on the
  <a href="../../game/#/map">course map</a>
- **Assignment** None
:::

## Why this matters

In twelve weeks this course went from a Python environment to language-model agents. On the way
you met relational and columnar databases, dataframes and streams, forecasting, regression and
classification, neural networks in PyTorch and JAX, physics-informed models, uncertainty, Bayesian
optimization, generative models, language models, retrieval and agents, and, if you came to the
optional sessions, reinforcement learning and deployment. That is far more ground than anyone
masters in a semester. It was not meant to be mastered. It was meant to be met, carefully enough
that you can return to any part of it and know where to start.

That breadth is also what your working life will look like. The tools in this course will change.
Several changed while it was being written: a publishing tool released a major version that would
have silently broken this site, scikit-learn changed how one cross-validation splitter assigns
folds between two minor releases, and the AI assistant used to build the course changed model
generation more than once along the way. You will change fields too. A chemical engineer moves
into batteries, a mechanical engineer into medical devices, a data scientist into a plant they have
never seen. Each move means learning a new vocabulary, new data, new failure modes and new tools,
quickly, and usually without a course to teach them.

This lecture does two things about that. It first looks back over the course as a whole, so the
pieces sit in one picture with the ideas that connect them. Then it shows how the course itself was
built. Two instructors produced 21 sets of notes, 21 slide decks, their notebooks and figures, a
practice game, an in-class clicker and a course map in about fifteen weeks, working with an AI
coding assistant and steering it the whole way. The repository's history records all of it,
including the parts that went wrong. That record is a worked example of learning a broad body of
material fast, and of the checks that keep fast work from becoming confidently wrong work. You
will need the same method the next time a technology or a field is new to you.

## Learning objectives

By the end of this session you should be able to:

- Describe the course's arcs and the ideas that recur across them, and name the lecture to go
  back to for each.
- Reconstruct how a project was built from its git history: when the work happened, where it
  changed course, and which rules were written after a mistake.
- Explain how this course was built with an AI coding assistant: what the instructors decided,
  what the assistant did, and which checks caught its errors.
- Plan how to learn an unfamiliar technical area quickly with an AI assistant while still
  learning it yourself.

## The course in one picture

The deck for this session opens with the course map from Lecture 18, now with the fog lifted. The
trail runs through three regions, and each region answers one question about building an AI system
for engineering data.

### Three arcs

The first arc, **the data lowlands** of Lectures 1 to 7, asks where the data lives and how it gets
to a model in a state you can trust. [Lecture 1](../l01/notes.md) set out the system view of
machine learning, in which the model is a small box inside a much larger system, and the toolchain
the course used throughout. [Lecture 2](../l02/notes.md) made environments and experiments
reproducible with `uv` lockfiles, Git and run logging. [Lecture 3](../l03/notes.md) and
[Lecture 4](../l04/notes.md) stored sensor time series in PostgreSQL and then in Parquet and DuckDB,
and showed why a row store and a column store suit different questions.
[Lecture 5](../l05/notes.md) built batch pipelines over the Tennessee Eastman plant that are safe to
rerun, [Lecture 6](../l06/notes.md) dealt with streams, late data and validation gates that fail
loudly, and [Lecture 7](../l07/notes.md) turned raw signals into features that exist at the moment
a prediction is made.

The second arc, **the machine-learning highlands** of Lectures 8 to 16, asks how to fit a model and
how to know whether to believe it. Lectures [8](../l08/notes.md), [9](../l09/notes.md) and
[10](../l10/notes.md) were the machine-learning workflow three times over, for time series,
regression and classification: honest baselines, splits that respect time and groups,
cross-validation, hyperparameter search and experiment tracking. [Lecture 11](../l11/notes.md)
opened the box with tensors, automatic differentiation and a training loop written by hand, and
[Lecture 12](../l12/notes.md) matched architectures to the structure of engineering data.
[Lecture 13](../l13/notes.md) put physics back in, with physics-informed networks and neural ODEs
and DAEs. [Lecture 14](../l14/notes.md) asked how wrong a prediction might be,
[Lecture 15](../l15/notes.md) used that uncertainty to choose the next experiment, and
[Lecture 16](../l16/notes.md) learned whole distributions and sampled from them.

The third arc, **the language coast** of Lectures 17 to 19, asks what changes when the model reads
and writes text. [Lecture 17](../l17/notes.md) trained a tiny GPT to show what a language model is,
[Lecture 18](../l18/notes.md) controlled what the model gets to see through tools, search and
retrieval, and [Lecture 19](../l19/notes.md) put the model in a loop with tools as an agent, inside
a harness of checks. The two optional sessions on the AIChE dates went sideways from the trail:
reinforcement learning, which learns to act from rewards rather than from labelled answers, and
deployment, which serves a model to callers and measures what that costs.

### The ideas that ran through every arc

```{index} pair: failure mode; plausible output
```

A list of topics is the least useful way to remember a course. A handful of ideas kept returning
in different clothes, and they are what transfers to the next field.

**Make the result reproducible.** Lecture 1's demo notebook breaks on purpose, in three documented
ways, and Lecture 2 fixed the environment with a lockfile. The same idea returned in the optional
Lecture 21, where a container image is built from that lockfile so the running service is the
thing that was tested. A result you cannot rebuild is a result you cannot check, and nobody else can
check it either.

**Split the data the way the model will meet the world.** Lecture 7 built only features that exist
at prediction time. Lecture 8 split time series in time order. Lecture 9 grouped rows that belong
together, and Lecture 12 split the turbofan data by engine so no engine appeared on both sides. The
case studies from other fields repeat the lesson with different units: MIT-BIH heartbeats split by
patient, bearing faults split by bearing, chest X-rays from a hospital the model never saw. The
leak is always the same: information from the test set reaches training through a shared unit.

**Measure rather than assume.** The model in Lecture 11 ran two and a half times slower on the GPU
than on the CPU, because it was too small for the accelerator to pay for itself. In the optional
Lecture 21 an `async def` endpoint, which sounds faster, stalled the whole server. In both cases the
expectation came from a reasonable-sounding rule and the measurement came from how the
implementation actually works. Three more measurements changed a lecture the same way:

| We expected | We measured | Where |
|---|---|---|
| PyTorch and JAX both match the exact gradient | PyTorch was off by 7.5e-8 and JAX by 4.4e-16, because two Python numbers had silently become float32 | [Lecture 11](../l11/notes.md) |
| The same model ranking under any split | on the concrete strength data, a decision tree beats a straight line with random folds, and loses to it by 2 MPa when rows are grouped by mix | [Lecture 9](../l09/notes.md) |
| Our tiny GPT finishes all 16 course terms | 15 of 16: "physics-in" became "physics-into a s", because "into a" appears 58 times in the notes and "physics-informed" only 8 | [Lecture 17](../l17/notes.md) |

**Say how wrong you might be.** Lecture 14 attached intervals to predictions and checked whether
they covered as often as they claimed. Lecture 15 used those intervals to decide where to measure
next. An engineering decision made on a point prediction alone has thrown away the part of the
answer that tells you how much to trust it.

**The model is a small part of the system.** Lecture 1 drew the model as a small box among data
collection, validation, serving and monitoring. Lecture 6 built a validation gate, Lecture 18 built
the context around a language model, Lecture 19 built the harness around an agent, and the optional
Lecture 21 built the service around a regression model. Most of the engineering, and most of the
failures, were in the surrounding boxes.

**Plausible output is the failure to fear.** Across the course the dangerous results were the ones
that looked fine. In Lecture 11 Adam trained on unscaled inputs settled at a worse error instead of
failing, so the bug looked like an ordinary result. A leaky split gave a high score rather than an
error. A language model gave a fluent answer that was not in its sources. In each case the only
defence was knowing roughly what the right number should be before computing it.

## How this course was built

```{index} Git, git log, commit trailer, pull request, Claude Code
```

The rest of this lecture is about the course itself, read from its repository. Every change to the
course, from the first conventions file to this set of notes, is a commit in Git, and every commit
records a date, an author and a message. Most commits also carry a trailer line naming the model
that co-wrote them, in the form `Co-Authored-By: Claude Opus 5.5`. A trailer is a `Key: value` line
at the end of a commit message that tools can read back. Reading those lines with `git log` turns
the history into data, and the script behind this section does nothing more than that, with a fixed
cutoff of 2026-11-04 so that the numbers do not move as commits land after the lecture.

:::{admonition} Definition: commit trailer
:class: tip
A **commit trailer** is a `Key: value` line at the end of a Git commit message, such as
`Co-Authored-By:`, that tools can parse to say who or what contributed to the commit.
:::

[Lecture 19](../l19/notes.md) already showed the pipeline that one change takes to this site: an
instructor writes the specification, the coding agent Claude Code reads the conventions and writes
the material, a pull request carries the change, automatic checks run on it, and an instructor reads
it and merges it.

```{figure} ../l19/figures/course-build.png
:alt: How one change reaches this course's site. Top row, left to right: an instructor writes the spec, topics, data and examples; Claude Code reads CLAUDE.md, the rules, and writes notes, slides, figures, notebook and practice questions; a pull request, a branch with the change; automatic checks, a strict build, the index, quiz quotes that must match the notes, figures that must exist, and no instructor file published. Bottom row, right to left: an instructor reads it, asks for fixes and merges; a weekly release, a bot that opens the release of the next lecture; the public site with notes, slides, notebooks, the practice game and the map. A red arrow from the checks back to Claude Code says a check fails, fix it; a green arrow from the instructor back to Claude Code says changes requested.
:width: 100%

How one change reaches this site, the figure from Lecture 19.
```

Three guardrails sit along that path. The agent's permissions set what it may do without asking
us. The build fails on any warning, and other checks confirm that every practice question still
matches the notes, that no instructor-only file is published, and that the live site serves the
new version. And nothing reaches the site until one of us merges it. The pipeline is a harness for
the whole course, in the sense of Lecture 19, and the model is one box in it. The rest of this
section is the history of that pipeline in use: how much went through it, when, and what changed
along the way.

### The record

Up to the cutoff the repository holds 354 commits, not counting merges, between 2026-07-20 and
2026-11-04. They arrived through 133 pull requests, each a branch of related commits that an
instructor reviewed and merged into the main branch. Of the 354 commits, 196 were made by one
instructor and 144 by the other, and 13 by cloud sessions of the assistant working on branches of
their own, which an instructor then reviewed. 305 of them, 86%, carry a trailer crediting a Claude model.

```{figure} ../l19/figures/course-history.png
:alt: Every pull request merged into the course's repository from July to November 2026, drawn as arcs off a horizontal line labeled main. Each arc runs from the branch's first commit to the day it merged; taller arcs carry more commits. Arcs above the line are lectures, in blue, and course pages, in gray. Arcs below are the practice game and map, in green, the clicker, arcade and Ask button, in gold, and the build, checks and rules, in purple. Labels mark the first lecture, the weekly release gate, the course map, the clicker, the first weekly release, the arcade, the RAG chat and the Ask button.
:width: 100%

Every pull request as a branch off main, from its first commit to the day it merged; taller arcs
carry more commits. Above the line are the lectures and course pages, below it the practice game,
the clicker and the checks that guard them. Drawn from the repository's history by
`lectures/l19/figures/make_figures.py`.
```

The trailers name four versions. Claude Opus 4.8 appears from the first day, Claude Opus 5 from
2026-07-27 to 2026-09-22, Claude Sonnet 5 on five commits in late July and August, and Claude Opus
5.5 from 2026-09-23 onwards. The collaborator changed model generation twice while the course was
being written, which is the problem Lecture 2 taught you to pin against, arriving in the tool that
writes the code rather than in a library the code imports.

```{figure} figures/commits.png
:alt: Bar chart of commits per week from July to November 2026, each bar split by the model named in the commits' co-author lines. Early bars are mostly Claude Opus 4.8 in gold and Claude Opus 5 in blue, with a peak of 58 commits in the first week of August. A dashed line marks the first class on 2026-08-24. A week of about 50 commits follows it, half of them with no Claude trailer. From late September the bars are Claude Opus 5.5 in red, between 8 and 25 commits a week.
:width: 100%

Commits per week, split by the model named in each commit's co-author line, from
`figures/make_figures.py`. A gray segment is a commit with no Claude trailer, mostly hand edits to
the syllabus, the schedule and the notes. 124 of the 354 commits came before the first class.
```

### Before the semester: drafting the whole course

The first commit, on 2026-07-20, added the course package: the syllabus, the schedule, and one
specification file per week under `course/modules/`, written by the instructors. Each specification
names the objectives, the topics, the dataset and the demo for each lecture. Within two weeks there
were drafts for most of the course, one pull request per lecture, generated against those
specifications. 124 commits came before the first class on 2026-08-24.

Those first drafts were not good enough, and the history shows the standard rising after them. The
first set of notes for Lecture 1 was rewritten on the same day to ground it in verified case studies,
and a separate commit removed an unsupported statistic from the specification itself (the "less than
10% of the code is the model" claim, which [Lecture 1](../l01/notes.md) now uses as its first example
of checking a claim against its source). When Lecture 3 was written it set a depth that the first
two had not met, and Lecture 2 was rewritten to match. On 2026-08-07 a writing style guide arrived
with rules for plain, direct prose. Between 2026-08-08 and 2026-08-17 the notes were audited against
it and every slide deck was restyled to topic titles and green definition boxes. A pull
request for Lecture 11 was closed unmerged on 2026-07-27 and redone, because it had been branched off
another unmerged lecture and its diff carried that lecture's work too.

The plan was also more ambitious than the course that was taught. The specification of 2026-07-20
called for 26 lectures, two class days for the miniproject, a capstone studio, and twelve
assignments: A1 to A11, one per module, and the miniproject. By November the schedule held 22
lectures, two of them optional, and five assignments had been released alongside the miniproject
and the final project. MLOps moved to an optional page, the evaluation lecture went to an archive,
and A6, A8, A9 and A10 are written and on hold. Each cut was a decision to put the effort into the
lectures rather than spread it across more graded work, and each is recorded in the commit that
made it.

### The tools built for you

Most of what the course gave you beyond notes and slides was built in the five weeks around the
start of the semester, and most of it exists because the instructors saw a gap and asked for
something to fill it.

```{figure} figures/milestones.png
:alt: A timeline from mid July to early November 2026, with the period before the first class shaded. Red dots mark the first commit of each piece of course infrastructure, labelled with its date: conventions file July 20; writing style guide and practice game August 7; course map August 8; Open in Colab buttons August 23; clicker August 25; one lecture released at a time August 27; arcade minigames August 29; interactive figures with L12 September 27; narrated slides with L20 October 12; Ask button October 28; case studies from other fields November 1; agent skill for the course November 2.
:width: 100%

When each piece of course infrastructure first appeared, dated by the first commit that added its
file. The lectures themselves are not on this timeline; it shows what was built around them.
```

The **practice game** arrived on 2026-08-07: a seeded selection of questions per lecture, each one
quoting the section of the notes it tests, with a check in continuous integration that fails if a
quoted passage no longer appears in the notes. The **course map** followed the next day, built from
the cross-references between lectures. On 2026-08-23 every demo notebook gained an Open in Colab
button, so a notebook could run without a local install.

The **clicker** is the clearest example of building something new and checking it by measurement.
The course had no way to take the room's pulse in the middle of a lecture. The first design tried to
use GitHub to count votes anonymously, since that would have avoided running a new service. The
commit that added the clicker on 2026-08-25 records why that failed: the only anonymous counter
GitHub exposes is the download count of a release asset, and a measurement showed it reporting an
unchanged count for about fourteen minutes while it was visibly gaining downloads. So the clicker
runs on a small Cloudflare Worker that stores each vote and knows nothing about questions or
lectures, because the questions live on the slides. The same commit rejects Cloudflare's key-value
store for its eventual consistency, which could delay a vote by up to a minute and would have
reproduced the GitHub failure. An opt-in leaderboard followed on 2026-08-26, and on 2026-09-12 the
explanation behind each answer began to show for every room, not only the rooms that got it right.

The **arcade**, on 2026-08-29, filled a gap between the clicker and the practice game: one-minute
games over the same question banks, so there is still one place where a claim about the course is
written down and one check that the claim matches the notes. On 2026-08-27 the release process
changed from one week at a time to one lecture at a time, each released as its own pull request and
in lecture order, because a lecture's notes cross-reference the ones before it and cannot go public
first.

### Adapting during the semester

During the semester the work changed character. The commits per week fell, from a peak of 58 in
August to between 8 and 25 a week from late September, and most of them changed something that
already existed in response to how it was going.

The slides changed most. The first decks were sparse: the Lecture 1 deck has 3 figures and the
Lecture 2 deck has 1, and neither has an interactive element. From Lecture 9, diagrams were drawn
directly in the slides, and Lecture 9's deck carries 27 figures. Lecture 12, on 2026-09-27,
introduced interactive figures that run in the browser, with sliders and play buttons over the
lecture's own data, and most decks after it carry several. The links to sources rose too, from 6 to
17 in the first eight decks to between 24 and 65 in the last eight. The optional Lecture 20 added a
spoken narration for every slide, read aloud in the browser, so that the deck can be followed without a speaker.

```{figure} figures/decks.png
:alt: Five rows of bars, one bar per lecture from L1 to L21. Image figures are small for L1 to L8, then 27 for L9, 37 for L13 and 22 for L15. Diagrams drawn in the slide appear only in L9, L10, L13, L14, L18 and L19. Interactive figures are absent before L12, then 15 for L12 and between 3 and 9 for most later decks. Clicker questions peak at 6 for L3 and appear in about half the decks. Links to sources rise from under 20 in the early decks to 59 for L14, 62 for L19 and 65 for L21.
:width: 100%

What each slide deck contains, counted from the deck files by `figures/make_figures.py`. The
interactive figures start with L12 and stay. The clicker questions do not follow the same trend:
they peak at L3, the first deck written after the clicker existed, and later decks use them where a
question fits.
```

The slides also grew their own presenter tools as they were needed in the room. The clicker runs
inside a slide, with its timer, live bars, reveal and leaderboard (2026-08-25). The interactive
figures carry a still image for previews that do not run scripts (2026-09-27). The narration in
Lecture 20 shows its spoken script beside the speaker notes in presenter view (2026-10-12). From
Lecture 16 on 2026-10-21, a deck can set `presenter: true` to get drawing tools on the live slide, a
pen, a highlighter, a laser pointer and a spotlight, and Lecture 18 put the course's Ask search
inside a slide (2026-11-01). Every deck is still one plain MARP text file, checked like the notes.

The count corrects the story that was planned for this lecture, which was that the decks became
steadily more interactive. Interactive figures did arrive and stay. Clicker questions did not: the
largest number is in Lecture 3, and about half the decks have none, because a clicker question works
only when the slide before it states the fact the question needs. The measurement replaced the
expectation, which is the move this course has made in every lecture.

The schedule for publishing changed as well. The plan was to publish each lecture a week before
its class. Lecture 3, the first released under the one-lecture process, went public four days
ahead. By October the margin was a day or two, and Lecture 19 was released at 12:34 on the day it
was taught. Of the 17 lectures released since release gating began on 2026-08-20, seven went public
on the day of their class.

```{figure} figures/releases.png
:alt: Bar chart of how many days before its class each lecture from L3 to L19 was published, with a dashed line at seven days labelled the plan, a week ahead. L3 is 4 days, L4 3, L5 1, L6 2, L7 0, L8 3, L9 0, L10 0, L11 2, L12 5, L13 0, L14 1, L15 0, L16 2, L17 0, L18 1 and L19 0. No bar reaches the dashed line.
:width: 100%

Days between each lecture going public and its class, from the commit that uncommented the lecture
in `_toc.yml`. Same-day releases are in red. L1 and L2 were published before the semester.
```

Content changed too. On 2026-10-08 the back half of the schedule was restructured. On 2026-10-12
Lecture 20 changed from agents to reinforcement learning. On 2026-11-01, the day before Lecture 18,
seven case studies from other fields arrived: biomedical engineering, biomedical imaging, health
care, energy, mechanical and electrical engineering, civil engineering, and materials science.
Each one reads a documented example through the lectures it illustrates and links back to them, and
the Lecture 18 map gained side paths to them. The students in this course come from many fields, and
the case studies give each of them a worked example closer to their own. On 2026-10-28 an Ask button
on every page began to search the course notes for an answer, and on 2026-11-02 the course became an agent skill that a student
can install in their own coding assistant. On 2026-11-04 the schedule changed again, and the
deployment lecture moved to the optional slot it holds now.

An assistant is what made that pace possible. A new case study with every number checked against
its source, or a new interactive figure built from a lecture's own data, is days of work for one
person writing it by hand. With the assistant doing the research and the drafting, and an instructor
steering and reviewing, it fitted between one class and the next, so the course could change in
response to what happened in the room.

### The conventions file

```{index} CLAUDE.md, conventions file
```

At the root of the repository is `CLAUDE.md`, the file the assistant reads at the start of every
session. It says what is public and what is not, which file is the source of truth for which claim,
what a set of notes must contain, how a number must be verified, and what not to do. Every rule in
it is a decision made once so that it does not have to be made again in every session.

:::{admonition} Definition: conventions file
:class: tip
A **conventions file** is a file at the root of a project that records its rules and decisions,
read by every person and every AI assistant that works on it, so that a decision is made once and
then followed.
:::

```{figure} figures/ratchet.png
:alt: A step plot of the number of lines in CLAUDE.md from July to November 2026. It starts at 241 lines on July 20 and reaches about 445 within days, stays flat until early August, then climbs in steps to about 920 by mid August. It dips to about 860 just before the dashed first-class line on August 24, rises to about 950 in early September, and then grows slowly to 984 by November 4.
:width: 100%

The length of `CLAUDE.md` at each of the 42 commits that changed it, from `figures/make_figures.py`.
```

The file grew from 241 lines on 2026-07-20 to 859 the day before the first class, and to 984 by
2026-11-04. Most of the growth came in the two weeks before the semester, when the practice game,
the style guide and the map each brought rules of their own. During the ten weeks of teaching it
grew by about 125 lines, and once went 33 days without a change. That shape is what a conventions
file is for. The rules were mostly written while the course was being designed, and then the
semester ran on them.

Most of the rules were written after a mistake, so that the same mistake is not made twice:

| Rule | The mistake behind it |
|---|---|
| Check every number against its source | the famous "less than 10% of the code is the model" is not in the paper it is cited to ([Lecture 1](../l01/notes.md)) |
| Draw every figure from a script, never copy one | the drift figure in Lecture 1 was meant to show steady decay, and the data showed a seasonal swing |
| Pin the site builder, Jupyter Book, below version 2 | version 2 names each page after its file, so every lecture's `notes.md` would collapse into one page |
| Branch from an up-to-date main branch | a lecture branched from a stale one had its links to already-merged lectures downgraded to plain text to make the build pass |
| Re-check a quoted section whenever the notes change | a practice question can quietly start testing text that no longer exists |
| Never judge past work by present content | growing a practice question pool made finished modules count as unfinished |

A rule that exists because of a mistake carries the reason with it, which is why it survives.

### What the instructors decided, and what the assistant did

Two instructors wrote the specifications: the topics, the datasets, the demos and the readings for
each lecture. They set the standards in `CLAUDE.md` and in the style guide, mostly by reacting to
output that was not good enough. They merged every pull request and closed the ones that were not
right. The assistant did the research, the measurement, the figure scripts, the drafting and the
checks, at a pace no instructor could match alone.

| The instructors | The assistant |
|---|---|
| chose the topics, datasets, examples and level | searched for and read the sources |
| wrote the rules it works by | drafted notes, slides and practice questions |
| reviewed what it produced | wrote and ran the scripts behind every figure and number |
| decided every change that reached the site | built the interactive figures, the practice game and the checks |
| taught the lectures | |

Two things were kept out of the assistant's hands entirely, as the
[syllabus](../../course/syllabus.md) states: AI is not used to grade your work or to write feedback
on it, and your submissions and personal information do not go into AI tools.

The steering is visible in the record and in what was sent back. A draft that read well but rested
on a number nobody had checked was sent back to find the source. A slide that was crowded was made
readable. An explanation that was correct but not introductory enough was rewritten from a story
before the mathematics, as the matrix section of Lecture 20 was this month. The numbers in the
optional Lecture 21 were first measured while other heavy jobs were running on the same machine, and
were remeasured from scratch on an idle machine once that was noticed, and in the same pass a
container image size that had been labelled as unpacked turned out to be the compressed size. Each
of those errors would have shipped if the output had been read for fluency rather than checked.

The assistant's failures are specific, and they are the reason the checks exist. It writes fluent,
well-organized prose that can be confidently wrong, and it can produce it faster than a person can
read it carefully. It will treat a link that resolves as a link that supports the claim. It will
report a measurement without asking whether the machine was busy. The rules in `CLAUDE.md` read as a
list of those failures: research before writing, verify every source in two steps, generate every
figure from a committed script, and run every check in continuous integration rather than trusting
anyone to remember it.

## Learning a new field quickly

```{index} specification, two-step verification
```

You will not have a course for the next field you move into. What you can take from this one is the
method it was built with, because it is a method for learning a broad body of unfamiliar material
quickly and getting it right. None of it depends on the particular tools.

**Start from a specification.** Before generating anything, write down what you need to know and
why: the decisions you have to make, the data you will have, what a good answer would look like.
This course started from one specification per week, and every lecture was checked against it. An
assistant given a vague request produces a confident survey. Given a specification, it produces an
answer to your question, and you can tell when it has drifted.

**Research first, write second.** Start from primary sources: the paper, the documentation, the
standard, the dataset's own description. Read them before you write anything, and let what you find
change the plan. A draft written from memory and then supported with links afterwards is how an
invented statistic gets into a report.

**Verify every source in two steps.** First, the source exists and the link resolves. Second, the
source actually says what you are citing it for. The second check is the one people skip, and it is
where most of the errors in this course's history were caught. A widely repeated claim is not more
likely to be in its source; it is only more likely to be repeated.

**Predict before you measure.** Write down the number you expect before you run the code. When the
measurement disagrees you have found the place where your understanding was wrong, which is the most
valuable thing a measurement can tell you. If you did not write the prediction down first, the
measured value will seem unsurprising, because it always does afterwards.

**Generate every number and figure from code.** If a number appears in your report, a committed
script should print it. This turns "I remember it was about 3 dB" into a command anyone can rerun,
and it catches the drift when the data or a library changes.

**Write the rule down the first time something goes wrong.** Keep one file at the root of your
project, and add to it whenever you lose an hour to something avoidable. It will look untidy for a
month and then start saving you time, and it is the only way a lesson reaches the next person, or
the next session of an assistant that does not remember the last one.

**Make the check automatic.** A rule that depends on someone remembering it erodes. A rule that runs
on every change does not. Promote warnings to errors, test the thing you actually ship, and give an
assistant a check it can run that comes back pass or fail. The Claude Code documentation puts it the
same way: "Give Claude something it can run that comes back pass or fail," and ask for the evidence,
"the command it ran and its output," because "'All tests pass' on its own tells you very little"
([Best practices for Claude Code](https://code.claude.com/docs/en/best-practices)).

**Steer actively.** Read the plan before the work starts, when mistakes are cheapest to fix. Watch
the first minute of a long task and stop it the moment it drifts. The same documentation advises
that after two failed corrections you start a fresh session with a better prompt rather than try a
third. Review the output the way you would review a capable new colleague's work: assume it is
fluent, and check whether it is right.

## Generating is not learning

```{index} testing effect, retrieval practice, illusion of explanatory depth, desirable difficulty, learning by teaching
```

The method above produces correct material quickly. It does not put that material into your head,
and an assistant makes it easy to confuse the two. This course was produced in about fifteen weeks.
The notes alone run to about 169,000 words, which is more than ten hours to read once, and working
through them properly, running the notebooks and rederiving the numbers, takes many times that. Production got much faster.
Learning did not, because it is limited by how fast a person can be changed by something, and an
assistant does not change that. A folder of correct, well-organized material that nobody has worked
through feels like progress and is not.

### Reading feels like learning, and is measurably worse

Roediger and Karpicke tested this in 2006. Students read short prose passages and then either
reread them or took a recall test on them, and were tested again later. Five
minutes afterwards, rereading won: 81% recalled against 75%. Two days later, testing won by 68%
against 54%, and a week later by 56% against 42%. In a second experiment, students who read a
passage four times recalled the most at five minutes and the least a week later, and they were also
the most confident that they would remember it. Their sense of how well they knew the material moved
in the opposite direction from how well they actually knew it
([Roediger and Karpicke, 2006](https://psychology.ecu.edu/wp-content/pv-uploads/sites/216/2019/03/Roediger-Karpicke-2006.pdf)).

```{figure} figures/rereading.png
:alt: Line chart of the share of a passage recalled on a final test, against the time until that test. Students who reread the passage recalled 81% at 5 minutes, 54% at 2 days and 42% at 1 week. Students who took a recall test instead recalled 75%, 68% and 56%. The lines cross between 5 minutes and 2 days.
:width: 80%

Recall after rereading against after a recall test, at three delays, redrawn from the numbers
Roediger and Karpicke (2006) report for their first experiment.
```

:::{admonition} Definition: testing effect
:class: tip
The **testing effect** is the finding that trying to recall material improves long-term retention
more than studying it again for the same time, even though rereading feels more effective.
:::

Asking an assistant to explain something and reading its clear answer is rereading with the fluency
turned up. The explanation is more coherent than the one you would have written, so it feels more
like understanding. That feeling is the signal the experiment says not to trust. Bjork and Bjork call
the alternatives, such as testing yourself, spacing your study and mixing problem types,
**desirable difficulties**: conditions that make practice feel harder and slower and make the
learning last. In their words, "current performance can be a highly unreliable index of whether
learning has occurred" ([Bjork and Bjork, 2011](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/04/EBjork_RBjork_2011.pdf)).

### Explaining shows you what you do not know

Rozenblit and Keil asked people to rate how well they understood how everyday devices work, such as
a zipper or a cylinder lock, then to write a detailed step-by-step causal explanation, and then to
rate themselves again. "Nearly all participants showed drops in estimates of what they knew when
confronted with having to provide a real explanation." They called the gap the illusion of
explanatory depth, and found it strongest for knowledge of how things work, which is the kind this
course is made of ([Rozenblit and Keil, 2002](https://cogdevlab.yale.edu/sites/default/files/files/rozenblit%20&%20keil%20%202002.pdf)).

The practical test takes ten minutes. Close the notes and write out a mechanism from memory, in full
sentences, for someone who has not read them: why a random split leaks on time series, what a
conformal interval guarantees, why `async def` can stall a server. Stop where you stall. That point
is the actual edge of your knowledge, which you could not see before you tried. Then read only the
part you stalled on. Teaching goes one step further. Fiorella and Mayer found that students who
prepared to teach a lesson and then actually taught it on video did best on a delayed comprehension
test, while students who only prepared to teach did better on an immediate test but not a delayed
one ([Fiorella, 2023](https://www.unh.edu/teaching-learning-resource-hub/sites/default/files/media/2023-06/itow-learning-by-teaching-fiorella.pdf)).
Expecting to explain is not enough; the explaining is what helps.

### What the AI studies show

```{index} pair: case study; GPT Tutor high school mathematics trial
```
```{index} pair: case study; AI assistance and coding skill formation
```

Two recent experiments measured this directly with AI assistants. Bastani and colleagues gave nearly
a thousand high school mathematics students access to an AI tutor built on a large language model
during practice sessions. One group had a plain chat interface, GPT Base, and one had a version
designed to act as a tutor rather than hand out answers, GPT Tutor. On the practice problems, grades rose by 48% with GPT Base and 127% with GPT
Tutor. On the later exam, taken without the assistant, the GPT Base group did 17% worse than students
who never had it. The GPT Tutor group did no worse than the control group, but no better either, and
yet those students believed they had done better
([Bastani et al., 2025, PNAS](https://pmc.ncbi.nlm.nih.gov/articles/PMC12232635/)).

Shen and Tamkin, at Anthropic, asked 52 mostly junior software engineers to learn Trio, a Python
library none of them knew, with or without an AI assistant, and quizzed them right after the task on
debugging, reading code and concepts. The AI group averaged 50% on the quiz against 67% for the group
that coded by hand, and was not significantly faster. How the assistant was used mattered more than
whether it was used: participants who asked it only conceptual questions scored well, and those who
handed it the code to write, or leaned on it to debug, scored lowest
([Anthropic, 2026](https://www.anthropic.com/research/AI-assistance-coding-skills);
[Shen and Tamkin, arXiv:2601.20245](https://arxiv.org/abs/2601.20245)).

Neither study says not to use an assistant. Both say that an assistant used to produce the answer
raises the score on the task in front of you and lowers what you can do afterwards without it, and
that an assistant used to question you, give hints or explain a concept you then apply yourself does
much less harm. When you learn a new field with one, use it as a tutor and an examiner. Have it quiz
you on the paper you just read and grade your answer. Write your explanation first, then ask it to
find the gaps. Ask it why, not only what. Then do the problem yourself, and keep the attempt that
failed, because the failure is where the learning is.

### The rung ladder

```{index} rung ladder
```

Every practice question in this course shows a rung, a number from 0 to 7. Each rung is a way of
working through the material that costs more effort than the one below it and teaches more,
following the studies above. Rung 0 is the rereading that Roediger and Karpicke found weakest, rung
5 is Rozenblit and Keil's written explanation, and rung 6 is Fiorella's actual teaching.

| Rung | What to do |
|---|---|
| 0 | Read the notes |
| 1 | Write down a prediction before each measured result |
| 2 | Work out one number yourself, without looking |
| 3 | Run a notebook, break it on purpose, and predict the error |
| 4 | Change one assumption in a figure script, predict what moves, and rerun it |
| 5 | Close everything and write the mechanism from memory |
| 6 | Explain one section out loud to a classmate, without notes |
| 7 | Find something wrong in the course and tell us, with the evidence |

Rung 5 shows you where your understanding stops. Rung 6 helps when you explain to someone, not when
you only prepare to. Rung 7 improves the course for the next person, and it is the same work as
the two-step verification above, pointed at us.

### Try this

1. **The gradient that should have agreed.** Before running anything, predict whether PyTorch and
   JAX match the exact gradient, and to how many digits. Then run
   `lectures/l11/figures/make_figures.py`, and explain the gap before you read the script's header.
2. **Fix a broken notebook.** Run `lectures/l01/l01-reproducibility.ipynb`. It is broken on purpose
   in three documented ways. Fix each one.
3. **Count tokens.** Predict how many tokens one line of a datasheet costs, then count it with
   [Tiktokenizer](https://tiktokenizer.vercel.app/).
4. **Fix something.** Find one thing in this course that is wrong, unclear or out of date, and tell
   us, with the source.

## Limitations and trade-offs

Building a course this way has real costs, and some of them are easy to miss.

**Review is the bottleneck, and it does not get faster.** The assistant could draft a lecture in
hours. Reading it carefully enough to catch a wrong number, a misattributed quote or a figure that
contradicts its caption still took a person most of a day. Without that review the speed is a
liability, because errors accumulate faster than anyone notices them. Most of the 49 commits in the
history with no Claude trailer are an instructor editing by hand: the syllabus, the schedule, the
assignments, and small fixes to notes and slides.

**Fluent errors outpace casual review.** Most of the corrections in the history are about claims
rather than code: a statistic not in its source, a measurement taken on a busy machine, an image
size labelled as unpacked that was compressed, a quoted passage that had changed. None of them would
have been caught by a test suite. They were caught by checking against a source or by measuring
again.

**The collaborator is not a fixed quantity.** Four model versions appear in the trailers, and each
change of model was a change in the collaborator. Rules written down in `CLAUDE.md` survived the changes; habits that
lived only in a session did not.

**It costs money, and it produces more than anyone can read.** The figures for the language-model
lectures call paid APIs, and they cache their results so that rerunning a script does not pay twice.
The larger cost is the one in the previous section: material is now cheap to produce and exactly as
expensive as before to learn.

**It is the wrong tool when you cannot check the output.** An assistant is most useful where the
result can be verified: a script that runs, a test that passes, a number that matches its source.
Where you cannot tell a right answer from a fluent wrong one, it hands you confidence you have not
earned. That is the situation you are in at the start of every new field, which is why the method
above begins with sources and checks rather than with generation.

## In-class demo

The demo notebook, [`l22-git-history.ipynb`](l22-git-history.ipynb), reads the history of any git
repository with `git log` and plots three things: commits per week, the share of commits with each
kind of co-author trailer, and the length of one file over time, such as a `README.md` or a
`CLAUDE.md`. In class it runs on this course's repository. Then run it on your own final-project
repository, and ask the same questions this lecture asked of the course: when did the work happen,
where did it change direction, and which of your fixes should have become a rule.

## Summary

The course covered three arcs, from data you can trust through models you can believe to language
models in loops with tools, and a few ideas ran through all of it: make results reproducible, split
the data the way the model will meet the world, measure rather than assume, say how wrong you might
be, remember that the model is a small part of the system, and fear the output that looks fine. The
course itself was built in about fifteen weeks by two instructors and an AI coding assistant, in 354
commits through 133 pull requests, 86% of them crediting a Claude model and four model versions
along the way. The instructors wrote the specifications, set the standards, and reviewed and merged
every change; the assistant researched, measured, drafted and checked, fast enough that the course
could change in response to the room. Most of its rules were written before the semester began, each
after a specific mistake, and most of its corrections came from checking a claim against its source
or measuring again. The same method will serve you in the next field: start from a specification,
read primary sources, verify in two steps, predict before you measure, generate every number from
code, write the rule down, and make the check automatic. And because generating material is not
learning it, use the assistant to test you and to find the gaps in your own explanation, not to skip
the attempt.

## Resources

- [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices). The current
  guidance on giving an assistant a check it can run, keeping a conventions file short, and steering
  a session, from the tool used to build this course.
- [`CLAUDE.md`](https://github.com/jkitchin/f26-06763/blob/main/CLAUDE.md). The course's
  conventions file in full, with the reason behind each rule.
- [Roediger and Karpicke, Test-enhanced learning (Psychological Science, 2006)](https://psychology.ecu.edu/wp-content/pv-uploads/sites/216/2019/03/Roediger-Karpicke-2006.pdf)
  (publisher PDF on a university mirror). The experiment in which rereading wins at five minutes,
  loses at a week, and raises confidence anyway.
- [Rozenblit and Keil, The misunderstood limits of folk science (Cognitive Science, 2002)](https://cogdevlab.yale.edu/sites/default/files/files/rozenblit%20&%20keil%20%202002.pdf)
  (authors' copy). Rate, explain, re-rate: the ten-minute test of whether you understand a
  mechanism. Study 1 is enough.
- [Bjork and Bjork, Making things hard on yourself, but in a good way (2011)](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/04/EBjork_RBjork_2011.pdf)
  (authors' copy). Desirable difficulties in nine pages, including when a difficulty stops being
  desirable.
- [Fiorella, Learning by teaching (2023)](https://www.unh.edu/teaching-learning-resource-hub/sites/default/files/media/2023-06/itow-learning-by-teaching-fiorella.pdf).
  A short chapter on the evidence that explaining to someone helps and expecting to explain is not
  enough.
- [Bastani et al., Generative AI without guardrails can harm learning (PNAS, 2025)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12232635/)
  (open access). The high school mathematics trial: practice scores up, exam scores down, and a
  tutor-style prompt that removed most of the harm.
- [Anthropic, How AI assistance impacts the formation of coding skills (2026)](https://www.anthropic.com/research/AI-assistance-coding-skills)
  and the paper, [Shen and Tamkin, arXiv:2601.20245](https://arxiv.org/abs/2601.20245). Learning a
  new library with and without an assistant, and the usage patterns that kept the learning.
- [Becker et al., Measuring the impact of early-2025 AI on experienced open-source developer productivity (arXiv:2507.09089)](https://arxiv.org/abs/2507.09089).
  The METR trial from Lecture 19, in which developers forecast that AI would make them 24% faster,
  believed afterwards it had made them 20% faster, and were measured 19% slower. Your own sense of
  how much an assistant helps is another number to measure rather than assume.
- [Pro Git, Viewing the commit history](https://git-scm.com/book/en/v2/Git-Basics-Viewing-the-Commit-History).
  The `git log` options the demo notebook uses, for reading a repository's history yourself.

## Assignment

None. Your final-project presentations are on Wednesday 11-18 and Monday 11-23; see the
[final project](../../course/final-project.md) page for what to bring.
