/* Ship It: assemble a toolchain, then deploy it and read what broke.
 *
 * The other three games ask what you remember. This one asks you to make an
 * engineering decision and then live with it, which is the thing a quiz format
 * cannot do at all.
 *
 * The course wrote this game down before the game existed. lectures/l01 has a
 * table of Layer -> Tool -> the failure it prevents, introduced by the sentence
 * that is the whole design: "Each choice exists to prevent a specific failure,
 * and it is worth naming the failure rather than the feature." The learning
 * objective is already on the books as l01-o4, "Justify each component of the
 * course toolchain in terms of the failure it prevents."
 *
 * Three things stop this being eight multiple-choice questions in a trenchcoat,
 * and all three are quoted from the notes rather than invented:
 *
 *   the workload decides    The notes refuse to name a best database: "the
 *                           practitioner question is not which database is best
 *                           but what access pattern do I have." So a round draws
 *                           a workload, and PostgreSQL is right under streaming
 *                           writes and wrong under a wide analytical scan.
 *
 *   layers depend on layers MLflow logs a run whose environment was never
 *                           locked just as happily as one that was, and a
 *                           lockfile says nothing about system C libraries. So
 *                           picking the right tool for one layer can still leave
 *                           its failure unprevented. That is the difference
 *                           between a stack and a shopping list.
 *
 *   the failures are real   Each layer names a case study: the 15,841 cases that
 *                           fell off the end of a spreadsheet, the 386-degree
 *                           readings, the fresh checkout that broke three times.
 *
 * Scoring, and one detail that matters more than the numbers:
 *
 *     +25  a layer whose pick suits the workload
 *     +25  each cross-layer dependency that holds
 *     +50  a clean deploy
 *     +2   a second still on the clock when you deploy
 *
 * THE SCORE LOCKS THE MOMENT DEPLOY IS PRESSED, before the report animates. The
 * shell's clock calls finish() at zero and submits whatever the score is, so a
 * report still playing must never be able to cost points.
 */
(function () {
  'use strict';

  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  /* Pure, and separated out so it can be tested without a browser. It decides
   * what a student is told they got wrong, which is worth a test for the same
   * reason the clicker's scoring is. See arcade/test/deploy.test.mjs. */
  function evaluate(stack, workload, picks) {
    var prefers = (workload && workload.prefers) || {};
    var penalises = (workload && workload.penalises) || {};
    var byLayer = {};

    var layers = (stack.layers || []).map(function (spec) {
      var pick = picks[spec.layer];
      var opt = null;
      (spec.options || []).forEach(function (o) { if (o.text === pick) opt = o; });

      var ok = false, why = '', cite = '';
      if (!opt) {
        // An empty slot ships nothing, and nothing prevents nothing. A slot
        // holding something that was never on offer is a different fault --
        // the UI cannot produce it, but a replayed transcript could -- and
        // saying "nothing was chosen" about it would be a lie in the report.
        why = pick
          ? pick + ' is not one of the options for this layer.'
          : 'Nothing was chosen for this layer.';
      } else if (!opt.ok) {
        why = opt.because;
        cite = opt.cite;
      } else if (prefers[spec.layer] && prefers[spec.layer].indexOf(pick) < 0) {
        // A real tool, in its own layer, wrong for THIS workload. The most
        // interesting way to be wrong in the whole game.
        ok = false;
        why = (penalises[spec.layer] || {}).because || '';
        cite = (penalises[spec.layer] || {}).from || '';
      } else {
        ok = true;
      }

      byLayer[spec.layer] = ok;
      return {
        layer: spec.layer, pick: pick || null, ok: ok,
        prevents: spec.prevents, why: why, cite: cite, 'case': spec['case'] || '',
      };
    });

    // A dependency holds only when BOTH ends are right. Picking MLflow and
    // shipping requirements.txt does not buy you attributable results.
    var requires = (stack.requires || []).map(function (r) {
      var held = !!byLayer[r.layer] && !!byLayer[r.needs];
      return { layer: r.layer, needs: r.needs, held: held, because: r.because, cite: r.cite };
    });

    var layersOk = layers.filter(function (l) { return l.ok; }).length;
    var reqsOk = requires.filter(function (r) { return r.held; }).length;
    var clean = layersOk === layers.length && reqsOk === requires.length && layers.length > 0;

    return {
      layers: layers, requires: requires,
      layersOk: layersOk, reqsOk: reqsOk, clean: clean,
      points: 25 * layersOk + 25 * reqsOk + (clean ? 50 : 0),
    };
  }

  Arcade.register('deploy', {
    seconds: 90,

    pick: function (items) {
      return items.filter(function (i) {
        return i.stack && i.stack.layers && i.stack.layers.length >= 3;
      });
    },

    mount: function (root, ctx) {
      var item = ctx.items[0];
      var stack = item.stack;
      var workloads = stack.workloads || [];
      var workload = workloads.length
        ? workloads[Math.floor(ctx.rng() * workloads.length)]
        : { prefers: {}, penalises: {}, text: '' };

      var picks = {};
      var focus = 0, done = false, deployed = false;
      var startedAt = performance.now();

      root.textContent = '';
      root.classList.add('ship');

      var brief = el('div', 'ship-brief');
      var briefP = el('p', 'ship-brief-text', stack.brief);
      var loadP = el('p', 'ship-workload', workload.text);
      brief.appendChild(briefP);
      brief.appendChild(loadP);

      var sheet = el('div', 'ship-sheet');
      var tray = el('div', 'ship-tray');
      var deployBtn = el('button', 'ship-deploy', 'Deploy');
      deployBtn.type = 'button';

      root.appendChild(brief);
      root.appendChild(sheet);
      root.appendChild(tray);
      root.appendChild(deployBtn);

      /* --- the build sheet --- */

      var rows = stack.layers.map(function (spec, i) {
        var row = el('button', 'ship-slot');
        row.type = 'button';
        row.appendChild(el('span', 'ship-layer', spec.layer));
        var val = el('span', 'ship-pick', '—');
        row.appendChild(val);
        row.addEventListener('click', function () { setFocus(i); });
        sheet.appendChild(row);
        return { row: row, val: val, spec: spec };
      });

      function paintSheet() {
        rows.forEach(function (r, i) {
          r.row.className = 'ship-slot' +
            (i === focus ? ' is-focus' : '') +
            (picks[r.spec.layer] ? ' is-filled' : '');
          r.val.textContent = picks[r.spec.layer] || '—';
        });
        var filled = Object.keys(picks).length;
        deployBtn.textContent = filled === rows.length
          ? 'Deploy'
          : 'Deploy (' + filled + '/' + rows.length + ')';
      }

      /* --- the options for the focused layer --- */

      function paintTray() {
        tray.textContent = '';
        var spec = rows[focus].spec;
        // The failure this layer exists to prevent, named above its options,
        // because that is the whole point the lecture makes about it.
        tray.appendChild(el('div', 'ship-prevents', 'prevents: ' + spec.prevents));

        var opts = el('div', 'ship-options');
        // Shuffled with the run's seeded rng so the right answer is not always
        // in the same place, and the order is reconstructable from the run id.
        var order = spec.options.map(function (_, i) { return i; });
        for (var i = order.length - 1; i > 0; i--) {
          var j = Math.floor(ctx.rng() * (i + 1));
          var t = order[i]; order[i] = order[j]; order[j] = t;
        }
        order.forEach(function (idx, slot) {
          var o = spec.options[idx];
          var b = el('button', 'ship-option' + (picks[spec.layer] === o.text ? ' is-picked' : ''));
          b.type = 'button';
          b.appendChild(el('span', 'ship-num', String(slot + 1)));
          b.appendChild(el('span', 'ship-opt-text', o.text));
          b.addEventListener('click', function () { choose(o.text); });
          opts.appendChild(b);
        });
        tray.appendChild(opts);
      }

      function setFocus(i) {
        if (done) return;
        focus = (i + rows.length) % rows.length;
        paintSheet();
        paintTray();
      }

      function choose(text) {
        if (done) return;
        var spec = rows[focus].spec;
        picks[spec.layer] = text;
        ctx.record({ id: item.id, layer: spec.layer, pick: text });
        paintSheet();
        paintTray();
        // Move on by itself: the player is filling a sheet, not administering
        // one, and eight layers in ninety seconds has no time for a second click.
        var next = rows.findIndex(function (r, i) { return i > focus && !picks[r.spec.layer]; });
        if (next < 0) next = rows.findIndex(function (r) { return !picks[r.spec.layer]; });
        if (next >= 0) setFocus(next);
      }

      /* --- deploy --- */

      function deploy() {
        if (done || deployed) return;
        deployed = true;

        var left = Math.max(0, ctx.seconds - (performance.now() - startedAt) / 1000);
        var result = evaluate(stack, workload, picks);
        // Locked here, before a single line of the report is drawn.
        ctx.score(result.points + 2 * Math.round(left));

        report(result);
      }

      function report(result) {
        done = true;
        window.removeEventListener('keydown', onKey, true);
        brief.hidden = sheet.hidden = tray.hidden = deployBtn.hidden = true;

        var box = el('div', 'ship-report');
        box.appendChild(el('h4', 'ship-verdict' + (result.clean ? ' is-clean' : ''),
          result.clean
            ? 'Shipped clean.'
            : (result.layers.length - result.layersOk) + ' of ' + result.layers.length +
              ' layers let a known failure through.'));

        var list = el('ol', 'ship-lines');
        result.layers.forEach(function (l) {
          var li = el('li', 'ship-line ' + (l.ok ? 'is-ok' : 'is-bad'));
          li.appendChild(el('span', 'ship-line-layer', l.layer));
          li.appendChild(el('span', 'ship-line-pick', l.pick || 'nothing'));
          li.appendChild(el('span', 'ship-line-what',
            (l.ok ? 'prevented: ' : '') + l.prevents));
          if (!l.ok && l.why) li.appendChild(el('p', 'ship-line-why', l.why));
          if (!l.ok && l['case']) li.appendChild(el('p', 'ship-line-case', l['case']));
          list.appendChild(li);
        });
        box.appendChild(list);

        // The cross-layer lines come last because they are the surprise: a
        // player who picked every tool right can still land here.
        result.requires.forEach(function (r) {
          if (r.held) return;
          var d = el('div', 'ship-depends');
          d.appendChild(el('strong', null, r.layer + ' needed ' + r.needs + '.'));
          if (r.because) d.appendChild(el('p', null, r.because));
          box.appendChild(d);
        });

        if (result.clean && stack.epilogue && stack.epilogue.text) {
          // Winning is not the end of the argument, and the notes say so.
          var ep = el('p', 'ship-epilogue');
          ctx.markdown(ep, stack.epilogue.text + '.');
          box.appendChild(ep);
        }

        root.appendChild(box);
        if (!reduced) box.classList.add('is-animating');
        ctx.end();
      }

      deployBtn.addEventListener('click', deploy);

      // Captured, as in every other game here: a MARP deck steers on the arrow
      // keys and would otherwise walk off this slide mid-build.
      function onKey(e) {
        if (done) return;
        if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
          e.preventDefault(); e.stopPropagation(); setFocus(focus + 1); return;
        }
        if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
          e.preventDefault(); e.stopPropagation(); setFocus(focus - 1); return;
        }
        if (e.key === 'Enter') {
          e.preventDefault(); e.stopPropagation(); deploy(); return;
        }
        var n = parseInt(e.key, 10);
        if (!n || n < 1) return;
        var opts = tray.querySelectorAll('.ship-option');
        if (n > opts.length) return;
        e.preventDefault(); e.stopPropagation();
        opts[n - 1].click();
      }

      window.addEventListener('keydown', onKey, true);
      setFocus(0);

      return {
        stop: function () {
          done = true;
          window.removeEventListener('keydown', onKey, true);
        },
      };
    },
  });

  // For the test harness, which drives this file rather than a copy of its rules.
  Arcade.deployEvaluate = evaluate;
})();
