/* The arcade shell: everything a one-minute minigame is NOT.
 *
 * Include once per page, after the content, followed by the games you want:
 *
 *     <script src=".../arcade/arcade.js"></script>
 *     <script src=".../arcade/games/whackabug.js"></script>
 *
 * arcade.css comes along by itself, from beside this file. A page that wants to
 * load it earlier can, with <link rel="stylesheet" data-arcade-css ...>.
 *
 * Markup, in a MARP slide or an MyST notes page alike:
 *
 *     <div class="arcade" data-game="whackabug" data-lecture="l03"
 *          data-seconds="60" data-board="live"
 *          data-read="https://clicker.f26-06763.workers.dev"></div>
 *
 * This file owns identity, the round protocol, the clock, the submit and the
 * board. A game owns its sixty seconds of pixels and nothing else, which is
 * what keeps a new one to an afternoon:
 *
 *     Arcade.register('whackabug', {
 *       seconds: 60,
 *       mount: function (root, ctx) { ...; return { stop: function () {} } },
 *     })
 *
 * ctx carries { items, rng, seconds, score(n), end() } and nothing about the
 * server. A game that could reach the network could also decide what it scored
 * without telling the shell, and then no two games would agree on what a point
 * was.
 *
 * Three things here are deliberate and worth not undoing:
 *
 *   - The device id and nickname are the CLICKER's, same localStorage keys and
 *     same /name route. A student is one person on one board all semester
 *     rather than a clicker name and an unrelated arcade name.
 *
 *   - The round order is seeded by the run id the server minted, so a run can
 *     be replayed exactly from its transcript. That is the only reason the
 *     transcript is worth keeping.
 *
 *   - Nothing here is graded, and the code says so where a student can see it.
 *     The score is a claim the browser makes; the arcade is formative for the
 *     same reason the clicker is.
 */
(function () {
  'use strict';

  var GAMES = {};

  // Shared with vote.html on purpose. See the note above.
  var DEV_KEY = 'f26-06763-clicker/device';
  var NAME_KEY = 'f26-06763-clicker/name';
  var ANON_KEY = 'f26-06763-clicker/anon';

  // rounds/ sits next to this script, so a slide never has to say where the
  // content is and can never say it wrong.
  var HERE = (function () {
    var s = document.currentScript;
    return s && s.src ? s.src.replace(/\/[^/]*$/, '/') : './';
  })();

  /* ---- storage, which is allowed to not work ---------------------------- */

  function store(key, val) { try { localStorage.setItem(key, val); } catch (e) {} }
  function load(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }

  // A random pseudonym, not an identity: it lets a board tell two players apart
  // and lets one browser recognise its own past runs. Nothing else.
  function deviceId() {
    var d = load(DEV_KEY);
    if (d && /^[A-Za-z0-9_-]{8,64}$/.test(d)) return d;
    var bytes = new Uint8Array(12);
    if (self.crypto && self.crypto.getRandomValues) self.crypto.getRandomValues(bytes);
    else for (var i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
    d = Array.prototype.map.call(bytes, function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
    store(DEV_KEY, d);
    return d;
  }

  /* ---- a seeded shuffle ------------------------------------------------- */

  // xmur3 + mulberry32. Not cryptography and not trying to be: it exists so the
  // order a player saw can be reconstructed from the run id in the transcript.
  function rngFrom(seed) {
    var h = 1779033703 ^ seed.length;
    for (var i = 0; i < seed.length; i++) {
      h = Math.imul(h ^ seed.charCodeAt(i), 3432918353);
      h = (h << 13) | (h >>> 19);
    }
    var a = h >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function shuffle(list, rng) {
    var out = list.slice();
    for (var i = out.length - 1; i > 0; i--) {
      var j = Math.floor(rng() * (i + 1));
      var t = out[i]; out[i] = out[j]; out[j] = t;
    }
    return out;
  }

  /* ---- the smallest markdown that renders a bank prompt ----------------- */

  // Prompts carry fenced code, inline code, bold, and the occasional link into
  // the notes. Everything else is treated as text. Built out of createElement
  // and textContent rather than a string of HTML: the content is trusted, the
  // habit is what stops the day it is not.
  //
  // A link keeps its label and loses its target. Nothing in a sixty-second game
  // is worth navigating away for, and leaving the raw [text](url) on screen
  // reads as a rendering bug rather than as a link.
  function markdown(el, src) {
    el.textContent = '';
    String(src || '').split(/```/).forEach(function (chunk, i) {
      if (i % 2) {
        var pre = document.createElement('pre');
        var code = document.createElement('code');
        code.textContent = chunk.replace(/^[a-zA-Z]*\n/, '').replace(/\s+$/, '');
        pre.appendChild(code);
        el.appendChild(pre);
        return;
      }
      chunk.split(/\n{2,}/).forEach(function (para) {
        if (!para.trim()) return;
        var p = document.createElement('p');
        // Links go first, before the backtick split: a label is often itself
        // code, so splitting first leaves the brackets stranded in two
        // different pieces and neither one can see it was ever a link.
        para = para.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
        para.split(/`/).forEach(function (bit, j) {
          if (!bit) return;
          if (j % 2) {
            var c = document.createElement('code');
            c.textContent = bit;
            p.appendChild(c);
          } else {
            var text = bit.replace(/\s*\n\s*/g, ' ');
            text.split(/\*\*/).forEach(function (run, k) {
              if (!run) return;
              if (k % 2) {
                var b = document.createElement('strong');
                b.textContent = run;
                p.appendChild(b);
              } else {
                p.appendChild(document.createTextNode(run));
              }
            });
          }
        });
        el.appendChild(p);
      });
    });
  }

  /* ---- the board -------------------------------------------------------- */

  function fmtMs(ms) {
    var s = ms / 1000;
    if (s < 60) return (s < 10 ? s.toFixed(1) : Math.round(s)) + 's';
    var m = Math.floor(s / 60);
    return m + 'm' + ('0' + Math.round(s - m * 60)).slice(-2) + 's';
  }

  // Every name here was typed by a student, so every one of them goes in
  // through textContent. The server restricts the charset and this is the
  // second lock on the same door.
  function renderBoard(el, data, mine) {
    el.textContent = '';

    var h = document.createElement('div');
    h.className = 'arcade-board-title';
    h.textContent = data && data.all ? 'This semester' : 'Just now';
    el.appendChild(h);

    var rows = (data && data.standings) || [];
    if (!rows.length) {
      var empty = document.createElement('div');
      empty.className = 'arcade-board-empty';
      // Two different blanks, and neither is an error. An unexplained empty box
      // reads as broken in front of a room.
      empty.textContent = data && data.players
        ? 'Nobody has picked a nickname yet.'
        : 'No runs yet. Be the first.';
      el.appendChild(empty);
      return;
    }

    var ol = document.createElement('ol');
    ol.className = 'arcade-board-list';
    rows.forEach(function (s) {
      var li = document.createElement('li');
      if (mine && s.name === mine) li.className = 'is-me';
      [['rank', s.rank], ['who', s.name], ['pts', s.score], ['secs', fmtMs(s.ms)]].forEach(function (pair) {
        var span = document.createElement('span');
        span.className = pair[0];
        span.textContent = pair[1];
        li.appendChild(span);
      });
      ol.appendChild(li);
    });
    el.appendChild(ol);

    var foot = document.createElement('div');
    foot.className = 'arcade-board-foot';
    // The field is everyone who played; the list is everyone who is named. A
    // player who skipped the nickname still took a place, and saying so is what
    // keeps the ranks honest.
    foot.textContent = data.players + (data.players === 1 ? ' player' : ' players') +
      (data.players > data.named ? ', ' + (data.players - data.named) + ' unnamed' : '');
    el.appendChild(foot);
  }

  /* ---- one arcade cabinet ----------------------------------------------- */

  function setup(root) {
    var api = (root.dataset.read || '').replace(/\/+$/, '');
    var gameId = root.dataset.game || '';
    var lecture = root.dataset.lecture || '';
    var game = GAMES[gameId];
    if (!api || !game || !lecture) {
      root.textContent = 'This game is not configured: it needs data-read, data-game and data-lecture.';
      return;
    }

    var seconds = parseInt(root.dataset.seconds, 10) || game.seconds || 60;
    var key = lecture + '-' + gameId;                       // the opaque board key
    var wantAll = root.dataset.board === 'all';
    var top = parseInt(root.dataset.top, 10) || 8;
    var device = deviceId();
    var roundsUrl = root.dataset.rounds || (HERE + 'rounds/' + lecture + '.json');

    root.classList.add('arcade-ready');
    root.textContent = '';

    /* --- the furniture --- */

    var stage = document.createElement('div');
    stage.className = 'arcade-stage';

    var hud = document.createElement('div');
    hud.className = 'arcade-hud';
    var scoreEl = document.createElement('span'); scoreEl.className = 'arcade-score'; scoreEl.textContent = '0';
    var timerEl = document.createElement('span'); timerEl.className = 'arcade-timer'; timerEl.textContent = seconds;
    var whoEl = document.createElement('span'); whoEl.className = 'arcade-who';
    hud.appendChild(scoreEl); hud.appendChild(timerEl); hud.appendChild(whoEl);

    var panel = document.createElement('aside');
    panel.className = 'arcade-panel';
    var boardEl = document.createElement('div');
    boardEl.className = 'arcade-board';
    var startBtn = document.createElement('button');
    startBtn.className = 'arcade-start';
    startBtn.type = 'button';
    startBtn.textContent = 'Play';
    var noteEl = document.createElement('p');
    noteEl.className = 'arcade-note';
    noteEl.textContent = 'Nothing here is graded.';
    panel.appendChild(boardEl); panel.appendChild(startBtn); panel.appendChild(noteEl);

    root.appendChild(stage); root.appendChild(hud); root.appendChild(panel);

    /* --- who you are, if you want to be anyone --- */

    function myName() { return load(NAME_KEY) || ''; }

    function paintWho() {
      whoEl.textContent = '';
      var label = document.createElement('span');
      label.textContent = myName() ? myName() : 'playing anonymously';
      whoEl.appendChild(label);
      var change = document.createElement('button');
      change.type = 'button';
      change.className = 'arcade-rename';
      change.textContent = myName() ? 'change' : 'pick a nickname';
      change.addEventListener('click', askName);
      whoEl.appendChild(change);
    }

    // Skipping is a first-class choice rather than a dead end: an anonymous run
    // counts, holds its place in the field, and simply is not named on the wall.
    function askName() {
      var want = window.prompt(
        'A nickname for the board. Invent one, never your Andrew ID.\n' +
        'Leave it empty to keep playing anonymously.',
        myName()
      );
      if (want === null) return;
      want = want.trim();
      if (!want) { store(ANON_KEY, '1'); store(NAME_KEY, ''); paintWho(); return; }
      fetch(api + '/name?d=' + encodeURIComponent(device) + '&n=' + encodeURIComponent(want), { cache: 'no-store' })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
        .then(function (res) {
          if (!res.ok) throw new Error(res.body && res.body.error === 'taken'
            ? 'Someone already has that one.'
            : (res.body && res.body.error) || 'rejected');
          store(NAME_KEY, res.body.name);
          store(ANON_KEY, '0');
          paintWho();
          drawBoard();
        })
        .catch(function (err) { window.alert(err.message); });
    }

    paintWho();

    /* --- the board --- */

    function drawBoard() {
      var q = '/board?g=' + encodeURIComponent(key) + '&top=' + top + (wantAll ? '&all=1' : '&hours=6');
      return fetch(api + q, { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (d) { renderBoard(boardEl, d, myName()); })
        .catch(function () {
          boardEl.textContent = '';
          var e = document.createElement('div');
          e.className = 'arcade-board-empty';
          e.textContent = 'Could not reach the server.';
          boardEl.appendChild(e);
        });
    }

    /* --- content --- */

    var rounds = null;
    function loadRounds() {
      if (rounds) return Promise.resolve(rounds);
      return fetch(roundsUrl, { cache: 'no-store' })
        .then(function (r) {
          if (!r.ok) throw new Error('no round file for ' + lecture);
          return r.json();
        })
        .then(function (d) { rounds = d; return d; });
    }

    /* --- a run --- */

    var live = null, tick = null, score = 0, transcript = [];

    function setScore(n) { score = n; scoreEl.textContent = n; }

    function stop() {
      if (tick) { clearInterval(tick); tick = null; }
      if (live && live.stop) { try { live.stop(); } catch (e) {} }
      live = null;
    }

    function finish(runId) {
      stop();
      startBtn.disabled = false;
      startBtn.textContent = 'Play again';
      timerEl.textContent = 'done';

      // The transcript is what makes an implausible run reviewable later. It is
      // never read by the server and never scored by it.
      var detail = JSON.stringify({ v: 1, items: transcript.slice(0, 120) });

      var q = '/submit?d=' + encodeURIComponent(device) +
              '&g=' + encodeURIComponent(key) +
              '&run=' + encodeURIComponent(runId) +
              '&s=' + score +
              '&detail=' + encodeURIComponent(detail);

      fetch(api + q, { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.ok) {
            noteEl.textContent = d.rank
              ? 'Scored ' + d.score + '. ' + (d.rank === 1 ? 'Top of ' : 'Rank ' + d.rank + ' of ') + d.players + '.'
              : 'Scored ' + d.score + '.';
          }
          return drawBoard();
        })
        .catch(function () { noteEl.textContent = 'Scored ' + score + ', but the server did not hear it.'; });
    }

    function begin() {
      startBtn.disabled = true;
      startBtn.textContent = 'Loading';
      noteEl.textContent = 'Nothing here is graded.';

      Promise.all([
        loadRounds(),
        fetch(api + '/start?d=' + encodeURIComponent(device) + '&g=' + encodeURIComponent(key), { cache: 'no-store' })
          .then(function (r) { return r.json(); }),
      ])
        .then(function (both) {
          var data = both[0], run = both[1];
          if (!run || !run.run) throw new Error('the server did not open a run');

          // Seeded by the run id, so the order is reproducible from the
          // transcript and is nevertheless different every time.
          var rng = rngFrom(run.run);
          setScore(0);
          transcript = [];
          startBtn.textContent = 'Playing';

          var left = seconds;
          timerEl.textContent = left;
          timerEl.classList.remove('is-over');
          tick = setInterval(function () {
            left -= 1;
            timerEl.textContent = Math.max(0, left);
            if (left <= 0) { timerEl.classList.add('is-over'); finish(run.run); }
          }, 1000);

          live = game.mount(stage, {
            items: shuffle(data.items || [], rng),
            rng: rng,
            seconds: seconds,
            markdown: markdown,
            // A game reports what it scored and when it is out of road. It
            // never learns the device, the run id, or the address of the server.
            score: setScore,
            record: function (entry) { transcript.push(entry); },
            end: function () { finish(run.run); },
          });
        })
        .catch(function (err) {
          stop();
          startBtn.disabled = false;
          startBtn.textContent = 'Play';
          noteEl.textContent = 'Could not start: ' + err.message;
        });
    }

    startBtn.addEventListener('click', begin);
    drawBoard();

    // Leaving the slide mid-run stops the clock rather than submitting a run
    // nobody was playing. The abandoned run row is swept by the next /start.
    if ('IntersectionObserver' in window) {
      var section = root.closest('section') || root.parentElement;
      new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting && live) {
            stop();
            startBtn.disabled = false;
            startBtn.textContent = 'Play';
            timerEl.textContent = seconds;
          }
        });
      }, { threshold: [0.2] }).observe(section);
    }
  }

  /* ---- boot -------------------------------------------------------------- */

  window.Arcade = {
    register: function (id, game) { GAMES[id] = game; },
  };

  // The stylesheet comes from beside this script, for the same reason rounds/
  // does: a page that has to remember a second path is a page that will one day
  // get it wrong, and an unstyled cabinet on a projector looks broken rather
  // than unstyled. A page that has already loaded it keeps its own copy.
  function styles() {
    if (document.querySelector('link[data-arcade-css]')) return;
    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = HERE + 'arcade.css';
    link.setAttribute('data-arcade-css', '');
    document.head.appendChild(link);
  }

  function boot() {
    styles();
    document.querySelectorAll('.arcade[data-read]').forEach(setup);
  }

  // Games register themselves in scripts that come after this one, so the scan
  // waits for the document rather than running where this file sits.
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else setTimeout(boot, 0);
})();
