# The arcade

One-minute minigames over the quiz banks. A round is sixty seconds, produces a
score, and lands on a leaderboard.

| game | asks | fed by |
|---|---|---|
| **Whack-a-Bug** | is this claim true? | an item's `options` |
| **Pipeline Panic** | what order do these go in? | an item's `sequence` |
| **Concept Chase** | which of these words belong? | an item's `terms` |
| **Ship It** | which tool for each layer, and what breaks? | an item's `stack` |
| **Boss Rush** | who is best across all of them? | the per-game boards |

The first three ask what you remember. **Ship It** asks you to make an
engineering decision and then live with it, which the multiple-choice format
cannot do at all. It runs 90 seconds rather than 60 — eight layers to fill and a
report worth reading — and that costs nothing across games because Boss Rush
ranks by placing rather than score.

It fills the gap between the two things the course already had. The clicker is
live and social and scored, but the only verb is *tap one of four letters*. The
practice modules in `game/` are deep and per-student and produce the evidence
PDF, but they deliberately have no score and take rather longer than a minute.
There was nothing in between: nothing a student plays in the time it takes to
settle into a seat, and immediately sees themselves ranked in.

Nothing here is graded. The 15% participation mark stays with the MAC'd evidence
PDF, and the reason is in [Scores are claims](#scores-are-claims).

## Using one

In a MARP slide or an MyST notes page, identically:

```html
<div class="arcade" data-game="whackabug" data-lecture="l03"
     data-seconds="60" data-board="live"
     data-read="https://clicker.f26-06763.workers.dev"></div>

<script src=".../arcade/arcade.js"></script>
<script src=".../arcade/games/whackabug.js"></script>
```

| attribute | |
|---|---|
| `data-read` | the Worker's base URL. Required. |
| `data-game` | which game, by its `Arcade.register` id. Required. |
| `data-lecture` | `lNN`, or `all` for every published lecture. Picks `rounds/<x>.json`. Required. |
| `data-seconds` | round length, default the game's own, usually 60 |
| `data-board` | `live` (a six-hour rolling window) or `all` (the semester) |
| `data-top` | how many names to show, default 8 |
| `data-rounds` | override the round file URL; normally leave it alone |

`live` in the hall and `all` in the notes is the right split: in class you are
racing the room, alone you are racing the semester.

`data-lecture="all"` is what an ordering game wants: one lecture carries at most
a couple of sequences, which is fifteen seconds of play rather than sixty.

**Boss Rush** is a board rather than a game, so it takes a different element and
needs no run:

```html
<div class="arcade-rush" data-read="..."
     data-games="l03-whackabug,all-pipeline,l01-chase" data-top="10"></div>
```

It ranks by **placing** — 10, 8, 6, then 5 4 3 2 1, and 1 for anything after
that — summed across games and tie-broken on games played. Ranking on raw score
would not work: Concept Chase pays out two hundred a run and Pipeline Panic pays
thirty, so a score-ranked rush is a Concept Chase ladder with decoration. It
aggregates in the browser, which is why it needed no server change.

Both `arcade.css` and `rounds/` are found relative to `arcade.js` itself, so a
page never has to say where they are and can never say it wrong.

## Content comes from the quiz bank

There is no arcade content and there must not be. A game is a *renderer* over
`game/content/lNN.yml`, so the bank stays the one place a claim about this course
is written down and `game/validate.py` stays the one thing that checks a claim
against the notes.

```
python tools/arcade_rounds.py           # every published bank -> arcade/rounds/
python tools/arcade_rounds.py --check   # CI: rebuild and diff, never write
```

Published banks only. A lecture that has not been released cannot be played, so
an unfinished bank cannot leak out through a slide.

Regenerate and commit `arcade/rounds/*.json` whenever a bank changes. An item is
skipped, loudly, if an option runs past 180 characters — a claim nobody can read
while it moves is a claim the player has to guess at, and shortening it is the
author's call rather than this tool's.

## Adding a game

A game is one file and one call. The shell owns identity, the clock, the round
protocol, the submit and the board; a game owns its sixty seconds of pixels.

```js
Arcade.register('whackabug', {
  seconds: 60,
  // Which items this game can render. A round file carries all three shapes and
  // no item has all of them, so a game handed nothing fails out loud in the
  // shell rather than mounting a blank stage that reads as broken.
  pick: function (items) { return items.filter(function (i) { return i['true'] }) },
  mount: function (root, ctx) {
    // ctx = { items, rng, seconds, markdown, score(n), record(entry), end() }
    return { stop: function () { /* put your timers down */ } }
  },
})
```

`ctx` carries nothing about the server on purpose. A game that could reach the
network could also decide what it scored without telling the shell, and then no
two games would agree on what a point was.

Two things a game must do: honour `prefers-reduced-motion`, and be playable from
the keyboard. `MapView` in `game/` chose DOM over canvas for the same reason.

## Scores are claims

The clicker's leaderboard is unusually hard to forge, because both of its inputs
belong to the server: correctness comes from a mark written at reveal, and
timing is `vote.ts - window.from_ts`. An arcade score does not have that
property. The game runs in the student's own tab, so the number that arrives is
asserted, exactly as a `/mark` is asserted.

What is done about it:

- **The server owns the clock.** `/start` and `/submit` are both stamped here,
  so a duration cannot be shortened, and consuming the run row on submit means a
  run cannot be replayed.
- **The transcript is kept.** `detail` records which claims came up and what was
  picked. Nothing reads it live; it makes an implausible run reviewable, and it
  means a server-graded mode could be added later without a migration.
- **It is said out loud.** The arcade is formative and feeds no grade, so the
  cost of a bogus run is a row a human can delete. This is the same bargain
  `worker.js` already documents for `/mark`.

The round order is seeded by the run id the server minted, so a run can be
replayed exactly from its transcript. That is the only reason the transcript is
worth keeping.

## Running it locally

```
cd clicker && npx wrangler d1 execute clicker --local --file schema.sql
cd clicker && npx wrangler dev --local          # the Worker on :8787
python3 -m http.server 8080                     # from the repository root
```

Then open <http://127.0.0.1:8080/arcade/local.html>. Opening the file directly
as `file://` will not work, because the round file is fetched.

The server routes are `/start`, `/submit`, `/board` and `/me`, documented in
`clicker/worker.js` and tested in `clicker/test/arcade.test.mjs` (`npm test` in
`clicker/`). The Boss Rush placing rule and Ship It's deploy evaluation are tested
separately, without a browser, by `node --test "arcade/test/*.test.mjs"`. Deploying is the clicker's deploy: `npm run deploy`, and
`npm run schema:remote` for the two new tables. Forgetting `--remote` is the
classic D1 mistake and the Worker will tell you so.
