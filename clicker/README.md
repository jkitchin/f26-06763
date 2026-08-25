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
| `GET /export?from=&to=` | raw rows as CSV |
| `GET /stats?days=` | overall usage plus a per-day breakdown |
| `GET /questions?from=&to=&gap=` | question windows, **detected** rather than declared |

`/questions` is the one worth understanding. The server never learns what a question
is, so it infers one: a burst of votes separated from the next by more than `gap`
milliseconds (two minutes by default). That is what makes archiving possible without
anyone writing down when each question ran, and it is why the deploy-once property
survives contact with reporting.

`vote.html` is bundled into the Worker by `import`, so the page is same-origin with
the vote endpoint: no CORS on the write path, and the page shows a real confirmation
rather than firing blind. Only `/r` is read cross-origin, by the slide.

## The deck and the driver

`shakedown.md` is a MARP deck for a dry run at the end of class: it checks the thing
works with a room full of real phones before anything depends on it, and asks students
to set a few defaults. Render it next to its assets, because MARP emits relative paths:

```bash
npx @marp-team/marp-cli clicker/shakedown.md --html -o clicker/shakedown.html
```

`clicker-slide.js` drives every `.clicker` on a deck. It is a separate file rather than
inlined so a second deck does not mean a second copy; a deck pulls it in with
`<script src="clicker-slide.js"></script>`. A *lecture* deck would also need CI to copy
it next to the rendered slides, which is not wired up yet.

Per question:

```html
<div class="clicker" data-seconds="60" data-answer="B" data-read="https://...">
```

`data-answer` is optional. With it, the reveal scores the room and reacts on Mazur's
three bands: fireworks above 70%, "turn to your neighbour" between 30 and 70, rain
below 30. Without it the bars just appear, which is what an opinion poll wants.

The correct answer lives on the slide and is **never sent to the server**. That is what
keeps the server question-agnostic.

Styles live in `themes/course.css` with the other slide classes.

## Reading the results

```bash
python3 tools/clicker.py stats                    # usage overall and per day
python3 tools/clicker.py questions --date today   # detected windows, with bars
python3 tools/clicker.py show                     # live bars, a backstop for the slide
python3 tools/clicker.py archive l03 --date today # writes course/clicker/l03.yml
```

Time zones live in the CLI, not the Worker: the Worker takes `from`/`to` in epoch ms and
stays ignorant of dates, which is what lets it be deployed once and never touched.

`archive` fills in everything the server knows and leaves `prompt` and `answer` blank,
because the server never sees either. Device pseudonyms are deliberately not carried
into the archive.

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
- **Cloudflare's browser-integrity check 403s `Python-urllib`** with error code 1010, so
  `tools/clicker.py` sends a real User-Agent. Anything else scripting these endpoints
  needs to do the same.
- **MARP scales slides with a CSS transform**, which defeats coordinate-based clicking in
  Puppeteer. Browser tests must dispatch `element.click()` in-page instead.
