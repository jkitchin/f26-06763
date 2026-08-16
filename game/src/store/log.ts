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

/**
 * One item as it was served. Recorded when a sitting opens, and never revised.
 *
 * This is the content stamp, and it is the whole fix. Completeness used to be
 * judged by comparing the number of items answered against the number the bank
 * serves *right now*, which meant raising `serve` from 8 to 12 silently
 * un-completed every sitting anyone had already finished: their level dropped
 * to zero, their tick vanished, and the button that re-downloads their PDF
 * disappeared with it. Recording the plan answers the question at the only
 * moment it is still true.
 */
export interface PlannedItem {
  id: string
  variant: string
  /** The option order served, indexing the original pool order. */
  opts: number[]
}

/** The premise of a sitting, written once when it opens. */
export interface SessionOpened {
  t: 'opened'
  session: string
  lecture: string
  /** Frozen so a PDF stays reproducible if the student later fixes a typo. */
  andrewId: string
  plan: PlannedItem[]
  /**
   * Which run at this lecture this is, 1-based, fixed when the sitting opens.
   *
   * It selects the questions (see `derive`), so it is a premise of the sitting
   * and not a statistic about it. Stamped here rather than recomputed at PDF
   * time for the reason the plan above is: a student who finishes a second
   * module between starting and finishing this one would otherwise have their
   * attempt number move underneath them, and the PDF would re-derive to items
   * they were never served.
   *
   * Not tamper-proof, and nothing here pretends otherwise: clearing site data
   * resets it to 1 and re-serves attempt 1's questions. It raises the cost of a
   * retake above the cost of answering, which is the whole design goal, and
   * tools/verify_evidence.py flags the same attempt arriving twice.
   */
  attempt: number
  /**
   * Diagnostic only. Never read by any derivation: if you find yourself
   * consulting `content.serve` to decide something, the bug is back.
   */
  content: { pool_version: number; serve: number }
  at: number
}

/**
 * A planned item that is no longer answerable, because it left the bank.
 *
 * It satisfies the plan, so the sitting can still finish, and it is excluded
 * from scoring, so a withdrawal is never a punishment. Same treatment free
 * response already gets.
 */
export interface ItemWithdrawn {
  t: 'withdrawn'
  session: string
  itemId: string
  at: number
}

/**
 * A room stood in on the map.
 *
 * Ungraded today, and deliberately shaped so it need not be redesigned if that
 * changes. It is an event in the same append-only log as everything else, so
 * "which rooms has this student explored" is a question about history rather
 * than a counter somebody can set, and an evidence PDF covering map progress
 * would read it exactly the way the module PDF reads answers.
 *
 * Every derivation above ignores it, because each one identifies its events
 * positively rather than by exclusion. That is the property that lets the log
 * grow new event kinds without a migration, and it is worth preserving: a
 * derivation written as "anything that is not an opened event" would have
 * quietly counted these as answers.
 */
export interface RoomVisited {
  t: 'visited'
  room: string
  at: number
}

/** One answered item. Append-only: entries are never edited or removed. */
export interface LogEntry {
  t?: 'answer'

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

export type Event = SessionOpened | ItemWithdrawn | RoomVisited | LogEntry

const isOpened = (e: Event): e is SessionOpened => (e as SessionOpened).t === 'opened'
const isWithdrawn = (e: Event): e is ItemWithdrawn => (e as ItemWithdrawn).t === 'withdrawn'
const isVisit = (e: Event): e is RoomVisited => (e as RoomVisited).t === 'visited'
const isAnswer = (e: Event): e is LogEntry =>
  (e as LogEntry).itemId !== undefined && !isOpened(e) && !isWithdrawn(e) && !isVisit(e)

export interface SessionSummary {
  session: string
  lecture: string
  opened: SessionOpened
  entries: LogEntry[]
  /** Planned items with neither an answer nor a withdrawal. */
  remaining: PlannedItem[]
  startedAt: number
  finishedAt: number
  activeMs: number
  firstTry: number
  /** True once every item in the PLAN is settled. */
  complete: boolean
}

/**
 * Group the log into sittings, and decide which are complete.
 *
 * NOTE THE SIGNATURE. There is no content parameter, and there must never be
 * one again. Completeness is a question about the plan recorded when the
 * sitting opened, so this function is deliberately unable to see the bank at
 * all. Making the bad call unrepresentable is cheaper than remembering not to
 * make it, which is why `game/tests/persistence.ts` asserts the arity.
 */
export function sessionsOf(log: readonly Event[]): SessionSummary[] {
  const opened = new Map<string, SessionOpened>()
  const answers = new Map<string, LogEntry[]>()
  const withdrawn = new Map<string, Set<string>>()

  for (const e of log) {
    if (isOpened(e)) {
      // First writer wins: a duplicate open must not replace a plan a student
      // has already answered against.
      if (!opened.has(e.session)) opened.set(e.session, e)
    } else if (isWithdrawn(e)) {
      const set = withdrawn.get(e.session) ?? new Set<string>()
      set.add(e.itemId)
      withdrawn.set(e.session, set)
    } else if (isAnswer(e)) {
      const list = answers.get(e.session)
      if (list) list.push(e)
      else answers.set(e.session, [e])
    }
  }

  const out: SessionSummary[] = []
  for (const [session, open] of opened) {
    const entries = (answers.get(session) ?? []).sort((a, b) => a.at - b.at)
    const settled = new Set(entries.map((e) => e.itemId))
    for (const id of withdrawn.get(session) ?? []) settled.add(id)
    const remaining = open.plan.filter((p) => !settled.has(p.id))
    out.push({
      session,
      lecture: open.lecture,
      opened: open,
      entries,
      remaining,
      startedAt: entries.length
        ? Math.min(open.at, ...entries.map((e) => e.at - e.totalMs))
        : open.at,
      finishedAt: entries.length ? Math.max(...entries.map((e) => e.at)) : open.at,
      activeMs: entries.reduce((n, e) => n + e.totalMs, 0),
      firstTry: entries.filter((e) => e.firstOk).length,
      // A plan can be satisfied entirely by withdrawals if the bank is gutted
      // between two visits. That is a satisfied plan but it is not a completed
      // module, and crediting it would make deleting items a way to earn the
      // tick. At least one item has to have actually been answered.
      complete: open.plan.length > 0 && remaining.length === 0 && entries.length > 0,
    })
  }
  return out.sort((a, b) => a.finishedAt - b.finishedAt)
}

/**
 * Where to resume: the first planned item that is not settled.
 *
 * By id, not by count. `entries.length` was wrong twice over: a re-logged item
 * skipped a question, and growing the pool displaced one so a mid-session
 * student resumed into a different list and produced a sitting spanning two
 * derivations, which the verifier then flags against honest work.
 */
export function resumeAt(s: SessionSummary): number {
  const settled = new Set(s.entries.map((e) => e.itemId))
  const i = s.opened.plan.findIndex((p) => !settled.has(p.id))
  return i < 0 ? s.opened.plan.length : i
}

/** Completed sittings for one lecture, oldest first. */
export function completedFor(
  log: readonly Event[],
  lecture: string,
): SessionSummary[] {
  return sessionsOf(log).filter((s) => s.lecture === lecture && s.complete)
}

/**
 * Which attempt a sitting started *now* would be. 1-based.
 *
 * Counts completed sittings only, so abandoning a module halfway does not burn
 * an attempt and push a student onto questions they have not earned their way
 * to. Someone who opens L9, answers two items and walks away resumes the same
 * sitting when they come back, because `openSessionFor` hands them the
 * unfinished one and this is never consulted.
 *
 * Call it once, when the sitting opens, and store the answer. Reading it later
 * gives a different number.
 */
export function nextAttemptFor(log: readonly Event[], lecture: string): number {
  return completedFor(log, lecture).length + 1
}

/**
 * The attempt a sitting was opened under.
 *
 * Defaulted rather than required at the read site because a save exported
 * before attempts existed has no such field, and the honest reading of a log
 * that never recorded one is that it was a first run.
 */
export function attemptOf(s: SessionSummary): number {
  return s.opened.attempt ?? 1
}

/** Deducted per wrong answer. One knob, so the rule can be restated in a line. */
export const WRONG_PENALTY = 0.25

/**
 * How well one item was answered. Each item is worth a point, and each wrong
 * answer costs a quarter of it.
 *
 *   right first time      1
 *   one wrong first       0.75
 *   two wrong             0.5
 *   three wrong           0.25
 *   revealed              0
 *
 * This replaced `1 / tries`, and the reason to write the arithmetic down is that
 * the replacement is *softer*, which is not what anyone expects a change made to
 * discourage guessing to be. Every graded item here has four options and is
 * retry-until-right, so a student who knows nothing has the answer in a uniform
 * position and averages 1.5 wrong attempts: 0.625 under this rule, against
 * 0.521 under `1 / tries`. The teeth in this design are the attempt window and
 * the fresh questions on a retake, not the size of this deduction.
 *
 * Revealing scores zero whatever was clicked afterwards: the escape hatch exists
 * so a stuck student can finish, and finishing is still what earns the credit,
 * but it is not knowing. It is the one path to a genuine zero, which is why the
 * floor below is not reachable by answering badly.
 */
export function scoreFromTries(tries: number, revealed: boolean): number {
  if (revealed) return 0
  return Math.max(0, 1 - WRONG_PENALTY * Math.max(0, tries - 1))
}

export function itemScore(entry: LogEntry): number {
  return scoreFromTries(entry.tries, entry.revealed)
}

/**
 * The score as integer thousandths, which is what the payload carries.
 *
 * The evidence payload holds no floats anywhere, deliberately: they are the
 * classic cross-language serialization mismatch and the verifier has to agree
 * with this file exactly. Every value this rule produces is a multiple of
 * 0.25, so thousandths are exact and would stay exact if the penalty moved to
 * a tenth.
 */
export function earnedMilli(entries: readonly LogEntry[]): number {
  return entries
    .filter(isGradeable)
    .reduce((n, e) => n + Math.round(itemScore(e) * 1000), 0)
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
 * Deliberately not a straight percentage: on a five-item module one wrong
 * answer costs 0.05, and a student who got everything right except one they
 * needed two goes at should not drop two levels for it.
 *
 * These thresholds were set against `1 / tries` and still sit sensibly under
 * the quarter-point rule: a clean run is level 5, one wrong answer holds level
 * 5, two drops to 4, and the 0.625 a pure guesser averages lands at level 2.
 * Levels are the practice display only. The participation score on the PDF is
 * `sittingScore` unrounded, and nothing here feeds it.
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
  log: readonly Event[],
  lecture: string,
): number {
  const done = completedFor(log, lecture)
  if (!done.length) return 0
  const best = Math.max(...done.map((s) => sittingScore(s.entries) ?? 0))
  return Math.min(MAX_LEVEL, 1 + LEVEL_AT.filter((t) => best >= t).length)
}

/** The best score itself, for showing a percentage next to the dots. */
export function bestScoreFor(
  log: readonly Event[],
  lecture: string,
): number | null {
  const done = completedFor(log, lecture)
  if (!done.length) return null
  return Math.max(...done.map((s) => sittingScore(s.entries) ?? 0))
}

/** The most recent completed sitting, which is what the PDF is issued from. */
export function latestCompleted(
  log: readonly Event[],
  lecture: string,
): SessionSummary | null {
  const done = completedFor(log, lecture)
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
  log: readonly Event[],
  lecture: string,
): SessionSummary | null {
  const open = sessionsOf(log)
    .filter((s) => s.lecture === lecture && !s.complete)
    .sort((a, b) => a.finishedAt - b.finishedAt)
  return open.length ? open[open.length - 1]! : null
}

/** The entries already recorded for one sitting, in the order they were answered. */
export function entriesFor(log: readonly Event[], session: string): LogEntry[] {
  return log.filter((e): e is LogEntry => isAnswer(e) && e.session === session)
    .sort((a, b) => a.at - b.at)
}

/** Total answered items, for the HUD. */
export function answeredCount(log: readonly Event[]): number {
  return log.filter(isAnswer).length
}

/** First-try accuracy across the whole log, for the dashboard. */
export function accuracy(log: readonly Event[]): number {
  const answers = log.filter(isAnswer)
  if (!answers.length) return 0
  return answers.filter((e) => e.firstOk).length / answers.length
}

/** Rooms this student has stood in, which is what draws the map. */
export function visitedRooms(log: readonly Event[]): Set<string> {
  return new Set(log.filter(isVisit).map((e) => e.room))
}

/** When each room was first entered, for ordering a "where you have been" list. */
export function firstVisits(log: readonly Event[]): Map<string, number> {
  const out = new Map<string, number>()
  for (const e of log) {
    if (isVisit(e) && !out.has(e.room)) out.set(e.room, e.at)
  }
  return out
}
