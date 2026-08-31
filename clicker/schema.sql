-- Apply to the REMOTE database (the one the deployed Worker talks to):
--   npx wrangler d1 execute clicker --remote --file schema.sql
-- and to the local one used by `wrangler dev`:
--   npx wrangler d1 execute clicker --local  --file schema.sql
--
-- Forgetting --remote is the classic D1 mistake: the deploy succeeds and the
-- live Worker then fails on every vote with "no such table: vote".

CREATE TABLE IF NOT EXISTS vote (
  ts     INTEGER NOT NULL,  -- ms since epoch, from the server's clock
  opt    TEXT    NOT NULL,  -- 'A' | 'B' | 'C' | 'D'
  device TEXT               -- random per-browser id, so a student can change their answer
);

-- Every read is a time-range scan, so index the only column we filter on.
CREATE INDEX IF NOT EXISTS vote_ts ON vote (ts);

-- A slide marks its own window when voting closes, so the archive knows which
-- question a burst of votes belonged to instead of inferring it from gaps.
--
-- The server never reads this to decide anything: `tag`, `prompt` and `answer`
-- are opaque annotations it stores and hands back. That is what keeps it
-- question-agnostic and deployable once, even though it now records what a
-- question was called.
CREATE TABLE IF NOT EXISTS window (
  ts      INTEGER NOT NULL,   -- when the mark was written
  tag     TEXT    NOT NULL,   -- e.g. shakedown-q4, l03-q1
  from_ts INTEGER NOT NULL,   -- the vote window this describes
  to_ts   INTEGER NOT NULL,
  round   INTEGER,            -- 1 for the first vote, 2 after discussion
  answer  TEXT,               -- 'A'..'D', or null for an opinion poll
  prompt  TEXT
);

CREATE INDEX IF NOT EXISTS window_from ON window (from_ts);

-- The single currently-open question, so a phone can tell whether voting is open
-- without knowing anything about what the question is. One row, replaced each time
-- a slide opens a window.
--
-- This is the only server state that is not append-only, and it is deliberately
-- disposable: losing it costs a phone one polling cycle of staleness, nothing more.
CREATE TABLE IF NOT EXISTS live (
  id      INTEGER PRIMARY KEY CHECK (id = 1),
  tag     TEXT,
  start_ts INTEGER NOT NULL,
  end_ts   INTEGER NOT NULL
);

-- A student's chosen nickname, which is what the leaderboard puts on the wall.
-- One row per browser, keyed by the same random `device` pseudonym the votes
-- carry. Picking one is optional: a phone with no row here still votes, still
-- counts in every tally and every band, and simply never appears in the
-- standings.
--
-- Keyed by device rather than by name so that renaming is RETROACTIVE. A student
-- who changes their nickname mid-semester keeps one history instead of splitting
-- into two half-scored people on the board.
--
-- Like `live`, this is mutable rather than append-only, and like `live` it is
-- self-healing: every phone re-asserts its name once per page load, so losing
-- this table costs one page load per student, not a semester of standings.
--
-- name_key is the lowercased name and is UNIQUE, so two students cannot claim
-- the same nickname and a projected board is never ambiguous about who is who.
CREATE TABLE IF NOT EXISTS voter (
  device     TEXT PRIMARY KEY,
  name       TEXT    NOT NULL,
  name_key   TEXT    NOT NULL,
  updated_ts INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS voter_name_key ON voter (name_key);

-- ---------------------------------------------------------------------------
-- The arcade: one-minute minigames that produce a score instead of a letter.
-- ---------------------------------------------------------------------------

-- A finished run of one minigame.
--
-- `game` and `round` are opaque strings, exactly like a clicker `tag`: the
-- server stores them and hands them back and never parses either one. That is
-- what lets a new minigame ship as a slide and a content file with no redeploy
-- here, which is the same bargain the clicker already made with questions.
--
-- `detail` is the run's transcript -- which items came up and what was picked.
-- Nothing here reads it. It exists so an implausible run can be looked at by a
-- human afterwards, and so a server-graded mode could be added later without a
-- migration.
--
-- `ms` is the SERVER's measurement, submit_ts - run.start_ts, never a duration
-- the browser reports. The score itself is a claim the browser makes and cannot
-- be anything else while the game runs in the student's tab; the clock does not
-- have to be, so it is not.
CREATE TABLE IF NOT EXISTS play (
  ts     INTEGER NOT NULL,   -- server clock, when the run was submitted
  game   TEXT    NOT NULL,   -- e.g. 'l03-whackabug'
  round  TEXT,               -- the run id minted by /start
  device TEXT    NOT NULL,
  score  INTEGER NOT NULL,
  ms     INTEGER,
  detail TEXT
);

-- Every board is "this game, this time range", so index the pair.
CREATE INDEX IF NOT EXISTS play_game_ts ON play (game, ts);

-- An open run: minted by /start, consumed by /submit, so the server owns both
-- ends of the clock. Deleting the row on submit is what stops one run from
-- being submitted twice, which is the cheapest forgery available otherwise.
--
-- Like `live`, this is mutable and deliberately disposable: an abandoned run is
-- a row nobody will ever consume, and /start sweeps ones older than an hour.
CREATE TABLE IF NOT EXISTS run (
  id       TEXT PRIMARY KEY,
  device   TEXT NOT NULL,
  game     TEXT NOT NULL,
  start_ts INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS run_start ON run (start_ts);
