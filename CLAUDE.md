# CLAUDE.md — working conventions for this repo

Course materials for **06-763 / 14-763 / 18-763, Systems & Toolchains for AI in
Engineering** (Fall 2026). This file is the contract for how lecture material is
structured, so that notes and slides written weeks apart, by different people or in
different sessions, read as one course.

Read this before creating or editing any lecture material.

---

## 1. What is public

**The repository is private. The rendered site is public.**

The GitHub Pages site at <http://kitchingroup.cheme.cmu.edu/f26-06763/> is world-readable
even though the repo is not. Anything reachable from the `toc:` in `myst.yml` is
published. Anything not listed there stays private.

| Published | Private |
|---|---|
| `index.md` | `course/modules/wkNN.md` (instructor planning, teaching notes, pitfalls) |
| `course/syllabus.md`, `course/schedule.md` | Anything under a `solutions/` directory |
| `lectures/*/notes.md` | Draft material not yet added to the toc |
| `course/assignments/aNN.md` | Grading keys, exam material, student data |
| `course/miniproject.md`, `course/final-project.md` | |
| Rendered slide decks at `/slides/lNN.html` | |

Rules that follow from this:

- **Never add `course/modules/` to the toc.** Those files contain instructor-facing
  teaching notes and class-management observations.
- Never put solutions, grading keys, or anything identifying a student in a published file.
- Student-facing pitfalls *should* be lifted out of the module files into the notes, where
  students will read them. Instructor-facing observations stay in `course/modules/`.
- When adding any file to the toc, confirm it contains nothing instructor-only.

---

## 2. Layout

```
├── CLAUDE.md              this file
├── myst.yml               Jupyter Book 2 config + table of contents
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

**Required structure**, H2 sections in this order:

1. `## Why this matters` — narrative motivation opening on the engineering problem, not the
   tool. Two or three paragraphs. Ideally a concrete failure.
2. `## Learning objectives` — the one legitimate bullet list in the body, from the module file.
3. Three to six topic sections following the module's Topics.
4. `## In-class demo` — short orientation, pointing at `demo.ipynb`.
5. `## Summary` — a paragraph, not bullets. Connect forward to the next session.
6. `## Resources` — annotated links, one line each on why it is worth reading.
7. `## Assignment` — a pointer and a deadline, never a copy of the rubric.

Plus YAML frontmatter (`title`, `short_title`, `subtitle`) and an opening
`:::{admonition} At a glance` block linking the slides, demo, and assignment.

**Writing.** Connected prose, not bullet fragments. A student who missed class should be
able to follow the argument from the notes alone. Prefer one idea developed properly over
four mentioned in passing. Use the field's real names for concepts and link them, so the
notes work as an index into the literature.

**MyST features** available since this is Jupyter Book 2: `:::{admonition}` blocks with
`:class: tip|warning|note`, `$...$` and `$$...$$` math, `[text](path.md)` cross-references
between notes, and fenced code with a language tag. Keep code blocks in notes short and
illustrative; the runnable version belongs in `demo.ipynb`.

---

## 5. Slide decks

`lectures/lNN/slides.md`. MARP markdown. Start from `_templates/slides.md`.

**Purpose.** Projected during class. It is scaffolding for a talk, not a document. The
prose lives in the notes; if a slide needs a paragraph, that paragraph belongs in the notes
and the slide should carry the pointer instead.

**Required structure:** title → roadmap → content sections → demo marker → recap → next.

**Budget** roughly 20 to 30 slides for an 80-minute session, including the section dividers.

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

```bash
# Full book, output in _build/html
jupyter-book build --html

# Live-reloading preview while writing notes
jupyter-book start

# One deck to HTML
npx @marp-team/marp-cli lectures/l01/slides.md -o /tmp/l01.html

# One deck to PDF (needs Chromium; CI only builds HTML)
npx @marp-team/marp-cli lectures/l01/slides.md --pdf -o /tmp/l01.pdf

# Watch a deck while writing it
npx @marp-team/marp-cli -w lectures/l01/slides.md -o /tmp/l01.html
```

CI (`.github/workflows/book.yml`) builds the book, renders every `lectures/*/slides.md` to
`_build/html/slides/lNN.html`, and deploys to Pages on push to `main`. Pull requests build
as a check but do not deploy.

:warning: **`BASE_URL` matters.** Pages serves this site from `/f26-06763/`, not from the
domain root. MyST bakes absolute asset paths at build time, so CI sets
`BASE_URL=/f26-06763`. Without it the HTML loads but every stylesheet and script 404s, and
the site renders as unstyled text with a "Site not loading correctly?" banner.

Do **not** set `BASE_URL` for local work, where the preview is served from the root. If you
want to reproduce the deployed layout exactly:

```bash
BASE_URL=/f26-06763 jupyter-book build --html
python3 -m http.server 8000   # then visit http://localhost:8000/f26-06763/
```

Checking that a deployed page returns HTTP 200 does not tell you it rendered. Confirm an
asset URL from the page source also returns 200.

---

## 9. Adding a lecture

1. Read `course/modules/wkNN.md` for that lecture's block. It is the spec.
2. `mkdir -p lectures/lNN` and copy both templates in.
3. Write `notes.md` first, then compress it into `slides.md`. Notes before slides, always.
4. Add `demo.ipynb` if the module file specifies a live demo.
5. **Add the notes file to `toc:` in `myst.yml`**, under Lectures, in session order. It
   will not appear on the site otherwise.
6. Build locally and confirm it renders before pushing.

`lectures/l01/` is the worked reference. When something here is ambiguous, match L1.

---

## 10. Things not to do

- Do not add `course/modules/` to the toc. See section 1.
- Do not restate assignment rubrics in lecture notes. Two copies will disagree.
- Do not swap the dataset a module specifies for a more familiar one.
- Do not write slides first and back-fill the notes.
- Do not commit rendered output (`_build/`), large data files, or `node_modules/`.
- Do not create parallel variants of a file. Edit the canonical one in place.
