/**
 * The module list.
 *
 * A flat, honest list rather than the winding path the source app used. That
 * app's path map earns its keep because its units are a genuine prerequisite
 * chain; here the lectures are already numbered, already scheduled, and already
 * listed on the course site, and inventing a second ordering on top would only
 * disagree with the first one.
 *
 * Level comes from `levelFor`, which counts completed sittings in the log. It is
 * recomputed on every render, so there is no stored number to tamper with.
 */

import type { Bank } from '../content/load.ts'
import { levelFor, MAX_LEVEL, type LogEntry } from '../store/log.ts'

interface Props {
  banks: Record<string, Bank>
  log: LogEntry[]
  andrewId: string
  onStart: (lecture: string) => void
  onEvidence: (lecture: string) => void
}

export function Home({ banks, log, andrewId, onStart, onEvidence }: Props) {
  const lectures = Object.values(banks).sort((a, b) => a.lecture.localeCompare(b.lecture))
  const servedFor = (id: string) => banks[id]?.serve ?? Infinity

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-bold">Practice modules</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Signed in as <span className="font-mono">{andrewId}</span>
        </p>
      </header>

      <ul className="space-y-3">
        {lectures.map((bank) => {
          const level = levelFor(log, bank.lecture, servedFor)
          const done = level > 0
          return (
            <li
              key={bank.lecture}
              className="rounded-xl border-2 border-[var(--border)] bg-[var(--surface-raised)] p-4"
            >
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-sm font-bold uppercase">{bank.lecture}</span>
                <span className="flex-1 text-[15px] font-medium">{bank.title}</span>
                <span
                  className="font-mono text-xs text-[var(--muted)]"
                  aria-label={`level ${level} of ${MAX_LEVEL}`}
                >
                  {'●'.repeat(level)}
                  {'○'.repeat(MAX_LEVEL - level)}
                </span>
              </div>
              <p className="mt-1 text-sm text-[var(--muted)]">
                {bank.serve} questions, about {Math.round(bank.serve * 1.2)} minutes
              </p>
              <div className="mt-3 flex gap-2">
                <button type="button" onClick={() => onStart(bank.lecture)} className="btn-primary">
                  {done ? 'Practise again' : 'Start'}
                </button>
                {done && (
                  <button
                    type="button"
                    onClick={() => onEvidence(bank.lecture)}
                    className="btn-quiet"
                  >
                    Download PDF
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ul>

      {!lectures.length && (
        <p className="text-[var(--muted)]">No modules published yet.</p>
      )}
    </div>
  )
}
