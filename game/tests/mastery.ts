/** Mastery scoring: run with `npm run mastery`. */
import {
  bestScoreFor, entriesFor, isGradeable, itemScore, levelFor, sittingScore,
  type Event, type LogEntry,
} from '../src/store/log.ts'

let fails = 0
const check = (ok: boolean, label: string, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? `  ${detail}` : ''}`)
  if (!ok) fails++
}

const SERVE = 4

function entry(o: Partial<LogEntry> & { itemId: string }): LogEntry {
  return {
    session: 's1', lecture: 'l09', variant: '-', opts: [0, 1, 2, 3],
    chosen: ['opt0'], tries: 1, firstMs: 1000, totalMs: 2000,
    firstOk: true, revealed: false, at: 1, ...o,
  }
}

/**
 * A sitting: the opened event that records the plan, then the answers.
 *
 * The opened event is not scaffolding. A sitting with no recorded plan is not a
 * sitting any more, which is the point of the change these tests came with, so
 * building one by hand is now the only way to build one at all.
 */
function sitting(
  id: string, tries: number[], revealed: boolean[] = [], planSize = tries.length,
): Event[] {
  const plan = Array.from({ length: planSize }, (_, i) =>
    ({ id: `l09-q0${i}`, variant: '-', opts: [0, 1, 2, 3] }))
  const opened: Event = {
    t: 'opened', session: id, lecture: 'l09', andrewId: 'test', plan,
    content: { pool_version: 1, serve: SERVE }, at: 0,
  }
  return [
    opened,
    ...tries.map((t, i) =>
      entry({
        itemId: `l09-q0${i}`, session: id, tries: t,
        firstOk: t === 1 && !revealed[i], revealed: !!revealed[i], at: i + 1,
      }),
    ),
  ]
}

console.log('mastery:')

// --- per item -------------------------------------------------------------
check(itemScore(entry({ itemId: 'a', tries: 1 })) === 1, 'right first time scores 1')
check(itemScore(entry({ itemId: 'a', tries: 2 })) === 0.5, 'second attempt scores a half')
check(Math.abs(itemScore(entry({ itemId: 'a', tries: 4 })) - 0.25) < 1e-9,
  'fourth attempt scores a quarter')
check(itemScore(entry({ itemId: 'a', tries: 1, revealed: true })) === 0,
  'a revealed answer scores nothing however many tries')

// --- free response --------------------------------------------------------
check(!isGradeable(entry({ itemId: 'a', chosen: [] })),
  'a free-response item does not count toward mastery')
/** The answers out of a sitting. sittingScore grades answers, not events. */
const answers = (log: Event[]) => entriesFor(log, 's')

const mixed = [...sitting('s', [1, 1]), entry({ itemId: 'free', chosen: [], session: 's', at: 9 })]
check(sittingScore(answers(mixed)) === 1, 'free-response items do not inflate the score')

// --- whole sitting --------------------------------------------------------
check(sittingScore(answers(sitting('s', [1, 1, 1, 1]))) === 1, 'all first time is 100%')
check(sittingScore(answers(sitting('s', [2, 2, 2, 2]))) === 0.5, 'all second time is 50%')
check(sittingScore([]) === null, 'a sitting that graded nothing has no score')

// --- levels ---------------------------------------------------------------
const lvl = (tries: number[], rev: boolean[] = []) =>
  levelFor(sitting('s1', tries, rev), 'l09')
check(lvl([1, 1, 1, 1]) === 5, 'everything first time is level 5', String(lvl([1, 1, 1, 1])))
check(lvl([1, 1, 1, 2]) === 4, 'one second attempt costs a level', String(lvl([1, 1, 1, 2])))
check(lvl([2, 2, 2, 2]) === 2, 'everything on the second go is level 2', String(lvl([2, 2, 2, 2])))
check(lvl([1, 1, 1, 1], [true, true, true, true]) === 1,
  'revealing everything still completes the module', String(lvl([1, 1, 1, 1], [true, true, true, true])))
check(levelFor([], 'l09') === 0, 'never attempted is level 0')

// --- an incomplete sitting earns nothing ----------------------------------
// Short of ITS OWN plan, which is the only definition of short there is now.
// This used to compare against the bank's current `serve`, so raising serve
// from 8 to 12 retroactively un-completed every finished sitting.
check(levelFor(sitting('s1', [1, 1], [], SERVE), 'l09') === 0,
  'a sitting short of its own plan does not count as complete')

// --- the load-bearing property --------------------------------------------
const good = sitting('s1', [1, 1, 1, 1])
const sloppy = sitting('s2', [3, 3, 3, 3])
const before = levelFor(good, 'l09')
const after = levelFor([...good, ...sloppy], 'l09')
check(after === before,
  'practising again can never lower the level', `${before} -> ${after}`)
check(
  (bestScoreFor([...sloppy, ...good], 'l09') ?? 0) === 1,
  'the best run is the one that counts, whichever order they happened in',
)

console.log(fails ? `\n${fails} failed` : '\nall checks passed')
process.exit(fails ? 1 : 0)
