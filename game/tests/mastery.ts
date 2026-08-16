/** Mastery scoring: run with `npm run mastery`. */
import {
  WRONG_PENALTY, attemptOf, bestScoreFor, completedFor, earnedMilli, entriesFor,
  isGradeable, itemScore, levelFor, nextAttemptFor, sittingScore,
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
    t: 'opened', session: id, lecture: 'l09', andrewId: 'test', plan, attempt: 1,
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

/** The answers out of a sitting. Scoring grades answers, not events. */
const answersOf = (log: Event[]) => entriesFor(log, 's')

console.log('mastery:')

// --- per item -------------------------------------------------------------
// One point a question, less WRONG_PENALTY for each wrong answer. Every graded
// item in the course has four options, so three wrong answers is the worst a
// student can do without revealing, and 0.25 is the floor rather than zero.
check(itemScore(entry({ itemId: 'a', tries: 1 })) === 1, 'right first time scores 1')
check(itemScore(entry({ itemId: 'a', tries: 2 })) === 0.75, 'one wrong answer costs a quarter')
check(Math.abs(itemScore(entry({ itemId: 'a', tries: 4 })) - 0.25) < 1e-9,
  'three wrong answers leave a quarter point')
check(itemScore(entry({ itemId: 'a', tries: 1, revealed: true })) === 0,
  'a revealed answer scores nothing however many tries')
check(itemScore(entry({ itemId: 'a', tries: 9 })) === 0,
  'the score floors at zero rather than going negative')
check(WRONG_PENALTY === 0.25, 'the penalty is a quarter point', String(WRONG_PENALTY))

// The payload carries integer thousandths, never a float. Both halves of the
// evidence chain read this, so a rounding difference here is a verification
// failure for an honest student.
check(earnedMilli(answersOf(sitting('s', [1, 2, 3]))) === 1000 + 750 + 500,
  'earnedMilli sums integer thousandths',
  String(earnedMilli(answersOf(sitting('s', [1, 2, 3])))))

// --- free response --------------------------------------------------------
check(!isGradeable(entry({ itemId: 'a', chosen: [] })),
  'a free-response item does not count toward mastery')
const answers = answersOf

const mixed = [...sitting('s', [1, 1]), entry({ itemId: 'free', chosen: [], session: 's', at: 9 })]
check(sittingScore(answers(mixed)) === 1, 'free-response items do not inflate the score')

// --- whole sitting --------------------------------------------------------
check(sittingScore(answers(sitting('s', [1, 1, 1, 1]))) === 1, 'all first time is 100%')
check(sittingScore(answers(sitting('s', [2, 2, 2, 2]))) === 0.75, 'all with one wrong is 75%')
check(sittingScore([]) === null, 'a sitting that graded nothing has no score')

// --- levels ---------------------------------------------------------------
const lvl = (tries: number[], rev: boolean[] = []) =>
  levelFor(sitting('s1', tries, rev), 'l09')
check(lvl([1, 1, 1, 1]) === 5, 'everything first time is level 5', String(lvl([1, 1, 1, 1])))
check(lvl([1, 1, 1, 2]) === 4, 'one second attempt costs a level', String(lvl([1, 1, 1, 2])))
check(lvl([2, 2, 2, 2]) === 3, 'everything on the second go is level 3', String(lvl([2, 2, 2, 2])))
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

// --- attempts -------------------------------------------------------------
// The retake defence. `nextAttemptFor` decides which questions a student is
// about to see, so an off-by-one here hands somebody attempt 1's items on their
// second run, which is the whole thing this was built to stop.
check(nextAttemptFor([], 'l09') === 1, 'a first run is attempt 1')
check(nextAttemptFor(good, 'l09') === 2, 'after one completed sitting the next is attempt 2',
  String(nextAttemptFor(good, 'l09')))
check(nextAttemptFor([...good, ...sloppy], 'l09') === 3, 'and two completed makes it 3')
check(nextAttemptFor(good, 'l11') === 1, 'attempts are counted per lecture, not globally')

// An abandoned sitting must not burn an attempt. A student who opens a module,
// answers two of five and closes the tab resumes that same sitting; if this
// counted them they would come back to a different set of questions and their
// two recorded answers would be orphaned.
check(nextAttemptFor(sitting('s1', [1, 1], [], SERVE), 'l09') === 1,
  'an unfinished sitting does not burn an attempt',
  String(nextAttemptFor(sitting('s1', [1, 1], [], SERVE), 'l09')))

// The PDF reads the attempt off the sitting, never off today's log.
const s1 = completedFor(good, 'l09')[0]!
check(attemptOf(s1) === 1, 'a sitting reports the attempt it was opened under')

console.log(fails ? `\n${fails} failed` : '\nall checks passed')
process.exit(fails ? 1 : 0)
