/* The floating "Ask" button on every page of the notes.
 *
 * It opens a side panel holding the L18 capstone, chat/rag-chat.js: retrieval over the released
 * notes and slides, and optional answers from a model run in the tab through WebLLM. This file
 * is only the button and the panel. The retrieval, the abstention gate and the model all live in
 * rag-chat.js, so the site and the L18 deck run one pipeline, not two that can disagree.
 *
 * Jupyter Book 1 loads every .js file under _static/ on every page, so this file must cost
 * nothing until it is used: it draws a button and fetches nothing. The first click injects
 *
 *     <div class="rag-chat compact" data-index="<site>/chat/rag-index.json">
 *     <script src="<site>/chat/rag-chat.js">
 *
 * and rag-chat.js mounts on load. From then on the downloads are rag-chat.js's (chat/README.md,
 * "The network exception"): the index, MiniSearch, transformers.js and a 23 MB embedding model on
 * open, and WebLLM with a ~1.6 GB model only when the reader presses its load button.
 *
 * CI publishes chat/rag-chat.js and the index at /chat/ ("Build the course-notes chat index" in
 * book.yml). A local `jupyter-book build` has neither, so the panel opens and says so.
 *
 * Paths come from this script's own src, <site>/_static/ask.js, so nothing here hardcodes
 * /f26-06763/ and the button works at any nesting depth.
 */
(function () {
  'use strict';

  var SELF = document.currentScript;
  if (!SELF) return;
  var SITE = new URL('../', SELF.src);

  var CSS = [
    '.ask-toggle{position:fixed;right:1.25rem;bottom:1.25rem;z-index:1045;display:inline-flex;',
    'align-items:center;gap:.45em;background:#c41230;color:#fff;border:1px solid #c41230;',
    'border-radius:999px;font:inherit;font-size:.95rem;font-weight:600;line-height:1.2;',
    'padding:.6em 1.15em;cursor:pointer;',
    'box-shadow:0 3px 10px rgba(0,0,0,.25),0 8px 28px rgba(0,0,0,.18);',
    'transition:transform .15s ease,box-shadow .15s ease,background .15s ease}',
    '.ask-toggle:hover{background:#9e0e27;border-color:#9e0e27;transform:translateY(-1px)}',
    '.ask-toggle:focus-visible{outline:2px solid var(--pst-color-text-base,#222);outline-offset:2px}',
    '.ask-toggle svg{display:block;width:1.15em;height:1.15em;fill:currentColor}',
    'body.ask-open .ask-toggle{display:none}',
    '@media (max-width:700px){.ask-toggle{padding:0;width:2.9rem;height:2.9rem;',
    'justify-content:center}.ask-toggle-label{display:none}}',
    '@media (prefers-reduced-motion:reduce){.ask-toggle{transition:none}',
    '.ask-toggle:hover{transform:none}}',

    '.ask-panel{position:fixed;top:0;right:0;bottom:0;z-index:1050;width:min(34rem,100vw);',
    'display:flex;flex-direction:column;gap:.5em;padding:.8em 1em;overflow-y:auto;',
    'background:var(--pst-color-background,#fff);color:var(--pst-color-text-base,#222);',
    'border-left:1px solid var(--pst-color-border,rgba(128,128,128,.35));',
    'box-shadow:-6px 0 24px rgba(0,0,0,.18)}',
    '.ask-panel[hidden]{display:none}',
    '.ask-head{display:flex;align-items:center;justify-content:space-between}',
    '.ask-head h2{margin:0;font-size:1.15rem}',
    '.ask-close{background:none;border:0;font-size:1.6rem;line-height:1;cursor:pointer;',
    'color:inherit;padding:0 .2em}',
    '.ask-foot{font-size:.8rem;opacity:.75;margin-top:auto}',
    '.ask-error{font-size:.9rem}',

    /* rag-chat.js is laid out for a slide, 1280 px wide. In a side panel, stack the answer above
       the passages and let both run to their full length, since the panel itself scrolls. */
    '.ask-panel .rag-out{grid-template-columns:1fr}',
    '.ask-panel .rag-out>:last-child{order:-1}',
    '.ask-panel .rag.compact .rag-hits,.ask-panel .rag.compact .rag-answer{max-height:none}',
    '.ask-panel .rag-stage{flex:1 1 auto}',
    /* On a phone the eight-stage strip wraps to three rows of broken words before the question
       box; the timings it shows are for the lecture, not for a reader looking something up. */
    '@media (max-width:700px){.ask-panel .rag-strip{display:none}}',
    '.ask-panel .rag input[type=text]{min-width:0}',
    /* rag-chat.js paints its controls white, which is unreadable under the theme's dark mode. */
    '.ask-panel .rag-stage,.ask-panel .rag button:not(.primary),.ask-panel .rag input[type=text]',
    '{background:var(--pst-color-surface,#fff);color:inherit}'
  ].join('');

  // A speech bubble, inline so it needs no icon font and no second request.
  var ICON =
    '<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">' +
    '<path d="M8 1.5c-3.9 0-7 2.4-7 5.4 0 1.7 1 3.2 2.6 4.2-.1.8-.5 1.8-1.3 2.6' +
    '-.2.2 0 .5.2.5 1.6-.1 3-.7 4-1.5.5.1 1 .1 1.5.1 3.9 0 7-2.4 7-5.4S11.9 1.5 8 1.5z"/></svg>';

  var ui = {};

  function el(tag, cls, parent, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  }

  function buildPanel() {
    var panel = el('aside', 'ask-panel', document.body);
    panel.hidden = true;
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Ask the course notes');

    var head = el('div', 'ask-head', panel);
    el('h2', null, head, 'Ask the course notes');
    var close = el('button', 'ask-close', head, '×');
    close.type = 'button';
    close.setAttribute('aria-label', 'Close');
    close.addEventListener('click', closePanel);

    ui.body = el('div', null, panel);

    el('p', 'ask-foot', panel,
      'Searches the released lecture notes and slides, and runs entirely in your browser: ' +
      'nothing you type is sent anywhere. Opening this panel downloads a 23 MB search model. ' +
      'Written answers need WebGPU and a model of about 1.6 GB, fetched only when you press ' +
      'its load button. A small model can misread good passages, so check its answer against ' +
      'the passages it cites.');

    ui.panel = panel;
  }

  // Mounted on first open, not at page load: rag-chat.js starts downloading the index and the
  // embedding model the moment it finds a .rag-chat element.
  function mountChat() {
    if (ui.mounted) return;
    ui.mounted = true;
    var chat = el('div', 'rag-chat compact', ui.body);
    chat.dataset.index = new URL('chat/rag-index.json', SITE).href;
    var s = document.createElement('script');
    s.src = new URL('chat/rag-chat.js', SITE).href;
    s.onerror = function () {
      chat.remove();
      el('p', 'ask-error', ui.body,
        'The assistant is not part of this build. CI publishes it at /chat/ when it deploys ' +
        'the site; a local jupyter-book build does not.');
    };
    document.head.appendChild(s);
  }

  function openPanel() {
    ui.panel.hidden = false;
    document.body.classList.add('ask-open');
    mountChat();
    var input = ui.panel.querySelector('input[type=text]');
    (input || ui.panel.querySelector('.ask-close')).focus();
  }

  function closePanel() {
    ui.panel.hidden = true;
    document.body.classList.remove('ask-open');
    ui.toggle.focus();
  }

  function init() {
    // Book pages only. The theme's main column marks one; a page without it has no reader to ask.
    if (!document.querySelector('.bd-main') || document.querySelector('.ask-toggle')) return;
    el('style', null, document.head, CSS);
    buildPanel();

    var btn = el('button', 'ask-toggle', document.body);
    btn.type = 'button';
    btn.title = 'Ask a question about the course notes (runs in your browser)';
    btn.setAttribute('aria-label', 'Ask the course notes');
    el('span', null, btn).innerHTML = ICON;
    el('span', 'ask-toggle-label', btn, 'Ask');
    btn.addEventListener('click', function () {
      if (ui.panel.hidden) openPanel();
      else closePanel();
    });
    ui.toggle = btn;

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !ui.panel.hidden) closePanel();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
