/**
 * Resolve a sitting, then play it.
 *
 * This exists as its own component for one reason: the plan has to be written
 * to the log before the first item is drawn, and a write cannot happen during
 * render. So the route resolves in an effect and holds the screen for one frame
 * until the log answers. That frame is the price of never deriving the same
 * sitting twice.
 *
 * WHY THE PLAN IS READ BACK RATHER THAN REUSED. `derive` is called once, and
 * its result goes into the log; everything after that reads `opened.plan`. The
 * tempting shortcut is to keep the derived list in a variable and use it, since
 * it is right there and identical today. It is identical only today. The whole
 * failure this replaces was code that re-derived from the current bank and got
 * a different answer than the one the student was actually served, so the
 * derived value is deliberately dropped on the floor after it is recorded.
 *
 * WITHDRAWALS. A planned item can vanish, because an item can be deleted or
 * rewritten between two sittings. The plan still names it, so without handling
 * the sitting could never be completed and the student would be stuck on a
 * module they cannot finish. A missing item is recorded as withdrawn, which
 * satisfies the plan without scoring, and the student answers the rest. That is
 * the same treatment free response already gets, and it puts the cost of an
 * edit on the course rather than on whoever happened to be mid-module.
 */

import { useEffect, useMemo } from 'react'
import { poolOf, type Bank } from '../content/load.ts'
import { derive } from '../seed.ts'
import { openSessionFor, type LogEntry, type PlannedItem } from '../store/log.ts'
import { useProgress } from '../store/useProgress.ts'
import { SessionPlayer } from './SessionPlayer.tsx'

interface Props {
  bank: Bank
  andrewId: string
  onFinish: () => void
  onQuit: () => void
}

export function SessionRoute({ bank, andrewId, onFinish, onQuit }: Props) {
  const log = useProgress((s) => s.log)
  const append = useProgress((s) => s.append)
  const openSession = useProgress((s) => s.openSession)

  const open = useMemo(() => openSessionFor(log, bank.lecture), [log, bank.lecture])

  useEffect(() => {
    if (open) return
    const plan: PlannedItem[] = derive(
      andrewId, bank.lecture, poolOf(bank), bank.pool_version, bank.serve,
    ).map((s) => ({ id: s.id, variant: s.variant, opts: s.option_order }))
    openSession(bank.lecture, andrewId, plan, {
      pool_version: bank.pool_version, serve: bank.serve,
    })
  }, [open, bank, andrewId, openSession])

  // Planned items that are still answerable, in the order they were planned.
  const { served, missing } = useMemo(() => {
    if (!open) return { served: [], missing: [] as string[] }
    const byId = new Map(bank.items.map((i) => [i.id, i]))
    const settled = new Set(open.entries.map((e) => e.itemId))
    return {
      served: open.opened.plan
        .filter((p) => byId.has(p.id))
        .map((p) => ({ id: p.id, variant: p.variant, option_order: p.opts })),
      missing: open.opened.plan
        .filter((p) => !byId.has(p.id) && !settled.has(p.id))
        .map((p) => p.id),
    }
  }, [open, bank])

  useEffect(() => {
    if (!open || !missing.length) return
    const already = new Set(
      log.flatMap((e) =>
        'itemId' in e && e.session === open.session ? [e.itemId as string] : [],
      ),
    )
    const fresh = missing.filter((id) => !already.has(id))
    if (!fresh.length) return
    const at = Date.now()
    append(fresh.map((itemId) => ({ t: 'withdrawn' as const, session: open.session, itemId, at })))
  }, [open, missing, log, append])

  if (!open) return <p className="p-8 text-[var(--muted)]">Opening…</p>

  const itemsById = Object.fromEntries(bank.items.map((i) => [i.id, i]))
  return (
    <SessionPlayer
      key={`${bank.lecture}/${open.session}`}
      lecture={bank.lecture}
      sessionId={open.session}
      served={served}
      itemsById={itemsById}
      resumed={open.entries}
      onAnswer={(entry: LogEntry) => append([entry])}
      onFinish={onFinish}
      onQuit={onQuit}
    />
  )
}
