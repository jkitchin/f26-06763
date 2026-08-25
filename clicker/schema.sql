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
