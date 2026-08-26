/* Drives every .clicker element on a MARP deck.
 *
 * Include once per deck, after the slides:
 *     <script src="clicker-slide.js"></script>
 *
 * Markup per question:
 *     <div class="clicker" data-seconds="60" data-answer="B"
 *          data-read="https://clicker.f26-06763.workers.dev">
 *       <div class="clicker-main"><ol class="clicker-opts">...</ol></div>
 *       <aside class="clicker-panel">... .clicker-start .clicker-timer .clicker-count ...</aside>
 *     </div>
 *
 * data-answer is optional; omit it for an opinion poll, which then reveals bars
 * with no verdict and no effects.
 *
 * data-hint is optional too, and appears only when the room did NOT sail through:
 * on the discuss band and the re-teach band. It is the nudge that makes a second
 * vote worth taking, so keep it a pointer rather than the answer.
 *
 * data-why is its complement, shown only when the room got there. Celebrating
 * without saying why the answer is the answer teaches nobody, including the people
 * who guessed. It plays the same role as the `evidence` field in the quiz banks.
 *
 * Voting opens by itself when the slide comes up, so the presenter does not have to
 * remember to press anything. data-autostart="false" opts a question out. Coming
 * back to a slide does NOT reopen it: that would start a second window and throw
 * away the first one's result.
 *
 * After a reveal the button becomes "Vote again" and opens a fresh window on the
 * same question. Peer instruction is vote, argue, vote again, so the second round
 * has to be one click away.
 *
 * data-tag, if present, makes the slide record its own window when voting closes:
 * the tag, the exact boundaries, the round, and the prompt and answer. The archive
 * then knows which votes belonged to which question instead of inferring it from
 * gaps. The server stores those as opaque strings and never interprets them, so it
 * stays question-agnostic; the mark is written after the fact and is never consulted
 * while voting is open.
 *
 * Two rules the classroom depends on:
 *   - the distribution stays hidden while voting is open, because showing it
 *     biases whoever has not voted yet. Only the count moves.
 *   - the window is CLOSED, [start, start+seconds], and both ends come from the
 *     server's clock. A projector whose clock drifts would otherwise silently
 *     mis-slice every question.
 *
 * The correct answer lives here on the slide and is never sent to the server.
 * That is what lets the server stay question-agnostic and deployed-once.
 */
(function () {
  'use strict';

  var LETTERS = ['A', 'B', 'C', 'D'];
  var MUTE_KEY = 'f26-06763-clicker/mute';

  // Mazur's peer instruction bands. The middle one is the whole point: it is
  // where discussion changes minds, so it prompts an action instead of a verdict.
  function band(pct) {
    if (pct > 70) return { key: 'good', text: 'Nicely done. Moving on.' };
    if (pct >= 30) return { key: 'mixed', text: 'Turn to your neighbour and convince them. Then we vote again.' };
    return { key: 'poor', text: 'That one is on me. Let us take it again.' };
  }

  /* ---- sound ---------------------------------------------------------- */
  /* Synthesized rather than sampled: the decks are published, so a downloaded
   * sound effect is a licensing question that an oscillator is not. */

  var actx = null;
  function audio() {
    if (actx) return actx;
    var C = window.AudioContext || window.webkitAudioContext;
    if (!C) return null;
    actx = new C();
    return actx;
  }
  function muted() { try { return localStorage.getItem(MUTE_KEY) === '1'; } catch (e) { return false; } }
  function setMuted(v) { try { localStorage.setItem(MUTE_KEY, v ? '1' : '0'); } catch (e) {} }

  function boom(ctx, at) {
    // A short noise burst through a falling band-pass: a crackle, not a beep.
    var dur = 0.5;
    var buf = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
    var d = buf.getChannelData(0);
    for (var i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
    var src = ctx.createBufferSource(); src.buffer = buf;
    var bp = ctx.createBiquadFilter(); bp.type = 'bandpass';
    bp.frequency.setValueAtTime(2200, at);
    bp.frequency.exponentialRampToValueAtTime(320, at + dur);
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.22, at);
    g.gain.exponentialRampToValueAtTime(0.001, at + dur);
    src.connect(bp).connect(g).connect(ctx.destination);
    src.start(at); src.stop(at + dur);
  }

  function whistle(ctx, at) {
    var o = ctx.createOscillator(); o.type = 'sine';
    o.frequency.setValueAtTime(420, at);
    o.frequency.exponentialRampToValueAtTime(1500, at + 0.45);
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, at);
    g.gain.exponentialRampToValueAtTime(0.05, at + 0.1);
    g.gain.exponentialRampToValueAtTime(0.0001, at + 0.5);
    o.connect(g).connect(ctx.destination);
    o.start(at); o.stop(at + 0.5);
  }

  function downpour(ctx, at, dur) {
    // Pink-ish noise under a low-pass, which is what rain mostly is.
    var buf = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
    var d = buf.getChannelData(0), last = 0;
    for (var i = 0; i < d.length; i++) {
      var w = Math.random() * 2 - 1;
      last = (last + 0.02 * w) / 1.02;
      d[i] = last * 3.5;
    }
    var src = ctx.createBufferSource(); src.buffer = buf;
    var lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 1400;
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, at);
    g.gain.linearRampToValueAtTime(0.18, at + 0.3);
    g.gain.setValueAtTime(0.18, at + dur - 0.6);
    g.gain.linearRampToValueAtTime(0.0001, at + dur);
    src.connect(lp).connect(g).connect(ctx.destination);
    src.start(at); src.stop(at + dur);
  }

  /* ---- canvas effects -------------------------------------------------- */

  function canvasOver(section) {
    // MARP sections are not positioned by default, and the canvas must sit on top.
    if (getComputedStyle(section).position === 'static') section.style.position = 'relative';
    var c = section.querySelector('canvas.clicker-fx');
    if (!c) {
      c = document.createElement('canvas');
      c.className = 'clicker-fx';
      section.appendChild(c);
    }
    c.width = section.clientWidth;
    c.height = section.clientHeight;
    return c;
  }

  function fireworks(section, quiet) {
    var c = canvasOver(section), g = c.getContext('2d');
    var parts = [], shells = 0, ctx = quiet ? null : audio();
    var hues = [350, 45, 200, 120, 285];

    function burst(x, y, hue) {
      for (var i = 0; i < 120; i++) {
        var a = Math.random() * Math.PI * 2, s = 2 + Math.random() * 6;
        parts.push({
          x: x, y: y, px: x, py: y,
          vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: 1, hue: hue,
        });
      }
      if (ctx) boom(ctx, ctx.currentTime);
    }

    function launch() {
      var x = c.width * (0.12 + Math.random() * 0.76);
      var y = c.height * (0.12 + Math.random() * 0.4);
      var hue = hues[shells % hues.length];
      if (ctx) whistle(ctx, ctx.currentTime);
      setTimeout(function () { burst(x, y, hue); }, 320);
      shells++;
    }

    // Fire the first one immediately. setInterval waits a full period before its
    // first tick, which put nearly a second of dead air between the click and any
    // sign that something was happening.
    launch();
    var launcher = setInterval(function () {
      if (shells >= 6) { clearInterval(launcher); return; }
      launch();
    }, 380);

    var t0 = performance.now();
    (function frame(now) {
      g.clearRect(0, 0, c.width, c.height);
      g.lineCap = 'round';
      for (var i = parts.length - 1; i >= 0; i--) {
        var p = parts[i];
        p.px = p.x; p.py = p.y;
        p.x += p.vx; p.y += p.vy; p.vy += 0.055; p.vx *= 0.985; p.vy *= 0.985;
        p.life -= 0.011;
        if (p.life <= 0) { parts.splice(i, 1); continue; }
        var col = 'hsl(' + p.hue + ', 95%, ' + (52 + 26 * p.life) + '%)';
        g.globalAlpha = Math.max(0, p.life);
        // A short trail behind each spark covers far more of the screen than the
        // head alone, which is what makes this readable from the back of a room.
        g.strokeStyle = col;
        g.lineWidth = 3.2;
        g.beginPath(); g.moveTo(p.px, p.py); g.lineTo(p.x, p.y); g.stroke();
        g.fillStyle = col;
        g.beginPath(); g.arc(p.x, p.y, 3.4, 0, 6.284); g.fill();
      }
      g.globalAlpha = 1;
      if (now - t0 < 5200 || parts.length) requestAnimationFrame(frame);
      else { clearInterval(launcher); c.remove(); }
    })(t0);
  }

  function rain(section, quiet) {
    var c = canvasOver(section), g = c.getContext('2d');
    var ctx = quiet ? null : audio();
    var DUR = 4200;
    if (ctx) downpour(ctx, ctx.currentTime, DUR / 1000);

    var drops = [];
    for (var i = 0; i < 260; i++) {
      drops.push({
        x: Math.random() * c.width,
        y: Math.random() * c.height,
        len: 9 + Math.random() * 16,
        v: 7 + Math.random() * 9,
      });
    }
    var t0 = performance.now();
    (function frame(now) {
      var age = now - t0;
      var fade = age < 400 ? age / 400 : (age > DUR - 500 ? Math.max(0, (DUR - age) / 500) : 1);
      g.clearRect(0, 0, c.width, c.height);

      // A dark band across the top, which reads as cloud without a bitmap.
      var grad = g.createLinearGradient(0, 0, 0, c.height * 0.55);
      grad.addColorStop(0, 'rgba(40,46,54,' + 0.55 * fade + ')');
      grad.addColorStop(1, 'rgba(40,46,54,0)');
      g.fillStyle = grad;
      g.fillRect(0, 0, c.width, c.height * 0.55);

      g.strokeStyle = 'rgba(150,175,205,' + 0.72 * fade + ')';
      g.lineWidth = 1.4;
      g.beginPath();
      drops.forEach(function (d) {
        g.moveTo(d.x, d.y); g.lineTo(d.x - 1.6, d.y + d.len);
        d.y += d.v; d.x -= 0.35;
        if (d.y > c.height) { d.y = -d.len; d.x = Math.random() * c.width; }
      });
      g.stroke();

      if (age < DUR) requestAnimationFrame(frame);
      else c.remove();
    })(t0);
  }

  /* ---- one question ---------------------------------------------------- */

  function setup(root) {
    var api = (root.dataset.read || '').replace(/\/+$/, '');
    var seconds = parseInt(root.dataset.seconds, 10) || 60;
    var answer = (root.dataset.answer || '').toUpperCase();
    var btn = root.querySelector('.clicker-start');
    if (!btn || !api) return;

    var timerEl = root.querySelector('.clicker-timer');
    var countEl = root.querySelector('.clicker-count');
    var panel = root.querySelector('.clicker-panel');
    var main = root.querySelector('.clicker-main') || panel;
    var section = root.closest('section') || root.parentElement;

    // The bars carry the option text, and the option list is hidden while they are
    // up. Showing both overflows the slide: four options plus four bars plus a
    // verdict plus a hint does not fit in 720px, and the hint is what gets cut.
    var opts = root.querySelector('.clicker-opts');
    var optText = opts
      ? Array.prototype.map.call(opts.querySelectorAll('li'), function (li) {
          return li.textContent.trim();
        })
      : [];

    var bars = document.createElement('div');
    bars.className = 'clicker-bars';
    bars.hidden = true;
    LETTERS.forEach(function (L, i) {
      bars.insertAdjacentHTML('beforeend',
        '<span class="lab" data-lab="' + L + '">' + L + '</span>' +
        '<span class="barwrap">' +
          '<span class="txt">' + (optText[i] || '') + '</span>' +
          '<span class="track"><i class="fill" data-fill="' + L + '"></i></span>' +
        '</span>' +
        '<span class="num" data-num="' + L + '">0</span>');
    });
    main.appendChild(bars);

    var verdict = document.createElement('p');
    verdict.className = 'clicker-verdict';
    verdict.hidden = true;
    main.appendChild(verdict);

    var tag = root.dataset.tag || '';
    var hintText = root.dataset.hint || '';
    var hint = document.createElement('p');
    hint.className = 'clicker-hint';
    hint.hidden = true;
    hint.textContent = hintText;
    main.appendChild(hint);

    var whyText = root.dataset.why || '';
    var why = document.createElement('p');
    why.className = 'clicker-why';
    why.hidden = true;
    why.textContent = whyText;
    main.appendChild(why);

    var round = 0;

    // The heading is already the question, so read it rather than making the
    // author write it out a second time and let the two drift.
    function promptText() {
      var sec = root.closest('section');
      var h = sec && sec.querySelector('h1, h2, h3');
      return (h ? h.textContent : '').trim().slice(0, 300);
    }

    // Mute lives next to the button so it is reachable without leaving the slide.
    var mute = document.createElement('button');
    mute.className = 'clicker-mute';
    mute.type = 'button';
    function paintMute() { mute.textContent = muted() ? 'sound off' : 'sound on'; }
    paintMute();
    mute.addEventListener('click', function () { setMuted(!muted()); paintMute(); });
    panel.appendChild(mute);

    var start = null, end = null, poll = null, tick = null, open = false, offset = 0;

    function read(to) {
      return fetch(api + '/r?from=' + start + '&to=' + to, { cache: 'no-store' })
        .then(function (r) { return r.json(); });
    }

    function reveal(data) {
      open = false;
      clearInterval(poll); clearInterval(tick);

      var max = LETTERS.reduce(function (m, L) { return Math.max(m, data[L] || 0); }, 0);
      LETTERS.forEach(function (L) {
        var n = data[L] || 0;
        bars.querySelector('[data-fill="' + L + '"]').style.width = (100 * n / Math.max(1, max)) + '%';
        bars.querySelector('[data-num="' + L + '"]').textContent = n;
        bars.querySelector('[data-lab="' + L + '"]').classList.toggle('is-answer', !!answer && L === answer);
      });
      bars.hidden = false;
      if (opts) opts.hidden = true;
      timerEl.textContent = 'done';
      timerEl.classList.add('is-over');
      countEl.textContent = data.total + (data.total === 1 ? ' vote' : ' votes');

      // Vote, argue, vote again. The second round is the one that moves people,
      // so it must not need a page reload.
      btn.textContent = 'Vote again';
      btn.disabled = false;

      // Tell the archive which question this window was. Best-effort on purpose:
      // a failed mark must never disturb what is on the screen in front of a room.
      if (tag) {
        var q = '?tag=' + encodeURIComponent(tag) +
                '&from=' + start + '&to=' + data.to +
                '&round=' + round +
                (answer ? '&answer=' + encodeURIComponent(answer) : '') +
                '&prompt=' + encodeURIComponent(promptText());
        fetch(api + '/mark' + q, { cache: 'no-store' }).catch(function () {});
      }

      // Revealing nothing at all, with no explanation, is the worst thing this can
      // do in front of a room: it looks broken rather than empty. Say which it is.
      if (!data.total) {
        verdict.textContent = 'No votes in that window.';
        verdict.className = 'clicker-verdict is-mixed';
        verdict.hidden = false;
        return;
      }
      if (!answer) return;   // opinion poll: bars, no verdict, no effects
      var pct = Math.round(100 * (data[answer] || 0) / data.total);
      var b = band(pct);
      verdict.textContent = 'Round ' + round + ': ' + pct + '% correct. ' + b.text;
      verdict.className = 'clicker-verdict is-' + b.key;
      verdict.hidden = false;

      // The hint is for the rooms that need a second go; the explanation is for the
      // ones that got there. A celebration on its own teaches nobody, including
      // whoever guessed.
      if (hintText && b.key !== 'good') hint.hidden = false;
      if (whyText && b.key === 'good') why.hidden = false;

      if (b.key === 'good') fireworks(section, muted());
      else if (b.key === 'poor') rain(section, muted());
    }

    function close() {
      if (!open) return;
      read(Math.min(Date.now() - offset, end)).then(reveal).catch(function () {
        timerEl.textContent = '!';
        countEl.textContent = 'could not reach the server';
      });
    }

    function openWindow() {
      if (open) return;

      // Unlock audio on any interaction we can get. Browsers block autoplay until
      // a user gesture; navigating to this slide is one, so by the time a question
      // opens the page has almost always had one. resume() is a no-op otherwise.
      var a = muted() ? null : audio();
      if (a && a.state === 'suspended') a.resume();

      // One cheap call establishes the server's clock before anything else.
      fetch(api + '/r?from=0&to=0', { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          offset = Date.now() - d.server_ts;
          start = d.server_ts;
          end = start + seconds * 1000;
          open = true;
          round += 1;
          btn.textContent = 'Reveal now';

          // Tell the phones a question is running and when it stops, so they can
          // clear themselves at the right moment instead of guessing with a timer.
          // Best-effort: a failure here must never disturb what is on screen.
          fetch(api + '/open?seconds=' + seconds +
                (tag ? '&tag=' + encodeURIComponent(tag) : ''),
                { cache: 'no-store' }).catch(function () {});
          timerEl.classList.remove('is-over');

          // A fresh window means the previous round's result is stale. Clear it,
          // and keep the hint up: it is what people are arguing about.
          bars.hidden = true;
          if (opts) opts.hidden = false;
          verdict.hidden = true;
          why.hidden = true;
          document.querySelectorAll('canvas.clicker-fx').forEach(function (c) { c.remove(); });

          tick = setInterval(function () {
            var left = Math.max(0, Math.round((end - (Date.now() - offset)) / 1000));
            timerEl.textContent = left;
            if (left <= 0) close();
          }, 200);

          poll = setInterval(function () {
            read(end).then(function (data) {
              // Count only. The breakdown stays hidden until voting closes.
              countEl.textContent = data.total === 0
                ? 'no votes yet'
                : data.total + (data.total === 1 ? ' vote in' : ' votes in');
            }).catch(function () { countEl.textContent = 'server unreachable'; });
          }, 1000);
        })
        .catch(function () { countEl.textContent = 'could not reach the server'; });
    }

    btn.addEventListener('click', function () {
      if (open) close();
      else openWindow();
    });

    // Open when the slide actually comes up. Watching visibility rather than the
    // deck's own events keeps this working in slide mode and scroll mode alike,
    // and does not depend on MARP's internals, which are not exposed.
    if (root.dataset.autostart !== 'false' && 'IntersectionObserver' in window) {
      var armed = true;
      new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (!armed || !e.isIntersecting || e.intersectionRatio < 0.6) return;
          armed = false;          // once per slide, never on the way back
          openWindow();
        });
      }, { threshold: [0.6] }).observe(section);
    }
  }

  document.querySelectorAll('.clicker[data-read]').forEach(setup);
})();
