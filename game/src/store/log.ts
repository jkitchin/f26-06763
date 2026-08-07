/**
 * The append-only event log, and everything derived from it.
 *
 * This is the part that differs most from the app this was adapted from, and
 * the difference is deliberate.
 *
 * That app stored a per-lesson `{ level, sessions, lastCompleted }` record and
 * folded each answer into a scheduler, discarding the answers themselves. Both
 * halves are wrong here. The evidence PDF *is* the discarded per-item data, so
 * it has to be kept; and a stored completion flag is a boolean somebody can set
 * to true in devtools in about four seconds.
 *
 * So nothing about completion is stored. The log records what happened, one
 * entry per answered item, and every notion of progress is recomputed from it.
 * There is no `level` to raise and no `completed` to flip: to fake a module you
 * would have to author a log with the right item ids, in the order your Andrew
 * ID derives to, with plausible timings. That is strictly more work than
 * answering eight multiple-choice questions with the answer key open, which you
 * can also do, because the answer key ships in this bundle and the syllabus
 * says so.
 *
 * The attack is not blocked. It is made pointless, which is cheaper and holds
 * up better.
 */

export const MAX_LEVEL = 5

/** One answered item. Append-only: entries are never edited or removed. */
export interface LogEntry {
  /** Groups entries into a sitting. Derived, not random: see newSessionId. */
  session: string
  lecture: string
  itemId: string
  variant: string
  /** The option order this student was served, so the shuffle stays checkable. */
  opts: number[]
  /** Option ids, indexing the original pool order. Never display positions. */
  chosen: string[]
  tries: number
  /** Integer milliseconds. No floats: they are the cross-language mismatch. */
  firstMs: number
  totalMs: number
  firstOk: boolean
  revealed: boolean
  at: number
}

export interface SessionSummary {
  session: string
  lecture: string
  entries: LogEntry[]
  startedAt: number
  finishedAt: number
  activeMs: number
  firstTry: number
  /** True once every served item has an entry. */
  complete: boolean
}

/**
 * Group the log into sittings, and decide which are complete.
 *
 * `servedFor` returns how many items that lecture serves, so completeness is a
 * question about the content rather than about a stored flag.
 */
export function sessionsOf(
  log: readonly LogEntry[],
  servedFor: (lecture: string) => number,
): SessionSummary[] {
  const byId = new Map<string, LogEntry[]>()
  for (const entry of log) {
    const list = byId.get(entry.session)
    if (list) list.push(entry)
    else byId.set(entry.session, [entry])
  }

  const out: SessionSummary[] = []
  for (const [session, entries] of byId) {
    const lecture = entries[0]!.lecture
    // Distinct items, not entry count: a resumed session that re-logged an item
    // must not count twice toward completion.
    const distinct = new Set(entries.map((e) => e.itemId)).size
    out.push({
      session,
      lecture,
      entries,
      startedAt: Math.min(...entries.map((e) => e.at - e.totalMs)),
      finishedAt: Math.max(...entries.map((e) => e.at)),
      activeMs: entries.reduce((n, e) => n + e.totalMs, 0),
      firstTry: entries.filter((e) => e.firstOk).length,
      complete: distinct >= servedFor(lecture),
    })
  }
  return out.sort((a, b) => a.finishedAt - b.finishedAt)
}

/** Completed sittings for one lecture, oldest first. */
export function completedFor(
  log: readonly LogEntry[],
  lecture: string,
  servedFor: (lecture: string) => number,
): SessionSummary[] {
  return sessionsOf(log, servedFor).filter((s) => s.lecture === lecture && s.complete)
}

/**
 * Mastery level for a lecture: how many times it has been completed, capped.
 *
 * Recomputed on every read rather than incremented and stored. The cost is a
 * pass over the log; the benefit is that there is no counter to edit.
 */
export function levelFor(
  log: readonly LogEntry[],
  lecture: string,
  servedFor: (lecture: string) => number,
): number {
  return Math.min(MAX_LEVEL, completedFor(log, lecture, servedFor).length)
}

/** The most recent completed sitting, which is what the PDF is issued from. */
export function latestCompleted(
  log: readonly LogEntry[],
  lecture: string,
  servedFor: (lecture: string) => number,
): SessionSummary | null {
  const done = completedFor(log, lecture, servedFor)
  return done.length ? done[done.length - 1]! : null
}

/**
 * Session ids are derived, not random.
 *
 * Math.random would make a resumed session after a page reload a *new* session,
 * so a student who refreshed at item 6 would have two half-sittings and no
 * completion. Deriving from (andrew id, lecture, start-of-sitting) means a
 * reload rejoins the sitting it left.
 */
export function newSessionId(andrewId: string, lecture: string, startedAt: number): string {
  return `${andrewId}/${lecture}/${startedAt}`
}

/** Total answered items, for the HUD. */
export function answeredCount(log: readonly LogEntry[]): number {
  return log.length
}

/** First-try accuracy across the whole log, for the dashboard. */
export function accuracy(log: readonly LogEntry[]): number {
  if (!log.length) return 0
  return log.filter((e) => e.firstOk).length / log.length
}
