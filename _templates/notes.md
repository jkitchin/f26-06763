# L00 · Full lecture title in sentence case

<!-- The H1 above is the page title and the nav label. Jupyter Book 1 takes the
     title from the first heading, not from YAML frontmatter. -->

:::{admonition} At a glance
:class: tip

- **Session** L00, Week 00 · **Arc** Arc name
- **Slides** <a href="../../slides/l00.html">Deck for this session</a>
- **Demo** `demo.ipynb` (walked live in class)
- **Assignment** A00 released / due this session
:::

<!--
STRUCTURE CONTRACT. Keep these H2 sections, in this order, in every set of notes.
Delete a section only if it genuinely does not apply, and say why in one line.
Prose over bullets in the body. See CLAUDE.md for the full convention.
-->

## Why this matters

Two or three paragraphs of narrative motivation. Open with the engineering problem, not
the tool. The reader should finish this section understanding what breaks in practice if
they do not know this material, ideally through a concrete failure: a sensor that drifted,
a model that could not be rebuilt six months later, a pipeline nobody could trace.

Name the payoff explicitly. This is the section students reread when they ask why the
course spent a session on this.

## Learning objectives

By the end of this session you should be able to:

- Objective lifted from the corresponding `course/modules/wkNN.md` lecture block.
- Keep these verbatim from the module file unless the lecture genuinely changed.
- Three to six objectives, each an observable capability rather than a topic name.

## Main section one

The body of the notes. Use three to six H2 sections that follow the **Topics** list of the
matching lecture block in `course/modules/wkNN.md`, expanded from bullets into narrative.

Write in connected prose. A student who missed class should be able to read this and
follow the argument without the slides. Where a concept has a name in the literature,
use the name and link it, so the notes double as an index into the field.

Code goes in fenced blocks with a language tag, kept short enough to read on a page:

```python
# Illustrative, not the full demo. The runnable version lives in demo.ipynb.
import polars as pl

df = pl.read_parquet("data/sensors.parquet")
```

## Main section two

Continue the argument. Prefer one idea developed properly over four mentioned in passing.

:::{admonition} Common pitfall
:class: warning

Pull the student-facing pitfalls out of the module file's teaching notes and surface them
here, where students will actually read them. Keep instructor-only observations about
class management in `course/modules/`, which is not published.
:::

## In-class demo

What happens live, and what the student should watch for. State the starting point, the
ending point, and the one or two moments where things are supposed to break. Link the
runnable artifact: `demo.ipynb`.

This section is short. It orients the reader; the notebook carries the detail.

## Summary

A paragraph, not a bullet list. What was the argument, and what should stick after the
details fade. Connect forward to the next session so the arc is visible.

## Resources

Annotated links. One line per entry saying why it is worth the reader's time, because an
unannotated link list is a list nobody opens.

- [Title of primary source](https://example.org). what it is and why it is here.
- [Documentation page](https://example.org). the specific section that matters.

## Assignment

One paragraph pointing at the spec, with the deadline. Full details live in
`course/assignments/aNN.md`; do not restate the rubric here, since two copies of a rubric
will disagree eventually.
