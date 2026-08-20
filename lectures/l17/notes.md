# Lecture 17: Retrieval-augmented generation and vector databases

:::{admonition} Overview
:class: tip

- **Session** Lecture 17, Week 10
- **Arc** LLM and agentic engineering
- **Slides** <a href="../../slides/l17/">Deck for this session</a>
- **Demo** [`l17-rag.ipynb`](l17-rag.ipynb), a RAG pipeline measured end to end
- **Assignment 9** released this session
:::

## Why this matters

In 2022, Jake Moffatt's grandmother died, and he went to Air Canada's website to book a
last-minute flight for the funeral. He asked the airline's customer service chatbot about
bereavement fares, and it told him he could book a full-price ticket immediately and apply
for a bereavement discount within 90 days after travel. He did exactly that. Air Canada then
refused the refund, pointing out, correctly, that its actual bereavement policy required the
discount request to be submitted *before* travel, not after. The chatbot's answer simply was
not what the airline's policy said. Air Canada's defense in the case that followed argued the
chatbot was "a separate legal entity that is responsible for its own actions," and that Mr.
Moffatt should have verified the chatbot's claim against the airline's own policy page himself.
Canada's Civil Resolution Tribunal rejected that argument
in February 2024, calling it "a remarkable submission" and holding that a company is
responsible for all the information on its website, "whether it comes from a static page or a
chatbot." Air Canada was ordered to pay the fare difference and damages.

Read past the legal outcome and the engineering failure is precise and entirely familiar by
this point in the course: a language model was asked a factual question about a policy
document that exists, in full, in a specific, retrievable place, and instead of being shown
that document, it was left to generate an answer from whatever pattern of bereavement-policy
language it had absorbed in training. The chatbot had no intent to deceive: it was doing
exactly what a language model does when nothing constrains it to a source, producing
plausible, fluent, and in this case wrong text. Grounding is not an optional refinement of a
chatbot: a model unconstrained by a real source generates plausible text, and "plausible" and
"correct" are different properties that coincide often enough to be dangerous.

Retrieval-augmented generation is the engineering answer to exactly this failure: instead of
asking a model to recall a fact from its training data, hand it the actual, current,
retrievable text of the fact and ask it to answer from that. The word "augmented" undersells
what is happening: RAG makes a model's answer traceable to a source a human can go check.
That traceability is the property Air Canada's chatbot was missing, and it is what this
session builds toward. RAG also solves two problems retrieval-free generation cannot touch at
all: **freshness**, since a retrieved document can be updated the moment the policy changes
with no retraining, and **cost**, since retrieving three relevant paragraphs is cheaper than
either fine-tuning a model on your entire corpus or pasting the entire corpus into every
prompt. Retrieval and simply using a very long context window, now that models support
hundreds of thousands of tokens, are not the same choice: a longer context is not a substitute
for retrieval, both because it is billed by the token on every single call and because, as
later sections show, a model does not read a long context uniformly.

## Learning objectives

By the end of this session you should be able to:

- Explain why RAG exists (grounding, freshness, source attribution, cost vs long-context) and
  where it breaks.
- Build each stage of a RAG pipeline and reason about the design choices at each stage.
- Evaluate retrieval quality quantitatively and connect retrieval failures to downstream
  answer failures.

## The anatomy of a RAG pipeline

```{index} retrieval-augmented generation
```
```{index} see: RAG; retrieval-augmented generation
```

Split the system into the two paths that actually run at different times, because conflating
them is the fastest way to get confused about where a bug lives. The **ingestion path** runs
once per document, offline, whenever your corpus changes: load the raw files, clean them,
**chunk** them into retrievable pieces, embed each chunk into a vector, and write the vectors
into an index. The **query path** runs once per user question, online, under a latency budget
a user is actually waiting on: embed the incoming question with the same embedding model used
at ingestion, retrieve the top-k most similar chunks from the index, assemble those chunks
into a prompt alongside an instruction to answer only from them, and generate an answer that
cites which chunk supported which claim.

The architecture traces back to a specific 2020 paper, Lewis and colleagues' "Retrieval-
Augmented Generation for Knowledge-Intensive NLP Tasks," which coined the name and the
now-standard shape: a retriever that scores documents against a query, and a generator
conditioned on both the query and whatever the retriever returned. What has changed since 2020
is mostly the scale and convenience of the pieces, embeddings are better, indexes are faster,
context windows are longer, but the two-path shape and the reason for it, do not ask a model to
recall what you can instead show it, has not moved.

Every stage in that anatomy is a place a design decision changes the answer's correctness, and
the rest of this session works through them in order: what makes a good chunk, what an index
actually buys you, how retrieval itself works, how to force the generation step to stay
honest, and, last, how you would know any of this is working before you ship it.

## Chunking strategy

```{index} chunking, fixed-size chunking, structure-aware chunking
```

A chunk is the unit your retriever can return, and that constraint cuts both ways. Too large a
chunk and a query about one clause drags in several unrelated ones, diluting the similarity
signal and wasting context budget on irrelevant text. Too small a chunk and a single fact gets
severed from the context that makes it unambiguous, a number with no unit, a clause with no
subject.

**Fixed-size chunking** is the default anyone reaches for first: pick a token count, say 256
or 1024, and a chunk boundary every that-many tokens, usually with some overlap between
consecutive chunks so a fact sitting near a boundary has a chance of appearing whole in at
least one chunk. It is trivial to implement and it is blind to the document's own structure,
which is exactly what makes it a poor fit for the kind of document this session's demo uses:
an engineering standard or manual, built from numbered clauses and tables, where the unit of
meaning is a numbered clause like "clause 4.2" or a table row like "the row for 3/8 inch
bolts." A fixed window does not know where clause 4.2 ends. It will, with some regularity, end a chunk in the middle
of a table row, separating a bolt size from its torque value, or bury one short, specific
clause inside a chunk dominated by an unrelated neighboring one.

**Structure-aware chunking** respects the document's own boundaries instead: one chunk per
section, per clause, per table, using whatever markup or numbering the source document already
provides. It costs more to implement, since it needs a parser for the document's actual
structure rather than a token counter, but it never splits a fact in half and never merges two
unrelated ones, because the chunk boundary is the same boundary the document's author already
decided was meaningful.

This session's demo measures the difference rather than asserting it. On a small constructed
corpus of clause-numbered engineering notes, structure-aware chunking holds recall@k at or near
1.0 for a 15-query gold set; a naive fixed-size chunker that ignores both clause and document
boundaries drops recall to roughly 0.93 at k=3 and, more tellingly, drops nDCG considerably
further, from about 0.95 to somewhere around 0.6-0.7, meaning even the queries that still
technically succeed are finding their answer ranked lower and buried next to an arbitrary
neighboring clause the splitter happened to glue on. Two specific queries fail outright: one
because the value it needs is stitched into a mostly-irrelevant window from a neighboring
clause, the other because a table row's specific size-and-radius pair ends up split across
chunk boundaries. Neither failure is subtle once you look at the retrieved text; both are
invisible if you only look at an aggregate score.

Whichever chunking strategy you use, keep **metadata** alongside every chunk: the source
document, the section or clause number, a page if there is one, and a revision or version
identifier. A citation without a section number is not a citation a reader can check, and a
chunk with no revision tag becomes a liability the day the source document is revised and your
index is not.

:::{admonition} Common pitfall
:class: warning

Chunk size and overlap interact with your embedding model's own limits in a way that is easy
to ignore until it silently truncates something. Most embedding models have a maximum input
length; a chunk built without checking against it does not raise an error, it just gets cut
off, and the last third of a long clause quietly never makes it into the vector that is
supposed to represent it.
:::

## Vector databases and the index that backs retrieval

```{index} vector database, approximate nearest neighbor search, HNSW, FAISS, pgvector
```

A **vector database** (or, for smaller corpora, an in-process vector index) exists to answer
one question fast: given a query vector, which of my stored vectors are closest to it. What it
actually provides, beyond a big array of floats, is **approximate nearest-neighbor (ANN)
search** at a scale where checking every vector one at a time would be too slow, **metadata
filtering** so you can restrict a search to, say, only the current revision of a document, and
**persistence** so the index survives past one Python process.

Name the real options rather than treating "vector database" as one interchangeable thing,
because they occupy genuinely different points in the operations-versus-scale trade-off.
[FAISS](https://faiss.ai/) is a library, not a server: it runs in-process, has no
authentication or multi-user story, and is the right choice for exactly the situation this
session's demo is in, a corpus that fits in memory on the machine doing the retrieving.
[Chroma](https://www.trychroma.com/) and [Qdrant](https://qdrant.tech/) are purpose-built
vector databases with a server component, persistence, and metadata filtering built in as
first-class features, appropriate once more than one process needs to query the same index or
the corpus stops fitting comfortably in one machine's memory. [pgvector](https://github.com/pgvector/pgvector)
takes a different and, for a course that spent Week 2 on PostgreSQL, a notable path: it adds a
vector column type and similarity operators directly to Postgres, so a team already running
Postgres for its relational data gets approximate nearest-neighbor search without introducing
a second database technology to operate and back up. The right choice is the one whose
operational model matches what you already run and how many queries per second you actually
expect, not whichever tool is loudest in a given year.

The **exact-versus-approximate** distinction is the trade-off every one of these systems is
built around. An exact nearest-neighbor search, checking every stored vector's distance to the
query, always returns the true top-k, but its cost grows linearly with the number of stored
vectors. An approximate index (FAISS's `IndexIVFFlat` or HNSW-based indexes being common
examples) trades a small, tunable chance of missing the true best match for retrieval times
that barely grow as the corpus scales into the millions of vectors. For a corpus in the
thousands to low millions, exact search is often fast enough that the complexity of an
approximate index is not worth adding; the trade-off starts to matter once query latency
under exact search would already be noticeable to a user.

## Retrieval mechanics: dense, keyword, and hybrid

```{index} dense retrieval, keyword retrieval, BM25, hybrid retrieval, re-ranking, cross-encoder
```

**Dense retrieval** embeds both the query and every chunk into the same vector space with a
neural embedding model and ranks chunks by vector similarity, cosine similarity being the
usual choice. Its strength is exactly what makes it "semantic": a query about a "leak" can
retrieve a chunk about "seepage" because the embedding model learned that those concepts sit
near each other in the space, with no shared vocabulary required. Karpukhin and colleagues'
2020 Dense Passage Retrieval paper is the result that made this the default for open-domain
question answering, showing dense retrieval beating classical keyword search on exactly the
kind of paraphrase mismatch keyword search cannot see past.

**Keyword retrieval**, of which **BM25** (a scoring function refined through the 1990s and
still the workhorse of the field) is the standard implementation, scores a chunk by how many
of the query's exact terms it contains, weighted by how rare each term is across the whole
corpus. It cannot see past a paraphrase, but it is exact where dense retrieval is fuzzy: a
query for a specific part number, error code, or clause number is precisely the case where you
want literal term matching, not a model's notion of semantic similarity, because "similar to
part number 4471-B" is not a coherent idea and a dense retriever has no principled way to treat
it as one.

**Hybrid retrieval**, running both and combining the rankings, is the practical answer to
neither being uniformly better: it catches the paraphrase case dense retrieval is built for and
the exact-identifier case BM25 is built for, at the cost of maintaining two indexes and a
combination rule. **Metadata filters**, restricting a search to chunks tagged with the current
document revision or a particular equipment class, apply on top of either method and are
frequently what actually saves a query from returning a technically-similar but obsolete
answer.

**Re-ranking** with a cross-encoder is the step that trades latency for precision at the very
top of the ranking. A dense or BM25 retriever scores each chunk independently against the
query, cheaply, across the whole corpus, to produce a candidate list. A cross-encoder instead
takes the query and one candidate chunk together as a single input and scores that pair
jointly, which lets it model interactions between the two that independent scoring cannot see,
at the cost of being far too slow to run against the whole corpus. The standard pattern is
therefore two stages: a fast retriever narrows the corpus to a few dozen candidates, and a
slower cross-encoder re-ranks just those, spending its expense only where it can afford to.

## Grounding the generation

```{index} grounding
```

Retrieval only gets you halfway. The generation step has to be explicitly instructed to use
what it was given rather than what it remembers, and this session's demo shows exactly why
that instruction has to live at generation time rather than being papered over earlier in the
pipeline. It is tempting to think a retrieval score can do this job, refuse to answer whenever
the top match scores below some threshold, but a similarity score measures topical closeness,
not "does this chunk actually answer the question." A question about PVC conduit bend radius
retrieves a chunk about rigid metal conduit bend radius at a similarity score indistinguishable
from the scores of genuinely correct matches elsewhere in the same corpus, because the two
questions really are topically close. The wrong document is not an unrelated document, and no
number computed before generation reliably tells the two apart.

The instruction has to be explicit and has to be evaluated by something that can actually read:
answer only from the provided context, cite the section or chunk that supports each claim, and
if the context does not contain the answer, say so in fixed, recognizable words rather than
guessing. That last clause matters mechanically: a model instructed only to "be careful" will
still often produce a plausible-sounding answer, because plausible-sounding answers are what
it was trained to produce. An explicit refusal phrase gives you something to grep for later
when you audit whether the instruction actually worked.

**Conflicting or duplicate chunks** are the other case worth handling on purpose rather than by
accident. Retrieval frequently returns two chunks that say almost the same thing, an older and
a newer revision of the same clause, or two engineering handbooks that specify a slightly
different torque value for the same fastener, and a generation prompt that hands both over with
no guidance will produce an answer that arbitrarily favors whichever chunk happened to appear
first in the context. Preferring the chunk with the most recent revision tag, deduplicating
near-identical chunks before they reach the prompt, or explicitly asking the model to note a
conflict rather than silently pick one are all better than leaving the choice to whatever the
model's attention happens to favor.

## Evaluating retrieval, separately from evaluating the answer

```{index} gold set, LLM-as-judge
```
```{index} pair: metric; Recall@k
```
```{index} pair: metric; MRR
```
```{index} pair: metric; nDCG
```

The single most common mistake in building a RAG system is judging it by reading the final
answers and deciding whether they sound right. That skips the one measurement that tells you
where a failure actually lives: if the retriever did not return the right chunk, no generation
strategy can produce a correct, grounded answer, and a good-sounding answer produced despite
bad retrieval is luck: the system still failed, it just did not look like it failed.

Retrieval evaluation needs a **gold set**: a list of queries paired with the chunk or chunks
that actually answer each one, built by a human who knows the corpus, the same discipline this
session's demo uses at a toy scale with 15 queries. Four metrics, all standard information
retrieval measures rather than anything RAG-specific, cover what you need. **Recall@k** asks
whether a relevant chunk appears anywhere in the top k results, the most basic and most
important question, since nothing downstream can succeed if the answer was never retrieved at
all. **Precision@k** asks what fraction of the top k is actually relevant, which matters
because irrelevant chunks in the context are not free, they compete for the generation model's
attention and for your context budget. **MRR** (mean reciprocal rank) rewards ranking the first
relevant result higher, averaged across queries. **nDCG** (normalized discounted cumulative
gain) generalizes that idea to reward the whole ranking, not just the first hit, discounting a
relevant result more the further down the list it appears.

Keep **answer-quality metrics** conceptually and practically separate from these. Faithfulness
(does the generated answer actually follow from the retrieved context, rather than adding
something the context never said), correctness (is the answer actually right), and citation
validity (does the cited chunk actually support the claim attached to it) are properties of the
generation step, and a system can score well on retrieval metrics while still failing every one
of them if the generation step ignores its instructions. [RAGAS](https://docs.ragas.io/), from
Es and colleagues' 2023 paper, is one attempt to standardize this vocabulary and offers a
worked set of these metrics if you want a starting point rather than building your own.

**LLM-as-judge**, using a second language model call to score faithfulness or correctness
because no simple string match can, is worth introducing here as a tool you will reach for, with
one caveat stated plainly now and addressed later in the course: a judge model has its own
biases and blind spots, and treating its score as ground truth without ever checking it against
human judgment just moves the trust problem rather than solving it.

## Where this pushes back

RAG is a genuine fix for ungrounded generation, and it introduces failure modes of its own that
are easy to miss precisely because the system appears to be working.

**A confident wrong answer looks identical to a confident right one.** Nothing about a fluent,
well-cited-looking answer distinguishes a case where retrieval actually found the right chunk
from a case where it confidently found the wrong one, unless you specifically built and ran
the retrieval evaluation from the previous section. A RAG system without a retrieval eval is
not obviously safer than no RAG system at all: its failures now come with a citation attached,
which can make them more convincing.

**Long context is not a free substitute for retrieval, and it has its own failure mode.** With
context windows now reaching hundreds of thousands of tokens, the obvious question is why chunk
and retrieve at all instead of pasting the whole corpus into every prompt. Cost is one answer,
you pay per token on every call regardless of whether the model needed most of them. A second,
less obvious answer is that models do not read a long context uniformly: Liu and colleagues'
2023 study "Lost in the Middle" found that model accuracy on a fact embedded in a long context
is reliably higher when that fact sits near the beginning or end of the context and measurably
worse when it sits in the middle, regardless of how relevant the fact actually is. A shorter,
retrieval-curated context is cheaper and, for exactly this reason, can be more reliable too.

**Embedding-model and index mismatch fails silently.** Re-embedding a query with a different
model than the one used to build the index does not raise an error. It just returns nearest
neighbors in a space the query vector was never placed in correctly, and every retrieval
quietly degrades with no exception to catch. Pin the embedding model as part of your index's
own version metadata, the same discipline as pinning a random seed or a library version
elsewhere in this course.

**Chunking is a lossy transformation you cannot fully undo downstream.** No amount of clever
re-ranking recovers a fact that structure-blind chunking already split across two chunks at
ingestion time. Money spent getting chunking right the first time buys more than the same
money spent on a fancier retriever afterward.

**Hybrid and re-ranking add real operational cost for a real gain.**
Maintaining two indexes, or adding a cross-encoder pass, is more moving parts, more latency,
and more to keep synchronized when the corpus updates. Measure the recall and nDCG gain against
your actual gold set before adding either; a corpus small and clean enough that plain dense
retrieval already hits recall@k near 1.0 has nothing left for a re-ranker to improve.

:::{admonition} What a practitioner should take from this
:class: tip

Build the retrieval gold set and measure recall@k before you ever judge a generated answer.
Treat a similarity score as a measure of topical closeness, never as a confidence score, and
put the "answer only from context, or say you cannot" instruction, and a check that it was
followed, at the generation step where it belongs. A RAG system's citations make its failures
look more trustworthy. That is why the evaluation has to be a measurement, not a glance at
whether the answers sound plausible.
:::

## In-class demo

We build one small RAG pipeline over a constructed engineering-manual corpus end to end:
structure-aware and naive fixed-size chunking, a dense index (FAISS, over embeddings built
without any network access this notebook could rely on) alongside a BM25 keyword index,
retrieval evaluated against a 15-query gold set with recall@k, precision@k, MRR, and nDCG, a
chunking sweep that measures the fixed-versus-structure-aware gap directly rather than asserting
it, and a walk through one query the retriever gets confidently wrong to show why a similarity
threshold cannot rescue you and why the grounding instruction belongs in the prompt sent to
generation. There is no hosted LLM call in this notebook; it assembles and shows you the exact
grounded prompt a real model would receive, which is as far as a network-free notebook can take
the generation step. Assignment 9 is where you connect that prompt to an actual model and measure what
comes back.

The runnable notebook is [`l17-rag.ipynb`](l17-rag.ipynb). It requires no external data
download and no API key; everything it measures runs locally.

## Summary

A language model asked a factual question with nothing to ground it will answer anyway, fluently
and often wrong, and Air Canada's chatbot is what that costs when the question was one a real
document already answered correctly. Retrieval-augmented generation's whole argument is that an
answer traceable to a retrievable source is worth building deliberately: chunk a corpus with its
own structure in mind rather than an arbitrary token count, index it in a vector index sized to
your actual scale, retrieve with dense, keyword, or hybrid search depending on whether your
queries are paraphrases or exact identifiers, and instruct the generation step, explicitly and
checkably, to answer only from what it was given. None of that is safe to assume works until you
measure it, and retrieval evaluation, recall@k first, is the measurement this whole argument
depends on. Next session turns the question around: given prompting, RAG, and
fine-tuning all on the table, which one actually fits a given engineering task, and what does a
LoRA fine-tune on the course GPU look like when behavior, not knowledge, is what needs fixing.

## Resources

- [Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"](https://arxiv.org/abs/2005.11401),
  NeurIPS 2020. The paper that named the architecture this whole session is built around.
- [Karpukhin et al., "Dense Passage Retrieval for Open-Domain Question Answering"](https://arxiv.org/abs/2004.04906),
  EMNLP 2020. The result that made dense retrieval the default over classical keyword search
  for open-domain QA.
- [Es et al., "RAGAS: Automated Evaluation of Retrieval Augmented Generation"](https://arxiv.org/abs/2309.15217),
  2023. A working vocabulary and toolkit for the faithfulness/answer-relevance/context-relevance
  metrics this session only introduces.
- [Liu et al., "Lost in the Middle: How Language Models Use Long Contexts"](https://arxiv.org/abs/2307.03172),
  2023. The primary source for the long-context accuracy dip discussed in the limitations
  section; read this before deciding retrieval is unnecessary because your context window is big.
- [FAISS documentation](https://faiss.ai/). The in-process vector index used in this session's
  demo; start with the "Getting started" guide.
- [Chroma documentation](https://docs.trychroma.com/) and [Qdrant documentation](https://qdrant.tech/documentation/).
  Two purpose-built vector databases with a server model, for when an in-process index stops
  being enough.
- [pgvector](https://github.com/pgvector/pgvector). Vector search as a Postgres extension,
  worth reading against your Week 2 notes on when a relational database is already the right
  home for your data.
- [Moffatt v. Air Canada, 2024 BCCRT 149](https://www.canlii.org/en/bc/bccrt/doc/2024/2024bccrt149/2024bccrt149.html).
  The tribunal decision behind the case study above; short and worth reading in full.

## Assignment

Assignment 9, "RAG system over an engineering corpus," is released this session and due roughly one week
later. It asks you to build a retrieval-augmented QA system over an engineering corpus and
measure, not assume, both retrieval quality and answer quality against a gold set, connecting
the assembled grounded prompt this session's demo stops at to an actual hosted-LLM call. This
paragraph is a pointer, not the rubric.
