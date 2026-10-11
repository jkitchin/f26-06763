# Chat with the course notes (L18 capstone)

A retrieval-augmented generation pipeline over the released lecture notes and slides that runs
entirely in a browser tab: no server, no API key, no account. It is the capstone of L18 (context
engineering), and every stage of it is a block students met earlier in that lecture.

## The pipeline, block by block

| Block | Runs | What it does | Cost |
|---|---|---|---|
| Chunk | CI, `tools/rag_index.py` | Splits each released `notes.md` at H2/H3 headings (long sections again at paragraphs, heading repeated) and each `slides.md` at `---`, one chunk per slide, keeping lecture, section and a link | ~1,200 chunks for L1 to L17, 1.3 MB of text |
| Embed | CI, `chat/embed.mjs` | `Xenova/all-MiniLM-L6-v2`, dtype q8, mean pooling, unit length; stored as int8 with one scale per vector | ~3 min on a laptop CPU; 1.9 MB index |
| Load | Browser | Fetches `rag-index.json`, decodes the vectors | ~60 ms |
| Keyword | Browser | MiniSearch (BM25+) over section titles and text, built in the tab | ~5 ms |
| Embed query | Browser | The same model and dtype through transformers.js, which the index records and the page checks | ~25 ms after a one-time 23 MB model download |
| Vector | Browser | Exact cosine against every chunk (int8 dot products) | ~3 ms |
| Fuse | Browser | Reciprocal rank fusion, 1 / (60 + rank), of the two top-20 lists | under 1 ms |
| Rerank (optional) | Browser | Cross-encoder `Xenova/ms-marco-MiniLM-L-6-v2` over the top 12, 256 tokens each; a top score below zero is reported as "probably not in the notes" | a few seconds on CPU; 23 MB download |
| Prompt | Browser | Top 5 passages, numbered, between two copies of the question, inside a fixed instruction; shown verbatim | none; about 1,100 to 1,600 tokens |
| Gate | Browser | If the best cosine is below 0.285, or the best cross-encoder score is below −6, answer "Not in the notes" and do not call the model | none |
| Generate | Browser, WebGPU | WebLLM running `Qwen2.5-1.5B-Instruct-q4f16_1-MLC` (or the `data-model` override), loaded only on a button press | ~1.6 GB of GPU memory; 5 s from cache; ~25 s per answer (Llama 3.2 1B: 7 to 19 s) |

Times were measured in headless Chrome on an Apple-silicon Mac (reranking: 3.2 s for 12 pairs); treat them as orders of magnitude.

## Why it is built this way

- **One model, two runtimes avoided.** The chunks are embedded at build time with transformers.js
  in Node, the query in the browser with transformers.js, same version (pinned in
  `package.json` and in `rag-chat.js`), same model and dtype. A Python embedding of the index
  and a JavaScript embedding of the query would disagree by enough to reorder close results.
- **Built at deploy, never committed.** The index is a function of what `_toc.yml` releases, so
  CI builds it (`book.yml`, "Build the course-notes chat index") and copies it beside any
  released deck that contains `class="rag-chat"`. It cannot go stale, and it cannot contain an
  unreleased lecture or anything from `course/modules/`.
- **Exact search, on purpose.** 1,200 dot products of length 384 take milliseconds. An
  approximate index would add code and lose recall for nothing at this size; the lecture's
  tuning section says where that changes.
- **Abstention is code, not a prompt.** Told to reply "Not in the notes" when the passages do not
  answer, Llama 3.2 1B instead defined LoRA, wrongly, from passages about something else. The
  gate decides from the retrieval scores before the model is called. Its thresholds were
  calibrated on the L18 gold set (`lectures/l18/figures/make_figures.py`, group ladder): they catch
  three of four out-of-corpus questions and refuse none of the 24 answerable ones, by margins of a
  few hundredths. A cross-encoder cutoff of 0, the obvious choice, would have refused seven
  answerable paraphrases.
- **A 1B model is a weak reader.** With the right passages it produced a substantively correct
  answer on one run and, after a prompt change, an answer that inverted the passages. The
  capstone is for seeing the pipeline; students should read the passages and the prompt, not
  trust the answer. Qwen2.5 1.5B, the default since 2026-10-11, answered the same question
  correctly in two sentences in the passage's own terms (one run each, so anecdotal);
  `data-model="Llama-3.2-1B-Instruct-q4f16_1-MLC"` restores the smaller model for comparison.
- **Generation is optional.** Without WebGPU, or before the model loads, the widget stops after
  the prompt and shows the passages with links. Retrieval is the part worth inspecting.

## The network exception

`_static/widgets.js` promises no network access. This module does not: it loads
transformers.js, MiniSearch and WebLLM from jsDelivr, and model weights from the Hugging Face
Hub, the first time each is needed, and the browser caches them. That is deliberate and limited
to this capstone. WebGPU also requires a secure context, which the site has had since HTTPS was
enforced on 2026-08-08 (CLAUDE.md section 8); a page served over plain HTTP would see no
`navigator.gpu` and fall back to retrieval only.

**Measured** (headless Chrome, Apple silicon): a 1,529-token prompt and a short answer took
12.8 s, so prompt processing runs at roughly 100+ tokens per second once the model is warm.

**First load is slow.** On the development machine the Llama 3.2 1B weights downloaded at about
0.6 MB/s from the Hugging Face CDN (242 MB in 379 s), so a first load takes on the order of
15 to 20 minutes; later loads come from the cache in seconds. Load the model on the projector
machine before class, and do not ask a room of students to download it at once over one network.

## Building and testing locally

```bash
python tools/rag_index.py --lectures l01-l17      # or no flag: whatever _toc.yml releases
(cd chat && npm ci && node embed.mjs)            # writes chat/build/rag-index.json
python3 -m http.server -d chat 8016              # modules and fetch do not work from file://
# open http://localhost:8016/demo.html; demo.html?q=... runs one query on load
```

To author the L18 deck locally, symlink the module and the index beside it (both are
gitignored, like the clicker's):

```bash
ln -s ../../chat/rag-chat.js lectures/l18/rag-chat.js
ln -s ../../chat/build/rag-index.json lectures/l18/rag-index.json
```

## Changing things

- **The embedding model**: change `MODEL` in `embed.mjs`, rebuild, and nothing else; the page
  reads the model name from the index. Changing the transformers.js version means changing it in
  `package.json` and `TRANSFORMERS_VERSION` in `rag-chat.js` together; the page refuses an index
  built with a different version.
- **The generator**: `LLM` in `rag-chat.js`. WebLLM's prebuilt list gives the GPU memory each
  needs; Llama 3.2 1B (879 MB) and Qwen2.5 1.5B (1,630 MB) are the sensible range for laptops.
- **Chunking**: `MAX_WORDS` and `MIN_WORDS` in `tools/rag_index.py`. Measure a change on the L18
  gold set before keeping it.
