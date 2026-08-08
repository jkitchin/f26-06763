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
 * How well one item was answered, from 1 down to 0.
 *
 *   right first time      1
 *   right on the second   0.5
 *   third                 0.33
 *   revealed              0
 *
 * 1/tries rather than a lookup table, because it needs no thresholds and
 * degrades sensibly however many options an item has. Revealing scores zero
 * whatever was clicked afterwards: the escape hatch exists so a stuck student
 * can finish, and finishing is what earns the credit, but it is not knowing.
 */
export function itemScore(entry: LogEntry): number {
  if (entry.revealed) return 0
  return 1 / Math.max(1, entry.tries)
}

/**
 * Whether an item can contribute to mastery at all.
 *
 * Free-response items are scored by the student against a checklist, and they
 * commit with tries = 1 by construction, so counting them would hand everybody
 * a free 1.0 and quietly inflate every score. Mastery measures the items that
 * were actually graded.
 */
export function isGradeable(entry: LogEntry): boolean {
  return entry.chosen.length > 0
}

/** Mean item score over one sitting, or null if it graded nothing. */
export function sittingScore(entries: readonly LogEntry[]): number | null {
  const gradeable = entries.filter(isGradeable)
  if (!gradeable.length) return null
  return gradeable.reduce((n, e) => n + itemScore(e), 0) / gradeable.length
}

/**
 * Score at which each level is reached. Five is "everything first time".
 *
 * Deliberately not a straight percentage: on a six-item module one second
 * attempt costs 0.083, and a student who got everything right except one they
 * needed two goes at should not drop two levels for it.
 */
const LEVEL_AT = [0.95, 0.8, 0.65, 0.45] as const

/**
 * Mastery level for a lecture, from the student's BEST completed sitting.
 *
 * Best rather than latest, and this is the load-bearing choice. If a casual
 * second run could lower the number, the rational move would be to stop
 * practising once the number looked good, which is the exact opposite of what
 * the thing is for. Practising can only help.
 *
 * Level 1 means completed, which is the only level that matters for credit.
 * Two through five are for anyone who wants them.
 *
 * Recomputed on every read rather than incremented and stored, so there is no
 * counter to edit.
 */
export function levelFor(
  log: readonly LogEntry[],
  lecture: string,
  servedFor: (lecture: string) => number,
): number {
  const done = completedFor(log, lecture, servedFor)
  if (!done.length) return 0
  const best = Math.max(...done.map((s) => sittingScore(s.entries) ?? 0))
  return Math.min(MAX_LEVEL, 1 + LEVEL_AT.filter((t) => best >= t).length)
}

/** The best score itself, for showing a percentage next to the dots. */
export function bestScoreFor(
  log: readonly LogEntry[],
  lecture: string,
  servedFor: (lecture: string) => number,
): number | null {
  const done = completedFor(log, lecture, servedFor)
  if (!done.length) return null
  return Math.max(...done.map((s) => sittingScore(s.entries) ?? 0))
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

/**
 * The unfinished sitting for this lecture, if there is one.
 *
 * This is what makes the paragraph above true rather than aspirational. An
 * earlier version derived the id from Date.now() at the moment Start was
 * clicked and only wrote to the log when the whole module finished, so a
 * refresh at item six minted a new id and discarded five answers. Entries are
 * now appended as they are committed, and a returning student rejoins the
 * sitting they left by looking it up here.
 */
export function openSessionFor(
  log: readonly LogEntry[],
  lecture: string,
  servedFor: (lecture: string) => number,
): string | null {
  const open = sessionsOf(log, servedFor)
    .filter((s) => s.lecture === lecture && !s.complete)
    .sort((a, b) => a.finishedAt - b.finishedAt)
  return open.length ? open[open.length - 1]!.session : null
}

/** The entries already recorded for one sitting, in the order they were answered. */
export function entriesFor(log: readonly LogEntry[], session: string): LogEntry[] {
  return log.filter((e) => e.session === session).sort((a, b) => a.at - b.at)
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
