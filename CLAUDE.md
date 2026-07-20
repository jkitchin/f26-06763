# CLAUDE.md — working conventions for this repo

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
to recover a session they missed. It carries the full argument and the links. It is not a
transcript of the slides, and the slides are not a summary of it. They are two different
artifacts with two different jobs.

**The page title is the first H1**, not YAML frontmatter. Jupyter Book 1 takes the document
title and the navigation label from the leading `# L1 · Title` heading. Do not add a
frontmatter `title:` and expect it to render.

**Required structure**, H2 sections in this order, after the H1 and an opening
`:::{admonition} At a glance` block:

1. `## Why this matters` — narrative motivation opening on the engineering problem, not the
   tool. Two or three paragraphs. Ideally a concrete failure.
2. `## Learning objectives` — the one legitimate bullet list in the body, from the module file.
3. Three to six topic sections following the module's Topics.
4. `## In-class demo` — short orientation, pointing at `demo.ipynb`.
5. `## Summary` — a paragraph, not bullets. Connect forward to the next session.
6. `## Resources` — annotated links, one line each on why it is worth reading.
7. `## Assignment` — a pointer and a deadline, never a copy of the rubric.

**Writing.** Connected prose, not bullet fragments. A student who missed class should be
able to follow the argument from the notes alone. Prefer one idea developed properly over
four mentioned in passing. Use the field's real names for concepts and link them, so the
notes work as an index into the literature.

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

---

## 5. Slide decks

`lectures/lNN/slides.md`. MARP markdown. Start from `_templates/slides.md`.

**Purpose.** Projected during class. It is scaffolding for a talk, not a document. The
prose lives in the notes; if a slide needs a paragraph, that paragraph belongs in the notes
and the slide should carry the pointer instead.

**Required structure:** title → roadmap → content sections → demo marker → recap → next.

**Budget** roughly 20 to 30 slides for an 80-minute session, including section dividers.

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

## 6. Demo notebooks

`lectures/lNN/demo.ipynb`, optional but expected wherever the module file specifies a live
demo. This is the artifact driven in class, deliberately kept separate from the deck so the
deck stays diffable and the demo stays runnable.

Notebooks must run top to bottom after "Restart and Run All" against the repo's `uv`
environment, use relative paths only, and pin any seed that affects a displayed number. A
demo whose point is that something *breaks* should break loudly and on purpose, with a
markdown cell saying so.

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

# One deck to HTML
npx @marp-team/marp-cli lectures/l01/slides.md -o /tmp/l01.html

# One deck to PDF (needs Chromium; CI only builds HTML)
npx @marp-team/marp-cli lectures/l01/slides.md --pdf -o /tmp/l01.pdf

# Watch a deck while writing it
npx @marp-team/marp-cli -w lectures/l01/slides.md -o /tmp/l01.html
```

CI (`.github/workflows/book.yml`) builds the book, renders every `lectures/*/slides.md` to
`_build/html/slides/lNN.html`, checks that no `course/modules/` page leaked into the
output, and deploys to Pages on push to `main`. Pull requests build as a check but do not
deploy.

**Verifying a deploy.** Checking that a page returns HTTP 200 does not tell you it
rendered. Confirm an asset URL from the page source also returns 200, or screenshot it:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
  --virtual-time-budget=8000 --window-size=1280,900 \
  --screenshot=/tmp/site.png http://kitchingroup.cheme.cmu.edu/f26-06763/
```

---

## 9. Adding a lecture

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

## 10. Things not to do

- Do not add `course/modules/` to `_toc.yml`, and do not disable `only_build_toc_files`.
- Do not upgrade to `jupyter-book>=2`. See section 8.
- Do not restate assignment rubrics in lecture notes. Two copies will disagree.
- Do not swap the dataset a module specifies for a more familiar one.
- Do not write slides first and back-fill the notes.
- Do not commit rendered output (`_build/`), large data files, or `node_modules/`.
- Do not create parallel variants of a file. Edit the canonical one in place.
