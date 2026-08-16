# L15 · Foundation models and LLMs at a systems level: architecture, tokenization, embeddings

:::{admonition} At a glance
:class: tip

- **Session** L15, Week 9 · **Arc** LLM & agentic engineering
- **Slides** <a href="../../slides/l15/">Deck for this session</a>
- **Demo** [`l15-tokens-embeddings.ipynb`](l15-tokens-embeddings.ipynb), what a datasheet costs and what a log book clusters into
- **Assignment** A8 released this session
:::

## Why this matters

Here is a string from a pump datasheet: `±0.05 mm`. Eight characters, one tolerance,
one number. Here is what the model receives when you send it:

```
'±'  '0'  '.'  '05'  ' mm'
```

Five tokens, and not one of them is `0.05`. The number the specification is about does
not exist anywhere in the model's input. It exists as three fragments that the model has
to reassemble, and the fragment `05` is the same fragment it would see in `2005`, in
`0.5`, and in a serial number. This is not a corner case. It is what happens to almost
every quantity in almost every engineering document, and it is the reason that an
extraction pipeline which handles prose beautifully starts quietly returning `2.5` where
the datasheet said `25.0`.

The second thing that happens to that datasheet is that it costs different amounts
depending on who you ask. The two-page pump specification in these notes is 2,365
characters. `tiktoken`, the tokenizer most engineers reach for because it is the one that
installs locally, counts **776 tokens**. Claude Haiku 4.5 counts **924**. Claude Opus 5
counts **1,263**, which is **63% more than the local estimate and 37% more than another
model from the same vendor**. Scale that to a real corpus and the difference between the
number you planned with and the number you were billed for is not a rounding error; on the
146-page report these notes measure, estimating with `tiktoken` understates the Opus 5
input bill by **31%**.

Both of those failures come from the same place: not knowing what the model actually
consumes. That is what this session is about. An LLM is not a black box that reads
English, it is a next-token predictor over a fixed vocabulary of subword fragments, and
almost every engineering constraint you will meet in the next four weeks (what fits, what
it costs, how long it takes, what it gets wrong about numbers) falls out of that one
sentence. The point of building the mental model is not theoretical interest. It is that
once you have it, the failures become predictable in advance instead of surprising in
production.

## Learning objectives

By the end of this session you should be able to:

- Build a correct-enough mental model of a decoder-only LLM to reason about failure modes
  (truncation, hallucination, context limits) rather than treat it as a black box.
- Understand tokenization concretely: subword units, why "10.5 MPa" or "SS316L" may split
  oddly, and how token counts drive cost/latency.
- Understand embeddings as vectors and use cosine similarity to cluster/retrieve
  engineering text.

## The shape of a decoder-only model

```{index} decoder-only transformer, self-attention, feed-forward network, foundation model
```

At the level that matters for engineering, a modern LLM is five stages in a loop.

**Tokenize.** The input string is cut into subword units drawn from a fixed vocabulary,
typically 50,000 to 200,000 entries. This is the stage that will get its own section
below, because it is where engineering text goes wrong.

**Embed and position.** Each token id indexes a row of a learned matrix, turning a
sequence of integers into a sequence of vectors. Position information is injected here
(originally as a sinusoidal encoding, and in many current models as a rotary transformation
of the query and key vectors), because everything downstream is otherwise order-blind.

**Stack of blocks.** Each block does two things. **Self-attention** lets every position
look at every earlier position: each token emits a *query*, every token exposes a *key* and
a *value*, the query is compared against the keys to produce weights, and the values are
mixed in those proportions. This is the mechanism that lets "it" three sentences later
refer to the pump. Then a **feed-forward network** transforms each position independently.
Both are wrapped in residual connections and normalization. Dozens to over a hundred of
these blocks are stacked.

**Logits.** The final vector at the last position is multiplied by an output matrix to
produce one real number per vocabulary entry. A softmax turns those into a probability
distribution over "what comes next."

**Sample and repeat.** One token is drawn from that distribution, appended to the
sequence, and the whole thing runs again. This is what *autoregressive* means, and it is
worth pausing on: generating 500 tokens is 500 forward passes, in strict sequence, and no
amount of hardware makes step 200 start before step 199 finishes.

That last point is the reason the latency measurement later in these notes comes out the
way it does, and it is the most useful structural fact in the whole architecture. Reading
the input is a *parallel* operation: all of it can be processed at once. Writing the output
is a *serial* one.

:::{admonition} You have already built the pieces
:class: note

Nothing in that stack is new to this course. [L11](../l11/notes.md) covered tensors,
matrix multiplication on a GPU, autodiff, and why batch dimensions exist. A transformer
block is those operations arranged in a particular order and repeated. What is new is the
scale and the training objective, not the machinery.
:::

The term **foundation model** comes from Bommasani et al.'s 2021 report, and it names the
economic fact rather than the architecture: a single model is trained once on broad data
at enormous cost and then adapted to many downstream tasks. For you, the consequence is
that you are not going to train one. You are going to *call* one, which makes the
interface, the budget, and the failure modes your engineering problem rather than the
architecture.

## Prediction, fluency, and hallucination

```{index} hallucination
```
```{index} pair: failure mode; confident hallucination
```

The model computes a probability distribution over the next token. That single fact
explains both why the output reads so well and why it is confidently wrong, and you can
watch it happen.

```{figure} figures/next-token.png
:alt: Four panels. First, a question whose answer is in the prompt, showing one token at probability 1.000 and zero bits of entropy. Second, the same question about a part number that does not exist, showing probability spread across the digits 1, 2, 10, 3, 16 and 2.22 bits. Third, the same gap with NOT FOUND permitted, collapsing back to one token at 1.000 and zero bits. Fourth, grouped bars showing how temperature and top-p reshape a measured distribution.
:width: 100%

The top-20 next-token probabilities returned by `gpt-4.1-mini`, for four prompts about the
same pump. Generated by `figures/make_figures.py`.
```

Ask for a value that is present in the prompt and the distribution collapses: the token
`10` arrives with probability **1.000** and an entropy of **0.00 bits**. The model is not
reasoning about pressure; it is completing a pattern that the context has made
overwhelming.

Now ask the same question about `Kessler-Voss KV-7710/B`, a pump that does not exist. The
distribution does not become uniform, and it does not contain any signal that means "I
have never heard of this." It puts **0.405** on the token `1`, **0.358** on `2`, and
spreads the rest over `10`, `3`, `16`, `6`, `4`. Entropy rises to **2.22 bits**. Read that
carefully, because it is the whole hallucination story in one measurement: the model is
*less* certain, but it is still emitting a digit. There is no token in its vocabulary that
means "not in the source," so the probability mass that ought to go there has nowhere to go
except onto plausible numbers.

Give it that token and the problem disappears. The third panel is the same missing value,
with one clause added to the prompt: *or with the words NOT FOUND if the answer is not in
the text below*. The distribution collapses again, this time onto `NOT` at probability
**1.000**, entropy **0.00 bits**. The escape hatch costs eleven words and it is the single
highest-leverage line in an extraction prompt.

:::{admonition} What a practitioner should take from this
:class: tip

Hallucination is not the model lying. It is the model doing exactly what it was trained to
do, in a situation where the correct answer is not expressible in its output space.

The three fixes follow directly, and you will use all of them in A8. **Put the answer in
the context**, because grounded questions collapse to near-zero entropy. **Give it a way
to say no**, explicitly, in the prompt and in the schema, so that a null is a legal answer
rather than an impossible one. **Do not rely on confidence as a detector**: entropy went
from 0.00 to 2.22 bits between a right answer and a fabricated one, which is a real signal
but nowhere near a clean one, and you do not get to see it at all on most APIs.
:::

### The two knobs, and what they cannot do

```{index} temperature, top-p sampling
```

**Temperature** divides the logits before the softmax. Below 1 it sharpens the
distribution toward the leading candidate; above 1 it flattens it. **Top-p** (nucleus
sampling) truncates instead: sort candidates by probability, keep the smallest set whose
mass exceeds *p*, renormalize, and sample only from those. The fourth panel of the figure
applies both to a measured distribution.

The important thing about both is what they are *not*. Neither adds information. The
distribution has already been computed by the time either knob applies, and every
candidate the model was going to consider is already in it. Lowering the temperature to
zero does not make the model more accurate; it makes it more repeatable at whatever
accuracy it had. For extraction, that repeatability is what you want, which is why A8 asks
for a low temperature.

:::{admonition} Common pitfall
:class: warning

**"It worked once" is not a passing test, and low temperature does not make it one.**

Sending the *same* prompt to `gpt-4.1-mini` five times, and reading the returned
distribution rather than the sampled token, the leading candidate's probability ranged from
**0.626 to 0.858** and the entropy from **0.71 to 1.26 bits**. The prompt was byte
identical. The distribution itself was not reproducible, before any sampling happened.

Providers batch requests, run in reduced precision, and route across heterogeneous
hardware, and floating-point addition is not associative. You should expect run-to-run
variation as a property of the platform, not as a bug you can configure away. Evaluate on a
set, not on an anecdote, and re-run the set when you change anything.
:::

## Tokenization, and what it does to engineering text

```{index} tokenization, byte-pair encoding
```

The vocabulary is learned. Nobody sat down and decided that ` MP` should be a token and
`MPa` should not.

The dominant scheme is **byte-pair encoding**, an idea Philip Gage published in 1994 as a
data-compression algorithm and Sennrich, Haddow and Birch repurposed in 2016 to give
neural translation systems an open vocabulary. Training it is almost embarrassingly simple:
start with the raw bytes as your vocabulary, find the most frequent adjacent pair in the
corpus, merge it into a new symbol, and repeat once per vocabulary entry you want, which in
practice is tens or hundreds of thousands of times. The merge list is then frozen and
shipped with the model. Encoding new text means replaying those merges greedily.

Everything that follows is a consequence of that corpus being mostly ordinary web text.
Fragments that are common in English get merged early and become single tokens. Fragments
that are common in *your* documents and rare on the web never get merged at all.

```{figure} figures/tokenization.png
:alt: Three panels. Left, eight engineering strings drawn as sequences of coloured token boxes, showing 10.5 MPa as five tokens and P/N 4L-2200-XG as ten. Middle, a horizontal bar chart of characters per token for five kinds of text, from 4.82 for technical prose down to 2.35 for an alarm table. Right, four bars for the token count of the same datasheet under cl100k_base, o200k_base, Claude Haiku 4.5, and Claude Opus 5, at 776, 770, 924, and 1,263.
:width: 100%

The same characters, three different ways of looking at what they cost. Generated by
`figures/make_figures.py`.
```

### What breaks, specifically

**Units detach from their numbers.** `10.5 MPa` is five tokens: `10`, `.`, `5`, ` MP`,
`a`. The unit is split across a token that also begins "MP3" and "MPG", and a bare `a`.

**Numbers are cut in fixed-width digit groups, not at their real boundaries.** `1500 rpm`
tokenizes as `150`, `0`, ` rpm`. The model never sees `1500` as a unit; it sees a
three-digit chunk followed by a stray zero. `4140` in `AISI 4140` becomes `414` + `0`, and
`2200` becomes `220` + `0`. If you have wondered why LLMs are unreliable at arithmetic on
long numbers, this is a large part of the answer: the representation itself does not
respect place value.

**Part numbers shatter.** `P/N 4L-2200-XG` is 14 characters and **10 tokens**, a rate of
1.4 characters per token against 4.8 for prose. Identifiers are the densest and most
expensive thing in your corpus and they are also the thing you most need extracted exactly.

**Some characters are not even one token.** `Ø25` under `cl100k_base` is three tokens, and
the first two are *halves of a character*: `Ø` is two bytes in UTF-8 and the encoder had no
merge for that pair, so it emitted each byte separately. Neither one decodes to a printable
character on its own. Under the newer `o200k_base` the same string is two tokens. Nothing
about your document changed.

**Case and spacing matter.** `bearing` is one token. `Bearing` is two (`B` + `earing`).
`BEARING` is two. Maintenance logs written in capitals, which is most of them, cost more
than the same words in lower case, and the model sees different symbols.

### What that adds up to per page

Averaged over a document, the effect shows up as characters per token, which is the number
worth carrying in your head:

| kind of text | characters per token |
|---|---|
| technical prose | 4.82 |
| free-text maintenance log | 3.82 |
| pump datasheet | 3.05 |
| Python source | 2.56 |
| an alarm table flattened out of a PDF | 2.35 |

A page of a datasheet costs about **1.6 times** as many tokens as a page of prose with the
same number of characters, and a page of tabular data costs about **twice**. Any budget
you build from a general "four characters per token" rule of thumb will be wrong in the
expensive direction for exactly the documents this course cares about.

### Count, do not estimate

The measured spread across tokenizers is the practical lesson. On the same 2,365-character
datasheet:

| tokenizer | tokens | against `cl100k_base` |
|---|---|---|
| `cl100k_base` (OpenAI) | 776 | baseline |
| `o200k_base` (OpenAI) | 770 | −1% |
| Claude Haiku 4.5 | 924 | +19% |
| Claude Opus 5 | 1,263 | **+63%** |

People expect the vendors to differ. The gap that catches them is the last row against the
one above it. **Two models from the same provider disagree by 37% on the same text**,
because Anthropic changed tokenizer within its own model line and documents the change as
roughly 30% more tokens for the same input. "Use the provider's tokenizer" is not a
sufficient rule. Use the *model's*, for the exact model id you are going to call, and
re-measure when you change model.

Mechanically, the two providers make opposite trade-offs and you should know both.
OpenAI's `tiktoken` is a local library: counting is free, offline, instantaneous, and
exact for their models. Anthropic publishes no offline tokenizer and instead exposes a
[token counting endpoint](https://platform.claude.com/docs/en/build-with-claude/token-counting),
`POST /v1/messages/count_tokens`, which is free to call but is a network round trip,
consumes its own rate limit, and is documented as an *estimate* that may differ slightly
from what you are billed. Neither is wrong; they are different points on a
latency-versus-fidelity curve. What is always wrong is using one vendor's local library to
predict another vendor's bill.

:::{admonition} Common pitfall
:class: warning

Anthropic's own documentation puts it bluntly, and it is worth quoting because it is the
mistake in this section that costs real money: `tiktoken` "is OpenAI's tokenizer. It
undercounts Claude tokens by ~15–20% on typical text, and by much more on code or
non-English input."

Measured on the 146-page report in the next section: `tiktoken` says 87,556 tokens, Claude
Opus 5 bills 126,452. The estimate is **31% low**. On a corpus of ten thousand documents,
that is the difference between a budget that holds and one that does not.
:::

## The context window as a budget

```{index} context window
```

The context window is the total number of tokens a model can attend to at once, and the
budget is shared: **tokens in plus tokens out**. If you send 190,000 tokens to a model
with a 200,000-token window, you have left room for 10,000 tokens of answer, whatever you
set `max_tokens` to. On the providers this course uses, exceeding the window is a
request-level error rather than a silent truncation, which is the merciful behaviour, and
you should confirm that for any provider you add. The silent truncation that
actually bites you happens earlier, in your own code: a chunker with an off-by-one, a PDF
extractor that gives up on page 40, a `[:8000]` somebody added while debugging and never
removed.

Windows are now large enough that "will it fit" is rarely the binding question. What
replaced it is "what does each question cost, and which model can I afford to route to."

```{figure} figures/context-cost.png
:alt: Three panels. Left, cumulative tokens across 146 pages of a NASA report, drawn twice, once as tiktoken counts it reaching 88 thousand and once as Claude Opus 5 bills it reaching 126 thousand, against a dashed line at the 200 thousand token Haiku context window. Middle, log-log cost per call against input tokens for two models with and without prompt caching, marking 63 cents per question for this report on Opus 5. Right, measured wall-clock latency against token count, with input length nearly flat and output length rising steeply to 22 seconds.
:width: 100%

One real document, measured three ways: what it counts as, what it costs, and what it does
to latency. Generated by `figures/make_figures.py`.
```

The document is NASA RP-1218, Brooks, Pope and Marcolini's 1989 report on airfoil
self-noise. This course has used the dataset from it twice already, in
[L9](../l09/notes.md) and [L13](../l13/notes.md); this is the report itself. It is 146
pages and 248,947 characters of extracted text, and it is a 1989 scan, so what the
extractor returns is OCR output complete with figure axis labels, running heads, and
garbled fragments like `oi` and `TEj LE`. That is not a defect in the demonstration, it is
the realistic case: **you pay tokens for whatever your extractor produces, noise
included**. It comes out at 2.84 characters per token, more token-dense than the datasheet
at 3.05, which is what OCR noise and equations do to a document.

Three numbers follow, and each drives a different decision:

**It counts as 126,452 tokens on Claude Opus 5** and 100,448 on Claude Haiku 4.5. Against a
1M-token window that is 13%, so it fits comfortably. Against Haiku's 200K window it is
half, so it fits exactly once with room for a conversation and no more. The constraint is
not the document, it is the document plus everything else you wanted in the prompt.

**It costs $0.63 per question** at Opus 5's $5 per million input tokens, every time you
re-send it. Ask fifty questions over a working session and you have spent $31 on one
report. Prompt caching, which most providers now offer, cuts the repeat reads to about a
tenth, which is the difference between a workflow and a line item. The same document on
Haiku 4.5 is $0.10 per question, which is what "route the easy subtasks to a smaller
model" means in practice.

**It barely affects latency at all**, and this is the measurement that most often reverses
students' intuition.

### Input is cheap in time; output is not

The right-hand panel is a real sweep against Claude Haiku 4.5, three repeats per point,
with the individual repeats drawn as faint dots so you can see the scatter honestly.

| what varied | from | to | median latency |
|---|---|---|---|
| input tokens (`max_tokens` = 16) | 769 | 100,456 | 0.85 s → 1.21 s |
| output tokens (39-token prompt) | 16 | 2,048 | 1.00 s → 22.55 s |

A **130-fold** increase in input added about **0.4 seconds**, which is inside the
run-to-run scatter. A **128-fold** increase in output added **22 seconds**. Generation ran
at roughly 90 tokens per second and that rate is set by the serial loop described earlier,
not by anything you can pay to avoid.

Put crudely: **one output token costs about as much wall-clock time as a thousand input
tokens.** So the instinct to trim the document you paste in, to make the call faster,
optimizes the wrong term. Trimming the input saves money. Trimming what you ask
the model to *write* saves time. For an extraction task that returns a small JSON object,
you are almost entirely paying for input tokens in dollars and almost entirely paying for
output tokens in seconds, and those are two different budgets with two different fixes.

:::{admonition} What a practitioner should take from this
:class: tip

Before you build anything, write down three numbers for one representative document:
tokens under the model you will call, dollars per call, and seconds per call. All three
are one API call away and none of them can be guessed reliably.

Then decide where the loop is. If the same large context is queried repeatedly, prompt
caching is the first optimization and it is nearly free. If each document is seen once,
caching does nothing and a smaller model is the lever. If a human is waiting, cap
`max_tokens` and ask for the smallest output that answers the question, because that is
the only term that moves the clock.
:::

## Embeddings

An embedding is a vector that stands in for a piece of text, arranged so that texts with
similar meaning land near each other. That is the whole idea, and the reason it earns a
section is that for a large class of engineering problems it is a better tool than an LLM
call: cheaper by orders of magnitude, faster, deterministic, and easy to index.

### Two different things are called embeddings

```{index} embedding
```
```{index} single: embedding; token embedding
```
```{index} single: embedding; sentence embedding
```

Inside the model, the first stage after tokenization is an embedding lookup: a table with
one row per vocabulary entry. Those are **token embeddings**, and there is one per
fragment, not one per word or per sentence. `SS316L` has three of them.

What you get from an embeddings API is a **sentence or document embedding**: one vector
for the whole input, produced by a separate model trained specifically so that distance
between vectors means semantic similarity. Reimers and Gurevych's 2019 Sentence-BERT paper
is the standard reference for why the distinction matters. Averaging the token embeddings
of a generative model is not a substitute; those vectors were optimized to predict the
next token, not to make cosine distance meaningful, and they perform badly at it.

Providers differ here in a way worth knowing. Anthropic does not train an embedding model
at all and its documentation points you at
[third-party providers](https://platform.claude.com/docs/en/build-with-claude/embeddings),
recommending Voyage AI. OpenAI ships `text-embedding-3-small` (1,536 dimensions) and
`text-embedding-3-large` (3,072). Voyage's current models default to 1,024. The measurements
below use `text-embedding-3-small`, and every claim in them is a property of that model
rather than of embeddings in general.

### Cosine similarity, and what it buys you

```{index} cosine similarity, TF-IDF
```

Vectors are compared by the cosine of the angle between them, which is the dot product of
the unit-normalized vectors. Most embedding APIs return vectors already normalized, in
which case cosine similarity and dot product are the same computation and the second is
faster. Cosine ranges from −1 to 1, though in practice the interesting range for one
model on one corpus is much narrower, and the absolute values are not comparable across
models.

The demonstration is 34 free-text maintenance log entries, written the way maintenance
logs are actually written: abbreviations, missing articles, inconsistent tag formats.

```{figure} figures/embeddings.png
:alt: Three panels. Left, a 34 by 34 cosine similarity heatmap with visible bright blocks along the diagonal corresponding to labelled clusters. Middle, a scatter of embedding cosine against TF-IDF cosine for every pair, with same-event pairs in green well above the lexical baseline and one at zero lexical overlap. Right, a two-dimensional PCA projection of the same vectors coloured by cluster.
:width: 100%

Thirty-four maintenance log entries, embedded and compared. The middle panel is the
argument for embeddings: the vertical spread at the left edge is pairs with no words in
common. Generated by `figures/make_figures.py`.
```

The single most convincing pair in the whole set:

> `brg vibration p101 high at startup`
> `Operator reports growling from the drive end bearing on P-101`

These describe the same event. Their **TF-IDF cosine is 0.000**: after tokenizing on word
boundaries, they share not one term. Any keyword search, any `LIKE '%bearing%'`, any
lexical index misses this pair completely. Their **embedding cosine is 0.532**, comfortably
above the 0.364 median for unrelated pairs. That gap is the entire value proposition, and
it is why the vector store previewed in Week 2 exists.

### When embeddings beat an LLM call

Deduplicating those 34 entries pairwise with an LLM means 561 calls. At roughly a
thousand input tokens and a short answer each, that is on the order of a dollar and several
minutes, and the answers are not reproducible. Embedding all 34 entries was **one call, 455
tokens, and a fraction of a cent**, after which every pairwise comparison is a dot product:
a 34 × 1,536 matrix times its own transpose, microseconds. Scaled to a hundred thousand
records the LLM approach is arithmetically impossible, while the embedding approach is a
single matrix multiply or an approximate-nearest-neighbour index.

The rule of thumb: **use embeddings when the question is "which of these are alike," and an
LLM when the question is "what does this one say."** Deduplication, clustering, near-
duplicate detection, and retrieval are the first kind. Extraction, summarization, and
judgment are the second. Most real pipelines use embeddings to narrow a corpus from
millions to tens, and then spend LLM tokens only on the tens. That pipeline is
retrieval-augmented generation, the subject of [L17](../l17/notes.md) in two sessions'
time, and this is the half of it you can build today.

### Dimensionality is a storage decision

Vector size is not free. A million chunks at 1,536 float32 dimensions is 6 GB before any
index overhead, which is a database decision rather than a modelling one.

Both OpenAI's v3 models and Voyage's current models are trained so the vector can be
**truncated from the end** and renormalized, a technique known as Matryoshka
representation. Measured on this corpus, keeping the leading *n* dimensions and asking
whether each entry's nearest neighbour is unchanged:

| dimensions kept | bytes per vector | nearest neighbour unchanged |
|---|---|---|
| 1,536 | 6,144 | 100% |
| 1,024 | 4,096 | 97.1% |
| 512 | 2,048 | 100% |
| 256 | 1,024 | 85.3% |
| 128 | 512 | 82.4% |
| 64 | 256 | 67.6% |

A third of the storage for no measurable loss is a good trade and you should take it. But
look at the 1,024 row, which does *worse* than the 512 row below it. The curve is not
monotonic, and on 34 records it cannot be: this is sampling noise, not a property of the
model. It is in the table rather than smoothed away because the temptation to tune a
storage decision on a small sample is exactly the mistake this course keeps warning about,
and here it is in one of our own measurements.

:::{admonition} Common pitfall
:class: warning

**Embeddings from two different models are not comparable, and there is no conversion.**

Cosine values from `text-embedding-3-small` and from `voyage-4` are different numbers in
different spaces. A threshold tuned on one is meaningless on the other. This makes changing
embedding model a *migration*: you must re-embed the entire corpus, which costs the full
corpus in tokens again, and you must re-tune every threshold downstream. Pin the model id
in your config next to the vectors, the way you would pin a schema version.

Two related traps. Some providers use **asymmetric** embeddings, where a query and a
document must be embedded with a different `input_type` flag because the model prepends a
different instruction to each; embedding both sides the same way silently degrades
retrieval. And embedding APIs have their own token limits (8,192 for OpenAI's v3 models,
32,000 for Voyage's), so a long document must be chunked before it can be embedded at all.
:::

## Where this pushes back

Everything above sold you two tools. This section is the part where they are weighed, and
the honest summary is that cosine similarity is a much blunter instrument than its
convenience suggests.

```{figure} figures/embedding-limits.png
:alt: Three panels. Left, a strip plot of embedding cosine for unrelated pairs, same-event pairs, and opposite-meaning pairs, with the same-event and opposite-meaning groups overlapping almost completely inside a shaded band. Middle, precision and recall against cosine threshold on the labelled pairs, with precision never exceeding 0.62. Right, top-1 neighbour agreement against the number of dimensions kept.
:width: 100%

The same 34 entries, asked harder questions. Generated by `figures/make_figures.py`.
```

### Cosine similarity does not know about negation

```{index} pair: failure mode; cosine similarity and negation
```

Consider these two entries:

> `Mechanical seal leaking, approx 8 drops/min, pump P-101`
> `P-101 seal inspected, no leak found`

One is a fault and the other is its refutation. Their cosine similarity is **0.694**. Now
recall the pair from the previous section, which describe the *same* event and score
**0.532**.

**A pair that means the opposite scores higher than a pair that means the same thing.**
This is not a near miss. Across the eight opposite-meaning pairs in this set, **all eight
score above the weakest true match**, and the medians are 0.691 for the opposite pairs
against 0.655 for the true ones. The left panel shows the two groups sitting on top of each
other.

The reason is structural rather than a defect of this particular model. Cosine similarity
measures how much two texts are *about the same thing*, and a report of a leak and a report
of no leak are maximally about the same thing. The word "no" is one token among a dozen and
it does not move the vector far. Nothing in the training objective of an embedding model
requires it to.

The middle panel is what that costs you operationally. Sweeping the duplicate-detection
threshold across the labelled pairs, precision never rises above **0.62** at any cut that
retains meaningful recall. There is no threshold. Not a badly chosen one; there is no value
that separates these two classes, because the classes overlap in the underlying quantity.

### Units are invisible

Two more entries:

> `Bearing temperature 85 degC steady on the drive end`
> `Bearing temperature 85 degF steady on the drive end`

Cosine **0.971**. One of these describes a bearing at its alarm limit and the other
describes a bearing at room temperature. To the embedding they are the same sentence with a
typo. The same effect on pressures, `10.5 MPa` against `10.5 bar`, gives **0.761**, still
well inside the range where a deduplicator would merge them.

This should worry you specifically because of A8. Unit normalization cannot be delegated to
semantic similarity, and it cannot be delegated to the LLM's good judgment either. It has
to be an explicit, typed, tested step in your pipeline, which is why the assignment requires
units in the schema and a normalization stage with the original value retained.

### The theoretical objection

There is also a principled critique worth knowing about. Steck, Ekanadham and Kallus'
2024 paper *Is Cosine-Similarity of Embeddings Really About Similarity?* shows that for
regularized linear models, cosine similarity between learned embeddings can yield
"arbitrary and therefore meaningless" similarities, because the values are governed by the
regularization applied during training rather than by anything semantic. Deep models
combine several regularizers with similar unintended effects. The paper does not say never
use cosine, and neither do these notes. It says the metric is a convention with no
guarantee attached, which is a good frame for the measurements above: they are the
empirical version of the same warning.

### And the tokenizer moves under you

The 37% disagreement between two models from one vendor is not a quirk of this month. It
is the normal condition. Model ids are deprecated, tokenizers are revised, context windows
and prices change, and the numbers in these notes are dated 2026-08-06 for exactly that
reason. Anything in your system that depends on a token count (a chunk size, a cost
estimate, a context-fit check, a rate-limit budget) is a hardcoded assumption about a
model version. Pin the model id, record it in your outputs, and re-measure on upgrade. A8
requires you to report the exact model id you used, and this is why.

## In-class demo

[`l15-tokens-embeddings.ipynb`](l15-tokens-embeddings.ipynb) runs in two halves.

The first half tokenizes a datasheet. We start with the strings from the figure above,
predict the token counts as a room before revealing them, then tokenize the whole document
and count it four ways. The moment to watch for is `Ø25`, where the tokenizer emits two
fragments that are not characters, and the four-way count, where the two Anthropic models
disagree with each other by more than either disagrees with OpenAI.

The second half embeds the thirty-four maintenance log entries. Before we compute anything,
you will be asked to predict which pairs cluster. Most rooms get the near-duplicates right
and the negations wrong, which is the point: the pair everyone marks as "obviously
different" scores higher than the pair everyone marks as "obviously the same."

The notebook runs without any API key using local tokenizers and a lexical baseline, and
uses the provider endpoints when `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are set. Bring
keys if you have them.

## Summary

An LLM is a next-token predictor over a vocabulary of subword fragments, and nearly every
engineering property you care about follows from that. Tokenization decides what the model
actually sees, and it treats engineering notation badly: numbers split at digit-group
boundaries rather than real ones, units detach, part numbers shatter into ten tokens, and a
character can fail to be a token at all. Token counts decide cost, and they are not
portable: the same datasheet is 776 tokens to `tiktoken` and 1,263 to Claude Opus 5, so you
count with the model you are going to call rather than the library you happen to have.
Context is a shared budget of input plus output, but on current models the binding
constraint is usually money rather than capacity, and the latency is set almost entirely by
what you ask the model to write rather than what you give it to read. Hallucination is what
happens when the right answer is not expressible in the output space, so the fix is to
ground the question and to supply a token that means "not found." Embeddings turn text into
vectors whose distances mean something, which finds near-duplicates that share no words at
all, and which is blind to negation and to units in ways that will bite an extraction
pipeline that trusts them too far.

Next session takes all of this to the interface. L16 covers the request and response shape,
schema-constrained structured output, validation and repair loops, prompt caching and cost
accounting, and how to evaluate a prompt against a gold set instead of by reading the
output and nodding. The extractor you build there is A8, and the three habits from today
(count the tokens, ground the question, give it a way to say no) are the ones it is built
on. From there the arc continues into [L17](../l17/notes.md), where these vectors become a
retrieval index, and [L19](../l19/notes.md), where the model starts calling tools.

## Resources

- [Vaswani et al., *Attention Is All You Need*](https://arxiv.org/abs/1706.03762) (2017).
  The architecture, from the paper that introduced it. Skim for Figure 1 and section 3.2;
  the point is the block diagram, not the derivation.
- [Jay Alammar, *The Illustrated Transformer*](https://jalammar.github.io/illustrated-transformer/).
  The best visual explanation of attention there is. Read this before the paper if the
  paper is heavy going.
- [Jay Alammar, *The Illustrated Word2vec*](https://jalammar.github.io/illustrated-word2vec/).
  Where the intuition that vector distance means semantic similarity comes from, built up
  from scratch.
- [Bommasani et al., *On the Opportunities and Risks of Foundation Models*](https://arxiv.org/abs/2108.07258)
  (2021). Read the introduction for the framing: why one model trained once and adapted
  many times changes the engineering problem.
- [Sennrich, Haddow and Birch, *Neural Machine Translation of Rare Words with Subword Units*](https://arxiv.org/abs/1508.07909)
  (2016). The paper that brought byte-pair encoding into language models. Section 3.2 is
  the algorithm, and it is shorter than you expect.
- [Reimers and Gurevych, *Sentence-BERT*](https://arxiv.org/abs/1908.10084) (2019). Why a
  sentence embedding is a different object, trained specifically so that cosine similarity
  between two independently computed vectors means something. The abstract's arithmetic is
  the part to keep: finding the most similar pair in 10,000 sentences takes about 65 hours
  of cross-encoder inference and about 5 seconds with sentence embeddings.
- [Steck, Ekanadham and Kallus, *Is Cosine-Similarity of Embeddings Really About Similarity?*](https://arxiv.org/abs/2403.05440)
  (2024). The principled version of this session's limits section. Short, and it will make
  you more careful with thresholds.
- [Anthropic, token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting).
  The endpoint, its rate limits, and the note that Claude 4.7 and later use a tokenizer
  producing roughly 30% more tokens for the same text.
- [Anthropic, embeddings](https://platform.claude.com/docs/en/build-with-claude/embeddings).
  Worth reading precisely because Anthropic does not have an embedding model; it is a clear
  statement of what to look for in one, and the Voyage sections cover `input_type`,
  Matryoshka truncation, and quantization.
- [OpenAI, embeddings guide](https://developers.openai.com/api/docs/guides/embeddings). The
  `dimensions` parameter, the 8,192-token input limit, and the model comparison.
- [`tiktoken`](https://github.com/openai/tiktoken). OpenAI's local BPE tokenizer. Fast,
  exact for OpenAI models, and correct for no others; useful in this course mainly as the
  thing to measure other tokenizers against.
- [Brooks, Pope and Marcolini, *Airfoil self-noise and prediction*](https://ntrs.nasa.gov/citations/19890016302),
  NASA RP-1218 (1989). The 146-page report measured in these notes, and the source of the
  dataset used in L9 and L13. Public domain, and a good test document precisely because the
  scan is imperfect.

## Assignment

**A8, structured extraction from engineering documents**, is released today and is due at
the start of L17 on 2026-11-04. You will build and *evaluate* an LLM extractor that turns
messy engineering text into a schema-validated, normalized table, with a gold set, a
measured prompt iteration, and per-call cost accounting. The full specification is in
[`course/assignments/a08.md`](../../course/assignments/a08.md).

Two things from today feed straight into it and are worth starting on now. Task 2 is a
token and cost baseline over your corpus, which you can do with nothing but the tokenizer
and the counting endpoint before you have written any extraction code. And the corpus
itself needs two or three deliberately incomplete documents, because the "not found"
behaviour measured in this session is exactly what those documents exist to test.
