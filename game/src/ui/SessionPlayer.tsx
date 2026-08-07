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
 * Timing is recorded per item, split into "time to first answer" and "total
 * time", because with retry-until-right the total is mostly a function of how
 * many tries it took and the first is the one that means anything.
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
  onFinish: (entries: LogEntry[]) => void
  onQuit: () => void
}

type Phase = 'predict' | 'answer' | 'feedback'

export function SessionPlayer({
  lecture,
  sessionId,
  served,
  itemsById,
  onFinish,
  onQuit,
}: Props) {
  const [at, setAt] = useState(0)
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [phase, setPhase] = useState<Phase>('answer')
  const [selected, setSelected] = useState<number | null>(null)
  const [tries, setTries] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [prediction, setPrediction] = useState('')

  const startedAt = useRef(Date.now())
  const firstAnswerMs = useRef<number | null>(null)

  const current = served[at]
  const item = current ? itemsById[current.id] : undefined

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

  const isPredict = !!item?.predict
  const isFree = !item?.options?.length

  // Reset per item. Deliberately keyed on `at` rather than on the item id, so
  // an item that somehow appears twice still gets a clean slate.
  useEffect(() => {
    setPhase(isPredict ? 'predict' : 'answer')
    setSelected(null)
    setTries(0)
    setRevealed(false)
    setPrediction('')
    startedAt.current = Date.now()
    firstAnswerMs.current = null
  }, [at, isPredict])

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
      const next = [...entries, entry]
      setEntries(next)
      if (at + 1 >= served.length) onFinish(next)
      else setAt(at + 1)
    },
    [at, current, entries, item, lecture, onFinish, served.length, sessionId, tries],
  )

  const check = useCallback(() => {
    if (selected === null || !item) return
    if (firstAnswerMs.current === null) {
      firstAnswerMs.current = Date.now() - startedAt.current
    }
    const correct = shown[selected]?.text === item.answer
    if (correct) {
      setPhase('feedback')
    } else {
      // Retry until right: the module is graded on completion, so a wrong
      // answer costs a second attempt and the evidence records that it took two.
      setTries((n) => n + 1)
      setPhase('feedback')
    }
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

  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 py-6">
      <header className="mb-6 flex items-center gap-4">
        <button
          type="button"
          onClick={onQuit}
          className="text-sm text-[var(--muted)] hover:text-[var(--ink)]"
          aria-label="Leave this session"
        >
          ✕
        </button>
        <div
          className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--surface-raised)]"
          role="progressbar"
          aria-valuenow={at}
          aria-valuemax={served.length}
        >
          <div
            className="h-full rounded-full bg-[var(--brand)] transition-[width]"
            style={{ width: `${(at / served.length) * 100}%` }}
          />
        </div>
        <span className="font-mono text-sm text-[var(--muted)]">
          {at + 1}/{served.length}
        </span>
      </header>

      <main className="flex-1">
        <p className="mb-1 font-mono text-xs uppercase tracking-wide text-[var(--muted)]">
          {item.kind.replace(/_/g, ' ')} · rung {item.rung}
        </p>
        <Markdown className="prose-tight mb-6 text-[17px] leading-relaxed">
          {item.prompt}
        </Markdown>

        {phase === 'predict' && item.predict && (
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

        {phase !== 'predict' && !isFree && (
          <ChoiceGrid
            options={shown.map((o) => o.text)}
            selected={selected}
            onSelect={setSelected}
            // Only paint the right answer once the item is actually over:
            // got it right, or gave up via "Show me". Revealing it on a wrong
            // first try and then offering "Try again" is not a retry, it is a
            // copy exercise.
            revealed={
              phase !== 'feedback'
                ? null
                : { answerIndex: settled ? answerShownIndex : -1 }
            }
          />
        )}

        {phase !== 'predict' && isFree && (
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

        {phase === 'feedback' && (
          <aside
            className={`mt-6 rounded-xl border-2 p-4 ${
              settled
                ? 'border-[var(--correct)] bg-[var(--correct-wash)]'
                : 'border-[var(--wrong)] bg-[var(--wrong-wash)]'
            }`}
          >
            {/* Nothing that gives the answer away until the item is actually
                over. The evidence explains *why* the answer is the answer, so
                showing it beside a "Try again" button turns the retry into a
                reading-comprehension exercise and throws away the second
                attempt, which is the only part that involves thinking. */}
            {settled ? (
              <>
                {item.predict && prediction.trim() && (
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
              // The escape hatch. A student stuck on item 6 with no way out is a
              // student who never finishes, and completion is the grade. It is
              // recorded, and it forfeits first-try credit.
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
            {isFree || correctNow || revealed
              ? at + 1 >= served.length
                ? 'Finish'
                : 'Continue'
              : 'Try again'}
          </button>
        )}
      </footer>
    </div>
  )
}
