// Tests for the Boss Rush placing rule, run with `node --test arcade/test/*.test.mjs`.
//
// Same approach as clicker/test/leaderboard.test.mjs and for the same reason:
// this rule decides what goes on a wall in front of a room, and the REAL file
// is driven here rather than a copy of its rules. bossrush.js is a plain
// browser script, so it is read, evaluated with a stub `Arcade` global, and the
// pure function it hangs there is the thing under test. A test against a
// reimplementation would agree with itself forever.

import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const src = await readFile(new URL('../games/bossrush.js', import.meta.url), 'utf8')
const Arcade = { myName: () => '' }
// The file only touches `document` inside setup(), which nothing here calls.
new Function('Arcade', 'window', 'document', src)(Arcade, {}, undefined)
const rank = Arcade.rushStandings

const board = (...names) => ({
  standings: names.map((name, i) => ({ name, rank: i + 1, score: 100 - i, ms: 1000 })),
})

test('points come from placing, so one big-scoring game cannot decide the board', () => {
  // ada wins a game that pays 200 a run; grace wins two that pay 30. Ranked on
  // raw score ada would be untouchable; ranked on placing grace is ahead.
  const rows = rank([
    { standings: [{ name: 'ada', rank: 1, score: 2000 }, { name: 'grace', rank: 2, score: 1500 }] },
    { standings: [{ name: 'grace', rank: 1, score: 30 }] },
    { standings: [{ name: 'grace', rank: 1, score: 28 }] },
  ])
  assert.deepEqual(rows.map((r) => [r.name, r.points]), [['grace', 28], ['ada', 10]])
})

test('the placing table is 10/8/6/5/4/3/2/1', () => {
  const rows = rank([board('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h')])
  assert.deepEqual(rows.map((r) => r.points), [10, 8, 6, 5, 4, 3, 2, 1])
})

test('finishing outside the top eight still beats not playing', () => {
  const names = Array.from({ length: 12 }, (_, i) => 'p' + String(i + 1).padStart(2, '0'))
  const rows = rank([board(...names)])
  assert.equal(rows[8].points, 1, 'ninth scores one')
  assert.equal(rows[11].points, 1, 'twelfth scores one')
  // Somebody who never appeared on any board is simply absent.
  assert.equal(rows.find((r) => r.name === 'nobody'), undefined)
})

test('a player who skipped a game is not credited for it', () => {
  const rows = rank([board('ada', 'grace'), board('ada')])
  const ada = rows.find((r) => r.name === 'ada')
  const grace = rows.find((r) => r.name === 'grace')
  assert.deepEqual([ada.points, ada.games], [20, 2])
  assert.deepEqual([grace.points, grace.games], [8, 1])
})

test('a tie on points breaks on games played, then on name', () => {
  // Both reach 10: ada by winning once, grace by two second places (8) and a
  // last place (1) plus one more (1). Breadth wins the tie.
  const rows = rank([
    { standings: [{ name: 'ada', rank: 1 }, { name: 'grace', rank: 2 }] },
    { standings: [{ name: 'grace', rank: 8 }] },
    { standings: [{ name: 'grace', rank: 8 }] },
  ])
  assert.deepEqual(rows.map((r) => [r.name, r.points, r.games]), [['grace', 10, 3], ['ada', 10, 1]])

  const tied = rank([{ standings: [{ name: 'zoe', rank: 1 }] }, { standings: [{ name: 'abe', rank: 1 }] }])
  assert.deepEqual(tied.map((r) => r.name), ['abe', 'zoe'], 'name is the final tiebreak')
})

test('best placing is tracked across games', () => {
  const rows = rank([board('x', 'ada'), board('ada')])
  assert.equal(rows.find((r) => r.name === 'ada').best, 1)
})

test('an unreachable game contributes nothing rather than blanking the board', () => {
  // draw() turns a failed fetch into { standings: [] }; that must be harmless.
  const rows = rank([board('ada'), { standings: [] }, {}, null])
  assert.deepEqual(rows.map((r) => [r.name, r.points, r.games]), [['ada', 10, 1]])
})

test('an anonymous run cannot reach the board', () => {
  // /board already omits nameless players, but a row with no name must not
  // become a player called "undefined" if that ever changes.
  const rows = rank([{ standings: [{ rank: 1 }, { name: '', rank: 2 }, { name: 'ada', rank: 3 }] }])
  assert.deepEqual(rows.map((r) => r.name), ['ada'])
})

test('top caps the board without renumbering anybody', () => {
  const rows = rank([board('a', 'b', 'c')], 2)
  assert.deepEqual(rows.map((r) => [r.name, r.rank]), [['a', 1], ['b', 2]])
})
