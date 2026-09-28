/**
 * What a finished sitting puts on its evidence PDF, read from the log alone.
 *
 * NOTE THE SIGNATURE. `evidenceOf` takes the sitting and nothing else: no bank,
 * no pool, no pool version. That is the fix for the L7 short PDFs, made
 * unrepresentable rather than remembered, and `game/tests/persistence.ts`
 * asserts the arity for the same reason it asserts `sessionsOf`'s.
 *
 * The bug it replaces: the PDF used to re-derive the served list from the bank
 * as it stood *at download time*, and then kept only the answers whose ids were
 * in that list. The pool version is part of the selection seed, so any bump
 * between opening a sitting and downloading its PDF re-derived a different five
 * questions, and the PDF carried only the one or two answers that happened to
 * be in both. L7 went from pool v6 to v7 three hours after release on 9/16, and
 * students who had opened it under v6 uploaded PDFs with one question on them,
 * scored 100% on that one, with nothing on the page to say anything was wrong.
 *
 * Everything here comes from the `opened` event, which was written once when
 * the sitting began and describes what the student was actually served: the
 * plan, the pool version it was drawn from, the serve count, and the attempt.
 * The verifier re-derives against the archived snapshot of that pool version
 * (game/content/pools/), which is what makes a PDF issued weeks later check out.
 */

import type { ServedItem } from '../seed.ts'
import { attemptOf, type SessionSummary } from '../store/log.ts'
import type { ItemRecord } from './payload.ts'

export interface SittingEvidence {
  /** As frozen when the sitting opened, so correcting a typo later cannot break the PDF. */
  andrewId: string
  lecture: string
  /** The pool the plan was drawn from, as recorded when the sitting opened. */
  poolVersion: number
  serve: number
  attempt: number
  /** The plan, in planned order, in the shape the payload hashes. */
  served: ServedItem[]
  /**
   * One record per answered item, in planned order, so the payload's item list
   * and the verifier's re-derivation line up positionally. A withdrawn item
   * (deleted from the bank mid-sitting) has no answer and so no record; the
   * verifier accounts for it by checking the item has left the live bank.
   */
  items: ItemRecord[]
}

export function evidenceOf(session: SessionSummary): SittingEvidence {
  const { opened } = session
  const entryFor = new Map(session.entries.map((e) => [e.itemId, e]))
  const items: ItemRecord[] = opened.plan.flatMap((p) => {
    const e = entryFor.get(p.id)
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
  return {
    andrewId: opened.andrewId,
    lecture: opened.lecture,
    poolVersion: opened.content.pool_version,
    serve: opened.content.serve,
    attempt: attemptOf(session),
    served: opened.plan.map((p) => ({ id: p.id, variant: p.variant, option_order: p.opts })),
    items,
  }
}
