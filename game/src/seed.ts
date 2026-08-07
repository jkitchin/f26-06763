/**
 * Seeded per-student item selection. The TypeScript half.
 *
 * This file and tools/derive.py must agree byte for byte, forever. If they ever
 * disagree, every submitted PDF fails verification and you find out when
 * submissions land, not before. `npm run vectors` regenerates
 * game/tests/vectors.json from this file, and CI replays it through the Python
 * side; that test is the only thing standing between this design and that
 * failure. Change one side, change the other, regenerate, let CI prove it.
 *
 * The order of RNG consumption is part of the contract, not an implementation
 * detail: variant first, then option order, per item, in selection order.
 *
 * NOTE ON CRYPTO. This deliberately does not use `window.crypto.subtle`. Every
 * link to the course site in this repository is `http://`, and on a non-secure
 * origin `crypto.subtle` is `undefined`. It would work on localhost and fail
 * for every student, which is exactly the class of failure CLAUDE.md section 8
 * exists to prevent. @noble/hashes is synchronous, ~8 KB, and has no deps.
 */

import { sha256 } from '@noble/hashes/sha256'

/**
 * Not a secret. It ships in this bundle, so anyone can read it. It is a domain
 * separator and a between-semesters rotation knob. Calling it security would be
 * the kind of self-deception this course teaches against.
 */
export const SELECTION_SALT = 'f26'

const ID_RE = /^[a-z][a-z0-9]{1,15}$/

const enc = new TextEncoder()

function bytes(s: string): Uint8Array {
  return enc.encode(s)
}

/** Concatenate with NUL separators, because "ab"+"c" and "a"+"bc" would collide. */
function joinNul(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((n, p) => n + p.length, 0) + Math.max(0, parts.length - 1)
  const out = new Uint8Array(total)
  let at = 0
  parts.forEach((p, i) => {
    if (i > 0) out[at++] = 0
    out.set(p, at)
    at += p.length
  })
  return out
}

function concat(a: Uint8Array, b: Uint8Array): Uint8Array {
  const out = new Uint8Array(a.length + b.length)
  out.set(a, 0)
  out.set(b, a.length)
  return out
}

export function hex(b: Uint8Array): string {
  return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
}

/**
 * Canonical Andrew ID. The seed depends on this byte for byte.
 *
 * A typo here produces a PDF that fails verification for an honest student,
 * which is the most likely operational failure in the whole system. The UI
 * echoes the normalized result back for confirmation before building anything
 * on top of it.
 */
export function normalizeId(raw: string): string {
  let s = raw.normalize('NFKC').trim().toLowerCase()
  for (const suffix of ['@andrew.cmu.edu', '@cmu.edu']) {
    if (s.endsWith(suffix)) s = s.slice(0, -suffix.length)
  }
  if (!ID_RE.test(s)) throw new Error(`not a well-formed Andrew ID: ${JSON.stringify(raw)}`)
  return s
}

export function selectionSeed(andrewId: string, lecture: string, poolVersion: number): Uint8Array {
  return sha256(
    joinNul([
      bytes('06763/select/v1'),
      bytes(SELECTION_SALT),
      bytes(normalizeId(andrewId)),
      bytes(lecture),
      bytes(String(poolVersion)),
    ]),
  )
}

/**
 * SHA-256 in counter mode. Must be byte-identical to the Rng in derive.py.
 *
 * A stream cipher rather than mulberry32 because the two implementations have
 * to agree exactly, and "SHA-256 of seed || counter" is something both
 * languages do the same way. Small PRNGs depend on 32-bit integer semantics
 * that are easy to get subtly wrong across languages.
 */
export class Rng {
  private ctr = 0
  private buf: Uint8Array<ArrayBufferLike> = new Uint8Array(0)
  private readonly seed: Uint8Array

  // A plain assignment rather than a TypeScript parameter property, so this
  // file runs under `node --experimental-strip-types` with no build step. CI
  // replays the vectors that way.
  constructor(seed: Uint8Array) {
    this.seed = seed
  }

  private u32(): number {
    if (this.buf.length < 4) {
      // 32 is divisible by 4, so a block is consumed exactly and no bytes are
      // ever discarded. If that stops being true the two languages diverge.
      const ctr = new Uint8Array(4)
      new DataView(ctr.buffer).setUint32(0, this.ctr, false) // big-endian
      this.buf = sha256(concat(this.seed, ctr))
      this.ctr += 1
    }
    const view = new DataView(this.buf.buffer, this.buf.byteOffset, 4)
    const value = view.getUint32(0, false)
    this.buf = this.buf.subarray(4)
    return value
  }

  /** Uniform in [0, n). Rejection sampling, so no modulo bias. */
  below(n: number): number {
    if (n <= 0) throw new Error('n must be positive')
    const limit = Math.floor(0x100000000 / n) * n
    for (;;) {
      const value = this.u32()
      if (value < limit) return value % n
    }
  }

  shuffle<T>(items: readonly T[]): T[] {
    const out = [...items]
    for (let i = out.length - 1; i > 0; i--) {
      const j = this.below(i + 1)
      ;[out[i], out[j]] = [out[j]!, out[i]!]
    }
    return out
  }
}

/**
 * Hash-and-take-lowest, not shuffle-and-slice.
 *
 * Order-independent, so reordering the YAML file does not reshuffle every
 * student; and when the pool grows one item is displaced rather than the whole
 * selection, so adding a question does not invalidate PDFs already issued.
 */
export function selectItems(seed: Uint8Array, poolIds: readonly string[], k: number): string[] {
  return [...poolIds]
    .map((id) => ({
      key: hex(sha256(concat(concat(bytes('06763/pick/v1\x00'), seed), bytes(`\x00${id}`)))),
      id,
    }))
    .sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : a.id < b.id ? -1 : 1))
    .slice(0, k)
    .map((x) => x.id)
}

export interface ServedItem {
  id: string
  variant: string
  option_order: number[]
}

export interface PoolItem {
  options?: readonly string[]
  variants?: readonly { id: string; options?: readonly string[] }[]
}

/** The served list: which items, which variant, which option order. */
export function derive(
  andrewId: string,
  lecture: string,
  pool: Record<string, PoolItem>,
  poolVersion: number,
  k: number,
): ServedItem[] {
  const seed = selectionSeed(andrewId, lecture, poolVersion)
  const picked = selectItems(seed, Object.keys(pool).sort(), k)
  const rng = new Rng(sha256(concat(bytes('06763/order/v1\x00'), seed)))

  return picked.map((id) => {
    const item = pool[id]!
    const variants = item.variants?.length ? item.variants : [{ id: '-' }]
    const variant = variants[rng.below(variants.length)]!
    const options = variant.options ?? item.options ?? []
    const order = options.length ? rng.shuffle([...options.keys()]) : []
    return { id, variant: variant.id ?? '-', option_order: order }
  })
}

/** Short digest of a derived list, so the verifier can compare one field. */
export function selectionHash(served: readonly ServedItem[]): string {
  const blob = served.map((s) => `${s.id}:${s.variant}:${s.option_order.join(',')}`).join(';')
  return hex(sha256(concat(bytes('06763/selhash/v1\x00'), bytes(blob)))).slice(0, 16)
}
