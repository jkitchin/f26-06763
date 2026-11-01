# How this course was built

:::{admonition} At a glance
:class: tip

- **Optional.** Nothing here is graded.
- **What it is:** how we built this course with an AI coding agent, and what you can take from
  that for your own work.
- **The short version** is the instructors' AI statement in the [syllabus](../syllabus.md).
:::

## What we used

- **[Claude Code](https://claude.com/claude-code)**, Anthropic's AI coding agent. It reads
  files, searches, runs code and edits files, in a loop, while we review and approve.
- **Several Claude models** over the semester: Claude Opus 4.8, Opus 5, Opus 5.5 and Sonnet 5.
  The model changed under us mid-project.
- **Both instructors** built the course this way. In the
  [commit history](https://github.com/jkitchin/f26-06763/commits/main), every change made with
  Claude carries a "Co-Authored-By: Claude" line.

## Who did what

| We, the instructors | The agent |
|---|---|
| chose the topics, datasets, examples and level | searched for and read the sources |
| wrote the rules it works by | drafted notes, slides and practice questions |
| reviewed what it produced | wrote and ran the scripts behind every figure and number |
| decided every change that reached this site | built the interactive figures, the practice game and the checks |
| teach the lectures | |

- AI is not used to grade your work or to write feedback on it.
- We do not put your submissions or personal information into AI tools.

## How one change reaches this site

1. **Request:** we describe the change and point the agent to the course's rules.
2. **Work:** the agent reads, searches, runs code and edits files, in a loop.
3. **Review:** we read the change and ask for fixes.
4. **Checks:** continuous integration (CI) rebuilds the site and runs the automatic checks.
5. **Merge:** one of us merges the pull request (PR), and the site updates.

The guardrails along the way:

- **Permissions:** we set what the agent may do without asking us.
- **Automatic checks:** the build fails on any warning. Other checks confirm that every practice
  question still matches the notes, that no instructor-only file is published, and that the
  live site serves the new version.
- **A person merges.** Nothing reaches this site without one of us.

## The rules file

- `CLAUDE.md`, at the root of the [repository](https://github.com/jkitchin/f26-06763/blob/main/CLAUDE.md),
  holds the course's rules. The agent reads it at the start of every session.
- Most rules were written after a mistake, so the mistake is not made twice:

| Rule | The mistake behind it |
|---|---|
| Check every number against its source | the famous "less than 10% of the code is the model" is not in the paper it is cited to ([Lecture 1](../../lectures/l01/notes.md)) |
| Draw every figure from a script, never copy one | the drift figure in Lecture 1 was meant to show steady decay; the data showed a seasonal swing |
| Pin the site builder, Jupyter Book, below version 2 | version 2 names each page after its file, so every lecture's `notes.md` would collapse into one page |
| Never judge past work by today's content | growing a quiz pool made finished practice modules count as unfinished |

## Measure, do not assume

- Every figure, and every number we measured, comes from a script you can rerun:
  `figures/make_figures.py` in each lecture's folder.
- Measuring changed the lecture more than once:

| We expected | We measured | Where |
|---|---|---|
| PyTorch and JAX both match the exact gradient | PyTorch was off by 7.5e-8, JAX by 4.4e-16: two Python numbers had silently become float32 | [Lecture 11](../../lectures/l11/notes.md) |
| The same model ranking under any split | on the concrete strength dataset, a decision tree beats a straight line with random folds, and loses to it by 2 MPa when rows are grouped by mix | [Lecture 9](../../lectures/l09/notes.md) |
| Our tiny GPT finishes all 16 course terms | 15 of 16: "physics-in" became "physics-into a s", because "into a" appears 58 times in our notes and "physics-informed" only 8 | [Lecture 17](../../lectures/l17/notes.md) |

## Generating is not learning

- Producing course material is now cheap. Learning it costs what it always did.
- Rereading the notes feels like learning. Testing yourself works better, although rereading
  leaves you more confident ([Roediger and Karpicke, 2006](https://pubmed.ncbi.nlm.nih.gov/16507066/)).
- Use the course actively. Each rung costs more and teaches more, and every practice question
  shows its rung:

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

- Rung 5 shows you where your understanding stops.
- Rung 6 works when you explain to someone, not when you only prepare to.
- Rung 7 improves the course for the next person.

## Try this

1. **The gradient that should have agreed.** Before running anything, predict whether PyTorch
   and JAX match the exact gradient, and to how many digits. Then run
   `lectures/l11/figures/make_figures.py`. Explain the gap before you read the script's header.
2. **Fix a broken notebook.** Run `lectures/l01/l01-reproducibility.ipynb`. It is broken on
   purpose in three documented ways. Fix each one.
3. **Count tokens.** Predict how many tokens one line of a datasheet costs, then count it with
   [Tiktokenizer](https://tiktokenizer.vercel.app/).
4. **Fix something.** Find one thing in this course that is wrong, unclear or out of date, and
   tell us, with the source.

## Resources

- [Claude Code documentation](https://code.claude.com/docs): the agent we used, including the
  rules file and the permission settings.
- [`CLAUDE.md`](https://github.com/jkitchin/f26-06763/blob/main/CLAUDE.md): the course's rules
  file, in full.
- [Roediger and Karpicke (2006)](https://pubmed.ncbi.nlm.nih.gov/16507066/): students who
  restudied felt more confident, but two days or a week later they remembered less than students
  who had tested themselves.
- [Rozenblit and Keil (2002)](https://cogdevlab.yale.edu/sites/default/files/files/rozenblit%20&%20keil%20%202002.pdf):
  people rate their understanding lower after trying to write out a mechanism (rung 5). Study 1
  is enough.
- [Fiorella, *Learning by teaching*](https://www.unh.edu/teaching-learning-resource-hub/sites/default/files/media/2023-06/itow-learning-by-teaching-fiorella.pdf):
  a short summary of the evidence that explaining to someone beats preparing to (rung 6).
