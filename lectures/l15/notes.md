# L15 · Foundation models and LLMs at a systems level: architecture, tokenization, embeddings

:::{admonition} At a glance
:class: tip

- **Session** L15, Week 9 · **Arc** LLM & agentic engineering
- **Slides** <a href="../../slides/l15/">Deck for this session</a>
- **Demo** [`l15-tokenization-embeddings.ipynb`](l15-tokenization-embeddings.ipynb), a datasheet's token count and a maintenance log's cosine-similarity matrix
- **Assignment** A8 released this session
:::

## Why this matters

Every session so far in this course has ended with a number you could check against
something: an RMSE, a coverage percentage, a wall-clock time. This session starts an arc
where the model's output is a paragraph, and a paragraph does not come with a residual. That
difference changes what "debugging" means, and the change catches engineers off guard in a
specific way: an LLM feels like a function you call, `answer = llm(question)`, and functions
are supposed to fail loudly. This one fails by being fluent.

Here is the failure to hold onto. An engineer pastes a forty-page equipment manual into a
chat window and asks for the maximum operating pressure. The model answers with a number,
confidently, in the right units, in a sentence that reads like every other sentence it has
written all day. The number is wrong, not because the model made an arithmetic mistake, but
because the manual was longer than the model's context window, the interface truncated the
tail silently, and the actual pressure rating was on page thirty-one. Nothing in the
response signals this. There is no exception, no null return, no warning icon. The failure
mode of a relational query is an error message; the failure mode of an LLM call is a
plausible paragraph with a wrong number quietly inside it, and the paragraph is exactly as
fluent whether the number is right or not.

You cannot engineer around a failure you cannot see, so this session's job is to open the
box just enough that the two properties driving that failure, "there is a hard token budget"
and "the model is a next-token predictor, not an oracle," become things you check for rather
than things that surprise you. Neither requires the math of *Attention Is All You Need*. Both
require noticing that a datasheet's units, part numbers, and tolerances are exactly the kind
of text a language model's vocabulary was not built to compress cheaply, which is where this
session's two measurements come in: tokenizing engineering text costs more than tokenizing
ordinary prose, and a document's length in *words* is a bad predictor of its length in
*tokens*, in a direction that always makes the budget tighter than it looks. Get that wrong
and A8's extraction pipeline silently truncates the one datasheet that mattered.

## Learning objectives

By the end of this session you should be able to:

- Build a correct-enough mental model of a decoder-only LLM to reason about failure modes
  (truncation, hallucination, context limits) rather than treat it as a black box.
- Understand tokenization concretely: subword units, why "10.5 MPa" or "SS316L" may split
  oddly, and how token counts drive cost/latency.
- Understand embeddings as vectors and use cosine similarity to cluster/retrieve engineering
  text.

## Inside a decoder-only transformer

Strip away the marketing and a large language model is a function with an unglamorous
signature: it takes in a sequence of tokens and returns a probability distribution over what
the next token is. Everything else, the chat interface, the streaming animation, the sense
of a conversation, is scaffolding built around that one function, called in a loop.

The sequence starts as text and ends as integers. A **tokenizer** splits the input into
pieces from a fixed vocabulary, typically tens of thousands of subword fragments (more on
what "subword" means and why it matters in the next section), and maps each piece to an
integer id. Each id indexes into an **embedding table**, a learned matrix with one row per
vocabulary entry, so the token sequence becomes a sequence of vectors. Because a transformer
has no inherent sense of order, those vectors are combined with **positional information**:
Vaswani et al.'s original 2017 architecture added fixed sinusoidal signals; most current
decoder-only models instead use a learned scheme or **rotary position embeddings (RoPE)**,
which rotates each vector by an angle proportional to its position and turns "how far apart
are these two tokens" into an algebraic property of the vectors themselves, which turns out
to generalize better to sequence lengths longer than anything seen in training.

That sequence of position-aware vectors then passes through a stack of identical blocks,
typically dozens of them in a production model. Each block does two things in sequence:
**self-attention**, where every position computes a weighted combination of every earlier
position's vector (never a later one, since a decoder-only model is trained to predict
forward and is masked so it cannot cheat by looking ahead), and a **position-wise
feed-forward network**, an ordinary two-layer MLP applied identically and independently at
every position. Both are wrapped in residual connections and a normalization step, which is
mostly what makes stacking dozens of these blocks trainable at all rather than a description
of what each block computes. The attention step is where the model decides which earlier
words are relevant to the current one, computed fresh for every input rather than fixed in
advance, which is the entire reason it beat the recurrent and convolutional architectures
that preceded it: a word at the start of a paragraph can inform a word at the end in a single
step, with no information having to survive a long recurrent chain to get there.

After the last block, a final linear layer projects each position's vector back out to the
size of the vocabulary, producing one number per possible next token, called a **logit**. A
softmax turns those logits into a probability distribution, and the model samples (or picks
greedily) from that distribution to choose the next token. That token is appended to the
sequence, and the whole thing runs again to produce the token after it. This is the
**autoregressive generation loop**: one token out per full forward pass, glued end to end
until a stop condition fires. It is why a longer response takes proportionally longer to
generate than a short one, and it is the entire mechanism by which a coherent multi-paragraph
answer gets built one token at a time, with no step at which the model plans the paragraph
in advance. (Production systems cache the internal representations of already-processed
tokens so each new step only does new work for the newest token, which is why cost and
latency scale roughly linearly in the number of tokens generated rather than quadratically;
you do not need the mechanics of that cache to reason about the system, only the fact that it
is why generation is not as expensive as re-running the whole model from scratch at every
step.)

## Why "it predicts the next token" explains both fluency and hallucination

The training objective behind everything above is almost embarrassingly simple to state:
given an enormous corpus of text, adjust the model's parameters so that, at every position,
the probability it assigns to the token that actually comes next is as high as possible. No
labels, no annotation, just text predicting itself. That single objective, run at a scale of
trillions of tokens and hundreds of billions of parameters, is what produces something that
can draft an email, summarize a report, or explain a traceback.

It is worth sitting with how strange that is, because the same fact that explains the
fluency also explains the failure mode this session opened with. A model trained to predict
the next token has no separate mechanism for "is this true," only "is this likely given
everything before it." Fluent, grammatical, contextually appropriate text is high-likelihood
text, so the objective rewards fluency directly. But a false but plausible-sounding
continuation is often *also* high-likelihood, especially when the true answer is rare, absent
from training data, or missing from the current context. The model does not have a
introspective "I don't actually know this" state to fall back on; it always has *some*
distribution over the next token, and it always samples from it. **Hallucination is not a
bug that better training removes; it is the same generative mechanism that produces fluency,
running in a case where the plausible continuation happens to be false.** That is why
grounding a model in retrieved or provided text (this session's embeddings section, and
L17's subject) and instructing it explicitly to say "not found" instead of guessing are
engineering controls external to the model, not properties the architecture gives you for
free.

Two knobs control how that final distribution gets turned into a specific token.
**Temperature** rescales the logits before the softmax: dividing by a temperature below 1
sharpens the distribution toward the single most likely token (temperature 0 is effectively
"always pick the most likely one," useful for extraction tasks where you want the same answer
every time), while a temperature above 1 flattens it, increasing variety and, correspondingly,
the odds of a strange or wrong token being chosen. **Top-p (nucleus) sampling** takes a
different cut at the same problem: rather than reshaping the whole distribution, it restricts
sampling to the smallest set of tokens whose cumulative probability exceeds `p`, discarding
the long unlikely tail entirely before sampling from what remains. The two compose (many APIs
expose both), and the practical rule for this course's extraction-style work is the boring
one: low temperature, narrow top-p, for anything where you want the same input to produce the
same output.

## The context window is a hard budget, and tokenization decides how fast you spend it

Every call to a hosted LLM has a **context window**: a maximum number of tokens the model can
process in one request, counting the prompt you send *and* the response it generates
together. This is not a soft guideline. It is a hard architectural limit tied to how the
model was trained and (for some architectures) to the cost of the attention computation
itself, and every provider enforces it, though not always the same way: some APIs return an
explicit error when a request would exceed the limit, and some interfaces built on top of an
API silently drop or truncate the oldest turns of a conversation to make room. Which behavior
you get is a property of the specific product you are calling, not of language models in
general, which is exactly why you cannot assume: read the current behavior of whichever
interface you are using, and treat "count the tokens before you send the request" as a
required step rather than a nice-to-have, never a silent truncation.

That requirement is where **tokenization** stops being a footnote and becomes the thing that
determines whether your budget holds. A modern subword tokenizer is not splitting on
whitespace; it is applying a fixed vocabulary of a few tens of thousands to a few hundred
thousand subword fragments, learned in advance from a training corpus by repeatedly merging
the most frequent adjacent pair of symbols until the vocabulary reaches its target size. This
is **byte-pair encoding (BPE)**, adapted for tokenization by [Sennrich, Haddow and Birch
(2016)](https://aclanthology.org/P16-1162/) from a much older data-compression algorithm;
GPT-family and Claude-family tokenizers are both variants of this same idea, trained on
different corpora with different vocabularies.

The consequence of "learned from a training corpus by frequency" is the one that bites
engineering text specifically. Common English words and their frequent fragments earn short,
often single-token representations because the training corpus is overwhelmingly ordinary
prose. Anything statistically rare relative to that corpus does not: a number, a unit
symbol, an alloy designation, a chemical formula, a part number, a code identifier. Those
strings get fragmented into several short pieces, sometimes down to individual characters,
because no merge rule for them was frequent enough to earn a place in the vocabulary.

```{figure} figures/bpe-fragmentation.png
:alt: Bar chart of tokens per character for seven test strings under a small byte-pair-encoding tokenizer trained on ordinary engineering prose. The plain-prose sentence sits at 0.32 tokens per character; a tolerance callout, a diameter symbol, an alloy code, a stainless grade, a pressure value, and a chemical formula all sit between 1.0 and 1.33 tokens per character, three to four times higher.
:width: 100%

A tokenizer trained here from scratch on twelve sentences of engineering prose (see
`figures/make_figures.py`), then applied to text it never saw. This is not the tokenizer any
production model uses; it is the same algorithm, at a scale small enough to run offline, and
it makes the same point a real provider tokenizer would.
```

That figure is not from a hosted provider (see the note on why in the practitioner box
below), but the mechanism it demonstrates is identical to the one that runs inside a real
provider's tokenizer, just at toy scale: eighty merge rules learned from a 76-word
vocabulary. The plain sentence "the pump operated within specification" comes out at 0.32
tokens per character, 11 tokens for 34 letters, because most of those words were frequent
enough in the tiny training corpus to merge into large chunks. Every other test string comes
out between 1.00 and 1.33 tokens per character: "AISI 4140" takes 8 tokens for 8 characters,
one token per character, essentially no compression at all, because digits and an
unfamiliar alloy code never appeared often enough to earn a merge. That is a three-to-four
times difference in token density for text that, to a human reading a datasheet, looks like
it should be no harder to read than the sentence next to it.

:::{admonition} What a practitioner should take from this
:class: tip

A page count or a word count is not a token budget, and the gap between them is worst
exactly where engineering documents are richest: units, tolerances, part numbers, chemical
formulas. Do not estimate a document's token cost from its word count using a rule of thumb
borrowed from ordinary prose; count it with the tokenizer you will actually call, on the
actual document, before you build a pipeline around an assumed budget.

And do this per provider. **Never estimate one provider's token usage with another
provider's tokenizer.** Anthropic and OpenAI (and any other provider) train separate
vocabularies on separate corpora, so the same string produces a different token count on
each, and a count computed with the wrong one is not an approximation, it is a number about a
different tokenizer entirely. Use the provider's own token-counting endpoint or library
(Anthropic's `count_tokens` method, OpenAI's [`tiktoken`](https://github.com/openai/tiktoken))
against the model you are actually going to call.
:::

:::{admonition} Why this session's numbers come from a tokenizer built here, not a provider's
:class: note

This sandbox's network policy allows package registries but not Anthropic's, OpenAI's, or
Hugging Face's endpoints, so a live provider tokenizer cannot be called while writing these
notes, and a specific token count copied from memory would be exactly the kind of
unverified number this course argues against citing. `figures/make_figures.py` instead trains
a real byte-pair-encoding tokenizer from scratch, on a corpus written for this file, so every
number above is computed, not asserted, and the script that produced it is checked in. Run it
yourself, or better, replace the toy training corpus with your provider's real vocabulary
call once you have a key: the fragmentation pattern will be the same shape, and the exact
numbers will differ. `l15-tokenization-embeddings.ipynb` is written to call the real API and
is the version to run in class.
:::

A second source of surprise is **whitespace and casing sensitivity**. Because most subword
tokenizers operate on raw bytes or characters and frequently include the leading space as
part of a token, `"pressure"`, `" pressure"`, and `"Pressure"` can be three entirely distinct
tokens with no normalization applied automatically. A prompt template that is inconsistent
about a leading space is not a cosmetic issue; it can change which tokens a downstream
extraction or classification step actually sees.

## Embeddings: representing text as vectors you can compare

Everything above is about generating text. **Embeddings** are the other half of the systems
picture: representing text as a fixed-length vector so that you can compare, search, or
cluster pieces of text numerically, without generating anything.

Two different things share the name "embedding" and are worth separating. **Token
embeddings** are the per-token vectors that live inside the model described above; by the
time they have passed through several attention blocks they are *contextual*, meaning the
vector for "bearing" in "the bearing failed" differs from the vector for "bearing" in "she
gave birth, bearing the pain," because attention has mixed in information from the rest of
the sentence. **Sentence or document embeddings**, the kind you call an API for, pool an
entire passage into a single vector, typically via a pooling step trained specifically so
that semantically similar passages land close together in the resulting vector space. When
this session (and the module) say "call an embeddings API," this second kind is what is
meant: one vector per maintenance-log entry, per datasheet paragraph, per support ticket.

The standard way to compare two embedding vectors is **cosine similarity**: normalize both
vectors to unit length and take their dot product, which measures the angle between them
rather than their magnitude. Angle, not length, is the meaningful quantity here because
embedding magnitude is largely an artifact of training rather than a signal about content, so
two conventions exist to make magnitude irrelevant before comparing: cosine similarity
divides it out explicitly, and many models are trained so their embeddings are already close
to unit length, making cosine similarity and a plain dot product nearly interchangeable in
practice. Dimensionality varies by model, from a few hundred to a few thousand components,
and more dimensions is not automatically better: it costs more to store and search, and
retrieval quality is an empirical property of the specific model, benchmarked on tasks like
those in the [Massive Text Embedding Benchmark
(MTEB)](https://huggingface.co/spaces/mteb/leaderboard), not a function of vector length
alone.

Why reach for an embedding call instead of an LLM completion call at all? Because a large
class of engineering tasks is not "generate new text," it is "find the text I already have
that is most like this one": deduplicating near-identical failure reports, clustering
maintenance logs by failure mode, retrieving the three datasheet paragraphs most relevant to
a question. An embedding call is a single forward pass to a vector, dramatically cheaper and
faster than a generative completion, and it turns "find similar text among thousands of
candidates" into ordinary nearest-neighbor search over vectors. That is the exact mechanism
this course returns to in L17 under the name **retrieval-augmented generation**; today's
embeddings section is the preview.

```{figure} figures/lexical-similarity.png
:alt: Heatmap of cosine similarity across 24 maintenance-log entries in five fault categories (bearing, seal, valve, corrosion, overheat), computed with TF-IDF rather than a learned embedding. Most entries within a category show weak but visible similarity to each other; the entry "brg vibration increasing over past week" shows zero similarity to every other entry, including the other four bearing entries.
:width: 100%

TF-IDF cosine similarity, a lexical-overlap baseline computed here (see
`figures/make_figures.py`), not a semantic embedding. Mean within-category similarity 0.130
against 0.009 between categories, a real signal, and a weak one.
```

That figure is deliberately *not* a semantic embedding. It is **TF-IDF**, a classical vector
representation that weights each word by how often it appears in a document relative to how
often it appears across the whole collection, which is a decades-old, fully offline,
lexical-overlap technique with no learned semantics in it at all. It is the honest stand-in
this session can compute without network access to a hosted embedding API (the same
constraint that shaped the tokenization figure above), and it earns its place in these notes
because its failure is the whole argument for embeddings. Grouped by their true fault
category, entries sharing vocabulary do cluster weakly: mean within-category cosine
similarity is 0.130 against 0.009 between categories, a fourteen-times gap and a real signal.
But the entry logged in a technician's own shorthand, "brg vibration increasing over past
week," shares not one word with any of the other twenty-three entries, including the four
other bearing-failure reports it should cluster with. Its cosine similarity to *every other
entry in the set, including its own category*, is exactly 0.000. TF-IDF cannot see past the
absence of shared vocabulary at all.

A semantic embedding model represents meaning learned from a large corpus, not surface word
overlap, which is precisely why the field moved past keyword and TF-IDF matching for
retrieval: it is expected to place "brg vibration" close to "noisy bearing" and "bearing
noise" despite the zero word overlap, because all three describe the same failure. This
session's sandbox cannot call a hosted embedding API to confirm that number for this exact
sentence set (see the note above), which is exactly why `l15-tokenization-embeddings.ipynb`
is written to make that call live, with your own provider key, in class: predict, before you
run it, which entries a real embedding model pulls together that TF-IDF above kept apart.

## Where this pushes back

**"It predicts the next token" is a useful mental model, not a complete theory.** It
correctly predicts truncation and hallucination, which is what this session needs it for, but
it does not by itself explain why scaling up the same objective produces qualitatively new
abilities (multi-step reasoning, following a novel instruction format, translating between
languages never paired in training) at particular scales rather than smoothly. That
phenomenon, sometimes called emergence, is actively studied and only partially understood;
treat the token-prediction picture as the floor of your intuition, not the ceiling.

**A token fitting inside the context window is not the same as the model using it well.**
Context windows have grown from thousands of tokens to hundreds of thousands over the last
few years, but a larger budget does not mean every token in it receives equal attention.
[Liu et al.'s "Lost in the Middle"](https://arxiv.org/abs/2307.03172) (next session's
reading) found that retrieval accuracy for a fact placed in the middle of a long context can
be markedly worse than the same fact placed at the start or the end, in models that never
raise an error and never truncate anything. "It fits in the context window" is a necessary
condition for the model to use a fact, and this course will spend next session on why it is
not a sufficient one.

**Provider tokenizers and embedding models are not portable across time or across vendors.**
A new model release can retokenize entirely, which silently invalidates a token count or a
cost estimate calibrated against the previous version. Embeddings from two different models,
or two versions of the same model, are not directly comparable: they live in unrelated vector
spaces with different dimensionality, so computing a cosine similarity between an embedding
from one model and an embedding from another is not merely inaccurate, it is comparing
numbers that were never in the same space to begin with. Re-embed your corpus whenever you
change embedding models; do not mix vectors from two.

**Every specific number in a provider's documentation is a number that changes.** Context
limits, pricing, and which sampling parameters are exposed all move as providers ship new
models, and this session has deliberately not repeated any of them, because a number
memorized today from a lecture is a number a student would be wrong to trust in November.
Read the current page for the provider and model you choose for A8, and note the model ID
you tested against in your report, because "it worked" is a claim about one specific,
dated version of a system that will not stay still.

## In-class demo

The runnable notebook is
[`l15-tokenization-embeddings.ipynb`](l15-tokenization-embeddings.ipynb). It has two parts,
matching the module's live activity.

First, we take a page of a real datasheet-style passage (units, tolerances, a part number or
two) and count its tokens with a provider's own tokenizer or token-counting call, and compare
that count against a naive word-count guess, then do the same for a much longer document to
show how quickly a naive estimate and the real count diverge. Second, we take the same
twenty-four maintenance-log entries behind this session's TF-IDF figure and embed them with a
real hosted embedding model, then look at which entries land close together. The prediction
to make before that cell runs: does "brg vibration increasing over past week" land next to
the other bearing-failure entries this time, where TF-IDF put it nowhere near anything?

Both cells require a provider API key and network access, which this session's sandbox does
not have; the notebook is written to the same pattern as the SECOM download cell in
[L5](../l05/notes.md), so it will run once you supply a key, and it is the version to drive
live in class rather than the offline figures above.

## Summary

A large language model is, mechanically, a next-token predictor: text becomes tokens,
tokens become vectors, a stack of attention and feed-forward blocks refines those vectors,
and a final projection produces a distribution the model samples from, one token at a time,
in a loop. That single fact explains both why the output is fluent and why it can be
confidently wrong, since nothing in the mechanism distinguishes a plausible answer from a
true one. Two engineering constraints follow directly from the same architecture: the
context window is a hard token budget shared between prompt and response, and the tokenizer
that converts your text into that budget is frequency-driven and provider-specific, which is
why engineering text, unusually rich in units, part numbers, and formulas, tokenizes far less
efficiently than ordinary prose, by a factor this session measured at three to four times.
Embeddings are the complementary tool: a fixed vector per passage, compared by cosine
similarity, useful for exactly the tasks an LLM call is the wrong, expensive tool for, and
this session's own lexical baseline showed concretely what a representation without learned
semantics misses. Next session takes the API surface these two ideas sit behind, the actual
request, the structured-output modes, the cost and latency accounting, and the discipline of
measuring a prompt instead of eyeballing it.

## Resources

- A. Vaswani et al., ["Attention Is All You Need"](https://arxiv.org/abs/1706.03762), NeurIPS
  2017. Skim it for the architecture diagram (Figure 1) and the description of multi-head
  attention, not for the full derivation; this is the paper that introduced the architecture
  every model in this session's arc descends from.
- Jay Alammar, ["The Illustrated
  Transformer"](https://jalammar.github.io/illustrated-transformer/) and ["The Illustrated
  Word2vec"](https://jalammar.github.io/illustrated-word2vec/). The visual walkthroughs this
  session's block-diagram description is condensing; read them for the diagrams this format
  cannot reproduce.
- Your chosen provider's current *tokenization/token-counting*, *embeddings*, and
  *models/pricing* documentation. Read the version live on the site when you do A8, not a
  cached copy from this session, since all three change.
- R. Bommasani et al., ["On the Opportunities and Risks of Foundation
  Models"](https://arxiv.org/abs/2108.07258), Stanford CRFM, 2021. Read the introduction and
  the framing sections for the "systems" view of what a foundation model is and what
  building on top of one entails; it is long, and this session only asks for the frame, not
  the full survey.

## Assignment

**A8, structured extraction from engineering documents**, releases this session. Full spec
and rubric: [`course/assignments/a08.md`](../../course/assignments/a08.md); this paragraph is
a pointer, not the rubric. The tokenizer discipline from this session (count before you send,
never guess with the wrong provider's tokenizer, never let a document silently truncate) is
the first thing A8's grading will look for.
