/* Boss Rush: one board across every game, so the arcade is one thing.
 *
 * Not a game. There is no run, no clock and nothing to submit: it reads the
 * per-game boards the Worker already serves and combines them in the browser,
 * which is why adding it needed no server change and no redeploy.
 *
 *     <div class="arcade-rush" data-read="https://clicker.f26-06763.workers.dev"
 *          data-games="l03-whackabug,all-pipeline,l01-chase" data-top="10"></div>
 *
 * POINTS BY PLACING, not by score. Ranking on raw score would let one game
 * decide the whole board -- Concept Chase can pay out two hundred while
 * Pipeline Panic pays thirty, so a rush ranked on score is a Concept Chase
 * ladder with decoration. Placing normalizes that away: what carries across
 * games is where you came, not what the scoring formula happened to be.
 *
 *     1st 10, 2nd 8, 3rd 6, then 5, 4, 3, 2, 1 -- and 1 for any place after
 *     that, because turning up to a game and finishing it should never be
 *     worth exactly as much as not playing it at all.
 *
 * Ties break on games played, then on name, so two equal totals never swap
 * places between two reads of the same data in front of a room.
 */
(function () {
  'use strict';

  var PLACING = [10, 8, 6, 5, 4, 3, 2, 1];

  function pointsFor(rank) {
    if (!(rank >= 1)) return 0;
    return PLACING[rank - 1] || 1;
  }

  /* Pure, and separated out so it can be tested without a browser: this rule
   * decides what goes on a wall, which is the same reason the clicker's
   * scoring lives behind a test. See arcade/test/bossrush.test.mjs. */
  function rushStandings(boards, top) {
    var by = {};
    (boards || []).forEach(function (b) {
      ((b && b.standings) || []).forEach(function (s) {
        if (!s || !s.name) return;
        var rec = by[s.name] || (by[s.name] = { name: s.name, points: 0, games: 0, best: null });
        rec.points += pointsFor(s.rank);
        rec.games += 1;
        if (rec.best === null || s.rank < rec.best) rec.best = s.rank;
      });
    });

    var rows = Object.keys(by).map(function (k) { return by[k]; });
    rows.sort(function (a, b) {
      return b.points - a.points || b.games - a.games || a.name.localeCompare(b.name);
    });
    rows.forEach(function (r, i) { r.rank = i + 1; });
    return top ? rows.slice(0, top) : rows;
  }

  function setup(el) {
    var api = (el.dataset.read || '').replace(/\/+$/, '');
    var games = (el.dataset.games || '').split(',')
      .map(function (g) { return g.trim(); })
      .filter(Boolean);
    var top = parseInt(el.dataset.top, 10) || 10;
    if (!api || !games.length) {
      el.textContent = 'This board is not configured: it needs data-read and data-games.';
      return;
    }

    el.textContent = '';
    var body = document.createElement('div');
    body.className = 'arcade-board';
    el.appendChild(body);

    var refresh = document.createElement('button');
    refresh.className = 'arcade-board-refresh';
    refresh.type = 'button';
    refresh.textContent = 'Refresh';
    el.appendChild(refresh);

    function draw() {
      // The semester window, not the rolling one: a rush is a season standing,
      // and half its games will not have been played in the last six hours.
      Promise.all(games.map(function (g) {
        return fetch(api + '/board?g=' + encodeURIComponent(g) + '&all=1&top=200', { cache: 'no-store' })
          .then(function (r) { return r.json(); })
          // One unreachable game must not blank the whole board.
          .catch(function () { return { standings: [] }; });
      })).then(function (boards) {
        render(boards);
      }).catch(function () {
        body.textContent = '';
        var e = document.createElement('div');
        e.className = 'arcade-board-empty';
        e.textContent = 'Could not reach the server.';
        body.appendChild(e);
      });
    }

    function render(boards) {
      var rows = rushStandings(boards, top);
      var mine = Arcade.myName();
      body.textContent = '';

      var h = document.createElement('div');
      h.className = 'arcade-board-title';
      h.textContent = 'Boss Rush';
      body.appendChild(h);

      if (!rows.length) {
        var empty = document.createElement('div');
        empty.className = 'arcade-board-empty';
        empty.textContent = 'No named runs in any game yet.';
        body.appendChild(empty);
        return;
      }

      var ol = document.createElement('ol');
      ol.className = 'arcade-board-list';
      rows.forEach(function (r) {
        var li = document.createElement('li');
        if (mine && r.name === mine) li.className = 'is-me';
        // Every name here was typed by a student, so every one goes in through
        // textContent.
        [['rank', r.rank], ['who', r.name], ['pts', r.points],
         ['secs', r.games + '/' + boards.length]].forEach(function (pair) {
          var span = document.createElement('span');
          span.className = pair[0];
          span.textContent = pair[1];
          li.appendChild(span);
        });
        ol.appendChild(li);
      });
      body.appendChild(ol);

      var foot = document.createElement('div');
      foot.className = 'arcade-board-foot';
      foot.textContent = boards.length + ' games · points by placing, not by score';
      body.appendChild(foot);
    }

    refresh.addEventListener('click', draw);
    draw();
  }

  // The shell calls this for every .arcade-rush element it finds.
  Arcade.rush = setup;
  // Exposed for the test harness, which reads this file rather than a copy of
  // its rules.
  Arcade.rushStandings = rushStandings;
})();
