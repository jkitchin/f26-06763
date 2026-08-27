# The in-class clicker

An anonymous multiple-choice clicker for lecture. The question is on the projected
slide; the student's phone is a bare A/B/C/D pad. No account, no sign-in, no
credential of any kind, and nothing that identifies a student.

**Vote page:** <https://clicker.f26-06763.workers.dev>
**Rendered deck:** <https://kitchingroup.cheme.cmu.edu/f26-06763/slides/clicker/>

---

## Contents

1. [Design, and why it is shaped this way](#design-and-why-it-is-shaped-this-way)
2. [Why not GitHub](#why-not-github)
3. [Setting it up from nothing](#setting-it-up-from-nothing)
4. [The routes](#the-routes)
5. [Writing a clicker slide](#writing-a-clicker-slide)
6. [What happens when voting closes](#what-happens-when-voting-closes)
7. [The leaderboard](#the-leaderboard)
8. [Reading the results](#reading-the-results)
9. [Working on it](#working-on-it)
10. [Things that will bite you](#things-that-will-bite-you)
11. [What this does not defend against](#what-this-does-not-defend-against)

---

## Design, and why it is shaped this way

**The server knows nothing about questions, lectures, or the semester.** It appends
`(timestamp, letter, device)` rows and answers time-range queries. Every question
lives in the slides, so **changing a question never means redeploying the server.**
It has been deployed once and is meant to stay that way for the semester.

**The phone never sees the question.** It is four buttons. That keeps every upcoming
question off every student's device, means nothing leaks by reading a bundle, and is
why a single QR code works all year.

**A question is a closed window** `[start, start + seconds]`. Both ends come from the
server's clock, returned as `server_ts`, because a projector whose clock drifts would
otherwise mis-slice every window silently. Votes landing outside every window are
counted by nothing, which is what stops a late vote from polluting the next question.

**Re-voting replaces, it does not add.** Each browser mints a random `device`
pseudonym, and a tally counts only that device's *most recent* vote inside the window.
A student who taps the wrong letter just taps the right one. "Lock the buttons for N
seconds" was considered and rejected: it counts the mis-tap *and* the correction.

The `device` id is a pseudonym, not an identity: a random string the browser invents
and keeps in `localStorage`. Nothing links it to a person, and it is deliberately not
carried into the committed archive.

**The pad clears itself the moment voting closes.** A slide calls `/open` when a
question starts, and the phone polls `/state` every 5 seconds to learn whether one is
running and when it stops. A changed `start` means a new question, so the pad clears;
past `end`, it clears and says "Voting closed". Students also get a live countdown.

The server learns only that *a* question is running and when it stops, never what it
is, so this costs none of the deploy-once property. `live` is the only table that is
not append-only, and it is deliberately disposable: losing it costs one polling cycle
of staleness.

This replaced a fixed 75-second timer started at the moment of voting, which could not
work: it had no idea when voting actually ended, so a student who voted at second 5 of
a 45-second question stared at their own answer for 40 seconds past the reveal. The
timer survives only as a fallback for a phone that cannot reach `/state`.

Polling pauses while the phone is pocketed and resumes on wake, which keeps a 40-person
class near 24k requests a session against a 100k/day budget.

**A nickname is a pseudonym a student invents, and the server never learns who
chose it.** The board needs a name to put on the wall, and that is the only thing it
needs. A phone stores its nickname in `localStorage` next to the `device` pseudonym it
already had, re-asserts it once per page load, and the `voter` table maps one to the
other. Nothing in that chain reaches a roster: a student who types `null_pointer` is
`null_pointer` to the server, to the projector, and to the committed archive.

**Both halves of a score come off the server's clock.** A point is one correct answer,
and the tiebreak is time summed over the *correct* answers only, measured from the
moment the slide opened the window to the moment the vote row landed. Neither number
is client-supplied, so neither can be improved by editing a request. That makes the
leaderboard the hardest thing here to cheat, which is an odd place for the strongest
guarantee in an otherwise unauthenticated system to end up. Check that before you
decide to attach anything to it.

`game/` is untouched. CLAUDE.md section 9c says "a feature that needs a server is a
feature this design cannot have"; the clicker shares none of the game's code, so that
statement stays true as written.

## Why not GitHub

Capturing votes in GitHub was the first design, and it would have avoided a new
service. It was measured rather than assumed, and it fails: release asset
`download_count` is the only anonymous counter GitHub exposes, and it is **batched on
roughly a ten minute cadence**. A busy asset sat frozen for fourteen minutes while
visibly being downloaded; a fresh asset first updated at t+611s. Everything else on
GitHub (issues, comments, discussions, gists, `repository_dispatch`) needs a
credential.

GoatCounter was rejected too: `/count` is rate-limited to 4 requests/second keyed on
IP plus User-Agent, so a lecture hall behind one NAT drops votes **silently**, which
is the worst failure a vote counter can have.

## Setting it up from nothing

This has been done once already. These are the steps to reproduce it, for a new
semester or a new owner.

### 1. A Cloudflare account

Sign up at <https://dash.cloudflare.com/sign-up> with an email and password. The
Workers free plan needs no payment method.

**Skip the "Add a site" onboarding.** You do not need a domain and you do not need to
move DNS anywhere; Workers run on a free `workers.dev` subdomain with TLS Cloudflare
manages. There is no certificate to obtain or renew.

### 2. Choose the account subdomain carefully

Your first deploy asks you to claim an account-wide subdomain. The Worker is named
`clicker`, so the two are joined:

```
clicker  .  f26-06763  . workers.dev
(worker)    (the account subdomain)
```

It is **account-wide, permanent in practice, and baked into the QR code**. Changing it
later breaks every printed deck, and the API refuses to change it at all (error 10036,
"Account already has an associated subdomain"); only the dashboard can, at
Workers & Pages -> Change next to *Your subdomain*.

### 3. Log in and create the database

```bash
cd clicker
npx wrangler login                       # opens a browser
npx wrangler d1 create clicker           # prints a [[d1_databases]] block
```

Paste the printed block into `wrangler.toml`, but keep `binding = "DB"`: the binding
name is what the code reads as `env.DB` and does not have to match the database name.

### 4. Create the tables, on the remote database

```bash
npm run schema:remote     # wrangler d1 execute clicker --remote --file schema.sql
npm run schema:local      # the separate database `wrangler dev` uses
```

**Forgetting `--remote` is the classic D1 mistake.** The table gets created only in a
local dev file, `wrangler deploy` succeeds, and the live Worker then fails every vote
with "no such table: vote". The Worker detects that case and returns the fix in its
error body.

### 5. Deploy

```bash
npm run deploy            # wrangler deploy
```

A brand-new hostname has **no certificate for the first minute or several**, which
shows up as `ERR_SSL_VERSION_OR_CIPHER_MISMATCH` in the browser and a TLS alert 40 in
curl. That is provisioning lag, not a misconfiguration. Renaming the subdomain took
about four minutes; the first deploy took about one. Wait rather than debug.

### 6. Generate the QR code

```bash
uv run --with segno clicker/make_qr.py
```

It encodes the vote URL and writes `clicker/figures/clicker-qr.png`. Because the
server is question-agnostic, **the URL is identical for every question and every
lecture, so one QR serves the whole course** and students can bookmark it.

Regenerate only if the hostname changes, which also invalidates every printed deck.

Before trusting it, check it scans **at projector size from the back of the room**.
That is the only test that matters and the only one you cannot do at a desk.

## The routes

| Route | Does |
|---|---|
| `GET /` | serves `vote.html` |
| `GET /v/{A-D}?d={device}` | append one vote |
| `GET /r?from=&to=` | tally a window, plus `server_ts` (CORS `*`) |
| `GET /export?from=&to=` | raw rows as CSV |
| `GET /stats?days=` | overall usage and a per-day breakdown |
| `GET /questions?from=&to=&gap=` | question windows **inferred** from gaps |
| `GET /mark?tag=&from=&to=&round=&answer=&prompt=` | a slide records its own window |
| `GET /windows?from=&to=` | the marked windows, each with its tally |
| `GET /open?tag=&seconds=` | a slide announces that a question just opened |
| `GET /state` | is a question running, and when does it stop |
| `GET /name?d={device}&n={nickname}` | claim or change a nickname; `409` if taken |
| `GET /leaderboard?from=&to=&top=` | standings for a range (CORS `*`) |

`vote.html` is bundled into the Worker by `import`, so the page is same-origin with
the vote endpoint: no CORS on the write path, and the page shows a real confirmation
rather than firing blind. Only the read routes are cross-origin, called by the deck.

`/mark` and `/windows` are how the archive knows which votes belonged to which
question. The server still never *interprets* any of it: `tag`, `prompt` and `answer`
are opaque strings it stores and hands back, written after the fact and never
consulted while voting is open. That is what keeps the deploy-once property intact
even though the server now records what a question was called.

`/leaderboard` is a join of `window` against `vote` and costs the server no new
knowledge of what a question is: it reads the marks a slide already wrote at reveal,
finds each device's last vote inside each window, and scores it. A question that was
never revealed has no mark, so it never scores. An opinion poll has a mark with no
answer, so it scores nothing either.

`/questions` is the fallback for a deck whose slides carry no tag: it infers a
question as a burst of votes separated from the next by more than `gap` milliseconds
(two minutes by default).

## Writing a clicker slide

MARP is configured with `html: true` in `.marprc.yml`, so a slide can carry raw HTML.
Styles live in `themes/course.css` with the other slide classes; the behaviour lives
in `clicker-slide.js`, which a deck pulls in **once, at the end**:

```html
<script src="clicker-slide.js"></script>
```

It is a separate file rather than inlined so a second deck is not a second copy of
300 lines. CI copies it next to **every** rendered deck, so `src="clicker-slide.js"`
resolves for a lecture deck as well. `figures/clicker-qr.png` is copied the same way
and for the same reason: one code serves the whole course, so it lives once here
rather than as 22 copies that all go stale the day the vote URL changes.

Rendering a lecture deck **locally** needs both of those beside the deck, which is the
wrinkle `figures/` already has. Symlink them once, and `.gitignore` keeps the links out
of the repository:

```bash
ln -sf ../../clicker/clicker-slide.js          lectures/l03/clicker-slide.js
ln -sf ../../../clicker/figures/clicker-qr.png lectures/l03/figures/clicker-qr.png
```

Skip that and the deck still renders, with a dead `Start voting` button and a broken
image where the QR belongs. CI catches the same two omissions in its own render, so
this bites only while authoring.

One question looks like this:

```html
## Now one that will not go well

<div class="clicker"
     data-tag="l03-q1"
     data-seconds="45"
     data-answer="C"
     data-hint="A pointer at what to reconsider, never the answer."
     data-why="Why the answer is the answer, shown only when they get there."
     data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**Everyone tap B.** You tap A, change your mind, and tap C. What does the tally count?

<ol class="clicker-opts">
<li>Both of them, one vote each</li>
<li>Only my first answer, A</li>
<li>Only my last answer, C</li>
<li>Neither, it throws both away</li>
</ol>

</div>
<aside class="clicker-panel">
<img src="figures/clicker-qr.png" alt="QR code linking to the vote page">
<div class="clicker-url">clicker.f26-06763.workers.dev</div>
<button class="clicker-start">Start voting</button>
<div class="clicker-timer">45</div>
<div class="clicker-count">no votes yet</div>
</aside>
</div>
```

| Attribute | Required | Does |
|---|---|---|
| `data-read` | yes | the Worker's base URL |
| `data-seconds` | no (60) | how long the window stays open |
| `data-tag` | no | records the window for the archive; lowercase, `[a-z0-9._-]`, 64 chars |
| `data-answer` | no | `A`-`D`. Omit for an opinion poll: bars appear, no verdict, no effects |
| `data-autostart` | no | `false` to require pressing the button instead of opening on slide entry |
| `data-hint` | no | shown only when the room did **not** sail through |
| `data-why` | no | shown only when they **did** |
| `data-top` | no (5) | how many names the board shows at reveal |
| `data-leaderboard` | no | `false` to reveal this question with no board at all |

The options are an `<ol class="clicker-opts">`; the A/B/C/D badges are CSS counters,
so never number them by hand. Leave blank lines around markdown inside the divs or it
will not render.

**The correct answer lives on the slide and is never sent to the server while voting
is open.** That is what lets the server stay question-agnostic. It travels to `/mark`
only after the window closes, as an archival annotation.

The prompt recorded with a mark is read from the slide's heading, so nobody maintains
the question text twice.

Render it with:

```bash
cd clicker && npm run slides       # -> shakedown.html
```

**That script deliberately renders from the repo root.** `.marprc.yml` says
`themeSet: ./themes`, which resolves against the working directory, so running marp
from inside `clicker/` silently drops the course theme: no red rules, no two-column
layout, the QR at its natural 420px pushing the timer and the Start button off the
bottom of the slide, and the options showing native `1. 2. 3.` markers. It looks like
a broken deck rather than a missing theme, so if a deck ever renders as plain
markdown, check the working directory first.

## What happens when voting closes

While a question is open the panel shows **only how many votes have arrived**, never
the distribution. Showing live bars biases whoever has not voted yet, which is the one
thing peer instruction is strict about.

**Voting opens by itself when the slide comes up**, so there is nothing to remember.
That is driven by an `IntersectionObserver` on the slide rather than MARP's own events,
which are not exposed, so it works in slide mode and scroll mode alike. Returning to a
slide does not reopen it: that would start a second window and discard the first
result. `data-autostart="false"` opts a question out, and the button still works.

Opening a window takes the baseline from the server's clock and unlocks audio (browsers
block autoplay until a user gesture; navigating to the slide is one). The button reads
**Reveal now**, so you can close early instead of waiting out the clock.

At zero, or on **Reveal now**, the bars appear, the correct bar is highlighted, and the
room's score is placed in one of three bands. The bands are Mazur's, and they are
chosen because they map onto what to *do* next rather than merely scoring the room:

| Correct | What appears | What it means you do |
|---|---|---|
| **above 70%** | fireworks on a canvas, a short synthesized crackle, the green `data-why` box | They have it. Say why, and move on. |
| **30% to 70%** | no effect, an amber verdict reading "turn to your neighbour and convince them", and the `data-hint` box | The productive case. Give them 30 seconds to argue, then press **Vote again**. |
| **below 30%** | dark clouds and rain on a canvas, a filtered-noise downpour, and the `data-hint` box | Not their fault. Re-teach it, then vote again. |

With no `data-answer` there is no verdict and no effect: the bars simply appear, which
is what an opinion poll wants. **With no votes at all it says so**, rather than
revealing an empty chart in silence, which reads as broken rather than empty.

The option list is hidden while results are up and the option text moves into the bars.
Showing both overflows the slide: four options plus four bars plus a verdict plus a
hint does not fit in 720px, and the hint is what gets cut off.

**After any reveal the button becomes "Vote again"** and opens a fresh window on the
same question, clearing the previous bars and labelling the rounds. Peer instruction is
vote, argue, vote again, and the second round is the one that moves people, so it must
not need a page reload. Each round marks itself separately, so the archive shows round
one and round two under the same tag; the change between them is the interesting part.

A mute toggle sits under the timer, and the setting persists.

The effects are **synthesized, not downloaded**: canvas particles and WebAudio
oscillators. The decks are published, so a downloaded sound effect or animated GIF is a
licensing question that original work is not, which is the argument CLAUDE.md section
5b already makes about figures. It also keeps the deck diffable, per section 5.

## The leaderboard

A student who wants to be on the board picks a nickname. The pad prompts for one the
first time it is opened, the name is kept in `localStorage` so it is asked for once,
and **change nickname** in the footer reopens the prompt at any time. Renaming is
retroactive, because the `voter` table is keyed by device rather than by name: a
student who has been `phone_4` all lecture and picks something better at the end
appears under the new name everywhere, including in the archive.

**Skipping stays available, and it is not a second-class path.** The prompt has "or
vote without a nickname" beside the Save button, an anonymous phone votes normally,
its votes are in every bar and every band, and it never appears in the standings. That
was the design constraint the whole feature had to satisfy: the reason the answers are
honest is that nothing traces back to a person, and a board that made anonymity
awkward would trade the honest answers for a game.

### How a score is computed

One point per correct answer, and the tiebreak is the total time over the **correct
answers only**. So a wrong answer costs the point and adds nothing to the clock, which
means attempting a question you are unsure about can only help you. Summing over every
answer would have punished exactly the students who guessed and engaged.

The clock for one question runs from the moment the slide opened the window to the
moment that student's vote row landed, both read off the server. Timing this way rather
than from the phone was a deliberate choice: the pad is always open on a student's
phone, so it has no idea when the projector put a question up, and the projector does.
It means a time includes however long you spent talking over the question before
answering, which is fair in the sense that it is the same for everybody in the room.

Three consequences to know before you rely on it:

- **A question that is never revealed scores nothing**, because the mark that records
  the window is written at reveal. Skipping past a slide costs the room that question.
- **Re-voting inside one window replaces**, so the counted time is the time of the vote
  that counted, not of the first tap.
- **Round two overwrites round one on the same tag**, but a student who was right in
  round one and stayed out of round two keeps the point. Scoring only the final round
  would take back something already earned, purely for staying quiet during the
  argument.

### On the slides

At reveal, a question's panel replaces its QR code with the running top five. The
standings are cumulative for the session rather than per-question, so the board on the
fourth question is the story so far. "The session" is the page load: the first window
a deck opens sets the boundary, which is what keeps the server free of any notion of
lectures, dates, or time zones. `data-top` changes how many names appear and
`data-leaderboard="false"` suppresses the board on one question.

A summary slide for the end of the lecture is one div and needs nothing else:

```html
## Final standings

<div class="clicker-leaderboard"
     data-read="https://clicker.f26-06763.workers.dev"
     data-top="10"
     data-hours="6"
     data-title="Final standings"></div>
```

It redraws every time the slide comes up, and carries a Refresh button for the case
where somebody is still voting while you are talking. Ten rows fit on a slide that
carries nothing else and eight fit under a line of framing text; there is no scrollbar
on a projector to rescue a `data-top` set higher than the slide can hold, so check the
render rather than assuming. `data-hours` is the fallback
lookback for a deck opened straight to its last slide, which has no session boundary
to work from; when the deck has run a question, the session boundary wins.

An empty board says which kind of empty it is, "no scored questions yet" against
"nobody has picked a nickname yet", because a blank box in front of a room reads as
broken rather than empty.

## Reading the results

```bash
python3 tools/clicker.py stats                     # usage overall and per day
python3 tools/clicker.py windows --date today      # what the slides marked
python3 tools/clicker.py questions --date today    # bursts, inferred from gaps
python3 tools/clicker.py show                      # live bars, a backstop for the slide
python3 tools/clicker.py leaderboard --date today  # standings, scored as the room saw them
python3 tools/clicker.py archive l03 --date today  # writes course/clicker/l03.yml
```

`leaderboard` asks the same endpoint the projector asked, so what it prints afterwards
is what the room saw at the end of the lecture. `archive` folds the standings into the
YAML under `standings:`, with nicknames and without device pseudonyms: a nickname is
something a student invented and identifies nobody, which is the premise of the board,
while a device id identifies nobody and is of no use to anybody either.

`archive` prefers the marks, because they are exact and carry the prompt and the
answer, and falls back to gap-detected bursts, telling you which it used. Pass
`--force-bursts` to ignore marks.

Time zones live in the CLI, not the Worker: the Worker takes `from`/`to` in epoch
milliseconds and stays ignorant of dates, which is what lets it be deployed once.

## Working on it

```bash
cd clicker
npm install               # wrangler and marp, pinned
npm run dev               # local; add --remote to hit the real database
npm run deploy
npm run tail              # live request log, genuinely useful during class
npm run slides            # render shakedown.md
npm test                  # the scoring rules, against a fake D1
```

`npm test` drives the real handler out of `worker.js` (its `import` of `vote.html` is
stripped, since node cannot import HTML) against a fake database, so it needs no
wrangler, no network and no D1. It covers the parts of the scoring rule that are easy
to break without noticing: time counted over correct answers only, a round overwriting
its predecessor without taking back an earned point, anonymous voters staying out of
the standings, and the nickname charset. CI runs it in the `quiz` job.

Schema changes go in `schema.sql` and must be applied to **both** databases with
`npm run schema:remote` and `npm run schema:local`.

## Things that will bite you

- **`clicker/vote.html` is exempted in the root `.gitignore`.** The repo has a blanket
  `*.html` rule for rendered output, which silently excluded a *source* file that
  `worker.js` imports, breaking deploys from a fresh clone. `game/index.html` already
  carries a comment about the same trap.
- **A new or renamed hostname has no certificate for a few minutes.** See step 5.
- **The account subdomain cannot be changed through the API**, only the dashboard.
- **Cloudflare's browser-integrity check 403s `Python-urllib`** with error code 1010,
  so `tools/clicker.py` sends a real User-Agent. Anything else scripting these
  endpoints must too.
- **MARP scales slides with a CSS transform**, which defeats coordinate-based clicking
  in Puppeteer. Browser tests must dispatch `element.click()` in-page.
- **A published deck exposes `data-answer` in its page source**, and anyone reading it
  can start a window and vote into the same stream as the room. This deck *is*
  published, at `/f26-06763/slides/clicker/`, which was a deliberate call. If a
  question ever carries weight, strip `data-answer` during the CI render and gate the
  window behind a code shown only on the projector.
- **Clearing site data strands a nickname on the old device id.** The name is held by
  the browser and re-asserted from it, so a student who clears storage comes back as a
  new device and finds their own name taken. Blank the orphaned row and they can claim
  it again:
  ```bash
  wrangler d1 execute clicker --remote \
    --command "DELETE FROM voter WHERE name_key = 'thename'"
  ```
- **A nickname is student-typed and lands on a projector.** The charset is narrow (2 to
  24 characters of letters, digits, space, dot, dash, underscore, ASCII only, at least
  one alphanumeric) and every name is rendered through `textContent`, so nothing typed
  can be markup. None of that stops a name that is merely offensive, which is a
  moderation problem and not a technical one; the command above is also the repair for
  that, and it takes effect on the next read of the board.
- **Running marp from `clicker/` silently drops the theme.** See above.
- Free plan ceilings are 100k requests/day and 100k D1 row writes/day, against roughly
  240 votes per session. There is no realistic path to hitting them.

## What this does not defend against

Nothing here is tamper-proof, and it is not trying to be.

Every route is unauthenticated, because requiring a credential was the one thing ruled
out from the start. So anyone with the URL can vote repeatedly from different browsers,
and anyone can write a `/mark` with any tag. A mark is a claim, not a fact.

That is an acceptable trade because **the clicker is formative and feeds no grade.**
Participation credit still comes from the weekly evidence PDF, which is a different
system with a different threat model. The cost of an abused clicker is a wrong bar on
a slide and a line in an archive that a human can delete.

Votes are anonymous in a real sense: a row is a timestamp, a letter, and a random
string the browser invented. There is nothing to trace, which is also the reason the
answers are honest.

A nickname does not change that, and it is worth being precise about why. The server
stores the name a student typed against the pseudonym their browser invented, and
learns nothing else; there is no roster, no Andrew ID, and no path from a row to a
person that does not run through a student telling you which name is theirs. The pad
says so in as many words, and tells them not to use their name or their Andrew ID.
Whether a nickname is anonymous is then a decision the student makes and can revise,
which is why "change nickname" is in the footer and why skipping it is offered in the
same breath as choosing one.

What a nickname does change is that the board is a place a student can be seen, and
appearing near the bottom of a projected list stings. So: keep it formative, keep it
ungraded, show five names rather than everybody's rank, and leave the anonymous path
as easy as it is now. Attach anything to a position on that board and you trade away
the honest answers this system was built to get.
