# L00 · Full lecture title in sentence case

<!-- The H1 above is the page title and the nav label. Jupyter Book 1 takes the
     title from the first heading, not from YAML frontmatter. -->

:::{admonition} At a glance
:class: tip

- **Session** L00, Week 00 · **Arc** Arc name
- **Slides** <a href="../../slides/l00/">Deck for this session</a>
- **Practice** <a href="../../game/#/l00">Practice module for this session</a>
- **Demo** `demo.ipynb` (walked live in class)
- **Assignment** A00 released / due this session
:::

<!--
STRUCTURE CONTRACT. Keep these H2 sections, in this order, in every set of notes.
Delete a section only if it genuinely does not apply, and say why in one line.
Write it like a chapter of a textbook: developed, connected paragraphs, not a
bulleted outline with sentences attached. Surface the surprises. A full set runs
to several thousand words. lectures/l03/notes.md is the reference for depth and
voice. See CLAUDE.md section 4 for the full convention.

Index the terms as you write, not afterwards: twelve to twenty {index} entries,
one directive under each heading that defines something. lectures/l04/notes.md is
the reference, CLAUDE.md section 4b is the convention, and CI rejects a lecture
that arrives without them.
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

```{index} first term, second term, third term
```
```{index} pair: failure mode; the thing that goes wrong here
```

The body of the notes. Use three to six H2 sections that follow the **Topics** list of the
matching lecture block in `course/modules/wkNN.md`, expanded from bullets into narrative.
One `{index}` directive per line, an untyped line splitting on commas into separate
entries; see CLAUDE.md section 4b, and note that a second line inside one directive is a
build error rather than a second entry.

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

## Where this pushes back

The limits section. Wherever the tool or method has real trade-offs, examine them: what it is
bad at, the failure modes and surprises a practitioner will hit, and when to reach for
something else instead. This is expected, not optional, wherever it applies, and it usually
sets up the next session. Be honest enough to turn the critique on the approach the notes just
recommended. `lectures/l03/notes.md`, "Where the relational model pushes back," is the worked
model. Delete this section only if the subject genuinely has no meaningful trade-offs, and say
so in a line.

## In-class demo

What happens live, and what the student should watch for. State the starting point, the
ending point, and the one or two moments where things are supposed to break. Link the
runnable artifact: `demo.ipynb`.

This section is short. It orients the reader; the notebook carries the detail.

## Summary

A paragraph, not a bullet list. What was the argument, and what should stick after the
details fade. Close the session on its own terms: no pointer to the next one, because the
course releases one lecture at a time and that lecture is not out yet. Backward references
to earlier sessions are fine.

## Resources

Annotated links. One line per entry saying why it is worth the reader's time, because an
unannotated link list is a list nobody opens.

- [Title of primary source](https://example.org). what it is and why it is here.
- [Documentation page](https://example.org). the specific section that matters.

## Assignment

One paragraph pointing at the spec, with the deadline. Full details live in
`course/assignments/aNN.md`; do not restate the rubric here, since two copies of a rubric
will disagree eventually.

## Practice module

The link to this lecture's practice module, which is where the participation credit comes
from. Copy the two lines from an existing lecture, changing only the number: one in the At a
glance block above, one here. A published bank with nothing linking to it is a module no
student can reach.

<a href="../../game/#/l00"><strong>Practice module for this session</strong></a>, about ten
minutes of questions drawn from this session. It runs entirely in your browser, the questions
are selected from your Andrew ID, and it ends by producing a PDF you upload for participation
credit.
