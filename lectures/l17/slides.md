---
marp: true
theme: course
paginate: true
header: "06-763 · L17"
footer: "Systems and Toolchains for AI Engineers"
---

<!-- _class: title -->

# L17 · Retrieval-augmented generation & vector databases

## Week 10 · LLM & agentic engineering

**Systems and Toolchains for AI Engineers**

---

## Roadmap

1. Why this matters: a chatbot, a policy, a tribunal
2. The anatomy of a RAG pipeline
3. Chunking strategy
4. Vector databases and indexes
5. Retrieval mechanics: dense, keyword, hybrid
6. Grounding the generation
7. Evaluating retrieval, separately from the answer
8. Live demo: one pipeline, measured end to end

<!-- 110 min. Budget roughly 10/15/15/10/15/15/15/15 demo.
     No hosted LLM call in the demo -- no network in the build environment.
     The demo assembles and shows the grounded prompt instead of calling a model.
     If running long, cut the vector-DB options slide, not the demo. -->

---

<!-- _class: section -->

# Why this matters

---

## Why this matters

2022: Jake Moffatt asks Air Canada's chatbot about
bereavement fares.

Bot: book now, apply for the discount within 90 days
**after** travel.

**The airline's actual policy.**

Discount had to be requested **before** travel.

Air Canada refused the refund. Case went to
Canada's Civil Resolution Tribunal.

---

## Why this matters, air Canada's defense

The chatbot was "a separate legal entity ...
responsible for its own actions."

The customer should have checked the real
policy page himself.

---

## Why this matters, the tribunal's answer

February 2024: "a remarkable submission."

A company is responsible for all the information
on its website, chatbot or static page.

[Moffatt v. Air Canada, 2024 BCCRT 149](https://www.canlii.org/en/bc/bccrt/doc/2024/2024bccrt149/2024bccrt149.html)

---

## Why this matters, the engineering failure, precisely

A factual question about a document that
**already existed, in full, retrievably**.

The model answered from training-data pattern
instead of being shown the actual policy.

---

## Why this matters, not lying. Doing exactly what it does.

No source to constrain it →
plausible, fluent, fluent-and-wrong text.

**Plausible** and **correct** are different
properties that often coincide. Not always.

---

## Why this matters, what RAG actually buys you

Not "smarter." **Traceable to a source
a human can go check.**

Plus: freshness (update the doc, not the model)
and cost (retrieve 3 paragraphs, not fine-tune).

**Why not just use a huge context window?.**

Billed per token, every call, whether the
model needed most of them or not.

And: a model doesn't read a long context
uniformly. More on this later.

---

<!-- _class: section -->

# Anatomy of a RAG pipeline

---

## Anatomy of a RAG pipeline

<div class="definition">

**Retrieval-augmented generation**: retrieving passages from your own corpus and putting them in the context, so the model answers from them rather than from memory.

</div>

**Ingestion** (offline, once per doc change):
load → clean → chunk → embed → index

**Query** (online, once per question, user waiting):
embed query → retrieve top-k → assemble prompt → generate + cite

---

## Anatomy of a RAG pipeline, where the name comes from

Lewis et al., NeurIPS 2020: "Retrieval-Augmented
Generation for Knowledge-Intensive NLP Tasks"

A retriever scoring documents against a query +
a generator conditioned on the query **and** what came back.

[arxiv.org/abs/2005.11401](https://arxiv.org/abs/2005.11401)

---

## Anatomy of a RAG pipeline, what's changed since 2020

Embeddings better. Indexes faster.
Context windows longer.

The two-path shape, and the reason for it,
hasn't moved.

---

<!-- _class: section -->

# Chunking strategy

---

## Chunking strategy

<div class="definition">

**Chunk**: the unit you embed and retrieve. Too large and the match is diluted; too small and the passage loses the context that made it meaningful.

</div>

Too large → one query drags in unrelated clauses,
dilutes the signal.

Too small → a fact loses the context that
makes it unambiguous.

---

## Chunking strategy, fixed-size chunking

Pick a token count (256? 1024?), cut there,
overlap a bit at the boundary.

Trivial to implement. **Blind to the document's
own structure.**

**Why that's bad for engineering docs.**

A fixed window doesn't know clause 4.2 ends
where it ends.

It will, with regularity, split a table row:
a bolt size, severed from its torque value.

---

## Chunking strategy, structure-aware chunking

One chunk per section, per clause, per table.
Uses the document's own boundaries.

Costs a parser instead of a token counter.
Never splits a fact in half.

---

## Chunking strategy, measured, not asserted

15-query gold set, this session's demo:

| Chunking | recall@3 | nDCG@3 |
|---|---|---|
| Structure-aware | ~1.00 | ~0.95 |
| Naive fixed (crosses clause + doc bounds) | ~0.93 | ~0.6-0.7 |

---

## Chunking strategy, what the two real misses look like

One: a value stitched into a mostly-irrelevant
neighboring window.

One: a table row's size-and-radius pair,
split across a chunk boundary.

Neither subtle once you read the retrieved text.
Both invisible in an aggregate score alone.

---

## Chunking strategy, keep metadata with every chunk

Source document. Section/clause number.
Page. **Revision.**

A citation with no section number isn't
a citation a reader can check.

**The pitfall: silent truncation.**

Chunk built without checking the embedding
model's max input length?

No error. The last third of a long clause
just never makes it into the vector.

---

<!-- _class: section -->

# Vector databases and indexes

---

## Vector databases and indexes

<div class="definition">

**Approximate nearest neighbour**: an index that trades exact recall for speed, returning most of the true nearest vectors in a fraction of the time.

</div>

**Approximate nearest-neighbor search** at scale.
**Metadata filtering** (current revision only).
**Persistence** past one Python process.

---

## Vector databases and indexes, name the real options

**FAISS**: a library, in-process, no server.
**Chroma / Qdrant**: purpose-built vector DBs, a server, filtering built in.
**pgvector**: a Postgres extension, no second database to operate.

---

## Vector databases and indexes, pick by access pattern, not hype

| | FAISS | Chroma/Qdrant | pgvector |
|---|---|---|---|
| Ops model | none, in-process | dedicated server | your existing Postgres |
| Fits | fits-in-memory corpora | multi-process, growing scale | already-Postgres shops |

---

## Vector databases and indexes, exact vs. approximate

**Exact**: check every vector. Always right.
Cost grows linearly with corpus size.

**Approximate (ANN)**: small, tunable miss chance.
Near-flat latency into the millions of vectors.

---

## Vector databases and indexes, when the trade-off starts to matter

Thousands to low millions of chunks:
exact search is often fast enough already.

Add ANN complexity when exact latency would
already be noticeable to a user.

---

<!-- _class: section -->

# Retrieval mechanics

---

## Retrieval mechanics

Same vector space, query and chunk both embedded.
Rank by cosine similarity.

"Leak" retrieves "seepage." No shared vocabulary needed.

[Karpukhin et al., DPR, EMNLP 2020](https://arxiv.org/abs/2004.04906)

---

## Retrieval mechanics, keyword retrieval: BM25

Score by exact term overlap, weighted by
how rare each term is corpus-wide.

Can't see past a paraphrase.
**Exact where dense retrieval is fuzzy.**

---

## Retrieval mechanics, when you want BM25, specifically

A query for a part number, an error code,
a clause number.

"Similar to part 4471-B" isn't a coherent idea.

**Hybrid: run both, combine rankings.**

Catches the paraphrase case **and**
the exact-identifier case.

Cost: two indexes, a combination rule.

---

## Retrieval mechanics, re-ranking with a cross-encoder

Retriever scores each chunk **independently**,
cheaply, across the whole corpus.

Cross-encoder scores query + **one** candidate
**jointly**, sees interactions, too slow at scale.

**The standard two-stage pattern.**

Fast retriever → narrow to ~dozens of candidates.

Slow cross-encoder → re-rank just those.
Spend the expense only where you can afford it.

---

<!-- _class: section -->

# Grounding the generation

---

## Grounding the generation

<div class="definition">

**Grounding**: instructing the model to answer only from the retrieved context, and treating an unsupported claim as a failure.

</div>

The generation step has to be told, explicitly,
to use what it was given, not what it remembers.

---

## Grounding the generation, why a similarity threshold can't do this job

A PVC-conduit question retrieves an RMC-conduit
chunk at a score **indistinguishable** from genuine matches.

The wrong document isn't an unrelated one.
No pre-generation number tells them apart.

---

## Grounding the generation, the instruction has to be explicit

> Answer only from the provided context.
> Cite the section for every claim.
> If it's not there, say so, in fixed words.

Enforced by the model **reading**, not a number.

---

## Grounding the generation, why "fixed words" matters

A model told only to "be careful" still often
produces something plausible-sounding.

An exact refusal phrase gives you something
to grep for when you audit later.

---

## Grounding the generation, conflicting or duplicate chunks

Two chunks, almost the same claim: an old and
a new revision, or two manuals disagreeing.

Hand both over with no guidance →
the model arbitrarily favors whichever came first.

**Handle it on purpose.**

Prefer the chunk with the newer revision tag.
Deduplicate near-identical chunks before the prompt.

Or: ask the model to name the conflict explicitly.

---

<!-- _class: section -->

# Evaluating retrieval

---

## Evaluating retrieval

<div class="definition">

**Recall@k and nDCG**: whether the right passage is in the top k at all, and how highly it is ranked when it is.

</div>

Judging a RAG system by reading the final
answers and deciding if they sound right.

Skips the one measurement that shows
**where** a failure actually lives.

---

## Evaluating retrieval, build a gold set

Queries paired with the chunk(s) that actually
answer each one. A human who knows the corpus writes it.

This session's demo: 15 queries, toy scale, same discipline.

---

## Evaluating retrieval, four retrieval metrics

**recall@k**: is the answer anywhere in the top k
**precision@k**: what fraction of top k is relevant
**MRR**: how high does the first hit rank
**nDCG**: rewards the whole ranking, not just the first hit

---

## Evaluating retrieval, keep answer-quality metrics separate

**Faithfulness**: does the answer follow from the context
**Correctness**: is it actually right
**Citation validity**: does the cited chunk support the claim

A system can ace retrieval and fail all three.

---

## Evaluating retrieval, RAGAS: a starting vocabulary

Es et al., 2023: faithfulness, answer relevance,
context relevance, worked out as metrics.

Not mandatory. A reasonable place to not start from scratch.

[docs.ragas.io](https://docs.ragas.io/)

---

## Evaluating retrieval, LLM-as-judge: a tool, with a caveat

A second model call scores faithfulness because
no string match can.

It has its own biases. Trusting it blindly just
moves the trust problem. (Full treatment: Week 12.)

---

<!-- _class: section -->

# Where this pushes back

---

## Where this pushes back

Nothing about a fluent, cited-looking answer
tells you retrieval quietly failed.

A RAG system with no retrieval eval is not
obviously safer than no RAG at all.

---

## Where this pushes back, long context isn't a free substitute

Cost: billed per token, every call.

Liu et al. 2023, "Lost in the Middle": accuracy on
a fact **drops** when it sits mid-context, regardless of relevance.

[arxiv.org/abs/2307.03172](https://arxiv.org/abs/2307.03172)

---

## Where this pushes back, embedding/index mismatch fails silently

Re-embed a query with a different model than
built the index?

No error. Nearest neighbors in a space the
query was never correctly placed in.

**Pin the embedding model.**

Same discipline as a pinned random seed
or a pinned library version, elsewhere in this course.

---

## Where this pushes back, chunking is lossy, and not undoable downstream

No re-ranker recovers a fact that structure-blind
chunking already split at ingestion.

Money spent on chunking beats the same money
spent on a fancier retriever after the fact.

---

## Where this pushes back, hybrid + re-ranking: real cost, not a free upgrade

More indexes. More latency. More to keep in sync.

Measure the recall/nDCG gain against your gold set
before adding either.

**What a practitioner should take from this.**

Build the gold set and measure recall@k **before**
judging any generated answer.

A similarity score is topical closeness,
never a confidence score.

---

<!-- _class: demo -->

# Demo

## `l17-rag.ipynb`

Chunk two ways, index with FAISS + BM25,
evaluate on a 15-query gold set, sweep chunking, ground.

---

## What to watch

- Structure-aware vs. naive fixed: recall and nDCG, measured
- The PVC-conduit miss: score 0.827, sitting inside the true-match range
- The assembled grounded prompt: what a real model would receive
- No hosted LLM call here, that's A9

---

## Recap

- A model with nothing to ground it answers anyway, plausible, not necessarily correct
- Chunk with the document's own structure; a fixed token count doesn't know where a clause ends
- Dense retrieval for paraphrase, BM25 for exact identifiers, hybrid for both
- A similarity threshold cannot substitute for an explicit "answer only from context" instruction
- Measure recall@k before you ever judge a generated answer

---

## Next

**Assignment** A9 released today, due ~1 week
**Reading** Lewis et al. 2020 (RAG); Liu et al. 2023 (Lost in the Middle)
**L18** Prompting vs. RAG vs. fine-tuning: a decision framework,
plus a real LoRA fine-tune on the course GPU

Full notes, with all sources: `lectures/l17/notes.md`
