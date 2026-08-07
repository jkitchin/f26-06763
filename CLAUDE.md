# CLAUDE.md, working conventions for this repo

Course materials for **06-763 / 14-763 / 18-763, Systems & Toolchains for AI in
Engineering** (Fall 2026). This file is the contract for how lecture material is
structured, so that notes and slides written weeks apart, by different people or in
different sessions, read as one course.

Read this before creating or editing any lecture material.

**Toolchain:** notes are MyST markdown built by **Jupyter Book 1.x** (pinned `<2`, see
section 8), slides are **MARP** markdown, and CI publishes both to GitHub Pages.

---

## 1. What is public

**The repository is private. The rendered site is public.**

The GitHub Pages site at <http://kitchingroup.cheme.cmu.edu/f26-06763/> is world-readable
even though the repo is not.

| Published | Private |
|---|---|
| `index.md` | `course/modules/wkNN.md` (instructor planning, teaching notes, pitfalls) |
| `course/syllabus.md`, `course/schedule.md` | Anything under a `solutions/` directory |
| `lectures/*/notes.md` | Draft material not yet added to `_toc.yml` |
| `course/assignments/aNN.md` | Grading keys, exam material, student data |
| `course/miniproject.md`, `course/final-project.md` | |
| `course/optional/*.md` | |
| Rendered slide decks at `/slides/lNN.html` | |

Three mechanisms enforce this, and all three should stay in place:

1. `_toc.yml` lists only publishable files.
2. `_config.yml` sets `only_build_toc_files: true`. **This matters more than it looks.**
   Sphinx by default builds every source file it finds, not just the ones in the table of
   contents. Without this setting, `course/modules/` would be absent from the navigation
   but still reachable at a guessable URL.
3. `_config.yml` also lists `course/modules` in `exclude_patterns`, and CI has a step that
   fails the build if any `modules` page reaches the output directory.

Rules that follow:

- **Never add `course/modules/` to `_toc.yml`**, and never set `only_build_toc_files: false`.
- Never put solutions, grading keys, or anything identifying a student in a published file.
- Student-facing pitfalls *should* be lifted out of the module files into the notes, where
  students will read them. Instructor-facing observations stay in `course/modules/`.
- When adding any file to `_toc.yml`, confirm it contains nothing instructor-only.

---

## 2. Layout

```
├── CLAUDE.md              this file
├── _config.yml            Jupyter Book 1 config (privacy settings live here)
├── _toc.yml               table of contents; only listed files are built
├── index.md               book landing page
├── .marprc.yml            MARP config (resolves `theme: course`)
├── themes/course.css      shared MARP theme
├── _templates/
│   ├── notes.md           skeleton + structure contract for notes
│   └── slides.md          skeleton + structure contract for decks
├── course/                planning material, authored before the semester
│   ├── syllabus.md        published
│   ├── schedule.md        published, L1–L26 + MP-1/MP-2
│   ├── modules/wkNN.md    NOT published, the spec for each week
│   └── assignments/aNN.md published
├── lectures/
│   └── lNN/
│       ├── notes.md       narrative, student-facing, read outside class
│       ├── slides.md      MARP deck, projected during class
│       ├── demo.ipynb     runnable artifact driven live (optional)
│       └── figures/       images referenced by notes or slides
└── .github/workflows/book.yml
```

**Naming.** Lectures are `l01` through `l26`, zero-padded, matching the L-numbers in
`course/schedule.md`. The Week 8 mini-project sessions are `mp1` and `mp2`. Assignments
are `a01` through `a11` (there is deliberately no `a07`; the mini-project is A7).

One directory per **session**, not per week. Week 1 is two directories, `l01` and `l02`.

Published URLs mirror this structure: `lectures/l01/notes.md` becomes
`/f26-06763/lectures/l01/notes.html`.

---

## 3. The source-of-truth chain

```
course/modules/wkNN.md  →  lectures/lNN/notes.md  →  lectures/lNN/slides.md
   (the spec)                (the full argument)        (the delivery)
```

**Always read the module file first.** Each `course/modules/wkNN.md` contains, per lecture,
the objectives, topics, live demo, engineering framing/dataset, and readings. That is the
specification. Notes expand it into narrative; slides compress the notes for projection.

Specific obligations:

- Learning objectives in the notes are lifted **verbatim** from the module file's lecture
  block, unless the lecture genuinely changed. If it changed, update the module file too so
  the two do not drift.
- The notes' H2 sections should follow the module's **Topics** list, expanded from bullets
  into prose. Reorder or merge where the argument reads better; do not silently drop a topic.
- The demo and dataset named in the module file are the ones the notes and slides use.
  Datasets are chosen per module on purpose; do not substitute one for convenience.
- Readings in the module file are the seed for the notes' Resources section, which should
  annotate them and may add more.

If the module file and an existing set of notes disagree, say so rather than picking one.

---

## 4. Lecture notes

`lectures/lNN/notes.md`. Start from `_templates/notes.md`.

**Purpose.** A narrative document a student reads *outside* of class, either to prepare or
to recover a session they missed. It carries the full argument and the links. It should read
like a chapter of a good textbook: connected, developed paragraphs that carry the reader
through an argument, not a bulleted outline with sentences attached. It is not a transcript of
the slides, and the slides are not a summary of it. They are two different artifacts with two
different jobs.

**The page title is the first H1**, not YAML frontmatter. Jupyter Book 1 takes the document
title and the navigation label from the leading `# L1 · Title` heading. Do not add a
frontmatter `title:` and expect it to render.

**Required structure**, H2 sections in this order, after the H1 and an opening
`:::{admonition} At a glance` block:

1. `## Why this matters`, narrative motivation opening on the engineering problem, not the
   tool. Two to four developed paragraphs. Ideally a concrete failure.
2. `## Learning objectives`, the one legitimate bullet list in the body, from the module file.
3. Three to six topic sections following the module's Topics, each expanded into connected
   prose rather than named in passing.
4. A limitations or trade-offs section, where appropriate. Not every session needs one, but
   wherever the notes introduce or compare a technology, a candid pros-and-cons discussion
   belongs here: what the tool or method is bad at, its failure modes and surprises, and when
   to reach for something else. When it applies it usually sets up the next arc. L3's "Where
   the relational model pushes back" is the worked model.
5. `## In-class demo`, short orientation, pointing at `demo.ipynb`.
6. `## Summary`, a paragraph, not bullets. Connect forward to the next session.
7. `## Resources`, annotated links, one line each on why it is worth reading.
8. `## Assignment`, a pointer and a deadline, never a copy of the rubric.

**Writing.** Write it as a chapter of a book, not a set of slides rendered as prose. That
means developed, connected paragraphs that carry an argument from one to the next, full
sentences rather than fragments, and enough breadth that a student who missed class can follow
the whole thread from the notes alone. Prefer one idea developed properly over four mentioned
in passing. Open each concept in plain terms, then go deep. Surface the things that will
surprise a reader (the counterintuitive result, the footgun, the name that misleads) rather
than only the tidy summary, because those are what make a chapter worth reading twice. Where it
earns its place, a sentence or two of history or provenance grounds an idea. Use the field's
real names for concepts and link them, so the notes double as an index into the literature. A
full set runs to several thousand words; if a draft feels thin, it usually is.
`lectures/l03/notes.md` is the reference for this depth and voice, and `lectures/l01/` remains
the reference for structure and for the demo and figure mechanics.

**MyST features** enabled in `_config.yml`: `:::{admonition}` blocks with
`:class: tip|warning|note` (via `colon_fence`), `$...$` and `$$...$$` math (via
`dollarmath`), and bare-URL autolinking (via `linkify`). Cross-reference another page with
`[text](../l02/notes.md)`; Sphinx resolves the `.md` path.

**Linking the slide deck** requires a raw HTML anchor, not markdown link syntax:

```html
<a href="../../slides/l01.html">Deck for this session</a>
```

The deck is rendered by MARP outside the Sphinx build, so it is not a known document.
A markdown link would raise `myst.xref_missing`, and CI builds with `--warningiserror`.

Keep code blocks in notes short and illustrative; the runnable version belongs in
`demo.ipynb`.

### Researching and sourcing the notes

**Research first, write second.** Do not draft a set of notes from memory and then look for
links to support it. That process produces confident prose wrapped around claims nobody
checked, and it is how invented statistics enter a syllabus. Start from the module file's
readings, follow them to primary sources, read them, and let what you find shape the
section.

**Verify every link and every number.** Two separate checks, and the second is the one
people skip:

1. The URL resolves. Check the status code.
2. The page actually contains the claim you are citing it for. Fetch it and confirm.

A 200 response is not evidence that a source says what you think it says. When a figure is
widely repeated, find it in the primary source or do not use it. If you cannot verify a
commonly cited number, that absence is itself worth teaching: L1 uses the "less than 10% of
the code is ML code" claim this way, because the number does not appear in the Sculley
paper at all.

Prefer primary sources over summaries, link to a version students can actually open (a
paywalled DOI is a poor reading assignment), and note it in the annotation when a link is
an author's copy or a mirror rather than the publisher's version.

**Write for a practitioner.** For each topic, ask what someone doing this work actually
needs: what decision does this let them make, what will they get wrong, and what does the
failure look like when they do. Prefer that to a survey of everything true about the topic.
The `:::{admonition} What a practitioner should take from this` block after a case study is
the place to make this explicit, and it should contain advice specific enough to act on.

**High-level concept first, then detail.** Open each section with the idea in plain terms,
so a reader who stops after the first paragraph still has a correct mental model. Put the
mechanism, the numbers, and the caveats in the paragraphs and `###` subsections that
follow. A reader should be able to choose their depth without missing the point.

**Use real case studies.** A named incident with verified figures does more work than any
amount of abstract warning, because it gives students something to reason from and to cite.
Good ones share three properties: the failure is documented in a primary source, the causal
mechanism is specific enough to generalize from, and the lesson maps onto something the
student will plausibly build. Anchor each case with a `###` subsection under the concept it
illustrates rather than collecting them in an appendix.

Where a case involves harm to real people, state what the investigations concluded and stop
there. No dramatization, no speculation about motive, and no repeating a popular framing
that the primary sources contradict.

---

## 5. Slide decks

`lectures/lNN/slides.md`. MARP markdown. Start from `_templates/slides.md`.

**Purpose.** Projected during class. It is scaffolding for a talk, not a document. The
prose lives in the notes; if a slide needs a paragraph, that paragraph belongs in the notes
and the slide should carry the pointer instead.

**Required structure:** title → roadmap → content sections → demo marker → recap → next.

**Sessions are 110 minutes.** Budget accordingly, and note that this is long enough that a
deck which merely names topics will run dry well before the room does.

Slides here are deliberately sparse, roughly one idea each, so they run fast: about 1.5
minutes for a fragment slide, three or four for a table, a quote, or a figure you actually
talk through. For 110 minutes with a 20-minute demo that lands around **55 to 70 slides**.
L1 is 63. If a draft comes in at 30, the problem is usually not pacing, it is that the
content is thinner than the session length demands.

**Every deck needs links and figures.** A deck with neither is a deck that cannot be
revisited by a student and cannot be checked by anyone. Put the source link on the slide
that makes the claim, not only in the notes. L1 carries 17 links and 3 figures.

**Weigh technologies, do not just sell them.** Where a session introduces or compares a
technology, the deck should carry the trade-offs too, mirroring the notes' limitations
section: a pros/cons or "when to use, when not" slide, for which a contrast table is ideal.
Not every deck needs one, but a deck that only lists what a tool can do is a sales pitch, not
a lecture.

**Rules:**

- One idea per slide. Six lines maximum, fewer is better.
- Fragments, not sentences. The slide is the pointer; the instructor is the explanation.
- Code on a slide is for reading aloud. More than about ten lines belongs in the demo.
- Frontmatter is fixed: `marp: true`, `theme: course`, `paginate: true`, plus `header`
  (`"06-763 · LNN"`) and `footer` (the course title).
- Slide classes from the shared theme: `<!-- _class: title -->` for the opener,
  `<!-- _class: section -->` for arc dividers, `<!-- _class: demo -->` for the switch to
  live code.
- Speaker notes go in HTML comments and show up in presenter view. Use them for timing
  cues and the things you always forget to say.
- Tables earn their space when they contrast two things (naive versus what we do).
- Final slide points back at the notes path.

`slides.md` is excluded from the Sphinx build in `_config.yml`. It is MARP source, not a
book page, and would render as broken markdown if included.

**Do not** use the deck as the primary artifact and then generate notes from it. That
produces bullet-shaped notes, which are bad notes.

---

## 5b. Figures

Figures live in `lectures/lNN/figures/`, generated by a committed
`figures/make_figures.py` and committed alongside the PNGs it produces.

**Generate, do not copy.** Three reasons, in order of importance. The site is public, so
reproducing a figure from a copyrighted paper is a licensing problem that showing it in a
classroom is not. A figure you can regenerate is a figure you can check, which is the same
argument this course makes about everything else. And computing the claim yourself
routinely changes it: the L1 drift figure was written expecting monotonic decay and the
data showed a seasonal swing instead, which is a better lesson and would have been missed
by pasting someone else's chart.

Where a well-known figure is the point of the discussion, redraw it. `make_figures.py`
redraws the Sculley system diagram as original artwork making the same argument.

**Referencing them.** In notes, use a MyST figure so it gets a caption:

```markdown
```{figure} figures/drift-calibration.png
:alt: describe it for screen readers
:width: 100%

Caption, including where the numbers came from.
```
```

In slides, use MARP image syntax with an explicit width: `![w:1000](figures/x.png)`.

**Path mechanics, which are not obvious.** MARP does *not* inline local images into HTML
output; it emits `<img src="figures/x.png">`. So CI renders each deck into its own
directory, `_build/html/slides/lNN/index.html`, and copies that lecture's PNGs to
`_build/html/slides/lNN/figures/`. The relative path then resolves identically whether you
open the deck from `lectures/lNN/` while writing or from `/slides/lNN/` in production. A CI
step fails the build if any `<img>` in a rendered deck has no corresponding file, because a
missing figure otherwise shows up as a silent broken image in front of a lecture hall.

Raw data for figure generation is cached in `lectures/*/figures/.cache/` and is gitignored.
Do not commit datasets.

---

## 6. Demo notebooks

**Name them `lNN-<topic>.ipynb`**, for example `l01-reproducibility.ipynb`. Never
`demo.ipynb`. Twenty-six files with the same name are ambiguous the moment they leave their
directory, which is exactly what happens when a student downloads three of them or opens
them as browser tabs. The lecture number goes in the filename because the filename is often
the only context that travels with the file.

Optional but expected wherever the module file specifies a live demo. This is the artifact
driven in class, deliberately kept separate from the deck so the deck stays diffable and the
demo stays runnable.

Add the notebook to `_toc.yml` as a `sections:` entry under that lecture's notes, so it is
published and students can actually download it. A notebook the notes reference but never
publish is a promise the site does not keep.

Notebooks must run top to bottom after "Restart and Run All" against the repo's `uv`
environment, use relative paths only, and pin any seed that affects a displayed number.

**Deliberately broken demos are the exception**, and they carry extra obligations. A demo
whose point is that something breaks should break loudly, on purpose, with a markdown cell
saying so, and the defects must be documented in a generator script rather than left to
look like bugs in the `.ipynb` JSON. `l01-reproducibility.ipynb` is the worked example.

If a demo depends on a library version, make it break for **every** student rather than
half of them. L1 integrates a curve twice, once with `np.trapz` (present in NumPy 1.x,
removed in 2.0) and once with `np.trapezoid` (added in 2.0, absent from 1.x), so exactly
one cell fails whichever version they installed, and comparing failures with a neighbour is
the discussion. A defect that only fires on one version teaches only the students who
happened to have it.

Verify the failure modes by actually executing the notebook under each environment you
claim to cover. Do not reason about which cell will fail.

Notebooks are **not executed at build time** (`execute_notebooks: 'off'`), because they may
depend on data that is not in the repo.

---

## 7. Writing style

- **No em-dashes.** Use commas, parentheses, colons, or separate sentences.
- Prose over bullets in the notes. Bullets are correct in slides, in learning objectives,
  and in reference tables like the ones in this file.
- Sentence case for titles and headings.
- Link resources inline with real URLs. Every resource gets one line saying why it is there.
- Second person ("you should be able to") in objectives and assignments. Avoid "we will
  learn" filler.
- Name the engineering context. This course is distinguished from a generic ML course by
  sensor data, simulation output, experimental measurement, and surrogate models. Examples
  should reflect that rather than defaulting to MNIST or the iris dataset.

---

## 8. Building and previewing

**Jupyter Book is pinned to 1.x.** Do not upgrade to 2.x without reading this paragraph.
Jupyter Book 2 (the MyST rewrite) derives page URLs from the file **basename**, so
`lectures/l01/notes.md` and `lectures/l02/notes.md` both become `/notes` and silently
collapse into one page, with no warning and no error. A `slug:` in frontmatter does not
override it. Version 1.x mirrors the directory structure instead, which is what this
layout depends on. 1.x also emits *relative* asset paths, so the site works at the
`/f26-06763/` subpath with no `BASE_URL` configuration.

```bash
# Install the pinned version
pip install "jupyter-book<2"

# Full build, output in _build/html
jupyter-book build .

# Match CI exactly (CI treats warnings as errors)
jupyter-book build . --warningiserror --keep-going

# Force a clean rebuild after moving or renaming files
jupyter-book build . --all

# The whole course as one PDF, into _build/latex/course.pdf
jupyter-book build . --builder pdflatex

# One deck to HTML
npx @marp-team/marp-cli lectures/l01/slides.md -o /tmp/l01.html

# One deck to PDF (needs Chromium). --allow-local-files or the figures drop out
npx @marp-team/marp-cli lectures/l01/slides.md --pdf --allow-local-files -o /tmp/l01.pdf

# Watch a deck while writing it
npx @marp-team/marp-cli -w lectures/l01/slides.md -o /tmp/l01.html
```

CI (`.github/workflows/book.yml`) builds the book, builds the course PDF, renders every
`lectures/*/slides.md` to `_build/html/slides/lNN/index.html` and again to PDF for the
merged `slides.pdf`, checks that no `course/modules/` page leaked into the output, deploys
to Pages on push to `main`, and then verifies that the deploy actually landed. Pull
requests build as a check but do not deploy.

**The PDF.** `--builder pdflatex` produces the whole course as one document, and CI copies
it to `_build/html/course.pdf` so it is downloadable at `/f26-06763/course.pdf`. It is
linked from `index.md` with a raw HTML anchor, for the same reason the slide decks are: the
PDF is not a Sphinx document, so markdown link syntax would fail `myst.xref_missing` under
`--warningiserror`.

Three things about it are load-bearing and live under `latex:` in `_config.yml`:

- **`latex_engine: xelatex`.** These sources carry 34 distinct non-ASCII characters
  (arrows, box drawing, Greek, superscripts, the micro sign). The pdflatex default cannot
  set them without a `\DeclareUnicodeCharacter` per character; xelatex plus GNU FreeFont
  handles all of them. CI installs `texlive-xetex` and `fonts-freefont-otf` for this.
- **`latex_documents.targetname`.** Without it the output is `projectnamenotset.pdf`.
- **`latex_documents.title`.** Jupyter Book copies the top-level `title:` into `\title{}`
  *unescaped* (see `jupyter_book/config.py`, `latex_doc_overrides`), and the `&` in this
  course's title fails the LaTeX run with `Misplaced alignment tab character &`. The
  override supplies an escaped `\&`. Do not "simplify" it away.

Measured on a green run rather than estimated: the whole CI job takes 4m46s, of which the
TeX install is 134s, the PDF build 55s, and the artifact check 13s. The PDF build runs on
pull requests as well as on `main` on purpose: a PDF that only breaks after merge is the
kind of silent failure the rest of this workflow exists to prevent. The check inspects the
artifact rather than the exit code, because a LaTeX run can succeed and still emit
something truncated.

**The slides PDF.** The decks get the same treatment, one document for the whole semester
at `/f26-06763/slides.pdf`, next to `course.pdf` and linked from `index.md` by the same raw
HTML anchor. CI renders each `lectures/*/slides.md` a second time with `--pdf`, then merges
the results with `pypdf`, one bookmark per session. Four things about it are worth knowing
before editing that job:

- **It needs a browser.** MARP has no PDF path that is not headless Chrome. The step uses
  the runner image's `google-chrome-stable` and falls back to fetching Chrome for Testing
  through puppeteer. It deliberately does not `apt-get install chromium`, which on Ubuntu 24
  is a snap wrapper that will not run on a runner.
- **`--allow-local-files` is required.** Without it every `figures/*.png` is silently
  dropped from the PDF, verified by rendering L1 both ways: three figures with the flag,
  zero without. The HTML export needs no such flag, which is exactly why this is easy to
  lose in an edit.
- **Session order is not filename order.** `mp1`/`mp2` sort to the end of a glob but belong
  in Week 8, between L14 and L15, so the merge sorts on an explicit session key.
- **The checks are not decoration.** One page per slide (a deck that renders short is
  caught), the title text of every deck present in the merged text, and at least as many
  embedded images as the deck references figures. Each was tested by breaking it on purpose:
  truncating a deck to ten pages and dropping the local-files flag both fail the job. The
  title probe compares with whitespace removed, because a long title wraps on the rendered
  slide and L17's does.

**Verifying a deploy.** There are three separate things here and they fail independently.

*The page returns 200.* That does not tell you it rendered. Confirm an asset URL from the
page source also returns 200, or screenshot it:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
  --virtual-time-budget=8000 --window-size=1280,900 \
  --screenshot=/tmp/site.png http://kitchingroup.cheme.cmu.edu/f26-06763/
```

*The run is green.* That does not tell you the site updated, and this one is nastier
because it looks conclusive. On 2026-08-06 the build job succeeded, `deploy-pages` timed
out in `deployment_queued`, and the site silently served the previous commit for hours
while the run's build job showed green. It was caught only because somebody fetched a
lecture URL by hand and got a 404.

*So the build stamps itself.* Every build writes `_build/html/build-info.json` containing
the commit it came from, and a `verify` job reads that back **off the live site** after
deploying and fails if it is not this commit. To check by hand at any time, which answers
"what is actually published" rather than "did the last run go green":

```bash
curl -s http://kitchingroup.cheme.cmu.edu/f26-06763/build-info.json
```

Two things in that job are load-bearing and should not be tidied away. It **polls** for
about three minutes, because Pages reports success slightly before the CDN serves the new
build. And it appends a **cache-busting query string**, because without one an edge cache
can keep answering with the previous build, which would make the check pass or fail on
stale data and would defeat its entire purpose.

---

## 9. Adding a lecture

0. **Branch from an up-to-date `main`.** `git fetch origin` first, every time. Cross-
   references to another lecture (`[L9](../l09/notes.md)`) fail the build under
   `--warningiserror` when that page is not on the branch's base, and the tempting local
   fix is to downgrade the link to plain text, which quietly loses it. This has cost a
   closed pull request (#37, branched off an unmerged lecture, redone as #38) and a rebase
   (#47, branched off a `main` that was four merges stale). If you find yourself removing a
   cross-reference to make the build pass, check the base first.
1. Read `course/modules/wkNN.md` for that lecture's block. It is the spec.
2. `mkdir -p lectures/lNN` and copy both templates in.
3. Write `notes.md` first, then compress it into `slides.md`. Notes before slides, always.
4. Add `demo.ipynb` if the module file specifies a live demo.
5. **Add the notes file to `_toc.yml`** under the Lectures part, in session order, as an
   extensionless path: `- file: lectures/lNN/notes`. It will not be built otherwise,
   because `only_build_toc_files` is on.
6. Update the deck link in the notes to `../../slides/lNN.html`.
7. Build locally with `--warningiserror` and confirm it renders before pushing.

`lectures/l01/` is the worked reference. When something here is ambiguous, match L1.

---

## 9b. Optional material

`course/optional/` holds published material that is not part of any session and that no
assignment depends on: method, process, and reading that outlives the syllabus. It is
listed in `_toc.yml` under its own part, so the same publishing rules apply as to anything
else public.

Two constraints specific to it. It **describes** `course/modules/` but never quotes it, so
that instructor-only content stays instructor-only even when the process is the subject.
And it is written from the repository's actual record, meaning the git history, the pull
requests, and the committed figure scripts, rather than from recollection. A claim about
how the course was built is subject to the same two-step verification as any other claim in
section 4: the artifact exists, and it says what you are citing it for.

Add to it when something is worth adding, not on a schedule.
`course/optional/overview.md` lists what is there and what might come.

---

## 10. Things not to do

- Do not add `course/modules/` to `_toc.yml`, and do not disable `only_build_toc_files`.
- Do not upgrade to `jupyter-book>=2`. See section 8.
- Do not restate assignment rubrics in lecture notes. Two copies will disagree.
- Do not swap the dataset a module specifies for a more familiar one.
- Do not write slides first and back-fill the notes.
- Do not commit rendered output (`_build/`), large data files, or `node_modules/`.
- Do not create parallel variants of a file. Edit the canonical one in place.
