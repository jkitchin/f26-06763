// Tests for the scoring rule, run with `npm test`.
//
// The rule decides who goes on the wall in front of a room, so it is worth more
// than a reading of the code. Everything here drives the REAL handler out of
// worker.js rather than a copy of it: the module is read, its `import` of
// vote.html is stripped (node cannot import HTML), and the rest is evaluated as
// written. A test against a reimplementation would agree with itself forever.
//
// The fake DB answers the three queries `/leaderboard` issues, matched by a
// substring of each, and is deliberately dumb: it does the WHERE clauses in JS
// so that a query rewritten to filter differently shows up here as a failure.

import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const src = (await readFile(new URL('../worker.js', import.meta.url), 'utf8'))
  .replace(/^import VOTE_PAGE.*$/m, 'const VOTE_PAGE = ""')
const mod = await import('data:text/javascript;base64,' + Buffer.from(src).toString('base64'))
const worker = mod.default

/* ---- a fake D1 --------------------------------------------------------- */

function makeDB({ votes = [], marks = [], voters = [] } = {}) {
  const rows = votes.map((v, i) => ({ rowid: i + 1, ...v }))
  return {
    prepare(sql) {
      const q = { sql, args: [] }
      q.bind = (...a) => {
        q.args = a
        return q
      }
      q.all = async () => ({ results: run(sql, q.args) })
      q.first = async () => run(sql, q.args)[0] ?? null
      q.run = async () => ({ success: true })
      return q
    },
  }

  function run(sql, args) {
    if (sql.includes('FROM window')) {
      const [from, to] = args
      return marks
        .filter((m) => m.from_ts >= from && m.from_ts <= to && m.answer != null)
        .sort((a, b) => a.from_ts - b.from_ts)
    }
    // `FROM voter` has to be tested before `FROM vote`, because the second is a
    // substring of the first and the votes branch would swallow it.
    if (sql.includes('FROM voter')) {
      if (args.length) return voters.filter((v) => v.name.toLowerCase() === args[0])
      return voters
    }
    if (sql.includes('FROM vote')) {
      const [lo, hi] = args
      return rows
        .filter((r) => r.ts >= lo && r.ts <= hi && r.device != null)
        .sort((a, b) => a.ts - b.ts)
    }
    throw new Error('unexpected query: ' + sql)
  }
}

const T0 = 1_800_000_000_000

async function board(fixture, top = 50) {
  const url = `https://x/leaderboard?from=${T0 - 1000}&to=${T0 + 3_600_000}&top=${top}`
  const res = await worker.fetch(new Request(url), { DB: makeDB(fixture) })
  assert.equal(res.status, 200)
  return res.json()
}

// One 45-second question opening at T0 + `at`, answer `answer`.
const q = (tag, at, answer, round = 1) => ({
  tag,
  from_ts: T0 + at,
  to_ts: T0 + at + 45_000,
  round,
  answer,
})

// A vote `after` ms into the window that opened at T0 + `at`.
const v = (device, at, after, opt) => ({ device, ts: T0 + at + after, opt })

const named = (...names) => names.map((n) => ({ device: 'dev-' + n, name: n }))

/* ---- the rules --------------------------------------------------------- */

test('ranks by correct answers first, and time only breaks ties', async () => {
  const d = await board({
    marks: [q('q1', 0, 'A'), q('q2', 60_000, 'B')],
    votes: [
      // slow but right twice
      v('dev-tortoise', 0, 40_000, 'A'),
      v('dev-tortoise', 60_000, 40_000, 'B'),
      // instant, but right only once
      v('dev-hare', 0, 500, 'A'),
      v('dev-hare', 60_000, 500, 'C'),
    ],
    voters: named('tortoise', 'hare'),
  })

  assert.deepEqual(
    d.standings.map((s) => [s.name, s.correct]),
    [
      ['tortoise', 2],
      ['hare', 1],
    ],
    'two right beats one right no matter how fast the one was',
  )
  assert.equal(d.questions, 2)
  assert.equal(d.players, 2)
})

test('a tie on correct answers goes to the faster total', async () => {
  const d = await board({
    marks: [q('q1', 0, 'A')],
    votes: [v('dev-quick', 0, 2_000, 'A'), v('dev-slow', 0, 30_000, 'A')],
    voters: named('quick', 'slow'),
  })
  assert.deepEqual(d.standings.map((s) => s.name), ['quick', 'slow'])
  assert.equal(d.standings[0].seconds, 2)
  assert.equal(d.standings[1].seconds, 30)
})

test('a wrong answer costs the point but adds no time', async () => {
  // The whole reason for summing time over correct answers only: `bold` and
  // `cautious` did identically well on what they got right, and `bold` also
  // attempted a question they missed. That must not push them down the board.
  const d = await board({
    marks: [q('q1', 0, 'A'), q('q2', 60_000, 'B')],
    votes: [
      v('dev-bold', 0, 5_000, 'A'),
      v('dev-bold', 60_000, 30_000, 'D'), // attempted, wrong
      v('dev-cautious', 0, 5_000, 'A'),
      // cautious sat q2 out entirely
    ],
    voters: named('bold', 'cautious'),
  })

  const bold = d.standings.find((s) => s.name === 'bold')
  const cautious = d.standings.find((s) => s.name === 'cautious')
  assert.equal(bold.ms, cautious.ms, 'the wrong answer contributed no time')
  assert.equal(bold.correct, cautious.correct)
  assert.equal(bold.answered, 2)
  assert.equal(cautious.answered, 1)
})

test('re-voting inside one window replaces rather than adds', async () => {
  const d = await board({
    marks: [q('q1', 0, 'C')],
    votes: [
      v('dev-changer', 0, 3_000, 'A'), // first thought, wrong
      v('dev-changer', 0, 9_000, 'C'), // changed their mind, right
    ],
    voters: named('changer'),
  })
  assert.equal(d.standings[0].correct, 1)
  assert.equal(d.standings[0].answered, 1, 'one question, not two')
  assert.equal(d.standings[0].seconds, 9, 'the counted vote is the one timed')
})

test('round two overwrites round one on the same question', async () => {
  const d = await board({
    marks: [q('q1', 0, 'B', 1), q('q1', 120_000, 'B', 2)],
    votes: [
      v('dev-persuaded', 0, 10_000, 'D'), // wrong first time
      v('dev-persuaded', 120_000, 8_000, 'B'), // right after discussion
    ],
    voters: named('persuaded'),
  })
  assert.equal(d.standings[0].correct, 1)
  assert.equal(d.standings[0].answered, 1, 'two rounds are still one question')
  assert.equal(d.standings[0].seconds, 8)
})

test('a round-one win survives sitting out round two', async () => {
  // The failure this guards against: scoring only the final round would take
  // back a point somebody had already earned, purely for staying quiet during
  // the argument.
  const d = await board({
    marks: [q('q1', 0, 'B', 1), q('q1', 120_000, 'B', 2)],
    votes: [v('dev-sure', 0, 4_000, 'B')],
    voters: named('sure'),
  })
  assert.equal(d.standings[0].correct, 1)
  assert.equal(d.standings[0].seconds, 4)
})

test('a phone with no nickname votes but never appears', async () => {
  const d = await board({
    marks: [q('q1', 0, 'A')],
    votes: [v('dev-shy', 0, 1_000, 'A'), v('dev-named', 0, 9_000, 'A')],
    voters: named('named'),
  })
  assert.deepEqual(d.standings.map((s) => s.name), ['named'])
  assert.equal(d.players, 1, 'the anonymous voter is absent from the count too')
})

test('an opinion poll scores nothing', async () => {
  const d = await board({
    marks: [{ tag: 'poll', from_ts: T0, to_ts: T0 + 45_000, round: 1, answer: null }],
    votes: [v('dev-someone', 0, 1_000, 'A')],
    voters: named('someone'),
  })
  assert.deepEqual(d.standings, [])
  assert.equal(d.questions, 0)
})

test('votes outside every window are not scored', async () => {
  const d = await board({
    marks: [q('q1', 0, 'A')],
    votes: [
      v('dev-late', 0, 60_000, 'A'), // 15s after the window shut
      v('dev-ontime', 0, 44_000, 'A'),
    ],
    voters: named('late', 'ontime'),
  })
  assert.deepEqual(d.standings.map((s) => s.name), ['ontime'])
})

test('identical scores keep a stable order', async () => {
  // Two reads of the same data must not swap two people in front of a room.
  const fixture = {
    marks: [q('q1', 0, 'A')],
    votes: [v('dev-zeta', 0, 5_000, 'A'), v('dev-alpha', 0, 5_000, 'A')],
    voters: named('zeta', 'alpha'),
  }
  const a = await board(fixture)
  const b = await board(fixture)
  assert.deepEqual(a.standings.map((s) => s.name), b.standings.map((s) => s.name))
  assert.deepEqual(a.standings.map((s) => s.rank), [1, 2])
})

test('top= truncates the board but not the player count', async () => {
  const d = await board(
    {
      marks: [q('q1', 0, 'A')],
      votes: ['a', 'b', 'c'].map((n, i) => v('dev-' + n, 0, 1_000 * (i + 1), 'A')),
      voters: named('a', 'b', 'c'),
    },
    2,
  )
  assert.equal(d.standings.length, 2)
  assert.equal(d.players, 3)
})

/* ---- nicknames --------------------------------------------------------- */

async function claim(name, device = 'dev-abcdefgh', voters = []) {
  const url = `https://x/name?d=${device}&n=${encodeURIComponent(name)}`
  const res = await worker.fetch(new Request(url), { DB: makeDB({ voters }) })
  return { status: res.status, body: await res.json() }
}

test('a nickname is trimmed and collapsed, never silently mangled', async () => {
  assert.equal((await claim('  quick   silver  ')).body.name, 'quick silver')
  assert.equal((await claim('null_pointer')).body.name, 'null_pointer')
})

test('a nickname that cannot be a name is rejected', async () => {
  for (const bad of ['', 'x', '...', 'naïve', '‮evil', 'has<script>']) {
    const r = await claim(bad)
    assert.equal(r.status, 400, `expected ${JSON.stringify(bad)} to be rejected`)
  }
})

test('a nickname held by another device is taken', async () => {
  const r = await claim('taken_one', 'dev-newphone', [
    { device: 'dev-oldphone', name: 'taken_one' },
  ])
  assert.equal(r.status, 409)
  assert.equal(r.body.error, 'taken')
})

test('re-asserting your own nickname is free', async () => {
  const r = await claim('mine_already', 'dev-samephone', [
    { device: 'dev-samephone', name: 'mine_already' },
  ])
  assert.equal(r.status, 200)
  assert.equal(r.body.ok, true)
})
