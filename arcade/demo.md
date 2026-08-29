---
marp: true
theme: course
paginate: true
header: "06-763 · arcade"
footer: "Systems and Toolchains for AI Engineers"
---

<!-- _class: title -->

# One minute on the arcade

## Whack-a-Bug, over the L03 bank

**Systems and Toolchains for AI Engineers**

<!--
The same shape as the clicker and the same nickname: a student who has voted
this semester is already on this board under the name they invented.

Sixty seconds, three lives. A claim about the pinned snippet rises; ship it or
call it a bug. Nothing here is graded, and the pad says so on the slide.

Run it once as a warm-up at the top of a lecture, and once at the end. The
second run is the interesting one.
-->

---

## How it works

- A claim about the snippet **rises up the lane**. Judge it before it lands.
- **←** or **Bug** if it is false. **→** or **Ship it** if it is true.
- Three lives. A wrong call and a missed one cost the same.
- Right answers score; **no answer ever costs points**, so believe yourself.

The claims are the quiz bank, unchanged. If one of them is wrong, that is a bug
in the notes and worth more than the point.

---

## Whack-a-Bug · L03

<div class="arcade" data-game="whackabug" data-lecture="l03"
     data-seconds="60" data-board="live" data-top="6"
     data-read="https://clicker.f26-06763.workers.dev"></div>

<!--
data-board="live" is the six-hour rolling window: in the hall you are racing the
room, not the semester. The notes page uses data-board="all" instead.
-->

---

## Where you stand this semester

<div class="arcade" data-game="whackabug" data-lecture="l03"
     data-seconds="60" data-board="all" data-top="10"
     data-read="https://clicker.f26-06763.workers.dev"></div>

<!--
Same game, same board key, a different window. Ranked by each player's best run
rather than by how often they played, so grinding it does not climb it.
-->

---

## Pipeline Panic · every published lecture

<div class="arcade" data-game="pipeline" data-lecture="all"
     data-seconds="60" data-board="live" data-top="6"
     data-read="https://clicker.f26-06763.workers.dev"></div>

<!--
data-lecture="all" rather than one lecture: a single lecture carries at most a
couple of sequences, which is fifteen seconds of play.

This is the only game here that tests ORDER. An MCQ can ask which step comes
third, but only by listing the other steps in the question, which is most of the
answer. That is why a sequence is worth its own key in the bank.
-->

---

## Concept Chase · L01

<div class="arcade" data-game="chase" data-lecture="l01"
     data-seconds="60" data-board="live" data-top="6"
     data-read="https://clicker.f26-06763.workers.dev"></div>

<!--
Eat the terms that belong to the category. The ghosts are eating the right ones
too, so the board empties whether or not you are quick: left alone they clear it
in about forty seconds. Wrong pellets cost points here, unlike the other two
games, because avoiding one is the skill being tested.

Every correct term appears in this lecture's notes and no wrong one does. The
round generator refuses to build a file where that is not true.
-->

---

## Boss Rush

<div class="arcade-rush" data-read="https://clicker.f26-06763.workers.dev"
     data-games="l03-whackabug,all-pipeline,l01-chase" data-top="10"></div>

<!--
Points by placing rather than by score: 10, 8, 6, then 5 4 3 2 1, and 1 for
anything after that. Concept Chase pays out two hundred a run and Pipeline Panic
pays thirty, so a board ranked on raw score would be a Concept Chase ladder with
decoration. Where you came carries across games; what the formula paid does not.
-->

---

<script src="arcade.js"></script>
<script src="games/whackabug.js"></script>
<script src="games/pipeline.js"></script>
<script src="games/chase.js"></script>
<script src="games/bossrush.js"></script>
