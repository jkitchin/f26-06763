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
      for (var i = 0; i < 70; i++) {
        var a = Math.random() * Math.PI * 2, s = 1.5 + Math.random() * 4.5;
        parts.push({ x: x, y: y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: 1, hue: hue });
      }
      if (ctx) boom(ctx, ctx.currentTime);
    }

    var launcher = setInterval(function () {
      if (shells >= 5) { clearInterval(launcher); return; }
      var x = c.width * (0.15 + Math.random() * 0.7);
      var y = c.height * (0.15 + Math.random() * 0.35);
      if (ctx) whistle(ctx, ctx.currentTime);
      setTimeout(function () { burst(x, y, hues[shells % hues.length]); }, 450);
      shells++;
    }, 420);

    var t0 = performance.now();
    (function frame(now) {
      g.clearRect(0, 0, c.width, c.height);
      for (var i = parts.length - 1; i >= 0; i--) {
        var p = parts[i];
        p.x += p.vx; p.y += p.vy; p.vy += 0.055; p.vx *= 0.985; p.vy *= 0.985;
        p.life -= 0.012;
        if (p.life <= 0) { parts.splice(i, 1); continue; }
        g.globalAlpha = Math.max(0, p.life);
        g.fillStyle = 'hsl(' + p.hue + ', 90%, ' + (55 + 25 * p.life) + '%)';
        g.beginPath(); g.arc(p.x, p.y, 2.6, 0, 6.284); g.fill();
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

    var bars = document.createElement('div');
    bars.className = 'clicker-bars';
    bars.hidden = true;
    LETTERS.forEach(function (L) {
      bars.insertAdjacentHTML('beforeend',
        '<span class="lab" data-lab="' + L + '">' + L + '</span>' +
        '<span class="track"><i class="fill" data-fill="' + L + '"></i></span>' +
        '<span class="num" data-num="' + L + '">0</span>');
    });
    main.appendChild(bars);

    var verdict = document.createElement('p');
    verdict.className = 'clicker-verdict';
    verdict.hidden = true;
    main.appendChild(verdict);

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
      timerEl.textContent = 'done';
      timerEl.classList.add('is-over');
      countEl.textContent = data.total + (data.total === 1 ? ' vote' : ' votes');
      btn.textContent = 'Closed';
      btn.disabled = true;

      if (!answer || !data.total) return;   // opinion poll: bars, no verdict
      var pct = Math.round(100 * (data[answer] || 0) / data.total);
      var b = band(pct);
      verdict.textContent = pct + '% correct. ' + b.text;
      verdict.className = 'clicker-verdict is-' + b.key;
      verdict.hidden = false;
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

    btn.addEventListener('click', function () {
      if (open) { close(); return; }

      // This click is also the user gesture that unlocks audio. Browsers block
      // autoplay until one happens, so the reveal would otherwise be silent.
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
          btn.textContent = 'Reveal now';
          timerEl.classList.remove('is-over');

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
    });
  }

  document.querySelectorAll('.clicker[data-read]').forEach(setup);
})();
