/**
 * End of a module: the score, and the button that issues the evidence PDF.
 *
 * The PDF is built here from the *log*, not from anything held in component
 * state, so the same file can be regenerated later from Home and comes out
 * identical. That matters more than it looks: the commonest support request in
 * a scheme like this is "I closed the tab before the download finished".
 */

import { useState } from 'react'
import type { Bank } from '../content/load.ts'
import { poolOf } from '../content/load.ts'
import { derive } from '../seed.ts'
import { buildAttestation, type ItemRecord } from '../evidence/payload.ts'
import { buildPdf, filenameFor } from '../evidence/pdf.ts'
import { itemScore, latestCompleted, sittingScore, type Event } from '../store/log.ts'
import { Markdown } from './Markdown.tsx'

const APP_VERSION = '0.1.0'
const BUILD_COMMIT: string = import.meta.env?.VITE_BUILD_COMMIT ?? '0'.repeat(40)

interface Props {
  bank: Bank
  log: Event[]
  andrewId: string
  displayName: string
  onHome: () => void
}

export function Summary({ bank, log, andrewId, displayName, onHome }: Props) {
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const session = latestCompleted(log, bank.lecture)

  if (!session) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <p className="text-[var(--muted)]">No completed sitting for {bank.lecture} yet.</p>
        <button type="button" onClick={onHome} className="btn-primary mt-6">
          Back
        </button>
      </div>
    )
  }

  const byId = Object.fromEntries(bank.items.map((i) => [i.id, i]))

  async function download() {
    try {
      const served = derive(andrewId, bank.lecture, poolOf(bank), bank.pool_version, bank.serve)

      // Order the log entries by the served order rather than by time, so the
      // payload's item list and the re-derived list line up positionally and
      // the verifier compares like with like.
      const entryFor = new Map(session!.entries.map((e) => [e.itemId, e]))
      const items: ItemRecord[] = served.flatMap((s) => {
        const e = entryFor.get(s.id)
        if (!e) return []
        return [{
          id: e.itemId,
          v: e.variant,
          opts: e.opts,
          ans: e.chosen,
          first_ms: e.firstMs,
          total_ms: e.totalMs,
          tries: e.tries,
          first_ok: e.firstOk,
          revealed: e.revealed,
        }]
      })

      const attestation = buildAttestation({
        andrewId,
        name: displayName,
        lecture: bank.lecture,
        poolVersion: bank.pool_version,
        serve: bank.serve,
        appVersion: APP_VERSION,
        buildCommit: BUILD_COMMIT,
        contentSha256: '',
        startedAt: new Date(session!.startedAt).toISOString(),
        finishedAt: new Date(session!.finishedAt).toISOString(),
        elapsedMs: session!.finishedAt - session!.startedAt,
        activeMs: session!.activeMs,
        tzOffsetMin: -new Date().getTimezoneOffset(),
        resumes: 0,
        served,
        items,
      })

      const labels: Record<string, { prompt: string; chosen: string }> = {}
      for (const rec of items) {
        const item = byId[rec.id]
        const idx = rec.ans[0] ? Number(rec.ans[0].slice(3)) : -1
        labels[rec.id] = {
          prompt: (item?.prompt ?? '').split('\n')[0] ?? rec.id,
          chosen: (item?.options?.[idx] ?? '(written answer)').slice(0, 70),
        }
      }

      const doc = await buildPdf({
        attestation,
        name: displayName,
        andrewId,
        lecture: bank.lecture,
        lectureTitle: bank.title,
        finishedAtLocal: new Date(session!.finishedAt).toLocaleString(),
        elapsedMs: session!.finishedAt - session!.startedAt,
        activeMs: session!.activeMs,
        resumes: 0,
        items,
        labels,
      })
      doc.save(filenameFor(bank.lecture, andrewId))
      setError(null)
    } catch (err) {
      setError(String(err))
    }
  }

  const minutes = Math.round(session.activeMs / 60000)
  const score = sittingScore(session.entries)

  return (
    <div className="mx-auto max-w-2xl px-4 py-16 text-center">
      <p className="text-5xl" aria-hidden>
        ✓
      </p>
      <h1 className="mt-4 text-2xl font-bold">{bank.lecture.toUpperCase()} complete</h1>
      <p className="mt-2 text-[15px] text-[var(--muted)]">
        {session.firstTry} of {session.entries.length} right first time, in about{' '}
        {minutes || 1} minute{minutes === 1 ? '' : 's'}.
      </p>
      {score !== null && (
        <p className="mt-1 text-[15px]">
          <span className="text-[var(--muted)]">This run scored </span>
          <strong>{Math.round(score * 100)}%</strong>
          <span className="text-[var(--muted)]">
            {' '}
            (a second attempt is worth half, a revealed answer nothing).
          </span>
        </p>
      )}
      <p className="mt-1 text-sm text-[var(--muted)]">
        The grade is for finishing, not for the score.
      </p>

      <button type="button" onClick={download} className="btn-primary mt-8 w-full">
        Download the PDF
      </button>
      <p className="mt-2 text-xs text-[var(--muted)]">
        Upload it to Canvas. You can download it again from the module list, on
        this browser: progress is not stored anywhere else, so download it now
        if you might finish on a different computer.
      </p>
      {error && <p className="mt-3 text-sm text-[var(--wrong)]">{error}</p>}

      <button type="button" onClick={onHome} className="btn-quiet mt-6 w-full">
        Back to modules
      </button>

      {/* The review list. This is where the explanations are most likely to be
          read: the module is over, nothing is at stake, and the student already
          knows which ones they missed. Mid-session the same text competes with
          wanting to get to the end. */}
      <section className="mt-12 text-left">
        <h2 className="mb-4 text-lg font-bold">Your answers</h2>
        <ul className="space-y-3">
          {session.entries.map((e, i) => {
            const item = byId[e.itemId]
            if (!item) return null
            const idx = e.chosen[0] ? Number(e.chosen[0].slice(3)) : -1
            const chosen = item.options?.[idx]
            const open = expanded === e.itemId
            return (
              <li
                key={e.itemId}
                className="rounded-xl border-2 border-[var(--border)] bg-[var(--surface-raised)]"
              >
                <button
                  type="button"
                  onClick={() => setExpanded(open ? null : e.itemId)}
                  aria-expanded={open}
                  className="flex w-full items-start gap-3 p-3 text-left"
                >
                  <span
                    aria-hidden
                    className={e.firstOk ? 'text-[var(--correct)]' : 'text-[var(--muted)]'}
                  >
                    {e.revealed ? '·' : e.firstOk ? '✓' : `${e.tries}×`}
                  </span>
                  <span className="flex-1 text-sm">
                    <span className="text-[var(--muted)]">{i + 1}. </span>
                    {(item.prompt ?? '').split('\n').find((l) => l.trim()) ?? e.itemId}
                  </span>
                  <span className="text-[var(--muted)]" aria-hidden>
                    {open ? '−' : '+'}
                  </span>
                </button>
                {open && (
                  <div className="border-t border-[var(--border)] p-3">
                    <p className="mb-2 text-xs text-[var(--muted)]">
                      {e.revealed
                        ? 'Revealed, so it scored 0.'
                        : `Answered in ${e.tries} ${e.tries === 1 ? 'attempt' : 'attempts'}, scoring ${Math.round(itemScore(e) * 100)}%.`}
                    </p>
                    {chosen && (
                      <p className="mb-2 text-sm">
                        <span className="text-[var(--muted)]">You chose: </span>
                        {chosen}
                      </p>
                    )}
                    {!e.firstOk && item.answer && (
                      <p className="mb-2 text-sm">
                        <span className="text-[var(--muted)]">Answer: </span>
                        {item.answer}
                      </p>
                    )}
                    <Markdown className="text-sm leading-relaxed">{item.evidence}</Markdown>
                    <p className="mt-2 text-xs text-[var(--muted)]">
                      Source: {item.source.file}
                      {item.source.heading ? ` · ${item.source.heading}` : ''}
                    </p>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      </section>
    </div>
  )
}
