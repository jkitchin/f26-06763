---
marp: true
theme: course
paginate: true
header: "06-763 · L00"
footer: "Systems and Toolchains for AI Engineers"
---

<!--
STRUCTURE CONTRACT for decks. Keep this slide order:
  title -> roadmap -> content -> demo marker -> recap -> next
Budget roughly 55-70 slides for a 110-minute session (see CLAUDE.md section 5).
Slides carry pointers; the notes carry the prose. Never paste paragraphs here.
Where the session introduces or compares a technology, include a trade-offs
slide (pros/cons or "when to use, when not"); a contrast table is ideal.
See CLAUDE.md for the full convention.
-->

<!-- _class: title -->

# L00 · Lecture title

## Week 00 · Arc name

**Systems and Toolchains for AI Engineers**

---

## Roadmap

1. First movement
2. Second movement
3. Live demo
4. What this buys you

<!-- Speaker notes go in HTML comments and are visible in presenter view.
     Use them for timing cues and the things you always forget to say. -->

---

## One idea per slide

- Six lines maximum, and fewer is better
- Fragments, not sentences
- The slide is the pointer; you are the explanation

---

## Show, do not tell

```python
uv init && uv add polars mlflow
uv run python -m airquality.train --seed 0
```

Code on slides is for reading aloud. Anything longer than about ten lines
belongs in the demo notebook.

---

<!-- _class: section -->

# Second movement

---

## Contrast slides earn their space

| Naive | What we do |
|---|---|
| `pip install -r requirements.txt` | `uv sync` against a lockfile |
| "works on my machine" | pinned interpreter, deterministic rebuild |

---

<!-- _class: demo -->

# Demo

## `demo.ipynb`

Watch for the moment the rebuild fails.

---

## Recap

- The claim you want them to leave with
- The second claim
- The thing that will be on the assignment

---

## Next

**Reading** linked at the end of the notes
**Assignment** A00, due next week
**Next session** L01, what it covers

Notes for this lecture: `lectures/l00/notes.md`
