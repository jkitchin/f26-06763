/* Pipeline Panic: sixty seconds of getting things in the right order.
 *
 * The steps of a process arrive shuffled. Click them in order. Three lives.
 *
 * This is the only game in the arcade that tests ORDER, and order is the thing
 * the multiple-choice format structurally cannot ask about: an MCQ can ask
 * which step comes third, but only by naming the other steps in the question,
 * which is most of the answer. So a sequence is worth its own key in the bank
 * and its own game here.
 *
 * Clicking rather than dragging, deliberately. Drag-and-drop is poor on a
 * phone, effectively unusable from a keyboard, and slow even with a mouse --
 * and what is being tested is whether you know the order, not whether you can
 * drag. Number keys pick too, so the whole game is playable without a pointer.
 *
 * Scoring:
 *
 *     right   25, plus a streak bonus and a bonus for deciding early
 *     wrong   nothing, and a life
 *
 * As in Whack-a-Bug, no answer ever costs points, so being unsure never makes
 * silence the better play.
 */
(function () {
  'use strict';

  var LIVES = 3;
  // A step is a short phrase rather than a claim, so it reads faster than a
  // Whack-a-Bug chip and the clock can be tighter per decision.
  var BASE_MS = 6000;
  var STEP_MS = 150;
  var FLOOR_MS = 3000;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  Arcade.register('pipeline', {
    seconds: 60,

    pick: function (items) {
      return items.filter(function (i) {
        return i.sequence && i.sequence.steps && i.sequence.steps.length >= 3;
      });
    },

    mount: function (root, ctx) {
      var queue = ctx.items;
      var qi = -1, score = 0, streak = 0, lives = LIVES;
      var current = null, want = 0, startedAt = 0, dur = BASE_MS;
      var raf = null, done = false, decided = 0;
      var wrong = [];

      root.textContent = '';
      root.classList.add('pipe');

      var promptEl = el('div', 'pipe-prompt');
      var chain = el('ol', 'pipe-chain');
      var bar = el('div', 'pipe-bar');
      var fill = el('i', 'pipe-fill');
      bar.appendChild(fill);
      var livesEl = el('div', 'pipe-lives');
      var tray = el('div', 'pipe-tray');

      root.appendChild(promptEl);
      root.appendChild(livesEl);
      root.appendChild(chain);
      root.appendChild(bar);
      root.appendChild(tray);

      function paintLives() {
        livesEl.textContent = '';
        for (var k = 0; k < LIVES; k++) {
          livesEl.appendChild(el('span', 'pipe-life' + (k < lives ? '' : ' is-gone'), '●'));
        }
      }

      function stop() {
        done = true;
        if (raf) { cancelAnimationFrame(raf); raf = null; }
        window.removeEventListener('keydown', onKey, true);
      }

      // What you got out of order, and why the order is what it is. The
      // sequence's own `why` is written for exactly this moment -- the L01 one
      // spends it saying the list is NOT linear, which is the thing the notes
      // most want unlearned.
      function summarise() {
        tray.hidden = true;
        bar.hidden = true;
        chain.hidden = true;
        promptEl.hidden = true;
        var box = el('div', 'pipe-summary');
        box.appendChild(el('h4', null, wrong.length ? 'Worth a second look' : 'Nothing out of order.'));
        var seen = {};
        wrong.forEach(function (w) {
          if (seen[w.id]) return;
          seen[w.id] = 1;
          var d = el('div', 'pipe-missed');
          d.appendChild(el('p', 'pipe-missed-order', w.steps.join('  →  ')));
          if (w.why) {
            var why = el('div', 'pipe-missed-why');
            ctx.markdown(why, w.why);
            d.appendChild(why);
          }
          box.appendChild(d);
        });
        root.appendChild(box);
      }

      function over() {
        if (done) return;
        stop();
        summarise();
        ctx.end();
      }

      function nextSequence() {
        if (done) return;
        qi += 1;
        if (qi >= queue.length) return over();   // ran out of bank before time

        current = queue[qi];
        want = 0;
        ctx.markdown(promptEl, current.sequence.prompt || 'Put these in order.');
        chain.textContent = '';
        tray.textContent = '';

        // The tray is shuffled with the run's own seeded rng, so the order a
        // player saw is reconstructable from the run id in the transcript.
        var steps = current.sequence.steps.slice();
        var order = steps.map(function (_, i) { return i; });
        for (var i = order.length - 1; i > 0; i--) {
          var j = Math.floor(ctx.rng() * (i + 1));
          var t = order[i]; order[i] = order[j]; order[j] = t;
        }
        order.forEach(function (idx, slot) {
          var b = el('button', 'pipe-step');
          b.type = 'button';
          b.dataset.idx = idx;
          b.appendChild(el('span', 'pipe-num', String(slot + 1)));
          b.appendChild(el('span', 'pipe-text', steps[idx]));
          b.addEventListener('click', function () { choose(b); });
          tray.appendChild(b);
        });

        dur = Math.max(FLOOR_MS, BASE_MS - STEP_MS * decided);
        startedAt = performance.now();
        if (raf) cancelAnimationFrame(raf);
        raf = requestAnimationFrame(tick);
      }

      function tick(now) {
        if (done) return;
        var t = Math.min(1, (now - startedAt) / dur);
        fill.style.width = (100 - 100 * t) + '%';
        if (t >= 1) return judge(null);
        raf = requestAnimationFrame(tick);
      }

      function choose(btn) {
        if (done || btn.disabled) return;
        judge(parseInt(btn.dataset.idx, 10), btn);
      }

      function judge(idx, btn) {
        if (done || !current) return;
        var elapsed = performance.now() - startedAt;
        var right = idx === want;

        ctx.record({ id: current.id, want: want, got: idx, ms: Math.round(elapsed) });
        decided += 1;

        if (right) {
          streak += 1;
          var speed = Math.round(10 * Math.max(0, 1 - elapsed / dur));
          score += 25 + Math.min(streak, 5) + speed;
          ctx.score(score);

          var li = el('li', 'pipe-locked', current.sequence.steps[idx]);
          chain.appendChild(li);
          if (btn) { btn.disabled = true; btn.classList.add('is-used'); }

          want += 1;
          if (want >= current.sequence.steps.length) {
            // Whole sequence placed. Take a breath, then the next process.
            if (raf) { cancelAnimationFrame(raf); raf = null; }
            return setTimeout(nextSequence, 500);
          }
          // The clock restarts per step rather than per sequence, so a long
          // process is not automatically harder than a short one.
          dur = Math.max(FLOOR_MS, BASE_MS - STEP_MS * decided);
          startedAt = performance.now();
          return;
        }

        streak = 0;
        lives -= 1;
        paintLives();
        wrong.push({ id: current.id, steps: current.sequence.steps, why: current.sequence.why });
        if (btn) {
          btn.classList.add('is-wrong');
          setTimeout(function () { btn.classList.remove('is-wrong'); }, 400);
        }
        if (raf) { cancelAnimationFrame(raf); raf = null; }
        if (lives <= 0) return setTimeout(over, 450);
        // A missed step moves on rather than stalling on a process the player
        // has already shown they do not know.
        setTimeout(nextSequence, 450);
      }

      // Captured, for the reason Whack-a-Bug documents: a MARP deck steers on
      // the arrow keys and would otherwise advance out from under a run.
      // Digits are not deck controls, but capturing them keeps the two games
      // behaving the same way.
      function onKey(e) {
        if (done || !current) return;
        var n = parseInt(e.key, 10);
        if (!n || n < 1) return;
        var btn = tray.children[n - 1];
        if (!btn || btn.disabled) return;
        e.preventDefault();
        e.stopPropagation();
        choose(btn);
      }

      window.addEventListener('keydown', onKey, true);
      paintLives();
      nextSequence();

      return { stop: stop };
    },
  });
})();
