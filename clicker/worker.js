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

    return json(
      { error: 'not found', routes: ['/', '/v/{A-D}', '/r', '/export', '/stats', '/questions'] },
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
