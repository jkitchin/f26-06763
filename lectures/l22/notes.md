# Lecture 22: Course overview and how this course was built

:::{admonition} At a glance
:class: tip

- **Session** Lecture 22, Week 12
- **Arc** Course wrap-up
- **Slides** <a href="../../slides/l22/">Deck for this session</a>
- **Course map** <a href="../../game/#/map">The knowledge graph</a> and
  <a href="../../game/#/map/system">the system figure</a>, live in your browser
- **Practice** No practice module for this session. Every earlier module stays open on the
  <a href="../../game/#/map">course map</a>
- **Assignment** None
:::

## Why this matters

- In twelve weeks the course went from a Python environment to language-model agents.
- Nobody masters that much in a semester. The goal was to meet each idea well enough to know
  where to start when you need it again.
- Most examples were engineering data: a chemical plant, concrete mixes, jet engines, roadside
  gas sensors.
- The methods are not tied to that data. The same mistakes and the same fixes show up in
  medicine, power grids, bridges and materials.
- This session:
  - Puts the course in one picture.
  - Shows seven applications outside chemical engineering.
  - Introduces two interactive reviews of the course: a knowledge graph and a live version of
    Lecture 1's system figure.
  - Shows how the course was built with an artificial intelligence (AI) coding assistant, with
    lessons for your own projects.
  - Gives a method for learning the next field, and for still learning it yourself.

## Learning objectives

By the end of this session you should be able to:

- Describe the course's four parts and the ideas that run through them, and name the lecture
  to go back to for each.
- Connect the course's methods to applications in other fields, using the case studies.
- Use the course map's knowledge graph and system figure to review a lecture, a topic or a part
  of a machine learning system.
- Explain how this course was built with an AI coding assistant: what the instructors decided,
  what the assistant did, and which checks caught its errors.
- Plan how to learn a new technical area quickly with an AI assistant while still learning it
  yourself.

## The course in one picture

### Four parts

- Each part builds on the one before.
- The colours match the knowledge graph.

**Foundations, Lectures 1 and 2:** the system around the model, and reproducible work.

- [Lecture 1](../l01/notes.md): the model is a small box inside a much larger system.
- [Lecture 2](../l02/notes.md): reproducible environments with `uv`, lockfiles and Git.

**Data systems, Lectures 3 to 7:** store, move and check the data before any model sees it.

- [Lecture 3](../l03/notes.md) and [Lecture 4](../l04/notes.md): sensor data in PostgreSQL, then
  in Parquet and DuckDB.
- [Lecture 5](../l05/notes.md): batch pipelines that are safe to rerun.
- [Lecture 6](../l06/notes.md): streams, late data and checks on incoming data.
- [Lecture 7](../l07/notes.md): features that exist at the moment of prediction.

**Machine learning, Lectures 8 to 16:** fit models, and decide whether to trust them.

- [Lecture 8](../l08/notes.md), [Lecture 9](../l09/notes.md) and [Lecture 10](../l10/notes.md):
  the workflow for time series, regression and classification.
- [Lecture 11](../l11/notes.md): tensors, automatic differentiation and a training loop by hand.
- [Lecture 12](../l12/notes.md): network architectures for engineering data.
- [Lecture 13](../l13/notes.md): physics-informed networks, and neural ordinary and
  differential-algebraic equations.
- [Lecture 14](../l14/notes.md): how wrong a prediction might be.
- [Lecture 15](../l15/notes.md): using that uncertainty to choose the next experiment.
- [Lecture 16](../l16/notes.md): learning a whole distribution and sampling from it.

**Language models, Lectures 17 to 19:** models that read and write text, and use tools.

- [Lecture 17](../l17/notes.md): a tiny language model, trained from scratch.
- [Lecture 18](../l18/notes.md): choosing what the model sees, with tools and search.
- [Lecture 19](../l19/notes.md): a model in a loop with tools, inside a set of checks.
- Optional, [Lecture 20](../l20/notes.md): reinforcement learning, learning to act from rewards.

### The ideas that come back

- These ideas work in any field. The tools will change.
- **Make results reproducible:** lock the software versions and keep the code in Git
  ([Lecture 1](../l01/notes.md), [Lecture 2](../l02/notes.md)).
- **Split the data the way the model will be used:** never let one unit (a time period, a mix,
  an engine, a patient) sit on both sides of the split ([Lecture 8](../l08/notes.md),
  [Lecture 9](../l09/notes.md), [Lecture 12](../l12/notes.md)).
- **Measure, do not assume:** time it and test it, because rules of thumb about speed and
  accuracy can be wrong ([Lecture 11](../l11/notes.md)).
- **Report the uncertainty:** give a range with every prediction
  ([Lecture 14](../l14/notes.md), [Lecture 15](../l15/notes.md)).
- **The model is a small part of the system:** most of the work is in the data, the checks and
  the serving ([Lecture 1](../l01/notes.md), [Lecture 19](../l19/notes.md)).
- **Check results that look right:** a high score or a fluent answer can still be wrong
  ([Lecture 9](../l09/notes.md), [Lecture 17](../l17/notes.md)).

## Applications across fields

```{index} pair: case study; MIT-BIH patient split
```
```{index} pair: case study; chest X-ray hospital shortcut
```
```{index} pair: case study; Epic Sepsis Model validation
```
```{index} pair: case study; GEFCom2014 load forecasting
```
```{index} pair: case study; CWRU bearing benchmark
```
```{index} pair: case study; Z24 bridge monitoring
```
```{index} pair: case study; shape memory alloy search
```

- Seven published case studies, one per field, use methods from this course.
- Each one is an overview: the problem, what happened, why, and which course concepts apply.
- "Course tools that apply here" lists tools you met in the lectures that you could use on the
  same problem. They are not necessarily the tools the original authors used.
- Each case has its own page on the course site, with the full story and sources.

| Field | The problem | Lectures |
|---|---|---|
| Biomedical engineering | Label each heartbeat in electrocardiogram (ECG) recordings | L9, L10, L12 |
| Medical imaging | Find pneumonia in chest X-rays | L1, L7, L12 |
| Health care | Warn hospital staff early that a patient may have sepsis | L1, L10, L14 |
| Energy | Forecast electricity demand for each hour | L7, L8, L14 |
| Mechanical and electrical | Detect a failing bearing from its vibration | L7, L10, L12 |
| Civil | Detect damage in a bridge from how it vibrates | L1, L6, L8 |
| Materials | Choose which new alloy to make and test next | L9, L14, L15 |

### Biomedical engineering: heartbeat classification

- **Problem:** software labels each heartbeat in an electrocardiogram (ECG) as normal or abnormal.
- **What happened:** a method scored 98.7% on patients it had already seen, but 76.3% on new
  patients.
- **Why:** each person's heartbeats look alike, so testing on known patients inflated the score.
- **Concepts from our course:** split by patient with grouped cross-validation
  ([Lecture 9](../l09/notes.md)); precision and recall for rare classes
  ([Lecture 10](../l10/notes.md)); neural networks for signals ([Lecture 12](../l12/notes.md)).
- **Course tools that apply here:** scikit-learn, PyTorch.
- **Takeaway:** test on new patients, the way the model will be used.
- **References:** [Luz et al. (2016), ECG-based heartbeat classification for arrhythmia
  detection: a survey](https://doi.org/10.1016/j.cmpb.2015.12.008)
  ([open copy](https://web.archive.org/web/20220624180052/https://www.repositorio.ufop.br/bitstream/123456789/7011/1/ARTIGO_ECGHeartBeat.pdf));
  [de Chazal et al. (2004)](https://doi.org/10.1109/TBME.2004.827359)
  ([open copy](https://web.archive.org/web/20060514090303/http://dsp.ucd.ie:80/dspfiles/main_files/pdf_files/PdeC_HeartBeatjuly04.pdf));
  [our case study page](../../case-studies/ecg-patient-splits.md).

### Medical imaging: chest X-rays and the hospital they came from

- **Problem:** a neural network learned to find pneumonia in chest X-rays from two hospitals, then
  was tested at a third.
- **What happened:** it did worse at the new hospital. Another network could tell which hospital
  took an X-ray almost every time.
- **Why:** one hospital had far more pneumonia (34% against about 1%). Clues to the hospital, like
  a metal marker in the corner, can become a shortcut to the answer.
- **Concepts from our course:** neural networks for images ([Lecture 12](../l12/notes.md));
  leakage, an input that gives away the answer ([Lecture 7](../l07/notes.md)); testing on data
  from a new source ([Lecture 1](../l01/notes.md)).
- **Course tools that apply here:** PyTorch, scikit-learn.
- **Takeaway:** test on a new source: a new hospital, lab or plant.
- **References:** [Zech et al. (2018), Variable generalization performance of a deep learning
  model to detect pneumonia in chest radiographs](https://doi.org/10.1371/journal.pmed.1002683)
  (open access); [our case study page](../../case-studies/chest-xray-shortcuts.md).

### Health care: a sepsis alert already in use

- **Problem:** a commercial model, used in hundreds of hospitals, warns staff that a patient may
  be developing sepsis, a dangerous reaction to infection.
- **What happened:** in an independent test, it missed 2 of every 3 sepsis cases. Only 1 in 8
  flagged patients had sepsis.
- **Why:** sepsis is rare (7% of hospital stays), so false alarms outnumber real cases. No
  independent test had been published before.
- **Concepts from our course:** recall, precision and the alert threshold
  ([Lecture 10](../l10/notes.md)); calibration, whether a 30% risk means 30%
  ([Lecture 14](../l14/notes.md)); good results on the developer's data are not proof
  ([Lecture 1](../l01/notes.md)).
- **Course tools that apply here:** scikit-learn metrics, calibration plots.
- **Takeaway:** measure a model on your own data before you trust it.
- **References:** [Wong et al. (2021), External validation of a widely implemented proprietary
  sepsis prediction model in hospitalized patients](https://pmc.ncbi.nlm.nih.gov/articles/PMC8218233/)
  (open access); [our case study page](../../case-studies/sepsis-alert-validation.md).

### Energy: forecasting electricity demand

- **Problem:** grid operators must predict electricity demand to decide which power plants to run.
- **What happened:** in the Global Energy Forecasting Competition 2014, teams predicted a range of
  demand for every hour of the next month, and were scored on the whole range.
- **Why:** underestimating demand means too little power, so planners need to know how high demand
  could go.
- **Concepts from our course:** lagged features, such as past temperature and demand
  ([Lecture 7](../l07/notes.md)); forecast horizons and simple baselines
  ([Lecture 8](../l08/notes.md)); prediction intervals ([Lecture 14](../l14/notes.md)).
- **Course tools that apply here:** pandas, Polars, scikit-learn.
- **Takeaway:** when the extremes matter, forecast the range of possible outcomes.
- **References:** [Hong et al. (2016), Probabilistic energy forecasting: Global Energy
  Forecasting Competition 2014 and beyond](https://robjhyndman.com/papers/gefcom2014.pdf)
  (authors' copy); [Hyndman and Fan (2010), Density forecasting for long-term peak electricity
  demand](https://robjhyndman.com/papers/peak_electricity_demand.pdf) (authors' copy);
  [North American Electric Reliability Corporation, 2025 Summer Reliability
  Assessment](https://www.nerc.com/globalassets/programs/rapa/ra/nerc_sra_2025.pdf);
  [our case study page](../../case-studies/electric-load-forecasting.md).

### Mechanical and electrical engineering: bearing faults

- **Problem:** spot damaged motor bearings from their vibration, using a popular public dataset.
- **What happened:** recent papers report scores over 94%. One network scored 100% on bearings it
  had seen, and 63% on new ones (50% is a coin flip).
- **Why:** the usual splits put the same bearing in training and testing, so models can learn the
  bearing instead of the fault.
- **Concepts from our course:** features from vibration signals ([Lecture 7](../l07/notes.md));
  splitting by bearing, and comparing with simple models ([Lecture 12](../l12/notes.md));
  accuracy can hide missed faults ([Lecture 10](../l10/notes.md)).
- **Course tools that apply here:** scikit-learn, PyTorch.
- **Takeaway:** when a score looks near perfect, check that the test data is really new.
- **References:** [Vieira et al. (2026), Towards a more realistic evaluation of machine learning
  models for bearing fault diagnosis](https://arxiv.org/abs/2509.22267) (open preprint);
  [Case Western Reserve University Bearing Data Center](https://engineering.case.edu/bearingdatacenter);
  [our case study page](../../case-studies/bearing-fault-benchmark.md).

### Civil engineering: damage or a cold night? The Z24 bridge

- **Problem:** spot damage in a bridge from how it vibrates.
- **What happened:** the Z24 bridge was monitored for a year, then damaged on purpose. Temperature
  changed its vibration more than the damage did.
- **Why:** freezing made the bridge much stiffer. So the team predicted how fast the healthy
  bridge should vibrate at each temperature. After the damage, it vibrated slower than predicted.
- **Concepts from our course:** seasons and drift change the data ([Lecture 1](../l01/notes.md));
  checks on incoming sensor data ([Lecture 6](../l06/notes.md)); modelling normal behaviour and
  flagging what is left over ([Lecture 8](../l08/notes.md)).
- **Course tools that apply here:** pandera, scikit-learn.
- **Takeaway:** model what the environment does, then look for what it cannot explain.
- **References:** [Peeters and De Roeck (2001), One-year monitoring of the Z24-Bridge:
  environmental effects versus damage events](https://doi.org/10.1002/1096-9845(200102)30:2%3C149::AID-EQE1%3E3.0.CO;2-Z);
  [Gowdridge et al. (2022)](https://arxiv.org/abs/2209.05484) (open preprint);
  [KU Leuven Z24 bridge page](https://bwk.kuleuven.be/bwm/z24);
  [our case study page](../../case-studies/bridge-health-monitoring.md).

### Materials science: searching for a new alloy

- **Problem:** find the best new metal alloy among about 800,000 options, each made and tested in
  a lab.
- **What happened:** a model picked 4 alloys per round. After 9 rounds, 14 of the 36 new alloys
  beat the team's best earlier one.
- **Why:** the model predicted how good each alloy would be and how sure it was, and each round
  picked a mix of promising and uncertain options.
- **Concepts from our course:** models that report their uncertainty
  ([Lecture 14](../l14/notes.md)); Bayesian optimization picks the next experiment
  ([Lecture 15](../l15/notes.md)); regression on composition ([Lecture 9](../l09/notes.md)).
- **Course tools that apply here:** scikit-learn, BoTorch.
- **Takeaway:** when experiments are expensive, let the model choose the next one.
- **References:** [Xue et al. (2016), Accelerated search for materials with targeted properties
  by adaptive design](https://www.nature.com/articles/ncomms11241) (open access);
  [our case study page](../../case-studies/alloy-adaptive-design.md).

## The interactive reviews

```{index} knowledge graph, force-directed layout
```

- Two interactive reviews of the course run in your browser, also on a phone.
- They need no login and record nothing.

### The knowledge graph

<a href="../../game/#/map">Open the knowledge graph</a>.

:::{admonition} Definition: knowledge graph
:class: tip
A **knowledge graph** is a network of things (here lectures, topics and concepts) joined by links
that each mean something specific (here, one lecture's notes link to another).
:::

```{figure} figures/kg-lectures.png
:alt: The knowledge graph by lecture on a dark background. Each lecture is a coloured circle with its number and short title, coloured by part of the course, with this lecture in red at the centre. Curved lines join lectures whose notes link to each other.
:width: 100%

The course by lecture. A line joins two lectures when one's notes link to the other.
```

- **By lecture:** point at a lecture to light up what it builds on and what builds on it. Click
  it to see its takeaways, learning objectives and applications.
- **By topic:** each theme of the course, with the concepts from the course index around it.
- **Quick review:** one click lights every failure mode, case study or metric in the course.

### The system figure from Lecture 1

<a href="../../game/#/map/system">Open the system figure</a>.

```{figure} figures/system.png
:alt: Lecture 1's system figure as a grid of boxes on a dark background, each sized by the code it needs: configuration, data collection, feature extraction, analysis tools, process management tools, machine resource management, monitoring, data verification, serving infrastructure, and a small red box for the machine learning code, 3.7% of the area. Each box shows the lectures that cover it.
:width: 100%

Lecture 1's figure, live. The model is the small red box, 3.7% of the area.
```

- The same boxes as the figure in [Lecture 1](../l01/notes.md), with the same sizes.
- Click a box to see the lectures, the tools and the case studies for that part of the system.

### How they are built

- The course notes are text files, one per lecture.
- A Python script turns them into a list of lectures, links and concepts.
- It runs again on every change, so the map always matches the course.
- A web page draws them in your browser with React and the d3-force library. No server is
  needed.
- A **force-directed layout** places the points by simulating forces: points push each other
  apart, links pull their two ends together, and the picture is where the simulation comes to
  rest.

## How this course was built

```{index} Git, pull request, Claude Code, continuous integration
```

### The process

```{figure} figures/process.svg
:alt: How the course was made. The instructors designed the course and its order, chose every dataset and example, wrote a spec for every lecture, set the standards and the rules, planned the extra materials, edited every draft, reviewed every change and merged every change. Claude Code researches the sources and drafts additional notes, slides, figures and extras. Automatic checks run on every change, and a failed check goes back to be fixed. A change merges only after an instructor approves; otherwise the instructor asks for changes. The result is the course you used: lecture notes and slides, plus a practice game, a course map, a clicker, case studies, narrated slides and interactive figures.
:width: 100%

How the course was made: the instructors' work, the assistant, the automatic checks, and the
review before any change reached you. [Lecture 19](../l19/notes.md) showed the same path for one
change.
```

The instructors:

- Designed the course and its order.
- Chose every dataset and example.
- Wrote a specification for every lecture.
- Set the standards and the rules the assistant follows.
- Planned the extra materials.
- Edited every draft, directly or through Claude Code.
- Reviewed every change, and sent work back.
- Merged every change you saw.

The assistant, Claude Code:

- Researched the sources.
- Drafted additional notes, slides, figures and extra materials.

On every change:

- Automatic checks ran: the build, the links, the figures and the quiz quotes.
- The result: the lecture notes and slides, plus extra materials for a better class: a practice
  game, a course map, a clicker, case studies, narrated slides and interactive figures.

For your own projects: an AI assistant drafts fast, but the design, the standards and the final
review stay with you.

### The history

```{figure} figures/changes.png
:alt: Every change merged into the course from July to November 2026, as one dot on the day it merged, in five lanes: lectures (64 changes), course pages and assignments (17), practice game and course map (21), clicker, arcade and Ask (14), and build, checks and rules (17). Bigger dots carry more commits. A dashed line marks the first class on August 24.
:width: 100%

Every change merged into the course up to November 4, by the part of the course it touched.
Bigger dots carry more commits.
```

- Every change was built, tested and reviewed before it reached you.
- For your own projects: set up **continuous integration**, automatic checks that build and test
  every change before it goes live, for example with GitHub Actions.

### What we added along the way

```{figure} figures/timeline.svg
:alt: A timeline from July to November 2026 of what was built around the lectures, coloured by kind. Rules: the rules file, July 20. Practice and review: the practice game, August 7; the course map, August 8; the knowledge graph, November 5. In class: the clicker, August 25; interactive figures, September 27; narrated slides, October 12. Reading and help: the Ask button, October 28; case studies, November 1. The first class was on August 24.
:width: 100%

What was built around the lectures, and when, coloured by kind.
```

- The extra materials kept coming all semester, added as the class needed them.
- The knowledge graph and the live system figure arrived on November 5.
- For your own projects: ship a first version early, then improve it with feedback.
- Building with AI at high quality is more work, not less. Aim for very good, ship it, then keep
  improving.

### The rules file

```{index} CLAUDE.md, conventions file
```

:::{admonition} Definition: conventions file
:class: tip
A **conventions file** is a file in a project that lists its rules. Every person and every AI
assistant that works on the project reads it.
:::

- This course's conventions file is `CLAUDE.md`.
- Each rule follows the same loop:
  1. Something goes wrong.
  2. Find the cause.
  3. Write a rule, with the reason.
  4. Automate the check, so the same mistake does not come back.

Two examples from the course's infrastructure:

| What went wrong | The check now |
|---|---|
| A deploy reported success, but the site still showed the old version | Every deploy checks the live site |
| Slides had text cut off at the bottom | A check renders every deck and fails if anything overflows |

For your own projects: keep a rules file, and turn each rule into an automatic check where you
can.

## Learning a new field quickly

- You will not have a course for the next field you move into.
- The way this course was built works as a method for learning one.

Before you start:

1. Write down what you need to know, and what a good answer looks like.
2. Start from original sources: papers, documentation, data descriptions.

While you work:

3. Confirm each fact at its source before you build on it.
4. Predict the result, then run it. A surprise shows what you got wrong.
5. Make every number and figure with code you keep, so anyone can rerun it.

When something goes wrong:

6. Write down a rule, with the reason.
7. Automate the check, so it runs on every change.

An AI assistant makes each step faster. It does not let you skip any of them.

## Generating is not learning

```{index} testing effect, illusion of explanatory depth, learning by teaching
```

- An assistant can write the material for you. It cannot learn it for you.
- The notes of this course run to about 169,000 words.
- Producing them got much faster. Learning them did not.

### Test yourself

:::{admonition} Definition: testing effect
:class: tip
The **testing effect** is the finding that you remember more by trying to recall something than
by reading it again.
:::

- Roediger and Karpicke (2006) had students read two short texts. They read one again, and
  wrote down what they remembered of the other.
- Share of the text recalled on a final test:

| Final test after | Read it again | Wrote down what they remembered |
|---|---|---|
| 5 minutes | 81% | 75% |
| 2 days | 54% | 68% |
| 1 week | 42% | 56% |

```{figure} figures/rereading.png
:alt: Line chart of the share of a text recalled against the time until the final test. Reading again starts higher at 5 minutes and ends lower at 1 week; recalling crosses above it between 5 minutes and 2 days.
:width: 80%

Reading again is ahead after five minutes and behind after two days.
```

- In a second experiment, the students who only reread were the most confident, and
  remembered the least after a week.
- Reading an AI's explanation feels like learning. Recalling it yourself is what lasts.

### Explain it to find the gaps

- Rozenblit and Keil (2002) asked people how well they understood a zipper or a lock, then asked
  them to explain it step by step, then asked again.
- Almost everyone rated their understanding lower after trying to explain it. They called this
  the **illusion of explanatory depth**.
- Try it: close the notes and write down from memory why a random split leaks on time series.
  Where you get stuck is where your understanding stops.
- Teaching helps more than preparing to teach: in
  [Fiorella and Mayer's studies](https://doi.org/10.1016/j.cedpsych.2013.06.001), students who
  actually taught did best on a later test (**learning by teaching**).

### An AI tutor study

```{index} pair: case study; GPT Tutor high school mathematics trial
```

- Nearly 1,000 high school students practised math in three groups, assigned by class: no AI, a
  chat assistant that gives answers, or an AI tutor told to give hints instead of answers (with
  the teachers' solutions in its instructions).
- Then everyone took the same exam without AI
  ([Bastani et al., 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12232635/)).

| Group | Practice grades, with the AI | Exam grades, without the AI |
|---|---|---|
| Chat assistant (gives answers) | 48% higher than no AI | 17% lower than no AI |
| AI tutor (gives hints) | 127% higher than no AI | about the same as no AI |

- Both AI groups did much better in practice.
- On the exam, the answers group did worse than students who never had AI. The hints group did
  not do worse, but did not do better either.
- The tutor group rated their exam performance higher than the no-AI group did. Their scores
  were the same.

### Ways to study, from 0 to 7

- Higher levels take more effort and teach more, following the studies above.
- The practice questions in this course show their level as "rung".

| Level | What to do |
|---|---|
| 0 | Read about it |
| 1 | Predict the result before you look |
| 2 | Work one example by hand |
| 3 | Break working code on purpose, and predict the error |
| 4 | Change one assumption, predict what moves, and rerun |
| 5 | Explain it from memory, in writing |
| 6 | Teach it to someone |
| 7 | Fix a bug in open-source code, or tackle an open problem |

With an AI assistant:

- Ask it to quiz you, and to grade your answer.
- Explain first, then ask it for the gaps.
- Ask why, not only what.
- Solve the problem yourself.
- Use the assistant to move up the levels, not to skip them.

## Limitations and trade-offs

| Good at | Watch out for |
|---|---|
| Drafting from a clear plan | Confident answers that are wrong |
| Code you can run and test | Numbers and quotes with no real source |
| Finding sources, which you then read | More text than anyone can read and check |
| Repetitive work: figures, formatting, checks | Doing the practice for you |

- A good workflow: you plan, the assistant drafts, you check (run it, test it, read the source),
  and you decide.
- Use an assistant where you can check the result, and check what it gives you.
- At the start of a new field you often cannot check yet, which is why the method starts with
  original sources.

## Summary

- The course had four parts: foundations, data systems, machine learning, and language models
  that use tools.
- A few ideas ran through all of them: make results reproducible, split the data the way the
  model will be used, measure instead of assuming, report the uncertainty, and remember that the
  model is a small part of the system.
- None of these is specific to chemical engineering. The same split mistake appears in
  heartbeats, bearings and hospital X-rays, and the same methods in power grids, bridges and
  alloy design.
- The knowledge graph and the live system figure let you review the whole course and find the
  lecture to go back to.
- The course was built with an AI coding assistant. The instructors designed it, wrote every
  spec, edited every draft, and reviewed and merged every change, with automatic checks on every
  change.
- For the next field: write down what you need, start from original sources, confirm each fact,
  predict before you measure, and automate the checks.
- Generating material is not learning it. Use an assistant to test you, not to do the work for
  you.

## Resources

- [Case studies across engineering](../../case-studies/index.md). The seven case studies, each
  with the lectures it connects to and its full references.
- [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices). How to give
  an assistant checks it can run, and how to guide a session.
- [`CLAUDE.md`](https://github.com/jkitchin/f26-06763/blob/main/CLAUDE.md). The course's rules
  file, with the reason for each rule.
- [GitHub Actions documentation](https://docs.github.com/en/actions). Automatic checks on every
  change, as this course uses.
- [Roediger and Karpicke, Test-enhanced learning (2006)](https://psychology.ecu.edu/wp-content/pv-uploads/sites/216/2019/03/Roediger-Karpicke-2006.pdf)
  (publisher's copy on a university site). Reading again wins after five minutes and loses after
  a week.
- [Rozenblit and Keil, The misunderstood limits of folk science (2002)](https://cogdevlab.yale.edu/sites/default/files/files/rozenblit%20&%20keil%20%202002.pdf)
  (authors' copy). Rate, explain, rate again.
- [Bastani et al., Generative AI without guardrails can harm learning (2025)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12232635/)
  (open access). Practice grades up, exam grades down.
- [d3-force](https://d3js.org/d3-force). The force simulation behind the knowledge graph's
  layout.

## Assignment

None. Your final-project presentations are on Wednesday 11-18 and Monday 11-23; see the
[final project](../../course/final-project.md) page for what to bring.
