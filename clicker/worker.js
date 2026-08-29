// The 06-763 clicker backend.
//
// Deployed once and then left alone for the semester. It knows nothing about
// questions, lectures, or which week it is: it appends (timestamp, letter) rows
// and answers time-range queries. All the course content lives in the slides,
// so changing a question never means redeploying this.
//
// A "question" is a closed window [start, start+60s] chosen by the slide. Votes
// that land outside every window are simply never counted by anything, which is
// what stops a late vote from polluting the next question.

import VOTE_PAGE from './vote.html'

const OPTS = ['A', 'B', 'C', 'D']

// Only the read routes are cross-origin: the vote page is served from this same
// Worker, but the slide deck is served from the course site.
const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET, HEAD, OPTIONS',
  'access-control-max-age': '86400',
}

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      ...CORS,
    },
  })

// Missing/garbage params fall back rather than throwing, so a malformed slide
// shows zeros instead of a stack trace in front of a lecture hall.
function intParam(url, name, fallback) {
  const raw = url.searchParams.get(name)
  if (raw === null || raw === '') return fallback
  const n = Number(raw)
  return Number.isFinite(n) ? Math.trunc(n) : fallback
}

// D1 throws an opaque error when the table is missing, which happens whenever
// someone applies the schema without --remote. Say so plainly.
function dbError(err) {
  const msg = String(err && err.message ? err.message : err)
  const missing = /no such table/i.test(msg)
  return json(
    {
      error: msg,
      hint: missing
        ? 'The vote table does not exist on this database. Run: npx wrangler d1 execute clicker --remote --file schema.sql'
        : undefined,
    },
    500,
  )
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url)
    const path = url.pathname.replace(/\/+$/, '') || '/'

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS })
    }
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return json({ error: 'method not allowed' }, 405)
    }

    if (path === '/') {
      return new Response(VOTE_PAGE, {
        headers: {
          'content-type': 'text/html; charset=utf-8',
          'cache-control': 'no-store',
        },
      })
    }

    const vote = /^\/v\/([A-D])$/.exec(path)
    if (vote) return castVote(env, vote[1], deviceOf(url))

    if (path === '/r') return readWindow(env, url)
    if (path === '/export') return exportCsv(env, url)
    if (path === '/stats') return stats(env, url)
    if (path === '/questions') return questions(env, url)
    if (path === '/mark') return mark(env, url)
    if (path === '/windows') return windows(env, url)
    if (path === '/open') return openWindow(env, url)
    if (path === '/state') return state(env, url)
    if (path === '/name') return setName(env, url)
    if (path === '/leaderboard') return leaderboard(env, url)

    // The arcade. Same bargain as the clicker: `game` is an opaque key the
    // server never parses, so a new minigame is a slide and a content file
    // rather than a redeploy.
    if (path === '/start') return startRun(env, url)
    if (path === '/submit') return submitRun(env, url)
    if (path === '/board') return board(env, url)
    if (path === '/me') return personalBest(env, url)

    return json(
      {
        error: 'not found',
        routes: [
          '/', '/v/{A-D}', '/r', '/export', '/stats',
          '/questions', '/mark', '/windows', '/open', '/state',
          '/name', '/leaderboard',
          '/start', '/submit', '/board', '/me',
        ],
      },
      404,
    )
  },
}

// A device id is a random string the browser makes up and keeps. It carries no
// identity: its only job is to let one phone replace its own earlier answer, and
// to let the live counter report distinct voters rather than raw taps.
function deviceOf(url) {
  const d = url.searchParams.get('d')
  return d && /^[A-Za-z0-9_-]{8,64}$/.test(d) ? d : null
}

async function castVote(env, opt, device) {
  const ts = Date.now()
  try {
    await env.DB.prepare('INSERT INTO vote (ts, opt, device) VALUES (?, ?, ?)')
      .bind(ts, opt, device)
      .run()
  } catch (err) {
    return dbError(err)
  }
  return json({ ok: true, opt, ts })
}

// GET /r?from=<ms>&to=<ms>
// Returns the tally for a closed window plus the server's clock, which is what
// the slide uses as its baseline. Using the browser's clock instead would
// silently mis-slice every window whenever the projector machine drifts.
async function readWindow(env, url) {
  const now = Date.now()
  const from = intParam(url, 'from', 0)
  const to = intParam(url, 'to', now)

  const counts = Object.fromEntries(OPTS.map((o) => [o, 0]))
  let total = 0

  try {
    // One vote per device per window, and it is the LAST one they cast. That is
    // what makes "tap again to change your answer" mean change rather than add.
    // Rows with no device id (or from a browser with storage blocked) fall back
    // to their rowid, so each such tap counts once on its own.
    const { results } = await env.DB.prepare(
      `SELECT opt, COUNT(*) AS n FROM (
         SELECT opt,
                ROW_NUMBER() OVER (
                  PARTITION BY COALESCE(device, 'row:' || rowid)
                  ORDER BY ts DESC, rowid DESC
                ) AS rn
         FROM vote
         WHERE ts >= ?1 AND ts <= ?2
       )
       WHERE rn = 1
       GROUP BY opt`,
    )
      .bind(from, to)
      .all()

    for (const row of results ?? []) {
      if (Object.prototype.hasOwnProperty.call(counts, row.opt)) {
        counts[row.opt] = row.n
        total += row.n
      }
    }
  } catch (err) {
    return dbError(err)
  }

  return json({ ...counts, total, server_ts: now, from, to })
}

// GET /export?from=<ms>&to=<ms> -> CSV, for committing the record into the repo.
async function exportCsv(env, url) {
  const from = intParam(url, 'from', 0)
  const to = intParam(url, 'to', Date.now())

  let results
  try {
    ;({ results } = await env.DB.prepare(
      'SELECT ts, opt, device FROM vote WHERE ts >= ? AND ts <= ? ORDER BY ts',
    )
      .bind(from, to)
      .all())
  } catch (err) {
    return dbError(err)
  }

  const lines = ['ts,iso,opt,device']
  for (const r of results ?? []) {
    lines.push(`${r.ts},${new Date(r.ts).toISOString()},${r.opt},${r.device ?? ''}`)
  }

  return new Response(lines.join('\n') + '\n', {
    headers: {
      'content-type': 'text/csv; charset=utf-8',
      'cache-control': 'no-store',
      ...CORS,
    },
  })
}

/* ---- reporting -------------------------------------------------------- */

// One vote per device, keeping their last, over an arbitrary list of rows.
// Rows with no device id count individually: a browser with storage blocked
// cannot be recognised between taps, and guessing would be worse than counting.
function tally(rows) {
  const latest = new Map()
  for (const r of rows) {
    const key = r.device || 'row:' + r.rowid
    const prev = latest.get(key)
    if (!prev || r.ts >= prev.ts) latest.set(key, r)
  }
  const counts = Object.fromEntries(OPTS.map((o) => [o, 0]))
  let total = 0
  for (const r of latest.values()) {
    if (Object.prototype.hasOwnProperty.call(counts, r.opt)) {
      counts[r.opt] += 1
      total += 1
    }
  }
  return { ...counts, total }
}

// GET /stats -> overall usage plus a per-day breakdown.
// Days are UTC. Anything that needs Pittsburgh dates should ask /questions for
// an explicit range instead, so the server stays ignorant of time zones.
async function stats(env, url) {
  const days = Math.min(Math.max(intParam(url, 'days', 30), 1), 365)
  try {
    const overall = await env.DB.prepare(
      `SELECT COUNT(*) AS votes,
              COUNT(DISTINCT device) AS devices,
              MIN(ts) AS first_ts,
              MAX(ts) AS last_ts
       FROM vote`,
    ).first()

    const { results } = await env.DB.prepare(
      `SELECT date(ts / 1000, 'unixepoch') AS day,
              COUNT(*) AS votes,
              COUNT(DISTINCT device) AS devices
       FROM vote
       GROUP BY day
       ORDER BY day DESC
       LIMIT ?1`,
    )
      .bind(days)
      .all()

    return json({
      votes: overall?.votes ?? 0,
      devices: overall?.devices ?? 0,
      first_ts: overall?.first_ts ?? null,
      last_ts: overall?.last_ts ?? null,
      first_iso: overall?.first_ts ? new Date(overall.first_ts).toISOString() : null,
      last_iso: overall?.last_ts ? new Date(overall.last_ts).toISOString() : null,
      days: results ?? [],
      server_ts: Date.now(),
    })
  } catch (err) {
    return dbError(err)
  }
}

// GET /questions?from=&to=&gap= -> the question windows, detected rather than declared.
//
// The server never learns what a question is, so it infers one: a burst of votes
// separated from the next by more than `gap` ms. That is what makes archiving
// possible without anyone writing down when each question ran.
async function questions(env, url) {
  const from = intParam(url, 'from', 0)
  const to = intParam(url, 'to', Date.now())
  const gap = Math.min(Math.max(intParam(url, 'gap', 120000), 5000), 3600000)
  const LIMIT = 20000

  let rows
  try {
    ;({ results: rows } = await env.DB.prepare(
      `SELECT rowid, ts, opt, device FROM vote
       WHERE ts >= ?1 AND ts <= ?2 ORDER BY ts LIMIT ?3`,
    )
      .bind(from, to, LIMIT)
      .all())
  } catch (err) {
    return dbError(err)
  }
  rows = rows ?? []

  const out = []
  let cur = []
  for (const r of rows) {
    if (cur.length && r.ts - cur[cur.length - 1].ts > gap) {
      out.push(cur)
      cur = []
    }
    cur.push(r)
  }
  if (cur.length) out.push(cur)

  return json({
    gap,
    truncated: rows.length === LIMIT,
    questions: out.map((b, i) => ({
      n: i + 1,
      from: b[0].ts,
      to: b[b.length - 1].ts,
      from_iso: new Date(b[0].ts).toISOString(),
      seconds: Math.round((b[b.length - 1].ts - b[0].ts) / 1000),
      raw_votes: b.length,
      ...tally(b),
    })),
    server_ts: Date.now(),
  })
}

/* ---- marked windows --------------------------------------------------- */

// GET /mark?tag=&from=&to=&round=&answer=&prompt=
//
// A slide calls this when its question closes, so the archive knows which votes
// belonged to which question instead of inferring it from gaps in the stream.
//
// The server never interprets any of it. `tag`, `prompt` and `answer` are opaque
// strings it stores and hands back, which is what keeps it question-agnostic and
// deployable-once even though it now records what a question was called. Nothing
// here is consulted while voting; the mark is written after the fact.
//
// Like every other route this is unauthenticated, so a mark is a claim rather
// than a fact. That is the same posture as the votes themselves: the clicker is
// formative and feeds no grade, so the cost of a bogus mark is a line in an
// archive that a human can delete.
async function mark(env, url) {
  const tag = url.searchParams.get('tag') || ''
  if (!/^[a-z0-9][a-z0-9._-]{0,63}$/.test(tag)) {
    return json({ error: 'tag must match ^[a-z0-9][a-z0-9._-]{0,63}$' }, 400)
  }

  const from = intParam(url, 'from', 0)
  const to = intParam(url, 'to', 0)
  if (!from || !to || to < from) return json({ error: 'from and to are required, with to >= from' }, 400)

  const answerRaw = (url.searchParams.get('answer') || '').toUpperCase()
  const answer = OPTS.includes(answerRaw) ? answerRaw : null
  const round = intParam(url, 'round', 1)
  // Enough for a question, short enough that nobody can use this as storage.
  const prompt = (url.searchParams.get('prompt') || '').slice(0, 300) || null

  try {
    await env.DB.prepare(
      'INSERT INTO window (ts, tag, from_ts, to_ts, round, answer, prompt) VALUES (?, ?, ?, ?, ?, ?, ?)',
    )
      .bind(Date.now(), tag, from, to, round, answer, prompt)
      .run()
  } catch (err) {
    return dbError(err)
  }
  return json({ ok: true, tag, from, to, round })
}

// GET /windows?from=&to= -> marked windows, each with its tally.
//
// Prefer this over /questions when the slides marked themselves: the boundaries
// are exact rather than guessed, and the prompt and answer come along.
async function windows(env, url) {
  const from = intParam(url, 'from', 0)
  const to = intParam(url, 'to', Date.now())

  let marks
  try {
    ;({ results: marks } = await env.DB.prepare(
      `SELECT ts, tag, from_ts, to_ts, round, answer, prompt FROM window
       WHERE from_ts >= ?1 AND from_ts <= ?2 ORDER BY from_ts LIMIT 2000`,
    )
      .bind(from, to)
      .all())
  } catch (err) {
    return dbError(err)
  }
  marks = marks ?? []
  if (!marks.length) return json({ windows: [], server_ts: Date.now() })

  // One scan over the votes covering every mark, rather than a query per mark.
  const lo = Math.min(...marks.map((m) => m.from_ts))
  const hi = Math.max(...marks.map((m) => m.to_ts))
  let rows
  try {
    ;({ results: rows } = await env.DB.prepare(
      'SELECT rowid, ts, opt, device FROM vote WHERE ts >= ?1 AND ts <= ?2 ORDER BY ts LIMIT 20000',
    )
      .bind(lo, hi)
      .all())
  } catch (err) {
    return dbError(err)
  }
  rows = rows ?? []

  return json({
    windows: marks.map((m) => ({
      tag: m.tag,
      round: m.round,
      answer: m.answer,
      prompt: m.prompt,
      from: m.from_ts,
      to: m.to_ts,
      from_iso: new Date(m.from_ts).toISOString(),
      seconds: Math.round((m.to_ts - m.from_ts) / 1000),
      ...tally(rows.filter((r) => r.ts >= m.from_ts && r.ts <= m.to_ts)),
    })),
    server_ts: Date.now(),
  })
}

/* ---- the currently open question -------------------------------------- */

// GET /open?tag=&seconds= -> record that a question just opened.
//
// The server still does not know what the question IS. It knows only that one is
// running and when it stops, which is the least it can know and still let a phone
// clear itself at the right moment instead of guessing with a timer.
async function openWindow(env, url) {
  const tag = url.searchParams.get('tag') || ''
  if (tag && !/^[a-z0-9][a-z0-9._-]{0,63}$/.test(tag)) {
    return json({ error: 'bad tag' }, 400)
  }
  const seconds = Math.min(Math.max(intParam(url, 'seconds', 60), 5), 3600)
  const now = Date.now()
  const end = now + seconds * 1000
  try {
    await env.DB.prepare(
      'INSERT OR REPLACE INTO live (id, tag, start_ts, end_ts) VALUES (1, ?, ?, ?)',
    )
      .bind(tag || null, now, end)
      .run()
  } catch (err) {
    return dbError(err)
  }
  return json({ ok: true, tag: tag || null, start: now, end, server_ts: now })
}

// GET /state -> is a question open, and when does it stop?
//
// Every phone polls this, so it stays one indexed row and no scan. `start` is the
// identity of a question as far as a phone is concerned: when it changes, a new
// question began and the pad should clear.
async function state(env) {
  const now = Date.now()
  let row
  try {
    row = await env.DB.prepare('SELECT tag, start_ts, end_ts FROM live WHERE id = 1').first()
  } catch (err) {
    return dbError(err)
  }
  if (!row) return json({ open: false, start: null, end: null, tag: null, server_ts: now })
  return json({
    open: now < row.end_ts,
    start: row.start_ts,
    end: row.end_ts,
    tag: row.tag,
    server_ts: now,
  })
}

/* ---- nicknames and the leaderboard ------------------------------------ */

// A nickname is 2 to 24 characters, ASCII only, and must contain a letter or a
// digit. The charset is narrow on purpose: this ends up projected at the front
// of a room, where a right-to-left override or a confusable is a prank rather
// than a name, and where anything non-ASCII is a rendering gamble on whichever
// machine happens to be driving the projector.
//
// Returns null for anything that cannot be made into a name, rather than
// silently mangling it into something the student did not type.
const NAME_MAX = 24

function normalizeName(raw) {
  let s = String(raw || '')
    .replace(/[\u0000-\u001f\u007f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (s.length > NAME_MAX) s = s.slice(0, NAME_MAX).trim()
  if (s.length < 2) return null
  if (!/^[A-Za-z0-9 ._-]+$/.test(s)) return null
  if (!/[A-Za-z0-9]/.test(s)) return null
  return s
}

// GET /name?d=<device>&n=<nickname> -> claim or change a nickname.
//
// Called when a student first picks a name, when they change it, and once per
// page load as a re-assertion. That last one is what makes the `voter` table
// disposable in the same sense `live` is: drop it and every phone puts its own
// row back the next time the pad is opened.
//
// Names are unique, case-insensitively, so the board is never ambiguous about
// who is who. A name already held by a DIFFERENT device is a 409 the pad turns
// into "that one is taken"; the same device re-claiming its own name is a no-op
// success, which is what makes the re-assertion on load free.
async function setName(env, url) {
  const device = deviceOf(url)
  if (!device) return json({ error: 'a device id is required' }, 400)

  const name = normalizeName(url.searchParams.get('n'))
  if (!name) {
    return json(
      { error: 'a nickname is 2 to 24 characters, using letters, digits, space, dot, dash or underscore' },
      400,
    )
  }
  const key = name.toLowerCase()

  try {
    const holder = await env.DB.prepare('SELECT device FROM voter WHERE name_key = ?')
      .bind(key)
      .first()
    if (holder && holder.device !== device) return json({ error: 'taken', name }, 409)

    await env.DB.prepare(
      `INSERT INTO voter (device, name, name_key, updated_ts) VALUES (?1, ?2, ?3, ?4)
       ON CONFLICT(device) DO UPDATE SET name = ?2, name_key = ?3, updated_ts = ?4`,
    )
      .bind(device, name, key, Date.now())
      .run()
  } catch (err) {
    // Two phones can pass the check above in the same instant; the unique index
    // is what actually decides it, so report the loser as taken rather than 500.
    if (/UNIQUE/i.test(String(err && err.message))) return json({ error: 'taken', name }, 409)
    return dbError(err)
  }

  return json({ ok: true, name })
}

// GET /leaderboard?from=&to=&top=&hours= -> the standings.
//
// Everything this needs is already on disk, which is why a leaderboard costs the
// server no new knowledge and no redeploy when a question changes. A marked
// window carries the answer and the exact boundaries; a vote carries the
// server's own timestamp. So:
//
//   correct  = the student's last answer on a question matched the mark
//   response = vote.ts - window.from_ts, both ends off the server's clock
//
// Neither number is supplied by the phone, so neither can be forged by editing a
// request, which is a stronger position than the rest of these routes are in.
//
// Only questions that were TAGGED and REVEALED can score, because a mark is
// written at reveal and is the only place a start time survives. An unrevealed
// question scores nothing, the same way it archives as nothing.
async function leaderboard(env, url) {
  const now = Date.now()
  const hours = Math.min(Math.max(intParam(url, 'hours', 6), 1), 24 * 30)
  const to = intParam(url, 'to', now)
  const from = intParam(url, 'from', to - hours * 3600000)
  const top = Math.min(Math.max(intParam(url, 'top', 5), 1), 200)

  let marks
  try {
    ;({ results: marks } = await env.DB.prepare(
      `SELECT tag, from_ts, to_ts, round, answer FROM window
       WHERE from_ts >= ?1 AND from_ts <= ?2 AND answer IS NOT NULL
       ORDER BY from_ts LIMIT 2000`,
    )
      .bind(from, to)
      .all())
  } catch (err) {
    return dbError(err)
  }
  marks = marks ?? []
  // An opinion poll carries no answer and cannot score, so a session made only
  // of those comes back empty rather than as an error.
  if (!marks.length) {
    return json({ standings: [], players: 0, questions: 0, from, to, server_ts: now })
  }

  const lo = Math.min(...marks.map((m) => m.from_ts))
  const hi = Math.max(...marks.map((m) => m.to_ts))

  let rows, voters
  try {
    ;({ results: rows } = await env.DB.prepare(
      `SELECT rowid, ts, opt, device FROM vote
       WHERE ts >= ?1 AND ts <= ?2 AND device IS NOT NULL
       ORDER BY ts LIMIT 20000`,
    )
      .bind(lo, hi)
      .all())
    // One row per student for the whole semester, so this stays small enough to
    // read whole rather than joining it per device.
    ;({ results: voters } = await env.DB.prepare('SELECT device, name FROM voter').all())
  } catch (err) {
    return dbError(err)
  }
  rows = rows ?? []

  // device -> tag -> { correct, elapsed }
  const per = new Map()
  const tags = new Set()

  for (const m of marks) {
    tags.add(m.tag)

    // Their last vote inside this window, which is the same rule the tally uses:
    // tapping again changes your answer rather than adding to it.
    const last = new Map()
    for (const r of rows) {
      if (r.ts < m.from_ts || r.ts > m.to_ts) continue
      const prev = last.get(r.device)
      if (!prev || r.ts > prev.ts || (r.ts === prev.ts && r.rowid > prev.rowid)) {
        last.set(r.device, r)
      }
    }

    for (const [device, r] of last) {
      if (!per.has(device)) per.set(device, new Map())
      // Marks arrive in from_ts order, so round two overwrites round one: your
      // last answer on a question counts. Overwriting rather than merging is
      // what stops a student who nailed round one and then sat out round two
      // from losing a point they had already earned.
      per.get(device).set(m.tag, {
        correct: r.opt === m.answer,
        elapsed: Math.max(0, r.ts - m.from_ts),
      })
    }
  }

  const nameOf = new Map((voters ?? []).map((v) => [v.device, v.name]))
  const standings = []

  for (const [device, byTag] of per) {
    const name = nameOf.get(device)
    // No nickname means voting anonymously, which stays a supported way to use
    // the clicker: those votes counted in every bar and every band, and simply
    // do not appear here.
    if (!name) continue

    let correct = 0
    let ms = 0
    let answered = 0
    for (const rec of byTag.values()) {
      answered += 1
      // Time accumulates only on answers that were RIGHT. A wrong answer costs
      // the point and nothing else, so attempting a question you are unsure of
      // is never worse than staying quiet.
      if (rec.correct) {
        correct += 1
        ms += rec.elapsed
      }
    }
    standings.push({ name, correct, answered, ms, seconds: Math.round(ms / 100) / 10 })
  }

  // More right always beats faster; time is the tiebreak, and the name is a
  // final tiebreak so that two identical scores do not swap places between two
  // reads of the same data in front of a room.
  standings.sort((a, b) => b.correct - a.correct || a.ms - b.ms || a.name.localeCompare(b.name))
  standings.forEach((s, i) => {
    s.rank = i + 1
  })

  // `device` is deliberately absent from the response. The board carries the
  // name a student invented and nothing that links it back to a browser.
  return json({
    standings: standings.slice(0, top),
    players: standings.length,
    questions: tags.size,
    from,
    to,
    server_ts: now,
  })
}

/* ---- the arcade ---------------------------------------------------------
 *
 * A minigame is a slide plus a content file. This server learns none of that:
 * it mints a run id, stamps the clock at both ends, and ranks integers under an
 * opaque `game` key. The same reason the clicker has been deployed once and
 * left alone applies here, which is the only reason the arcade is allowed to
 * live in this Worker at all.
 *
 * What is and is not trustworthy here, said plainly, because the difference
 * matters more than the code does:
 *
 *   ms     the server's own subtraction, submit_ts - run.start_ts. A phone
 *          cannot shorten it, and a run cannot be submitted twice because
 *          /submit deletes the row it consumed.
 *   score  a CLAIM. The game runs in the student's tab, so the number arrives
 *          the way a /mark arrives: asserted, not proven. The arcade is
 *          formative and feeds no grade, exactly like the clicker, so the cost
 *          of a bogus run is a row in a table a human can delete.
 *
 * If a scored-for-real variant is ever wanted, the shape already exists in this
 * file: post a transcript, supply the key afterwards the way /mark does, and
 * grade retroactively. `detail` is where that transcript already lands.
 */

// Same shape as a clicker tag, and validated for the same reason: it is
// concatenated into no SQL, but a board keyed by junk is a board nobody can
// find again.
function gameOf(url) {
  const g = url.searchParams.get('g')
  return g && /^[a-z0-9][a-z0-9_-]{0,63}$/.test(g) ? g : null
}

// A run older than this was abandoned rather than played, so it can neither be
// submitted nor kept. Thirty minutes is long enough for a student to be
// interrupted mid-round and short enough that the table stays small.
const RUN_MAX_MS = 30 * 60 * 1000

// Not a content-aware cap -- the server does not know what any game scores out
// of, and must not. It is a sanity bound, so a garbled or malicious submission
// lands as an outlier a human can spot rather than as Number.MAX_SAFE_INTEGER
// permanently on top of every board.
const SCORE_LIMIT = 1000000

// GET /start?d=<device>&g=<game> -> { run, start, server_ts }
//
// The handshake exists for one reason: so the duration of a run is measured by
// this clock rather than reported by the browser that has every reason to
// report a short one.
async function startRun(env, url) {
  const device = deviceOf(url)
  const game = gameOf(url)
  if (!device) return json({ error: 'a device id is required' }, 400)
  if (!game) return json({ error: 'a game key is required' }, 400)

  const now = Date.now()
  const id = crypto.randomUUID()

  try {
    // Sweep first. An abandoned run is a row no /submit will ever consume, and
    // nothing else ever deletes one.
    await env.DB.prepare('DELETE FROM run WHERE start_ts < ?').bind(now - RUN_MAX_MS).run()
    await env.DB.prepare('INSERT INTO run (id, device, game, start_ts) VALUES (?, ?, ?, ?)')
      .bind(id, device, game, now)
      .run()
  } catch (err) {
    return dbError(err)
  }

  return json({ run: id, start: now, server_ts: now })
}

// GET /submit?d=&g=&run=&s=&detail= -> { ok, score, ms, rank, players, best }
//
// Consuming the run row is what makes a run single-use. A replayed submit finds
// nothing to consume and is rejected, which closes the one forgery that costs
// an attacker nothing at all.
async function submitRun(env, url) {
  const device = deviceOf(url)
  const game = gameOf(url)
  const runId = url.searchParams.get('run')
  if (!device) return json({ error: 'a device id is required' }, 400)
  if (!game) return json({ error: 'a game key is required' }, 400)
  if (!runId) return json({ error: 'a run id is required' }, 400)

  const raw = Number(url.searchParams.get('s'))
  if (!Number.isFinite(raw)) return json({ error: 'a numeric score is required' }, 400)
  const score = Math.max(-SCORE_LIMIT, Math.min(SCORE_LIMIT, Math.trunc(raw)))

  // Kept whole and never parsed here. Truncated rather than rejected: a run
  // that scored is worth recording even when its transcript ran long.
  const detail = (url.searchParams.get('detail') || '').slice(0, 4000) || null

  const now = Date.now()

  let open
  try {
    open = await env.DB.prepare('SELECT id, device, game, start_ts FROM run WHERE id = ?')
      .bind(runId)
      .first()
  } catch (err) {
    return dbError(err)
  }

  // One message for all four ways this fails -- unknown, already submitted,
  // someone else's, or a different game. Telling a caller which one it was only
  // helps the caller who is guessing.
  if (!open || open.device !== device || open.game !== game || now - open.start_ts > RUN_MAX_MS) {
    return json({ error: 'no open run' }, 409)
  }

  const ms = Math.max(0, now - open.start_ts)

  try {
    await env.DB.prepare(
      'INSERT INTO play (ts, game, round, device, score, ms, detail) VALUES (?, ?, ?, ?, ?, ?, ?)',
    )
      .bind(now, game, runId, device, score, ms, detail)
      .run()
    await env.DB.prepare('DELETE FROM run WHERE id = ?').bind(runId).run()
  } catch (err) {
    return dbError(err)
  }

  // Where that run left them, all-time, which is the number a solo player came
  // for. The live board is the slide's business, not the submitting phone's.
  const field = await bests(env, game, 0, now)
  if (field.error) return field.error
  const placed = rankOf(field.rows, device)

  return json({
    ok: true,
    score,
    ms,
    rank: placed.rank,
    players: field.rows.length,
    best: placed.best,
    server_ts: now,
  })
}

// Every device's BEST run of one game inside a time range, best first.
//
// Best rather than latest, and best rather than total: a board of totals ranks
// whoever played most, which rewards grinding a game they have already learned
// nothing more from. One good run is the claim being made, so one good run is
// what the board should carry.
async function bests(env, game, from, to) {
  let rows
  try {
    ;({ results: rows } = await env.DB.prepare(
      `SELECT device, score, ms, ts FROM (
         SELECT device, score, ms, ts,
                ROW_NUMBER() OVER (
                  PARTITION BY device ORDER BY score DESC, ms ASC, ts ASC
                ) AS rn
         FROM play
         WHERE game = ?1 AND ts >= ?2 AND ts <= ?3
       ) WHERE rn = 1
       LIMIT 5000`,
    )
      .bind(game, from, to)
      .all())
  } catch (err) {
    return { error: dbError(err) }
  }
  rows = rows ?? []
  // More points always beats faster, time is the tiebreak, and the device is a
  // final tiebreak so two identical runs do not swap places between two reads
  // of the same data in front of a room.
  rows.sort((a, b) => b.score - a.score || a.ms - b.ms || String(a.device).localeCompare(String(b.device)))
  return { rows }
}

// A device's place in the field.
//
// The field is EVERYONE who played, not everyone the board shows. A student who
// never picked a nickname still occupied a place, and quietly renumbering
// around them would tell the named players they beat more people than they did.
function rankOf(rows, device) {
  const i = rows.findIndex((r) => r.device === device)
  if (i < 0) return { rank: null, best: null }
  return { rank: i + 1, best: { score: rows[i].score, ms: rows[i].ms } }
}

// GET /board?g=&hours=&top=&all= -> { standings, players, from, to }
//
// Two boards, one route, because they differ only in where the window starts:
//
//   ?hours=6  the rolling live board, projected in the lecture hall, showing
//             what happened in this session and nothing older.
//   ?all=1    the semester board, every run since the table was created, still
//             ranked by each player's best rather than by how often they played.
async function board(env, url) {
  const now = Date.now()
  const game = gameOf(url)
  if (!game) return json({ error: 'a game key is required' }, 400)

  const hours = Math.min(Math.max(intParam(url, 'hours', 6), 1), 24 * 400)
  const to = intParam(url, 'to', now)
  const all = url.searchParams.get('all') === '1'
  const from = all ? 0 : intParam(url, 'from', to - hours * 3600000)
  const top = Math.min(Math.max(intParam(url, 'top', 10), 1), 200)

  const field = await bests(env, game, from, to)
  if (field.error) return field.error

  let voters
  try {
    ;({ results: voters } = await env.DB.prepare('SELECT device, name FROM voter').all())
  } catch (err) {
    return dbError(err)
  }
  const nameOf = new Map((voters ?? []).map((v) => [v.device, v.name]))

  // Playing without a nickname stays a supported way to use the arcade, and it
  // is the same rule the clicker's standings already follow: the run counted,
  // it occupies its place in the field, and it simply is not named here.
  const standings = []
  field.rows.forEach((r, i) => {
    const name = nameOf.get(r.device)
    if (!name) return
    standings.push({ name, score: r.score, ms: r.ms, seconds: Math.round(r.ms / 100) / 10, rank: i + 1 })
  })

  // `device` is deliberately absent, exactly as it is from /leaderboard. The
  // board carries a nickname a student invented and nothing that links it back
  // to a browser.
  return json({
    game,
    standings: standings.slice(0, top),
    named: standings.length,
    players: field.rows.length,
    all,
    from,
    to,
    server_ts: now,
  })
}

// GET /me?d=&g= -> { best, rank, players }
//
// A solo player needs a target without needing the board, and their own best is
// the only one that is theirs to beat.
async function personalBest(env, url) {
  const now = Date.now()
  const device = deviceOf(url)
  const game = gameOf(url)
  if (!device) return json({ error: 'a device id is required' }, 400)
  if (!game) return json({ error: 'a game key is required' }, 400)

  const field = await bests(env, game, 0, now)
  if (field.error) return field.error
  const placed = rankOf(field.rows, device)

  return json({
    game,
    best: placed.best,
    rank: placed.rank,
    players: field.rows.length,
    server_ts: now,
  })
}
