/**
 * The machine-readable half of the evidence PDF.
 *
 * A module is issued, a payload is built from the session's event log, and the
 * exact bytes of that payload are MAC'd and embedded in the PDF. The verifier
 * re-reads those bytes and checks them; it never re-serializes, so JavaScript's
 * JSON.stringify never has to be reproduced in Python. That single decision
 * removes canonicalization as a source of verification failure, which is
 * otherwise the classic way schemes like this break.
 *
 * Read tools/verify_evidence.py alongside this. The honest ordering of what
 * actually establishes anything is:
 *
 *   1. Canvas. The student authenticated to a real server which timestamped the
 *      upload. Identity is already solved there, by something with auth.
 *   2. The derivation. The served item set is a function of the Andrew ID, so a
 *      classmate's PDF carries the wrong items. This needs no secret and
 *      survives the MAC key being extracted, which it will be.
 *   3. The MAC, a distant third. Its key ships in this bundle and is therefore
 *      public. It defeats editing the PDF in a text editor, and it separates "I
 *      forgot" from "I extracted a key and forged a tag", which is a different
 *      conversation. It is not a signature and this file does not pretend it is.
 */

import { hmac } from '@noble/hashes/hmac'
import { sha256 } from '@noble/hashes/sha256'
import { selectionHash, type ServedItem } from '../seed.ts'

export const SCHEMA = 'cmu-06763-attest/1'
export const BEGIN = '-----BEGIN 06763 ATTESTATION-----'
export const END = '-----END 06763 ATTESTATION-----'

/**
 * Injected at build time from a GitHub Actions secret. It still ends up in the
 * public bundle; see the header. `dev` is the fallback so a local build works,
 * and CI fails the build on main if the shipped key_id is still `dev`, because
 * a silently unsigned deploy is worse than a broken one.
 */
// import.meta.env is Vite's, and is undefined when these modules are run
// directly under Node for the test fixtures. Falling through to process.env
// means the sample PDFs can be built with the same key the verifier will use,
// instead of silently being dev-key artifacts that fail every MAC check.
declare const process: { env?: Record<string, string | undefined> } | undefined
const env = (k: string): string | undefined =>
  import.meta.env?.[k] ?? (typeof process !== 'undefined' ? process?.env?.[k] : undefined)

const MAC_KEY: string = env('VITE_MAC_KEY') || 'dev-key-not-secret'
export const KEY_ID: string = env('VITE_KEY_ID') || 'dev'

const enc = new TextEncoder()

/** One answered item, as recorded in the append-only event log. */
export interface ItemRecord {
  id: string
  /** Variant served, "-" when the item has none. */
  v: string
  /** The option order this student was served, so the shuffle stays checkable. */
  opts: number[]
  /**
   * Option *ids*, never the displayed letter. The letter depends on `opts`, so
   * recording "B" would make correctness uncheckable from the pool alone.
   */
  ans: string[]
  /** Integer milliseconds. No floats anywhere: they are the classic
   *  cross-language serialization mismatch and there is no reason to accept it. */
  first_ms: number
  total_ms: number
  tries: number
  /**
   * First-try correctness. Not `correct`: with retry-until-right every item
   * ends correct, so `correct` carries no information and `first_ok` is the
   * only number that means anything.
   */
  first_ok: boolean
  /** Whether the player used the "show me" escape hatch. */
  revealed: boolean
}

export interface PayloadInput {
  andrewId: string
  name: string
  lecture: string
  poolVersion: number
  serve: number
  appVersion: string
  buildCommit: string
  contentSha256: string
  startedAt: string
  finishedAt: string
  elapsedMs: number
  activeMs: number
  tzOffsetMin: number
  resumes: number
  served: ServedItem[]
  items: ItemRecord[]
}

export interface Attestation {
  /** The exact bytes that were MAC'd. Embed these, do not rebuild them. */
  bytes: Uint8Array
  /** Base64url of `bytes`, which is what goes in the PDF. */
  b64: string
  /** The human-facing verification code. */
  code: string
  payload: unknown
}

function b64url(bytes: Uint8Array): string {
  let s = ''
  for (const b of bytes) s += String.fromCharCode(b)
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Crockford base32: no I, L, O or U, so a code read aloud is unambiguous. */
const CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'

function crockford(bytes: Uint8Array): string {
  let bits = 0
  let value = 0
  let out = ''
  for (const b of bytes) {
    value = (value << 8) | b
    bits += 8
    while (bits >= 5) {
      out += CROCKFORD[(value >>> (bits - 5)) & 31]
      bits -= 5
    }
  }
  if (bits > 0) out += CROCKFORD[(value << (5 - bits)) & 31]
  return out
}

export function makeCode(bytes: Uint8Array): string {
  const tag = hmac(sha256, enc.encode(MAC_KEY), concatDomain(bytes)).slice(0, 10)
  const raw = crockford(tag)
  return `${raw.slice(0, 4)}-${raw.slice(4, 8)}-${raw.slice(8, 12)}-${raw.slice(12, 16)}`
}

function concatDomain(bytes: Uint8Array): Uint8Array {
  const domain = enc.encode('06763/attest/v1\x00')
  const out = new Uint8Array(domain.length + bytes.length)
  out.set(domain, 0)
  out.set(bytes, domain.length)
  return out
}

export function buildAttestation(input: PayloadInput): Attestation {
  const payload = {
    schema: SCHEMA,
    student: { andrew_id: input.andrewId, name: input.name },
    module: {
      lecture: input.lecture,
      pool_version: input.poolVersion,
      serve: input.serve,
    },
    build: {
      app: input.appVersion,
      commit: input.buildCommit,
      content_sha256: input.contentSha256,
      key_id: KEY_ID,
    },
    session: {
      started_at: input.startedAt,
      finished_at: input.finishedAt,
      elapsed_ms: Math.round(input.elapsedMs),
      active_ms: Math.round(input.activeMs),
      tz_offset_min: input.tzOffsetMin,
      resumes: input.resumes,
    },
    derive: { selection_hash: selectionHash(input.served) },
    items: input.items,
    score: {
      served: input.serve,
      completed: input.items.length,
      first_try: input.items.filter((i) => i.first_ok).length,
    },
  }

  // Serialize once. These exact bytes are what gets MAC'd and what gets
  // embedded, and the verifier MACs the literal bytes it extracts.
  const bytes = enc.encode(JSON.stringify(payload))
  return { bytes, b64: b64url(bytes), code: makeCode(bytes), payload }
}

/**
 * The base64 body, hard-wrapped.
 *
 * Drawn one fixed-width line at a time in the PDF so text extraction returns it
 * in order. The verifier strips all whitespace inside the block before
 * decoding, because extractors insert newlines and sometimes spaces, and that
 * is the single most common reason a block like this fails to parse.
 */
export function attestationLines(b64: string, width = 64): string[] {
  const lines: string[] = [BEGIN]
  for (let i = 0; i < b64.length; i += width) lines.push(b64.slice(i, i + width))
  lines.push(END)
  return lines
}
