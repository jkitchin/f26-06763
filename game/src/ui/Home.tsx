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
import {
  WRONG_PENALTY, bestScoreFor, levelFor, nextAttemptFor, type Event,
} from '../store/log.ts'

interface Props {
  banks: Record<string, Bank>
  log: Event[]
  andrewId: string
  storageOk: boolean
  onStart: (lecture: string) => void
  onEvidence: (lecture: string) => void
  onMap: () => void
}

export function Home({ banks, log, andrewId, storageOk, onStart, onEvidence, onMap }: Props) {
  const lectures = Object.values(banks).sort((a, b) => a.lecture.localeCompare(b.lecture))

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-bold">Practice modules</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Signed in as <span className="font-mono">{andrewId}</span>
        </p>
        {/* The list is the primary view and stays that way. The map is the
            other way in, for the question a list cannot answer: which session
            covered this, and what does it depend on. */}
        <button type="button" onClick={onMap} className="btn-secondary mt-4">
          Explore the course map
        </button>
      </header>

      {!storageOk && (
        <p
          role="alert"
          className="mb-4 rounded-xl border-2 border-[var(--wrong)] bg-[var(--wrong-wash)] p-3 text-sm"
        >
          <strong>This browser is not saving your progress.</strong> Private
          browsing and some privacy settings block it. Finish a module in this
          tab and download the PDF before closing it, or switch to a normal
          window.
        </p>
      )}

      <p className="mb-4 text-sm text-[var(--muted)]">
        A <span className="text-[var(--correct)]">✓</span> means the module is
        complete. Each question is worth a point, less {WRONG_PENALTY.toFixed(2)}{' '}
        for every wrong answer, and the average is the participation score printed
        on your PDF. Answering carefully is worth more than answering fast.
      </p>

      <p className="mb-6 rounded-xl border border-[var(--border)] bg-[var(--surface-raised)] p-3 text-sm text-[var(--muted)]">
        <strong className="text-[var(--ink)]">Progress is saved in this browser
        only.</strong>{' '}
        On another computer, or in a private window, you will start a module
        again from the beginning. Your questions are chosen from your Andrew ID
        and from which attempt you are on, so a first attempt is the same
        wherever you sign in, and practising again gives you different questions
        from the same bank. The PDF is the thing that counts, so finish a module
        and download it in one sitting.
      </p>

      <ul className="space-y-3">
        {lectures.map((bank) => {
          const best = bestScoreFor(log, bank.lecture)
          const done = levelFor(log, bank.lecture) > 0
          const next = nextAttemptFor(log, bank.lecture)
          return (
            <li
              key={bank.lecture}
              className="rounded-xl border-2 border-[var(--border)] bg-[var(--surface-raised)] p-4"
            >
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-sm font-bold uppercase">{bank.lecture}</span>
                <span className="flex-1 text-[15px] font-medium">{bank.title}</span>
                {done && (
                  <span
                    className="text-base text-[var(--correct)]"
                    title="Complete. This is the whole requirement."
                    aria-label="complete"
                  >
                    ✓
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-[var(--muted)]">
                {bank.serve} questions, about {Math.round(bank.serve * 1.2)} minutes
                {done && best !== null && (
                  <> · best run {Math.round(best * 100)}%</>
                )}
                {/* Say which attempt is next before they click, not after. A
                    student who has finished once should know their next run
                    draws different questions and issues its own PDF. */}
                {next > 1 && <> · next is attempt {next}</>}
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
