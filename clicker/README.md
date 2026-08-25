# The in-class clicker

An anonymous multiple-choice clicker. The question is on the projected slide; the
student's phone is a bare A/B/C/D pad. No account, no sign-in, no credential of any
kind, and nothing that identifies a student.

**Live:** <https://clicker.f26-06763.workers.dev>

## Why it is a Worker and not part of `game/`

`game/` makes no runtime network call at all, deliberately (CLAUDE.md §9c: "A feature
that needs a server is a feature this design cannot have"). A live clicker needs
shared state, so it lives here instead and shares none of the game's code. §9c stays
true as written.

GitHub was tried first and rejected on measurement, not taste: release asset
download counts are the only anonymous counter GitHub exposes, and they update on a
**~10 minute batch**. Everything else on GitHub needs a credential.

## The design in one page

**The server knows nothing about questions, lectures, or the semester.** It is
deployed once and left alone. It appends `(ts, opt, device)` rows and answers
time-range queries; all the course content lives in the slides. Changing a question
never means redeploying this.

A question is a **closed window** `[start, start+60s]` chosen by the slide. Votes
outside every window are counted by nothing, which is what stops a late vote from
polluting the next question. The window baseline comes from `server_ts`, not the
projector's clock, which would otherwise mis-slice every window as it drifts.

**Re-voting replaces, it does not add.** Each browser mints a random `device` id and
`/r` counts only that device's *latest* vote in the window. So a student who taps the
wrong letter just taps the right one. A plain "lock for N seconds" was considered and
rejected: it counts the mis-tap *and* the correction.

The `device` id is a pseudonym, not an identity: a random string the browser invents
and keeps. Nothing links it to a person.

**It is not tamper-proof.** Anyone with the URL can vote, and votes are anonymous so
nothing is traceable. That is fine because the clicker is formative and feeds no
grade; participation still comes from the weekly evidence PDF.

## Routes

| Route | Does |
|---|---|
| `GET /` | serves `vote.html` |
| `GET /v/{A-D}?d={device}` | append one vote |
| `GET /r?from=&to=` | tally a window, plus `server_ts` (CORS `*`) |
| `GET /export?from=&to=` | raw rows as CSV, for the archive |

`vote.html` is bundled into the Worker by `import`, so the page is same-origin with
the vote endpoint: no CORS on the write path, and the page shows a real confirmation
rather than firing blind. Only `/r` is read cross-origin, by the slide.

## Working on it

```bash
cd clicker
npx wrangler dev                  # local; add --remote to hit the real database
npx wrangler deploy
npx wrangler tail                 # live request log, useful during class
```

Schema changes go in `schema.sql` and must be applied to **both** databases:

```bash
npx wrangler d1 execute clicker --remote --file schema.sql
npx wrangler d1 execute clicker --local  --file schema.sql
```

Forgetting `--remote` is the classic D1 mistake: the deploy succeeds and the live
Worker then fails every vote with "no such table: vote". The Worker detects that case
and returns the fix in its error body.

## Things that will bite you

- **`clicker/vote.html` is exempted in the root `.gitignore`.** The repo has a blanket
  `*.html` rule for rendered output. Without the exemption the file is silently not
  committed and `wrangler deploy` fails on a fresh clone, the same trap
  `game/index.html` already carries a comment about.
- **The `workers.dev` subdomain is account-wide and baked into the QR code.** Changing
  it breaks every printed deck. It is `f26-06763`, giving `clicker.f26-06763.workers.dev`.
- **A new hostname has no certificate for the first minute or so**, which shows up as
  `ERR_SSL_VERSION_OR_CIPHER_MISMATCH`. Wait rather than debug.
- Free plan ceilings are 100k requests/day and 100k D1 row writes/day, against roughly
  240 votes per session.
