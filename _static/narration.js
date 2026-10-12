// Narration for MARP decks: reads each slide's script aloud.
//
// A slide carries its script in a hidden block, written as prose:
//
//   <div class="narration">
//
//   What a presenter would say on this slide.
//
//   </div>
//
// The theme hides .narration, so the script never shows on the slide. This file adds a
// small 🔊 button to the corner of the deck. Pressing it reads the current slide's script,
// and from then on every slide starts its own script as soon as it opens. In presenter
// view the script is shown under the speaker notes instead of spoken, so the person
// giving the talk can read it.
//
// The voice is Kokoro-82M (Apache-2.0) through kokoro-js, the same voice as the pycse
// book's "Listen to this page". It runs in a Web Worker in this browser and nothing is
// sent anywhere. The model is downloaded once on first use (about 330 MB with WebGPU,
// about 90 MB without) and cached by the browser, so the button asks before downloading.
//
// A classic script rather than a module, so a deck opened from disk (file://) runs it.
(function () {
  'use strict';

  var KOKORO_URL = 'https://cdn.jsdelivr.net/npm/kokoro-js@1.2.1/dist/kokoro.web.js';
  var MODEL_ID = 'onnx-community/Kokoro-82M-v1.0-ONNX';
  var ENGINES = {
    // kokoro-js recommends fp32 on WebGPU; WASM runs one thread here, slower than real time
    gpu: { device: 'webgpu', dtype: 'fp32', size: '330 MB' },
    cpu: { device: 'wasm', dtype: 'q8', size: '90 MB' }
  };
  var VOICES = {
    af_heart: 'Heart (US)', af_bella: 'Bella (US)', am_michael: 'Michael (US)',
    am_fenrir: 'Fenrir (US)', bf_emma: 'Emma (UK)', bm_george: 'George (UK)', bm_fable: 'Fable (UK)'
  };
  var PREF_KEY = 'f26-06763:narration:v1';
  var MAX_CHUNK = 260; // characters; Kokoro truncates past about 510 phoneme tokens
  var KEEP = 60; // generated chunks kept in memory, about 20 slides of audio

  var view = new URLSearchParams(location.search).get('view') || '';
  if (view === 'next' || view === 'overview') return; // the presenter's preview frames

  // ---- text ---------------------------------------------------------------------------------
  function speakable(s) {
    return String(s)
      .replace(/\p{Extended_Pictographic}️?/gu, ' ')
      .replace(/[–—]/g, ', ')
      .replace(/\s+([,;.:!?])/g, '$1')
      .replace(/([,;])(?:\s*[,;])+/g, '$1')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // pieces short enough for one Kokoro call, cut at sentences, then clauses
  function chunkText(text) {
    var sentences = String(text).split(/(?<=[.!?])\s+(?=["'“(]?[A-Z0-9])/);
    var out = [];
    sentences.forEach(function (s) {
      s = s.trim();
      while (s.length > MAX_CHUNK) {
        var cut = -1;
        [/[;:]\s/g, /,\s/g, /\s/g].some(function (re) {
          var m;
          cut = -1;
          while ((m = re.exec(s)) && m.index < MAX_CHUNK) cut = m.index + 1;
          return cut > MAX_CHUNK / 3;
        });
        if (cut <= MAX_CHUNK / 3) cut = MAX_CHUNK;
        out.push(s.slice(0, cut).trim());
        s = s.slice(cut).trim();
      }
      if (s) out.push(s);
    });
    return out;
  }

  function scriptOf(slide) {
    var n = slide && slide.querySelector('.narration');
    if (!n) return [];
    var paras = n.querySelectorAll('p');
    var texts = paras.length ? [].map.call(paras, function (p) { return p.textContent; }) : [n.textContent];
    var chunks = [];
    texts.forEach(function (t) { chunkText(speakable(t)).forEach(function (c) { chunks.push(c); }); });
    return chunks;
  }

  // ---- the deck --------------------------------------------------------------------------------
  function slides() {
    var s = document.querySelectorAll('svg.bespoke-marp-slide');
    return s.length ? [].slice.call(s) : [].slice.call(document.querySelectorAll('svg[data-marpit-svg]'));
  }
  function activeIndex() {
    var all = slides();
    for (var i = 0; i < all.length; i++) if (all[i].classList.contains('bespoke-marp-active')) return i;
    var h = parseInt(location.hash.slice(1), 10);
    return isNaN(h) ? 0 : h - 1;
  }

  // ---- presenter view: show the script beside the speaker notes, say nothing -----------------------
  function presenterScripts() {
    var container = document.querySelector('.bespoke-marp-presenter-note-container');
    if (!container) return false;
    slides().forEach(function (svg, i) {
      var n = svg.querySelector('.narration');
      if (!n) return;
      var note = container.querySelector('.bespoke-marp-note[data-index="' + i + '"]');
      if (!note || note.querySelector('.narration-script')) return;
      var box = document.createElement('div');
      box.className = 'narration-script';
      box.innerHTML = '<div class="narration-label">Script</div>' + n.innerHTML;
      note.appendChild(box);
    });
    return true;
  }

  var CSS = [
    '.narration{display:none!important}',
    '.narration-script{margin-top:1em;padding-top:.6em;border-top:1px solid #666;color:#ddd}',
    '.narration-script p{margin:.5em 0}',
    '.narration-label{font-weight:700;color:#9ecbff;font-size:.85em;text-transform:uppercase;letter-spacing:.05em}',
    '#narr-bar{position:fixed;right:12px;top:12px;justify-content:flex-end;z-index:1000;display:flex;align-items:center;gap:6px;',
    ' padding:5px 8px;border-radius:10px;background:rgba(20,24,31,.82);color:#eee;font:13px/1.3 system-ui,sans-serif;',
    ' box-shadow:0 4px 14px rgba(0,0,0,.3);opacity:.45;transition:opacity .2s;max-width:calc(100vw - 24px);flex-wrap:wrap}',
    '#narr-bar:hover,#narr-bar:focus-within,#narr-bar.narr-ask{opacity:1}',
    '#narr-bar button,#narr-bar select{font:inherit;color:inherit;background:transparent;border:1px solid rgba(255,255,255,.35);',
    ' border-radius:6px;min-height:28px;padding:1px 8px;cursor:pointer}',
    '#narr-bar select option{color:initial}',
    '#narr-bar .narr-go{background:#c41230;border-color:#c41230}',
    '#narr-bar .narr-on{background:rgba(196,18,48,.6);border-color:#c41230}',
    '#narr-bar .narr-status{max-width:28rem;opacity:.9}',
    '#narr-bar [hidden]{display:none}',
    '#narr-cc{position:fixed;left:50%;transform:translateX(-50%);bottom:56px;z-index:999;max-width:min(80vw,900px);',
    ' padding:6px 12px;border-radius:6px;background:rgba(0,0,0,.75);color:#fff;font:20px/1.35 system-ui,sans-serif;text-align:center}',
    '#narr-cc[hidden]{display:none}',
    '@media print{#narr-bar,#narr-cc{display:none!important}}'
  ].join('');

  function readPrefs() {
    var p = { on: false, consent: false, voice: 'af_heart', speed: 1, captions: false };
    try { Object.assign(p, JSON.parse(localStorage.getItem(PREF_KEY) || '{}')); } catch (e) { /* storage blocked */ }
    if (!(p.voice in VOICES)) p.voice = 'af_heart';
    return p;
  }

  function boot() {
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    if (view === 'presenter' || document.body.getAttribute('data-bespoke-view') === 'presenter') {
      // bespoke builds the presenter panes after load; try until they are there
      var tries = 0;
      (function again() { if (!presenterScripts() && ++tries < 40) setTimeout(again, 250); })();
      return;
    }
    if (!slides().some(function (s) { return s.querySelector('.narration'); })) return;

    var prefs = readPrefs();
    var save = function () { try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); } catch (e) { /* blocked */ } };
    var gpuOK = 'gpu' in navigator
      ? navigator.gpu.requestAdapter().then(function (a) { return !!a; }, function () { return false; })
      : Promise.resolve(false);
    var engine = 'cpu';

    var bar = document.createElement('div');
    bar.id = 'narr-bar';
    bar.setAttribute('role', 'region');
    bar.setAttribute('aria-label', 'Narration');
    bar.innerHTML =
      '<button type="button" class="narr-toggle" aria-pressed="false" title="Narrate each slide">🔊 Narrate</button>' +
      '<button type="button" class="narr-play" hidden aria-label="Pause">⏸</button>' +
      '<button type="button" class="narr-replay" hidden aria-label="Replay this slide" title="Replay this slide">↺</button>' +
      '<select class="narr-speed" hidden aria-label="Speed">' + [0.9, 1, 1.1, 1.25, 1.5].map(function (s) {
        return '<option value="' + s + '"' + (s === prefs.speed ? ' selected' : '') + '>' + s + '×</option>';
      }).join('') + '</select>' +
      '<select class="narr-voice" hidden aria-label="Voice">' + Object.keys(VOICES).map(function (k) {
        return '<option value="' + k + '"' + (k === prefs.voice ? ' selected' : '') + '>' + VOICES[k] + '</option>';
      }).join('') + '</select>' +
      '<button type="button" class="narr-cc-btn" hidden aria-pressed="false" title="Captions">CC</button>' +
      '<button type="button" class="narr-go" hidden>Download the voice and narrate</button>' +
      '<span class="narr-status" role="status" aria-live="polite"></span>';
    document.body.appendChild(bar);
    var cc = document.createElement('div');
    cc.id = 'narr-cc';
    cc.hidden = true;
    document.body.appendChild(cc);

    var $ = function (s) { return bar.querySelector(s); };
    var status = function (s) { $('.narr-status').textContent = s; };
    // keys typed into the bar belong to the bar, not to the deck's navigation
    bar.addEventListener('keydown', function (e) { e.stopPropagation(); });

    var worker = null, loading = null, ready = false, nextId = 0;
    var pending = {}; // id -> {resolve, reject}
    var made = new Map(); // "slide|chunk|voice|speed" -> Promise<{audio, rate}>
    var ctx = null, source = null, session = 0, paused = false, current = -1;

    function startWorker() {
      if (loading) return loading;
      var eng = ENGINES[engine];
      var src = [
        'let tts = null; const queue = []; let busy = false;',
        'async function pump() {',
        '  if (busy) return; busy = true;',
        '  while (queue.length) {',
        '    const m = queue.shift();',
        '    try {',
        '      const a = await tts.generate(m.text, { voice: m.voice, speed: m.speed });',
        '      const audio = a.audio instanceof Float32Array ? a.audio : new Float32Array(a.audio);',
        '      self.postMessage({ type: "audio", id: m.id, audio, rate: a.sampling_rate }, [audio.buffer]);',
        '    } catch (e) { self.postMessage({ type: "error", id: m.id, message: String(e && e.message || e) }); }',
        '  }',
        '  busy = false;',
        '}',
        'self.onmessage = async (e) => {',
        '  const m = e.data;',
        '  if (m.type === "load") {',
        '    try {',
        '      const { KokoroTTS } = await import(m.lib);',
        '      tts = await KokoroTTS.from_pretrained(m.model, { dtype: m.dtype, device: m.device,',
        '        progress_callback: (p) => { if (p.status === "progress") self.postMessage({ type: "progress", file: p.file, loaded: p.loaded, total: p.total }); } });',
        '      self.postMessage({ type: "ready" });',
        '    } catch (e) { self.postMessage({ type: "error", message: String(e && e.message || e) }); }',
        '  } else if (m.type === "gen") { if (m.front) queue.unshift(m); else queue.push(m); pump(); }',
        '  else if (m.type === "drop") { for (let i = queue.length - 1; i >= 0; i--) if (m.ids.includes(queue[i].id)) queue.splice(i, 1); }',
        '};'
      ].join('\n');
      // a classic worker: Chrome refuses module workers from blob URLs on a file:// page, and
      // import() works in either
      worker = new Worker(URL.createObjectURL(new Blob([src], { type: 'text/javascript' })));
      var files = {};
      loading = new Promise(function (resolve, reject) {
        worker.onmessage = function (ev) {
          var m = ev.data;
          if (m.type === 'progress') {
            files[m.file] = m;
            var a = 0, b = 0;
            Object.keys(files).forEach(function (k) { a += files[k].loaded || 0; b += files[k].total || 0; });
            if (b) status('Downloading the voice… ' + Math.round(a / 1e6) + ' of ' + Math.round(b / 1e6) + ' MB');
          } else if (m.type === 'ready') { ready = true; resolve(); }
          else if (m.type === 'audio') { if (pending[m.id]) pending[m.id].resolve(m); delete pending[m.id]; }
          else if (m.type === 'error') {
            if (m.id != null) { if (pending[m.id]) pending[m.id].reject(new Error(m.message)); delete pending[m.id]; }
            else reject(new Error(m.message));
          }
        };
        worker.onerror = function (e) { reject(new Error(e.message || 'the voice could not be loaded')); };
      });
      status('Loading the voice…');
      worker.postMessage({ type: 'load', lib: KOKORO_URL, model: MODEL_ID, device: eng.device, dtype: eng.dtype });
      loading.catch(function (e) {
        status('The voice could not be loaded (' + e.message + ').');
        if (worker) worker.terminate();
        worker = null; loading = null; ready = false;
      });
      return loading;
    }

    var queued = []; // [key, id] still waiting in the worker
    function generate(slide, i, text, front) {
      var key = slide + '|' + i + '|' + prefs.voice + '|' + prefs.speed;
      if (!made.has(key)) {
        var id = nextId++;
        var p = new Promise(function (resolve, reject) { pending[id] = { resolve: resolve, reject: reject }; });
        p.catch(function () { made.delete(key); });
        worker.postMessage({ type: 'gen', id: id, text: text, voice: prefs.voice, speed: prefs.speed, front: !!front });
        made.set(key, p);
        queued.push([key, id]);
        if (made.size > KEEP) made.delete(made.keys().next().value);
      }
      return made.get(key);
    }
    // forget queued work for slides other than these; what is already generated stays
    function dropExcept(keep) {
      var drop = [];
      queued = queued.filter(function (q) {
        if (!pending[q[1]]) return false; // finished
        if (keep.indexOf(+q[0].split('|')[0]) >= 0) return true;
        drop.push(q[1]);
        pending[q[1]].reject(new Error('cancelled'));
        delete pending[q[1]];
        made.delete(q[0]);
        return false;
      });
      if (drop.length) worker.postMessage({ type: 'drop', ids: drop });
    }

    function halt() {
      session++;
      if (source) { source.onended = null; try { source.stop(); } catch (e) { /* not started */ } source = null; }
      cc.hidden = true;
    }

    function play(index) {
      halt();
      var my = session;
      current = index;
      var all = slides();
      var chunks = scriptOf(all[index]);
      var after = all[index + 1] ? scriptOf(all[index + 1]) : [];
      dropExcept([index, index + 1]);
      if (!chunks.length) { status('Slide ' + (index + 1) + ': no script.'); syncButtons(); return; }
      if (paused) setPaused(false);
      // this slide first, at the front of the queue, then the start of the next one
      chunks.forEach(function (t, i) { generate(index, i, t, i < 2); });
      after.slice(0, 2).forEach(function (t, i) { generate(index + 1, i, t); });
      (function step(i) {
        if (my !== session) return;
        if (i >= chunks.length) { status('Slide ' + (index + 1) + ': done. ↺ replays it.'); cc.hidden = true; return; }
        var t0 = performance.now();
        generate(index, i, chunks[i]).then(function (a) {
          if (my !== session) return;
          if (performance.now() - t0 > 400 && engine === 'cpu') status('Slide ' + (index + 1) + ' (on the CPU, so it may pause)');
          else status('Slide ' + (index + 1));
          if (prefs.captions) { cc.textContent = chunks[i]; cc.hidden = false; }
          var buf = ctx.createBuffer(1, a.audio.length, a.rate);
          buf.copyToChannel(a.audio, 0);
          source = ctx.createBufferSource();
          source.buffer = buf;
          source.connect(ctx.destination);
          source.onended = function () { source = null; step(i + 1); };
          source.start();
        }, function (e) {
          if (my !== session) return;
          if (e.message !== 'cancelled') status('Skipped a sentence the voice could not read (' + e.message + ').');
          step(i + 1);
        });
      })(0);
    }

    function setPaused(p) {
      paused = p;
      if (ctx) { if (p) ctx.suspend(); else ctx.resume(); }
      $('.narr-play').textContent = p ? '▶' : '⏸';
      $('.narr-play').setAttribute('aria-label', p ? 'Resume' : 'Pause');
      if (p) status('Paused.');
    }

    function syncButtons() {
      var t = $('.narr-toggle');
      t.textContent = prefs.on ? '🔊 On' : '🔊 Narrate';
      t.title = prefs.on ? 'Turn narration off' : 'Narrate each slide';
      t.className = 'narr-toggle' + (prefs.on ? ' narr-on' : '');
      t.setAttribute('aria-pressed', String(prefs.on));
      ['.narr-play', '.narr-replay', '.narr-speed', '.narr-voice', '.narr-cc-btn'].forEach(function (s) { $(s).hidden = !prefs.on; });
      $('.narr-cc-btn').setAttribute('aria-pressed', String(prefs.captions));
      $('.narr-cc-btn').style.background = prefs.captions ? 'rgba(255,255,255,.2)' : '';
    }

    // needs a user gesture: the browser will not start audio before one
    function unlock() {
      if (!ctx) ctx = new AudioContext();
      if (ctx.state === 'suspended' && !paused) return ctx.resume();
      return Promise.resolve();
    }

    function turnOn() {
      bar.classList.remove('narr-ask');
      $('.narr-go').hidden = true;
      prefs.on = true; save(); syncButtons();
      unlock();
      return gpuOK.then(function (ok) {
        engine = ok ? 'gpu' : 'cpu';
        return startWorker();
      }).then(function () {
        prefs.consent = true; save();
        if (prefs.on) play(activeIndex());
      }, function () { prefs.on = false; save(); syncButtons(); });
    }

    function turnOff() {
      halt();
      prefs.on = false; save();
      if (paused) setPaused(false);
      status('');
      syncButtons();
    }

    function ask() {
      gpuOK.then(function (ok) {
        engine = ok ? 'gpu' : 'cpu';
        bar.classList.add('narr-ask');
        $('.narr-go').hidden = false;
        status('Narration uses the open Kokoro voice, which runs in your browser. It is downloaded once (about ' +
          ENGINES[engine].size + ') and nothing is sent anywhere.' +
          (engine === 'cpu' ? ' This browser has no WebGPU, so the voice runs on the processor and may pause between sentences.' : ''));
        $('.narr-go').focus();
      });
    }

    $('.narr-toggle').onclick = function () {
      if (prefs.on) return turnOff();
      if (prefs.consent || ready) turnOn(); else ask();
    };
    $('.narr-go').onclick = turnOn;
    $('.narr-play').onclick = function () { if (prefs.on && ready) setPaused(!paused); };
    $('.narr-replay').onclick = function () { if (prefs.on && ready) { unlock(); play(activeIndex()); } };
    $('.narr-speed').onchange = function (e) { prefs.speed = Number(e.target.value); save(); e.target.blur(); if (prefs.on && ready) play(activeIndex()); };
    $('.narr-voice').onchange = function (e) { prefs.voice = e.target.value; save(); e.target.blur(); if (prefs.on && ready) play(activeIndex()); };
    $('.narr-cc-btn').onclick = function () { prefs.captions = !prefs.captions; save(); syncButtons(); if (!prefs.captions) cc.hidden = true; };

    // a new slide starts its own script
    var seen = activeIndex();
    function onMove() {
      var i = activeIndex();
      if (i === seen) return;
      seen = i;
      if (prefs.on && ready) { unlock(); if (paused) setPaused(false); play(i); }
    }
    new MutationObserver(onMove).observe(document.body, { attributes: true, subtree: true, attributeFilter: ['class'] });
    window.addEventListener('hashchange', onMove);

    syncButtons();
    if (prefs.on && prefs.consent) {
      // narration was on last time: load the voice now, start at the first key or click
      gpuOK.then(function (ok) { engine = ok ? 'gpu' : 'cpu'; return startWorker(); }).then(function () {
        status('Narration is on. Press a key or click to start.');
        var go = function () {
          window.removeEventListener('keydown', go, true);
          window.removeEventListener('pointerdown', go, true);
          unlock().then(function () { if (prefs.on && current < 0) play(activeIndex()); });
        };
        window.addEventListener('keydown', go, true);
        window.addEventListener('pointerdown', go, true);
      }, function () { /* status already says why */ });
    }
    window.__narration = { play: function (i) { play(i == null ? activeIndex() : i); }, scriptOf: function (i) { return scriptOf(slides()[i]); } };
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
