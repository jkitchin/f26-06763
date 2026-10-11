---
marp: true
theme: course
paginate: true
header: "06-763 · L18"
footer: "Systems and Toolchains for AI Engineers"
---

<style>
section p:has(> img:only-child) { text-align: center; }
section table { margin-left: auto; margin-right: auto; font-size: 0.74em; }
.source { font-size: 0.6em; color: #5c5c5c; }
.pt { color: #c41230; font-size: 0.8em; margin-right: 0.35em; }
</style>

<!-- _class: title -->

# Lecture 18: Context engineering, tools, search and retrieval

## Week 9, LLM and agentic engineering

<!-- 90 minutes of lecture, then the notebook and questions.
     Draft deck: the capstone section is complete; the sections before it are written from the
     notes, which come first. -->

---

## Roadmap

1. Why the context window decides the answer
2. Fetching context with tools
3. Keyword search over a document store
4. Semantic search
5. Reranking and late interaction
6. Tuning and scaling
7. Assembling and measuring the context
8. **Capstone: chat with the course notes**
9. Limitations and trade-offs

---

<!-- _class: section -->

# Capstone: chat with the course notes

<!-- 10 min. Load the model on this machine BEFORE class: the first download is 15 to 20
     minutes; from the browser cache it takes about 5 s. -->

---

## Capstone, at build time

Every block from today, running with no server and no API key. Two run once, in CI:

| Block | How | Cost |
|---|---|---|
| Chunk | the **released** notes and slides, split by section; one chunk per slide | 1,219 chunks for L1 to L17 |
| Embed | all-MiniLM-L6-v2 (384 dims) in transformers.js; stored as int8 | 1.9 MB index, ~3 min |

- Built at every deploy from `_toc.yml`: an unreleased lecture can never be retrieved
- <span class="pt">▶</span> the index is a build artifact of the course, like the slides themselves

---

## Capstone, in the browser

| Block | How | Cost |
|---|---|---|
| Keyword | BM25 (MiniSearch), built in the tab | ~5 ms |
| Embed query | same model, same runtime as the build | ~25 ms |
| Vector | exact cosine against every chunk | ~3 ms |
| Fuse | reciprocal rank fusion, 1 / (60 + rank) | < 1 ms |
| Rerank (optional) | cross-encoder over the top 12 | ~3 s |
| Gate | weak scores → "Not in the notes", model not called | 0 |
| Generate | WebLLM on WebGPU, Qwen2.5 1.5B (~1.6 GB) | ~25 s |

- <span class="pt">▶</span> retrieval takes milliseconds; the model is the slow, expensive, unreliable block

<!-- Times measured in Chrome on an Apple-silicon Mac. -->

---

## Capstone, live

<div class="rag-chat compact" data-index="rag-index.json"></div>

<!-- Try, in order: "what does forgetting zero_grad do" (keyword wins), "why can't I shuffle
     sensor data before splitting" (paraphrase: vectors find it), the same with rerank on, then
     "what is LoRA fine-tuning" (not in the notes: the gate stops it). Open "the exact prompt". -->

---

## Capstone, what to look at

- **The strip**: which blocks ran, and how long each took
- **The ranks**: BM25 rank, vector rank, and RRF for every passage
  - `zero_grad`: keyword rank 1; a paraphrase question: vector rank 1
- **The prompt**: the exact text the model reads, five numbered passages and the question twice
- **The gate**: an out-of-corpus question never reaches the model
- <span class="pt">▶</span> read the passages and the prompt before you read the answer

---

## Capstone, model size matters

Same passages and question ("why can't I shuffle sensor data before splitting?"), one run each:

- **Llama 3.2 1B**: only `[1] [2]`; after a prompt fix, one right answer and one **inverted**
- **Qwen2.5 1.5B**: a correct two-sentence answer in the passage's own terms
- On LoRA (not in the notes), Llama 3.2 1B invented a definition
- So "Not in the notes" is decided **in code**, from retrieval scores, before the model runs
- <span class="pt">▶</span> small models read unreliably: guard them with scores, not instructions

---

## Capstone, where each piece lives

- **Same embedding model at build and in the browser**: another runtime would reorder close results
- **Exact search**: 1,219 dot products take milliseconds; an approximate index would only lose recall
- **Network**: libraries and weights download once, then come from the cache; WebGPU needs HTTPS
- **No WebGPU?** The chat stops after the prompt and shows the passages and links
- <span class="pt">▶</span> each choice is a tuning trade-off, made for 1,200 chunks and one user

<span class="source">[WebLLM](https://github.com/mlc-ai/web-llm) · [transformers.js](https://huggingface.co/docs/transformers.js/index) · [MiniSearch](https://github.com/lucaong/minisearch) · [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) · [Cormack et al. 2009, RRF](http://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf)</span>

<script type="module" src="rag-chat.js"></script>
