/* Interactive figures for the notes and the decks.
 *
 * One file serves both. Jupyter Book 1 loads every .js file under _static/ on
 * every page, and CI copies _static/*.js beside each rendered MARP deck, the same
 * way it copies clicker-slide.js, so a deck includes it with
 *
 *     <script src="l12-widget-data.js"></script>
 *     <script src="widgets.js"></script>
 *
 * Markup, in a notes page or on a slide:
 *
 *     <div class="cw" data-widget="conv1d" data-source="l12"></div>
 *
 * On a slide add the `compact` class, which drops the figure's own title and
 * footnote and caps its height.
 *
 * data-widget picks the figure from WIDGETS below. data-source names the entry in
 * window.COURSE_WIDGET_DATA that holds its numbers, which a lecture's
 * figures/make_widget_data.py generates; nothing in this file is lecture data.
 *
 * Rules the figures keep:
 *   - nothing animates until the reader presses Play, and every animation can
 *     also be stepped and scrubbed, so a figure works for someone who reads
 *     slowly, for a projector, and for prefers-reduced-motion;
 *   - every figure writes what it is showing into a live text line, so the
 *     numbers are readable without the picture;
 *   - no network access. The data arrives as a script, so a deck opened from
 *     disk works exactly as it does on the site.
 */
(function () {
  'use strict';

  var SVGNS = 'http://www.w3.org/2000/svg';

  var CSS = [
    '.cw{--cw-accent:#1f6fb2;--cw-accent2:#c2410c;--cw-green:#2b8a3e;',
    '--cw-muted:rgba(128,128,128,.35);--cw-faint:rgba(128,128,128,.14);',
    '--cw-bg:rgba(128,128,128,.06);margin:1.2em 0;padding:.8em 1em;',
    'border:1px solid var(--cw-muted);border-radius:6px;background:var(--cw-bg);',
    'font-size:.92em;line-height:1.35}',
    'html[data-theme="dark"] .cw{--cw-accent:#6cb4ff;--cw-accent2:#ff9a5c;--cw-green:#69db7c}',
    '.cw-title{font-weight:600;margin:0 0 .4em}',
    '.cw svg{display:block;width:100%;height:auto;overflow:visible}',
    '.cw svg text{fill:currentColor;font-family:inherit}',
    '.cw-controls{display:flex;flex-wrap:wrap;gap:.4em .9em;align-items:center;margin:.5em 0 .2em}',
    '.cw-controls label{display:inline-flex;gap:.35em;align-items:center;white-space:nowrap}',
    '.cw button{font:inherit;padding:.15em .7em;border:1px solid var(--cw-muted);',
    'border-radius:4px;background:transparent;color:inherit;cursor:pointer}',
    '.cw button[aria-pressed="true"]{background:var(--cw-accent);border-color:var(--cw-accent);color:#fff}',
    '.cw select,.cw input[type=range]{font:inherit;color:inherit;background:transparent}',
    '.cw select option{color:#000}',
    '.cw-readout{font-variant-numeric:tabular-nums;margin-top:.35em;min-height:2.6em}',
    '.cw-note{opacity:.75;font-size:.9em;margin-top:.3em}',
    '.cw-missing{opacity:.7;font-style:italic}',
    '.cw .hot{cursor:pointer}',
    // On a slide the heading names the figure and the notes carry the fine
    // print, so the compact form drops both and caps the height to fit 720px.
    '.cw.compact{margin:.3em 0 0;padding:.4em .7em;font-size:.62em}',
    '.cw.compact .cw-title,.cw.compact .cw-note{display:none}',
    '.cw.compact svg{max-height:390px}',
    '.cw.compact .cw-readout{min-height:0}',
    '.cw.compact .cw-modes{display:none}'
  ].join('\n');

  // ------------------------------------------------------------------ helpers

  function el(tag, attrs, parent) {
    var node = document.createElementNS(SVGNS, tag);
    for (var k in attrs) node.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(node);
    return node;
  }

  function html(tag, attrs, parent, text) {
    var node = document.createElement(tag);
    for (var k in attrs) node.setAttribute(k, attrs[k]);
    if (text !== undefined) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }

  function scale(d0, d1, r0, r1) {
    return function (v) { return r0 + (v - d0) * (r1 - r0) / ((d1 - d0) || 1); };
  }

  function extent(xs) {
    var lo = Infinity, hi = -Infinity;
    xs.forEach(function (v) { if (v < lo) lo = v; if (v > hi) hi = v; });
    var pad = (hi - lo) * 0.08 || 0.5;
    return [lo - pad, hi + pad];
  }

  function fmt(v, d) { return (v >= 0 ? ' ' : '−') + Math.abs(v).toFixed(d === undefined ? 2 : d); }

  function sci(v) {
    if (v === 0) return '0';
    var e = Math.floor(Math.log10(Math.abs(v)));
    if (e >= -2 && e <= 3) return e >= 2 ? String(Math.round(v)) : v.toPrecision(3);
    return (v / Math.pow(10, e)).toFixed(1) + '×10^' + e;
  }

  function svgRoot(parent, w, h, label) {
    return el('svg', { viewBox: '0 0 ' + w + ' ' + h, role: 'img', 'aria-label': label }, parent);
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  function polyline(parent, xs, ys, attrs) {
    var pts = xs.map(function (x, i) { return x.toFixed(1) + ',' + ys[i].toFixed(1); }).join(' ');
    var a = { points: pts, fill: 'none' };
    for (var k in attrs) a[k] = attrs[k];
    return el('polyline', a, parent);
  }

  function text(parent, x, y, s, attrs) {
    var a = { x: x, y: y, 'font-size': 12 };
    for (var k in attrs) a[k] = attrs[k];
    var t = el('text', a, parent);
    t.textContent = s;
    return t;
  }

  // A Play/Pause + Step + scrubber trio driving an integer position.
  function player(controls, n, onChange, ms) {
    var pos = 0, timer = null;
    var play = html('button', { type: 'button' }, controls, 'Play');
    var step = html('button', { type: 'button' }, controls, 'Step');
    var lab = html('label', {}, controls);
    var range = html('input', { type: 'range', min: 0, max: n - 1, value: 0, 'aria-label': 'position' }, lab);
    function set(p) {
      pos = Math.max(0, Math.min(n - 1, p));
      range.value = pos;
      onChange(pos);
    }
    function stop() { clearInterval(timer); timer = null; play.textContent = 'Play'; }
    play.onclick = function () {
      if (timer) return stop();
      if (pos >= n - 1) set(0);
      play.textContent = 'Pause';
      timer = setInterval(function () { if (pos >= n - 1) stop(); else set(pos + 1); }, ms || 140);
    };
    step.onclick = function () { stop(); set(pos >= n - 1 ? 0 : pos + 1); };
    range.oninput = function () { stop(); set(+range.value); };
    return {
      set: set, stop: stop,
      resize: function (m) { n = m; range.max = n - 1; set(Math.min(pos, n - 1)); },
      get: function () { return pos; }
    };
  }

  function toggleGroup(controls, labels, initial, onPick) {
    var buttons = labels.map(function (lab, i) {
      var b = html('button', { type: 'button', 'aria-pressed': String(i === initial) }, controls, lab);
      b.onclick = function () {
        buttons.forEach(function (o) { o.setAttribute('aria-pressed', String(o === b)); });
        onPick(i);
      };
      return b;
    });
    return buttons;
  }

  function select(controls, label, options, initial, onPick) {
    var lab = html('label', {}, controls, label + ' ');
    var s = html('select', {}, lab);
    options.forEach(function (o, i) {
      var opt = html('option', { value: i }, s, o);
      if (i === initial) opt.selected = true;
    });
    s.onchange = function () { onPick(+s.value); };
    return s;
  }

  // ------------------------------------------------------------------ widgets

  var WIDGETS = {};

  /* A 1-D convolution sliding along one sensor. The kernel is a handful of
   * weights, the same at every position, and each output is their dot product
   * with the cycles under the window. */
  WIDGETS.conv1d = function (root, data) {
    var all = data.series.values;
    var xs = all.slice(all.length - 60);
    var n = xs.length;
    var k = 5, kind = 1;
    var W = 720, H = 344, L = 44, R = 12;
    html('div', { class: 'cw-title' }, root,
      'A convolution slides the same few weights along the window');
    var svg = svgRoot(root, W, H, 'Convolution kernel sliding along a sensor series');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Engine ' + data.series.engine + ', ' + data.series.sensor.replace('sensor', 'sensor ') +
      ', standardized, last 60 cycles before failure. "Valid" convolution, so the output is k−1 cycles shorter; ' +
      'the lecture model pads with zeros to keep the length. A trained network learns its kernels, 32 of them per layer, across all 14 sensors at once.');

    function kernel() {
      var w = [], i, c = (k - 1) / 2;
      if (kind === 0) for (i = 0; i < k; i++) w.push(1 / k);
      else if (kind === 1) {
        var ss = 0;
        for (i = 0; i < k; i++) ss += (i - c) * (i - c);
        for (i = 0; i < k; i++) w.push((i - c) / ss);
      } else {
        var seed = 7 + k;
        for (i = 0; i < k; i++) { seed = (seed * 16807) % 2147483647; w.push((seed / 2147483647 - 0.5) * 1.2); }
      }
      return w;
    }

    var p = player(controls, n - k + 1, draw, 120);
    select(controls, 'kernel', ['average (smooth)', 'least-squares slope', 'random, untrained'], kind,
      function (v) { kind = v; draw(p.get()); });
    select(controls, 'width k', ['3', '5', '7', '9'], 1, function (v) {
      k = [3, 5, 7, 9][v]; p.resize(n - k + 1); draw(p.get());
    });

    function draw(pos) {
      clear(svg);
      var w = kernel(), out = [], i, j;
      for (i = 0; i + k <= n; i++) {
        var s = 0;
        for (j = 0; j < k; j++) s += w[j] * xs[i + j];
        out.push(s);
      }
      var sx = scale(0, n - 1, L, W - R);
      var e1 = extent(xs), sy1 = scale(e1[0], e1[1], 130, 22);
      var e2 = extent(out), sy2 = scale(e2[0], e2[1], 300, 200);

      text(svg, L, 14, 'input: ' + data.series.sensor.replace('sensor', 'sensor ') + ' (standardized)', { 'font-size': 12 });
      el('rect', { x: sx(pos) - 4, y: 18, width: sx(pos + k - 1) - sx(pos) + 8, height: 118,
        fill: 'var(--cw-accent)', 'fill-opacity': 0.13, stroke: 'var(--cw-accent)', rx: 3 }, svg);
      polyline(svg, xs.map(function (_, i) { return sx(i); }), xs.map(sy1),
        { stroke: 'currentColor', 'stroke-opacity': 0.55, 'stroke-width': 1.2 });
      xs.forEach(function (v, i) {
        var inside = i >= pos && i < pos + k;
        el('circle', { cx: sx(i), cy: sy1(v), r: inside ? 3.6 : 2,
          fill: inside ? 'var(--cw-accent)' : 'currentColor', 'fill-opacity': inside ? 1 : 0.5 }, svg);
      });

      // Kernel weights, drawn as bars under the window they multiply.
      var kx0 = sx(pos), kw = Math.max(6, (sx(1) - sx(0)) * 0.7);
      var wmax = Math.max.apply(null, w.map(Math.abs)) || 1;
      text(svg, L - 38, 166, 'kernel', { 'font-size': 11 });
      w.forEach(function (v, j) {
        var h = 20 * v / wmax;
        el('rect', { x: sx(pos + j) - kw / 2, y: h >= 0 ? 165 - h : 165, width: kw, height: Math.abs(h) || 0.5,
          fill: v >= 0 ? 'var(--cw-accent)' : 'var(--cw-accent2)' }, svg);
      });
      el('line', { x1: kx0 - 6, x2: sx(pos + k - 1) + 6, y1: 165, y2: 165, stroke: 'currentColor', 'stroke-opacity': 0.4 }, svg);

      var centre = pos + (k - 1) / 2;
      el('line', { x1: sx(centre), x2: sx(centre), y1: 136, y2: sy2(out[pos]),
        stroke: 'var(--cw-accent)', 'stroke-dasharray': '3 3' }, svg);
      text(svg, L, 196, 'output: one number per window position', { 'font-size': 12 });
      var shown = out.slice(0, pos + 1);
      polyline(svg, shown.map(function (_, i) { return sx(i + (k - 1) / 2); }), shown.map(sy2),
        { stroke: 'var(--cw-accent)', 'stroke-width': 2 });
      polyline(svg, out.map(function (_, i) { return sx(i + (k - 1) / 2); }), out.map(sy2),
        { stroke: 'var(--cw-accent)', 'stroke-opacity': 0.15, 'stroke-width': 1 });
      el('circle', { cx: sx(centre), cy: sy2(out[pos]), r: 4, fill: 'var(--cw-accent)' }, svg);
      if (e2[0] < 0 && e2[1] > 0) {
        el('line', { x1: L, x2: W - R, y1: sy2(0), y2: sy2(0), stroke: 'currentColor', 'stroke-opacity': 0.25 }, svg);
      }
      [0, 20, 40, 59].forEach(function (i) {
        text(svg, sx(i), 322, String(n - 1 - i), { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 });
      });
      text(svg, (L + W - R) / 2, 338, 'cycles to failure', { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 });

      var terms = w.map(function (v, j) { return fmt(v) + '×' + fmt(xs[pos + j]); });
      readout.textContent = 'Window at ' + (n - 1 - pos) + '–' + (n - pos - k) +
        ' cycles to failure:  Σ wᵢxᵢ = ' + terms.join(' + ') + ' = ' + fmt(out[pos]) +
        '.  The same ' + k + ' weights are reused at all ' + out.length + ' positions.';
    }
    draw(0);
  };

  /* The vocabulary of a 2-D convolution on a small field: the kernel, stride
   * and padding, channels, and pooling. Each is a view of the same 8×8 grid,
   * small enough that every number can be read and checked by hand. The field
   * is an analytic hot spot, not lecture data, so this figure takes no data. */
  WIDGETS.conv2d = function (root) {
    var N = 8, W = 720, H = 300;
    var field = [], i, j;
    for (i = 0; i < N; i++) {
      field.push([]);
      for (j = 0; j < N; j++) {
        field[i].push(Math.round(2 + 7 * Math.exp(-((i - 2.5) * (i - 2.5) + (j - 5) * (j - 5)) / 5)));
      }
    }
    var KERNELS = [
      { name: 'vertical edge', w: [[-1, 0, 1], [-1, 0, 1], [-1, 0, 1]], div: 1 },
      { name: 'horizontal edge', w: [[-1, -1, -1], [0, 0, 0], [1, 1, 1]], div: 1 },
      { name: 'blur', w: [[1, 1, 1], [1, 1, 1], [1, 1, 1]], div: 9 }
    ];
    var MODES = ['kernel', 'stride and padding', 'channels', 'pooling'];
    var start = { kernel: 0, stride: 1, channels: 2, pooling: 3 }[root.getAttribute('data-mode')] || 0;
    var mode = start, kern = 0, stride = 2, pad = 1, poolMax = true;

    html('div', { class: 'cw-title' }, root, 'Kernel, stride, channels and pooling on a temperature field');
    var svg = svgRoot(root, W, H, 'Two-dimensional convolution on an 8 by 8 temperature field');
    // A slide shows one mode, so the compact form hides the switcher (see CSS).
    var row1 = html('div', { class: 'cw-controls cw-modes' }, root);
    var row2 = html('div', { class: 'cw-controls' }, root);
    var opts = html('span', { style: 'display:contents' }, row2);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'The input is a made-up 8×8 plate temperature field with one hot spot, in arbitrary units, ' +
      'small enough to check every number by hand. Orange is positive, blue negative.');
    toggleGroup(row1, MODES, mode, function (m) { mode = m; rebuild(); });
    var p = player(row2, 2, draw, 420);

    function conv(k, s, pd) {
      var o = Math.floor((N + 2 * pd - 3) / s) + 1, out = [];
      for (var r = 0; r < o; r++) {
        out.push([]);
        for (var c = 0; c < o; c++) {
          var sum = 0;
          for (var a = 0; a < 3; a++) for (var b = 0; b < 3; b++) {
            var ii = r * s - pd + a, jj = c * s - pd + b;
            if (ii >= 0 && ii < N && jj >= 0 && jj < N) sum += k.w[a][b] * field[ii][jj];
          }
          out[r].push(sum / k.div);
        }
      }
      return out;
    }
    function pool() {
      var out = [];
      for (var r = 0; r < N / 2; r++) {
        out.push([]);
        for (var c = 0; c < N / 2; c++) {
          var v = [field[2 * r][2 * c], field[2 * r][2 * c + 1], field[2 * r + 1][2 * c], field[2 * r + 1][2 * c + 1]];
          out[r].push(poolMax ? Math.max.apply(null, v) : v.reduce(function (x, y) { return x + y; }, 0) / 4);
        }
      }
      return out;
    }
    function num(v) { return Math.abs(v - Math.round(v)) < 1e-9 ? String(Math.round(v)).replace('-', '−') : v.toFixed(1).replace('-', '−'); }
    function maxAbs(g) {
      var m = 0;
      g.forEach(function (rw) { rw.forEach(function (v) { m = Math.max(m, Math.abs(v)); }); });
      return m || 1;
    }
    // One grid of numbered cells. `upto` hides cells past a flat index, so an
    // output map fills in as the kernel moves; `pd` draws a ring of padding zeros.
    function grid(x0, y0, cs, g, top, upto, pd) {
      var n = g.length + 2 * (pd || 0), m = top || maxAbs(g);
      for (var r = 0; r < n; r++) for (var c = 0; c < n; c++) {
        var gi = r - (pd || 0), gj = c - (pd || 0);
        var real = gi >= 0 && gi < g.length && gj >= 0 && gj < g.length;
        var x = x0 + c * cs, y = y0 + r * cs;
        if (!real) {
          el('rect', { x: x + 0.5, y: y + 0.5, width: cs - 1, height: cs - 1, rx: 2, fill: 'none',
            stroke: 'var(--cw-muted)', 'stroke-dasharray': '3 2' }, svg);
          text(svg, x + cs / 2, y + cs * 0.66, '0', { 'text-anchor': 'middle', 'font-size': cs * 0.4, opacity: 0.4 });
          continue;
        }
        var v = g[gi][gj], shown = upto === undefined || gi * g.length + gj <= upto;
        el('rect', { x: x + 0.5, y: y + 0.5, width: cs - 1, height: cs - 1, rx: 2,
          fill: shown ? (v < 0 ? 'var(--cw-accent)' : 'var(--cw-accent2)') : 'none',
          'fill-opacity': shown ? 0.08 + 0.62 * Math.abs(v) / m : 0, stroke: 'var(--cw-muted)' }, svg);
        if (shown) text(svg, x + cs / 2, y + cs * 0.66, num(v), { 'text-anchor': 'middle', 'font-size': cs * 0.4 });
      }
    }
    function box(x, y, w, h, color) {
      el('rect', { x: x, y: y, width: w, height: h, rx: 3, fill: 'none', stroke: color || 'var(--cw-accent2)',
        'stroke-width': 2.5 }, svg);
    }
    function link(x1, y1, x2, y2) {
      el('line', { x1: x1, y1: y1, x2: x2, y2: y2, stroke: 'currentColor', 'stroke-opacity': 0.35,
        'stroke-dasharray': '4 3' }, svg);
    }
    function label(x, y, s) { text(svg, x, y, s, { 'font-size': 12, opacity: 0.8 }); }

    function rebuild() {
      clear(opts);
      if (mode === 0 || mode === 2) {
        if (mode === 0) select(opts, 'kernel', KERNELS.map(function (k) { return k.name; }), kern,
          function (v) { kern = v; draw(p.get()); });
      } else if (mode === 1) {
        select(opts, 'stride', ['1', '2'], stride - 1, function (v) { stride = v + 1; rebuild(); });
        select(opts, 'padding', ['0', '1'], pad, function (v) { pad = v; rebuild(); });
      } else {
        toggleGroup(opts, ['max', 'average'], poolMax ? 0 : 1, function (v) { poolMax = v === 0; draw(p.get()); });
      }
      var n = mode === 3 ? 16 : mode === 1 ? Math.pow(Math.floor((N + 2 * pad - 3) / stride) + 1, 2) : 36;
      p.stop();
      p.resize(n);
      p.set(n - 1);  // start with the finished map; Play replays it from the corner
    }

    function draw(pos) {
      clear(svg);
      if (mode === 3) return drawPool(pos);
      if (mode === 2) return drawChannels(pos);
      var K = KERNELS[mode === 0 ? kern : 0], s = mode === 1 ? stride : 1, pd = mode === 1 ? pad : 0;
      var out = conv(K, s, pd), o = out.length, r = Math.floor(pos / o), c = pos % o;
      var cs = 26, x0 = 16, y0 = 24, n2 = N + 2 * pd;
      label(x0, 14, 'input, ' + N + '×' + N + (pd ? ', padded by ' + pd : ''));
      grid(x0, y0, cs, field, 9, undefined, pd);
      var kx = x0 + n2 * cs + 40, ky = y0 + (n2 - 3) * cs / 2;
      label(kx, ky - 10, 'kernel' + (K.div > 1 ? ' ÷ ' + K.div : ''));
      grid(kx, ky, cs, K.w, 1.6);
      var ox = kx + 3 * cs + 50;
      label(ox, 14, 'output, ' + o + '×' + o);
      grid(ox, y0, cs, out, maxAbs(out), pos);
      var wx = x0 + c * s * cs, wy = y0 + r * s * cs;
      box(wx, wy, 3 * cs, 3 * cs);
      box(ox + c * cs, y0 + r * cs, cs, cs);
      link(wx + 3 * cs, wy + 1.5 * cs, ox + c * cs, y0 + (r + 0.5) * cs);

      var terms = [];
      for (var a = 0; a < 3; a++) for (var b = 0; b < 3; b++) {
        var ii = r * s - pd + a, jj = c * s - pd + b;
        var x = ii >= 0 && ii < N && jj >= 0 && jj < N ? field[ii][jj] : 0;
        if (K.w[a][b] !== 0) terms.push(K.div > 1 ? String(x) : [K.w[a][b], Math.abs(K.w[a][b]) + '×' + x]);
      }
      var sum = K.div > 1 ? '(' + terms.join(' + ') + ') ÷ 9' : terms.map(function (t, n) {
        return (t[0] < 0 ? (n ? ' − ' : '−') : (n ? ' + ' : '')) + t[1];
      }).join('');
      if (mode === 0) {
        readout.textContent = 'Output row ' + (r + 1) + ', column ' + (c + 1) + ' = ' + sum + ' = ' + num(out[r][c]) +
          '.  The same 9 weights are reused at all ' + o * o + ' positions, so the whole map costs 9 parameters.';
      } else {
        readout.textContent = 'Output size = ⌊(n + 2p − k) / s⌋ + 1 = ⌊(' + N + ' + ' + 2 * pd + ' − 3) / ' + s +
          '⌋ + 1 = ' + o + ', so ' + o + '×' + o + '. ' + (s > 1 ? 'Stride ' + s + ' skips positions and shrinks each side. ' :
          'Stride 1 visits every position. ') + (pd ? 'Padding lets the kernel center on edge cells, which see zeros.' :
          'Without padding the map loses a border of ' + (s > 1 ? 'cells.' : 'one cell per side.'));
      }
    }

    function drawChannels(pos) {
      var outs = KERNELS.map(function (k) { return conv(k, 1, 0); });
      var r = Math.floor(pos / 6), c = pos % 6, cs = 26, x0 = 16, y0 = 40;
      label(x0, 30, 'input: 1 channel (temperature)');
      grid(x0, y0, cs, field, 9);
      var wx = x0 + c * cs, wy = y0 + r * cs;
      box(wx, wy, 3 * cs, 3 * cs);
      var vals = [];
      KERNELS.forEach(function (k, n) {
        var mx = 300 + n * 140, mcs = 20;
        label(mx, 30, 'channel ' + (n + 1));
        grid(mx + 33, 38, 18, k.w, 1.6);
        text(svg, mx + 60, 240, k.name, { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.8 });
        grid(mx, 104, mcs, outs[n], maxAbs(outs[n]), pos);
        box(mx + c * mcs, 104 + r * mcs, mcs, mcs);
        if (n === 0) link(wx + 3 * cs, wy + 1.5 * cs, mx + c * mcs, 104 + (r + 0.5) * mcs);
        vals.push(num(outs[n][r][c]));
      });
      el('path', { d: 'M300,250 v6 h400 v-6', fill: 'none', stroke: 'currentColor', 'stroke-opacity': 0.5 }, svg);
      text(svg, 500, 274, '3 kernels → 3 output channels, stacked as the next layer’s input',
        { 'text-anchor': 'middle', 'font-size': 12, opacity: 0.8 });
      readout.textContent = 'At row ' + (r + 1) + ', column ' + (c + 1) + ' the three kernels give ' + vals.join(', ') +
        ', one per channel.  Three 3×3×1 kernels plus biases: 30 parameters. ' +
        'A next layer’s kernel is 3×3×3, one slice per channel. A photo has 3 input channels (RGB); ' +
        'a CFD snapshot of u, v, p and T has 4.';
    }

    function drawPool(pos) {
      var out = pool(), r = Math.floor(pos / 4), c = pos % 4, cs = 30, x0 = 16, y0 = 24;
      label(x0, 14, 'input, 8×8');
      grid(x0, y0, cs, field, 9);
      var ox = 400, oy = y0 + 2 * cs;
      label(ox, oy - 10, 'pooled, 4×4');
      grid(ox, oy, cs, out, 9, pos);
      box(x0 + 2 * c * cs, y0 + 2 * r * cs, 2 * cs, 2 * cs);
      box(ox + c * cs, oy + r * cs, cs, cs);
      link(x0 + 2 * (c + 1) * cs, y0 + (2 * r + 1) * cs, ox + c * cs, oy + (r + 0.5) * cs);
      text(svg, 330, oy - 24, '2×2 ' + (poolMax ? 'max' : 'average') + ', stride 2', { 'text-anchor': 'middle', 'font-size': 12 });
      var v = [field[2 * r][2 * c], field[2 * r][2 * c + 1], field[2 * r + 1][2 * c], field[2 * r + 1][2 * c + 1]];
      readout.textContent = (poolMax ? 'max(' : 'mean(') + v.join(', ') + ') = ' + num(out[r][c]) +
        '.  8×8 becomes 4×4: a quarter of the values and no weights to learn. Each pooled cell covers 2×2 inputs, ' +
        'so a 3×3 kernel after pooling spans 6×6 of the original field.';
    }

    rebuild();
  };

  /* How far one output reaches back after a stack of convolutions, with and
   * without dilation, including the zero padding that "same" convolutions add
   * at the edges of the window. */
  WIDGETS.receptive = function (root, data) {
    var g = data.receptive, T = g.window, layers = g.layers;
    var k = g.kernel, dilated = false, sel = T - 1;
    var W = 720, H = 250;
    html('div', { class: 'cw-title' }, root, 'What one output of a stacked CNN can see');
    var svg = svgRoot(root, W, H, 'Receptive field of a stacked 1-D convolution');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Click a cell in the top row to pick an output. Hatched cells are padding zeros, not data. ' +
      'The lecture CNN is ' + layers + ' layers of width-' + g.kernel + ' kernels over a ' + T + '-cycle window, undilated.');
    toggleGroup(controls, ['plain', 'dilated 1, 2, 4'], 0, function (i) { dilated = i === 1; draw(); });
    select(controls, 'width k', ['3', '5', '7'], [3, 5, 7].indexOf(k), function (v) { k = [3, 5, 7][v]; draw(); });
    var lab = html('label', {}, controls, 'output cycle ');
    var range = html('input', { type: 'range', min: 1, max: T, value: sel + 1 }, lab);
    range.oninput = function () { sel = +range.value - 1; draw(); };

    var defs = el('defs', {}, svg);
    var pat = el('pattern', { id: 'cw-hatch', width: 5, height: 5, patternUnits: 'userSpaceOnUse',
      patternTransform: 'rotate(45)' }, defs);
    el('line', { x1: 0, y1: 0, x2: 0, y2: 5, stroke: 'currentColor', 'stroke-opacity': 0.45, 'stroke-width': 1.5 }, pat);
    var body = el('g', {}, svg);

    function draw() {
      clear(body);
      var dil = [], l;
      for (l = 0; l < layers; l++) dil.push(dilated ? Math.pow(2, l) : 1);
      var half = (k - 1) / 2, reach = 0;
      dil.forEach(function (d) { reach += half * d; });
      var span = T + 2 * reach, cw = (W - 80) / span, x0 = 70 + reach * cw;
      var rowY = function (r) { return 22 + (layers - r) * 52; };  // r = 0 input, layers = top
      var names = ['input'];
      for (l = 1; l <= layers; l++) names.push('conv ' + l);

      // Sets of touched positions, top down.
      var sets = [], cur = {};
      cur[sel] = true;
      sets[layers] = cur;
      for (l = layers; l >= 1; l--) {
        var next = {}, d = dil[l - 1];
        Object.keys(sets[l]).forEach(function (s) {
          for (var j = -half; j <= half; j++) next[+s + j * d] = true;
        });
        sets[l - 1] = next;
      }
      // Edges first, so cells sit on top of them.
      for (l = layers; l >= 1; l--) {
        var dd = dil[l - 1];
        Object.keys(sets[l]).forEach(function (s) {
          s = +s;
          for (var j = -half; j <= half; j++) {
            el('line', { x1: x0 + (s + 0.5) * cw, y1: rowY(l) + 7, x2: x0 + (s + j * dd + 0.5) * cw, y2: rowY(l - 1) + 7,
              stroke: 'var(--cw-accent)', 'stroke-opacity': 0.35, 'stroke-width': 0.8 }, body);
          }
        });
      }
      for (var r = 0; r <= layers; r++) {
        text(body, 4, rowY(r) + 11, names[r], { 'font-size': 11 });
        for (var i = -reach; i < T + reach; i++) {
          var real = i >= 0 && i < T, on = sets[r][i];
          if (!real && !on) continue;
          var rect = el('rect', { x: x0 + i * cw + 0.5, y: rowY(r), width: Math.max(1, cw - 1), height: 14, rx: 1.5,
            fill: !real ? 'url(#cw-hatch)' : on ? (r === layers ? 'var(--cw-accent2)' : 'var(--cw-accent)') : 'var(--cw-faint)',
            stroke: on ? 'var(--cw-accent)' : 'none', 'stroke-width': 0.6 }, body);
          if (r === layers && real) {
            rect.setAttribute('class', 'hot');
            (function (idx) { rect.onclick = function () { sel = idx; range.value = idx + 1; draw(); }; })(i);
          }
        }
      }
      var inputs = Object.keys(sets[0]).map(Number);
      var realIn = inputs.filter(function (i) { return i >= 0 && i < T; });
      var rf = 1 + 2 * reach;
      readout.textContent = 'Receptive field = 1 + (k−1)·Σ dilation = 1 + ' + (k - 1) + '×' +
        dil.reduce(function (a, b) { return a + b; }, 0) + ' = ' + rf + ' cycles.  The output at cycle ' + (sel + 1) +
        ' sees cycles ' + (Math.min.apply(null, realIn) + 1) + '–' + (Math.max.apply(null, realIn) + 1) +
        ': ' + realIn.length + ' real cycles of ' + T + ', plus ' + (inputs.length - realIn.length) + ' padding zeros.';
    }
    draw();
  };

  /* One leaky state unit stepping along the window: the recurrence a GRU
   * builds on, with the update gate held fixed so its effect is visible. */
  WIDGETS.recurrence = function (root, data) {
    var all = data.series.values, T = data.series.window;
    var wins = [all.slice(0, T), all.slice(all.length - T)];
    var labels = ['cycles 1–' + T + ' (healthy)', 'last ' + T + ' cycles (near failure)'];
    var which = 1, z = 0.2;
    var W = 720, H = 230, L = 44, R = 12;
    html('div', { class: 'cw-title' }, root, 'A recurrent state carries a summary forward one cycle at a time');
    var svg = svgRoot(root, W, H, 'A recurrent state updated one cycle at a time');
    var controls = html('div', { class: 'cw-controls' }, root);
    var controls2 = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'One state unit with a fixed update gate z. The lecture GRU has 64 units, reads all 14 sensors, and ' +
      'computes z (and a reset gate) from the input at every step, so it learns when to hold and when to update.');
    var p = player(controls, T, draw, 220);
    select(controls, 'window', labels, which, function (v) { which = v; draw(p.get()); });
    var lab = html('label', {}, controls2, 'update gate z ');
    var zr = html('input', { type: 'range', min: 0.02, max: 1, step: 0.01, value: z }, lab);
    var zv = html('span', {}, lab, z.toFixed(2));
    zr.oninput = function () { z = +zr.value; zv.textContent = z.toFixed(2); draw(p.get()); };

    function draw(t) {
      clear(svg);
      var xs = wins[which], hs = [], h = 0;
      xs.forEach(function (x) { h = (1 - z) * h + z * x; hs.push(h); });
      var e = extent(xs.concat([0])), sx = scale(0, T - 1, L, W - R), sy = scale(e[0], e[1], 190, 16);
      el('line', { x1: L, x2: W - R, y1: sy(0), y2: sy(0), stroke: 'currentColor', 'stroke-opacity': 0.2 }, svg);
      xs.forEach(function (x, i) {
        el('circle', { cx: sx(i), cy: sy(x), r: i === t ? 4.5 : 2.6,
          fill: i === t ? 'var(--cw-accent2)' : 'currentColor', 'fill-opacity': i <= t ? 0.8 : 0.25 }, svg);
      });
      var shown = hs.slice(0, t + 1);
      polyline(svg, [sx(0) - 14].concat(shown.map(function (_, i) { return sx(i); })),
        [sy(0)].concat(shown.map(sy)), { stroke: 'var(--cw-accent)', 'stroke-width': 2.4 });
      el('circle', { cx: sx(t), cy: sy(hs[t]), r: 5, fill: 'var(--cw-accent)' }, svg);
      if (t > 0) {
        el('line', { x1: sx(t - 1), y1: sy(hs[t - 1]), x2: sx(t) - 5, y2: sy(hs[t]), stroke: 'var(--cw-accent)',
          'stroke-width': 1, 'stroke-dasharray': '2 2' }, svg);
      }
      el('line', { x1: sx(t), y1: sy(xs[t]), x2: sx(t), y2: sy(hs[t]), stroke: 'var(--cw-accent2)',
        'stroke-width': 1, 'stroke-dasharray': '2 2' }, svg);
      text(svg, L, 12, '● input xₜ (sensor, standardized)', { 'font-size': 11, opacity: 0.8 });
      text(svg, L + 250, 12, '— state hₜ', { 'font-size': 11, fill: 'var(--cw-accent)' });
      for (var i = 0; i < T; i += 5) text(svg, sx(i), 212, String(i + 1), { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 });
      text(svg, W - R, 226, 'cycle in window', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
      var prev = t > 0 ? hs[t - 1] : 0;
      readout.textContent = 'Cycle ' + (t + 1) + ':  h = (1−z)·h_prev + z·x = ' + (1 - z).toFixed(2) +
        '×' + fmt(prev) + ' + ' + z.toFixed(2) + '×' + fmt(xs[t]) + ' = ' + fmt(hs[t]) +
        '.  Memory ≈ 1/z = ' + (1 / z).toFixed(1) + ' cycles; the prediction reads only the final state.';
    }
    draw(0);
  };

  /* How much of the loss's gradient reaches each earlier cycle when it has to
   * pass back through the recurrence once per step. */
  WIDGETS['gradient-flow'] = function (root, data) {
    var T = (data.series && data.series.window) || 30, a = 0.8, clip = false;
    var W = 720, H = 240, L = 56, R = 12, LO = -8, HI = 8;
    html('div', { class: 'cw-title' }, root, 'Backpropagation through time multiplies one factor per step');
    var svg = svgRoot(root, W, H, 'Gradient magnitude reaching each earlier cycle');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Idealized: the same factor at every step. In a plain RNN the factor is the recurrent weight times tanh′, ' +
      'usually below 1. A GRU’s state path multiplies by (1−z) instead, which training can hold near 1. ' +
      'Clipping rescales a gradient that is too large; nothing rescales one that has already vanished.');
    var lab = html('label', {}, controls, 'per-step factor ');
    var ar = html('input', { type: 'range', min: 0.5, max: 1.5, step: 0.01, value: a }, lab);
    var av = html('span', {}, lab, a.toFixed(2));
    ar.oninput = function () { a = +ar.value; av.textContent = a.toFixed(2); draw(); };
    var cl = html('label', {}, controls);
    var cb = html('input', { type: 'checkbox' }, cl);
    cl.appendChild(document.createTextNode(' clip at norm 1'));
    cb.onchange = function () { clip = cb.checked; draw(); };

    function draw() {
      clear(svg);
      var g = [], i;
      for (i = 0; i < T; i++) g.push(Math.pow(a, T - 1 - i));
      if (clip) {
        var norm = Math.sqrt(g.reduce(function (s, v) { return s + v * v; }, 0));
        if (norm > 1) g = g.map(function (v) { return v / norm; });
      }
      var sx = scale(0, T, L, W - R), sy = scale(LO, HI, 200, 28), bw = (W - L - R) / T * 0.75;
      for (var e = LO; e <= HI; e += 4) {
        el('line', { x1: L, x2: W - R, y1: sy(e), y2: sy(e), stroke: 'currentColor', 'stroke-opacity': e === 0 ? 0.45 : 0.12 }, svg);
        text(svg, L - 6, sy(e) + 4, '10^' + e, { 'text-anchor': 'end', 'font-size': 10, opacity: 0.75 });
      }
      g.forEach(function (v, i) {
        var lv = Math.max(LO, Math.min(HI, Math.log10(v)));
        var col = lv < -3 ? 'var(--cw-muted)' : lv > 3 ? 'var(--cw-accent2)' : 'var(--cw-accent)';
        el('rect', { x: sx(i) + 1, y: Math.min(sy(lv), sy(0)), width: bw, height: Math.abs(sy(lv) - sy(0)) || 1, fill: col }, svg);
      });
      for (i = 0; i < T; i += 5) text(svg, sx(i) + bw / 2, 218, String(i + 1), { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 });
      text(svg, W - R, 234, 'cycle in window (the loss is read at cycle ' + T + ')', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
      text(svg, L, 12, 'gradient reaching each cycle, |∂ loss / ∂ hₜ|, log scale', { 'font-size': 11 });
      var first = g[0], ratio = g[0] / g[T - 1], lr = Math.log10(ratio);
      var state = lr < -4 ? 'vanished: cycle 1 has effectively no say in what the network learns' :
        lr < -1 ? 'fading: early cycles barely move the weights' :
        lr > 3 ? 'exploding: one update would overshoot' : 'every cycle contributes';
      readout.textContent = 'Gradient reaching cycle 1 = ' + a.toFixed(2) + '^' + (T - 1) +
        (clip ? ' (then clipped)' : '') + ' = ' + sci(first) + ', ' + sci(ratio) +
        ' times what cycle ' + T + ' receives: ' + state + '.';
    }
    draw();
  };

  /* The same short window wired four ways: which cycles can influence which,
   * and whether the weights are shared across time. */
  WIDGETS.connectivity = function (root) {
    var T = 12, mode = 1, hover = T - 1;
    var W = 720, H = 250;
    var MODES = [
      { name: 'MLP', what: 'Every cycle has its own weight into every hidden unit. Nothing is shared across time, so a pattern learned at cycle 3 must be learned again at cycle 9.' },
      { name: 'CNN', what: 'Each hidden unit sees k neighbouring cycles through the same shared weights. Reach grows by k−1 per layer, then pooling or a readout combines positions.' },
      { name: 'GRU', what: 'One shared update applied cycle by cycle. Anything from early in the window reaches the prediction only by surviving every later update of the state.' },
      { name: 'Transformer', what: 'Every cycle can read every other in one layer, with weights computed from the content. Order is not built in: a position embedding is added to put it back.' }
    ];
    html('div', { class: 'cw-title' }, root, 'Four ways to wire the same window');
    var svg = svgRoot(root, W, H, 'Connectivity of four sequence models');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Drawn for a 12-cycle window and one hidden layer so the edges stay legible. Hover or tap a hidden unit to see what reaches it.');
    toggleGroup(controls, MODES.map(function (m) { return m.name; }), mode, function (i) { mode = i; draw(); });

    function draw() {
      clear(svg);
      var sx = function (i) { return 60 + i * (W - 120) / (T - 1); };
      var yIn = 210, yHid = 120, yOut = 30, i, j;
      var edges = [];   // [x1, y1, x2, y2, highlighted, weight]
      var hot = function (h) { return h === hover; };
      if (mode === 0) {
        for (j = 0; j < T; j++) for (i = 0; i < T; i++) edges.push([sx(i), yIn, sx(j), yHid, hot(j), 1]);
      } else if (mode === 1) {
        for (j = 0; j < T; j++) for (i = j - 1; i <= j + 1; i++) if (i >= 0 && i < T) edges.push([sx(i), yIn, sx(j), yHid, hot(j), 1]);
      } else if (mode === 2) {
        for (j = 0; j < T; j++) {
          edges.push([sx(j), yIn, sx(j), yHid, j <= hover, 1]);
          if (j > 0) edges.push([sx(j - 1), yHid, sx(j), yHid, j <= hover, 1]);
        }
      } else {
        for (j = 0; j < T; j++) for (i = 0; i < T; i++) {
          var w = Math.exp(-Math.abs(i - j) / 4) + 0.6 * Math.exp(-Math.abs(i - (T - 2)) / 1.5);
          edges.push([sx(i), yIn, sx(j), yHid, hot(j), w]);
        }
      }
      edges.forEach(function (e) {
        var attrs = { x1: e[0], y1: e[1], x2: e[2], y2: e[3], 'stroke-width': e[4] ? 1.6 : 0.8,
          stroke: e[4] ? 'var(--cw-accent)' : 'currentColor', 'stroke-opacity': e[4] ? Math.min(1, 0.35 + 0.5 * e[5]) : 0.12 };
        if (mode === 2 && e[1] === e[3]) {
          attrs['marker-end'] = 'url(#cw-arrow)';
        }
        el('line', attrs, svg);
      });
      var defs = el('defs', {}, svg);
      var m = el('marker', { id: 'cw-arrow', viewBox: '0 0 8 8', refX: 12, refY: 4, markerWidth: 6, markerHeight: 6, orient: 'auto' }, defs);
      el('path', { d: 'M0,0 L8,4 L0,8 z', fill: 'var(--cw-accent)' }, m);

      // Hidden layer to output.
      var readoutFrom = mode === 2 ? [T - 1] : Array.from({ length: T }, function (_, i) { return i; });
      readoutFrom.forEach(function (j) {
        el('line', { x1: sx(j), y1: yHid, x2: W / 2, y2: yOut, stroke: 'currentColor', 'stroke-opacity': 0.18 }, svg);
      });
      for (i = 0; i < T; i++) {
        el('circle', { cx: sx(i), cy: yIn, r: 7, fill: 'var(--cw-faint)', stroke: 'currentColor', 'stroke-opacity': 0.5 }, svg);
        var c = el('circle', { cx: sx(i), cy: yHid, r: 8, class: 'hot',
          fill: i === hover ? 'var(--cw-accent2)' : 'var(--cw-accent)', 'fill-opacity': i === hover ? 1 : 0.55 }, svg);
        (function (idx) { c.onmouseenter = c.onclick = function () { hover = idx; draw(); }; })(i);
      }
      el('circle', { cx: W / 2, cy: yOut, r: 10, fill: 'var(--cw-green)' }, svg);
      text(svg, W / 2 + 16, yOut + 4, 'predicted RUL', { 'font-size': 11 });
      text(svg, 4, yIn + 4, 'cycles', { 'font-size': 11 });
      text(svg, 4, yHid + 4, 'hidden', { 'font-size': 11 });
      var reach = mode === 0 || mode === 3 ? T : mode === 1 ? Math.min(hover + 2, T) - Math.max(hover - 1, 0) : hover + 1;
      readout.textContent = MODES[mode].name + ': ' + MODES[mode].what + '  Hidden unit ' + (hover + 1) +
        ' is reached by ' + reach + ' of ' + T + ' cycles' + (mode === 2 ? ', through ' + hover + ' later state updates for the earliest.' : '.');
      if (mode === 3) {
        text(svg, W - 12, H - 4, 'edge strength here is illustrative; the next figure shows trained weights',
          { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
      }
    }
    draw();
  };

  // ------------------------------------------------------- training figures

  // Small shared pieces for the training figures: a seeded generator, so a
  // figure draws the same noise on every load, and a unique id per clip path,
  // because a deck holds several copies of a figure in one document.
  function mulberry(seed) {
    return function () {
      seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function gauss(r) { return Math.sqrt(-2 * Math.log(1 - r())) * Math.cos(2 * Math.PI * r()); }
  var uid = 0;
  function clipRect(svg, x, y, w, h) {
    var id = 'cw-clip-' + (++uid);
    var cp = el('clipPath', { id: id }, el('defs', {}, svg));
    el('rect', { x: x, y: y, width: w, height: h }, cp);
    return el('g', { 'clip-path': 'url(#' + id + ')' }, svg);
  }
  function frame(svg, x, y, w, h) {
    el('rect', { x: x, y: y, width: w, height: h, fill: 'none', stroke: 'var(--cw-muted)' }, svg);
  }
  function legend(svg, x, y, items) {
    items.forEach(function (it, i) {
      var yy = y + i * 15;
      el('line', { x1: x, x2: x + 18, y1: yy - 4, y2: yy - 4, stroke: it[1], 'stroke-width': 2.2,
        'stroke-dasharray': it[2] || 'none' }, svg);
      text(svg, x + 23, yy, it[0], { 'font-size': 11 });
    });
  }
  var MUTED = 'rgba(128,128,128,.75)';

  /* Minibatch SGD on a bowl, one run with a decaying learning rate and one with
   * a constant rate, both fed the same noise. A constant rate keeps taking
   * noise-sized steps forever and settles into a cloud around the minimum; the
   * schedule shrinks the steps, so the cloud shrinks with them. */
  WIDGETS['lr-schedule'] = function (root) {
    var T = 150, A = 1, B = 8, SIG = 1.4, START = [-2.6, 1.6];
    var W = 720, H = 290, kind = 1, eta0 = 0.12;
    html('div', { class: 'cw-title' }, root, 'A learning-rate schedule against a constant rate, on a noisy bowl');
    var svg = svgRoot(root, W, H, 'Gradient descent paths and loss curves with and without a learning-rate schedule');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Loss = ½(x² + 8y²). Each step sees the true gradient plus random noise standing in for minibatch noise, ' +
      'the same noise for both runs. Along y the rate must stay below 2/8 = 0.25 or the steps grow instead of shrink.');
    toggleGroup(controls, ['step decay', 'cosine'], kind, function (i) { kind = i; recompute(); });
    var lab = html('label', {}, controls, 'starting rate η₀ ');
    var er = html('input', { type: 'range', min: 0.02, max: 0.3, step: 0.01, value: eta0 }, lab);
    var ev = html('span', {}, lab, eta0.toFixed(2));
    er.oninput = function () { eta0 = +er.value; ev.textContent = eta0.toFixed(2); recompute(); };
    var r = mulberry(7), noise = [];
    for (var t = 0; t < T; t++) noise.push([gauss(r), gauss(r)]);
    var runs;

    function f(p) { return 0.5 * (A * p[0] * p[0] + B * p[1] * p[1]); }
    function rate(k, t) {
      if (k === 'constant') return eta0;
      if (k === 0) return eta0 * Math.pow(0.2, Math.floor(3 * t / T));
      return eta0 * 0.5 * (1 + Math.cos(Math.PI * t / T));
    }
    function run(k) {
      var p = START.slice(), path = [p], loss = [f(p)], lr = [];
      for (var t = 0; t < T; t++) {
        var e = rate(k, t);
        lr.push(e);
        p = [p[0] - e * (A * p[0] + SIG * noise[t][0]), p[1] - e * (B * p[1] + SIG * noise[t][1])];
        p = p.map(function (v) { return Math.max(-1e4, Math.min(1e4, v)); });
        path.push(p);
        loss.push(f(p));
      }
      return { path: path, loss: loss, lr: lr };
    }
    function recompute() { runs = { s: run(kind), c: run('constant') }; draw(p.get()); }
    var p = player(controls, T + 1, function (i) { if (runs) draw(i); }, 45);

    function draw(pos) {
      clear(svg);
      // Left: the bowl, equal aspect.
      var px = 10, py = 18, pw = 330, ph = 262, u = pw / 6.2;
      var mx = function (x) { return px + pw / 2 + x * u; }, my = function (y) { return py + ph / 2 - y * u; };
      text(svg, px, 12, 'parameter path on the loss contours', { 'font-size': 11 });
      frame(svg, px, py, pw, ph);
      var g = clipRect(svg, px, py, pw, ph);
      [0.02, 0.1, 0.4, 1.2, 3, 6, 11].forEach(function (c) {
        el('ellipse', { cx: mx(0), cy: my(0), rx: Math.sqrt(2 * c / A) * u, ry: Math.sqrt(2 * c / B) * u,
          fill: 'none', stroke: 'currentColor', 'stroke-opacity': 0.18 }, g);
      });
      function path(run, color, w) {
        var pts = run.path.slice(0, pos + 1);
        polyline(g, pts.map(function (q) { return mx(q[0]); }), pts.map(function (q) { return my(q[1]); }),
          { stroke: color, 'stroke-width': w, 'stroke-opacity': 0.85 });
        var q = pts[pts.length - 1];
        el('circle', { cx: mx(q[0]), cy: my(q[1]), r: 4, fill: color }, g);
      }
      path(runs.c, MUTED, 1.2);
      path(runs.s, 'var(--cw-accent2)', 1.6);
      el('circle', { cx: mx(START[0]), cy: my(START[1]), r: 3, fill: 'none', stroke: 'currentColor' }, g);

      // Right top: the rate. Right bottom: the loss, log scale.
      var rx = 400, rw = W - rx - 10, sx = scale(0, T, rx, rx + rw);
      var ty = 18, th = 78, top = Math.max(0.3, eta0);
      var sy1 = scale(0, top, ty + th, ty);
      text(svg, rx, 12, 'learning rate', { 'font-size': 11 });
      frame(svg, rx, ty, rw, th);
      [runs.c, runs.s].forEach(function (run, i) {
        var n = Math.min(pos, T);
        var xs = [], ys = [];
        for (var t = 0; t < n; t++) { xs.push(sx(t)); ys.push(sy1(run.lr[t])); }
        if (n) polyline(svg, xs, ys, { stroke: i ? 'var(--cw-accent2)' : MUTED, 'stroke-width': i ? 2 : 1.4 });
      });
      el('line', { x1: rx, x2: rx + rw, y1: sy1(0.25), y2: sy1(0.25), stroke: 'var(--cw-accent)',
        'stroke-dasharray': '4 3', 'stroke-opacity': 0.8 }, svg);
      text(svg, rx + rw - 4, sy1(0.25) - 3, 'stability limit 0.25', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.8 });
      text(svg, rx - 4, sy1(top) + 9, top.toFixed(2), { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
      text(svg, rx - 4, sy1(0) + 3, '0', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });

      var by = 122, bh = 158, LO = -4, HI = 2;
      var sy2 = scale(LO, HI, by + bh, by);
      text(svg, rx, by - 6, 'loss, log scale', { 'font-size': 11 });
      frame(svg, rx, by, rw, bh);
      for (var e = LO; e <= HI; e += 2) {
        el('line', { x1: rx, x2: rx + rw, y1: sy2(e), y2: sy2(e), stroke: 'currentColor', 'stroke-opacity': 0.1 }, svg);
        text(svg, rx - 4, sy2(e) + 3, '10^' + e, { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
      }
      var g2 = clipRect(svg, rx, by, rw, bh);
      [runs.c, runs.s].forEach(function (run, i) {
        var xs = [], ys = [];
        for (var t = 0; t <= pos; t++) {
          xs.push(sx(t));
          ys.push(sy2(Math.max(LO - 1, Math.min(HI + 1, Math.log10(run.loss[t] + 1e-12)))));
        }
        polyline(g2, xs, ys, { stroke: i ? 'var(--cw-accent2)' : MUTED, 'stroke-width': i ? 1.8 : 1.3 });
      });
      text(svg, rx + rw, H - 2, 'step', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
      legend(svg, rx + rw - 118, by + 16, [[kind ? 'cosine' : 'step decay', 'var(--cw-accent2)'], ['constant', MUTED]]);

      var n = Math.min(30, pos + 1), ms = 0, mc = 0;
      for (var k = pos + 1 - n; k <= pos; k++) { ms += runs.s.loss[k] / n; mc += runs.c.loss[k] / n; }
      var name = kind ? 'cosine' : 'step decay';
      if (mc > 1e3 && ms > 1e3) {
        readout.textContent = 'Both runs diverge: η₀ = ' + eta0.toFixed(2) + ' is above the stability limit, so every step overshoots by more than it corrects.';
      } else if (mc > 1e3) {
        readout.textContent = 'The constant rate η₀ = ' + eta0.toFixed(2) + ' is above the stability limit and diverges. ' +
          'The ' + name + ' run survives only because its rate falls below 0.25 before the overshoots grow too large.';
      } else {
        readout.textContent = 'Step ' + pos + ': rate ' + (pos ? rate(kind, Math.min(pos, T) - 1) : eta0).toFixed(3) + ' (' + name + ') vs ' +
          eta0.toFixed(3) + ' (constant). Mean loss over the last ' + n + ' steps: ' + sci(ms) + ' with ' + name +
          ', ' + sci(mc) + ' constant' + (mc > ms ? ', ' + (mc / ms).toFixed(1) + '× lower with the schedule.' : '.');
      }
    }
    recompute();
    p.set(T);
  };

  /* Early stopping replayed on real learning curves: the lecture's GRU trained
   * for the whole epoch budget with stopping switched off, so the part a stopped
   * run never sees is available to draw. Epochs arrive one at a time; the
   * counter is epochs since the best validation score, and the run stops when it
   * reaches the patience and restores the best weights. */
  WIDGETS['early-stopping'] = function (root, data) {
    var tr = data.training, E = tr.max_epochs, W = 720, H = 290;
    var sched = 'constant', seed = 0, pat = tr.patience;
    html('div', { class: 'cw-title' }, root, 'Early stopping: keep the best epoch, stop when it stops improving');
    var svg = svgRoot(root, W, H, 'Training and validation error per epoch with the early-stopping point');
    var row1 = html('div', { class: 'cw-controls' }, root);
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'The lecture’s GRU on FD001, run for all ' + E + ' epochs with stopping switched off, so the epochs after the stop ' +
      'can be drawn (faint). Validation engines are held out by engine, as in the lecture. Seed changes the ' +
      'validation engines and the initial weights.');
    toggleGroup(row1, ['constant rate', 'cosine schedule'], 0, function (i) { sched = i ? 'cosine' : 'constant'; draw(p.get()); });
    select(row1, 'seed', [1, 2, 3, 4, 5].map(String), 0, function (i) { seed = i; draw(p.get()); });
    var lab = html('label', {}, controls, 'patience ');
    var pr = html('input', { type: 'range', min: 1, max: 40, step: 1, value: pat }, lab);
    var pv = html('span', {}, lab, String(pat));
    pr.oninput = function () { pat = +pr.value; pv.textContent = String(pat); draw(p.get()); };
    var p = player(controls, E, function (i) { draw(i); }, 150);

    // Replay the rule exactly: best so far, epochs since best, stop at patience.
    function replay(val) {
      var best = Infinity, be = 0, trace = [];
      for (var i = 0; i < val.length; i++) {
        if (val[i] < best) { best = val[i]; be = i; }
        trace.push({ best: best, be: be, since: i - be });
        if (i - be >= pat) return { stop: i, be: be, best: best, trace: trace };
      }
      return { stop: val.length - 1, be: be, best: best, trace: trace };
    }

    function draw(pos) {
      clear(svg);
      var run = tr.runs[sched], val = run.val[seed], trn = run.train[seed], rp = replay(val);
      var now = Math.min(pos, rp.stop), stopped = pos >= rp.stop;
      var px = 44, pw = W - px - 14, py = 14, ph = 196, lry = 236, lrh = 36;
      var sx = scale(0, E - 1, px, px + pw);
      var lo = Math.floor(Math.min.apply(null, trn.concat(val)) - 1), hi = Math.ceil(Math.max.apply(null, val.slice(2)) + 1);
      var sy = scale(lo, hi, py + ph, py);
      frame(svg, px, py, pw, ph);
      for (var y = Math.ceil(lo / 2) * 2; y <= hi; y += 2) {
        el('line', { x1: px, x2: px + pw, y1: sy(y), y2: sy(y), stroke: 'currentColor', 'stroke-opacity': 0.08 }, svg);
        text(svg, px - 5, sy(y) + 3, String(y), { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
      }
      text(svg, px, py - 3, 'RMSE, cycles', { 'font-size': 10, opacity: 0.7 });
      var g = clipRect(svg, px, py, pw, ph);
      function curve(v, col, w, from, to, op) {
        var xs = [], ys = [];
        for (var i = from; i <= to; i++) { xs.push(sx(i)); ys.push(sy(v[i])); }
        if (xs.length > 1) polyline(g, xs, ys, { stroke: col, 'stroke-width': w, 'stroke-opacity': op });
      }
      curve(trn, MUTED, 1.2, 0, E - 1, 0.25);
      curve(val, 'var(--cw-accent)', 1.2, 0, E - 1, 0.22);
      curve(trn, MUTED, 1.8, 0, now, 1);
      curve(val, 'var(--cw-accent)', 2, 0, now, 1);
      var t = rp.trace[now];
      el('line', { x1: sx(0), x2: sx(now), y1: sy(t.best), y2: sy(t.best), stroke: 'var(--cw-green)', 'stroke-dasharray': '3 3' }, g);
      el('rect', { x: sx(t.be), y: py, width: Math.max(0, sx(now) - sx(t.be)), height: ph, fill: 'var(--cw-accent2)', 'fill-opacity': 0.08 }, g);
      el('circle', { cx: sx(t.be), cy: sy(t.best), r: 5, fill: 'var(--cw-green)' }, g);
      text(svg, sx(t.be), sy(t.best) + 17, stopped ? 'restored: epoch ' + (t.be + 1) : 'best so far', { 'text-anchor': 'middle', 'font-size': 11, fill: 'var(--cw-green)' });
      if (stopped) {
        el('line', { x1: sx(rp.stop), x2: sx(rp.stop), y1: py, y2: py + ph, stroke: 'var(--cw-accent2)', 'stroke-width': 1.5 }, svg);
        text(svg, sx(rp.stop) + 4, py + 12, 'stop', { 'font-size': 11, fill: 'var(--cw-accent2)' });
      }
      var gmin = Math.min.apply(null, val), gi = val.indexOf(gmin);
      el('circle', { cx: sx(gi), cy: sy(gmin), r: 3.5, fill: 'none', stroke: 'var(--cw-accent)', 'stroke-opacity': 0.6 }, g);
      legend(svg, px + pw - 150, py + 16, [['validation', 'var(--cw-accent)'], ['training', MUTED]]);

      var sl = scale(0, tr.runs.cosine.lr[0], lry + lrh, lry);
      text(svg, px, lry - 4, 'learning rate', { 'font-size': 10, opacity: 0.7 });
      frame(svg, px, lry, pw, lrh);
      ['constant', 'cosine'].forEach(function (k) {
        var lr = tr.runs[k].lr, on = k === sched;
        polyline(svg, lr.map(function (_, i) { return sx(i); }), lr.map(function (v) { return sl(v); }),
          { stroke: on ? 'var(--cw-accent2)' : MUTED, 'stroke-width': on ? 1.8 : 1, 'stroke-opacity': on ? 1 : 0.5 });
      });
      el('line', { x1: sx(now), x2: sx(now), y1: lry, y2: lry + lrh, stroke: 'currentColor', 'stroke-opacity': 0.5 }, svg);
      text(svg, px + pw, H - 2, 'epoch', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });

      var lrNow = run.lr[now], lr0 = run.lr[0];
      if (!stopped) {
        readout.textContent = 'Epoch ' + (now + 1) + ': validation ' + val[now].toFixed(2) + ', best ' + t.best.toFixed(2) +
          ' at epoch ' + (t.be + 1) + '. Epochs since best: ' + t.since + ' of ' + pat + '.';
      } else {
        readout.textContent = 'Stopped at epoch ' + (rp.stop + 1) + ' and restored epoch ' + (rp.be + 1) + ' (validation ' +
          rp.best.toFixed(2) + '). Training all ' + E + ' epochs ends at ' + val[E - 1].toFixed(2) + '; the best anywhere is ' +
          gmin.toFixed(2) + ' at epoch ' + (gi + 1) + '. Learning rate at the stop: ' + Math.round(100 * lrNow / lr0) + '% of its start.';
      }
    }
    p.set(E - 1);
  };

  /* A loss with a steep wall, after Fig. 6 and section 3 of Pascanu, Mikolov and
   * Bengio (2013): gradient descent reaches the wall, the gradient there is huge,
   * and one unclipped step throws the parameter far past the minimum. Clipping
   * keeps the direction and caps the length. The right panel is the real
   * gradient norm of the lecture's GRU, when that data is present. */
  WIDGETS.clipping = function (root, data) {
    var T = 12, ETA = 0.5, S = 16, c = 1, W = 720, H = 270, YM = 16;
    var real = data && data.training ? data.training : null;
    html('div', { class: 'cw-title' }, root, 'Gradient clipping caps the step, and keeps its direction');
    var svg = svgRoot(root, W, H, 'Gradient descent on a loss with a steep wall, with and without clipping');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Left: one parameter, a made-up loss with a steep wall, learning rate ' + ETA + '. With many parameters the clip ' +
      'rescales the whole gradient vector to the threshold length, so its direction is unchanged. ' +
      (real ? 'Right: the lecture’s GRU on FD001, gradient norm per batch before clipping, summarized per epoch.' : ''));
    var lab = html('label', {}, controls, 'clip threshold ');
    var cr = html('input', { type: 'range', min: 0.25, max: 4, step: 0.25, value: c }, lab);
    var cv = html('span', {}, lab, c.toFixed(2));
    cr.oninput = function () { c = +cr.value; cv.textContent = c.toFixed(2); runs = [run(false), run(true)]; draw(p.get()); };

    function L(w) { return 0.25 * (w - 4) * (w - 4) + 5 / (1 + Math.exp(S * (w - 1.5))); }
    function dL(w) {
      var z = S * (w - 1.5);
      var s = z > 30 ? 0 : z < -30 ? 0 : Math.exp(z) / ((1 + Math.exp(z)) * (1 + Math.exp(z)));
      return 0.5 * (w - 4) - 5 * S * s;
    }
    function run(clip) {
      var w = -0.5, ws = [w], gs = [], steps = [];
      for (var t = 0; t < T; t++) {
        var g = dL(w), gc = clip && Math.abs(g) > c ? c * Math.sign(g) : g;
        gs.push(g); steps.push(-ETA * gc);
        w = w - ETA * gc;
        ws.push(w);
      }
      return { w: ws, g: gs, step: steps };
    }
    var runs = [run(false), run(true)];
    var p = player(controls, T + 1, function (i) { draw(i); }, 500);

    function draw(pos) {
      clear(svg);
      var px = 40, py = 18, pw = real ? 400 : W - 60, ph = 222, W0 = -1, W1 = 13;
      var sx = scale(W0, W1, px, px + pw), sy = scale(0, YM, py + ph, py);
      text(svg, px, 12, 'loss', { 'font-size': 11 });
      frame(svg, px, py, pw, ph);
      var xs = [], ys = [];
      for (var w = W0; w <= W1; w += 0.02) { xs.push(sx(w)); ys.push(sy(Math.min(YM, L(w)))); }
      polyline(svg, xs, ys, { stroke: 'currentColor', 'stroke-opacity': 0.6, 'stroke-width': 1.5 });
      text(svg, px + pw, py + ph + 14, 'parameter w', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
      text(svg, sx(1.5) - 6, sy(8), 'wall', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
      var g = clipRect(svg, px, py - 4, pw, ph + 8);
      runs.forEach(function (rn, i) {
        var col = i ? 'var(--cw-accent2)' : MUTED, dy = i ? 0 : 0;
        for (var t = 0; t < pos; t++) {
          var a = rn.w[t], b = rn.w[t + 1];
          var ya = sy(Math.min(YM, L(a))) + dy, yb = sy(Math.min(YM, L(b))) + dy;
          el('path', { d: 'M' + sx(a) + ',' + ya + ' Q' + (sx(a) + sx(b)) / 2 + ',' + (Math.min(ya, yb) - 18 - 10 * i) +
            ' ' + sx(b) + ',' + yb, fill: 'none', stroke: col, 'stroke-width': i ? 1.8 : 1.3, 'stroke-opacity': 0.85 }, g);
        }
        var wn = rn.w[pos];
        if (wn > W1) {
          text(svg, px + pw - 4, py + 14 + 14 * i, '→ off the plot, w = ' + wn.toFixed(1), { 'text-anchor': 'end', 'font-size': 11, fill: col });
        } else {
          el('circle', { cx: sx(wn), cy: sy(Math.min(YM, L(wn))), r: 4.5, fill: col }, g);
        }
      });
      legend(svg, px + pw - 110, py + 16, [['clipped at ' + c.toFixed(2), 'var(--cw-accent2)'], ['unclipped', MUTED]]);

      if (real) {
        var rx = 500, rw = W - rx - 10, ep = real.grad, E = ep.max.length;
        var gx = scale(1, E, rx, rx + rw), LO = -1.5, HI = 1.5, gy = scale(LO, HI, py + ph, py);
        text(svg, rx, 12, 'GRU gradient norm per batch (log)', { 'font-size': 11 });
        frame(svg, rx, py, rw, ph);
        [-1, 0, 1].forEach(function (e) {
          text(svg, rx - 4, gy(e) + 3, e === 0 ? '1' : '10^' + e, { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
        });
        var cg = clipRect(svg, rx, py, rw, ph);
        ['max', 'p50'].forEach(function (k, i) {
          polyline(cg, ep[k].map(function (_, j) { return gx(j + 1); }), ep[k].map(function (v) { return gy(Math.log10(v)); }),
            { stroke: i ? 'var(--cw-accent)' : 'var(--cw-accent2)', 'stroke-width': 1.6 });
        });
        el('line', { x1: rx, x2: rx + rw, y1: gy(Math.log10(real.clip)), y2: gy(Math.log10(real.clip)), stroke: 'currentColor',
          'stroke-dasharray': '4 3', 'stroke-opacity': 0.7 }, svg);
        text(svg, rx + rw - 4, gy(Math.log10(real.clip)) - 4, 'clip at ' + real.clip, { 'text-anchor': 'end', 'font-size': 10 });
        text(svg, rx + rw, py + ph + 14, 'epoch', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
        legend(svg, rx + 8, py + 14, [['largest batch', 'var(--cw-accent2)'], ['median batch', 'var(--cw-accent)']]);
      }

      var t = Math.max(0, pos - 1), u = runs[0], k = runs[1];
      var s = pos === 0 ? 'Press Play: both runs start at w = −0.5 on the plateau, loss ' + L(-0.5).toFixed(1) + '. ' :
        'Step ' + pos + ': gradient ' + u.g[t].toFixed(2) + ' unclipped (step ' + u.step[t].toFixed(2) + '), ' +
        k.g[t].toFixed(2) + ' on the clipped run (step ' + k.step[t].toFixed(2) + '). ';
      var far = Math.max.apply(null, u.w);
      s += 'Unclipped, one step on the wall throws w to ' + far.toFixed(1) + ', where the loss is ' + L(far).toFixed(1) +
        ', higher than where it started; clipped, no step is longer than ' + (ETA * c).toFixed(2) + '.';
      if (real) {
        var fr = real.grad.clipped, hit = [];
        fr.forEach(function (v, i) { if (v > 0) hit.push('epoch ' + (i + 1) + ' (' + Math.round(100 * v) + '% of batches)'); });
        s += ' In the GRU, clipping at ' + real.clip + ' acted only in ' + (hit.join(', ') || 'no epoch') + '.';
      }
      readout.textContent = s;
    }
    p.set(T);
  };

  /* Weight decay on a two-parameter quadratic: one direction the data pins
   * down firmly, one it barely constrains. The penalty pulls the optimum toward
   * zero, much further along the weak direction than the strong one. */
  WIDGETS['weight-decay'] = function (root) {
    var W0 = [2.4, 1.6], Hs = [3, 0.25], ETA = 0.3, T = 120, START = [-1.8, -1.4];
    var lam = 0.5, W = 720, H = 280;
    html('div', { class: 'cw-title' }, root, 'Weight decay pulls the weights toward zero, hardest where the data is weakest');
    var svg = svgRoot(root, W, H, 'Gradient descent with and without weight decay on two weights');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Loss = ½(3(w₁ − 2.4)² + 0.25(w₂ − 1.6)²) + ½λ‖w‖². The data fixes w₁ firmly (high curvature) and w₂ loosely. ' +
      'The dashed curve is where the optimum sits for every λ from 0 to ∞.');
    var lab = html('label', {}, controls, 'λ ');
    var lr = html('input', { type: 'range', min: 0, max: 2, step: 0.05, value: lam }, lab);
    var lv = html('span', {}, lab, lam.toFixed(2));
    lr.oninput = function () { lam = +lr.value; lv.textContent = lam.toFixed(2); runs = [run(0), run(lam)]; draw(p.get()); };

    function opt(l) { return [Hs[0] * W0[0] / (Hs[0] + l), Hs[1] * W0[1] / (Hs[1] + l)]; }
    function data(w) { return 0.5 * (Hs[0] * Math.pow(w[0] - W0[0], 2) + Hs[1] * Math.pow(w[1] - W0[1], 2)); }
    function run(l) {
      var w = START.slice(), path = [w];
      for (var t = 0; t < T; t++) {
        w = [w[0] * (1 - ETA * l) - ETA * Hs[0] * (w[0] - W0[0]), w[1] * (1 - ETA * l) - ETA * Hs[1] * (w[1] - W0[1])];
        path.push(w);
      }
      return path;
    }
    var runs = [run(0), run(lam)];
    var p = player(controls, T + 1, function (i) { draw(i); }, 40);

    function draw(pos) {
      clear(svg);
      var px = 30, py = 14, pw = 400, ph = 250, u = 60;
      var ox = px + 2.6 * u, oy = py + ph - 2.0 * u;
      var mx = function (x) { return ox + x * u; }, my = function (y) { return oy - y * u; };
      frame(svg, px, py, pw, ph);
      var g = clipRect(svg, px, py, pw, ph);
      el('line', { x1: px, x2: px + pw, y1: my(0), y2: my(0), stroke: 'currentColor', 'stroke-opacity': 0.3 }, g);
      el('line', { x1: mx(0), x2: mx(0), y1: py, y2: py + ph, stroke: 'currentColor', 'stroke-opacity': 0.3 }, g);
      [0.05, 0.2, 0.5, 1, 2, 3.5].forEach(function (c) {
        el('ellipse', { cx: mx(W0[0]), cy: my(W0[1]), rx: Math.sqrt(2 * c / Hs[0]) * u, ry: Math.sqrt(2 * c / Hs[1]) * u,
          fill: 'none', stroke: 'currentColor', 'stroke-opacity': 0.18 }, g);
      });
      var o = opt(lam), rad = Math.sqrt(o[0] * o[0] + o[1] * o[1]);
      el('circle', { cx: mx(0), cy: my(0), r: rad * u, fill: 'none', stroke: 'var(--cw-green)', 'stroke-dasharray': '3 3', 'stroke-opacity': 0.8 }, g);
      var cx = [], cy = [];
      for (var l = 0; l <= 60; l = l < 1 ? l + 0.02 : l * 1.1) { var q = opt(l); cx.push(mx(q[0])); cy.push(my(q[1])); }
      polyline(g, cx, cy, { stroke: 'var(--cw-green)', 'stroke-dasharray': '5 3', 'stroke-width': 1.3 });
      runs.forEach(function (rn, i) {
        var pts = rn.slice(0, pos + 1), col = i ? 'var(--cw-accent2)' : MUTED;
        polyline(g, pts.map(function (q) { return mx(q[0]); }), pts.map(function (q) { return my(q[1]); }), { stroke: col, 'stroke-width': i ? 1.8 : 1.3 });
        var e = pts[pts.length - 1];
        el('circle', { cx: mx(e[0]), cy: my(e[1]), r: 4, fill: col }, g);
      });
      el('path', { d: 'M' + (mx(W0[0]) - 5) + ',' + my(W0[1]) + 'h10M' + mx(W0[0]) + ',' + (my(W0[1]) - 5) + 'v10',
        stroke: 'currentColor', 'stroke-width': 1.5 }, g);
      text(svg, mx(W0[0]) + 6, my(W0[1]) - 6, 'data optimum', { 'font-size': 10 });
      text(svg, px + pw - 4, my(0) - 4, 'w₁', { 'text-anchor': 'end', 'font-size': 11 });
      text(svg, mx(0) + 5, py + 12, 'w₂', { 'font-size': 11 });
      legend(svg, px + 8, py + ph - 22, [['λ = ' + lam.toFixed(2), 'var(--cw-accent2)'], ['λ = 0', MUTED]]);

      // Right: how much of each weight survives, as bars.
      var bx = 480, bw = W - bx - 16, by = 40, bh = 170, top = 3;
      var sy = scale(0, top, by + bh, by);
      text(svg, bx, 24, 'final weights', { 'font-size': 11 });
      el('line', { x1: bx, x2: bx + bw, y1: sy(0), y2: sy(0), stroke: 'currentColor', 'stroke-opacity': 0.5 }, svg);
      var end0 = runs[0][pos], end1 = runs[1][pos];
      [['w₁ (firm)', 0], ['w₂ (loose)', 1]].forEach(function (it, j) {
        var x = bx + 20 + j * (bw / 2);
        [[end0[j], MUTED], [end1[j], 'var(--cw-accent2)']].forEach(function (b, k) {
          var v = Math.max(-top, Math.min(top, b[0]));
          el('rect', { x: x + k * 36, y: Math.min(sy(v), sy(0)), width: 30, height: Math.abs(sy(v) - sy(0)) || 1, fill: b[1] }, svg);
          text(svg, x + k * 36 + 15, Math.min(sy(v), sy(0)) - 4, b[0].toFixed(2), { 'text-anchor': 'middle', 'font-size': 10 });
        });
        text(svg, x + 33, by + bh + 16, it[0], { 'text-anchor': 'middle', 'font-size': 11 });
      });

      var k1 = Hs[0] / (Hs[0] + lam), k2 = Hs[1] / (Hs[1] + lam);
      readout.textContent = 'Each step: w ← (1 − ηλ)·w − η∇loss, so every weight shrinks by ' + (100 * ETA * lam).toFixed(0) +
        '% before the gradient step. At λ = ' + lam.toFixed(2) + ' the optimum moves from (2.40, 1.60) to (' + o[0].toFixed(2) +
        ', ' + o[1].toFixed(2) + '): w₁ keeps ' + (100 * k1).toFixed(0) + '%, w₂ keeps ' + (100 * k2).toFixed(0) +
        '%. The data loss there is ' + data(o).toFixed(2) + ' instead of 0.';
    }
    p.set(T);
  };

  /* One self-attention step, small enough to do by hand. Each cycle is a token
   * e = [x, p]: its sensor value and, when positional encoding is on, its slot
   * in the window scaled to [0, 1]. The query and key matrices are fixed so the
   * two sliders mean something: q = [a·x, b] and k = [x, p], so the score
   * q·k/√2 = (a·xᵢ·xⱼ + b·pⱼ)/√2 rewards similar values (a) and late slots (b).
   * The value is the sensor reading itself, so the output is a weighted average
   * of the window. Shuffling the cycles shows what the position term is for. */
  WIDGETS['self-attention'] = function (root, data) {
    var all = data.series.values, T = 10;
    var base = all.slice(all.length - 40, all.length - 40 + T);
    var perm = [6, 2, 9, 0, 4, 7, 1, 8, 5, 3];
    var usePos = false, shuffled = false, a = 2.0, b = 3.0, q = T - 1;
    var W = 720, H = 318, L = 70, R = 14;
    html('div', { class: 'cw-title' }, root, 'Self-attention step by step: score, softmax, weighted sum');
    var svg = svgRoot(root, W, H, 'One self-attention step over a ten-cycle window');
    var controls = html('div', { class: 'cw-controls' }, root);
    var controls2 = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Ten cycles of sensor 11 from FD001 engine 1, standardized. Token = [value, position]; query = [a·value, b]; ' +
      'key = [value, position]; value = the sensor reading. The lecture transformer does the same arithmetic with ' +
      '32-dimensional tokens built from all 14 sensors, learned matrices, and 4 heads in parallel.');
    var p = player(controls, T, function (i) { q = i; draw(); }, 500);
    toggleGroup(controls, ['no positional encoding', 'positional encoding'], 0, function (i) { usePos = i === 1; draw(); });
    toggleGroup(controls, ['recorded order', 'shuffled'], 0, function (i) { shuffled = i === 1; draw(); });
    function slider(label, lo, hi, v, set) {
      var lab = html('label', {}, controls2, label + ' ');
      var r = html('input', { type: 'range', min: lo, max: hi, step: 0.1, value: v }, lab);
      var s = html('span', {}, lab, v.toFixed(1));
      r.oninput = function () { set(+r.value); s.textContent = (+r.value).toFixed(1); draw(); };
    }
    slider('content weight a', 0, 3, a, function (v) { a = v; });
    slider('recency weight b', 0, 6, b, function (v) { b = v; });

    function attend(xs) {
      var pos = xs.map(function (_, j) { return usePos ? j / (T - 1) : 0; });
      var out = [], rows = [];
      for (var i = 0; i < T; i++) {
        var s = xs.map(function (xj, j) { return (a * xs[i] * xj + b * (usePos ? 1 : 0) * pos[j]) / Math.SQRT2; });
        var m = Math.max.apply(null, s), ex = s.map(function (v) { return Math.exp(v - m); });
        var z = ex.reduce(function (u, v) { return u + v; }, 0), w = ex.map(function (v) { return v / z; });
        rows.push({ s: s, w: w });
        out.push(w.reduce(function (u, wj, j) { return u + wj * xs[j]; }, 0));
      }
      return { rows: rows, out: out, pooled: out.reduce(function (u, v) { return u + v; }, 0) / T };
    }

    function draw() {
      clear(svg);
      var order = shuffled ? perm : perm.map(function (_, j) { return j; });
      var xs = order.map(function (j) { return base[j]; });
      var res = attend(xs), ref = attend(base), row = res.rows[q];
      var sx = scale(0, T - 1, L + 20, W - R - 20), bw = (W - L - R) / T * 0.55;
      var e = extent(base), sy = scale(e[0], e[1], 86, 26);
      function label(y, s1, s2) {
        text(svg, 4, y, s1, { 'font-size': 11 });
        if (s2) text(svg, 4, y + 13, s2, { 'font-size': 10, opacity: 0.7 });
      }
      // Panel 1: the tokens.
      label(40, 'tokens', 'value xⱼ');
      xs.forEach(function (x, j) {
        var dot = el('circle', { cx: sx(j), cy: sy(x), r: j === q ? 7 : 5, class: 'hot',
          fill: j === q ? 'var(--cw-accent2)' : 'var(--cw-accent)', 'fill-opacity': 0.25 + 0.75 * row.w[j] / Math.max.apply(null, row.w) }, svg);
        (function (k) { dot.onclick = function () { p.set(k); }; })(j);
        text(svg, sx(j), 104, 'cycle ' + (order[j] + 1), { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.8 });
      });
      text(svg, L + 20, 14, 'query = slot ' + (q + 1) + ' (orange); dot shade = how much it is read', { 'font-size': 11 });
      // Panel 2: scores.
      var smax = Math.max(1, Math.max.apply(null, row.s.map(Math.abs)));
      var y0 = 170, ss = scale(0, smax, 0, 42);
      label(142, 'score', 'qᵢ·kⱼ / √2');
      el('line', { x1: L, x2: W - R, y1: y0, y2: y0, stroke: 'currentColor', 'stroke-opacity': 0.3 }, svg);
      row.s.forEach(function (v, j) {
        var h = ss(Math.abs(v));
        el('rect', { x: sx(j) - bw / 2, y: v >= 0 ? y0 - h : y0, width: bw, height: Math.max(h, 1), fill: 'var(--cw-muted)', stroke: 'currentColor', 'stroke-opacity': 0.4 }, svg);
        text(svg, sx(j), v >= 0 ? y0 - h - 3 : y0 + h + 11, v.toFixed(2), { 'text-anchor': 'middle', 'font-size': 9, opacity: 0.8 });
      });
      // Panel 3: softmax weights.
      var wmax = Math.max(0.3, Math.max.apply(null, row.w)), wy0 = 296, ws = scale(0, wmax, 0, 72);
      label(236, 'weight', 'softmax, sums to 1');
      el('line', { x1: L, x2: W - R, y1: wy0, y2: wy0, stroke: 'currentColor', 'stroke-opacity': 0.3 }, svg);
      el('line', { x1: L, x2: W - R, y1: wy0 - ws(1 / T), y2: wy0 - ws(1 / T), stroke: 'var(--cw-accent2)', 'stroke-dasharray': '4 3' }, svg);
      text(svg, 4, wy0 - ws(1 / T) + 3, '- - uniform 0.10', { 'font-size': 9, fill: 'var(--cw-accent2)' });
      row.w.forEach(function (v, j) {
        el('rect', { x: sx(j) - bw / 2, y: wy0 - ws(v), width: bw, height: ws(v), fill: 'var(--cw-accent)' }, svg);
        text(svg, sx(j), wy0 - ws(v) - 3, v.toFixed(2), { 'text-anchor': 'middle', 'font-size': 9, opacity: 0.8 });
      });
      text(svg, W - R, 312, 'slot in the window', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });

      var terms = row.w.map(function (w, j) { return { w: w, x: xs[j] }; })
        .sort(function (u, v) { return v.w - u.w; }).slice(0, 3)
        .map(function (t) { return t.w.toFixed(2) + '×' + fmt(t.x).trim(); }).join(' + ');
      var same = Math.abs(res.pooled - ref.pooled) < 5e-4;
      readout.textContent = 'Slot ' + (q + 1) + ' (cycle ' + (order[q] + 1) + ', x = ' + fmt(xs[q]).trim() + ') outputs Σ wⱼxⱼ = ' +
        terms + ' + … = ' + fmt(res.out[q]).trim() + '. Mean-pooled window summary: ' + fmt(res.pooled, 3).trim() +
        (shuffled ? (same ? ', identical to the recorded order: without positions the cycles are a set.' :
          ' against ' + fmt(ref.pooled, 3).trim() + ' in recorded order: the positions make order count.') :
          (usePos ? '.' : '. With no positional encoding, b has nothing to act on.'));
    }
    p.set(T - 1);
  };

  /* Self-attention weights of the trained lecture transformer, read out of the
   * model by make_widget_data.py, for one engine near failure and one far. */
  WIDGETS.attention = function (root, data) {
    var att = data.attention, keys = Object.keys(att);
    var which = keys.indexOf('near') >= 0 ? keys.indexOf('near') : 0, layer = 0;
    var T = att[keys[0]].layers[0].length, q = T - 1;
    var W = 720, H = 300, CELL = 8, HX = 30, HY = 20, PX = 330;
    html('div', { class: 'cw-title' }, root, 'Where the trained transformer actually attends');
    var svg = svgRoot(root, W, H, 'Attention weights of the trained transformer');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Weights from the lecture transformer (seed 0, trained on all 100 engines), averaged over its 4 heads. ' +
      'Row = the cycle doing the reading, column = the cycle being read. Click a row or a point to pick the reading cycle. ' +
      'The dashed line is uniform attention, 1/' + T + ' of the weight on every cycle.');
    select(controls, 'test engine', keys.map(function (k) {
      var a = att[k]; return 'engine ' + a.engine + ': true RUL ' + a.true_rul + ', predicted ' + a.predicted_rul;
    }), which, function (v) { which = v; draw(); });
    toggleGroup(controls, ['layer 1', 'layer 2'], 0, function (i) { layer = i; draw(); });

    function draw() {
      clear(svg);
      var a = att[keys[which]], M = a.layers[layer].map(function (r) { return r.map(function (v) { return v / 1000; }); });
      var uni = 1 / T, top = 3 * uni;
      text(svg, HX, 12, 'attention matrix (query ↓, key →)', { 'font-size': 11 });
      for (var r = 0; r < T; r++) for (var c = 0; c < T; c++) {
        var cell = el('rect', { x: HX + c * CELL, y: HY + r * CELL, width: CELL, height: CELL, class: 'hot',
          fill: 'var(--cw-accent)', 'fill-opacity': Math.min(1, M[r][c] / top).toFixed(3) }, svg);
        (function (row) { cell.onclick = function () { q = row; draw(); }; })(r);
      }
      el('rect', { x: HX - 1, y: HY + q * CELL, width: T * CELL + 2, height: CELL, fill: 'none',
        stroke: 'var(--cw-accent2)', 'stroke-width': 1.5 }, svg);
      text(svg, HX, HY + T * CELL + 14, 'colour saturates at 3× uniform', { 'font-size': 10, opacity: 0.7 });

      // Right: the sensor over the window, and the chosen row as bars.
      var sx = scale(0, T - 1, PX + 20, W - 12);
      var e = extent(a.sensor), sy = scale(e[0], e[1], 110, 22);
      text(svg, PX + 20, 12, 'sensor 11 over the window', { 'font-size': 11 });
      polyline(svg, a.sensor.map(function (_, i) { return sx(i); }), a.sensor.map(sy),
        { stroke: 'currentColor', 'stroke-opacity': 0.6, 'stroke-width': 1.2 });
      a.sensor.forEach(function (v, i) {
        var dot = el('circle', { cx: sx(i), cy: sy(v), r: i === q ? 4.5 : 2.4, class: 'hot',
          fill: i === q ? 'var(--cw-accent2)' : 'currentColor', 'fill-opacity': i === q ? 1 : 0.55 }, svg);
        (function (row) { dot.onclick = function () { q = row; draw(); }; })(i);
      });
      var row = M[q], bmax = Math.max(top, Math.max.apply(null, row));
      var by = scale(0, bmax, 270, 140), bw = (W - 12 - PX - 20) / T * 0.75;
      text(svg, PX + 20, 134, 'weights read by cycle ' + (q + 1), { 'font-size': 11 });
      row.forEach(function (v, i) {
        el('rect', { x: sx(i) - bw / 2, y: by(v), width: bw, height: by(0) - by(v), fill: 'var(--cw-accent)' }, svg);
      });
      el('line', { x1: PX + 14, x2: W - 8, y1: by(uni), y2: by(uni), stroke: 'var(--cw-accent2)', 'stroke-dasharray': '4 3' }, svg);
      for (var i = 0; i < T; i += 5) text(svg, sx(i), 286, String(i + 1), { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 });
      text(svg, W - 12, 298, 'cycle in window', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });

      var arg = row.indexOf(Math.max.apply(null, row));
      var H0 = 0;
      row.forEach(function (v) { if (v > 0) H0 -= v * Math.log(v); });
      var last5 = row.slice(T - 5).reduce(function (s, v) { return s + v; }, 0);
      readout.textContent = 'Layer ' + (layer + 1) + ', cycle ' + (q + 1) + ' reads cycle ' + (arg + 1) + ' most (' +
        (1000 * row[arg]).toFixed(0) + '‰; uniform is ' + (1000 * uni).toFixed(0) + '‰). The last 5 cycles get ' +
        (100 * last5).toFixed(0) + '% of its attention (uniform: ' + (500 / T).toFixed(0) + '%). Entropy is ' +
        (100 * H0 / Math.log(T)).toFixed(0) + '% of the uniform maximum.';
    }
    draw();
  };

  // ------------------------------------------------------------------ L13

  var RED = '#c41230';

  // A clip region for one plot, so a curve that leaves its axes is cut at the
  // frame instead of running over the rest of the figure. draw() clears the
  // SVG each time, so each call makes a fresh, uniquely named clipPath.
  var CLIPN = 0;
  function clipTo(svg, x, y, w, h) {
    var id = 'cwclip' + (++CLIPN);
    var cp = el('clipPath', { id: id }, el('defs', {}, svg));
    el('rect', { x: x, y: y, width: w, height: h }, cp);
    return 'url(#' + id + ')';
  }

  function spring(parent, x, y0, y1, color) {
    var n = 10, pts = [[x, y0]], seg = (y1 - y0 - 8) / n;
    for (var i = 0; i < n; i++) pts.push([x + (i % 2 ? -7 : 7), y0 + 4 + seg * (i + 0.5)]);
    pts.push([x, y1]);
    polyline(parent, pts.map(function (p) { return p[0]; }), pts.map(function (p) { return p[1]; }),
      { stroke: color, 'stroke-width': 1.6 });
  }

  /* Estimating the damping and stiffness of a spring-mass from noisy data, from
   * one poor starting guess, two ways. Every iterate of each solver was recorded
   * by lectures/l13/figures/make_figures.py. Single shooting simulates at every
   * iterate; collocation starts on the data with the ODE broken and repairs it. */
  WIDGETS['seq-sim'] = function (root, data) {
    var d = data.seqsim, S = d.seq, M = d.sim, n = Math.max(S.length, M.length);
    var W = 720, H = 330, T0 = 30, B = 220;
    html('div', { class: 'cw-title' }, root, 'Sequential and simultaneous, iteration by iteration');
    var svg = svgRoot(root, W, H, 'Iterates of single shooting and of the simultaneous approach on the same estimation problem');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Lightly damped spring-mass (true μ = 1 N·s/m, k = 400 N/m), 51 measurements over 2 s with noise SD 0.03 m, both ' +
      'started from μ = 2, k = 150. Sequential: Runge-Kutta simulation inside BFGS. Simultaneous: trapezoidal collocation ' +
      'on 200 steps, solved by the POUNCE interior-point solver. Data error: sum of squared errors (SSE) against the ' +
      'measurements. Equation error: how far the model equations are from holding, the largest violation.');
    var panels = [
      { x0: 44, x1: 352, name: 'Sequential (single shooting)', color: 'var(--cw-accent2)', frames: S, dots: false },
      { x0: 404, x1: 712, name: 'Simultaneous (collocation)', color: 'var(--cw-accent)', frames: M, dots: true }
    ];
    var sy = scale(-1.15, 1.15, B, T0);
    function bar(x0, y, w, frac, color, label, value) {
      text(svg, x0, y - 3, label, { 'font-size': 11, opacity: 0.8 });
      el('rect', { x: x0 + 92, y: y - 12, width: w, height: 11, fill: 'currentColor', 'fill-opacity': 0.08 }, svg);
      el('rect', { x: x0 + 92, y: y - 12, width: Math.max(1, w * Math.min(1, Math.max(0, frac))), height: 11, fill: color }, svg);
      text(svg, x0 + 98 + w, y - 3, value, { 'font-size': 11 });
    }
    var p = player(controls, n, draw, 260);

    function draw(i) {
      clear(svg);
      var line = [];
      panels.forEach(function (pn) {
        var k = Math.min(i, pn.frames.length - 1), fr = pn.frames[k], done = k === pn.frames.length - 1;
        var sx = scale(0, d.T, pn.x0, pn.x1);
        var clip = clipTo(svg, pn.x0 - 4, T0, pn.x1 - pn.x0 + 8, B - T0);
        text(svg, (pn.x0 + pn.x1) / 2, 14, pn.name, { 'text-anchor': 'middle', 'font-size': 13, 'font-weight': 600, style: 'fill:' + pn.color });
        text(svg, (pn.x0 + pn.x1) / 2, 28, 'iteration ' + k + (done ? ' (final)' : ''), { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.75 });
        el('line', { x1: pn.x0, x2: pn.x1, y1: sy(0), y2: sy(0), stroke: 'currentColor', 'stroke-opacity': 0.15 }, svg);
        d.t_obs.forEach(function (v, j) { el('circle', { cx: sx(v), cy: sy(d.x_obs[j]), r: 2.4, fill: 'currentColor', 'fill-opacity': 0.75 }, svg); });
        polyline(svg, d.t.map(sx), fr.x.map(sy), { stroke: pn.color, 'stroke-width': 2, 'clip-path': clip });
        if (pn.dots) fr.x.forEach(function (v, j) { el('circle', { cx: sx(d.t[j]), cy: sy(v), r: 1.6, fill: pn.color, 'clip-path': clip }, svg); });
        [0, 1, 2].forEach(function (v) { text(svg, sx(v), B + 14, String(v), { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 }); });
        text(svg, (pn.x0 + pn.x1) / 2, B + 27, 'time (s)', { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 });
        // Fit to the data, on a log scale from 0.01 to 20.
        var fitFrac = (Math.log10(Math.max(fr.sse, 0.01)) + 2) / (Math.log10(20) + 2);
        bar(pn.x0, B + 52, 150, fitFrac, pn.color, 'data error', fr.sse.toFixed(2));
        if (pn.dots) {
          var defFrac = (Math.log10(Math.max(fr.defect, 1e-16)) + 16) / 17;
          bar(pn.x0, B + 74, 150, defFrac, RED, 'equation error', sci(fr.defect));
        } else {
          text(svg, pn.x0, B + 71, 'equation error  0 at every iterate: each one is a full simulation', { 'font-size': 11, opacity: 0.8 });
        }
        text(svg, pn.x0, B + 96, 'μ = ' + fr.mu.toFixed(2) + ' N·s/m,  k = ' + fr.k.toFixed(0) + ' N/m', { 'font-size': 11 });
        line.push(pn.name.split(' (')[0] + ' iteration ' + k + ': μ = ' + fr.mu.toFixed(2) + ', k = ' + fr.k.toFixed(0) +
          ', data error (SSE) = ' + fr.sse.toFixed(2) + (pn.dots ? ', equation error = ' + sci(fr.defect) : '') + (done ? ' (final)' : ''));
      });
      readout.textContent = line.join('.  ') + '.  True values: μ = 1, k = 400.';
    }
    p.set(0);
  };

  /* A projection layer on a heat exchanger's energy balance: the heat the hot water gives
   * up must equal the heat the cold water takes. Drag the raw network output; the layer
   * returns the closest point on the balance line. The hot-water flow sets the line. */
  WIDGETS.projection = function (root) {
    var TH = 90, TC = 20, MC = 1.0, CP = 4.18, mh = 1.0, raw = [62, 58];
    var PRESETS = [[62, 58], [45, 40], [80, 50], [35, 75], [55, 55]], pi = 0;
    var W = 720, H = 330, L = 46, S0 = 300;
    html('div', { class: 'cw-title' }, root, 'A projection layer moves the raw output to the nearest point that obeys the energy balance');
    var svg = svgRoot(root, W, H, 'Orthogonal projection of raw outlet temperatures onto the energy-balance line of a heat exchanger');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Counterflow heat exchanger: hot water in at 90 °C, cold water in at 20 °C and 1 kg/s. The outlet temperatures must satisfy ' +
      'ṁh (90 − Th,out) = ṁc (Tc,out − 20), a line a·y = b with a = (ṁh, ṁc). Drag the orange point, press Step, or change the ' +
      'hot-water flow: a and b change, the layer stays linear.');
    var step = html('button', { type: 'button' }, controls, 'Step');
    step.onclick = function () { pi = (pi + 1) % PRESETS.length; raw = PRESETS[pi].slice(); draw(); };
    var lab = html('label', {}, controls, 'hot-water flow ');
    var flow = html('input', { type: 'range', min: 0.3, max: 2.0, step: 0.05, value: mh, 'aria-label': 'hot-water flow' }, lab);
    var flowOut = html('span', {}, lab, ' ' + mh.toFixed(2) + ' kg/s');
    flow.oninput = function () { mh = parseFloat(flow.value); flowOut.textContent = ' ' + mh.toFixed(2) + ' kg/s'; draw(); };
    var sx = scale(20, 90, L, L + S0 - 20), sy = scale(20, 90, S0, 10);
    var dragging = false;
    function toData(evt) {
      var pt = svg.createSVGPoint();
      pt.x = evt.clientX; pt.y = evt.clientY;
      var q = pt.matrixTransform(svg.getScreenCTM().inverse());
      return [Math.max(20, Math.min(90, 20 + (q.x - L) / (S0 - 20) * 70)), Math.max(20, Math.min(90, 20 + (S0 - q.y) / (S0 - 10) * 70))];
    }
    svg.addEventListener('pointerdown', function (e) { dragging = true; raw = toData(e); draw(); });
    svg.addEventListener('pointermove', function (e) { if (dragging) { raw = toData(e); draw(); } });
    window.addEventListener('pointerup', function () { dragging = false; });

    function duties(y) { return [mh * CP * (TH - y[0]), MC * CP * (y[1] - TC)]; }
    function draw() {
      clear(svg);
      [20, 30, 40, 50, 60, 70, 80, 90].forEach(function (v) {
        el('line', { x1: sx(v), x2: sx(v), y1: sy(20), y2: sy(90), stroke: 'currentColor', 'stroke-opacity': 0.06 }, svg);
        el('line', { x1: sx(20), x2: sx(90), y1: sy(v), y2: sy(v), stroke: 'currentColor', 'stroke-opacity': 0.06 }, svg);
        text(svg, sx(v), sy(20) + 14, String(v), { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 });
        text(svg, sx(20) - 6, sy(v) + 4, String(v), { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
      });
      text(svg, sx(55), sy(20) + 28, 'hot-water outlet Th,out (°C)', { 'text-anchor': 'middle', 'font-size': 11 });
      text(svg, 4, sy(92) + 4, 'Tc,out (°C)', { 'font-size': 11 });
      var b = mh * TH + MC * TC, aa = mh * mh + MC * MC;
      var cpl = clipTo(svg, sx(20), sy(90), sx(90) - sx(20), sy(20) - sy(90));
      el('line', { x1: sx(20), y1: sy((b - mh * 20) / MC), x2: sx(90), y2: sy((b - mh * 90) / MC), stroke: 'var(--cw-green)', 'stroke-width': 3, 'clip-path': cpl }, svg);
      text(svg, sx(22), sy(23), 'energy balance: heat given up = heat taken', { 'font-size': 11.5, style: 'fill:var(--cw-green)' });
      var v = mh * raw[0] + MC * raw[1] - b, proj = [raw[0] - mh * v / aa, raw[1] - MC * v / aa];
      el('line', { x1: sx(raw[0]), y1: sy(raw[1]), x2: sx(proj[0]), y2: sy(proj[1]), stroke: 'currentColor', 'stroke-width': 1.6, 'stroke-dasharray': '5 3' }, svg);
      el('circle', { cx: sx(proj[0]), cy: sy(proj[1]), r: 8, fill: 'var(--cw-accent)', 'clip-path': cpl }, svg);
      el('circle', { cx: sx(raw[0]), cy: sy(raw[1]), r: 9, fill: 'var(--cw-accent2)', class: 'hot' }, svg);
      var qr = duties(raw), qp = duties(proj), gap = qr[1] - qr[0];
      var x0 = 380, rows = [
        ['raw output ỹ = (Th,out, Tc,out)', '(' + raw[0].toFixed(1) + ', ' + raw[1].toFixed(1) + ') °C', 'var(--cw-accent2)'],
        ['heat given up, heat taken', qr[0].toFixed(1) + ' kW, ' + qr[1].toFixed(1) + ' kW', gap > 0 ? RED : 'currentColor'],
        ['violation v = aᵀỹ − b', v.toFixed(2) + (Math.abs(gap) < 0.05 ? '' : gap > 0 ? '  (energy from nothing)' : '  (energy lost)'), RED],
        ['projected y = ỹ − a v / (aᵀa)', '(' + proj[0].toFixed(1) + ', ' + proj[1].toFixed(1) + ') °C', 'var(--cw-accent)'],
        ['check: heat given up, heat taken', qp[0].toFixed(1) + ' kW, ' + qp[1].toFixed(1) + ' kW', 'var(--cw-green)']
      ];
      text(svg, x0, 36, 'y = ỹ − a (aᵀỹ − b) / (aᵀa)', { 'font-size': 15, 'font-weight': 600 });
      rows.forEach(function (r, j) {
        text(svg, x0, 76 + 46 * j, r[0], { 'font-size': 12, opacity: 0.8 });
        text(svg, x0, 94 + 46 * j, r[1], { 'font-size': 14, style: 'fill:' + r[2], 'font-weight': 600 });
      });
      readout.textContent = 'Raw output: the hot water gives up ' + qr[0].toFixed(1) + ' kW and the cold water takes ' + qr[1].toFixed(1) +
        ' kW, ' + (Math.abs(gap) < 0.05 ? 'which balances.' : (gap > 0 ? Math.abs(gap).toFixed(1) + ' kW of energy from nothing.' : Math.abs(gap).toFixed(1) + ' kW lost to nowhere.')) +
        ' After the layer: (' + proj[0].toFixed(1) + ', ' + proj[1].toFixed(1) + ') °C, ' + qp[0].toFixed(1) + ' kW given up and ' + qp[1].toFixed(1) + ' kW taken.';
    }
    draw();
  };

  // A Play/Pause + Step + scrubber trio like player(), but the position is a
  // real number moved by requestAnimationFrame, so a figure can interpolate
  // between its recorded frames instead of jumping from one to the next.
  function smoothPlayer(controls, n, onChange, secPerStep, onState) {
    var pos = 0, raf = null, target = null, lastT = null;
    var play = html('button', { type: 'button' }, controls, 'Play');
    var step = html('button', { type: 'button' }, controls, 'Step');
    var lab = html('label', {}, controls);
    var range = html('input', { type: 'range', min: 0, max: n - 1, step: 'any', value: 0, 'aria-label': 'position' }, lab);
    function set(p) { pos = Math.max(0, Math.min(n - 1, p)); range.value = pos; onChange(pos); }
    function stop() {
      if (raf) cancelAnimationFrame(raf);
      raf = null; target = null; play.textContent = 'Play';
      if (onState) onState(false);
    }
    function tick(now) {
      if (lastT === null) lastT = now;
      var dp = (now - lastT) / 1000 / secPerStep;
      lastT = now;
      var goal = target === null ? n - 1 : target;
      set(Math.min(goal, pos + dp));
      if (pos >= goal) { stop(); return; }
      raf = requestAnimationFrame(tick);
    }
    function run(goal) { if (raf) cancelAnimationFrame(raf); target = goal; lastT = null; raf = requestAnimationFrame(tick); }
    play.onclick = function () {
      if (raf && target === null) return stop();
      if (pos >= n - 1) set(0);
      play.textContent = 'Pause';
      if (onState) onState(true);
      run(null);
    };
    step.onclick = function () {
      play.textContent = 'Play';
      if (pos >= n - 1 - 1e-9) { stop(); set(0); return; }
      run(Math.floor(pos + 1e-9) + 1);
    };
    range.oninput = function () { stop(); set(+range.value); };
    return { set: set, stop: stop, get: function () { return pos; } };
  }

  function lerp(a, b, w) { return a + w * (b - a); }
  function lerpArr(a, b, w) { return a.map(function (v, i) { return v + w * (b[i] - v); }); }
  function pts(xs, ys) { return xs.map(function (x, i) { return x.toFixed(1) + ',' + ys[i].toFixed(1); }).join(' '); }
  function interp1(xs, ys, x) {
    if (x <= xs[0]) return ys[0];
    for (var i = 1; i < xs.length; i++) if (xs[i] >= x) {
      return ys[i - 1] + (x - xs[i - 1]) / (xs[i] - xs[i - 1]) * (ys[i] - ys[i - 1]);
    }
    return ys[ys.length - 1];
  }
  // The points of a hanging coil spring from (x, y0) down to (x, y1).
  function coilPts(x, y0, y1, half) {
    var n = 12, p = [[x, y0], [x, y0 + 6]], seg = (y1 - y0 - 12) / n;
    for (var i = 0; i < n; i++) p.push([x + (i % 2 ? -half : half), y0 + 6 + seg * (i + 0.5)]);
    p.push([x, y1 - 6], [x, y1]);
    return p.map(function (q) { return q[0].toFixed(1) + ',' + q[1].toFixed(1); }).join(' ');
  }

  /* A hanging spring-mass with a damper. Drag the mass up or down and let go:
   * it moves by m x'' + mu x' + k x = 0, integrated here with RK4 in real or
   * slowed-down time, and its trace is drawn on the right. No data. */
  WIDGETS['spring-drag'] = function (root) {
    var m = 1, mu = 4, k = 400, x = 1, v = 0, t = 0, slow = 4, raf = null, last = null, dragging = false;
    var trace = [];
    var W = 720, H = 330, CX = 130, REST = 190, PPM = 80, PL = 330, PR = 704, PT = 24, PB = 282;
    html('div', { class: 'cw-title' }, root, 'Drag the mass, let go, and watch the equation of motion play out');
    var svg = svgRoot(root, W, H, 'A spring-mass with a damper that can be dragged and released');
    var c1 = html('div', { class: 'cw-controls' }, root);
    var c2 = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'x is the displacement from rest, positive upward. Releasing at rest gives x\'(0) = 0. The trace starts when you let go; ' +
      'slow motion stretches real time so the 3 oscillations per second can be followed.');
    function slider(parent, name, lo, hi, st, val, unit, set) {
      var lab = html('label', {}, parent, name + ' ');
      var s = html('input', { type: 'range', min: lo, max: hi, step: st, value: val, 'aria-label': name }, lab);
      var o = html('span', {}, lab, val + ' ' + unit);
      s.oninput = function () { set(+s.value); o.textContent = s.value + ' ' + unit; release(x); };
    }
    slider(c1, 'mass m', 0.5, 4, 0.5, m, 'kg', function (q) { m = q; });
    slider(c1, 'damping μ', 0, 20, 1, mu, 'N·s/m', function (q) { mu = q; });
    slider(c1, 'stiffness k', 100, 800, 50, k, 'N/m', function (q) { k = q; });
    var again = html('button', { type: 'button' }, c2, 'Release from x = 1 m');
    again.onclick = function () { release(1); };
    toggleGroup(c2, ['Real time', 'Slow ×4', 'Slow ×10'], 1, function (i) { slow = [1, 4, 10][i]; });

    var sy = scale(-1.25, 1.25, PB, PT);
    var g0 = el('g', {}, svg);
    el('rect', { x: CX - 70, y: 6, width: 140, height: 12, fill: 'currentColor', 'fill-opacity': 0.35 }, g0);
    el('line', { x1: CX - 95, x2: CX + 95, y1: REST, y2: REST, stroke: 'currentColor', 'stroke-opacity': 0.25, 'stroke-dasharray': '4 4' }, g0);
    text(g0, CX - 98, REST + 4, 'x = 0', { 'text-anchor': 'end', 'font-size': 11, opacity: 0.7 });
    var spring = el('polyline', { fill: 'none', stroke: 'currentColor', 'stroke-opacity': 0.55, 'stroke-width': 2.4 }, svg);
    var rod = el('line', { x1: CX + 34, x2: CX + 34, y1: 18, stroke: 'currentColor', 'stroke-width': 2.4 }, svg);
    var cyl = el('rect', { x: CX + 24, width: 20, fill: 'none', stroke: 'currentColor', 'stroke-width': 2.2 }, svg);
    var mass = el('rect', { x: CX - 42, width: 84, height: 44, rx: 4, fill: 'var(--cw-green)', class: 'hot', style: 'cursor:grab' }, svg);
    var mlab = text(svg, CX, 0, 'm', { 'text-anchor': 'middle', 'font-size': 18, style: 'fill:#fff;pointer-events:none', 'font-style': 'italic' });
    text(svg, CX - 50, 70, 'k', { 'font-size': 16, 'font-style': 'italic' });
    text(svg, CX + 52, 70, 'μ', { 'font-size': 16, 'font-style': 'italic' });
    var arrow = el('line', { x1: CX - 62, x2: CX - 62, y1: REST, stroke: RED, 'stroke-width': 2.4, style: 'pointer-events:none' }, svg);
    var xl = text(svg, CX - 70, 0, 'x', { 'text-anchor': 'end', 'font-size': 15, 'font-style': 'italic', style: 'fill:' + RED + ';pointer-events:none' });
    // the trace
    el('line', { x1: PL, x2: PR, y1: sy(0), y2: sy(0), stroke: 'currentColor', 'stroke-opacity': 0.2 }, svg);
    [-1, 0, 1].forEach(function (q) { text(svg, PL - 6, sy(q) + 4, String(q), { 'text-anchor': 'end', 'font-size': 11, opacity: 0.7 }); });
    text(svg, PL - 26, PT + 4, 'x (m)', { 'font-size': 11, opacity: 0.8 });
    var tlabs = [0, 1, 2, 3, 4].map(function (q) { return text(svg, 0, PB + 16, '', { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.7 }); });
    text(svg, (PL + PR) / 2, PB + 31, 'time since release (s)', { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.8 });
    var eqn = text(svg, PL, PT - 6, '', { 'font-size': 13, 'font-weight': 600 });
    var line = el('polyline', { fill: 'none', stroke: 'var(--cw-green)', 'stroke-width': 2.2 }, svg);
    var dot = el('circle', { r: 5, fill: 'var(--cw-green)' }, svg);

    function f(s) { return [s[1], -(mu * s[1] + k * s[0]) / m]; }
    function rk4(s, h) {
      var a = f(s), b = f([s[0] + h / 2 * a[0], s[1] + h / 2 * a[1]]);
      var c = f([s[0] + h / 2 * b[0], s[1] + h / 2 * b[1]]), d = f([s[0] + h * c[0], s[1] + h * c[1]]);
      return [s[0] + h / 6 * (a[0] + 2 * b[0] + 2 * c[0] + d[0]), s[1] + h / 6 * (a[1] + 2 * b[1] + 2 * c[1] + d[1])];
    }
    function draw() {
      var y = REST - PPM * x;
      spring.setAttribute('points', coilPts(CX - 18, 18, y - 22, 12));
      rod.setAttribute('y2', Math.min(y - 30, 18 + 60));
      cyl.setAttribute('y', Math.min(y - 30, 18 + 60) - 6);
      cyl.setAttribute('height', Math.max(8, y - 22 - (Math.min(y - 30, 18 + 60) - 6)));
      mass.setAttribute('y', y - 22);
      mlab.setAttribute('y', y + 6);
      arrow.setAttribute('y2', y);
      xl.setAttribute('y', (REST + y) / 2 + 5);
      var t0 = Math.max(0, t - 4), sx = scale(t0, t0 + 4, PL, PR);
      tlabs.forEach(function (lb, i) { var q = Math.ceil(t0) + i; lb.setAttribute('x', sx(q)); lb.textContent = q <= t0 + 4 ? String(q) : ''; });
      var vis = trace.filter(function (p) { return p[0] >= t0; });
      line.setAttribute('points', pts(vis.map(function (p) { return sx(p[0]); }), vis.map(function (p) { return sy(Math.max(-1.25, Math.min(1.25, p[1]))); })));
      dot.setAttribute('cx', sx(Math.max(t0, t)));
      dot.setAttribute('cy', sy(Math.max(-1.25, Math.min(1.25, x))));
      eqn.textContent = m + ' x″ + ' + mu + ' x′ + ' + k + ' x = 0';
      var wn = Math.sqrt(k / m), zeta = mu / (2 * Math.sqrt(k * m));
      readout.textContent = 't = ' + t.toFixed(2) + ' s, x = ' + fmt(x) + ' m.  Natural frequency √(k/m) = ' + wn.toFixed(1) +
        ' rad/s; damping ratio μ/(2√(km)) = ' + zeta.toFixed(2) + (zeta < 1 ? ' (oscillates)' : ' (no oscillation)') + '.';
    }
    function loop(now) {
      if (last === null) last = now;
      var dt = Math.min(0.05, (now - last) / 1000) / slow;
      last = now;
      var s = [x, v], h = 0.0005, nsub = Math.max(1, Math.ceil(dt / h));
      for (var i = 0; i < nsub; i++) s = rk4(s, dt / nsub);
      x = s[0]; v = s[1]; t += dt;
      trace.push([t, x]);
      draw();
      if (t > 30 || (mu > 0 && Math.abs(x) < 1e-3 && Math.abs(v) < 1e-2)) { raf = null; return; }
      raf = requestAnimationFrame(loop);
    }
    function release(x0) {
      if (raf) cancelAnimationFrame(raf);
      x = x0; v = 0; t = 0; trace = [[0, x0]]; last = null;
      raf = requestAnimationFrame(loop);
    }
    function toX(evt) {
      var p = svg.createSVGPoint();
      p.x = evt.clientX; p.y = evt.clientY;
      var q = p.matrixTransform(svg.getScreenCTM().inverse());
      return Math.max(-1.2, Math.min(1.2, (REST - q.y) / PPM));
    }
    mass.addEventListener('pointerdown', function (e) {
      dragging = true;
      if (raf) cancelAnimationFrame(raf);
      raf = null;
      mass.setPointerCapture(e.pointerId);
      mass.style.cursor = 'grabbing';
    });
    mass.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      x = toX(e); v = 0; t = 0; trace = [[0, x]];
      draw();
    });
    mass.addEventListener('pointerup', function () {
      if (!dragging) return;
      dragging = false;
      mass.style.cursor = 'grab';
      release(x);
    });
    draw();
  };

  /* A residual network or an RNN takes fixed steps h_(k+1) = h_k + dt f(h_k);
   * a neural ODE learns f itself, the arrows. On the phase plane of the
   * spring-mass, Euler steps of shrinking size fall onto the exact trajectory.
   * Everything is computed here; the figure takes no data. */
  WIDGETS['phase-plane'] = function (root) {
    var m = 1, mu = 4, k = 400, T = 1, DTS = [0.02, 0.01, 0.005, 0.0025, 0.00125, 0.000625];
    function f(s) { return [s[1], -(mu * s[1] + k * s[0]) / m]; }
    function euler(dt) {
      var s = [1, 0], out = [[0, 1, 0]];
      for (var j = 1; j <= Math.round(T / dt); j++) {
        var d = f(s);
        s = [s[0] + dt * d[0], s[1] + dt * d[1]];
        out.push([j * dt, s[0], s[1]]);
      }
      return out;
    }
    var ex = [], s = [1, 0], h = 0.0001;
    for (var j = 0; j <= T / h; j++) {
      if (j % 20 === 0) ex.push([j * h, s[0], s[1]]);
      var a = f(s), b = f([s[0] + h / 2 * a[0], s[1] + h / 2 * a[1]]), c = f([s[0] + h / 2 * b[0], s[1] + h / 2 * b[1]]),
        d = f([s[0] + h * c[0], s[1] + h * c[1]]);
      s = [s[0] + h / 6 * (a[0] + 2 * b[0] + 2 * c[0] + d[0]), s[1] + h / 6 * (a[1] + 2 * b[1] + 2 * c[1] + d[1])];
    }
    function exactAt(tq) { return interp1(ex.map(function (q) { return q[0]; }), ex.map(function (q) { return q[1]; }), tq); }
    var runs = DTS.map(function (dt) {
      var e = euler(dt), err = 0;
      e.forEach(function (q) { err = Math.max(err, Math.abs(q[1] - exactAt(q[0]))); });
      return { pts: e, err: err };
    });
    var W = 720, H = 330, PX0 = 46, PX1 = 330, PY0 = 18, PY1 = 286, TX0 = 400, TX1 = 704;
    html('div', { class: 'cw-title' }, root, 'Fixed steps against a vector field: shrink the step and the RNN becomes the ODE');
    var svg = svgRoot(root, W, H, 'Euler steps of a spring-mass on its phase plane, converging to the exact trajectory as the step shrinks');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'The spring-mass of the PINN section, m = 1 kg, μ = 4 N·s/m, k = 400 N/m, released from x = 1 m. State h = (x, v). ' +
      'Gray arrows: the right-hand side f(h) = (v, −(μv + kx)/m), drawn at fixed length. Orange: Euler steps ' +
      'h_(k+1) = h_k + Δt f(h_k). Blue: the exact solution.');
    var px = scale(-1.15, 1.15, PX0, PX1), pv = scale(-22, 22, PY1, PY0);
    var tx = scale(0, T, TX0, TX1), ty = scale(-1.15, 1.15, PY1, PY0);
    // static: axes, the field, the exact curves
    el('line', { x1: PX0, x2: PX1, y1: pv(0), y2: pv(0), stroke: 'currentColor', 'stroke-opacity': 0.2 }, svg);
    el('line', { x1: px(0), x2: px(0), y1: PY0, y2: PY1, stroke: 'currentColor', 'stroke-opacity': 0.2 }, svg);
    text(svg, PX1, pv(0) - 6, 'x (m)', { 'text-anchor': 'end', 'font-size': 11, opacity: 0.8 });
    text(svg, px(0) + 6, PY0 + 10, 'v (m/s)', { 'font-size': 11, opacity: 0.8 });
    for (var i = 0; i < 13; i++) for (var jj = 0; jj < 11; jj++) {
      var xq = -1.05 + 2.1 * i / 12, vq = -20 + 40 * jj / 10, dq = f([xq, vq]);
      var ux = dq[0] / 2.3, uy = dq[1] / 44, nn = Math.hypot(ux, uy) || 1, L = 9;
      var x0 = px(xq), y0 = pv(vq), x1 = x0 + L * ux / nn, y1 = y0 - L * uy / nn;
      el('line', { x1: x0 - (x1 - x0) / 2, y1: y0 - (y1 - y0) / 2, x2: x1, y2: y1, stroke: 'currentColor', 'stroke-opacity': 0.35, 'stroke-width': 1.2 }, svg);
      el('circle', { cx: x1, cy: y1, r: 1.6, fill: 'currentColor', 'fill-opacity': 0.45 }, svg);
    }
    polyline(svg, ex.map(function (q) { return px(q[1]); }), ex.map(function (q) { return pv(q[2]); }), { stroke: 'var(--cw-accent)', 'stroke-width': 2.4 });
    text(svg, (PX0 + PX1) / 2, PY1 + 30, 'phase plane: arrows = f, what a neural ODE learns', { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.85 });
    el('line', { x1: TX0, x2: TX1, y1: ty(0), y2: ty(0), stroke: 'currentColor', 'stroke-opacity': 0.2 }, svg);
    [-1, 0, 1].forEach(function (q) { text(svg, TX0 - 6, ty(q) + 4, String(q), { 'text-anchor': 'end', 'font-size': 11, opacity: 0.7 }); });
    [0, 0.25, 0.5, 0.75, 1].forEach(function (q) { text(svg, tx(q), PY1 + 16, String(q), { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.7 }); });
    text(svg, (TX0 + TX1) / 2, PY1 + 30, 'time t (s)', { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.8 });
    text(svg, TX0 - 30, PY0 + 4, 'x (m)', { 'font-size': 11, opacity: 0.8 });
    polyline(svg, ex.map(function (q) { return tx(q[0]); }), ex.map(function (q) { return ty(q[1]); }), { stroke: 'var(--cw-accent)', 'stroke-width': 2.4 });
    var lg = [['gray arrows: f(h), the vector field', 'currentColor', 0.5], ['orange: RNN steps, h(k+1) = h(k) + Δt f(h(k))', 'var(--cw-accent2)', 1],
      ['blue: the ODE solution, the limit Δt → 0', 'var(--cw-accent)', 1]];
    lg.forEach(function (q, j) {
      el('line', { x1: TX1 - 262, x2: TX1 - 244, y1: PY0 + 4 + 14 * j, y2: PY0 + 4 + 14 * j, stroke: q[1], 'stroke-width': 2.4, 'stroke-opacity': q[2] }, svg);
      text(svg, TX1 - 238, PY0 + 8 + 14 * j, q[0], { 'font-size': 10.5 });
    });
    var c1 = clipTo(svg, PX0, PY0, PX1 - PX0, PY1 - PY0), c2 = clipTo(svg, TX0, PY0, TX1 - TX0, PY1 - PY0);
    var dyn = el('g', {}, svg);
    var p = player(controls, DTS.length, draw, 1000);
    function draw(i) {
      clear(dyn);
      var r = runs[i].pts, big = r.length < 120;
      polyline(dyn, r.map(function (q) { return px(q[1]); }), r.map(function (q) { return pv(q[2]); }), { stroke: 'var(--cw-accent2)', 'stroke-width': 1.4, 'clip-path': c1 });
      polyline(dyn, r.map(function (q) { return tx(q[0]); }), r.map(function (q) { return ty(q[1]); }), { stroke: 'var(--cw-accent2)', 'stroke-width': 1.4, 'clip-path': c2 });
      if (big) r.forEach(function (q) {
        el('circle', { cx: px(q[1]), cy: pv(q[2]), r: 2.6, fill: 'var(--cw-accent2)', 'clip-path': c1 }, dyn);
        el('circle', { cx: tx(q[0]), cy: ty(q[1]), r: 2.6, fill: 'var(--cw-accent2)', 'clip-path': c2 }, dyn);
      });
      var e = runs[i].err;
      readout.textContent = 'Δt = ' + DTS[i] + ' s: ' + (r.length - 1) + ' steps for 1 s, largest error in x ' +
        (e > 1.15 ? 'over ' + e.toFixed(0) + ' m: the steps spiral out' : e.toFixed(3) + ' m') +
        (i > 0 && e < 1.15 ? ' (previous step size: ' + (runs[i - 1].err > 1.15 ? 'unstable' : runs[i - 1].err.toFixed(3) + ' m') + ')' : '') + '.';
    }
    p.set(0);
  };

  /* A plain network and a physics-informed network (PINN) trained on ten points
   * of a damped spring-mass. The player moves smoothly through 40 recorded
   * training steps, interpolating the curves between them. "Play motion" runs
   * time forward and moves three masses, each hanging at the displacement one
   * model predicts. Only the moving parts are redrawn. */
  WIDGETS['pinn-train'] = function (root, data) {
    var d = data.pinn, F = d.frames, t = d.t, n = t.length;
    var W = 720, H = 330, L = 46, PR = 500, T0 = 16, B = 292;
    var pos = F.length - 1, tc = 1, raf = null;
    html('div', { class: 'cw-title' }, root, 'A plain network and a PINN, trained on the same ten points');
    var svg = svgRoot(root, W, H, 'Training a plain network and a physics-informed network on a damped spring-mass');
    var c1 = html('div', { class: 'cw-controls' }, root);
    html('span', {}, c1, 'Play: the networks train, then the masses move.');
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'm = 1 kg, μ = 4 N·s/m, k = 400 N/m, released from x = 1 m at rest. Both networks have 3 hidden layers ' +
      'of 32 tanh units, the same starting weights and the same Adam steps (learning rate 0.001). The PINN also ' +
      'penalizes the equation\'s residual at 40 collocation points, the ticks on the time axis, with weight λ = 0.0001.');
    var sx = scale(0, 1, L, PR), sy = scale(-1.15, 1.35, B, T0), xs = t.map(sx);
    var tEnd = d.t_data[d.t_data.length - 1];
    var clip = clipTo(svg, L, T0, PR - L, B - T0);
    el('rect', { x: sx(0), y: T0, width: sx(tEnd) - sx(0), height: B - T0, fill: 'currentColor', 'fill-opacity': 0.07 }, svg);
    text(svg, (sx(0) + sx(tEnd)) / 2, T0 + 12, 'training data', { 'text-anchor': 'middle', opacity: 0.7 });
    text(svg, (sx(tEnd) + PR) / 2, T0 + 12, 'no data: extrapolation', { 'text-anchor': 'middle', opacity: 0.7 });
    el('line', { x1: L, x2: PR, y1: sy(0), y2: sy(0), stroke: 'currentColor', 'stroke-opacity': 0.2 }, svg);
    [-1, 0, 1].forEach(function (v) { text(svg, L - 6, sy(v) + 4, String(v), { 'text-anchor': 'end', 'font-size': 11, opacity: 0.7 }); });
    [0, 0.25, 0.5, 0.75, 1].forEach(function (v) { text(svg, sx(v), B + 16, String(v), { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.7 }); });
    text(svg, (L + PR) / 2, B + 31, 'time t (s)', { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.8 });
    text(svg, 12, (T0 + B) / 2, 'x (m)', { 'font-size': 11, opacity: 0.8, transform: 'rotate(-90 12 ' + (T0 + B) / 2 + ')', 'text-anchor': 'middle' });
    d.t_phys.forEach(function (v) { el('line', { x1: sx(v), x2: sx(v), y1: B - 5, y2: B, stroke: 'var(--cw-accent)', 'stroke-opacity': 0.8 }, svg); });
    polyline(svg, xs, d.exact.map(sy), { stroke: 'currentColor', 'stroke-opacity': 0.3, 'stroke-width': 6, 'clip-path': clip });
    var lineNN = el('polyline', { fill: 'none', stroke: 'var(--cw-accent2)', 'stroke-width': 2.2, 'clip-path': clip }, svg);
    var linePI = el('polyline', { fill: 'none', stroke: 'var(--cw-accent)', 'stroke-width': 2.2, 'stroke-dasharray': '7 4', 'clip-path': clip }, svg);
    d.t_data.forEach(function (v, i) { el('circle', { cx: sx(v), cy: sy(d.x_data[i]), r: 3.6, fill: 'currentColor' }, svg); });
    var marker = el('line', { y1: T0, y2: B, stroke: 'currentColor', 'stroke-opacity': 0.55, 'stroke-dasharray': '3 3' }, svg);
    el('line', { x1: 538, x2: 712, y1: T0 - 2, y2: T0 - 2, stroke: 'currentColor', 'stroke-width': 3 }, svg);
    var masses = [['truth', 'currentColor'], ['network', 'var(--cw-accent2)'], ['PINN', 'var(--cw-accent)']].map(function (mm, j) {
      var cx = 566 + 58 * j;
      text(svg, cx, B + 16, mm[0], { 'text-anchor': 'middle', 'font-size': 11 });
      return {
        cx: cx,
        guide: el('line', { x1: PR, x2: cx - 18, stroke: mm[1], 'stroke-opacity': 0.25, 'stroke-dasharray': '2 3' }, svg),
        spring: el('polyline', { fill: 'none', stroke: mm[1], 'stroke-width': 1.6 }, svg),
        box: el('rect', { x: cx - 16, width: 32, height: 24, rx: 3, fill: mm[1], 'fill-opacity': j ? 0.85 : 0.35 }, svg)
      };
    });
    var cur = { nn: F[0].nn, pinn: F[0].pinn };
    // One Play: the curves train, then the three masses move through the second.
    function stopMotion() { if (raf) cancelAnimationFrame(raf); raf = null; }
    function playMotion() {
      stopMotion();
      var start = null;
      tc = 0;
      function tick(now) {
        if (start === null) start = now;
        tc = Math.min(1, (now - start) / 4000);
        place();
        if (tc < 1) raf = requestAnimationFrame(tick); else raf = null;
      }
      raf = requestAnimationFrame(tick);
    }
    var p = smoothPlayer(c1, F.length, function (q) { pos = q; curves(); place(); }, 0.32, function (on) {
      if (on) { stopMotion(); tc = 1; place(); }
      else if (pos >= F.length - 1) playMotion();
    });
    function curves() {
      var i = Math.min(F.length - 2, Math.floor(pos)), w = pos - i, a = F[i], b = F[i + 1];
      cur.nn = lerpArr(a.nn, b.nn, w);
      cur.pinn = lerpArr(a.pinn, b.pinn, w);
      lineNN.setAttribute('points', pts(xs, cur.nn.map(sy)));
      linePI.setAttribute('points', pts(xs, cur.pinn.map(sy)));
      var stepNo = Math.round(lerp(a.step, b.step, w));
      readout.textContent = 'Step ' + stepNo + ': error over the whole second, network ' + lerp(a.nn_rmse, b.nn_rmse, w).toFixed(3) +
        ' m, PINN ' + lerp(a.pinn_rmse, b.pinn_rmse, w).toFixed(3) + ' m; PINN residual at the collocation points ' +
        lerp(a.pinn_phys, b.pinn_phys, w).toFixed(1) + ' N.';
    }
    function place() {
      var vals = [interp1(t, d.exact, tc), interp1(t, cur.nn, tc), interp1(t, cur.pinn, tc)];
      marker.setAttribute('x1', sx(tc));
      marker.setAttribute('x2', sx(tc));
      masses.forEach(function (mm, j) {
        var cy = Math.max(T0 + 40, Math.min(B - 14, sy(vals[j])));
        mm.guide.setAttribute('y1', sy(vals[j]));
        mm.guide.setAttribute('y2', cy);
        mm.spring.setAttribute('points', coilPts(mm.cx, T0 - 2, cy - 12, 7));
        mm.box.setAttribute('y', cy - 12);
      });
    }
    p.set(F.length - 1);
  };

  /* A new batch of the fed-batch bioreactor, predicted by the true mechanistic
   * model, by the neural ODE trained the sequential way, and by the neural DAE,
   * which keeps S >= 0. Three vessels show the substrate level; a level below
   * the floor is a negative concentration. Time moves continuously. */
  WIDGETS['fedbatch-run'] = function (root, data) {
    var d = data.fedbatch, t = d.t, n = t.length;
    var dae = t.map(function (v) { return interp1(d.dae.t, d.dae.S, v); });
    var series = [['true model', d.truth.S, 'currentColor'], ['neural ODE', d.node.S, 'var(--cw-accent2)'],
      ['neural DAE', dae, 'var(--cw-accent)']];
    var W = 720, H = 320, L = 46, PR = 470, T0 = 14, B = 270;
    html('div', { class: 'cw-title' }, root, 'A new batch: the true model, the neural ODE and the neural DAE');
    var svg = svgRoot(root, W, H, 'Substrate concentration in a new fed-batch run, predicted by a neural ODE and by a neural DAE');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Both models learned the growth rate from the same three batches, 0 to 40 h. New batch: X = ' + d.ic[0] + ' g/L, S = ' + d.ic[2] +
      ' g/L, V = ' + d.ic[3] + ' L at the start. The neural ODE was trained and is integrated with Diffrax; the neural DAE ' +
      'is trained and solved with SiNDAE, with S ≥ 0 as a constraint. Red below the floor is a negative concentration.');
    var sx = scale(0, 60, L, PR), sy = scale(-1.6, 7.6, B, T0);
    el('rect', { x: L, y: sy(0), width: PR - L, height: B - sy(0), fill: RED, 'fill-opacity': 0.09 }, svg);
    text(svg, PR - 6, B - 8, 'S < 0: impossible', { 'text-anchor': 'end', 'font-size': 11, style: 'fill:' + RED });
    el('line', { x1: L, x2: PR, y1: sy(0), y2: sy(0), stroke: 'currentColor', 'stroke-opacity': 0.4 }, svg);
    [0, 2, 4, 6].forEach(function (v) { text(svg, L - 6, sy(v) + 4, String(v), { 'text-anchor': 'end', 'font-size': 11, opacity: 0.7 }); });
    [0, 10, 20, 30, 40, 50, 60].forEach(function (v) { text(svg, sx(v), B + 16, String(v), { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.7 }); });
    text(svg, (L + PR) / 2, B + 31, 'time (h)', { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.8 });
    text(svg, 12, (T0 + B) / 2, 'S (g/L)', { 'font-size': 11, opacity: 0.8, transform: 'rotate(-90 12 ' + (T0 + B) / 2 + ')', 'text-anchor': 'middle' });
    var parts = series.map(function (s, j) {
      polyline(svg, t.map(sx), s[1].map(sy), { stroke: s[2], 'stroke-opacity': 0.15, 'stroke-width': j ? 1.5 : 5 });
      var vx = 510 + 72 * j, top = 40, floor = 190, w = 46;
      el('rect', { x: vx, y: top, width: w, height: floor - top, rx: 8, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.6 }, svg);
      text(svg, vx + w / 2, top - 8, s[0], { 'text-anchor': 'middle', 'font-size': 11 });
      return {
        line: el('polyline', { fill: 'none', stroke: s[2], 'stroke-width': j ? 2.4 : 6, 'stroke-opacity': j ? 1 : 0.35, 'stroke-dasharray': j === 2 ? '7 4' : 'none' }, svg),
        dot: el('circle', { r: 4, fill: s[2] }, svg),
        liquid: el('rect', { x: vx + 3, width: w - 6, fill: s[2], 'fill-opacity': j ? 0.55 : 0.3 }, svg),
        neg: el('rect', { x: vx + 3, y: floor + 2, width: w - 6, fill: RED, 'fill-opacity': 0.75 }, svg),
        val: text(svg, vx + w / 2, 268, '', { 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 600 }),
        top: top, floor: floor
      };
    });
    series.forEach(function (s, j) { text(svg, 510 + 72 * j + 23, 282, 'g/L', { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 }); });
    var p = smoothPlayer(controls, n, draw, 0.06);
    function draw(q) {
      var tq = q / (n - 1) * 60, k = Math.floor(q);
      series.forEach(function (s, j) {
        var P = parts[j], S = interp1(t, s[1], tq);
        var xs = t.slice(0, k + 1).map(sx).concat([sx(tq)]), ys = s[1].slice(0, k + 1).map(sy).concat([sy(S)]);
        P.line.setAttribute('points', pts(xs, ys));
        P.dot.setAttribute('cx', sx(tq));
        P.dot.setAttribute('cy', sy(S));
        var hgt = (P.floor - P.top) * Math.max(0, S) / 7.5;
        P.liquid.setAttribute('y', P.floor - hgt);
        P.liquid.setAttribute('height', hgt);
        P.neg.setAttribute('height', S < 0 ? (P.floor - P.top) * (-S) / 7.5 : 0);
        P.val.textContent = S.toFixed(2);
        P.val.setAttribute('style', 'fill:' + (S < 0 ? RED : 'currentColor'));
      });
      var Sn = interp1(t, d.node.S, tq);
      readout.textContent = 't = ' + tq.toFixed(1) + ' h: substrate, true model ' + interp1(t, d.truth.S, tq).toFixed(2) +
        ' g/L; neural ODE ' + Sn.toFixed(2) + ' g/L' + (Sn < 0 ? ' (impossible)' : '') + '; neural DAE ' +
        interp1(t, dae, tq).toFixed(2) + ' g/L.  Over the 60 h the neural ODE spends ' + d.summary.hours_below +
        ' h below zero, reaching ' + d.summary.minS_node + ' g/L.';
    }
    p.set(n - 1);
  };

  /* Training a network whose last layer is a projection onto a mass balance,
   * y1 + y2 = F. The strip on top is the architecture; while playing, a pulse
   * runs forward through it and the gradient runs back through the projection.
   * Left: the outputs in the (y1, y2) plane. Right: how far each network's
   * outputs break the balance, epoch by epoch, with and without the layer. */
  WIDGETS['proj-train'] = function (root, data) {
    var d = data.proj, Fr = d.frames, nF = Fr.length;
    var W = 720, H = 350;
    html('div', { class: 'cw-title' }, root, 'Training with a projection layer: no energy from nothing, at any epoch');
    var svg = svgRoot(root, W, H, 'Architecture of a network with a projection layer, the energy imbalance of its predictions during training, and the largest imbalance against epoch');
    var controls = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'A counterflow heat exchanger, water on both sides: hot water in at 90 °C, cold water in at 20 °C and 1 kg/s. The network ' +
      'maps the hot-water flow to the two outlet temperatures. 40 measurements with noise SD 1 °C on each temperature, so the ' +
      'measurements themselves break the energy balance. Both networks: 2 hidden layers of 16 tanh units, same starting weights, ' +
      'Adam with learning rate 0.01.');
    // architecture strip
    var boxes = [['flow ṁh', 8, 78], ['network', 102, 208], ['raw ỹ', 232, 302], ['projection', 326, 456], ['y', 480, 530], ['loss vs data', 554, 712]];
    var by = 12, bh = 34;
    boxes.forEach(function (b, i) {
      el('rect', { x: b[1], y: by, width: b[2] - b[1], height: bh, rx: 6, fill: i === 3 ? 'var(--cw-green)' : 'currentColor', 'fill-opacity': i === 3 ? 0.22 : 0.06, stroke: i === 3 ? 'var(--cw-green)' : 'currentColor', 'stroke-opacity': 0.6 }, svg);
      text(svg, (b[1] + b[2]) / 2, by + 22, b[0], { 'text-anchor': 'middle', 'font-size': 13, 'font-weight': i === 3 ? 700 : 400 });
      if (i < boxes.length - 1) el('line', { x1: b[2] + 2, x2: boxes[i + 1][1] - 4, y1: by + bh / 2, y2: by + bh / 2, stroke: 'currentColor', 'stroke-width': 1.6 }, svg);
    });
    text(svg, 391, by + bh + 13, 'y = ỹ − a(aᵀỹ − b)/(aᵀa): linear, no weights', { 'text-anchor': 'middle', 'font-size': 10.5, opacity: 0.85 });
    el('path', { d: 'M 633 ' + (by + bh) + ' L 633 ' + (by + bh + 26) + ' L 155 ' + (by + bh + 26) + ' L 155 ' + (by + bh + 2), fill: 'none', stroke: RED, 'stroke-width': 1.6, 'stroke-dasharray': '5 3' }, svg);
    text(svg, 180, by + bh + 22, 'gradient ∂L/∂θ, back through the projection', { 'font-size': 10.5, style: 'fill:' + RED });
    var pulse = el('circle', { r: 5.5, fill: 'var(--cw-accent2)', opacity: 0 }, svg);
    // energy imbalance against the hot-water flow
    var X0 = 56, X1 = 380, Y0 = 108, Y1 = 300;
    var px = scale(0.2, 2.0, X0, X1), py = scale(-20, 20, Y1, Y0);
    el('rect', { x: X0, y: py(20), width: X1 - X0, height: py(0) - py(20), fill: RED, 'fill-opacity': 0.06 }, svg);
    el('rect', { x: X0, y: py(0), width: X1 - X0, height: py(-20) - py(0), fill: 'var(--cw-accent)', 'fill-opacity': 0.05 }, svg);
    el('rect', { x: X0, y: Y0, width: X1 - X0, height: Y1 - Y0, fill: 'none', stroke: 'currentColor', 'stroke-opacity': 0.25 }, svg);
    var cpl = clipTo(svg, X0, Y0, X1 - X0, Y1 - Y0);
    text(svg, X1 - 6, py(16), 'energy from nothing', { 'text-anchor': 'end', 'font-size': 11, style: 'fill:' + RED });
    text(svg, X1 - 6, py(-17), 'energy lost to nowhere', { 'text-anchor': 'end', 'font-size': 11, style: 'fill:var(--cw-accent)' });
    [-20, -10, 0, 10, 20].forEach(function (v) { text(svg, X0 - 5, py(v) + 4, String(v), { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 }); });
    [0.5, 1.0, 1.5, 2.0].forEach(function (v) { text(svg, px(v), Y1 + 13, v.toFixed(1), { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 }); });
    text(svg, (X0 + X1) / 2, Y1 + 27, 'hot-water flow (kg/s)', { 'text-anchor': 'middle', 'font-size': 11 });
    text(svg, X0, Y0 - 6, 'Qc − Qh (kW): heat taken − heat given up', { 'font-size': 11 });
    d.u.forEach(function (u, i) { el('circle', { cx: px(u), cy: py(d.meas[i]), r: 2.6, fill: 'currentColor', 'fill-opacity': 0.4, 'clip-path': cpl }, svg); });
    var plainLine = el('polyline', { fill: 'none', stroke: 'var(--cw-accent2)', 'stroke-width': 2.2, 'clip-path': cpl }, svg);
    var projLine = el('polyline', { fill: 'none', stroke: 'var(--cw-accent)', 'stroke-width': 2.2, 'stroke-dasharray': '6 4', 'clip-path': cpl }, svg);
    var lx = X0 + 8;
    [['measured', 'currentColor', 0.4], ['plain network', 'var(--cw-accent2)', 1], ['with the layer', 'var(--cw-accent)', 1]].forEach(function (q, j) {
      el('circle', { cx: lx + 4, cy: Y0 + 12 + 15 * j, r: 3.5, fill: q[1], 'fill-opacity': q[2] }, svg);
      text(svg, lx + 12, Y0 + 16 + 15 * j, q[0], { 'font-size': 10.5 });
    });
    // violation chart
    var CX0 = 470, CX1 = 706, CY0 = 112, CY1 = 300;
    var cxs = scale(0, Math.log10(2000), CX0, CX1), cys = scale(-14, 3, CY1, CY0);
    function ex(e) { return cxs(Math.log10(Math.max(1, e))); }
    el('rect', { x: CX0, y: CY0, width: CX1 - CX0, height: CY1 - CY0, fill: 'none', stroke: 'currentColor', 'stroke-opacity': 0.25 }, svg);
    [2, -2, -6, -10, -14].forEach(function (v) { text(svg, CX0 - 5, cys(v) + 4, '1e' + v, { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 }); });
    [1, 10, 100, 1000].forEach(function (v) { text(svg, ex(v), CY1 + 13, String(v), { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 }); });
    text(svg, (CX0 + CX1) / 2, CY1 + 27, 'training epoch', { 'text-anchor': 'middle', 'font-size': 11 });
    text(svg, CX0, CY0 - 6, 'largest |Qc − Qh| (kW)', { 'font-size': 11 });
    var Fe = Fr.slice(1);
    polyline(svg, Fe.map(function (f) { return ex(f.epoch); }), Fe.map(function (f) { return cys(Math.log10(f.plain_viol)); }), { stroke: 'var(--cw-accent2)', 'stroke-width': 2 });
    polyline(svg, Fe.map(function (f) { return ex(f.epoch); }), Fe.map(function (f) { return cys(Math.log10(Math.max(f.viol, 1e-16))); }), { stroke: 'var(--cw-accent)', 'stroke-width': 2 });
    text(svg, CX1 - 4, cys(2.4) - 4, 'without the layer', { 'text-anchor': 'end', 'font-size': 10.5, style: 'fill:var(--cw-accent2)' });
    text(svg, CX1 - 4, cys(-11.5) - 6, 'with the layer: machine precision', { 'text-anchor': 'end', 'font-size': 10.5, style: 'fill:var(--cw-accent)' });
    var cur = el('line', { y1: CY0, y2: CY1, stroke: 'currentColor', 'stroke-opacity': 0.5, 'stroke-dasharray': '3 3' }, svg);
    var pRaf = null, pStart = null;
    function pulseLoop(now) {
      if (pStart === null) pStart = now;
      var ph = ((now - pStart) / 3600) % 1, x, y;
      if (ph < 0.55) { x = lerp(43, 633, ph / 0.55); y = by + bh / 2; pulse.setAttribute('fill', 'var(--cw-accent2)'); }
      else { var w = (ph - 0.55) / 0.45; x = lerp(633, 155, w); y = by + bh + 26; pulse.setAttribute('fill', RED); }
      pulse.setAttribute('cx', x);
      pulse.setAttribute('cy', y);
      pulse.setAttribute('opacity', 0.9);
      pRaf = requestAnimationFrame(pulseLoop);
    }
    var p = smoothPlayer(controls, nF, draw, 0.25, function (on) {
      if (on && !pRaf) pRaf = requestAnimationFrame(pulseLoop);
      if (!on && pRaf) { cancelAnimationFrame(pRaf); pRaf = null; pStart = null; pulse.setAttribute('opacity', 0); }
    });
    function pts(us, vs) { return us.map(function (u, j) { return px(u) + ',' + py(vs[j]); }).join(' '); }
    function draw(q) {
      var i = Math.min(nF - 2, Math.floor(q)), w = q - i, a = Fr[i], b = Fr[i + 1];
      plainLine.setAttribute('points', pts(d.ute, lerpArr(a.plain_imb, b.plain_imb, w)));
      projLine.setAttribute('points', pts(d.ute, lerpArr(a.imb, b.imb, w)));
      var ep = lerp(a.epoch, b.epoch, w);
      cur.setAttribute('x1', ex(ep));
      cur.setAttribute('x2', ex(ep));
      var f = w < 0.5 ? a : b;
      readout.textContent = 'Epoch ' + Math.round(ep) + ': error in the outlet temperatures, with the layer ' + f.rmse.toFixed(2) +
        ' °C, without ' + f.plain_rmse.toFixed(2) + ' °C. Largest energy imbalance, with the layer ' + sci(Math.max(f.viol, 1e-16)) +
        ' kW, without ' + f.plain_viol.toFixed(2) + ' kW.';
    }
    p.set(nF - 1);
  };

  // ------------------------------------------------------------------ L14

  var NORM_Z = { 0.1: 0.1257, 0.2: 0.2533, 0.3: 0.3853, 0.4: 0.5244, 0.5: 0.6745, 0.6: 0.8416,
    0.7: 1.0364, 0.8: 1.2816, 0.9: 1.6449, 0.95: 1.96 };

  /* Prediction intervals on the concrete strength dataset's test mixes, for three
   * methods and two test sets, at any nominal level. Each mix is a bar from its
   * interval; red where the interval misses the measured strength. The right
   * panel is the reliability diagram for the chosen method and test set. */
  WIDGETS.coverage = function (root, data) {
    var d = data.uq, LV = d.levels, split = 0, method = 0;
    var METHODS = ['GP', 'ensemble', 'conformal'];
    var NAMES = ['Gaussian process', 'ensemble spread', 'split conformal'];
    var W = 720, H = 320, L = 46, PR = 470, T0 = 14, B = 270;
    html('div', { class: 'cw-title' }, root, 'Do the intervals contain the truth as often as they claim?');
    var svg = svgRoot(root, W, H, 'Prediction intervals on the test mixes and the reliability diagram');
    var c1 = html('div', { class: 'cw-controls' }, root);
    var c2 = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Concrete strength dataset, Lecture 9\'s grouped split (195 test rows) and an extrapolation split that holds out the ' +
      '20% of mixes with the lowest water/cement ratio (265 rows, the strongest mixes). Test mixes are sorted by measured ' +
      'strength. Ensemble: five of Lecture 9\'s networks, interval from their spread alone. Conformal: width set on 210 calibration rows.');
    toggleGroup(c1, ['Grouped split', 'Extrapolation split'], 0, function (v) { split = v; draw(p.get()); });
    toggleGroup(c2, NAMES, 0, function (v) { method = v; draw(p.get()); });
    var p = player(c1, LV.length, draw, 500);

    function halfwidths(s, lv) {
      var i = LV.indexOf(lv), z = NORM_Z[lv];
      if (method === 0) return s.gp_sd_pts.map(function (v) { return z * v; });
      if (method === 1) return s.ens_sd_pts.map(function (v) { return z * v; });
      return s.y.map(function () { return s.q[i]; });
    }
    function centers(s) { return method === 0 ? s.gp_mu : method === 1 ? s.ens_mu : s.conf_mu; }

    function draw(li) {
      clear(svg);
      var s = d.splits[split], lv = LV[li], hw = halfwidths(s, lv), c = centers(s);
      var order = s.y.map(function (_, i) { return i; }).sort(function (a, b) { return s.y[a] - s.y[b]; });
      var sx = scale(0, order.length - 1, L, PR), sy = scale(-10, 100, B, T0);
      [0, 20, 40, 60, 80].forEach(function (v) {
        el('line', { x1: L, x2: PR, y1: sy(v), y2: sy(v), stroke: 'currentColor', 'stroke-opacity': 0.08 }, svg);
        text(svg, L - 6, sy(v) + 4, String(v), { 'text-anchor': 'end', 'font-size': 11, opacity: 0.7 });
      });
      text(svg, 12, (T0 + B) / 2, 'MPa', { 'font-size': 11, opacity: 0.8 });
      text(svg, (L + PR) / 2, B + 18, 'test mixes, sorted by measured strength', { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.8 });
      var hit = 0;
      order.forEach(function (i, k) {
        var ok = Math.abs(s.y[i] - c[i]) < hw[i];
        if (ok) hit++;
        var col = ok ? 'var(--cw-accent)' : RED;
        el('line', { x1: sx(k), x2: sx(k), y1: sy(c[i] - hw[i]), y2: sy(c[i] + hw[i]), stroke: col, 'stroke-opacity': ok ? 0.35 : 0.7, 'stroke-width': 1.5 }, svg);
        el('circle', { cx: sx(k), cy: sy(s.y[i]), r: 1.8, fill: ok ? 'currentColor' : RED }, svg);
      });
      // Reliability diagram.
      var rx = scale(0, 1, 520, 700), ry = scale(0, 1, 230, 50);
      el('rect', { x: 520, y: 50, width: 180, height: 180, fill: 'none', stroke: 'currentColor', 'stroke-opacity': 0.25 }, svg);
      el('line', { x1: rx(0), y1: ry(0), x2: rx(1), y2: ry(1), stroke: 'currentColor', 'stroke-dasharray': '4 3', 'stroke-opacity': 0.6 }, svg);
      var cov = s.coverage[METHODS[method]];
      polyline(svg, LV.map(rx), cov.map(ry), { stroke: 'var(--cw-accent2)', 'stroke-width': 2 });
      LV.forEach(function (v, i) { el('circle', { cx: rx(v), cy: ry(cov[i]), r: i === li ? 6 : 2.5, fill: 'var(--cw-accent2)' }, svg); });
      text(svg, 610, 40, 'reliability diagram', { 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 600 });
      text(svg, 610, 250, 'nominal coverage', { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.8 });
      text(svg, 512, 140, 'observed', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.8 });
      text(svg, 690, 222, 'below: overconfident', { 'text-anchor': 'end', 'font-size': 10, style: 'fill:' + RED });
      var width = hw.reduce(function (a, b) { return a + b; }, 0) / hw.length * 2;
      readout.textContent = NAMES[method] + ', ' + (split ? 'extrapolation split' : 'grouped split') + ', nominal ' +
        Math.round(lv * 100) + '%: ' + hit + ' of ' + order.length + ' test mixes inside their interval (' +
        Math.round(100 * hit / order.length) + '%); mean width ' + width.toFixed(1) + ' MPa.';
    }
    p.set(LV.length - 1);
  };

  /* Bayesian optimization on a 1-D test function with two peaks. Pick the
   * acquisition; each step fits the GP to the points so far, maximizes the
   * acquisition and evaluates there. All eight iterations of each run were
   * recorded by lectures/l14/figures/make_figures.py. */
  WIDGETS['bo-loop'] = function (root, data) {
    var d = data.bo, kinds = ['EI', 'PI', 'UCB'], kind = 0;
    var NAMES = ['expected improvement', 'probability of improvement', 'upper confidence bound, κ = 3'];
    var W = 720, H = 330, L = 46, R = 16;
    html('div', { class: 'cw-title' }, root, 'The Bayesian optimization loop, one evaluation at a time');
    var svg = svgRoot(root, W, H, 'Gaussian process, acquisition function and next evaluation at each iteration');
    var c1 = html('div', { class: 'cw-controls' }, root);
    var c2 = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Maximize g(x) = −(6x − 2)² sin(12x − 4) on [0, 1] (the Forrester et al. benchmark, flipped). Global maximum 6.02 at ' +
      'x = 0.758, a smaller peak near 0.15. Start: four points at 0, 0.33, 0.66 and 1. Gray: the true function, hidden from the ' +
      'optimizer. Blue: the GP mean and 95% band. Green: the acquisition, scaled to its maximum.');
    toggleGroup(c2, NAMES, 0, function (v) { kind = v; draw(p.get()); });
    var p = player(c1, 8, draw, 900);
    function g(x) { return -Math.pow(6 * x - 2, 2) * Math.sin(12 * x - 4); }

    function draw(i) {
      clear(svg);
      var fr = d.runs[kinds[kind]][i], grid = d.grid;
      var sx = scale(0, 1, L, W - R), sy = scale(-22, 12, 200, 12), sa = scale(0, 1, 300, 222);
      el('line', { x1: L, x2: W - R, y1: sy(0), y2: sy(0), stroke: 'currentColor', 'stroke-opacity': 0.12 }, svg);
      [-20, -10, 0, 10].forEach(function (v) { text(svg, L - 6, sy(v) + 4, String(v), { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 }); });
      var up = fr.mu.map(function (m, j) { return m + 1.96 * fr.sd[j]; }), lo = fr.mu.map(function (m, j) { return m - 1.96 * fr.sd[j]; });
      var pts = grid.map(function (x, j) { return sx(x).toFixed(1) + ',' + sy(up[j]).toFixed(1); })
        .concat(grid.slice().reverse().map(function (x, j) { var k = grid.length - 1 - j; return sx(x).toFixed(1) + ',' + sy(lo[k]).toFixed(1); }));
      el('polygon', { points: pts.join(' '), fill: 'var(--cw-accent)', 'fill-opacity': 0.15 }, svg);
      polyline(svg, grid.map(sx), d.truth.map(sy), { stroke: 'currentColor', 'stroke-opacity': 0.35, 'stroke-width': 2.5 });
      polyline(svg, grid.map(sx), fr.mu.map(sy), { stroke: 'var(--cw-accent)', 'stroke-width': 2 });
      fr.x.forEach(function (x, j) { el('circle', { cx: sx(x), cy: sy(fr.y[j]), r: 4, fill: 'currentColor' }, svg); });
      el('line', { x1: sx(fr.next), x2: sx(fr.next), y1: 12, y2: 300, stroke: RED, 'stroke-dasharray': '5 3', 'stroke-width': 1.5 }, svg);
      polyline(svg, grid.map(sx), fr.acq.map(sa), { stroke: 'var(--cw-green)', 'stroke-width': 2 });
      el('line', { x1: L, x2: W - R, y1: sa(0), y2: sa(0), stroke: 'currentColor', 'stroke-opacity': 0.25 }, svg);
      text(svg, L, 216, 'acquisition', { 'font-size': 11, style: 'fill:var(--cw-green)' });
      [0, 0.25, 0.5, 0.75, 1].forEach(function (v) { text(svg, sx(v), 316, String(v), { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 }); });
      var best = Math.max.apply(null, fr.y);
      readout.textContent = NAMES[kind] + ', iteration ' + (i + 1) + ': ' + fr.x.length + ' points evaluated, best so far ' +
        best.toFixed(2) + ' (true maximum 6.02). Next x = ' + fr.next.toFixed(3) + ', where g = ' + g(fr.next).toFixed(2) + '.';
    }
    p.set(0);
  };

  // ------------------------------------------------------------------ L14a

  /* Shared pieces for the uncertainty-quantification figures. Everything a toy figure
   * reports is exact rather than sampled: the truth f(x) and the noise sd s(x) are known,
   * so the chance that y lands in [lo, hi] at x is Phi((hi - f)/s) - Phi((lo - f)/s). */
  function erf(x) {
    // Abramowitz and Stegun 7.1.26, absolute error below 1.5e-7.
    var s = x < 0 ? -1 : 1, t = 1 / (1 + 0.3275911 * Math.abs(x));
    var y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) *
      t * Math.exp(-x * x);
    return s * y;
  }
  function Phi(z) { return 0.5 * (1 + erf(z / Math.SQRT2)); }
  function pcov(lo, hi, f, s) { return Phi((hi - f) / s) - Phi((lo - f) / s); }
  function mean(a) { var t = 0; a.forEach(function (v) { t += v; }); return a.length ? t / a.length : NaN; }
  var TRUTHS = {
    sin: function (x) { return Math.sin(2 * Math.PI * x); },
    step: function (x) { return (x < 0.5 ? -0.5 : 0.5) + 0.2 * Math.sin(2 * Math.PI * x); }
  };
  function linspace(a, b, n) { var o = []; for (var i = 0; i < n; i++) o.push(a + (b - a) * i / (n - 1)); return o; }

  function chol(A) {
    var n = A.length, L = [], i, j, k;
    for (i = 0; i < n; i++) L.push(new Float64Array(n));
    for (i = 0; i < n; i++) {
      for (j = 0; j <= i; j++) {
        var s = A[i][j];
        for (k = 0; k < j; k++) s -= L[i][k] * L[j][k];
        if (i === j) { if (s <= 0) return null; L[i][i] = Math.sqrt(s); } else L[i][j] = s / L[j][j];
      }
    }
    return L;
  }
  function fwd(L, b) {
    var n = b.length, x = new Float64Array(n);
    for (var i = 0; i < n; i++) { var s = b[i]; for (var k = 0; k < i; k++) s -= L[i][k] * x[k]; x[i] = s / L[i][i]; }
    return x;
  }
  function bwd(L, b) {
    var n = b.length, x = new Float64Array(n);
    for (var i = n - 1; i >= 0; i--) { var s = b[i]; for (var k = i + 1; k < n; k++) s -= L[k][i] * x[k]; x[i] = s / L[i][i]; }
    return x;
  }
  /* A zero-mean GP with an RBF kernel and a noise variance per training point.
   * Returns null when the kernel matrix is not positive definite. */
  function gpFit(xs, ys, ell, sf, nvar) {
    var n = xs.length, K = [], i, j;
    for (i = 0; i < n; i++) {
      K.push([]);
      for (j = 0; j < n; j++) {
        var d = (xs[i] - xs[j]) / ell;
        K[i].push(sf * sf * Math.exp(-0.5 * d * d) + (i === j ? (typeof nvar === 'number' ? nvar : nvar[i]) + 1e-10 : 0));
      }
    }
    var L = chol(K);
    if (!L) return null;
    var alpha = bwd(L, fwd(L, ys));
    var logdet = 0, quad = 0;
    for (i = 0; i < n; i++) { logdet += 2 * Math.log(L[i][i]); quad += ys[i] * alpha[i]; }
    return {
      lml: -0.5 * quad - 0.5 * logdet - 0.5 * n * Math.log(2 * Math.PI),
      quad: quad, logdet: logdet,
      predict: function (x) {
        var k = xs.map(function (xi) { var d = (x - xi) / ell; return sf * sf * Math.exp(-0.5 * d * d); });
        var m = 0;
        for (var t = 0; t < n; t++) m += k[t] * alpha[t];
        var v = fwd(L, k), vv = 0;
        for (t = 0; t < n; t++) vv += v[t] * v[t];
        return [m, Math.max(sf * sf - vv, 1e-12)];
      }
    };
  }
  function band(parent, xs, lo, hi, sx, sy, attrs) {
    var pts = xs.map(function (x, j) { return sx(x).toFixed(1) + ',' + sy(hi[j]).toFixed(1); })
      .concat(xs.slice().reverse().map(function (x, j) { var k = xs.length - 1 - j; return sx(x).toFixed(1) + ',' + sy(lo[k]).toFixed(1); }));
    var a = { points: pts.join(' ') };
    for (var k in attrs) a[k] = attrs[k];
    return el('polygon', a, parent);
  }
  function slider(controls, label, min, max, step, value, show, onInput) {
    var lab = html('label', {}, controls, label + ' ');
    var r = html('input', { type: 'range', min: min, max: max, step: step, value: value }, lab);
    var out = html('span', {}, lab, show(value));
    r.oninput = function () { out.textContent = show(+r.value); onInput(+r.value); };
    return { input: r, set: function (v) { r.value = v; out.textContent = show(v); } };
  }
  function axes1d(svg, sx, sy, xt, yt, L, R, T, B) {
    yt.forEach(function (v) {
      el('line', { x1: L, x2: R, y1: sy(v), y2: sy(v), stroke: 'currentColor', 'stroke-opacity': v === 0 ? 0.18 : 0.07 }, svg);
      text(svg, L - 6, sy(v) + 4, String(v), { 'text-anchor': 'end', 'font-size': 11, opacity: 0.7 });
    });
    xt.forEach(function (v) { text(svg, sx(v), B + 16, String(v), { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.7 }); });
  }
  function pct(v) { return isFinite(v) ? Math.round(100 * v) + '%' : '–'; }

  /* Aleatoric and epistemic uncertainty. A GP with the true noise level and fixed kernel
   * settings, fitted to the first n of a fixed sequence of noisy points, so moving the n
   * slider adds points rather than redrawing them. */
  WIDGETS['uq-sources'] = function (root) {
    var W = 720, H = 300, L = 40, R = 706, T = 12, B = 268, sigma = 0.15, n = 8;
    html('div', { class: 'cw-title' }, root, 'Which part of the uncertainty does more data remove?');
    var svg = svgRoot(root, W, H, 'A Gaussian process band split into noise and model uncertainty');
    var c1 = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Truth sin(2πx), observed on [0, 1] with Gaussian noise. The GP is given the true noise level and a fixed ' +
      'length scale of 0.2, so the only thing that changes is the data. Dark band: epistemic (the GP\'s uncertainty ' +
      'about f). Light band: total, epistemic plus the noise. Both at ±1.96 standard deviations.');
    var rng = mulberry(11), X = [], E = [];
    for (var i = 0; i < 60; i++) { X.push(rng()); E.push(gauss(rng)); }
    slider(c1, 'noise sd', 0.02, 0.4, 0.01, sigma, function (v) { return v.toFixed(2); }, function (v) { sigma = v; draw(); });
    slider(c1, 'points', 1, 60, 1, n, function (v) { return String(v); }, function (v) { n = v; draw(); });
    var grid = linspace(-0.2, 1.4, 161);
    function draw() {
      clear(svg);
      var sx = scale(-0.2, 1.4, L, R), sy = scale(-2.2, 2.2, B, T);
      axes1d(svg, sx, sy, [0, 0.5, 1], [-2, -1, 0, 1, 2], L, R, T, B);
      el('rect', { x: sx(1), y: T, width: sx(1.4) - sx(1), height: B - T, fill: 'currentColor', 'fill-opacity': 0.04 }, svg);
      el('rect', { x: sx(-0.2), y: T, width: sx(0) - sx(-0.2), height: B - T, fill: 'currentColor', 'fill-opacity': 0.04 }, svg);
      var xs = X.slice(0, n), ys = xs.map(function (x, j) { return TRUTHS.sin(x) + sigma * E[j]; });
      var gp = gpFit(xs, ys, 0.2, 1, sigma * sigma);
      var P = grid.map(function (x) { return gp.predict(x); });
      var mu = P.map(function (p) { return p[0]; }), ve = P.map(function (p) { return p[1]; });
      band(svg, grid, mu.map(function (m, j) { return m - 1.96 * Math.sqrt(ve[j] + sigma * sigma); }),
        mu.map(function (m, j) { return m + 1.96 * Math.sqrt(ve[j] + sigma * sigma); }), sx, sy,
        { fill: 'var(--cw-accent)', 'fill-opacity': 0.14 });
      band(svg, grid, mu.map(function (m, j) { return m - 1.96 * Math.sqrt(ve[j]); }),
        mu.map(function (m, j) { return m + 1.96 * Math.sqrt(ve[j]); }), sx, sy,
        { fill: 'var(--cw-accent2)', 'fill-opacity': 0.35 });
      polyline(svg, grid.map(sx), grid.map(function (x) { return sy(TRUTHS.sin(x)); }), { stroke: 'currentColor', 'stroke-opacity': 0.35, 'stroke-width': 2.5 });
      polyline(svg, grid.map(sx), mu.map(sy), { stroke: 'var(--cw-accent)', 'stroke-width': 2 });
      xs.forEach(function (x, j) { el('circle', { cx: sx(x), cy: sy(ys[j]), r: 3.5, fill: 'currentColor' }, svg); });
      text(svg, sx(1.2), T + 14, 'no data', { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.7 });
      var inside = [];
      grid.forEach(function (x, j) { if (x >= 0 && x <= 1) inside.push(Math.sqrt(ve[j])); });
      var epi = mean(inside);
      readout.textContent = n + ' points. Across [0, 1] the epistemic sd averages ' + epi.toFixed(3) +
        ' and the noise sd is ' + sigma.toFixed(2) + ', so the noise is ' +
        Math.round(100 * sigma * sigma / (sigma * sigma + epi * epi)) + '% of the variance. Beyond the data the epistemic sd returns to 1, the prior.';
    }
    draw();
  };

  /* A GP you can fit by hand or by maximum likelihood, on one of four toy problems. Click
   * the plot to observe the truth, with its noise, at that x. */
  WIDGETS['gp-explorer'] = function (root, data) {
    var mode = root.getAttribute('data-mode') || 'smooth';
    var S = data.gp.scenarios[mode], f = TRUTHS[S.truth];
    var W = 720, H = 300, L = 40, R = 706, T = 12, B = 268;
    var ell = S.fit[0], sf = S.fit[1], sn = S.fit[2], hetero = false;
    var TITLES = { smooth: 'A Gaussian process on a smooth function', hetero: 'One noise level, when the noise grows with x',
      step: 'A smooth kernel on a function with a step', few: 'Five points, and the fitted settings' };
    html('div', { class: 'cw-title' }, root, TITLES[mode]);
    var svg = svgRoot(root, W, H, 'A Gaussian process fit with its 95% band and the true function');
    var c1 = html('div', { class: 'cw-controls' }, root);
    var c2 = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Gray: the truth. Blue: the GP mean and its 95% band for a new observation. Click the plot to observe the truth, ' +
      'with noise, at that x. "Fit" maximizes the log marginal likelihood over the length scale and the noise, with ' +
      'the signal sd at its best value for each pair. Coverage is exact against the known truth and noise, not sampled. ' +
      'The noise sd is ' + (S.b ? S.a + ' + ' + S.b + 'x' : S.a) + '.');
    var X = S.x.slice(), Y = S.y.slice(), rng = mulberry(29);
    function nsd(x) { return S.a + S.b * Math.max(x, 0); }
    var sl = slider(c1, 'length scale', -2, 0.3, 0.01, Math.log10(ell), function (v) { return Math.pow(10, v).toFixed(3); },
      function (v) { ell = Math.pow(10, v); draw(); });
    var ss = slider(c1, 'signal sd', 0.1, 3, 0.01, sf, function (v) { return v.toFixed(2); }, function (v) { sf = v; draw(); });
    var sn_ = slider(c1, 'noise sd', -2.5, -0.3, 0.01, Math.log10(sn), function (v) { return Math.pow(10, v).toFixed(3); },
      function (v) { sn = Math.pow(10, v); draw(); });
    var fitB = html('button', { type: 'button' }, c2, 'Fit by maximum likelihood');
    var resetB = html('button', { type: 'button' }, c2, 'Reset data');
    if (mode === 'hetero') {
      toggleGroup(c2, ['one noise level', 'noise learned per point'], 0, function (v) { hetero = v === 1; draw(); });
    }
    fitB.onclick = function () { fit(); draw(); };
    resetB.onclick = function () { X = S.x.slice(); Y = S.y.slice(); ell = S.fit[0]; sf = S.fit[1]; sn = S.fit[2]; sync(); draw(); };
    function sync() { sl.set(Math.log10(ell)); ss.set(sf); sn_.set(Math.log10(sn)); }
    function fit() {
      // Profile out the signal variance: for kernel sf^2 (R + lam I), the best sf^2 is y'A^-1 y / n.
      var best = null, n = X.length;
      linspace(-2, 0.3, 36).forEach(function (le) {
        linspace(-5, 1, 31).forEach(function (ll) {
          var g = gpFit(X, Y, Math.pow(10, le), 1, Math.pow(10, ll));
          if (!g) return;
          var s2 = g.quad / n, lml = -0.5 * n - 0.5 * (g.logdet + n * Math.log(s2));
          if (!best || lml > best[0]) best = [lml, Math.pow(10, le), Math.sqrt(s2), Math.sqrt(Math.pow(10, ll) * s2)];
        });
      });
      ell = best[1]; sf = Math.min(3, best[2]); sn = Math.max(Math.pow(10, -2.5), Math.min(Math.pow(10, -0.3), best[3]));
      sync();
    }
    var grid = linspace(-0.1, 1.4, 151);
    svg.addEventListener('click', function (ev) {
      var pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
      var p = pt.matrixTransform(svg.getScreenCTM().inverse());
      var x = (p.x - L) / (R - L) * 1.5 - 0.1;
      if (x < -0.1 || x > 1.4) return;
      X.push(x); Y.push(f(x) + nsd(x) * gauss(rng));
      draw();
    });
    svg.style.cursor = 'crosshair';

    function model() {
      if (!hetero) {
        var g = gpFit(X, Y, ell, sf, sn * sn);
        return g && function (x) { var p = g.predict(x); return [p[0], p[1] + sn * sn]; };
      }
      // Noise per point: regress log squared residuals on x with a second GP, then refit.
      // For Gaussian noise E[log eps^2] = log s^2 - 1.27 and Var[log eps^2] = pi^2 / 2.
      var nv = X.map(function () { return sn * sn; }), g1 = null, g2 = null, m = 0;
      for (var it = 0; it < 3; it++) {
        g1 = gpFit(X, Y, ell, sf, nv);
        if (!g1) return null;
        var z = X.map(function (x, j) { var r = Y[j] - g1.predict(x)[0]; return Math.log(r * r + 1e-12) + 1.2704; });
        m = mean(z);
        var vz = mean(z.map(function (v) { return (v - m) * (v - m); }));
        g2 = gpFit(X, z.map(function (v) { return v - m; }), 0.3, Math.sqrt(Math.max(vz - 4.93, 0.1)), 4.93);
        if (!g2) return null;
        nv = X.map(function (x) { return Math.exp(m + g2.predict(x)[0]); });
      }
      g1 = gpFit(X, Y, ell, sf, nv);
      return g1 && function (x) { var p = g1.predict(x); return [p[0], p[1] + Math.exp(m + g2.predict(x)[0])]; };
    }

    function draw() {
      clear(svg);
      var sx = scale(-0.1, 1.4, L, R), sy = scale(-2.2, 2.2, B, T);
      axes1d(svg, sx, sy, [0, 0.5, 1], [-2, -1, 0, 1, 2], L, R, T, B);
      el('rect', { x: sx(1), y: T, width: sx(1.4) - sx(1), height: B - T, fill: 'currentColor', 'fill-opacity': 0.04 }, svg);
      var mdl = model();
      polyline(svg, grid.map(sx), grid.map(function (x) { return sy(f(x)); }), { stroke: 'currentColor', 'stroke-opacity': 0.35, 'stroke-width': 2.5 });
      if (!mdl) { readout.textContent = 'These settings give a kernel matrix that is not positive definite. Raise the noise.'; return; }
      var P = grid.map(mdl), mu = P.map(function (p) { return p[0]; }), sd = P.map(function (p) { return Math.sqrt(p[1]); });
      var lo = mu.map(function (m, j) { return m - 1.96 * sd[j]; }), hi = mu.map(function (m, j) { return m + 1.96 * sd[j]; });
      band(svg, grid, lo.map(function (v) { return Math.max(-2.5, v); }), hi.map(function (v) { return Math.min(2.5, v); }), sx, sy,
        { fill: 'var(--cw-accent)', 'fill-opacity': 0.18 });
      polyline(svg, grid.map(sx), mu.map(function (v) { return sy(Math.max(-2.5, Math.min(2.5, v))); }), { stroke: 'var(--cw-accent)', 'stroke-width': 2 });
      X.forEach(function (x, j) { el('circle', { cx: sx(x), cy: sy(Y[j]), r: 3.2, fill: 'currentColor' }, svg); });
      var cin = [], cout = [], th = [[], [], []];
      grid.forEach(function (x, j) {
        var c = pcov(lo[j], hi[j], f(x), nsd(x));
        if (x >= 0 && x <= 1) { cin.push(c); th[Math.min(2, Math.floor(x * 3))].push(c); } else if (x > 1) cout.push(c);
      });
      var msg = X.length + ' points; length scale ' + ell.toFixed(3) + ', signal sd ' + sf.toFixed(2) + ', noise sd ' + sn.toFixed(3) +
        '. 95% band covers ' + pct(mean(cin)) + ' of new observations in [0, 1] and ' + pct(mean(cout)) + ' beyond x = 1';
      if (mode === 'hetero') msg += '; by third of [0, 1]: ' + th.map(function (t) { return pct(mean(t)); }).join(', ');
      if (mode === 'step') {
        var near = [];
        grid.forEach(function (x, j) { if (Math.abs(x - 0.5) < 0.1) near.push(pcov(lo[j], hi[j], f(x), nsd(x))); });
        msg += '; within 0.1 of the step: ' + pct(mean(near));
      }
      readout.textContent = msg + '.';
    }
    draw();
  };

  /* Ten networks from different seeds, or from bootstrap resamples, trained on [0, 1]. */
  WIDGETS['ensemble-members'] = function (root, data) {
    var d = data.ens, kind = 0, k = 5, addNoise = false;
    var W = 720, H = 300, L = 40, R = 706, T = 12, B = 268;
    html('div', { class: 'cw-title' }, root, 'An ensemble\'s spread, inside the data and beyond it');
    var svg = svgRoot(root, W, H, 'Ensemble members, their mean and a 95% band');
    var c1 = html('div', { class: 'cw-controls' }, root);
    var c2 = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Truth sin(2πx) plus noise of sd 0.1, 120 points on [0, 1]. Each member is a two-layer ReLU network (32 units each) ' +
      'from scikit-learn. Seeds: all the data, different starting weights. Bootstrap: a resample of the data for each. ' +
      'The noise estimate is the sd of the training residuals of the ensemble mean. Coverage is exact against the truth.');
    toggleGroup(c1, ['different seeds', 'bootstrap resamples'], 0, function (v) { kind = v; draw(); });
    slider(c1, 'members', 2, 10, 1, k, function (v) { return String(v); }, function (v) { k = v; draw(); });
    toggleGroup(c2, ['band from the spread only', 'spread plus a noise estimate'], 0, function (v) { addNoise = v === 1; draw(); });
    function draw() {
      clear(svg);
      var M = (kind ? d.bootstrap : d.seeds).slice(0, k), g = d.grid;
      var sx = scale(0, 1.5, L, R), sy = scale(-3, 2, B, T);
      axes1d(svg, sx, sy, [0, 0.5, 1, 1.5], [-3, -2, -1, 0, 1, 2], L, R, T, B);
      el('rect', { x: sx(1), y: T, width: sx(1.5) - sx(1), height: B - T, fill: 'currentColor', 'fill-opacity': 0.05 }, svg);
      text(svg, sx(1.25), T + 14, 'no data', { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.7 });
      var mu = g.map(function (_, j) { return mean(M.map(function (m) { return m[j]; })); });
      var sp = g.map(function (_, j) {
        var mm = mu[j], t = 0;
        M.forEach(function (m) { t += (m[j] - mm) * (m[j] - mm); });
        return Math.sqrt(t / (M.length - 1));
      });
      var res = d.x.map(function (x, i) {
        var j = Math.min(g.length - 2, Math.floor(x / 0.01)), w = (x - g[j]) / (g[j + 1] - g[j]);
        return d.y[i] - (mu[j] * (1 - w) + mu[j + 1] * w);
      });
      var rm = mean(res), sn = Math.sqrt(res.reduce(function (a, r) { return a + (r - rm) * (r - rm); }, 0) / (res.length - 1));
      var sd = sp.map(function (s) { return addNoise ? Math.sqrt(s * s + sn * sn) : s; });
      var lo = mu.map(function (m, j) { return m - 1.96 * sd[j]; }), hi = mu.map(function (m, j) { return m + 1.96 * sd[j]; });
      var g2 = clipRect(svg, L, T, R - L, B - T);
      band(g2, g, lo, hi, sx, sy, { fill: 'var(--cw-accent)', 'fill-opacity': 0.18 });
      M.forEach(function (m) { polyline(g2, g.map(sx), m.map(sy), { stroke: 'var(--cw-accent)', 'stroke-opacity': 0.45, 'stroke-width': 1 }); });
      polyline(g2, g.map(sx), g.map(function (x) { return sy(TRUTHS.sin(x)); }), { stroke: 'currentColor', 'stroke-opacity': 0.4, 'stroke-width': 2.5 });
      d.x.forEach(function (x, i) { el('circle', { cx: sx(x), cy: sy(d.y[i]), r: 1.8, fill: 'currentColor', 'fill-opacity': 0.7 }, svg); });
      var cin = [], cout = [], ein = [], eout = [], sin_ = [], sout = [];
      g.forEach(function (x, j) {
        var c = pcov(lo[j], hi[j], TRUTHS.sin(x), d.noise), e = Math.abs(mu[j] - TRUTHS.sin(x));
        if (x <= 1) { cin.push(c); ein.push(e); sin_.push(sp[j]); } else { cout.push(c); eout.push(e); sout.push(sp[j]); }
      });
      readout.textContent = k + ' members. Inside the data: spread ' + mean(sin_).toFixed(3) + ', error of the mean ' +
        mean(ein).toFixed(3) + ', 95% coverage ' + pct(mean(cin)) + '. Beyond x = 1: spread ' + mean(sout).toFixed(2) +
        ', error ' + mean(eout).toFixed(2) + ', coverage ' + pct(mean(cout)) + '. Noise estimate ' + sn.toFixed(3) + '.';
    }
    draw();
  };

  /* One scale factor on an ensemble's spread, on the concrete strength dataset. */
  WIDGETS['sigma-scale'] = function (root, data) {
    var D = data.scale, split = 0, s = 1, LV = D.levels;
    var W = 720, H = 300;
    html('div', { class: 'cw-title' }, root, 'Rescaling an ensemble\'s spread by one number');
    var svg = svgRoot(root, W, H, 'Negative log likelihood against the scale factor, and a reliability diagram');
    var c1 = html('div', { class: 'cw-controls' }, root);
    var c2 = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Concrete strength dataset. Five of Lecture 9\'s networks trained on the fitting mixes; the interval is the mean ' +
      '± z × s × spread. The factor s that minimizes the negative log likelihood on the calibration mixes is the root mean ' +
      'square of their z-scores. Grouped split: test mixes like the training mixes. Extrapolation split: the 20% of ' +
      'mixes with the lowest water/cement ratio held out, the strongest concrete.');
    toggleGroup(c1, ['grouped split', 'extrapolation split'], 0, function (v) { split = v; draw(); });
    var ssl = slider(c1, 'scale s', 0.5, 8, 0.05, s, function (v) { return v.toFixed(2); }, function (v) { s = v; draw(); });
    var fitB = html('button', { type: 'button' }, c2, 'Fit s on the calibration mixes');
    var oneB = html('button', { type: 'button' }, c2, 's = 1 (raw spread)');
    fitB.onclick = function () { s = D.splits[split].s; ssl.set(s); draw(); };
    oneB.onclick = function () { s = 1; ssl.set(1); draw(); };
    function nll(set, k) {
      var t = 0;
      set.y.forEach(function (y, i) { var sd = k * set.sd[i], z = (y - set.mu[i]) / sd; t += 0.5 * Math.log(2 * Math.PI * sd * sd) + 0.5 * z * z; });
      return t / set.y.length;
    }
    function cov(set, k, lv) {
      var z = NORM_Z[lv], hit = 0;
      set.y.forEach(function (y, i) { if (Math.abs(y - set.mu[i]) <= z * k * set.sd[i]) hit++; });
      return hit / set.y.length;
    }
    function draw() {
      clear(svg);
      var sp = D.splits[split], ks = linspace(0.5, 8, 76);
      var nc = ks.map(function (k) { return nll(sp.cal, k); }), nt = ks.map(function (k) { return nll(sp.test, k); });
      var lo = Math.min.apply(null, nc.concat(nt)), hi = Math.min(Math.max.apply(null, nc.concat(nt)), lo + 12);
      var L = 46, R = 380, T = 22, B = 262;
      var sx = scale(0.5, 8, L, R), sy = scale(lo - 0.3, hi, B, T);
      frame(svg, L, T, R - L, B - T);
      text(svg, (L + R) / 2, 14, 'negative log likelihood per mix', { 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 600 });
      [1, 2, 4, 6, 8].forEach(function (v) { text(svg, sx(v), B + 16, String(v), { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.7 }); });
      text(svg, (L + R) / 2, B + 32, 'scale factor s', { 'text-anchor': 'middle', 'font-size': 11, opacity: 0.8 });
      var g = clipRect(svg, L, T, R - L, B - T);
      polyline(g, ks.map(sx), nc.map(sy), { stroke: 'var(--cw-accent)', 'stroke-width': 2 });
      polyline(g, ks.map(sx), nt.map(sy), { stroke: 'var(--cw-accent2)', 'stroke-width': 2, 'stroke-dasharray': '5 3' });
      el('line', { x1: sx(sp.s), x2: sx(sp.s), y1: T, y2: B, stroke: 'var(--cw-accent)', 'stroke-opacity': 0.5, 'stroke-dasharray': '2 3' }, svg);
      el('line', { x1: sx(s), x2: sx(s), y1: T, y2: B, stroke: 'currentColor', 'stroke-width': 1.5 }, svg);
      text(svg, R - 6, T + 16, 'calibration mixes', { 'text-anchor': 'end', 'font-size': 11, style: 'fill:var(--cw-accent)' });
      text(svg, R - 6, T + 32, 'test mixes', { 'text-anchor': 'end', 'font-size': 11, style: 'fill:var(--cw-accent2)' });
      // Reliability diagram.
      var rx = scale(0, 1, 470, 690), ry = scale(0, 1, 262, 42);
      el('rect', { x: 470, y: 42, width: 220, height: 220, fill: 'none', stroke: 'currentColor', 'stroke-opacity': 0.25 }, svg);
      el('line', { x1: rx(0), y1: ry(0), x2: rx(1), y2: ry(1), stroke: 'currentColor', 'stroke-dasharray': '4 3', 'stroke-opacity': 0.6 }, svg);
      text(svg, 580, 30, 'reliability diagram at this s', { 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 600 });
      text(svg, 580, 292, 'nominal coverage', { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.8 });
      text(svg, 446, 152, 'observed', { 'text-anchor': 'end', 'font-size': 10, opacity: 0.8 });
      [0, 0.5, 1].forEach(function (v) {
        text(svg, rx(v), 276, String(v), { 'text-anchor': 'middle', 'font-size': 10, opacity: 0.7 });
        text(svg, 464, ry(v) + 4, String(v), { 'text-anchor': 'end', 'font-size': 10, opacity: 0.7 });
      });
      [['cal', 'var(--cw-accent)'], ['test', 'var(--cw-accent2)']].forEach(function (p) {
        var c = LV.map(function (lv) { return cov(sp[p[0]], s, lv); });
        polyline(svg, LV.map(rx), c.map(ry), { stroke: p[1], 'stroke-width': 2 });
        LV.forEach(function (v, i) { el('circle', { cx: rx(v), cy: ry(c[i]), r: 2.8, fill: p[1] }, svg); });
      });
      var w = 2 * 1.6449 * s * mean(sp.test.sd);
      readout.textContent = sp.label + ', s = ' + s.toFixed(2) + ' (fitted: ' + sp.s.toFixed(2) + '). 90% intervals cover ' +
        pct(cov(sp.cal, s, 0.9)) + ' of the calibration mixes and ' + pct(cov(sp.test, s, 0.9)) +
        ' of the test mixes, mean width ' + w.toFixed(1) + ' MPa. Test NLL ' + nll(sp.test, s).toFixed(2) + '.';
    }
    draw();
  };

  /* Split conformal on a problem whose noise grows with x. */
  WIDGETS.conformal = function (root, data) {
    var d = data.conf, alpha = 0.1, n = 200, norm = false, a0 = 0;
    var W = 720, H = 300, L = 40, R = 520, T = 12, B = 268;
    html('div', { class: 'cw-title' }, root, 'Split conformal: the width comes from the calibration residuals');
    var svg = svgRoot(root, W, H, 'A conformal band on a toy problem, and the histogram of calibration scores');
    var c1 = html('div', { class: 'cw-controls' }, root);
    var c2 = html('div', { class: 'cw-controls' }, root);
    var readout = html('div', { class: 'cw-readout', 'aria-live': 'polite' }, root);
    html('div', { class: 'cw-note' }, root,
      'Truth sin(2πx); noise sd 0.05 + 0.25x. The model (mean of five tanh networks) and ρ(x), a small network fitted to ' +
      'its absolute residuals, were trained on 300 other points in [0, 1]. Calibration points are drawn from [0, 1]. ' +
      'Score: |y − ŷ| for the constant band, |y − ŷ| / ρ(x) for the normalized one. q is the ⌈(n+1)(1−α)⌉-th smallest ' +
      'score. Coverage over the shaded test window is exact against the truth.');
    slider(c1, 'α', 0.05, 0.5, 0.01, alpha, function (v) { return v.toFixed(2); }, function (v) { alpha = v; draw(); });
    slider(c1, 'calibration points', 5, 500, 1, n, function (v) { return String(v); }, function (v) { n = v; draw(); });
    toggleGroup(c2, ['score |y − ŷ|', 'score |y − ŷ| / ρ(x)'], 0, function (v) { norm = v === 1; draw(); });
    slider(c2, 'test window starts at', 0, 1, 0.05, a0, function (v) { return v.toFixed(2); }, function (v) { a0 = v; draw(); });
    function draw() {
      clear(svg);
      var sx = scale(0, 1.5, L, R), sy = scale(-3, 2.5, B, T), g = d.grid;
      axes1d(svg, sx, sy, [0, 0.5, 1, 1.5], [-3, -2, -1, 0, 1, 2], L, R, T, B);
      el('rect', { x: sx(a0), y: T, width: sx(a0 + 0.5) - sx(a0), height: B - T, fill: 'var(--cw-accent2)', 'fill-opacity': 0.08 }, svg);
      text(svg, sx(a0 + 0.25), T + 12, 'test window', { 'text-anchor': 'middle', 'font-size': 11, style: 'fill:var(--cw-accent2)' });
      var sc = [];
      for (var i = 0; i < n; i++) { var r = Math.abs(d.cal.y[i] - d.cal.mu[i]); sc.push(norm ? r / d.cal.rho[i] : r); }
      var sorted = sc.slice().sort(function (p, q) { return p - q; }), k = Math.ceil((n + 1) * (1 - alpha));
      var q = k > n ? Infinity : sorted[k - 1];
      var hw = g.map(function (_, j) { return norm ? q * d.rho[j] : q; });
      var lo = d.mu.map(function (m, j) { return m - hw[j]; }), hi = d.mu.map(function (m, j) { return m + hw[j]; });
      var gg = clipRect(svg, L, T, R - L, B - T);
      if (isFinite(q)) band(gg, g, lo, hi, sx, sy, { fill: 'var(--cw-accent)', 'fill-opacity': 0.18 });
      polyline(gg, g.map(sx), d.truth.map(sy), { stroke: 'currentColor', 'stroke-opacity': 0.4, 'stroke-width': 2.5 });
      polyline(gg, g.map(sx), d.mu.map(sy), { stroke: 'var(--cw-accent)', 'stroke-width': 2 });
      for (i = 0; i < n; i++) el('circle', { cx: sx(d.cal.x[i]), cy: sy(d.cal.y[i]), r: 1.7, fill: 'currentColor', 'fill-opacity': 0.6 }, svg);
      // Histogram of scores.
      var hx = 560, hw_ = 150, hy = 40, hh = 200, top = Math.max(sorted[n - 1], isFinite(q) ? q : 0) * 1.05;
      var bins = 20, cnt = [];
      for (i = 0; i < bins; i++) cnt.push(0);
      sc.forEach(function (v) { cnt[Math.min(bins - 1, Math.floor(v / top * bins))]++; });
      var cmax = Math.max.apply(null, cnt);
      text(svg, hx + hw_ / 2, 28, 'calibration scores', { 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 600 });
      cnt.forEach(function (c, b) {
        el('rect', { x: hx + b * hw_ / bins, y: hy + hh - c / cmax * hh, width: hw_ / bins - 1, height: c / cmax * hh, fill: 'currentColor', 'fill-opacity': 0.35 }, svg);
      });
      if (isFinite(q)) {
        el('line', { x1: hx + q / top * hw_, x2: hx + q / top * hw_, y1: hy - 4, y2: hy + hh, stroke: RED, 'stroke-width': 2 }, svg);
        text(svg, hx + q / top * hw_, hy + hh + 14, 'q = ' + q.toFixed(3), { 'text-anchor': 'middle', 'font-size': 11, style: 'fill:' + RED });
      }
      var cw = [], th = [[], [], []];
      g.forEach(function (x, j) {
        var c = isFinite(q) ? pcov(lo[j], hi[j], d.truth[j], d.noise[j]) : 1;
        if (x >= a0 - 1e-9 && x <= a0 + 0.5 + 1e-9) cw.push(c);
        if (x <= 1) th[Math.min(2, Math.floor(x * 3))].push(c);
      });
      if (!isFinite(q)) {
        readout.textContent = 'With ' + n + ' calibration points and α = ' + alpha.toFixed(2) + ', ⌈(n+1)(1−α)⌉ = ' + k +
          ' exceeds n: the interval is infinite. You need n ≥ ' + Math.ceil(1 / alpha - 1) + '.';
        return;
      }
      readout.textContent = 'Target ' + pct(1 - alpha) + '. Test window [' + a0.toFixed(2) + ', ' + (a0 + 0.5).toFixed(2) +
        ']: ' + pct(mean(cw)) + ' covered. Inside [0, 1] by third: ' + th.map(function (t) { return pct(mean(t)); }).join(', ') + '.';
    }
    draw();
  };

  // ------------------------------------------------------------------ boot

  function boot() {
    if (!document.getElementById('cw-style')) {
      var st = document.createElement('style');
      st.id = 'cw-style';
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    var nodes = document.querySelectorAll('.cw[data-widget]');
    Array.prototype.forEach.call(nodes, function (node) {
      if (node.getAttribute('data-ready')) return;
      node.setAttribute('data-ready', '1');
      var fn = WIDGETS[node.getAttribute('data-widget')];
      var src = node.getAttribute('data-source');
      var data = src ? (window.COURSE_WIDGET_DATA || {})[src] : {};
      if (!fn || !data) {
        html('div', { class: 'cw-missing' }, node,
          'Interactive figure "' + node.getAttribute('data-widget') + '" could not load' +
          (fn ? ': its data file (' + src + ') is missing.' : '.'));
        return;
      }
      // A deck puts a static snapshot inside the div for viewers that do not run
      // scripts (the VS Code Marp preview, a PDF export); the live figure replaces it.
      clear(node);
      try { fn(node, data); } catch (err) {
        html('div', { class: 'cw-missing' }, node, 'Interactive figure failed: ' + err.message);
      }
    });
  }

  // The data files are separate scripts whose load order relative to this one
  // is not guaranteed in either the book or a deck, so wait for the whole page.
  if (document.readyState === 'complete') boot();
  else window.addEventListener('load', boot);
})();
