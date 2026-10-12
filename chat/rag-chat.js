/* Chat with the course notes: the L18 capstone, a retrieval-augmented generation pipeline that
 * runs entirely in the browser tab.
 *
 *     <div class="rag-chat" data-examples="what does forgetting zero_grad do|what is LoRA fine-tuning">
 *       fallback text, shown only where scripts do not run
 *     </div>
 *     <script src="rag-index.js"></script>
 *     <script src="rag-chat.js"></script>
 *
 * Plain scripts, not modules, so the page works opened straight from disk (file://) as well as
 * from a web server: browsers refuse module scripts and fetch() of local files on file:// pages,
 * but run classic scripts, and import() from a CORS-enabled CDN still works there. The index is
 * read from window.RAG_INDEX (rag-index.js); data-index="rag-index.json" fetches it instead.
 *
 * data-examples (optional, separated by |) adds one-click example questions; data-model picks
 * the generator. Anything inside the element is a fallback for viewers that do not run scripts
 * (an editor preview, a PDF export) and is removed on mount.
 *
 * Every stage is drawn as a block in a strip at the top of the widget, lit while it runs and
 * labeled with its time, because the point of the capstone is to see the pipeline, not only the
 * answer:
 *
 *   index    load chat/build/rag-index.json: the released notes and slides, chunked by section,
 *            each with a 384-dimension embedding computed at BUILD TIME (chat/embed.mjs)
 *   keyword  BM25 over the chunk text with MiniSearch, built in the tab from the same chunks
 *   embed    the query, with the same model, dtype and pooling as the build (transformers.js)
 *   vector   exact cosine against every chunk: 1,200 dot products is cheaper than any index
 *   fuse     reciprocal rank fusion of the two rankings, 1 / (60 + rank)
 *   rerank   optional: a cross-encoder reads the query and each of the top 20 together
 *   prompt   the top passages, numbered, inside a fixed instruction; shown verbatim
 *   generate WebLLM, a 1B-parameter model on the GPU through WebGPU, loaded only on request
 *
 * Without WebGPU (or before the model is loaded) it stops after "prompt" and shows the passages
 * and their links, which is the part of the pipeline worth inspecting anyway.
 *
 * NETWORK. Unlike _static/widgets.js, which promises no network access, this fetches libraries
 * and model weights from public CDNs on first use: transformers.js and the embedding model
 * (~23 MB), MiniSearch, and, only when asked, WebLLM and a model of about 0.9 GB. The browser
 * caches them. Versions are pinned here, and the embedding model must match the build's, which
 * the index records and this file checks.
 */

(function () {
'use strict';

const LIB = {
  transformers: 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.1',
  minisearch: 'https://cdn.jsdelivr.net/npm/minisearch@7.2.0/+esm',
  webllm: 'https://esm.run/@mlc-ai/web-llm@0.2.86',
};
const TRANSFORMERS_VERSION = '4.3.1';
const RERANKER = 'Xenova/ms-marco-MiniLM-L-6-v2';
// The generator. data-model on the element overrides the default, so a deck or the test page can
// compare models without editing this file. GPU memory figures are WebLLM's (vram_required_MB).
const MODELS = {
  'Llama-3.2-1B-Instruct-q4f16_1-MLC': 'Llama 3.2 1B, about 0.9 GB of GPU memory',
  'Qwen2.5-1.5B-Instruct-q4f16_1-MLC': 'Qwen2.5 1.5B, about 1.6 GB of GPU memory',
};
// Qwen2.5 1.5B by default: in testing it answered the leakage question correctly and briefly,
// where Llama 3.2 1B produced citation markers, an inverted answer, or an invented one.
const DEFAULT_MODEL = 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC';
const RRF_K = 60, POOL = 20, RERANK_N = 12, TOP = 5, WORDS_PER_PASSAGE = 220;
// The abstention gate. A small model told to say "Not in the notes" when the passages do not
// answer will still invent an answer, so the decision is made here, in code, from retrieval
// scores. The thresholds were calibrated on the L18 gold set (lectures/l18/figures, group
// ladder): out-of-corpus questions scored a best cosine of 0.28-0.35 and a best cross-encoder
// logit of -2.7 to -9.4; answerable ones 0.29-0.69 and -4.6 to 8.2. A cosine below 0.285 or a
// cross-encoder logit below -6 caught 3 of 4 out-of-corpus questions and refused none of the
// 24 answerable ones. The margins are thin and the values belong to this corpus and these models.
const MIN_COS = 0.285, MIN_CE = -6;

// Written for a 1B-parameter model, which follows simple, concrete instructions and copies
// formats it is shown. An earlier version that stressed "cite as [1], [2]" got answers made of
// nothing but citation markers.
const SYSTEM = 'You are a teaching assistant for a university course. Answer the question in two ' +
  'or three plain sentences, using only the passages you are given. End each sentence with the ' +
  'number of the passage it came from in square brackets, like [2]. ' +
  'If the passages do not answer the question, reply with exactly: Not in the notes.';

const STAGES = [
  ['index', 'index', 'build time: chunks + embeddings'],
  ['keyword', 'keyword (BM25)', 'MiniSearch'],
  ['embed', 'embed query', 'transformers.js'],
  ['vector', 'vector search', 'cosine, exact'],
  ['fuse', 'fuse (RRF)', '1 / (60 + rank)'],
  ['rerank', 'rerank', 'cross-encoder'],
  ['prompt', 'assemble prompt', 'top 5 passages'],
  ['generate', 'generate', 'WebLLM, WebGPU'],
];

const CSS = `
.rag{--a:#1f6fb2;--hot:#c41230;--mut:rgba(128,128,128,.35);font-size:15px;line-height:1.35;border:1px solid var(--mut);
  border-radius:6px;padding:.6em .8em;background:rgba(128,128,128,.05)}
.rag-strip{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:.5em}
.rag-stage{flex:1 1 0;min-width:88px;border:1px solid var(--mut);border-radius:5px;padding:3px 5px;font-size:12px;background:#fff}
.rag-stage b{display:block;font-size:12px}.rag-stage i{font-style:normal;opacity:.65}
.rag-stage.run{border-color:var(--hot);box-shadow:0 0 0 2px rgba(196,18,48,.25)}
.rag-stage.done{border-color:var(--a)}.rag-stage.skip{opacity:.4}
.rag-stage .t{float:right;font-variant-numeric:tabular-nums;color:var(--a)}
.rag-row{display:flex;gap:.5em;align-items:center;flex-wrap:wrap;margin:.3em 0}
.rag input[type=text]{flex:1;min-width:240px;font:inherit;padding:.25em .5em;border:1px solid var(--mut);border-radius:4px}
.rag button{font:inherit;padding:.2em .7em;border:1px solid var(--mut);border-radius:4px;background:#fff;cursor:pointer}
.rag button.primary{background:var(--a);color:#fff;border-color:var(--a)}
.rag button:disabled{opacity:.5;cursor:default}
.rag-status{font-size:13px;opacity:.8;min-height:1.2em}
.rag-out{display:grid;grid-template-columns:1.1fr 1fr;gap:.7em;margin-top:.4em}
.rag-hits{font-size:13px;max-height:330px;overflow:auto}
.rag-hit{border-left:3px solid var(--mut);padding:2px 6px;margin:0 0 5px}
.rag-hit.used{border-left-color:var(--a)}
.rag-hit a{font-weight:600;text-decoration:none}
.rag-hit .ranks{font-size:11px;opacity:.7;font-variant-numeric:tabular-nums}
.rag-hit .snip{opacity:.85}
.rag-answer{font-size:14px;max-height:330px;overflow:auto;white-space:pre-wrap}
.rag details{font-size:12px}.rag pre{white-space:pre-wrap;max-height:200px;overflow:auto;font-size:11px}
/* on a slide: everything smaller, so the strip, the question and both panels fit in 720 px */
.rag.compact{font-size:15px;padding:.4em .6em}.rag.compact .rag-stage{min-width:64px;padding:2px 4px}
.rag.compact .rag-stage b,.rag.compact .rag-stage i{font-size:11.5px}
.rag.compact .rag-hits,.rag.compact .rag-answer{max-height:330px;font-size:14px}.rag.compact .rag-hit{margin-bottom:3px}
.rag.compact .rag-out{margin-top:.2em}.rag.compact pre{max-height:140px}
`;

function h(tag, attrs, parent, text) {
  const n = document.createElement(tag);
  for (const k in attrs || {}) n.setAttribute(k, attrs[k]);
  if (text !== undefined) n.textContent = text;
  if (parent) parent.appendChild(n);
  return n;
}

function decodeVectors(index) {
  const bytes = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const q = new Int8Array(bytes(index.vectors).buffer);
  const scale = new Float32Array(bytes(index.scales).buffer);
  return { q, scale, dims: index.dims };
}

function words(text, n) {
  const w = text.split(/\s+/);
  return w.length <= n ? text : w.slice(0, n).join(' ') + ' …';
}

async function mount(root) {
  const LLM = { id: root.dataset.model || DEFAULT_MODEL };
  LLM.label = MODELS[LLM.id] || LLM.id;
  if (!document.getElementById('rag-css')) h('style', { id: 'rag-css' }, document.head, CSS);
  root.textContent = '';
  root.classList.add('rag');
  const strip = h('div', { class: 'rag-strip' }, root);
  const stage = {};
  for (const [key, name, sub] of STAGES) {
    const el = h('div', { class: 'rag-stage' }, strip);
    h('span', { class: 't' }, el);
    h('b', {}, el, name);
    h('i', {}, el, sub);
    stage[key] = el;
  }
  const setStage = (key, state, ms) => {
    const el = stage[key];
    el.classList.remove('run', 'done', 'skip');
    if (state) el.classList.add(state);
    el.querySelector('.t').textContent = ms === undefined ? '' : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
  };
  const timed = async (key, fn) => {
    setStage(key, 'run');
    const t0 = performance.now();
    const out = await fn();
    setStage(key, 'done', performance.now() - t0);
    return out;
  };

  const row = h('div', { class: 'rag-row' }, root);
  const input = h('input', { type: 'text', placeholder: 'Ask about the course notes, e.g. "why not shuffle a time series before splitting?"' }, row);
  const ask = h('button', { type: 'button', class: 'primary', disabled: '' }, row, 'Ask');
  const rr = h('label', {}, row);
  const rerankBox = h('input', { type: 'checkbox' }, rr);
  rr.append(' rerank');
  if (root.dataset.examples) {
    const ex = h('div', { class: 'rag-row' }, root);
    h('span', { class: 'rag-status' }, ex, 'Try:');
    root.dataset.examples.split('|').forEach((q) => {
      const b = h('button', { type: 'button' }, ex, q.trim());
      b.onclick = () => { input.value = q.trim(); if (!ask.disabled) run(); };
    });
  }
  const row2 = h('div', { class: 'rag-row' }, root);
  const loadBtn = h('button', { type: 'button' }, row2, `Load the model (${LLM.label})`);
  const status = h('div', { class: 'rag-status', 'aria-live': 'polite' }, row2, 'Loading the index…');
  const out = h('div', { class: 'rag-out' }, root);
  const hitsEl = h('div', { class: 'rag-hits' }, out);
  const right = h('div', {}, out);
  const answer = h('div', { class: 'rag-answer' }, right);
  const det = h('details', {}, right);
  h('summary', {}, det, 'the exact prompt sent to the model');
  const promptPre = h('pre', {}, det);

  if (!navigator.gpu) {
    loadBtn.disabled = true;
    loadBtn.textContent = 'No WebGPU in this browser: retrieval only';
  }

  // --- index, keyword index, embedder: everything retrieval needs, at mount time ---------------
  let index, vec, mini, embedder, reranker, engine = null;
  try {
    index = await timed('index', async () => window.RAG_INDEX ||
      (await fetch(root.dataset.index || 'rag-index.json')).json());
    if (index.transformers !== TRANSFORMERS_VERSION) {
      status.textContent = `Index built with transformers.js ${index.transformers}, page uses ${TRANSFORMERS_VERSION}: rebuild the index.`;
      return;
    }
    vec = decodeVectors(index);
    const { default: MiniSearch } = await import(LIB.minisearch);
    mini = new MiniSearch({ fields: ['section', 'text'], storeFields: [], searchOptions: { boost: { section: 2 }, prefix: true, fuzzy: 0.15 } });
    mini.addAll(index.chunks.map((c, i) => ({ id: i, section: c.section, text: c.text })));
    status.textContent = 'Loading the embedding model…';
    const tf = await import(LIB.transformers);
    embedder = await tf.pipeline('feature-extraction', index.model, { dtype: index.dtype });
    status.textContent = `${index.chunks.length} passages from ${index.lectures.length} lectures, built ${index.built}. Ask a question.`;
    ask.disabled = false;
    if (input.value.trim()) run(); // an example clicked while the models were still loading
    rerankBox.onchange = async () => {
      if (!rerankBox.checked || reranker) return;
      status.textContent = 'Loading the cross-encoder (about 23 MB)…';
      reranker = {
        tok: await tf.AutoTokenizer.from_pretrained(RERANKER),
        model: await tf.AutoModelForSequenceClassification.from_pretrained(RERANKER, { dtype: 'q8' }),
      };
      status.textContent = 'Reranker ready.';
    };
  } catch (err) {
    status.textContent = 'Could not load: ' + err.message;
    return;
  }

  loadBtn.onclick = async () => {
    loadBtn.disabled = true;
    try {
      const webllm = await import(LIB.webllm);
      engine = await webllm.CreateMLCEngine(LLM.id, {
        initProgressCallback: (p) => { status.textContent = p.text; },
      });
      loadBtn.textContent = `${LLM.id} loaded`;
      status.textContent = 'Model ready. Answers will be generated in this tab.';
    } catch (err) {
      status.textContent = 'Model failed to load: ' + err.message;
      loadBtn.disabled = false;
    }
  };

  async function run() {
    const query = input.value.trim();
    if (!query) return;
    ask.disabled = true;
    for (const [key] of STAGES.slice(1)) setStage(key, null);
    answer.textContent = '';
    promptPre.textContent = '';

    const kw = await timed('keyword', async () => mini.search(query).slice(0, POOL).map((r) => r.id));
    const qv = await timed('embed', async () => (await embedder(query, { pooling: 'mean', normalize: true })).data);
    const dense = await timed('vector', async () => {
      const n = index.chunks.length, d = vec.dims, s = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        let dot = 0;
        for (let j = 0; j < d; j++) dot += qv[j] * vec.q[i * d + j];
        s[i] = dot * vec.scale[i];
      }
      return Array.from(s.keys()).sort((a, b) => s[b] - s[a]).slice(0, POOL).map((i) => [i, s[i]]);
    });
    const fused = await timed('fuse', async () => {
      const score = new Map(), kRank = new Map(), dRank = new Map();
      kw.forEach((id, r) => { kRank.set(id, r + 1); score.set(id, (score.get(id) || 0) + 1 / (RRF_K + r + 1)); });
      dense.forEach(([id], r) => { dRank.set(id, r + 1); score.set(id, (score.get(id) || 0) + 1 / (RRF_K + r + 1)); });
      return [...score.entries()].sort((a, b) => b[1] - a[1]).slice(0, POOL)
        .map(([id, sc]) => ({ id, rrf: sc, k: kRank.get(id), d: dRank.get(id), cos: (dense.find(([i]) => i === id) || [])[1] }));
    });
    let ranked = fused;
    if (rerankBox.checked && reranker) {
      ranked = await timed('rerank', async () => {
        // A cross-encoder reads the query and the passage as one input, so its cost grows with
        // both: rerank only the top RERANK_N, each cut to 256 tokens.
        const head = fused.slice(0, RERANK_N);
        const docs = head.map((f) => index.chunks[f.id].text);
        const inputs = reranker.tok(new Array(docs.length).fill(query),
          { text_pair: docs, padding: true, truncation: true, max_length: 256 });
        const { logits } = await reranker.model(inputs);
        const sc = Array.from(logits.data);
        return head.map((f, i) => ({ ...f, ce: sc[i] })).sort((a, b) => b.ce - a.ce)
          .concat(fused.slice(RERANK_N));
      });
    } else setStage('rerank', 'skip');

    const top = ranked.slice(0, TOP);
    // The cross-encoder's score is a logit: below zero it judges the pair more likely irrelevant
    // than relevant. When even the best passage scores below zero, say so before anyone reads an
    // answer built on it.
    if (ranked[0].ce !== undefined && ranked[0].ce < MIN_CE) {
      status.textContent = `Best passage scored ${ranked[0].ce.toFixed(1)} by the cross-encoder: the notes probably do not answer this.`;
    }
    const passages = top.map((f, i) => {
      const c = index.chunks[f.id];
      return `[${i + 1}] ${c.title}: ${c.section}\n${words(c.text, WORDS_PER_PASSAGE)}`;
    }).join('\n\n');
    const user = `Question: ${query}\n\nPassages:\n\n${passages}\n\nQuestion: ${query}\nAnswer in two or three sentences:`;
    await timed('prompt', async () => { promptPre.textContent = `SYSTEM: ${SYSTEM}\n\nUSER: ${user}`; });

    hitsEl.textContent = '';
    ranked.slice(0, 10).forEach((f, i) => {
      const c = index.chunks[f.id];
      const el = h('div', { class: 'rag-hit' + (i < TOP ? ' used' : '') }, hitsEl);
      h('span', {}, el, i < TOP ? `[${i + 1}] ` : '');
      h('a', { href: c.url, target: '_blank', rel: 'noopener' }, el, `${c.lecture.toUpperCase()} ${c.kind}: ${c.section}`);
      h('div', { class: 'ranks' }, el,
        `BM25 rank ${f.k || '–'} · vector rank ${f.d || '–'}${f.cos !== undefined ? ` (cos ${f.cos.toFixed(2)})` : ''}` +
        ` · RRF ${f.rrf.toFixed(4)}${f.ce !== undefined ? ` · cross-encoder ${f.ce.toFixed(2)}` : ''}`);
      h('div', { class: 'snip' }, el, words(c.text.replace(/^.*\n\n/, ''), 30));
    });

    const bestCos = Math.max(...dense.map(([, c]) => c));
    const abstain = bestCos < MIN_COS || (ranked[0].ce !== undefined && ranked[0].ce < MIN_CE);
    if (abstain) {
      setStage('generate', 'skip');
      answer.textContent = 'Not in the notes. ' + (bestCos < MIN_COS
        ? `The closest passage has cosine ${bestCos.toFixed(2)} (below ${MIN_COS}), `
        : `The best passage scored ${ranked[0].ce.toFixed(1)} with the cross-encoder (below ${MIN_CE}), `) +
        'so the model was not asked: a small model given weak passages invents an answer.';
    } else if (!engine) {
      setStage('generate', 'skip');
      answer.textContent = navigator.gpu
        ? 'Retrieval only: load the model to generate an answer from these passages.'
        : 'This browser has no WebGPU, so there is no model to answer. The passages on the left are what it would have read.';
    } else {
      await timed('generate', async () => {
        const chunks = await engine.chat.completions.create({
          messages: [{ role: 'system', content: SYSTEM }, { role: 'user', content: user }],
          temperature: 0, max_tokens: 160, stream: true, stream_options: { include_usage: true },
        });
        let usage = null;
        for await (const ch of chunks) {
          answer.textContent += ch.choices[0]?.delta?.content || '';
          if (ch.usage) usage = ch.usage;
        }
        if (usage) status.textContent = `${usage.prompt_tokens} prompt tokens in, ${usage.completion_tokens} out.`;
      });
    }
    ask.disabled = false;
  }
  ask.onclick = run;
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !ask.disabled) run(); });
}

function boot() {
  document.querySelectorAll('.rag-chat').forEach((n) => {
    if (n.dataset.ready) return;
    n.dataset.ready = '1';
    mount(n);
  });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
})();
