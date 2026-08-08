/**
 * The session: one item at a time, with the predict-then-reveal mechanic.
 *
 * The commit step is the whole point and is not decoration. Rozenblit and
 * Keil's result, which course/optional/generating-is-not-learning.md builds on,
 * is that people cannot tell whether they understand something until they try
 * to produce the explanation. Reading an option list and recognising the right
 * answer is exactly the fluency signal that experiment says not to trust. So on
 * a predict item the player has to commit to an expectation *before* the
 * options appear, and is then shown the gap between it and the measurement.
 *
 * Two properties this component has to preserve, and an earlier version of it
 * preserved neither:
 *
 * ANSWERS ARE PERSISTED AS THEY HAPPEN. Entries used to accumulate in component
 * state and reach the log only when the whole module finished, so quitting or
 * refreshing at item six discarded five answers. Each entry now goes to the log
 * on commit, and a returning student resumes from what is already there.
 *
 * GOING BACK IS REVIEW, NOT A SECOND ATTEMPT. The evidence PDF records
 * first_ok, tries and per-item timing. If an item could be re-answered after
 * its answer was revealed, those fields would stop measuring anything and
 * first-try accuracy would be useless as course telemetry. So an answered item
 * is read-only: it shows what was chosen, whether it was right first time, and
 * the evidence, which is what a student wants from a back button anyway.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Item } from '../content/load.ts'
import type { ServedItem } from '../seed.ts'
import type { LogEntry } from '../store/log.ts'
import { ChoiceGrid } from './ChoiceGrid.tsx'
import { Markdown } from './Markdown.tsx'

interface Props {
  lecture: string
  sessionId: string
  served: ServedItem[]
  itemsById: Record<string, Item>
  /** Entries already in the log for this sitting; non-empty when resuming. */
  resumed: LogEntry[]
  /** Called the moment an item is committed, so nothing lives only in memory. */
  onAnswer: (entry: LogEntry) => void
  onFinish: () => void
  onQuit: () => void
}

type Phase = 'predict' | 'answer' | 'feedback'

export function SessionPlayer({
  lecture,
  sessionId,
  served,
  itemsById,
  resumed,
  onAnswer,
  onFinish,
  onQuit,
}: Props) {
  const [entries, setEntries] = useState<LogEntry[]>(resumed)
  /** The item being answered. Everything before it is answered and read-only. */
  const cursor = entries.length
  const [at, setAt] = useState(cursor)
  const reviewing = at < cursor

  const [phase, setPhase] = useState<Phase>('answer')
  const [selected, setSelected] = useState<number | null>(null)
  const [tries, setTries] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [prediction, setPrediction] = useState('')

  const startedAt = useRef(Date.now())
  const firstAnswerMs = useRef<number | null>(null)

  const current = served[at]
  const item = current ? itemsById[current.id] : undefined
  const record = reviewing ? entries[at] : undefined

  /** Options in this student's served order, with the key back to pool order. */
  const shown = useMemo(() => {
    if (!item?.options || !current) return []
    return current.option_order.map((poolIndex) => ({
      poolIndex,
      text: item.options![poolIndex]!,
    }))
  }, [item, current])

  const answerShownIndex = useMemo(
    () => shown.findIndex((o) => o.text === item?.answer),
    [shown, item],
  )

  /** Where the recorded choice sits in the order this student was served. */
  const recordedShownIndex = useMemo(() => {
    if (!record?.chosen.length) return -1
    const poolIndex = Number(record.chosen[0]!.slice(3))
    return record.opts.indexOf(poolIndex)
  }, [record])

  const isPredict = !!item?.predict
  const isFree = !item?.options?.length

  // Reset per item, but only for the item being answered: moving back to review
  // must not restart anybody's clock.
  useEffect(() => {
    if (at !== cursor) return
    setPhase(isPredict ? 'predict' : 'answer')
    setSelected(null)
    setTries(0)
    setRevealed(false)
    setPrediction('')
    startedAt.current = Date.now()
    firstAnswerMs.current = null
  }, [at, cursor, isPredict])

  const commit = useCallback(
    (correct: boolean, chosenPoolIndex: number | null, wasRevealed: boolean) => {
      if (!current || !item) return
      const now = Date.now()
      const entry: LogEntry = {
        session: sessionId,
        lecture,
        itemId: current.id,
        variant: current.variant,
        opts: current.option_order,
        chosen: chosenPoolIndex === null ? [] : [`opt${chosenPoolIndex}`],
        tries: Math.max(1, tries + 1),
        firstMs: Math.round(firstAnswerMs.current ?? now - startedAt.current),
        totalMs: Math.round(now - startedAt.current),
        // A revealed answer is never a first-try success, whatever was clicked.
        firstOk: correct && tries === 0 && !wasRevealed,
        revealed: wasRevealed,
        at: now,
      }
      // Straight to the log, not held until the end.
      onAnswer(entry)
      setEntries((prev) => [...prev, entry])
      if (at + 1 >= served.length) onFinish()
      else setAt(at + 1)
    },
    [at, current, item, lecture, onAnswer, onFinish, served.length, sessionId, tries],
  )

  const check = useCallback(() => {
    if (selected === null || !item) return
    if (firstAnswerMs.current === null) {
      firstAnswerMs.current = Date.now() - startedAt.current
    }
    if (shown[selected]?.text !== item.answer) setTries((n) => n + 1)
    setPhase('feedback')
  }, [item, selected, shown])

  const next = useCallback(() => {
    if (!item) return
    const correct = shown[selected ?? -1]?.text === item.answer
    if (correct || revealed) {
      commit(correct, shown[selected ?? -1]?.poolIndex ?? null, revealed)
    } else {
      setPhase('answer')
      setSelected(null)
    }
  }, [commit, item, revealed, selected, shown])

  if (!current || !item) return null

  const correctNow = shown[selected ?? -1]?.text === item.answer
  /** The item is finished: got it right, gave up, or it is not gradeable. */
  const settled = correctNow || revealed || isFree
  const showFeedback = reviewing || phase === 'feedback'
  const wasRight = reviewing ? !!record?.firstOk : settled

  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 py-6">
      <header className="mb-6 flex items-center gap-3">
        <button
          type="button"
          onClick={onQuit}
          className="text-sm text-[var(--muted)] hover:text-[var(--ink)]"
          aria-label="Leave this session"
        >
          ✕
        </button>

        <button
          type="button"
          onClick={() => setAt((n) => Math.max(0, n - 1))}
          disabled={at === 0}
          className="text-sm text-[var(--muted)] hover:text-[var(--ink)] disabled:opacity-30"
          aria-label="Previous question"
        >
          ‹
        </button>

        <div
          className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--surface-raised)]"
          role="progressbar"
          aria-valuenow={cursor}
          aria-valuemax={served.length}
        >
          <div
            className="h-full rounded-full bg-[var(--brand)] transition-[width]"
            style={{ width: `${(cursor / served.length) * 100}%` }}
          />
        </div>

        <button
          type="button"
          onClick={() => setAt((n) => Math.min(cursor, n + 1))}
          disabled={at >= cursor}
          className="text-sm text-[var(--muted)] hover:text-[var(--ink)] disabled:opacity-30"
          aria-label="Next question"
        >
          ›
        </button>

        <span className="font-mono text-sm text-[var(--muted)]">
          {at + 1}/{served.length}
        </span>
      </header>

      {reviewing && (
        <p
          className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--surface-raised)]
                     px-3 py-2 text-sm text-[var(--muted)]"
        >
          Reviewing an answered question. Your answer is recorded and cannot be
          changed.
        </p>
      )}

      <main className="flex-1">
        <p className="mb-1 font-mono text-xs uppercase tracking-wide text-[var(--muted)]">
          {item.kind.replace(/_/g, ' ')} · rung {item.rung}
        </p>
        <Markdown className="prose-tight mb-6 text-[17px] leading-relaxed">
          {item.prompt}
        </Markdown>

        {!reviewing && phase === 'predict' && item.predict && (
          <section aria-label="Commit to an expectation">
            <p className="mb-3 text-sm text-[var(--muted)]">{item.predict.ask}</p>
            <textarea
              value={prediction}
              onChange={(e) => setPrediction(e.target.value)}
              rows={3}
              autoFocus
              className="w-full rounded-xl border-2 border-[var(--border)] bg-[var(--surface-raised)]
                         p-3 text-[15px] outline-none focus:border-[var(--brand)]"
              placeholder="Write it down before you look."
            />
            <p className="mt-2 text-xs text-[var(--muted)]">
              This is not graded and is not stored. Writing it is what makes the
              next screen mean something.
            </p>
            <button
              type="button"
              onClick={() => setPhase('answer')}
              disabled={prediction.trim().length < 2}
              className="btn-primary mt-4"
            >
              Lock it in
            </button>
          </section>
        )}

        {(reviewing || phase !== 'predict') && !isFree && (
          <ChoiceGrid
            options={shown.map((o) => o.text)}
            selected={reviewing ? recordedShownIndex : selected}
            onSelect={reviewing ? () => {} : setSelected}
            revealed={
              !showFeedback
                ? null
                : { answerIndex: reviewing || settled ? answerShownIndex : -1 }
            }
          />
        )}

        {!reviewing && phase !== 'predict' && isFree && (
          <section aria-label="Write from memory">
            <textarea
              rows={7}
              autoFocus
              className="w-full rounded-xl border-2 border-[var(--border)] bg-[var(--surface-raised)]
                         p-3 text-[15px] outline-none focus:border-[var(--brand)]"
              placeholder="Write the mechanism. Stop when you stall, and note where."
            />
            {phase === 'feedback' && item.checklist && (
              <ul className="mt-4 space-y-2">
                {item.checklist.map((c) => (
                  <li key={c.needle} className="flex gap-2 text-sm">
                    <span aria-hidden>▫</span>
                    <span>{c.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {reviewing && isFree && item.checklist && (
          <ul className="space-y-2">
            {item.checklist.map((c) => (
              <li key={c.needle} className="flex gap-2 text-sm">
                <span aria-hidden>▫</span>
                <span>{c.text}</span>
              </li>
            ))}
          </ul>
        )}

        {showFeedback && (
          <aside
            className={`mt-6 rounded-xl border-2 p-4 ${
              wasRight
                ? 'border-[var(--correct)] bg-[var(--correct-wash)]'
                : 'border-[var(--wrong)] bg-[var(--wrong-wash)]'
            }`}
          >
            {reviewing && (
              <p className="mb-3 text-sm text-[var(--muted)]">
                {record?.revealed
                  ? 'You revealed this one.'
                  : record?.firstOk
                    ? 'Right first time.'
                    : `Answered in ${record?.tries ?? 2} attempts.`}
              </p>
            )}
            {/* Nothing that gives the answer away until the item is over. The
                evidence explains *why* the answer is the answer, so showing it
                beside a "Try again" button turns the retry into a reading
                exercise and throws away the second attempt. */}
            {reviewing || settled ? (
              <>
                {!reviewing && item.predict && prediction.trim() && (
                  <p className="mb-3 text-sm">
                    <span className="text-[var(--muted)]">You predicted: </span>
                    <span className="italic">{prediction.trim()}</span>
                  </p>
                )}
                <Markdown className="text-[15px] leading-relaxed">{item.evidence}</Markdown>
                <p className="mt-3 text-xs text-[var(--muted)]">
                  Source: {item.source.file}
                  {item.source.heading ? ` · ${item.source.heading}` : ''}
                </p>
              </>
            ) : (
              <p className="text-[15px]">
                Not that one. Have another go, or use <em>Show me</em> if you
                would rather see the answer and the reasoning.
              </p>
            )}
          </aside>
        )}
      </main>

      <footer className="mt-6 flex items-center gap-3">
        {reviewing ? (
          <button type="button" onClick={() => setAt(cursor)} className="btn-primary">
            Back to question {cursor + 1}
          </button>
        ) : (
          <>
            {phase === 'answer' && !isFree && (
              <>
                <button
                  type="button"
                  onClick={check}
                  disabled={selected === null}
                  className="btn-primary"
                >
                  Check
                </button>
                {tries > 0 && (
                  // The escape hatch. A student stuck on item 6 with no way out
                  // is a student who never finishes, and completion is the
                  // grade. It is recorded, and it forfeits first-try credit.
                  <button
                    type="button"
                    onClick={() => {
                      setRevealed(true)
                      setSelected(answerShownIndex)
                      setPhase('feedback')
                    }}
                    className="btn-quiet"
                  >
                    Show me
                  </button>
                )}
              </>
            )}
            {phase === 'answer' && isFree && (
              <button type="button" onClick={() => setPhase('feedback')} className="btn-primary">
                Show the checklist
              </button>
            )}
            {phase === 'feedback' && (
              <button
                type="button"
                onClick={isFree ? () => commit(true, null, false) : next}
                className="btn-primary"
                autoFocus
              >
                {settled ? (at + 1 >= served.length ? 'Finish' : 'Continue') : 'Try again'}
              </button>
            )}
          </>
        )}
      </footer>
    </div>
  )
}
