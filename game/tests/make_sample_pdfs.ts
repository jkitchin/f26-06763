/**
 * Produce sample evidence PDFs, clean and tampered, for the verifier tests.
 *
 *     cd game && npm run samples
 *
 * Written into game/tests/samples/ and gitignored: they are build products, and
 * the point is that tools/verify_evidence.py is exercised against real PDF
 * bytes rather than a dict someone wrote by hand. A verifier tested only on
 * hand-built input is a verifier that has never met pypdf.
 *
 * These load the *real* game/content/l15.yml. An earlier version used a
 * synthetic pool, and every clean sample came back REVIEW because the generator
 * and the verifier were deriving against two different pools. That is a fixture
 * bug rather than a verifier bug, and it is exactly the kind that gets
 * "resolved" by loosening a check, so: one pool, read from disk, both sides.
 */

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { derive } from '../src/seed.ts'
import { parseBank, poolOf } from '../src/content/load.ts'
import { buildAttestation, type ItemRecord } from '../src/evidence/payload.ts'
import { buildPdf, filenameFor } from '../src/evidence/pdf.ts'

const OUT = fileURLToPath(new URL('./samples/', import.meta.url))
mkdirSync(OUT, { recursive: true })

const LECTURE = 'l15'
const bank = parseBank(
  readFileSync(fileURLToPath(new URL(`../content/${LECTURE}.yml`, import.meta.url)), 'utf8'),
)
const POOL = poolOf(bank)
const BY_ID = Object.fromEntries(bank.items.map((i) => [i.id, i]))

interface Person {
  andrewId: string
  name: string
  /** Every nth served item is answered wrong first, deterministically. */
  wrongEvery: number
  msPerItem: number
}

async function session(
  p: Person,
  opts: { label: string; overrideId?: string; attempt?: number } = { label: 'clean' },
) {
  const ATTEMPT = opts.attempt ?? 1
  const served = derive(p.andrewId, LECTURE, POOL, bank.pool_version, bank.serve, ATTEMPT)

  const items: ItemRecord[] = served.map((s, i) => {
    const item = BY_ID[s.id]!
    const options = item.options ?? []
    const correctIdx = options.findIndex((o) => o === item.answer)
    const firstOk = (i + 1) % p.wrongEvery !== 0 && correctIdx >= 0

    // Option *ids* index the original pool order, never the displayed position.
    let chosenIdx = correctIdx
    if (!firstOk && options.length) {
      chosenIdx = options.findIndex((_, j) => j !== correctIdx)
    }

    return {
      id: s.id,
      v: s.variant,
      opts: s.option_order,
      ans: chosenIdx >= 0 ? [`opt${chosenIdx}`] : [],
      first_ms: Math.round(p.msPerItem * 0.4),
      total_ms: p.msPerItem + i * 500,
      tries: firstOk ? 1 : 2,
      first_ok: firstOk,
      revealed: false,
    }
  })

  const activeMs = items.reduce((n, it) => n + it.total_ms, 0)
  const attestation = buildAttestation({
    andrewId: opts.overrideId ?? p.andrewId,
    name: p.name,
    lecture: LECTURE,
    poolVersion: bank.pool_version,
    serve: bank.serve,
    attempt: ATTEMPT,
    appVersion: '0.1.0',
    buildCommit: '0'.repeat(40),
    contentSha256: 'f'.repeat(64),
    // Fixed timestamps, so the samples are byte-reproducible.
    startedAt: '2026-09-14T18:02:11Z',
    finishedAt: '2026-09-14T18:11:47Z',
    elapsedMs: activeMs + 64000,
    activeMs,
    tzOffsetMin: -240,
    resumes: 1,
    served,
    items,
  })

  const labels: Record<string, { prompt: string; chosen: string }> = {}
  for (const rec of items) {
    const item = BY_ID[rec.id]!
    const idx = rec.ans[0] ? Number(rec.ans[0].slice(3)) : -1
    labels[rec.id] = {
      prompt: (item.prompt ?? '').split('\n')[0] ?? rec.id,
      chosen: (item.options?.[idx] ?? '(free response)').slice(0, 70),
    }
  }

  const doc = await buildPdf({
    attestation,
    name: p.name,
    andrewId: opts.overrideId ?? p.andrewId,
    lecture: LECTURE,
    lectureTitle: bank.title,
    attempt: ATTEMPT,
    finishedAtLocal: '2026-09-14 14:11 EDT',
    elapsedMs: activeMs + 64000,
    activeMs,
    resumes: 1,
    items,
    labels,
  })

  const name = `${opts.label}-${filenameFor(LECTURE, opts.overrideId ?? p.andrewId)}`
  writeFileSync(`${OUT}${name}`, Buffer.from(doc.output('arraybuffer')))
  console.log(`  ${name}`)
  return { doc, attestation, items, served, labels }
}

const JK: Person = { andrewId: 'jkitchin', name: 'John Kitchin', wrongEvery: 4, msPerItem: 22000 }
const VA: Person = { andrewId: 'valves', name: 'Victor Alves', wrongEvery: 6, msPerItem: 31000 }

console.log('samples:')

// 1. Two honest students. Their item sets must visibly differ.
const a = await session(JK)
const b = await session(VA)
const overlap = a.served.filter((s, i) => s.id === b.served[i]?.id).length
console.log(`     (item sets agree in ${overlap}/${a.served.length} positions)`)

// 1b. The same student's second attempt. It must draw entirely different items,
//     which is the claim the attempt window makes and the thing a TA will be
//     asked about the first time a student retakes a module.
const a2 = await session(JK, { label: 'attempt2', attempt: 2 })
const repeated = a2.served.filter((s) => a.served.some((t) => t.id === s.id)).length
console.log(`     (attempt 2 repeats ${repeated}/${a2.served.length} of attempt 1's items)`)
if (repeated !== 0) throw new Error(`attempt 2 should be disjoint, repeated ${repeated}`)

// 2. The forgery the derivation exists to catch: a real session re-issued under
//    a different Andrew ID. The payload is internally consistent and the MAC is
//    valid, because this same code built it. The served items are jkitchin's.
await session(JK, { label: 'copied', overrideId: 'valves' })

// 3. The text-editor forgery: take a real PDF and change the printed name.
//    The attestation still says jkitchin, the page says someone else. Caught by
//    comparing the two, which needs no key, no repo and no pool.
{
  const served = derive(JK.andrewId, LECTURE, POOL, bank.pool_version, bank.serve)
  const items: ItemRecord[] = served.map((s, i) => ({
    id: s.id,
    v: s.variant,
    opts: s.option_order,
    ans: (() => {
      const opts = BY_ID[s.id]!.options ?? []
      const c = opts.findIndex((o) => o === BY_ID[s.id]!.answer)
      return c >= 0 ? [`opt${c}`] : []
    })(),
    first_ms: 9000,
    total_ms: 20000 + i * 500,
    tries: 1,
    first_ok: (BY_ID[s.id]!.options ?? []).length > 0,
    revealed: false,
  }))
  const activeMs = items.reduce((n, it) => n + it.total_ms, 0)
  const attestation = buildAttestation({
    andrewId: JK.andrewId,
    name: JK.name,
    lecture: LECTURE,
    poolVersion: bank.pool_version,
    serve: bank.serve,
    attempt: 1,
    appVersion: '0.1.0',
    buildCommit: '0'.repeat(40),
    contentSha256: 'f'.repeat(64),
    startedAt: '2026-09-14T18:02:11Z',
    finishedAt: '2026-09-14T18:11:47Z',
    elapsedMs: activeMs,
    activeMs,
    tzOffsetMin: -240,
    resumes: 0,
    served,
    items,
  })
  const labels: Record<string, { prompt: string; chosen: string }> = {}
  for (const rec of items) labels[rec.id] = { prompt: rec.id, chosen: 'answer' }

  const doc = await buildPdf({
    attestation,
    name: 'Morgan Reed',          // <- the edit
    andrewId: 'mreed',            // <- the edit
    lecture: LECTURE,
    lectureTitle: bank.title,
    attempt: 1,
    finishedAtLocal: '2026-09-14 14:11 EDT',
    elapsedMs: activeMs,
    activeMs,
    resumes: 0,
    items,
    labels,
  })
  writeFileSync(
    `${OUT}text-edited-${filenameFor(LECTURE, 'mreed')}`,
    Buffer.from(doc.output('arraybuffer')),
  )
  console.log(`  text-edited-${filenameFor(LECTURE, 'mreed')}`)
}

// 3b. The forgery the seal exists to catch. Once the score stops being a text
//     run there is no `(95%)` to retype, so editing it means redrawing the page,
//     and this is that PDF: jkitchin's real attestation carried on a page built
//     from a doctored item list that draws 100%. Everything a reader sees agrees
//     with itself, which is what makes it the interesting case. It disagrees
//     with the payload, and the seal check reads the drawn number back out of
//     the content stream and says so.
{
  const better: ItemRecord[] = a.items.map((i) => ({
    ...i,
    tries: 1,
    first_ok: i.ans.length > 0,
    revealed: false,
  }))
  const activeMs = a.items.reduce((n, it) => n + it.total_ms, 0)
  const doc = await buildPdf({
    attestation: a.attestation,      // <- the real one, untouched
    name: JK.name,
    andrewId: JK.andrewId,
    lecture: LECTURE,
    lectureTitle: bank.title,
    attempt: 1,
    finishedAtLocal: '2026-09-14 14:11 EDT',
    elapsedMs: activeMs + 64000,
    activeMs,
    resumes: 1,
    items: better,                   // <- the lie
    labels: a.labels,
  })
  writeFileSync(
    `${OUT}seal-edited-${filenameFor(LECTURE, JK.andrewId)}`,
    Buffer.from(doc.output('arraybuffer')),
  )
  console.log(`  seal-edited-${filenameFor(LECTURE, JK.andrewId)}`)
}

// 4. A fabricated PDF with no attestation at all.
{
  const doc = await buildPdf({
    attestation: { bytes: new Uint8Array(), b64: '', code: 'FAKE-FAKE-FAKE-FAKE', payload: {} },
    name: 'S Fake',
    andrewId: 'sfake',
    lecture: LECTURE,
    lectureTitle: bank.title,
    attempt: 1,
    finishedAtLocal: '2026-09-14 23:58 EDT',
    elapsedMs: 300000,
    activeMs: 298000,
    resumes: 0,
    items: [],
    labels: {},
  })
  doc.setProperties({ keywords: '' })
  writeFileSync(
    `${OUT}fabricated-${filenameFor(LECTURE, 'sfake')}`,
    Buffer.from(doc.output('arraybuffer')),
  )
  console.log(`  fabricated-${filenameFor(LECTURE, 'sfake')}`)
}

console.log(`\nwrote to ${OUT}`)
