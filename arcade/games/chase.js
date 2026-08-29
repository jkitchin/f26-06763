/* Concept Chase: eat the right words before the ghosts do.
 *
 * A maze scattered with terms. The banner names a category. Eat the terms that
 * belong to it, leave the ones that do not -- and the ghosts are eating the
 * right ones too, so the board empties whether or not you are quick. That
 * inversion is the whole design: a timer alone makes a quiz with sprites,
 * while an opponent competing for the SAME pellets makes the decision urgent
 * in a way a countdown never does.
 *
 * The terms come from the bank's `terms` key, and the generator guarantees
 * something this game could not check for itself: every correct term appears
 * in the lecture notes and no wrong one does. A distractor the notes actually
 * use would punish the student who read them.
 *
 * Scoring:
 *
 *     right   10, plus a streak bonus
 *     wrong   -5
 *     left    2 a second, when the board is cleared of correct terms
 *
 * A wrong pellet costs points here, unlike the other two games, because
 * avoiding one is the skill: with no penalty the best play is to drive through
 * everything, which is exactly the habit the game is meant to break.
 */
(function () {
  'use strict';

  // Nine by seven rather than a classic dense lattice: a cell has to be wide
  // enough to print "double precision" legibly on a projector, and thirteen
  // columns across a slide is about eighty pixels, which is not.
  var COLS = 9, ROWS = 7;
  var GHOSTS = 2;
  // Ghost pacing is the whole balance of this game and the first cut had it
  // badly wrong: two ghosts beelining every 620ms clear a sixteen-pellet board
  // in about seven seconds, so the round was over before the banner had been
  // read. A ghost now steps slowly, waits for the player to get going, and is
  // only usually greedy -- see GREEDY.
  var GHOST_MS = 1500;
  var HEAD_START_MS = 3000;
  // How often a ghost takes the step that actually closes on its target. The
  // rest of the time it wanders, which roughly halves how fast the board
  // empties and, incidentally, looks far more like a ghost than a solver does.
  var GREEDY = 0.6;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // A sparse maze rather than a dense one: the words need room to be readable,
  // and a classic Pac-Man lattice would leave no cell wide enough to print
  // "double precision" in.
  function walls(rng) {
    var w = {};
    for (var y = 1; y < ROWS - 1; y += 2) {
      for (var x = 1; x < COLS - 1; x += 2) {
        if (rng() < 0.55) w[x + ',' + y] = true;
      }
    }
    return w;
  }

  Arcade.register('chase', {
    seconds: 60,

    pick: function (items) {
      return items.filter(function (i) {
        return i.terms && (i.terms.correct || []).length >= 3 && (i.terms.wrong || []).length >= 3;
      });
    },

    mount: function (root, ctx) {
      var item = ctx.items[0];
      var score = 0, streak = 0, done = false, left = ctx.seconds;
      var raf = null, ghostTimer = null, ghostStart = null;
      var eatenWrong = [];

      root.textContent = '';
      root.classList.add('chase');

      var banner = el('div', 'chase-banner', item.terms.prompt || 'Eat the ones that belong.');
      var grid = el('div', 'chase-grid');
      var status = el('div', 'chase-status');
      root.appendChild(banner);
      root.appendChild(grid);
      root.appendChild(status);

      var wall = walls(ctx.rng);

      // Lay the pellets on the free cells. Correct and wrong are interleaved by
      // the shuffle rather than by region, so there is no spatial tell.
      var cells = [];
      for (var y = 0; y < ROWS; y++) {
        for (var x = 0; x < COLS; x++) {
          if (!wall[x + ',' + y]) cells.push({ x: x, y: y });
        }
      }
      for (var i = cells.length - 1; i > 0; i--) {
        var j = Math.floor(ctx.rng() * (i + 1));
        var t = cells[i]; cells[i] = cells[j]; cells[j] = t;
      }

      var pellets = {};
      var correctLeft = 0;
      var pool = item.terms.correct.map(function (w) { return { word: w, good: true }; })
        .concat(item.terms.wrong.map(function (w) { return { word: w, good: false }; }));
      for (var k = pool.length - 1; k > 0; k--) {
        var m = Math.floor(ctx.rng() * (k + 1));
        var s = pool[k]; pool[k] = pool[m]; pool[m] = s;
      }
      // Leave the first free cell for the player and the last two for ghosts.
      var spawn = cells.shift();
      var ghostHomes = cells.splice(-GHOSTS, GHOSTS);
      pool.slice(0, cells.length).forEach(function (p, n) {
        var c = cells[n];
        pellets[c.x + ',' + c.y] = p;
        if (p.good) correctLeft += 1;
      });

      var me = { x: spawn.x, y: spawn.y };
      var ghosts = ghostHomes.map(function (g) { return { x: g.x, y: g.y }; });

      /* --- rendering ------------------------------------------------------
       * DOM cells rather than canvas, for the reason MapView in game/ gives:
       * text in a canvas is invisible to a screen reader and does not scale
       * with the page. A 13x9 grid is nowhere near enough nodes to matter. */

      var nodes = {};
      grid.style.gridTemplateColumns = 'repeat(' + COLS + ', 1fr)';
      for (var yy = 0; yy < ROWS; yy++) {
        for (var xx = 0; xx < COLS; xx++) {
          var key = xx + ',' + yy;
          var c = el('div', 'chase-cell' + (wall[key] ? ' is-wall' : ''));
          c.dataset.k = key;
          nodes[key] = c;
          grid.appendChild(c);
        }
      }

      function paint() {
        Object.keys(nodes).forEach(function (key) {
          var n = nodes[key];
          var p = pellets[key];
          n.textContent = p ? p.word : '';
          n.className = 'chase-cell' + (wall[key] ? ' is-wall' : '') + (p ? ' has-word' : '');
        });
        ghosts.forEach(function (g) {
          var n = nodes[g.x + ',' + g.y];
          if (n) n.classList.add('is-ghost');
        });
        var mine = nodes[me.x + ',' + me.y];
        if (mine) mine.classList.add('is-me');
        status.textContent = correctLeft + (correctLeft === 1 ? ' left to eat' : ' left to eat');
      }

      function free(x, y) {
        return x >= 0 && y >= 0 && x < COLS && y < ROWS && !wall[x + ',' + y];
      }

      function stop() {
        done = true;
        if (raf) { cancelAnimationFrame(raf); raf = null; }
        if (ghostStart) { clearTimeout(ghostStart); ghostStart = null; }
        if (ghostTimer) { clearInterval(ghostTimer); ghostTimer = null; }
        window.removeEventListener('keydown', onKey, true);
        grid.removeEventListener('touchstart', onTouchStart);
        grid.removeEventListener('touchend', onTouchEnd);
      }

      function summarise() {
        grid.hidden = true;
        status.hidden = true;
        var box = el('div', 'chase-summary');
        if (eatenWrong.length) {
          box.appendChild(el('h4', null, 'Not in the notes'));
          box.appendChild(el('p', 'chase-ate', eatenWrong.join(', ')));
          box.appendChild(el('p', 'chase-ate-why',
            'None of those appear in this lecture. The ones that do: ' +
            item.terms.correct.join(', ') + '.'));
        } else {
          box.appendChild(el('h4', null, 'Clean run. Nothing eaten that should not have been.'));
        }
        root.appendChild(box);
      }

      function over() {
        if (done) return;
        // Clearing the board early is worth the time you saved, which is what
        // makes racing the ghosts worth doing rather than merely survivable.
        if (correctLeft === 0) {
          score += 2 * Math.max(0, Math.round(left));
          ctx.score(score);
        }
        stop();
        summarise();
        ctx.end();
      }

      function eat(x, y, byGhost) {
        var key = x + ',' + y;
        var p = pellets[key];
        if (!p) return;
        delete pellets[key];
        if (p.good) correctLeft -= 1;

        if (!byGhost) {
          ctx.record({ id: item.id, word: p.word, good: p.good });
          if (p.good) {
            streak += 1;
            score += 10 + Math.min(streak, 5);
          } else {
            streak = 0;
            score -= 5;
            eatenWrong.push(p.word);
          }
          ctx.score(score);
        }
        if (correctLeft <= 0) setTimeout(over, 250);
      }

      function step(dx, dy) {
        if (done) return;
        var nx = me.x + dx, ny = me.y + dy;
        if (!free(nx, ny)) return;
        me.x = nx; me.y = ny;
        eat(nx, ny, false);
        paint();
      }

      // A ghost walks toward the nearest correct pellet rather than toward the
      // player. It is not hunting you; it is competing with you, which is what
      // the game is about.
      function ghostStep() {
        if (done) return;
        ghosts.forEach(function (g) {
          var best = null, bestD = Infinity;
          Object.keys(pellets).forEach(function (key) {
            if (!pellets[key].good) return;
            var parts = key.split(',');
            var px = +parts[0], py = +parts[1];
            var d = Math.abs(px - g.x) + Math.abs(py - g.y);
            if (d < bestD) { bestD = d; best = { x: px, y: py }; }
          });
          if (!best) return;

          var moved = false;
          if (ctx.rng() < GREEDY) {
            var dx = Math.sign(best.x - g.x), dy = Math.sign(best.y - g.y);
            if (dx && free(g.x + dx, g.y)) { g.x += dx; moved = true; }
            else if (dy && free(g.x, g.y + dy)) { g.y += dy; moved = true; }
          }
          if (!moved) {
            var dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
            var d = dirs[Math.floor(ctx.rng() * dirs.length)];
            if (free(g.x + d[0], g.y + d[1])) { g.x += d[0]; g.y += d[1]; }
          }
          eat(g.x, g.y, true);
        });
        paint();
      }

      function onKey(e) {
        if (done) return;
        var d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
                  a: [-1, 0], d: [1, 0], w: [0, -1], s: [0, 1] }[e.key];
        if (!d) return;
        e.preventDefault();
        e.stopPropagation();
        step(d[0], d[1]);
      }

      var touch = null;
      function onTouchStart(e) { touch = e.changedTouches[0]; }
      function onTouchEnd(e) {
        if (!touch) return;
        var t = e.changedTouches[0];
        var dx = t.clientX - touch.clientX, dy = t.clientY - touch.clientY;
        touch = null;
        if (Math.abs(dx) < 20 && Math.abs(dy) < 20) return;
        e.preventDefault();
        if (Math.abs(dx) > Math.abs(dy)) step(Math.sign(dx), 0);
        else step(0, Math.sign(dy));
      }

      window.addEventListener('keydown', onKey, true);
      grid.addEventListener('touchstart', onTouchStart, { passive: true });
      grid.addEventListener('touchend', onTouchEnd, { passive: false });

      // The shell owns the countdown that ends the run; this one only feeds the
      // clear bonus, so it does not have to be exact.
      var startedAt = performance.now();
      (function count() {
        if (done) return;
        left = Math.max(0, ctx.seconds - (performance.now() - startedAt) / 1000);
        raf = requestAnimationFrame(count);
      })();

      // Reduced motion still gets ghosts -- they are the game -- but slower, so
      // the board does not flicker with movement nobody asked to see. Either
      // way they hold off until the player has had a moment to read the banner
      // and find themselves on the board.
      ghostStart = setTimeout(function () {
        ghostTimer = setInterval(ghostStep, reduced ? GHOST_MS * 2 : GHOST_MS);
      }, HEAD_START_MS);
      paint();

      return { stop: stop };
    },
  });
})();
