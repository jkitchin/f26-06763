// Tests for the arcade's run protocol and boards, run with `npm test`.
//
// Same approach as leaderboard.test.mjs, and for the same reason: the REAL
// handlers out of worker.js are driven here, with the `import` of vote.html
// stripped because node cannot import HTML. A test against a reimplementation
// would agree with itself forever.
//
// Two of these matter more than the rest. `ms` must come off the server's clock
// even when the browser insists otherwise, and a run must be submittable
// exactly once -- those are the only two properties an arcade score has that a
// student cannot simply type. Everything else here is a board that must not
// reward grinding.

import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const src = (await readFile(new URL('../worker.js', import.meta.url), 'utf8'))
  .replace(/^import VOTE_PAGE.*$/m, 'const VOTE_PAGE = ""')
const mod = await import('data:text/javascript;base64,' + Buffer.from(src).toString('base64'))
const worker = mod.default

/* ---- a fake D1 --------------------------------------------------------- */

// Mutable, because unlike the leaderboard's queries these handlers write. It
// does every WHERE and the best-per-device ranking in JS, so a query rewritten
// to filter or rank differently shows up here as a failure rather than as a
// silent agreement.
function makeDB({ plays = [], runs = [], voters = [] } = {}) {
  const db = { plays: plays.map((p) => ({ ...p })), runs: runs.map((r) => ({ ...r })), voters }

  db.prepare = (sql) => {
    const q = { sql, args: [] }
    q.bind = (...a) => {
      q.args = a
      return q
    }
    q.all = async () => ({ results: exec(sql, q.args) })
    q.first = async () => exec(sql, q.args)[0] ?? null
    q.run = async () => {
      exec(sql, q.args)
      return { success: true }
    }
    return q
  }

  function exec(sql, args) {
    if (sql.startsWith('INSERT INTO run')) {
      const [id, device, game, start_ts] = args
      db.runs.push({ id, device, game, start_ts })
      return []
    }
    if (sql.startsWith('DELETE FROM run WHERE id')) {
      db.runs = db.runs.filter((r) => r.id !== args[0])
      return []
    }
    if (sql.startsWith('DELETE FROM run')) {
      db.runs = db.runs.filter((r) => r.start_ts >= args[0])
      return []
    }
    if (sql.includes('FROM run')) {
      return db.runs.filter((r) => r.id === args[0])
    }
    if (sql.startsWith('INSERT INTO play')) {
      const [ts, game, round, device, score, ms, detail] = args
      db.plays.push({ ts, game, round, device, score, ms, detail })
      return []
    }
    if (sql.includes('FROM play')) {
      const [game, from, to] = args
      const best = new Map()
      for (const p of db.plays) {
        if (p.game !== game || p.ts < from || p.ts > to) continue
        const prev = best.get(p.device)
        // The same ordering the ROW_NUMBER() window uses: best score, then
        // fastest, then earliest.
        if (
          !prev ||
          p.score > prev.score ||
          (p.score === prev.score && p.ms < prev.ms) ||
          (p.score === prev.score && p.ms === prev.ms && p.ts < prev.ts)
        ) {
          best.set(p.device, p)
        }
      }
      return [...best.values()].map((p) => ({ device: p.device, score: p.score, ms: p.ms, ts: p.ts }))
    }
    if (sql.includes('FROM voter')) return db.voters
    throw new Error('unexpected query: ' + sql)
  }

  return db
}

const GAME = 'l03-whackabug'
const named = (...names) => names.map((n) => ({ device: 'dev-' + n, name: n }))

async function call(path, db) {
  const res = await worker.fetch(new Request('https://x' + path), { DB: db })
  return { status: res.status, body: await res.json() }
}

// A completed run: /start then /submit, with the clock held still between them
// unless `heldMs` says otherwise.
async function play(db, device, score, heldMs = 1000, extra = '') {
  const real = Date.now
  // End the run at the real now, so the row this inserts is in the past for
  // every handler that runs afterwards on the unmocked clock.
  let t = real() - heldMs
  Date.now = () => t
  try {
    const s = await call(`/start?d=${device}&g=${GAME}`, db)
    assert.equal(s.status, 200, 'start failed: ' + JSON.stringify(s.body))
    t += heldMs
    return await call(`/submit?d=${device}&g=${GAME}&run=${s.body.run}&s=${score}${extra}`, db)
  } finally {
    Date.now = real
  }
}

/* ---- the run protocol -------------------------------------------------- */

test('ms is the server subtraction, not anything the browser says', async () => {
  const db = makeDB()
  // The submit carries a flattering duration of its own. It must not survive.
  const r = await play(db, 'dev-liar', 100, 7_500, '&ms=1&seconds=0.1')
  assert.equal(r.status, 200)
  assert.equal(r.body.ms, 7_500)
  assert.equal(db.plays[0].ms, 7_500)
})

test('a run can be submitted exactly once', async () => {
  const db = makeDB()
  const real = Date.now
  let t = real()
  Date.now = () => t
  try {
    const s = await call(`/start?d=dev-alpha&g=${GAME}`, db)
    t += 1000
    const first = await call(`/submit?d=dev-alpha&g=${GAME}&run=${s.body.run}&s=50`, db)
    assert.equal(first.status, 200)
    // Replaying the identical request is the cheapest forgery there is.
    const again = await call(`/submit?d=dev-alpha&g=${GAME}&run=${s.body.run}&s=50`, db)
    assert.equal(again.status, 409)
    assert.equal(again.body.error, 'no open run')
    assert.equal(db.plays.length, 1)
  } finally {
    Date.now = real
  }
})

test('a run belonging to another device or another game is refused', async () => {
  const db = makeDB()
  const s = await call(`/start?d=dev-owner&g=${GAME}`, db)

  const stolen = await call(`/submit?d=dev-thief&g=${GAME}&run=${s.body.run}&s=999`, db)
  assert.equal(stolen.status, 409)

  const wrongGame = await call(`/submit?d=dev-owner&g=l03-pacman&run=${s.body.run}&s=999`, db)
  assert.equal(wrongGame.status, 409)

  const invented = await call(`/submit?d=dev-owner&g=${GAME}&run=not-a-real-run&s=999`, db)
  assert.equal(invented.status, 409)

  assert.equal(db.plays.length, 0)
})

test('a run abandoned for half an hour can no longer be submitted', async () => {
  const db = makeDB()
  const real = Date.now
  let t = real()
  Date.now = () => t
  try {
    const s = await call(`/start?d=dev-alpha&g=${GAME}`, db)
    t += 31 * 60 * 1000
    const late = await call(`/submit?d=dev-alpha&g=${GAME}&run=${s.body.run}&s=50`, db)
    assert.equal(late.status, 409)
  } finally {
    Date.now = real
  }
})

test('a score that is not a number is refused rather than stored as one', async () => {
  const db = makeDB()
  const s = await call(`/start?d=dev-alpha&g=${GAME}`, db)
  const bad = await call(`/submit?d=dev-alpha&g=${GAME}&run=${s.body.run}&s=NaN`, db)
  assert.equal(bad.status, 400)
  assert.equal(db.plays.length, 0)
})

test('an absurd score is clamped rather than left on top of every board forever', async () => {
  const db = makeDB()
  const r = await play(db, 'dev-cheat', Number.MAX_SAFE_INTEGER)
  assert.equal(r.body.score, 1000000)
})

test('a game key is required, and junk is not one', async () => {
  const db = makeDB()
  assert.equal((await call('/start?d=dev-valid-id', db)).status, 400)
  assert.equal((await call('/start?d=dev-valid-id&g=Not A Game', db)).status, 400)
  assert.equal((await call(`/board?hours=6`, db)).status, 400)
})

/* ---- the boards -------------------------------------------------------- */

const T0 = 1_800_000_000_000
const p = (device, score, ms, at = 0) => ({ device, score, ms, ts: T0 + at, game: GAME })

// A run already on record a minute ago, on the real clock, for the tests that
// also drive a live /start and /submit.
const recent = (device, score, ms) => ({ device, score, ms, ts: Date.now() - 60_000, game: GAME })

async function board(fixture, query = '') {
  const db = makeDB(fixture)
  const r = await call(`/board?g=${GAME}&to=${T0 + 3_600_000}&from=${T0 - 1000}${query}`, db)
  assert.equal(r.status, 200)
  return r.body
}

test('a board ranks each player by their BEST run, not their latest or their total', async () => {
  const d = await board({
    voters: named('ada', 'grace'),
    plays: [
      // ada peaks once and then plays badly a lot. Her peak is the claim.
      p('dev-ada', 300, 60_000, 0),
      p('dev-ada', 10, 60_000, 1000),
      p('dev-ada', 10, 60_000, 2000),
      p('dev-ada', 10, 60_000, 3000),
      // grace plays once, well. A board of totals would put ada above her.
      p('dev-grace', 200, 60_000, 0),
    ],
  })
  assert.deepEqual(d.standings.map((s) => [s.name, s.score]), [['ada', 300], ['grace', 200]])
})

test('time breaks a tie on score, and never outranks it', async () => {
  const d = await board({
    voters: named('quick', 'high'),
    plays: [p('dev-quick', 100, 5_000), p('dev-high', 140, 59_000)],
  })
  assert.deepEqual(d.standings.map((s) => s.name), ['high', 'quick'])

  const tied = await board({
    voters: named('slow', 'fast'),
    plays: [p('dev-slow', 100, 50_000), p('dev-fast', 100, 9_000)],
  })
  assert.deepEqual(tied.standings.map((s) => s.name), ['fast', 'slow'])
  assert.equal(tied.standings[0].seconds, 9)
})

test('a player with no nickname is off the board but still holds their place in it', async () => {
  const d = await board({
    voters: named('ada'),
    plays: [p('dev-ghost', 500, 10_000), p('dev-ada', 100, 10_000)],
  })
  // The anonymous run counted and won. Renumbering around it would tell ada she
  // came first when she came second.
  assert.deepEqual(d.standings.map((s) => [s.name, s.rank]), [['ada', 2]])
  assert.equal(d.players, 2)
  assert.equal(d.named, 1)
})

test('the live board forgets, and the semester board does not', async () => {
  const old = { device: 'dev-ada', score: 900, ms: 10_000, ts: T0 - 40 * 3_600_000, game: GAME }
  const fixture = { voters: named('ada', 'grace'), plays: [old, p('dev-grace', 100, 10_000)] }

  const live = await board(fixture)
  assert.deepEqual(live.standings.map((s) => s.name), ['grace'])
  assert.equal(live.all, false)

  const all = await board(fixture, '&all=1')
  assert.deepEqual(all.standings.map((s) => [s.name, s.score]), [['ada', 900], ['grace', 100]])
  assert.equal(all.all, true)
  assert.equal(all.from, 0)
})

test('a board never carries the device a run came from', async () => {
  const d = await board({ voters: named('ada'), plays: [p('dev-ada', 100, 10_000)] })
  assert.equal(JSON.stringify(d).includes('dev-ada'), false)
})

test('top caps the board without changing anybody rank', async () => {
  const d = await board(
    {
      voters: named('a', 'b', 'c'),
      plays: [p('dev-a', 300, 1000), p('dev-b', 200, 1000), p('dev-c', 100, 1000)],
    },
    '&top=2',
  )
  assert.deepEqual(d.standings.map((s) => [s.name, s.rank]), [['a', 1], ['b', 2]])
  assert.equal(d.named, 3)
})

/* ---- what a player is told about themselves ---------------------------- */

test('a submit reports where that run left you, counting everyone who played', async () => {
  const db = makeDB({ plays: [recent('dev-ghost', 500, 1000), recent('dev-rival', 200, 1000)] })
  const r = await play(db, 'dev-myself', 300)
  assert.equal(r.body.rank, 2)      // behind the anonymous 500, ahead of the 200
  assert.equal(r.body.players, 3)
  assert.equal(r.body.best.score, 300)
})

test('a personal best survives a worse run afterwards', async () => {
  const db = makeDB()
  await play(db, 'dev-myself', 300)
  await play(db, 'dev-myself', 20)
  const me = await call(`/me?d=dev-myself&g=${GAME}`, db)
  assert.equal(me.body.best.score, 300)
  assert.equal(me.body.rank, 1)
  assert.equal(me.body.players, 1)
})

test('a device that has never played has no best and no rank', async () => {
  const db = makeDB()
  const me = await call(`/me?d=dev-nobody&g=${GAME}`, db)
  assert.equal(me.status, 200)
  assert.equal(me.body.best, null)
  assert.equal(me.body.rank, null)
})

/* ---- the shape of the surface ------------------------------------------ */

test('the arcade routes are GET-only and are listed on a 404', async () => {
  const db = makeDB()
  const post = await worker.fetch(new Request('https://x/submit', { method: 'POST' }), { DB: db })
  assert.equal(post.status, 405)

  const missing = await call('/nope', db)
  assert.equal(missing.status, 404)
  for (const r of ['/start', '/submit', '/board', '/me']) {
    assert.ok(missing.body.routes.includes(r), r + ' is not advertised')
  }
})
