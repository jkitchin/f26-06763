# Scientific and technical writing guide

This guide governs the prose in this course's lecture notes, slide decks, and
assignment write-ups. It has two halves. The first is how to state a scientific
or engineering claim well. The second is the set of machine-writing patterns to
cut, kept from a wider list only where they damage technical prose. `CLAUDE.md`
references this file, so the rules here apply to every student-facing document.

The register is neutral, plain, and precise. Scientific writing does not need a
personality; it needs to be clear enough that a reader can check it. When a rule
here and `CLAUDE.md` disagree, `CLAUDE.md` wins.

---

## Part 1: How to write a claim

### Lead with the claim, then support it

Put the point in the first sentence of a paragraph, then give the evidence and
the caveats. A reader who stops after one sentence should still have the correct
idea. Do not build up to the result through three sentences of preamble.

Before:
> Having considered several storage layouts and their trade-offs, and after
> measuring each on the sensor table, we arrive at a conclusion about columns.

After:
> A columnar layout answered the whole-table average about 80 times faster than
> the row store on the 2.3M-row sensor table.

### Be precise and quantitative

Give numbers with units, and give the uncertainty when you have it. Prefer a
concrete figure to a vague adjective. "Large" is not a measurement.

Before:
> The columnar format was much smaller and a lot faster.

After:
> The columnar file was 5 times smaller (101 MB to 18 MB) and answered the query
> 80 times faster.

Round to the significant figures the measurement supports, and keep the same
precision across a comparison.

### Use one term for one concept

Pick a name for each thing and keep it. Synonym cycling ("the model", then "the
network", then "the estimator" for the same object) reads as varied prose but
makes a reader wonder whether you mean three different things. Define each term
of art on first use, use the field's real name for it, and link that name to a
primary source so the document doubles as an index into the literature.

### Tie every claim to evidence

Every quantitative claim needs a source: either a measurement you made and can
reproduce, or a citation to where the number comes from. Separate what you
measured from what you infer from it. Name the source rather than gesturing at
"studies" or "the literature".

Before:
> Studies show that fitting the scaler on all the data inflates the score.

After:
> Fitting the scaler on all the data before the split inflated test R^2 from
> 0.71 to 0.86 in this experiment; see Kaufman et al. (2012) for the general
> mechanism.

### Calibrate hedging to the evidence

Hedge exactly as much as the evidence warrants. Do not overclaim, and do not
bury a firm result under reflexive qualifiers. "May", "suggests", and "is
consistent with" are precise words; use them when they are true, not as a
nervous default.

Before:
> It could potentially be argued that the split might have some effect on the
> reported accuracy.

After:
> The split determines the reported accuracy: the random split scored 0.15
> higher than the per-unit split on the same model.

### Prefer active voice, with a methods-section exception

Active voice names the agent and is usually shorter and clearer: "we fit the
scaler on the training split". Passive voice is acceptable, and often normal, in
a methods description where the actor is obvious and the object is the point:
"the samples were annealed at 400 C". Use passive on purpose, not by habit.

### Report enough to reproduce

A method is described well enough when a competent reader could repeat it and get
your numbers. For computational work that means the data source and version, the
code version, the seed, and the key parameters. This is the same standard the
course teaches for reproducibility, applied to the writing.

### State limitations honestly

Say what the result does not show, where the method fails, and what you did not
test. A limitation stated plainly is stronger than one a reader has to discover.
Do not dramatize it, and do not bury it.

### Make figures and tables carry their own explanation

Every figure and table needs a caption that says what it shows and where the
numbers came from, so it can be read on its own. Refer to it by number in the
text ("Figure 2"), and state the claim the figure supports rather than leaving
the reader to infer it.

---

## Part 2: Constructions to avoid

These patterns appear far more often in machine-generated text than in careful
human writing. Each one trades precision for the appearance of depth, which is
the opposite of what scientific prose needs. The list is adapted from Wikipedia's
"Signs of AI writing", narrowed to what matters for technical documents.

### Significance inflation

Do not tell the reader that a result is important, pivotal, or a milestone. State
what it is and let its size speak.

Before:
> This benchmark marks a pivotal moment in the evolution of surrogate modeling.

After:
> The surrogate cut the wall-clock cost of one design evaluation from 40 minutes
> to 0.2 seconds.

Watch for: stands as, serves as, is a testament to, a crucial or pivotal role,
underscores its importance, marks a shift, evolving landscape.

### Promotional and hype language

Describe a tool or method by what it does, not with adjectives from a product
page.

Before:
> DuckDB is a powerful, cutting-edge engine that seamlessly delivers blazing-fast
> analytics.

After:
> DuckDB is an in-process SQL engine. It read the Parquet file directly and
> answered the aggregate in 10 ms.

Watch for: powerful, seamless, robust (as a boast), cutting-edge, blazing-fast,
game-changing, rich, vibrant.

### Vague attribution and weasel words

Name the source or cut the claim. "Experts believe" and "it is widely known" are
not evidence.

Before:
> Experts agree that streaming is necessary for modern sensor systems.

After:
> Streaming is necessary when a result must be produced within seconds of the
> reading that triggers it; a nightly batch job cannot meet that latency.

### Superficial analysis with -ing tails

Do not append a present-participle clause that restates the sentence as if adding
insight.

Before:
> We standardized the features, ensuring robust performance and highlighting the
> importance of preprocessing.

After:
> We standardized the features on the training split. Test error fell by 8%.

### The anaphoric evaluative coda

A plain sentence followed by a clause that reframes it as the important takeaway
instead of adding anything. Cut it: the sentence before it already made the
point, or replace the coda with the concrete claim it gestures at.

Before:
> The gap between the two runs is tiny. That is the point worth sitting with.

After:
> The gap between the two runs is tiny (0.786 versus 0.785), so logging the seed
> is the only way either number is reconstructible.

The family includes "that is the point", "this is the lesson", "and that
distinction matters", "worth keeping in mind", "X is what makes Y", and "the word
X is load-bearing". None are ungrammatical; the problem is the reflex.

### Negative parallelism and tailing negations

"Not X but Y", "not merely A, it is B", and clipped negations tacked on the end
("no guessing", "not a headline"). Write the positive statement.

Before:
> Parquet is not just a file format, it is a query engine.

After:
> Parquet is a file format. DuckDB is the engine that queries it.

### Rule-of-three padding

Do not force ideas into groups of three for rhythm. Keep the items that are true.

Before:
> The pipeline is fast, scalable, and elegant.

After:
> The pipeline processes the month of data in under a minute.

### Elegant variation

Covered in Part 1: one term per concept. Do not cycle synonyms for a defined
object.

### False ranges

"From X to Y" only works when X and Y sit on a real scale.

Before:
> The course takes you from raw bytes to deep insight.

After:
> The course covers storage, feature engineering, and model evaluation.

### Copula avoidance

Use "is", "are", and "has". Do not reach for "serves as", "stands as", or
"boasts" to dodge a plain verb.

Before:
> MLflow serves as the tracker and boasts a local store.

After:
> MLflow is the tracker. It has a local store, a single SQLite file.

### Filler phrases

Cut them. "In order to" is "to". "Due to the fact that" is "because". "It is
important to note that the data shows" is "the data shows".

### Persuasive authority tropes

Drop "the real question is", "at its core", "fundamentally", and "what really
matters". They promise depth and deliver a restated ordinary point.

### Signposting

Do the thing instead of announcing it. Delete "let's dive into", "here is what
you need to know", and "in this section we will".

### Manufactured drama and staccato

Do not stack short fragments to force emphasis. One short sentence for emphasis
is fine; a run of them reads as engineered.

### Aphorism formulas

Do not turn a claim into a reusable slogan ("data is the new oil", "X is the
language of Y"). State the concrete claim.

### Mechanical style tells

- No em dashes or en dashes. Use commas, colons, parentheses, or separate
  sentences.
- Straight quotes, not curly quotes.
- Sentence case for headings, not title case.
- No emoji in headings or bullets.
- Bold only a genuine key term at first definition, not for mechanical emphasis.
- Avoid inline-header bullet lists where every item starts with a bold word and a
  colon; write the sentence instead.
- No generic upbeat conclusion. End on the last concrete point.

---

## When these rules do not apply

Do not gut legitimate prose chasing tells. The following are not, on their own,
signs of machine writing:

- Formal or technical vocabulary. The field's real terms are correct.
- Passive voice in a methods description where the actor is obvious.
- A single short sentence used for emphasis.
- Consistent, polished formatting.
- One transition word, or one hedge, used where it is true.

When in doubt, look for a cluster of tells, not one in isolation, and keep the
specific, verifiable detail that marks real writing.

---

## Reference

The avoid-list is adapted from
[Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing),
maintained by WikiProject AI Cleanup, and narrowed to scientific and technical
prose. The positive principles follow standard guidance on scientific writing:
lead with the claim, quantify, cite, and report enough to reproduce.
