---
marp: true
theme: course
paginate: true
header: "06-763 · clicker"
footer: "Systems and Toolchains for AI Engineers"
---

<!-- _class: title -->

# Five minutes on the clicker

## A dry run, and two questions for you

**Systems and Toolchains for AI Engineers**

<!--
Four questions, about five minutes. The point is to find out whether this survives
30-odd real phones on real campus wifi before anything depends on it.

Question 3 is the one that matters: it is rigged to fail, then you let them argue
and press "Vote again", and it comes back as a win. That single question shows both
outcomes, which is why the separate rigged-win question was cut.

Four more spare questions sit after the closing slide if the room is fast.
Everything is anonymous and nothing is graded.
-->

---

## How it works

<div class="clicker" data-seconds="45" data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

Scan the code, or type the address. It is the **same link all semester**, so
bookmark it.

Your phone shows four buttons and nothing else. The question stays up here.

Tapped the wrong one? **Tap another.** Only your last answer counts.

A vote is a timestamp, a letter, and a random nickname your browser invents.
Nothing identifies you, and none of it is graded.

</div>
<aside class="clicker-panel">
<img src="figures/clicker-qr.png" alt="QR code linking to the vote page">
<div class="clicker-url">clicker.f26-06763.workers.dev</div>
</aside>
</div>

<!--
Leave this up while people get to the page. Say the URL out loud once; some
cameras will not focus from the back of the room.
-->

---

## Warm-up, does it reach you

<div class="clicker" data-tag="shakedown-warmup" data-seconds="60" data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

<ol class="clicker-opts">
<li>Scanned the QR code</li>
<li>Typed the address by hand</li>
<li>A neighbour showed me</li>
<li>Took a while, but I am in</li>
</ol>

</div>
<aside class="clicker-panel">
<img src="figures/clicker-qr.png" alt="QR code linking to the vote page">
<div class="clicker-url">clicker.f26-06763.workers.dev</div>
<button class="clicker-start">Start voting</button>
<div class="clicker-timer">60</div>
<div class="clicker-count">no votes yet</div>
</aside>
</div>

<!--
The real measurement is the vote COUNT, not the breakdown: compare it to the
number of heads in the room. Anyone who could not load the page cannot answer
this question, so the count is the only thing that detects them. Ask for a show
of hands from anyone who got nowhere and count those separately.
-->

---

## Changing your mind

<div class="clicker" data-tag="shakedown-change-my-mind" data-seconds="45" data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**Tap A. Then change your answer to D.**

If this works, the bars should show everyone on D and nobody on A.

<ol class="clicker-opts">
<li>Tap this one first</li>
<li>Not used</li>
<li>Not used</li>
<li>Then tap this one</li>
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

<!--
A real test: re-voting REPLACES rather than adds. If any A survives, some device
is not being recognised between taps, which usually means storage is blocked in
that browser. The next question leans on them remembering this one.
-->

---

## Now one that will not go well

<div class="clicker" data-tag="shakedown-rigged-miss" data-seconds="45" data-answer="C" data-hint="You ran this experiment on the last question. What happened to the A you tapped before you switched to D?" data-why="Your browser sends a random nickname with every tap, and the tally keeps only the most recent vote from each device inside the question's window. Changing your mind replaces your answer instead of adding a second one." data-read="https://clicker.f26-06763.workers.dev">
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

<!--
THE ONE THAT MATTERS. B is wrong, so this lands under 30%, the rain comes down,
and the hint appears.

THEN: 30 seconds to argue, and press 'Vote again'. The same question opens a
fresh window and should come back as fireworks, with the explanation. That loop,
vote badly, argue, vote again, is the whole reason for doing this rather than
asking for a show of hands. It also demonstrates both outcomes in one question.

B is a genuine misconception: plenty of systems do count the first response.
Worth saying so rather than treating it as a silly mistake.
-->

---

## A leaderboard, maybe

<div class="clicker" data-tag="shakedown-leaderboard" data-seconds="45" data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

You would invent a nickname, and your browser would remember it. Nobody, including me, would know whose is whose.

<ol class="clicker-opts">
<li>Yes, that sounds fun</li>
<li>Only if it stays optional</li>
<li>No thanks</li>
<li>No strong feeling</li>
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

<!--
Right now nothing at all is attached to a vote. A leaderboard needs something
durable to attach a score to, which is why the nickname is in the question
rather than a footnote. You would type it once and the browser would keep it,
per browser, so a new phone means typing it again. It stays a name you invent,
never your Andrew ID, and I would not be able to map it back to you.
-->

---

## That is the dry run

Thanks. The results set the defaults, rather than me guessing them.

The link is the same every class: **clicker.f26-06763.workers.dev**

Nothing here was graded, and nothing was recorded about who you are.

<!--
If the warm-up count came in well under the room count, chase that before using this
for anything that matters. Spare questions follow if there is time.
-->

---

<!-- _class: section -->

# Spares, if there is time

<!--
Everything past here is optional. Stop at the slide above if the room is done.
-->

---

## A rigged one, so you can see a win

<div class="clicker" data-tag="shakedown-rigged-win" data-seconds="45" data-answer="A" data-why="Your phone is deliberately dumb: four buttons and nothing else. That is what keeps every upcoming question off every student's device, and it is why one QR code works for the whole semester." data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

Rigged on purpose. **Everyone tap A.** Where does the question itself appear?

<ol class="clicker-opts">
<li>On the screen at the front</li>
<li>On my phone</li>
<li>In an email before class</li>
<li>Somewhere in the syllabus</li>
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

<!--
A guaranteed win on its own, if question 3 did not already give you one.
-->

---

## Same letter, no talking

<div class="clicker" data-tag="shakedown-same-letter" data-seconds="45" data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**Without saying anything, try to make the whole room pick the same letter.**

No right answer. Either we converge or we do not.

<ol class="clicker-opts">
<li>A</li>
<li>B</li>
<li>C</li>
<li>D</li>
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

<!--
Pure fun, and a free illustration of consensus with no coordination channel.
Most rooms pile onto A. Flat bars are the more interesting result.
-->

---

## How long is long enough

<div class="clicker" data-tag="shakedown-how-long" data-seconds="45" data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

A minute is the default. It is easy to change.

<ol class="clicker-opts">
<li>Too short, I was rushed</li>
<li>About right</li>
<li>Too long, it dragged</li>
<li>Depends on the question</li>
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

---

## How often

<div class="clicker" data-tag="shakedown-how-often" data-seconds="45" data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

<ol class="clicker-opts">
<li>One or two per class</li>
<li>Three or four per class</li>
<li>Five or more, keep me awake</li>
<li>None, I would rather not</li>
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

---

<script src="clicker-slide.js"></script>
