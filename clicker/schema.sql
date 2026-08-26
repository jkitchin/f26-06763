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
