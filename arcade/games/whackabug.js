/* Whack-a-Bug: sixty seconds of code review.
 *
 * A claim about the pinned snippet rises up the lane. Ship it or call it a bug
 * before it reaches the top. Three lives.
 *
 * The content is the quiz bank, unchanged and unwritten-for: an item's `answer`
 * is a true claim and every distractor beside it is a false one, which is what
 * the multiple-choice format already asserts. So this game costs no authoring,
 * and an author who wants a better claim edits the YAML.
 *
 * Why a binary judgement rather than a four-option one, when the bank is four
 * options: picking the best of four teaches elimination, and elimination is
 * exactly the skill that does not transfer to a pull request. A claim on its
 * own has to be judged on its own, which is the thing the course actually wants
 * and the thing an MCQ cannot ask for.
 *
 * Scoring, and the shape of it matters more than the numbers:
 *
 *     right   20, plus a streak bonus and a bonus for deciding early
 *     wrong   nothing, and a life
 *     missed  nothing, and a life
 *
 * No answer ever costs points. A player who is unsure is choosing between two
 * ways to lose a life and can pick the one they believe, rather than working
 * out whether a guess is worth less than a shrug. It is the same reason the
 * clicker accumulates time only on correct answers.
 */
(function () {
  'use strict';

  var LIVES = 3;
  var BASE_MS = 5200;      // how long the first claim has to cross the lane
  var STEP_MS = 140;       // and how much less each one after it gets
  var FLOOR_MS = 2400;

  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // Every item contributes its true claim and its false ones as separate
  // judgements, kept together so the pinned context changes only between items
  // rather than under a claim the player is still reading.
  function deal(items, rng) {
    var out = [];
    items.forEach(function (item) {
      var claims = [{ text: item['true'], bug: false }];
      (item['false'] || []).forEach(function (t) { claims.push({ text: t, bug: true }); });
      // Fisher-Yates on the item's own claims, so "the true one is first" is
      // never a pattern to learn instead of the material.
      for (var i = claims.length - 1; i > 0; i--) {
        var j = Math.floor(rng() * (i + 1));
        var t = claims[i]; claims[i] = claims[j]; claims[j] = t;
      }
      claims.forEach(function (c) {
        out.push({ id: item.id, context: item.context, why: item.why, text: c.text, bug: c.bug });
      });
    });
    return out;
  }

  Arcade.register('whackabug', {
    seconds: 60,

    // Round files also carry sequence-only and terms-only items now, and an
    // item with no claims has nothing for this game to float up the lane.
    pick: function (items) {
      return items.filter(function (i) {
        return i['true'] && i['false'] && i['false'].length;
      });
    },

    mount: function (root, ctx) {
      var queue = deal(ctx.items, ctx.rng);
      var i = -1, score = 0, streak = 0, lives = LIVES;
      var startedAt = 0, dur = BASE_MS, raf = null, done = false, travel = 0;
      var current = null;
      var wrong = [];

      root.textContent = '';
      root.classList.add('wab');

      var contextEl = el('div', 'wab-context');
      var lane = el('div', 'wab-lane');
      var chip = el('div', 'wab-chip');
      var bar = el('i', 'wab-bar');
      lane.appendChild(chip);
      lane.appendChild(bar);

      var livesEl = el('div', 'wab-lives');
      var controls = el('div', 'wab-controls');
      var bugBtn = el('button', 'wab-btn is-bug', 'Bug');
      var shipBtn = el('button', 'wab-btn is-ship', 'Ship it');
      bugBtn.type = shipBtn.type = 'button';
      // The keys are on the buttons rather than in a legend nobody reads.
      bugBtn.appendChild(el('kbd', null, '←'));
      shipBtn.appendChild(el('kbd', null, '→'));
      controls.appendChild(bugBtn);
      controls.appendChild(shipBtn);

      root.appendChild(contextEl);
      root.appendChild(livesEl);
      root.appendChild(lane);
      root.appendChild(controls);

      function paintLives() {
        livesEl.textContent = '';
        for (var k = 0; k < LIVES; k++) {
          livesEl.appendChild(el('span', 'wab-life' + (k < lives ? '' : ' is-gone'), '●'));
        }
      }

      function stop() {
        done = true;
        if (raf) { cancelAnimationFrame(raf); raf = null; }
        window.removeEventListener('keydown', onKey, true);
        bugBtn.disabled = shipBtn.disabled = true;
      }

      // What you got wrong, and why, from the bank's own evidence. A game that
      // only says "wrong" teaches nobody, including whoever guessed right.
      function summarise() {
        lane.hidden = true;
        controls.hidden = true;
        contextEl.hidden = true;
        livesEl.hidden = true;

        var box = el('div', 'wab-summary');
        box.appendChild(el('h4', null, wrong.length ? 'Worth a second look' : 'Nothing missed.'));

        // Grouped by item, because a run usually ends by losing every life on
        // ONE snippet, and printing that snippet's evidence three times reads
        // as a bug and buries the thing worth reading.
        var byItem = [];
        var seen = {};
        wrong.forEach(function (w) {
          if (!seen[w.id]) {
            seen[w.id] = { id: w.id, why: w.why, claims: [] };
            byItem.push(seen[w.id]);
          }
          seen[w.id].claims.push(w.text);
        });

        byItem.slice(0, 3).forEach(function (item) {
          var d = el('div', 'wab-missed');
          item.claims.forEach(function (text) {
            d.appendChild(el('p', 'wab-missed-claim', text));
          });
          if (item.why) {
            var why = el('div', 'wab-missed-why');
            ctx.markdown(why, item.why);
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

      function next() {
        if (done) return;
        i += 1;
        if (i >= queue.length) return over();   // ran out of bank before time

        current = queue[i];
        if (i === 0 || queue[i - 1].id !== current.id) {
          ctx.markdown(contextEl, current.context);
        }
        chip.textContent = current.text;
        chip.className = 'wab-chip';
        // In pixels, measured after the text is in: a percentage translate is
        // relative to the CHIP's own height, so a long claim would crawl and a
        // short one would fly. The lane is the deadline, so the lane is what
        // has to be crossed.
        travel = Math.max(0, lane.clientHeight - chip.offsetHeight);
        chip.style.transform = 'translateY(' + travel + 'px)';
        dur = Math.max(FLOOR_MS, BASE_MS - STEP_MS * i);
        startedAt = performance.now();

        if (raf) cancelAnimationFrame(raf);
        raf = requestAnimationFrame(step);
      }

      function step(now) {
        if (done) return;
        var t = Math.min(1, (now - startedAt) / dur);
        // Reduced motion gets a draining bar and a chip that holds still. The
        // deadline is the same; only the thing that moves is different.
        if (!reduced) chip.style.transform = 'translateY(' + travel * (1 - t) + 'px)';
        bar.style.width = (100 - 100 * t) + '%';
        if (t >= 1) return judge(null);
        raf = requestAnimationFrame(step);
      }

      function judge(saidBug) {
        if (done || !current) return;
        var elapsed = performance.now() - startedAt;
        var right = saidBug !== null && saidBug === current.bug;

        ctx.record({ id: current.id, bug: current.bug, said: saidBug, ms: Math.round(elapsed) });

        if (right) {
          streak += 1;
          // Deciding early is worth something, but never more than being right:
          // the base is 20 and the two bonuses together cap well under it.
          var speed = Math.round(10 * Math.max(0, 1 - elapsed / dur));
          score += 20 + Math.min(streak, 5) + speed;
          ctx.score(score);
          chip.classList.add('is-right');
        } else {
          streak = 0;
          lives -= 1;
          paintLives();
          wrong.push(current);
          chip.classList.add(saidBug === null ? 'is-missed' : 'is-wrong');
        }

        current = null;
        if (raf) { cancelAnimationFrame(raf); raf = null; }
        if (lives <= 0) return setTimeout(over, 450);
        setTimeout(next, 260);
      }

      // Captured rather than bubbled, and stopped rather than merely
      // default-prevented, because a MARP deck is a bespoke viewer that steers
      // on the arrow keys: its own handler sits on the document and would
      // otherwise advance the slide out from under a run before this one ever
      // saw the key. Only a live claim swallows the arrows, so a presenter can
      // still walk the deck whenever nothing is rising.
      function onKey(e) {
        if (done || !current) return;
        var bug = e.key === 'ArrowLeft' || e.key === 'a';
        var ship = e.key === 'ArrowRight' || e.key === 'd';
        if (!bug && !ship) return;
        e.preventDefault();
        e.stopPropagation();
        judge(bug);
      }

      bugBtn.addEventListener('click', function () { judge(true); });
      shipBtn.addEventListener('click', function () { judge(false); });
      window.addEventListener('keydown', onKey, true);

      paintLives();
      next();

      // The shell stops a run when the slide leaves the screen, so a game must
      // be able to put its own timers down on request.
      return { stop: stop };
    },
  });
})();
