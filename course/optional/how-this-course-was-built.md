# How this course was built, and what to take from that

:::{admonition} At a glance
:class: tip

- **Optional.** Nothing here is examinable. It is here because the method is more durable
  than the syllabus.
- **What it is.** A case study in tool triage and in navigating an unfamiliar problem, using
  this repository's own construction as the worked example.
- **What to do with it.** The roadmap at the end is the point. Read the rest for the
  evidence behind it.
:::

## Why this document exists

Some of the specific tools this course teaches will move, be replaced, or change their
defaults under you. Nobody can give you a reliable percentage for that, and this document
is not going to invent one, but the rate is visible in the repository itself. Within the
seventeen days between this repository's first commit and this document, all of the
following were live problems: the publishing tool had a major version whose default
behaviour would have silently broken the site, scikit-learn changed how a cross-validation
splitter assigns folds between two minor releases with no warning and no signature change,
one vendor's tokenizer changed inside its own model line by about 30%, and the AI assistant
used to do the work went through a model generation change mid-project. Every one of those
is documented in a lecture or a commit, and none of them is a cautionary tale from the
past.

So the course has a problem it cannot solve by teaching more tools. Whatever you leave
with has to survive the tools going stale. Three things do:

1. **You will always face more tools than you can learn.** Triage is the skill: deciding
   quickly which ones deserve your attention, which are someone else's problem, and which
   are actively worth avoiding. This is not a phase you get through at the start of a
   career. It is the job, permanently.

2. **When you enter a new area, you navigate with fundamentals and land with
   implementations.** The fundamentals tell you what must be true. The implementation is
   some particular approximation of that, with its own defaults, bugs, and silences. Being
   able to tell which of your two answers is the fundamental and which is the approximation
   is the whole game.

3. **This course used [Claude Code](https://claude.com/claude-code) to make the first two
   tractable at a scale a single instructor could not otherwise reach**, and did it in the
   open, in a repository whose entire history you can read.

That last point is why this document can be specific rather than inspirational. Most
courses hand you the output and hide the process. Here the process is the artifact: the
specification, the conventions file, the generators, the commits, the pull requests, the
continuous integration, and the record of everything that turned out to be wrong. You are
about to spend a semester being told to make your work reproducible and inspectable. It
would be strange if the course itself were not.

## What the record actually contains

As of 2026-08-06, on the published branch:

| | |
|---|---|
| sets of lecture notes | 14, totalling 7,331 lines |
| slide decks | 14 |
| demo notebooks | 14 |
| figure generator scripts | 10, producing 35 committed figures |
| commits on `main` | 37 |
| pull requests | 18, of which one was closed unmerged and redone |
| co-authorship trailers naming a model | 32, across four model versions |

That last row is worth pausing on before anything else. The commits credit Claude Opus 4.8,
Claude Opus 5, and Claude Sonnet 5. The course was not built with *a* model; it was built
across a model generation change, mid-project. Everything below about pinning, verifying,
and writing conventions down exists partly because the collaborator itself was not a fixed
quantity.

## The conventions file is the interesting artifact

At the root of the repository is `CLAUDE.md`, which opens by calling itself "the contract
for how lecture material is structured." It is read at the start of every working session,
by a person or by a model, and it is the single most load-bearing file in the project. It
sat at 447 lines for the two weeks before this document was written, and the table below is
how it got there.

It is not documentation. Documentation describes what exists. This file **decides**, in
advance, questions that would otherwise be re-litigated every session: what is public and
what is not, which file is the source of truth for which claim, how long a deck should be,
what counts as a verified number, what a set of notes is allowed to look like. Some of its
rules are flatly prohibitive, and a section titled "Things not to do" exists because each
of those things was done once.

### The file is a ratchet, and you can watch it tighten

Every rule in `CLAUDE.md` is a defect that was paid for once. The git history makes this
literal:

| revision | lines | what it added | what caused it |
|---|---|---|---|
| `4f42681` | 241 | the initial conventions | project start |
| `f112d2d` | 257 | asset-path configuration for a subpath deployment, and the rule that HTTP 200 is not evidence a page rendered | the freshly deployed site loaded as unstyled text |
| `abd2358` | 303 | a hard pin to Jupyter Book 1.x, and three independent mechanisms enforcing the public/private boundary | version 2 derives page URLs from the file basename, which would have silently collapsed every `lectures/*/notes.md` onto a single `/notes` page |
| `f422b3a` | 353 | "Research first, write second," and a two-step rule for verifying every link and every number | a widely repeated statistic turned out not to appear in the paper everyone cites for it |
| `0ca2480` | 425 | deck sizing against the 110-minute session, and "Generate, do not copy" for figures | a first-draft deck ran dry well before the room would have; a figure computed from real data disagreed with the claim it was drawn to illustrate |
| `487bcee` | 447 | the textbook-chapter depth standard, and the requirement that any session introducing a technology also weigh it | the third set of notes established a bar the first two had not met |

Five of those six revisions happened on the project's first day. The sixth came three days
later. **The file has not changed since 2026-07-23.**

That date matters more than the growth curve. When `CLAUDE.md` last changed, exactly two
sets of lecture notes existed. There are now fourteen. **Twelve sets of notes, twelve decks,
twelve notebooks, and nine figure scripts have been produced against a contract that has
not needed to change in the fourteen days since.**

This is the return on writing conventions down, and it is the thing to steal. The cost was
about a day of noticing what kept going wrong and being disciplined enough to write the
rule instead of just fixing the instance. The payoff is that a dozen subsequent sessions
did not have to rediscover any of it. A convention file whose growth tracks incidents is an
asset. One written up front, out of imagination, is a wish list.

### The source-of-truth chain, and fixing upstream

The file specifies a chain:

```
course/modules/wkNN.md  →  lectures/lNN/notes.md  →  lectures/lNN/slides.md
   (the spec)                (the full argument)        (the delivery)
```

with an explicit instruction: if the specification and an existing set of notes disagree,
say so rather than quietly picking one.

That rule earned itself early. While writing L1, verification turned up that the famous
claim that "less than 10% of the code in a machine learning system is the model" does not
appear in the paper it is universally attributed to. Sculley and colleagues say only that
the ML code box is "tiny in proportion to the rest of the system"; the precise-sounding
percentage was invented somewhere downstream and then repeated into apparent fact. The
lecture was corrected, and [L1's notes now use the discrepancy deliberately](../../lectures/l01/notes.md)
as the course's first example of checking a claim against its source.

The instructive part is what happened next. A separate commit, landing after the lecture
was already published, records that the *specification* still asserted the debunked figure.
The lecture had been fixed; the file that generates lectures had not. That commit corrected
the spec and added a note recording why the number is absent, so that a later well-meaning
edit would not helpfully reintroduce it.

Three habits are visible in that one small change, and all three transfer directly to
engineering work:

**When you find a defect, ask where it entered, not just where you noticed it.** Fixing the
lecture was fixing the symptom. The spec was the defect.

**A correction that leaves no trace will be undone.** Somebody, eventually, will notice the
missing statistic and add it back as an improvement. The note exists to make that person
stop.

**The authority of a source is not transitive.** Everyone citing the 10% figure was citing
a real paper. None of them had read it for that number.

## Meta-message one: triage, as actually practiced

The repository uses a fairly small number of tools for a project of its size, and the
interesting thing is not the list but the reasons.

| tool | the job it does | why this one |
|---|---|---|
| `uv` | environments and dependencies | lockfile plus pinned interpreter; `uv run --with pkg` declares a script's dependencies at the point of use, so no figure script depends on the state of a global environment |
| Jupyter Book 1.x | notes to a published site | **pinned below 2** for a specific reason, below |
| MARP | markdown to slides | decks stay diffable text in the same repository as the notes, so a claim and the slide that makes it move together |
| matplotlib | figures | every figure is produced by a committed script, never pasted |
| GitHub Actions | build, render, and publish | the build runs with warnings promoted to errors, so a broken cross-reference fails before it ships |
| GitHub issues and pull requests | one issue per session, one branch, one PR | the unit of work is reviewable and the reasoning survives in the PR description |
| Claude Code | the work itself | discussed below |

Two of those rows are worth expanding, because they are triage decisions rather than
preferences.

### The worked example: newer lost

Jupyter Book 2 is the current major version, a rewrite on a new engine, and by every
surface signal the obvious choice. It is pinned out.

The reason is in `CLAUDE.md` section 8: version 2 derives a page's URL from the file's
**basename**. This layout puts one directory per session, each containing a `notes.md`. Under
version 2, `lectures/l01/notes.md` and `lectures/l02/notes.md` both become `/notes`, and
one silently overwrites the other. No error, no warning, and a `slug:` in frontmatter does
not override it. Fourteen lectures would have collapsed into one page, and the failure mode
is invisible until somebody clicks the wrong link.

Notice what made that decision possible. It was not a feature comparison. It was asking a
fundamentals-level question, *how does this tool decide what a page is called*, and finding
that the answer conflicted with a structural commitment already made. Version 1 mirrors the
directory tree, which is what the layout depends on.

### The honest counterexample

That pin is enforced in continuous integration, where the workflow installs
`jupyter-book<2`. It is not enforced on a laptop. The machine this document was written on
has version 2.1.2 installed globally, so the build command printed in the course's own
README fails with `error: unknown option '--warningiserror'`.

The failure is mild but the shape of it is worth studying, because it is the shape of most
tooling failures you will actually meet. The error message names a flag, so the natural
reading is that the command has a typo. The natural fix is to drop the flag. That flag is
the one that turns broken cross-references into build failures, so dropping it would
disable the check and produce a build that looks successful. **A misleading error message
plus a plausible local fix is how a safety mechanism gets removed by someone trying to be
helpful.** The actual fix is to run the pinned version in a throwaway environment:

```bash
uv run --with "jupyter-book<2" jupyter-book build . --warningiserror --keep-going
```

### Three questions worth asking of any tool

Distilled from the above, and offered as something you can actually use on Monday:

**What decision does this make for me that I would otherwise make by hand?** That is the
value. If you cannot name it, you are adopting a dependency for its README.

**What does it cost when it is wrong?** Not *if*. Jupyter Book 2's URL scheme costs a
silently broken site. `tiktoken` used against a different vendor's model costs a budget that
is 31% low. An unpinned `GroupKFold` costs a number in your paper.

**How would I find out it is wrong?** This is the question people skip, and it is the one
that separates a tool you can rely on from one you merely use. If the answer is "I would
notice eventually," you need a check, not a tool.

## Meta-message two: fundamentals first, implementations second

The rule in `CLAUDE.md` is that every number appearing in a set of notes or a deck must be
printed by a committed script that anyone can re-run. Ten such scripts exist. They are not
a formality, and the reason is worth stating plainly: **if you cannot compute a claim, you
do not understand it well enough to teach it, and quite often you do not understand it well
enough to have believed it.**

The evidence is that computing the claims kept changing them. Each of these was drafted one
way, measured, and rewritten. Every one of the headers in those scripts records the
discrepancy on purpose, so the surprise survives into the next person's reading.

| what was expected | what was measured | why it happened |
|---|---|---|
| autodiff agrees with the analytic gradient to machine precision | PyTorch disagreed at 5e-8 while JAX agreed at 3e-16 | two Python floats silently became float32. The relative error was 1.25e-7 and float32 epsilon is 1.19e-7. Nothing warned, because float32 promotes to float64 on contact |
| the GPU is faster | for this model the accelerator was **7 times slower**, and only won past ~256 hidden units | the crossover, not the speedup, is the number that decides anything |
| unnormalized inputs cause NaNs | with SGD, immediately; with Adam, never. Training merely degraded from 5.5 to about 9.5 MPa | Adam's per-parameter scaling hides a scaling bug as mediocrity, which is worse than a crash |
| gradient boosting beats a neural net on small tabular data | it does by 0.51 MPa on a random split, and by 0.13 ± 0.18 MPa (a tie) under a grouped split | much of the advantage was the tree's greater ability to exploit a leaky split. A single seed showed the net *winning*; five seeds showed a tie |
| a cross-validation splitter is a cross-validation splitter | scikit-learn 1.8 and 1.9 assign groups to folds by different rules, same signature, no warning: 2.08 dB against 1.50 dB, and 91% coverage against 94% | the version drift was larger than most of the effects the lecture set out to measure |
| more samples give a better experimental design | a 81-point Sobol design was measurably *worse* than a 64-point one | the construction's balance guarantees hold at powers of two. Adding 17 points made the design worse |
| long inputs make an API call slow | 130 times more input added 0.4 seconds; 128 times more output added 22 | reading is parallel, writing is serial. One output token costs about a thousand input tokens of latency |
| semantically similar text scores higher than dissimilar text | "seal leaking" against "no leak found" scored 0.694, higher than a genuine near-duplicate pair at 0.532 | cosine similarity measures what a text is *about*. A leak and a no-leak are maximally about the same thing |

Read that column of causes again, because there is a single pattern under all of it. In
every case the *expectation* came from an authority: a textbook result, a module
specification, a vendor's positioning, a widely repeated benchmark. In every case the
*measurement* came from a fundamentals-level property of the implementation: float32 has
7 decimal digits; attention over a prompt is parallel and generation is not; a
low-discrepancy sequence is balanced at powers of two; an optimizer that rescales
per-parameter will absorb a scaling error.

That is meta-message two in operational form. **Fundamentals tell you what the answer has
to look like. The implementation tells you what you actually got. When they disagree, the
gap is where the lesson is**, and it is almost always more interesting than the claim you
started with.

There is a corollary that costs people real time. Most of those rows produce output that
looks completely fine. Nothing crashes. The float32 contamination, the Adam degradation,
the `GroupKFold` change, and the single-seed comparison all return a plausible number that
a careful person would write down and move on from. **Plausible
output is the failure mode you should fear**, and the only defence is knowing what the
number ought to be before you compute it.

## Meta-message three: what the collaboration actually looked like

The honest version, because a flattering one would undermine everything above.

**The shape.** One GitHub issue per session, each carrying the same skeleton: the topic, a
pointer to the module file as the specification, a checklist of deliverables, and a
reminder that the conventions live in `CLAUDE.md`. From the issue, a branch. On the branch,
research, measurement, figures, writing. Then a pull request whose description carries the
reasoning, continuous integration, review, and merge. The human wrote the specifications,
set the standards, merged every pull request, and closed the one that was not right.

**It is not "an AI wrote a course."** The specifications in `course/modules/` are the
instructor's, and they decide the topics, the datasets, the demos, and the readings.
The standards in `CLAUDE.md` were set by a human reacting to output that was not good
enough. Every merge was a human decision.

**The model's failure modes are specific and they are the reason the safeguards exist.** It
will produce fluent, well-structured, confidently wrong prose, and it will do so at a rate
that outpaces casual review. The "research first, write second" rule exists because the
opposite order produces exactly that. The verification rule exists because a resolving URL
was being treated as a verified claim. The requirement that figures be generated exists
partly because a generated figure cannot be a plausible-looking fabrication. Read the
safeguards as a map of what goes wrong.

**It moved a real bottleneck.** The scarce resource in course development is not typing.
It is the willingness to go and actually check the thirteenth claim, download the primary
source, run the measurement, and then rewrite a section you liked because the measurement
disagreed. That work is unglamorous, and it is precisely the work that scales well here.
The eight rows in the table above exist because checking became cheap enough to always do.

**It cost money and it is not free of drift.** The figures for the LLM lectures call
provider APIs; the L15 figures cost on the order of a dollar in credit, and they cache
their results so that re-runs do not. Model versions changed under the project
mid-flight, which is exactly the class of problem the course teaches you to pin for.

## What iteration actually looked like

Repository history is more honest than any retrospective, so here are the parts worth
reading.

**A pull request was closed and redone.** PR #37 and PR #38 are the same lecture. The first
was branched off another unmerged lecture's branch, because the notes cross-referenced a
page that did not exist yet and the build fails on a dangling cross-reference. That made
the diff carry someone else's work, so it was abandoned and redone standalone once the
dependency merged.

**The same footgun recurred two weeks later.** The most recent lecture was branched from a
stale copy of `main` that predated four merged lectures. Cross-references pointed at pages
that did not exist on that base, so they were downgraded to plain text to get a clean
build. After a rebase onto current `main`, all of them became working links again. Nobody
had written the rule down after the first occurrence.

That is the most useful thing in this document, so it is worth being blunt about it. **The
ratchet only ratchets when someone writes the rule.** A lesson learned and not recorded is a
lesson you will pay for again, and the second bill arrives when you have forgotten enough to
be surprised. As part of writing this document, that rule was added to `CLAUDE.md`, which
is the first change to that file in fourteen days. You can read the commit.

**Standards rose, and earlier work had to be revisited.** The depth standard was set when
L3 was written and turned out to be higher than what L2 had met, so L2 was later deepened
in a commit that exists only to bring earlier work up to a bar raised after it was written.
Expect this on any project long enough to have a learning curve. Budget for it rather than
pretending the first thing you made is still representative.

**Verification produced most of the rework.** The corrections in the history are
overwhelmingly about claims rather than code: an unsupported statistic, a figure that
disagreed with its caption, a number inherited from a library default. Very little of it is
the kind of bug a test suite catches.

## A roadmap

This is the part to actually use.

### Read the repository in this order

Each artifact answers a different question, and reading them in this order means each one
makes sense when you get to it.

1. **`CLAUDE.md`.** Ask: *which of these rules would I not have thought of, and what do I
   think it cost to learn?* You are reading a defect log written as instructions.
2. **One set of lecture notes, end to end.** `lectures/l03/notes.md` is the reference for
   depth. Ask: *where does this stop asserting and start measuring?*
3. **That lecture's `figures/make_figures.py`, header first.** The headers are written to
   record what the measurement changed. Ask: *would I have caught this, or would I have
   shipped the expectation?*
4. **The demo notebook.** `lectures/l01/l01-reproducibility.ipynb` is deliberately broken in
   three documented ways, and its generator explains each. Ask: *which of these three have I
   personally shipped?*
5. **The CI workflow**, `.github/workflows/book.yml`. Ask: *what is each step preventing,
   and how would I have found out without it?* One step exists solely to stop
   instructor-only files from reaching a public site.
6. **The git log and the pull requests.** Ask: *what got redone, and what would have
   prevented it?*

### Build the same discipline on your own work

Five steps, in increasing order of commitment. Steps one and two are worth doing this week
regardless of what else you take from the course.

**Write down the rule the first time something bites you.** Not the fix, the rule. One
file, at the root of your project, appended to whenever you lose an hour to something
avoidable. It will be ugly for a month and then it will start saving you time.

**Make every number in your write-up reproducible by a committed script.** If a number
appears in your report, a script in your repository should print it. This single practice
catches more errors than any amount of care, and it converts "I remember it was about 3
dB" into a command.

**Verify in two steps, always.** The source exists, *and* the source says what you are
citing it for. The second check is the one people skip and it is where fabricated facts
live.

**Predict before you measure.** Write down the number you expect before you run the code.
When they differ you have learned something; when you did not write it down first, you will
find the measured value unsurprising, because people always do.

**Make the check automatic.** A rule enforced by a person is a rule that erodes. A rule
enforced by continuous integration is a rule. Promote your warnings to errors and see what
falls out.

### Where this lands in this course

The assignments are built to exercise this rather than to reward it separately. A1 is the
reproducible scaffold, and the discipline above is what makes it worth more than a grade.
A8 requires a gold set and a measured comparison between two prompts specifically because
"it looked better" is not a result. The capstone is the place to bring the whole practice:
a convention file, generated figures, verified claims, and a build that fails when you
break something.

If you take one thing, take the ratchet. Everything else in this document is a consequence
of somebody writing down what went wrong, once, in a place the next person would read.

## Resources

- [`CLAUDE.md`](https://github.com/jkitchin/f26-06763/blob/main/CLAUDE.md) in this
  repository, if you have access. It is the artifact this document is mostly about, and it
  reads quickly.
- [Claude Code documentation](https://code.claude.com/docs). The tool used throughout,
  including the conventions-file mechanism described above.
- [Hidden Technical Debt in Machine Learning Systems](https://papers.nips.cc/paper_files/paper/2015/file/86df7dcfd896fcaf2674f757a2463eba-Paper.pdf).
  Sculley et al., NeurIPS 2015. The source of the framing in L1, and the paper whose
  misquotation is the running example above. Nine pages.
- [The Pragmatic Programmer](https://pragprog.com/titles/tpp20/the-pragmatic-programmer-20th-anniversary-edition/),
  Hunt and Thomas. Old, and the chapters on automation, plain text, and "don't repeat
  yourself" are the intellectual ancestor of most of what is described here.
- [`uv` documentation](https://docs.astral.sh/uv/). Specifically the `uv run --with`
  pattern, which is how every figure script in this repository declares its dependencies
  without a global environment.
- [Jupyter Book](https://jupyterbook.org/) and [MARP](https://marp.app/). The publishing
  half of the toolchain, and the subject of the version-pinning story above.
