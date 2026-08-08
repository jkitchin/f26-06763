/**
 * Does a save survive the course changing underneath it? Run with `npm run persistence`.
 *
 * The instructor's requirement for this game was that a student can stop and
 * come back later "even if we update the game with new resources". That is not
 * a nice-to-have: material is written during the semester, `game/content/l15.yml`
 * already carries a note planning to raise `serve` from 8 to 12, and a student's
 * log may be the only record that they did the work.
 *
 * Three separate mechanisms used to break it, and none of them errored.
 *
 *   1. COMPLETENESS WAS JUDGED AGAINST TODAY'S BANK. `sessionsOf` compared the
 *      number of items answered against `banks[lecture].serve` read at render
 *      time. Raising serve un-completed every finished sitting: level to zero,
 *      tick gone, and the button that re-downloads the evidence PDF gone with
 *      it. The first section below is that exact scenario.
 *
 *   2. A VERSION BUMP DISCARDED THE LOG. `persist` was configured with a
 *      `version` and no `migrate`, and zustand's documented behaviour in that
 *      case is to throw the persisted state away.
 *
 *   3. RESUME WAS POSITIONAL. `cursor = entries.length` indexed a freshly
 *      derived list, so growing a pool displaced an item and a returning
 *      student answered a different question than the one they were credited
 *      for, producing a sitting spanning two derivations that the verifier then
 *      flags as tampered against honest work.
 */

import assert from 'node:assert/strict'
import {
  completedFor, levelFor, openSessionFor, resumeAt, sessionsOf,
  type Event, type LogEntry, type PlannedItem, type SessionOpened,
} from '../src/store/log.ts'
import { derive, type PoolItem } from '../src/seed.ts'
// From migrate.ts, not the store: importing the store boots IndexedDB.
import { migrate, readSave, SAVE_VERSION } from '../src/store/migrate.ts'

let fails = 0
const check = (ok: boolean, label: string, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? `  ${detail}` : ''}`)
  if (!ok) fails++
}

console.log('persistence:')

// --- a bank that grows ----------------------------------------------------

const ID = 'jkitchin'
const LECTURE = 'l15'

/** A synthetic pool of n four-option items, ids stable as n grows. */
const pool = (n: number): Record<string, PoolItem> =>
  Object.fromEntries(
    Array.from({ length: n }, (_, i) => [
      `${LECTURE}-q${String(i + 1).padStart(2, '0')}`,
      { options: ['a', 'b', 'c', 'd'] } as PoolItem,
    ]),
  )

const answer = (session: string, p: PlannedItem, at: number): LogEntry => ({
  session, lecture: LECTURE, itemId: p.id, variant: p.variant, opts: p.opts,
  chosen: ['opt0'], tries: 1, firstMs: 1000, totalMs: 2000,
  firstOk: true, revealed: false, at,
})

/** Open a sitting the way SessionRoute does, and answer every planned item. */
function finishedSitting(poolSize: number, serve: number): Event[] {
  const plan: PlannedItem[] = derive(ID, LECTURE, pool(poolSize), 1, serve)
    .map((s) => ({ id: s.id, variant: s.variant, opts: s.option_order }))
  const session = `${ID}/${LECTURE}/1000`
  return [
    { t: 'opened', session, lecture: LECTURE, andrewId: ID, plan,
      content: { pool_version: 1, serve }, at: 1000 },
    ...plan.map((p, i) => answer(session, p, 1001 + i)),
  ]
}

// The scenario from game/content/l15.yml, played out. The student finished
// eight items in week 3; in week 9 the bank grew to twenty and serve went to
// twelve. Nothing about their save changed, so nothing about their credit may.
const saved = finishedSitting(12, 8)
const plannedIn = (log: Event[]) => (log[0] as SessionOpened).plan

check(levelFor(saved, LECTURE) === 5, 'a finished sitting is level 5')
check(completedFor(saved, LECTURE).length === 1, 'and counts as one completed sitting')
check(openSessionFor(saved, LECTURE) === null, 'with nothing left open')

// The bank grows. levelFor cannot see it, which is the entire fix, so the
// assertion is that the same log still reads the same way.
const grown = derive(ID, LECTURE, pool(20), 1, 12)
check(
  grown.length === 12 && grown.some((g) => !plannedIn(saved).some((p) => p.id === g.id)),
  'the grown bank really does derive a different list',
  `${grown.length} items, was 8`,
)
check(levelFor(saved, LECTURE) === 5, 'the finished sitting is STILL level 5 after the bank grows')
check(completedFor(saved, LECTURE).length === 1, 'still completed')
check(openSessionFor(saved, LECTURE) === null, 'and is not handed back as unfinished')

// --- the arity guard ------------------------------------------------------
//
// The bug was a content parameter. Making it unrepresentable is worth more than
// remembering not to pass one, so the shape of the function is the test.
check(sessionsOf.length === 1, 'sessionsOf takes the log and nothing else',
  `arity ${sessionsOf.length}`)
check(levelFor.length === 2, 'levelFor takes (log, lecture) and nothing else',
  `arity ${levelFor.length}`)
check(completedFor.length === 2, 'completedFor takes (log, lecture) and nothing else',
  `arity ${completedFor.length}`)
check(openSessionFor.length === 2, 'openSessionFor takes (log, lecture) and nothing else',
  `arity ${openSessionFor.length}`)

// --- resume is by id, not by count ----------------------------------------

const half = finishedSitting(12, 8).slice(0, 5) // opened + four answers
const open = openSessionFor(half, LECTURE)
check(open !== null && !open.complete, 'a half-finished sitting is still open')
check(open !== null && resumeAt(open) === 4, 'and resumes at the fifth planned item',
  String(open && resumeAt(open)))
check(open !== null && open.remaining.length === 4, 'with four items left')

// A duplicated answer used to push a positional cursor past a question the
// student never saw. Resuming by id is immune.
const dup = [...half, half[2]!]
const openDup = openSessionFor(dup, LECTURE)
check(openDup !== null && resumeAt(openDup) === 4,
  'a duplicated answer does not skip the next question',
  String(openDup && resumeAt(openDup)))

// --- a withdrawn item satisfies the plan ----------------------------------
//
// An item can be deleted between two sittings. Without this the student is
// stuck on a module they cannot finish, through no act of theirs.
const stuck = finishedSitting(12, 8).slice(0, 8) // opened + seven answers
const lastId = plannedIn(stuck)[7]!.id
const rescued: Event[] = [
  ...stuck,
  { t: 'withdrawn', session: `${ID}/${LECTURE}/1000`, itemId: lastId, at: 2000 },
]
check(openSessionFor(stuck, LECTURE) !== null, 'a sitting missing one item is open')
check(completedFor(rescued, LECTURE).length === 1,
  'withdrawing the missing item completes it')
check(levelFor(rescued, LECTURE) === 5,
  'and the withdrawal is not scored against the student', String(levelFor(rescued, LECTURE)))

// Answering nothing is not a way to complete a module.
const empty: Event[] = [{
  t: 'opened', session: 's', lecture: LECTURE, andrewId: ID,
  plan: [{ id: 'x', variant: '-', opts: [] }],
  content: { pool_version: 1, serve: 1 }, at: 1,
}, { t: 'withdrawn', session: 's', itemId: 'x', at: 2 }]
check(completedFor(empty, LECTURE).length === 0,
  'a sitting where every item was withdrawn is not complete')

// --- migration ------------------------------------------------------------

const v1 = {
  version: 1, andrewId: ID, displayName: 'J. Kitchin',
  settings: { hearts: true, theme: 'dark' },
  log: [answer('s', { id: 'l15-q01', variant: '-', opts: [0, 1, 2, 3] }, 5)],
}
const m1 = migrate(v1, 1)
check(m1.andrewId === ID && m1.displayName === 'J. Kitchin', 'migration keeps the identity')
check(m1.log.length === 1, 'and keeps the answers rather than discarding them')
check(m1.settings.hearts === true && m1.settings.theme === 'dark', 'and keeps the settings')
check(m1.version === SAVE_VERSION, 'and stamps the current version', String(m1.version))
check(m1.quarantine.length === 0, 'with nothing quarantined')

// A v1 log has no recorded plan, so its sittings cannot be judged at all. They
// are carried as history, not silently treated as complete.
check(completedFor(m1.log, 'l15').length === 0,
  'a v1 sitting is not resurrected as complete')

// Total for any input. zustand destructures the result inside its hydrate
// chain, so a throw here aborts hydration silently and the next write lands on
// top of an empty log.
for (const junk of [null, undefined, 42, 'nope', [], { log: 'not an array' }]) {
  const label = JSON.stringify(junk) ?? 'undefined'
  try {
    const out = migrate(junk, 1)
    check(Array.isArray(out.log), `migrate(${label}) returns a usable save`)
  } catch (err) {
    check(false, `migrate(${label}) threw`, String(err))
  }
}
check(migrate(null, 1).quarantine.length === 1, 'an unreadable save is quarantined, not dropped')
check(migrate(null, 1).quarantine[0]!.blob === 'null', 'and kept verbatim')

// A save from a future build is copied through, not downgraded. A stale cached
// tab must not eat a newer tab's work.
const future = migrate({ version: 99, andrewId: ID, displayName: '', log: saved, settings: {} }, 99)
check(future.log.length === saved.length, 'a newer save is carried through intact',
  `${future.log.length} of ${saved.length}`)
check(completedFor(future.log, LECTURE).length === 1, 'and is still readable as complete')

// readSave is the door every hydration goes through, including the ones zustand
// skips `migrate` for because the blob carries no version field.
check(readSave({ andrewId: ID, log: saved }).log.length === saved.length,
  'a versionless save is read rather than discarded')
check(readSave('garbage').quarantine.length === 1, 'and a garbage one is quarantined')
check(readSave({ version: SAVE_VERSION, andrewId: ID, displayName: '', log: saved,
                 settings: { hearts: false, theme: 'system' } }).log.length === saved.length,
  'a current save passes through readSave untouched')

assert.equal(fails, 0, `${fails} failed`)
console.log('\nall checks passed')
