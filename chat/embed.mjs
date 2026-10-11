// Add one embedding per chunk to chat/build/chunks.json and write chat/build/rag-index.json.
//
//     python tools/rag_index.py && (cd chat && npm ci && node embed.mjs)
//
// The model, its dtype and the pooling are the ones rag-chat.js uses to embed a query in the
// browser. That is the whole reason this step is JavaScript and not Python: a query and an index
// embedded by two different runtimes, or two quantizations of one model, disagree by enough to
// reorder close results, and nothing fails loudly when they do.
//
// Vectors are unit length, stored as int8 with one scale per vector (v ~ q * scale), which makes
// the file 4x smaller than float32 for a change in cosine of about 1e-3.
import { readFileSync, writeFileSync } from 'node:fs';
import { pipeline, env } from '@huggingface/transformers';

export const MODEL = 'Xenova/all-MiniLM-L6-v2';
export const DTYPE = 'q8';

const src = JSON.parse(readFileSync(new URL('./build/chunks.json', import.meta.url)));
const embed = await pipeline('feature-extraction', MODEL, { dtype: DTYPE });

const dims = 384, n = src.chunks.length, q = new Int8Array(n * dims), scale = new Float32Array(n);
const t0 = Date.now(), batch = 32;
for (let i = 0; i < n; i += batch) {
  const texts = src.chunks.slice(i, i + batch).map((c) => c.text);
  const out = await embed(texts, { pooling: 'mean', normalize: true });
  for (let b = 0; b < texts.length; b++) {
    const v = out.data.subarray(b * dims, (b + 1) * dims);
    let m = 0;
    for (const x of v) m = Math.max(m, Math.abs(x));
    const s = m / 127;
    scale[i + b] = s;
    for (let d = 0; d < dims; d++) q[(i + b) * dims + d] = Math.round(v[d] / s);
  }
}
const index = {
  model: MODEL, dtype: DTYPE, pooling: 'mean', dims, transformers: env.version, built: new Date().toISOString().slice(0, 10),
  lectures: src.lectures, chunks: src.chunks,
  vectors: Buffer.from(q.buffer).toString('base64'),
  scales: Buffer.from(scale.buffer).toString('base64'),
};
writeFileSync(new URL('./build/rag-index.json', import.meta.url), JSON.stringify(index));
console.error(`embedded ${n} chunks in ${((Date.now() - t0) / 1000).toFixed(0)} s`);
