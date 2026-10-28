---
marp: true
theme: course
paginate: true
header: "06-763 / L17, held back"
footer: "Systems and Toolchains for AI Engineers"
---

<style>
/* a figure alone in its paragraph is centered, and so is every table */
section p:has(> img:only-child) { text-align: center; }
section table { margin-left: auto; margin-right: auto; }

/* the first bullet is static (-) and the rest animate (*): keep the two lists as one */
section ul:has(+ ul) { margin-bottom: 0; }
section ul + ul { margin-top: 0; }

.cols { display: grid; gap: 1.1em; align-items: center; }
.cols-even { grid-template-columns: 1fr 1fr; }
.cols-lc { grid-template-columns: 1.25fr 1fr; }
.cols-cl { grid-template-columns: 1fr 1.25fr; }
.cols-top { align-items: start; }
.cols-side { grid-template-columns: 1.7fr 1fr; }
.card .big { font-size: 1.6em; font-weight: 700; line-height: 1.15; margin: 0.15em 0 0.3em; }
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 0.3em; }
.cards.four { grid-template-columns: repeat(4, 1fr); }
.cards.two { grid-template-columns: repeat(2, 1fr); }
.cards.one { grid-template-columns: 1fr; gap: 10px; }
.card { background: #f7f7f7; border-top: 5px solid #c41230; border-radius: 6px; padding: 8px 12px; font-size: 0.64em; }
.card:nth-child(2) { border-top-color: #1f5c99; }
.card:nth-child(3) { border-top-color: #b07d12; }
.card:nth-child(4) { border-top-color: #2e7d32; }
.card h4 { margin: 2px 0 5px; font-size: 1.2em; }
.card p { margin: 0.25em 0; }
.card img { width: 100%; display: block; margin: 0.2em 0; }
.card .MathJax { margin: 0.2em 0 !important; }
.cards.tight2 { grid-template-columns: 1fr 1fr; gap: 10px; }
.cards.tight2 .card { font-size: 0.58em; padding: 6px 10px; }

/* a box that says how to read a figure, and a closing line under it */
.readbox { background: #f7f7f7; border-left: 5px solid #1f5c99; border-radius: 0 6px 6px 0;
  padding: 0.35em 0.8em; font-size: 0.7em; line-height: 1.35; }
.readbox ul { margin: 0; padding-left: 1.1em; }
.readbox li { margin: 0.2em 0; }
.readbox p { margin: 0.2em 0; }
.readbox + .readbox { margin-top: 0.45em; }
.readbox.bgreen { border-left-color: #2e7d32; }
.readbox.bred { border-left-color: #c41230; }
.readbox.bgold { border-left-color: #b07d12; }
section p.takeaway { text-align: center; font-weight: 700; font-size: 0.78em; margin: 0.5em 0 0; }
.example { background: #fff8e6; border-left: 5px solid #b07d12; border-radius: 0 6px 6px 0; padding: 0.3em 0.8em;
  font-size: 0.66em; line-height: 1.4; margin-top: 0.5em; }
.example p { margin: 0.15em 0; }
.small { font-size: 0.72em; }
.smaller { font-size: 0.62em; }
.source { font-size: 0.6em; color: #5c5c5c; }
.center { text-align: center; }
.red { color: #c41230; }
.blue { color: #1f5c99; }
.gold { color: #b07d12; }
.green { color: #2e7d32; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }

/* big numbers */
.kpis { display: grid; gap: 16px; margin-top: 0.3em; }
.kpi { background: #f7f7f7; border-radius: 8px; padding: 8px 12px; text-align: center; border-top: 6px solid #8a8a8a; }
.kpi .v { font-size: 1.35em; font-weight: 700; line-height: 1.15; }
.kpi .l { font-size: 0.6em; color: #3c3c3c; }

/* the roadmap, a flow of boxes */
.road { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px 16px; margin-top: 0.1em; }
.road > div { background: #f7f7f7; border-radius: 10px; padding: 7px 10px; font-size: 0.6em; border-top: 6px solid #1f5c99;
  display: grid; grid-template-columns: 150px 1fr; gap: 10px; align-items: center; }
.road > div:nth-child(2) { border-top-color: #2e7d32; }
.road > div:nth-child(3) { border-top-color: #c41230; }
.road > div:nth-child(4) { border-top-color: #b07d12; }
.road > div:nth-child(5) { border-top-color: #7a3db8; }
.road > div:nth-child(6) { border-top-color: #148c96; }
.road img { width: 150px; height: 110px; object-fit: contain; background: #fff; border-radius: 6px; display: block; margin: 0; }
.road .n { font-size: 1.4em; font-weight: 700; color: #5c5c5c; }
.flow { display: flex; align-items: center; justify-content: center; gap: 10px; margin: 0.4em 0; font-size: 0.72em; }
.flow .box { background: #f7f7f7; border-radius: 8px; padding: 8px 14px; border: 2px solid #c8c8c8; text-align: center; }
.flow .box.dark { background: #2b2b2b; color: #fff; border-color: #2b2b2b; }
.flow .arr { font-size: 1.5em; color: #5c5c5c; }
.flow.small { font-size: 0.6em; }

/* equations whose terms light up with their card */
.eqrow { display: flex; justify-content: center; align-items: center; gap: 6px; margin: 0.1em 0 0.25em; flex-wrap: nowrap; }
.eqrow.big { font-size: 1.1em; }
.eqrow .term { border-radius: 8px; padding: 0 6px; border: 3px solid transparent; transition: background 0.3s, border-color 0.3s; }
.eqrow p { margin: 0; }

/* token chips */
.chips { display: flex; flex-wrap: wrap; justify-content: center; gap: 4px; margin: 0.5em 0 0.3em; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.74em; }
.chips p { display: contents; }
.chips span { padding: 4px 8px; border-radius: 6px; white-space: pre; }
.chips .ctx { background: #ececec; }
.chips .g { background: rgba(196, 18, 48, 0.12); border: 2px solid rgba(196, 18, 48, 0.55); }
.tk { display: inline-block; padding: 3px 7px; border-radius: 5px; white-space: pre; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.idk { display: inline-block; padding: 3px 7px; border-radius: 5px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: #2b2b2b; color: #fff; }

/* text, tokens, ids: one table, so each id sits under its token */
table.pipe { border-collapse: separate; border-spacing: 8px 10px; font-size: 0.8em; margin: 0.4em auto 0; }
table.pipe tr, table.toy tr { background: transparent !important; }
table.pipe td { border: none; padding: 0; text-align: center; }
table.pipe td.lab { text-align: right; color: #5c5c5c; font-size: 0.8em; padding-right: 10px; }
table.pipe td.txt { text-align: left; font-size: 1.05em; }
table.pipe .arrow td { color: #8a8a8a; font-size: 0.8em; line-height: 0.6; }

/* one sentence cut three ways */
.cut .row { display: grid; grid-template-columns: 130px 1fr; gap: 12px; align-items: center; margin: 0.25em 0; }
.cut .lab { font-size: 0.6em; text-align: right; color: #3c3c3c; line-height: 1.25; }
.cut .toks { display: flex; flex-wrap: wrap; gap: 3px; font-size: 0.62em; }

/* byte-pair encoding on a toy corpus */
table.toy { border-collapse: separate; border-spacing: 4px 6px; font-size: 0.58em; margin: 0 auto; }
table.toy td, table.toy th { border: none; padding: 0 2px; background: none; text-align: left; white-space: nowrap; }
table.toy th { font-weight: 700; color: #3c3c3c; border-bottom: none; }
table.toy td.m { color: #5c5c5c; text-align: right; padding-right: 8px; }
table.toy td.m b { color: #c41230; }
table.toy .tk { padding: 2px 5px; margin-right: 2px; }
table.toy .tk.new { outline: 2px solid #c41230; }

/* the generation cycle */
.cycle { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 0.3em; }
.cycle > div { background: #f7f7f7; border-radius: 10px; padding: 8px 12px; font-size: 0.64em; border-top: 6px solid #1f5c99; }
.cycle > div:nth-child(2) { border-top-color: #2e7d32; }
.cycle > div:nth-child(3) { border-top-color: #c41230; }
.cycle > div:nth-child(4) { border-top-color: #b07d12; }
.cycle .n { font-size: 1.5em; font-weight: 700; color: #5c5c5c; }
.cycle .mini { margin-top: 6px; background: #fff; border-radius: 6px; padding: 5px 7px; font-size: 0.92em; color: #3c3c3c; }
.cycle .MathJax { margin: 0.1em 0 !important; }

/* code with highlighted lines, a diagram of what the code builds, and the notes */
.codegrid { display: grid; grid-template-columns: 1fr 350px; gap: 18px; align-items: start; }
.codegrid.wide { grid-template-columns: 1fr 400px; }
pre.code { margin: 0; padding: 6px 0; font-size: var(--fs, 14px); line-height: 1.3; }
pre.code code { font-size: inherit; line-height: inherit; background: none; padding: 0; display: block; }
pre.code .ln { display: block; padding: 0 12px; white-space: pre; transition: background 0.25s; }
pre.code .ln.dim { opacity: 1; }
.tdiag { display: flex; flex-direction: column; gap: 5px; font-size: 0.56em; }
.tdiag .dio { text-align: center; color: #5c5c5c; font-style: italic; }
.dbox { background: #fff; border: 2px solid #c8c8c8; border-radius: 7px; padding: 4px 8px; text-align: center; transition: all 0.25s; }
.dbox.add { border-style: dashed; }
.cos { display: grid; margin-top: 6px; }
.cos > .co { grid-area: 1 / 1; }
.cos > .co[data-bespoke-marp-fragment="active"]:has(~ .co[data-bespoke-marp-fragment="active"]) { visibility: hidden; }
.co { background: #f7f7f7; border-left: 5px solid #1f5c99; border-radius: 0 6px 6px 0; padding: 5px 10px; font-size: 0.64em; line-height: 1.32; margin-bottom: 8px; }
.tdiag .co { font-size: 1.12em; margin-bottom: 0; }
.co p { margin: 0.15em 0; }
.co.c1 { border-left-color: #1f5c99; } .co.c2 { border-left-color: #2e7d32; } .co.c3 { border-left-color: #b07d12; }
.co.c4 { border-left-color: #c41230; } .co.c5 { border-left-color: #7a3db8; }
.co .mono { font-size: 0.95em; background: #fff; padding: 3px 6px; border-radius: 4px; margin-top: 4px; white-space: pre; }

/* three samples side by side */
.samples { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.samples > div { background: #f7f7f7; border-radius: 8px; padding: 6px 10px; font-size: 0.54em; border-top: 5px solid #1f5c99; }
.samples > div:nth-child(2) { border-top-color: #2e7d32; }
.samples > div:nth-child(3) { border-top-color: #c41230; }
.samples h4 { margin: 2px 0 4px; font-size: 1.3em; }
.samples pre { white-space: pre-wrap; font-size: 0.95em; line-height: 1.3; margin: 0; padding: 6px 8px; background: #fff; border-left: none; }
.samples p { margin: 0.35em 0 0; }

/* limitations: what goes wrong, and what to do */
.fix { display: grid; grid-template-columns: 1fr 1fr; gap: 7px 46px; align-items: center; font-size: 0.6em; margin-top: 0.1em; }
.fix .good { position: relative; }
.fix .good::before { content: '→'; position: absolute; left: -36px; top: 50%; transform: translateY(-50%); font-size: 1.4em; color: #5c5c5c; }
.fix .hd + .hd::before { content: none; }
.fix .bad { background: rgba(196, 18, 48, 0.08); border-left: 5px solid #c41230; border-radius: 0 6px 6px 0; padding: 5px 10px; }
.fix .good { background: rgba(46, 125, 50, 0.08); border-left: 5px solid #2e7d32; border-radius: 0 6px 6px 0; padding: 5px 10px; }
.fix .hd { font-weight: 700; color: #5c5c5c; font-size: 1.05em; }

/* recap: the pipeline, and tiles */
.pipeline { display: flex; align-items: stretch; justify-content: center; gap: 6px; font-size: 0.6em; }
.pnode { background: #f7f7f7; border: 2px solid #c8c8c8; border-radius: 8px; padding: 6px 10px; text-align: center; flex: 1; }
.pnode.dark { background: #2b2b2b; color: #fff; border-color: #2b2b2b; }
.parr { align-self: center; font-size: 1.5em; color: #5c5c5c; }
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.tile { background: #f7f7f7; border-radius: 10px; padding: 6px 12px; font-size: 0.6em; border-left: 6px solid #1f5c99; }
.tile h4 { margin: 2px 0 4px; font-size: 1.3em; }
.tile p { margin: 0.2em 0; }
.tile img { width: 100%; max-height: 120px; object-fit: contain; display: block; }
.tile:nth-child(2) { border-left-color: #2e7d32; } .tile:nth-child(3) { border-left-color: #c41230; }

/* post-training: three steps */
.steps3 { display: grid; grid-template-columns: 1fr 34px 1fr 34px 1fr 34px 1fr; align-items: stretch; font-size: 0.6em; }
.steps3 > div:not(.ar) { background: #f7f7f7; border-radius: 8px; padding: 6px 10px; border-top: 5px solid #8a8a8a; }
.steps3 .ar { align-self: center; text-align: center; font-size: 1.6em; color: #5c5c5c; }
.steps3 h4 { margin: 2px 0 4px; font-size: 1.2em; }
.steps3 p { margin: 0.2em 0; }
.steps3 .q { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.92em; background: #fff; border-radius: 5px; padding: 4px 6px; margin-top: 4px; }

/* the equation cards: each one lights up its term */
.card.c-joint { border-top-color: #1f5c99; } .card.c-prod { border-top-color: #b07d12; } .card.c-cond { border-top-color: #c41230; }
section:has(.card.c-joint[data-bespoke-marp-fragment="active"]) .term.t-joint { background: rgba(31, 92, 153, 0.12); border-color: #1f5c99; }
section:has(.card.c-prod[data-bespoke-marp-fragment="active"]) .term.t-prod { background: rgba(176, 125, 18, 0.15); border-color: #b07d12; }
section:has(.card.c-cond[data-bespoke-marp-fragment="active"]) .term.t-cond { background: rgba(196, 18, 48, 0.10); border-color: #c41230; }
.card.c-qkv { border-top-color: #7a3db8; } .card.c-score { border-top-color: #1f5c99; } .card.c-mask { border-top-color: #c41230; } .card.c-val { border-top-color: #2e7d32; }
section:has(.card.c-qkv[data-bespoke-marp-fragment="active"]):not(:has(.card.c-score[data-bespoke-marp-fragment="active"])) :is(.term.t-score, .term.t-val) { background: rgba(122, 61, 184, 0.12); border-color: #7a3db8; }
section:has(.card.c-score[data-bespoke-marp-fragment="active"]) .term.t-score { background: rgba(31, 92, 153, 0.12); border-color: #1f5c99; }
section:has(.card.c-mask[data-bespoke-marp-fragment="active"]) .term.t-mask { background: rgba(196, 18, 48, 0.10); border-color: #c41230; }
section:has(.card.c-val[data-bespoke-marp-fragment="active"]) .term.t-val { background: rgba(46, 125, 50, 0.12); border-color: #2e7d32; }
.card.c-num { border-top-color: #1f5c99; } .card.c-den { border-top-color: #b07d12; }
section:has(.card.c-num[data-bespoke-marp-fragment="active"]) .term.t-num { background: rgba(31, 92, 153, 0.12); border-color: #1f5c99; }
section:has(.card.c-den[data-bespoke-marp-fragment="active"]) .term.t-den { background: rgba(176, 125, 18, 0.15); border-color: #b07d12; }
.card.c-avg { border-top-color: #1f5c99; } .card.c-logp { border-top-color: #c41230; } .card.c-ce { border-top-color: #2e7d32; }
section:has(.card.c-avg[data-bespoke-marp-fragment="active"]) .term.t-avg { background: rgba(31, 92, 153, 0.12); border-color: #1f5c99; }
section:has(.card.c-logp[data-bespoke-marp-fragment="active"]) .term.t-logp { background: rgba(196, 18, 48, 0.10); border-color: #c41230; }
.card.c-tz { border-top-color: #1f5c99; } .card.c-tt { border-top-color: #c41230; }
section:has(.card.c-tz[data-bespoke-marp-fragment="active"]) .term.t-tz { background: rgba(31, 92, 153, 0.12); border-color: #1f5c99; }
section:has(.card.c-tt[data-bespoke-marp-fragment="active"]) .term.t-tt { background: rgba(196, 18, 48, 0.10); border-color: #c41230; }
.card.c-law { border-top-color: #1f5c99; }

/* L17 additions: a wide figure column, the vocabulary next to the token table, a training-loop
   group in the code diagrams, a split bar, a compact comparison table, the recap's pictures */
.cols-fig { grid-template-columns: 1.65fr 1fr; }
.cycle p { margin: 0.15em 0; }
.tokviz { display: grid; grid-template-columns: 1fr 290px; gap: 22px; align-items: center; margin-top: 0.3em; }
.vocab { background: #f7f7f7; border-radius: 8px; padding: 6px 10px; font-size: 0.5em; border-top: 5px solid #2b2b2b; }
.vocab .vh { font-weight: 700; margin-bottom: 4px; }
.vocab .vr { display: grid; grid-template-columns: 70px 1fr; gap: 8px; padding: 1px 6px; border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.vocab .vr .vid { text-align: right; color: #5c5c5c; }
.vocab .dots { color: #8a8a8a; display: block; text-align: center; line-height: 1; }
table.pipe .arrow td.al { text-align: left; font-size: 0.7em; color: #5c5c5c; line-height: 1.2; }
.dsplit { display: grid; grid-template-columns: 9fr 1fr; border: 2px solid #c8c8c8; border-radius: 7px; overflow: hidden;
  text-align: center; transition: all 0.25s; }
.dsplit .tr { background: #fff; padding: 4px 6px; }
.dsplit .ho { background: #ececec; padding: 4px 2px; font-size: 0.8em; writing-mode: horizontal-tb; }
.dsplit { grid-template-columns: 3fr 2fr; }
.loopgrp { display: flex; flex-direction: column; gap: 5px; border: 2px dashed #8a8a8a; border-radius: 10px; padding: 4px 8px 8px; }
.looplab { text-align: center; color: #5c5c5c; font-style: italic; }
table.cmp { font-size: 0.55em; border-collapse: collapse; width: 100%; }
table.cmp th, table.cmp td { border: 1px solid #d8d8d8; padding: 4px 7px; text-align: left; }
table.cmp tr { background: transparent !important; }
table.cmp td:first-child { font-weight: 700; color: #3c3c3c; white-space: nowrap; }
table.cmp th { background: #f2f2f2; }
.pnode .pv { margin-top: 5px; font-size: 0.95em; }
.pnode .pv.q { font-style: italic; }
.pnode img { width: 100%; max-height: 95px; object-fit: contain; display: block; margin: 4px auto 0; background: #fff; border-radius: 4px; }
.pnode .bars div { display: grid; grid-template-columns: 62px 1fr; gap: 4px; align-items: center; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.9em; }
.pnode .bars i { display: block; height: 9px; background: #1f5c99; border-radius: 2px; }
.pnode .bars div:first-child i { background: #c41230; }
.tk.g2 { background: rgba(196, 18, 48, 0.15); border: 1.5px solid rgba(196, 18, 48, 0.55); padding: 1px 5px; font-size: 0.95em; }
.pnode.dark .tk.g2 { background: rgba(255, 255, 255, 0.15); border-color: #f2a0ad; color: #fff; }
.tiles.four { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 0.5em; }
.tiles.four .tk { white-space: normal; }
.tiles.four .tile img { max-height: 100px; }
.tile h4 { margin: 2px 0 4px; }
.tile .MathJax { margin: 0.2em 0 !important; font-size: 0.85em; }
.cols-side .cw > img { max-height: 440px; width: auto; max-width: 100%; display: block; margin: 0 auto; }

/* 3Blue1Brown-inspired additions: the title credit, the vocabulary grid, a two-option bar pair */
section p.credit { font-size: 0.55em; opacity: 0.85; margin-top: 1.2em; }
.chips.left { justify-content: flex-start; }
.termgrid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px 12px; margin: 0.3em 0 0.5em; }
.termgrid .tc { background: rgba(46, 125, 50, 0.1); border-left: 5px solid #2e7d32; border-radius: 0 6px 6px 0; padding: 4px 8px;
  display: flex; gap: 8px; align-items: baseline; font-size: 0.6em; }
.termgrid .tc.miss { background: rgba(196, 18, 48, 0.1); border-left-color: #c41230; }
.termgrid .tl { color: #5c5c5c; font-size: 0.85em; min-width: 2.2em; }
.termgrid .tt { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.termgrid .tt b { color: #2e7d32; }
.termgrid .tc.miss .tt b { color: #c41230; }
.vs { font-size: 0.6em; width: 560px; margin: 0.3em auto 0.2em; }
.vs .vh { font-weight: 700; margin-bottom: 4px; text-align: center; }
.vs .vrow em { font-style: normal; }
.vs .vrow { display: grid; grid-template-columns: 7em 1fr 3.5em; gap: 6px; align-items: center; margin: 3px 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.vs .vrow i { display: block; height: 14px; background: #1f5c99; border-radius: 2px; }
.vs .vrow.pick i { background: #c41230; }
.readbox code b, .readbox code { white-space: nowrap; }
.readbox code b { color: #2e7d32; }
.readbox code b.no { color: #c41230; }

/* the single credit at the end */
.thanks { background: #fff8e6; border-left: 8px solid #b07d12; border-radius: 0 10px 10px 0; padding: 10px 18px; font-size: 0.64em; margin-bottom: 0.5em; }
.thanks .tk-h { font-size: 1.45em; font-weight: 800; color: #7a5200; margin-bottom: 0.2em; }
.thanks p { margin: 0.35em 0; }

/* code colors (pygments, default style) and the per-slide line highlights */
pre.code .c { color: #3D7B7B; font-style: italic } /* Comment */
pre.code .err { border: 1px solid #F00 } /* Error */
pre.code .k { color: #008000; font-weight: bold } /* Keyword */
pre.code .o { color: #666 } /* Operator */
pre.code .ch { color: #3D7B7B; font-style: italic } /* Comment.Hashbang */
pre.code .cm { color: #3D7B7B; font-style: italic } /* Comment.Multiline */
pre.code .cp { color: #9C6500 } /* Comment.Preproc */
pre.code .cpf { color: #3D7B7B; font-style: italic } /* Comment.PreprocFile */
pre.code .c1 { color: #3D7B7B; font-style: italic } /* Comment.Single */
pre.code .cs { color: #3D7B7B; font-style: italic } /* Comment.Special */
pre.code .gd { color: #A00000 } /* Generic.Deleted */
pre.code .ge { font-style: italic } /* Generic.Emph */
pre.code .ges { font-weight: bold; font-style: italic } /* Generic.EmphStrong */
pre.code .gr { color: #E40000 } /* Generic.Error */
pre.code .gh { color: #000080; font-weight: bold } /* Generic.Heading */
pre.code .gi { color: #008400 } /* Generic.Inserted */
pre.code .go { color: #717171 } /* Generic.Output */
pre.code .gp { color: #000080; font-weight: bold } /* Generic.Prompt */
pre.code .gs { font-weight: bold } /* Generic.Strong */
pre.code .gu { color: #800080; font-weight: bold } /* Generic.Subheading */
pre.code .gt { color: #04D } /* Generic.Traceback */
pre.code .kc { color: #008000; font-weight: bold } /* Keyword.Constant */
pre.code .kd { color: #008000; font-weight: bold } /* Keyword.Declaration */
pre.code .kn { color: #008000; font-weight: bold } /* Keyword.Namespace */
pre.code .kp { color: #008000 } /* Keyword.Pseudo */
pre.code .kr { color: #008000; font-weight: bold } /* Keyword.Reserved */
pre.code .kt { color: #B00040 } /* Keyword.Type */
pre.code .m { color: #666 } /* Literal.Number */
pre.code .s { color: #BA2121 } /* Literal.String */
pre.code .na { color: #687822 } /* Name.Attribute */
pre.code .nb { color: #008000 } /* Name.Builtin */
pre.code .nc { color: #00F; font-weight: bold } /* Name.Class */
pre.code .no { color: #800 } /* Name.Constant */
pre.code .nd { color: #A2F } /* Name.Decorator */
pre.code .ni { color: #717171; font-weight: bold } /* Name.Entity */
pre.code .ne { color: #CB3F38; font-weight: bold } /* Name.Exception */
pre.code .nf { color: #00F } /* Name.Function */
pre.code .nl { color: #767600 } /* Name.Label */
pre.code .nn { color: #00F; font-weight: bold } /* Name.Namespace */
pre.code .nt { color: #008000; font-weight: bold } /* Name.Tag */
pre.code .nv { color: #19177C } /* Name.Variable */
pre.code .ow { color: #A2F; font-weight: bold } /* Operator.Word */
pre.code .w { color: #BBB } /* Text.Whitespace */
pre.code .mb { color: #666 } /* Literal.Number.Bin */
pre.code .mf { color: #666 } /* Literal.Number.Float */
pre.code .mh { color: #666 } /* Literal.Number.Hex */
pre.code .mi { color: #666 } /* Literal.Number.Integer */
pre.code .mo { color: #666 } /* Literal.Number.Oct */
pre.code .sa { color: #BA2121 } /* Literal.String.Affix */
pre.code .sb { color: #BA2121 } /* Literal.String.Backtick */
pre.code .sc { color: #BA2121 } /* Literal.String.Char */
pre.code .dl { color: #BA2121 } /* Literal.String.Delimiter */
pre.code .sd { color: #BA2121; font-style: italic } /* Literal.String.Doc */
pre.code .s2 { color: #BA2121 } /* Literal.String.Double */
pre.code .se { color: #AA5D1F; font-weight: bold } /* Literal.String.Escape */
pre.code .sh { color: #BA2121 } /* Literal.String.Heredoc */
pre.code .si { color: #A45A77; font-weight: bold } /* Literal.String.Interpol */
pre.code .sx { color: #008000 } /* Literal.String.Other */
pre.code .sr { color: #A45A77 } /* Literal.String.Regex */
pre.code .s1 { color: #BA2121 } /* Literal.String.Single */
pre.code .ss { color: #19177C } /* Literal.String.Symbol */
pre.code .bp { color: #008000 } /* Name.Builtin.Pseudo */
pre.code .fm { color: #00F } /* Name.Function.Magic */
pre.code .vc { color: #19177C } /* Name.Variable.Class */
pre.code .vg { color: #19177C } /* Name.Variable.Global */
pre.code .vi { color: #19177C } /* Name.Variable.Instance */
pre.code .vm { color: #19177C } /* Name.Variable.Magic */
pre.code .il { color: #666 } /* Literal.Number.Integer.Long */
section:has(.cg1 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-B[data-bespoke-marp-fragment="active"])) .cg1 .L6, section:has(.cg1 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-B[data-bespoke-marp-fragment="active"])) .cg1 .L7, section:has(.cg1 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-B[data-bespoke-marp-fragment="active"])) .cg1 .L8, section:has(.cg1 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-B[data-bespoke-marp-fragment="active"])) .cg1 .L9, section:has(.cg1 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-B[data-bespoke-marp-fragment="active"])) .cg1 .L10, section:has(.cg1 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-B[data-bespoke-marp-fragment="active"])) .cg1 .L11, section:has(.cg1 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-B[data-bespoke-marp-fragment="active"])) .cg1 .L12, section:has(.cg1 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-B[data-bespoke-marp-fragment="active"])) .cg1 .L13, section:has(.cg1 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-B[data-bespoke-marp-fragment="active"])) .cg1 .L14, section:has(.cg1 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-B[data-bespoke-marp-fragment="active"])) .cg1 .L15, section:has(.cg1 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-B[data-bespoke-marp-fragment="active"])) .cg1 .L16 { background: rgba(31,92,153,0.14); box-shadow: inset 5px 0 0 rgb(31,92,153); }
section:has(.cg1 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-B[data-bespoke-marp-fragment="active"])) .cg1 .d-A { background: rgba(31,92,153,0.14); border-color: rgb(31,92,153); }
section:has(.cg1 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-C[data-bespoke-marp-fragment="active"])) .cg1 .L18, section:has(.cg1 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-C[data-bespoke-marp-fragment="active"])) .cg1 .L19, section:has(.cg1 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-C[data-bespoke-marp-fragment="active"])) .cg1 .L20, section:has(.cg1 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-C[data-bespoke-marp-fragment="active"])) .cg1 .L21, section:has(.cg1 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-C[data-bespoke-marp-fragment="active"])) .cg1 .L22 { background: rgba(46,125,50,0.14); box-shadow: inset 5px 0 0 rgb(46,125,50); }
section:has(.cg1 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-C[data-bespoke-marp-fragment="active"])) .cg1 .d-B { background: rgba(46,125,50,0.14); border-color: rgb(46,125,50); }
section:has(.cg1 .f-C[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-D[data-bespoke-marp-fragment="active"])) .cg1 .L23 { background: rgba(176,125,18,0.14); box-shadow: inset 5px 0 0 rgb(176,125,18); }
section:has(.cg1 .f-C[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-D[data-bespoke-marp-fragment="active"])) .cg1 .d-C { background: rgba(176,125,18,0.14); border-color: rgb(176,125,18); }
section:has(.cg1 .f-D[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-E[data-bespoke-marp-fragment="active"])) .cg1 .L24 { background: rgba(196,18,48,0.14); box-shadow: inset 5px 0 0 rgb(196,18,48); }
section:has(.cg1 .f-D[data-bespoke-marp-fragment="active"]):not(:has(.cg1 .f-E[data-bespoke-marp-fragment="active"])) .cg1 .d-D { background: rgba(196,18,48,0.14); border-color: rgb(196,18,48); }
section:has(.cg1 .f-E[data-bespoke-marp-fragment="active"]) .cg1 .L25 { background: rgba(122,61,184,0.14); box-shadow: inset 5px 0 0 rgb(122,61,184); }
section:has(.cg1 .f-E[data-bespoke-marp-fragment="active"]) .cg1 .d-E { background: rgba(122,61,184,0.14); border-color: rgb(122,61,184); }
section:has(.cg2 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg2 .f-B[data-bespoke-marp-fragment="active"])) .cg2 .L31, section:has(.cg2 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg2 .f-B[data-bespoke-marp-fragment="active"])) .cg2 .L32 { background: rgba(31,92,153,0.14); box-shadow: inset 5px 0 0 rgb(31,92,153); }
section:has(.cg2 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg2 .f-B[data-bespoke-marp-fragment="active"])) .cg2 .d-A { background: rgba(31,92,153,0.14); border-color: rgb(31,92,153); }
section:has(.cg2 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg2 .f-C[data-bespoke-marp-fragment="active"])) .cg2 .L33 { background: rgba(46,125,50,0.14); box-shadow: inset 5px 0 0 rgb(46,125,50); }
section:has(.cg2 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg2 .f-C[data-bespoke-marp-fragment="active"])) .cg2 .d-B { background: rgba(46,125,50,0.14); border-color: rgb(46,125,50); }
section:has(.cg2 .f-C[data-bespoke-marp-fragment="active"]):not(:has(.cg2 .f-D[data-bespoke-marp-fragment="active"])) .cg2 .L34, section:has(.cg2 .f-C[data-bespoke-marp-fragment="active"]):not(:has(.cg2 .f-D[data-bespoke-marp-fragment="active"])) .cg2 .L35 { background: rgba(176,125,18,0.14); box-shadow: inset 5px 0 0 rgb(176,125,18); }
section:has(.cg2 .f-C[data-bespoke-marp-fragment="active"]):not(:has(.cg2 .f-D[data-bespoke-marp-fragment="active"])) .cg2 .d-C { background: rgba(176,125,18,0.14); border-color: rgb(176,125,18); }
section:has(.cg2 .f-D[data-bespoke-marp-fragment="active"]) .cg2 .L37, section:has(.cg2 .f-D[data-bespoke-marp-fragment="active"]) .cg2 .L38, section:has(.cg2 .f-D[data-bespoke-marp-fragment="active"]) .cg2 .L39, section:has(.cg2 .f-D[data-bespoke-marp-fragment="active"]) .cg2 .L40 { background: rgba(196,18,48,0.14); box-shadow: inset 5px 0 0 rgb(196,18,48); }
section:has(.cg2 .f-D[data-bespoke-marp-fragment="active"]) .cg2 .d-D { background: rgba(196,18,48,0.14); border-color: rgb(196,18,48); }
section:has(.cg3 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg3 .f-B[data-bespoke-marp-fragment="active"])) .cg3 .L1, section:has(.cg3 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg3 .f-B[data-bespoke-marp-fragment="active"])) .cg3 .L2, section:has(.cg3 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg3 .f-B[data-bespoke-marp-fragment="active"])) .cg3 .L3 { background: rgba(31,92,153,0.14); box-shadow: inset 5px 0 0 rgb(31,92,153); }
section:has(.cg3 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg3 .f-B[data-bespoke-marp-fragment="active"])) .cg3 .d-A { background: rgba(31,92,153,0.14); border-color: rgb(31,92,153); }
section:has(.cg3 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg3 .f-C[data-bespoke-marp-fragment="active"])) .cg3 .L5, section:has(.cg3 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg3 .f-C[data-bespoke-marp-fragment="active"])) .cg3 .L6 { background: rgba(46,125,50,0.14); box-shadow: inset 5px 0 0 rgb(46,125,50); }
section:has(.cg3 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg3 .f-C[data-bespoke-marp-fragment="active"])) .cg3 .d-B { background: rgba(46,125,50,0.14); border-color: rgb(46,125,50); }
section:has(.cg3 .f-C[data-bespoke-marp-fragment="active"]) .cg3 .L12, section:has(.cg3 .f-C[data-bespoke-marp-fragment="active"]) .cg3 .L13 { background: rgba(176,125,18,0.14); box-shadow: inset 5px 0 0 rgb(176,125,18); }
section:has(.cg3 .f-C[data-bespoke-marp-fragment="active"]) .cg3 .d-C { background: rgba(176,125,18,0.14); border-color: rgb(176,125,18); }
section:has(.cg4 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-B[data-bespoke-marp-fragment="active"])) .cg4 .L1, section:has(.cg4 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-B[data-bespoke-marp-fragment="active"])) .cg4 .L2, section:has(.cg4 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-B[data-bespoke-marp-fragment="active"])) .cg4 .L3, section:has(.cg4 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-B[data-bespoke-marp-fragment="active"])) .cg4 .L4 { background: rgba(31,92,153,0.14); box-shadow: inset 5px 0 0 rgb(31,92,153); }
section:has(.cg4 .f-A[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-B[data-bespoke-marp-fragment="active"])) .cg4 .d-A { background: rgba(31,92,153,0.14); border-color: rgb(31,92,153); }
section:has(.cg4 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-C[data-bespoke-marp-fragment="active"])) .cg4 .L11, section:has(.cg4 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-C[data-bespoke-marp-fragment="active"])) .cg4 .L12, section:has(.cg4 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-C[data-bespoke-marp-fragment="active"])) .cg4 .L13 { background: rgba(46,125,50,0.14); box-shadow: inset 5px 0 0 rgb(46,125,50); }
section:has(.cg4 .f-B[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-C[data-bespoke-marp-fragment="active"])) .cg4 .d-B { background: rgba(46,125,50,0.14); border-color: rgb(46,125,50); }
section:has(.cg4 .f-C[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-D[data-bespoke-marp-fragment="active"])) .cg4 .L14, section:has(.cg4 .f-C[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-D[data-bespoke-marp-fragment="active"])) .cg4 .L15, section:has(.cg4 .f-C[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-D[data-bespoke-marp-fragment="active"])) .cg4 .L16 { background: rgba(176,125,18,0.14); box-shadow: inset 5px 0 0 rgb(176,125,18); }
section:has(.cg4 .f-C[data-bespoke-marp-fragment="active"]):not(:has(.cg4 .f-D[data-bespoke-marp-fragment="active"])) .cg4 .d-C { background: rgba(176,125,18,0.14); border-color: rgb(176,125,18); }
section:has(.cg4 .f-D[data-bespoke-marp-fragment="active"]) .cg4 .L18, section:has(.cg4 .f-D[data-bespoke-marp-fragment="active"]) .cg4 .L19, section:has(.cg4 .f-D[data-bespoke-marp-fragment="active"]) .cg4 .L20, section:has(.cg4 .f-D[data-bespoke-marp-fragment="active"]) .cg4 .L21, section:has(.cg4 .f-D[data-bespoke-marp-fragment="active"]) .cg4 .L22 { background: rgba(196,18,48,0.14); box-shadow: inset 5px 0 0 rgb(196,18,48); }
section:has(.cg4 .f-D[data-bespoke-marp-fragment="active"]) .cg4 .d-D { background: rgba(196,18,48,0.14); border-color: rgb(196,18,48); }
</style>

<!-- _class: section -->

# Worked example: the code

---

## The model, one transformer block in code

<div class="cg1 codegrid">
<div>

<pre class="code" style="--fs:13px"><code><span class="ln L4"><span class="k">class</span><span class="w"> </span><span class="nc">Block</span><span class="p">(</span><span class="n">nn</span><span class="o">.</span><span class="n">Module</span><span class="p">):</span></span><span class="ln L5">    <span class="c1"># one transformer block: causal self-attention, then an MLP</span></span><span class="ln L6">    <span class="k">def</span><span class="w"> </span><span class="fm">__init__</span><span class="p">(</span><span class="bp">self</span><span class="p">):</span></span><span class="ln L7">        <span class="nb">super</span><span class="p">()</span><span class="o">.</span><span class="fm">__init__</span><span class="p">()</span></span><span class="ln L8">        <span class="bp">self</span><span class="o">.</span><span class="n">ln1</span> <span class="o">=</span> <span class="n">nn</span><span class="o">.</span><span class="n">LayerNorm</span><span class="p">(</span><span class="n">n_embd</span><span class="p">)</span></span><span class="ln L9">        <span class="bp">self</span><span class="o">.</span><span class="n">qkv</span> <span class="o">=</span> <span class="n">nn</span><span class="o">.</span><span class="n">Linear</span><span class="p">(</span><span class="n">n_embd</span><span class="p">,</span> <span class="mi">3</span> <span class="o">*</span> <span class="n">n_embd</span><span class="p">)</span>       <span class="c1"># q, k, v at once</span></span><span class="ln L10">        <span class="bp">self</span><span class="o">.</span><span class="n">proj</span> <span class="o">=</span> <span class="n">nn</span><span class="o">.</span><span class="n">Linear</span><span class="p">(</span><span class="n">n_embd</span><span class="p">,</span> <span class="n">n_embd</span><span class="p">)</span></span><span class="ln L11">        <span class="bp">self</span><span class="o">.</span><span class="n">ln2</span> <span class="o">=</span> <span class="n">nn</span><span class="o">.</span><span class="n">LayerNorm</span><span class="p">(</span><span class="n">n_embd</span><span class="p">)</span></span><span class="ln L12">        <span class="bp">self</span><span class="o">.</span><span class="n">mlp</span> <span class="o">=</span> <span class="n">nn</span><span class="o">.</span><span class="n">Sequential</span><span class="p">(</span></span><span class="ln L13">            <span class="n">nn</span><span class="o">.</span><span class="n">Linear</span><span class="p">(</span><span class="n">n_embd</span><span class="p">,</span> <span class="mi">4</span> <span class="o">*</span> <span class="n">n_embd</span><span class="p">),</span></span><span class="ln L14">            <span class="n">nn</span><span class="o">.</span><span class="n">GELU</span><span class="p">(),</span></span><span class="ln L15">            <span class="n">nn</span><span class="o">.</span><span class="n">Linear</span><span class="p">(</span><span class="mi">4</span> <span class="o">*</span> <span class="n">n_embd</span><span class="p">,</span> <span class="n">n_embd</span><span class="p">),</span></span><span class="ln L16">        <span class="p">)</span></span><span class="ln L17"> </span><span class="ln L18">    <span class="k">def</span><span class="w"> </span><span class="nf">forward</span><span class="p">(</span><span class="bp">self</span><span class="p">,</span> <span class="n">h</span><span class="p">):</span></span><span class="ln L19">        <span class="n">B</span><span class="p">,</span> <span class="n">T</span><span class="p">,</span> <span class="n">C</span> <span class="o">=</span> <span class="n">h</span><span class="o">.</span><span class="n">shape</span></span><span class="ln L20">        <span class="n">q</span><span class="p">,</span> <span class="n">k</span><span class="p">,</span> <span class="n">v</span> <span class="o">=</span> <span class="bp">self</span><span class="o">.</span><span class="n">qkv</span><span class="p">(</span><span class="bp">self</span><span class="o">.</span><span class="n">ln1</span><span class="p">(</span><span class="n">h</span><span class="p">))</span><span class="o">.</span><span class="n">split</span><span class="p">(</span><span class="n">n_embd</span><span class="p">,</span> <span class="n">dim</span><span class="o">=</span><span class="mi">2</span><span class="p">)</span></span><span class="ln L21">        <span class="n">q</span><span class="p">,</span> <span class="n">k</span><span class="p">,</span> <span class="n">v</span> <span class="o">=</span> <span class="p">(</span><span class="n">t</span><span class="o">.</span><span class="n">view</span><span class="p">(</span><span class="n">B</span><span class="p">,</span> <span class="n">T</span><span class="p">,</span> <span class="n">n_head</span><span class="p">,</span> <span class="n">C</span> <span class="o">//</span> <span class="n">n_head</span><span class="p">)</span><span class="o">.</span><span class="n">transpose</span><span class="p">(</span><span class="mi">1</span><span class="p">,</span> <span class="mi">2</span><span class="p">)</span></span><span class="ln L22">                   <span class="k">for</span> <span class="n">t</span> <span class="ow">in</span> <span class="p">(</span><span class="n">q</span><span class="p">,</span> <span class="n">k</span><span class="p">,</span> <span class="n">v</span><span class="p">))</span></span><span class="ln L23">        <span class="n">a</span> <span class="o">=</span> <span class="n">F</span><span class="o">.</span><span class="n">scaled_dot_product_attention</span><span class="p">(</span><span class="n">q</span><span class="p">,</span> <span class="n">k</span><span class="p">,</span> <span class="n">v</span><span class="p">,</span> <span class="n">is_causal</span><span class="o">=</span><span class="kc">True</span><span class="p">)</span></span><span class="ln L24">        <span class="n">h</span> <span class="o">=</span> <span class="n">h</span> <span class="o">+</span> <span class="bp">self</span><span class="o">.</span><span class="n">proj</span><span class="p">(</span><span class="n">a</span><span class="o">.</span><span class="n">transpose</span><span class="p">(</span><span class="mi">1</span><span class="p">,</span> <span class="mi">2</span><span class="p">)</span><span class="o">.</span><span class="n">reshape</span><span class="p">(</span><span class="n">B</span><span class="p">,</span> <span class="n">T</span><span class="p">,</span> <span class="n">C</span><span class="p">))</span></span><span class="ln L25">        <span class="k">return</span> <span class="n">h</span> <span class="o">+</span> <span class="bp">self</span><span class="o">.</span><span class="n">mlp</span><span class="p">(</span><span class="bp">self</span><span class="o">.</span><span class="n">ln2</span><span class="p">(</span><span class="n">h</span><span class="p">))</span></span></code></pre>

</div>
<div class="tdiag">
<div class="dio">in: one vector per token, h</div>
<div class="dbox d-A d-B">LayerNorm</div>
<div class="dbox d-A d-B">q, k, v: one linear layer, 4 heads</div>
<div class="dbox d-A d-C">attention with the causal mask</div>
<div class="dbox add d-A d-D">⊕ add the input back</div>
<div class="dbox d-A d-E">LayerNorm</div>
<div class="dbox d-A d-E">MLP: linear → GELU → linear</div>
<div class="dbox add d-A d-E">⊕ add back</div>
<div class="dio">out: one vector per token</div>
<div class="cos">
<div class="co c1 f-A" data-marpit-fragment><b>__init__</b>: the layers and their weights, created once</div>
<div class="co c2 f-B" data-marpit-fragment>Normalize each vector (LayerNorm), then q, k, v from one linear layer, split into 4 heads: 4 attentions side by side</div>
<div class="co c3 f-C" data-marpit-fragment><code>is_causal=True</code>: attention with the causal mask. PyTorch builds M for us</div>
<div class="co c4 f-D" data-marpit-fragment><b>Residual</b>: add the result to the input h, so each block adds a correction</div>
<div class="co c5 f-E" data-marpit-fragment>A small MLP (Lecture 12) on each token's vector, also added back</div>
</div>
</div>
</div>


---

## The model, the whole tiny GPT in code

<div class="cg2 codegrid">
<div>

<pre class="code" style="--fs:15px"><code><span class="ln L28"><span class="k">class</span><span class="w"> </span><span class="nc">TinyGPT</span><span class="p">(</span><span class="n">nn</span><span class="o">.</span><span class="n">Module</span><span class="p">):</span></span><span class="ln L29">    <span class="k">def</span><span class="w"> </span><span class="fm">__init__</span><span class="p">(</span><span class="bp">self</span><span class="p">):</span></span><span class="ln L30">        <span class="nb">super</span><span class="p">()</span><span class="o">.</span><span class="fm">__init__</span><span class="p">()</span></span><span class="ln L31">        <span class="bp">self</span><span class="o">.</span><span class="n">tok</span> <span class="o">=</span> <span class="n">nn</span><span class="o">.</span><span class="n">Embedding</span><span class="p">(</span><span class="n">vocab_size</span><span class="p">,</span> <span class="n">n_embd</span><span class="p">)</span>    <span class="c1"># token -&gt; vector</span></span><span class="ln L32">        <span class="bp">self</span><span class="o">.</span><span class="n">pos</span> <span class="o">=</span> <span class="n">nn</span><span class="o">.</span><span class="n">Embedding</span><span class="p">(</span><span class="n">block_size</span><span class="p">,</span> <span class="n">n_embd</span><span class="p">)</span>    <span class="c1"># position -&gt; vector</span></span><span class="ln L33">        <span class="bp">self</span><span class="o">.</span><span class="n">blocks</span> <span class="o">=</span> <span class="n">nn</span><span class="o">.</span><span class="n">Sequential</span><span class="p">(</span><span class="o">*</span><span class="p">[</span><span class="n">Block</span><span class="p">()</span> <span class="k">for</span> <span class="n">_</span> <span class="ow">in</span> <span class="nb">range</span><span class="p">(</span><span class="n">n_layer</span><span class="p">)])</span></span><span class="ln L34">        <span class="bp">self</span><span class="o">.</span><span class="n">ln</span> <span class="o">=</span> <span class="n">nn</span><span class="o">.</span><span class="n">LayerNorm</span><span class="p">(</span><span class="n">n_embd</span><span class="p">)</span></span><span class="ln L35">        <span class="bp">self</span><span class="o">.</span><span class="n">head</span> <span class="o">=</span> <span class="n">nn</span><span class="o">.</span><span class="n">Linear</span><span class="p">(</span><span class="n">n_embd</span><span class="p">,</span> <span class="n">vocab_size</span><span class="p">)</span>      <span class="c1"># vector -&gt; logits</span></span><span class="ln L36"> </span><span class="ln L37">    <span class="k">def</span><span class="w"> </span><span class="nf">forward</span><span class="p">(</span><span class="bp">self</span><span class="p">,</span> <span class="n">x</span><span class="p">):</span></span><span class="ln L38">        <span class="n">T</span> <span class="o">=</span> <span class="n">x</span><span class="o">.</span><span class="n">shape</span><span class="p">[</span><span class="mi">1</span><span class="p">]</span></span><span class="ln L39">        <span class="n">h</span> <span class="o">=</span> <span class="bp">self</span><span class="o">.</span><span class="n">tok</span><span class="p">(</span><span class="n">x</span><span class="p">)</span> <span class="o">+</span> <span class="bp">self</span><span class="o">.</span><span class="n">pos</span><span class="p">(</span><span class="n">torch</span><span class="o">.</span><span class="n">arange</span><span class="p">(</span><span class="n">T</span><span class="p">,</span> <span class="n">device</span><span class="o">=</span><span class="n">x</span><span class="o">.</span><span class="n">device</span><span class="p">))</span></span><span class="ln L40">        <span class="k">return</span> <span class="bp">self</span><span class="o">.</span><span class="n">head</span><span class="p">(</span><span class="bp">self</span><span class="o">.</span><span class="n">ln</span><span class="p">(</span><span class="bp">self</span><span class="o">.</span><span class="n">blocks</span><span class="p">(</span><span class="n">h</span><span class="p">)))</span>      <span class="c1"># (batch, T, vocab)</span></span></code></pre>

</div>
<div class="tdiag">
<div class="dio">in: character ids, e.g. "pump" → 4 numbers</div>
<div class="dbox d-A d-D">token embedding + position embedding</div>
<div class="dbox d-B d-D">4 transformer blocks (previous slide)</div>
<div class="dbox d-C d-D">LayerNorm</div>
<div class="dbox d-C d-D">linear head: 129 logits</div>
<div class="dio">out: 129 logits at every position</div>
<div class="cos">
<div class="co c1 f-A" data-marpit-fragment><b>Embeddings</b>: a learned vector for each of the 129 characters, plus one for each position, since attention alone ignores order (Lecture 12)</div>
<div class="co c2 f-B" data-marpit-fragment>Four blocks, one after the other</div>
<div class="co c3 f-C" data-marpit-fragment>Normalize, then a linear layer: one logit per character in the vocabulary</div>
<div class="co c4 f-D" data-marpit-fragment><code>forward</code>: ids → vectors → blocks → logits, for every position at once</div>
</div>
</div>
</div>


---

## Training, inputs and targets in code

<div class="cg3 codegrid wide">
<div>

<pre class="code" style="--fs:14px"><code><span class="ln L1"><span class="n">data</span> <span class="o">=</span> <span class="n">torch</span><span class="o">.</span><span class="n">tensor</span><span class="p">(</span><span class="n">encode</span><span class="p">(</span><span class="n">text</span><span class="p">))</span></span><span class="ln L2"><span class="n">n</span> <span class="o">=</span> <span class="nb">int</span><span class="p">(</span><span class="mf">0.9</span> <span class="o">*</span> <span class="nb">len</span><span class="p">(</span><span class="n">data</span><span class="p">))</span></span><span class="ln L3"><span class="n">train_data</span><span class="p">,</span> <span class="n">val_data</span> <span class="o">=</span> <span class="n">data</span><span class="p">[:</span><span class="n">n</span><span class="p">],</span> <span class="n">data</span><span class="p">[</span><span class="n">n</span><span class="p">:]</span>     <span class="c1"># last 10% held out</span></span><span class="ln L4"> </span><span class="ln L5"><span class="n">block_size</span> <span class="o">=</span> <span class="mi">128</span>      <span class="c1"># context window: characters the model sees at once</span></span><span class="ln L6"><span class="n">batch_size</span> <span class="o">=</span> <span class="mi">64</span>       <span class="c1"># windows per training step</span></span><span class="ln L7"> </span><span class="ln L8"> </span><span class="ln L9"><span class="k">def</span><span class="w"> </span><span class="nf">get_batch</span><span class="p">(</span><span class="n">split</span><span class="p">):</span></span><span class="ln L10">    <span class="n">d</span> <span class="o">=</span> <span class="n">train_data</span> <span class="k">if</span> <span class="n">split</span> <span class="o">==</span> <span class="s2">&quot;train&quot;</span> <span class="k">else</span> <span class="n">val_data</span></span><span class="ln L11">    <span class="n">i</span> <span class="o">=</span> <span class="n">torch</span><span class="o">.</span><span class="n">randint</span><span class="p">(</span><span class="nb">len</span><span class="p">(</span><span class="n">d</span><span class="p">)</span> <span class="o">-</span> <span class="n">block_size</span> <span class="o">-</span> <span class="mi">1</span><span class="p">,</span> <span class="p">(</span><span class="n">batch_size</span><span class="p">,))</span></span><span class="ln L12">    <span class="n">x</span> <span class="o">=</span> <span class="n">torch</span><span class="o">.</span><span class="n">stack</span><span class="p">([</span><span class="n">d</span><span class="p">[</span><span class="n">j</span><span class="p">:</span><span class="n">j</span> <span class="o">+</span> <span class="n">block_size</span><span class="p">]</span> <span class="k">for</span> <span class="n">j</span> <span class="ow">in</span> <span class="n">i</span><span class="p">])</span>           <span class="c1"># inputs</span></span><span class="ln L13">    <span class="n">y</span> <span class="o">=</span> <span class="n">torch</span><span class="o">.</span><span class="n">stack</span><span class="p">([</span><span class="n">d</span><span class="p">[</span><span class="n">j</span> <span class="o">+</span> <span class="mi">1</span><span class="p">:</span><span class="n">j</span> <span class="o">+</span> <span class="n">block_size</span> <span class="o">+</span> <span class="mi">1</span><span class="p">]</span> <span class="k">for</span> <span class="n">j</span> <span class="ow">in</span> <span class="n">i</span><span class="p">])</span>   <span class="c1"># next chars</span></span><span class="ln L14">    <span class="k">return</span> <span class="n">x</span><span class="o">.</span><span class="n">to</span><span class="p">(</span><span class="n">device</span><span class="p">),</span> <span class="n">y</span><span class="o">.</span><span class="n">to</span><span class="p">(</span><span class="n">device</span><span class="p">)</span></span></code></pre>

</div>
<div class="tdiag">
<div class="dio">our notes: 668,651 characters</div>
<div class="dbox d-A">one long list of character ids</div>
<div class="dsplit d-A"><span class="tr">train: first 90%</span><span class="ho">held out: last 10%</span></div>
<div class="dbox d-B">64 random windows of 128 characters</div>
<div class="dbox d-C">x: each window · y: the same window, shifted by one</div>
<div class="dio">→ one batch for the model</div>
<div class="cos">
<div class="co c1 f-A" data-marpit-fragment>Our notes as one long list of character ids. The last 10% is <b>held out</b>: never trained on, kept to measure</div>
<div class="co c2 f-B" data-marpit-fragment>The context window: 128 characters. 64 windows at random places make one batch</div>
<div class="co c3 f-C" data-marpit-fragment>y is x <b>shifted by one</b>: the target for x[0..t] is y[t]
<div class="mono">x: "ce for recent readings. "
y: "e for recent readings. A"</div>
</div>
</div>
</div>
</div>


---

## Training, the loop in code

<div class="cg4 codegrid wide">
<div>

<pre class="code" style="--fs:14px"><code><span class="ln L1"><span class="n">torch</span><span class="o">.</span><span class="n">manual_seed</span><span class="p">(</span><span class="mi">0</span><span class="p">)</span></span><span class="ln L2"><span class="n">model</span> <span class="o">=</span> <span class="n">TinyGPT</span><span class="p">()</span><span class="o">.</span><span class="n">to</span><span class="p">(</span><span class="n">device</span><span class="p">)</span></span><span class="ln L3"><span class="n">optimizer</span> <span class="o">=</span> <span class="n">torch</span><span class="o">.</span><span class="n">optim</span><span class="o">.</span><span class="n">AdamW</span><span class="p">(</span><span class="n">model</span><span class="o">.</span><span class="n">parameters</span><span class="p">(),</span> <span class="n">lr</span><span class="o">=</span><span class="mf">1e-3</span><span class="p">)</span></span><span class="ln L4"><span class="nb">print</span><span class="p">(</span><span class="nb">sum</span><span class="p">(</span><span class="n">p</span><span class="o">.</span><span class="n">numel</span><span class="p">()</span> <span class="k">for</span> <span class="n">p</span> <span class="ow">in</span> <span class="n">model</span><span class="o">.</span><span class="n">parameters</span><span class="p">()),</span> <span class="s2">&quot;parameters&quot;</span><span class="p">)</span></span><span class="ln L5"> </span><span class="ln L6"><span class="n">steps</span> <span class="o">=</span> <span class="mi">2000</span>          <span class="c1"># on a CPU, try 500 first</span></span><span class="ln L7"><span class="n">losses</span> <span class="o">=</span> <span class="p">[]</span>           <span class="c1"># training loss at every step</span></span><span class="ln L8"><span class="n">history</span> <span class="o">=</span> <span class="p">[]</span>          <span class="c1"># (step, validation loss, sample) every 250 steps</span></span><span class="ln L9"><span class="n">start</span> <span class="o">=</span> <span class="n">time</span><span class="o">.</span><span class="n">time</span><span class="p">()</span></span><span class="ln L10"><span class="k">for</span> <span class="n">step</span> <span class="ow">in</span> <span class="nb">range</span><span class="p">(</span><span class="n">steps</span> <span class="o">+</span> <span class="mi">1</span><span class="p">):</span></span><span class="ln L11">    <span class="n">x</span><span class="p">,</span> <span class="n">y</span> <span class="o">=</span> <span class="n">get_batch</span><span class="p">(</span><span class="s2">&quot;train&quot;</span><span class="p">)</span></span><span class="ln L12">    <span class="n">logits</span> <span class="o">=</span> <span class="n">model</span><span class="p">(</span><span class="n">x</span><span class="p">)</span>                                   <span class="c1"># (batch, T, vocab)</span></span><span class="ln L13">    <span class="n">loss</span> <span class="o">=</span> <span class="n">F</span><span class="o">.</span><span class="n">cross_entropy</span><span class="p">(</span><span class="n">logits</span><span class="o">.</span><span class="n">view</span><span class="p">(</span><span class="o">-</span><span class="mi">1</span><span class="p">,</span> <span class="n">vocab_size</span><span class="p">),</span> <span class="n">y</span><span class="o">.</span><span class="n">view</span><span class="p">(</span><span class="o">-</span><span class="mi">1</span><span class="p">))</span></span><span class="ln L14">    <span class="n">optimizer</span><span class="o">.</span><span class="n">zero_grad</span><span class="p">()</span></span><span class="ln L15">    <span class="n">loss</span><span class="o">.</span><span class="n">backward</span><span class="p">()</span></span><span class="ln L16">    <span class="n">optimizer</span><span class="o">.</span><span class="n">step</span><span class="p">()</span></span><span class="ln L17">    <span class="n">losses</span><span class="o">.</span><span class="n">append</span><span class="p">(</span><span class="n">loss</span><span class="o">.</span><span class="n">item</span><span class="p">())</span></span><span class="ln L18">    <span class="k">if</span> <span class="n">step</span> <span class="o">%</span> <span class="mi">250</span> <span class="o">==</span> <span class="mi">0</span><span class="p">:</span></span><span class="ln L19">        <span class="n">sample</span> <span class="o">=</span> <span class="n">generate</span><span class="p">(</span><span class="s2">&quot;The model &quot;</span><span class="p">,</span> <span class="n">n</span><span class="o">=</span><span class="mi">120</span><span class="p">,</span> <span class="n">temperature</span><span class="o">=</span><span class="mf">0.8</span><span class="p">)</span></span><span class="ln L20">        <span class="n">history</span><span class="o">.</span><span class="n">append</span><span class="p">((</span><span class="n">step</span><span class="p">,</span> <span class="n">val_loss</span><span class="p">(),</span> <span class="n">sample</span><span class="p">))</span></span><span class="ln L21">        <span class="nb">print</span><span class="p">(</span><span class="sa">f</span><span class="s2">&quot;step </span><span class="si">{</span><span class="n">step</span><span class="si">:</span><span class="s2">4d</span><span class="si">}</span><span class="s2">  train </span><span class="si">{</span><span class="n">loss</span><span class="o">.</span><span class="n">item</span><span class="p">()</span><span class="si">:</span><span class="s2">.2f</span><span class="si">}</span><span class="s2">  &quot;</span></span><span class="ln L22">              <span class="sa">f</span><span class="s2">&quot;val </span><span class="si">{</span><span class="n">history</span><span class="p">[</span><span class="o">-</span><span class="mi">1</span><span class="p">][</span><span class="mi">1</span><span class="p">]</span><span class="si">:</span><span class="s2">.2f</span><span class="si">}</span><span class="s2">  (</span><span class="si">{</span><span class="n">time</span><span class="o">.</span><span class="n">time</span><span class="p">()</span><span class="w"> </span><span class="o">-</span><span class="w"> </span><span class="n">start</span><span class="si">:</span><span class="s2">.0f</span><span class="si">}</span><span class="s2"> s)&quot;</span><span class="p">)</span></span></code></pre>

</div>
<div class="tdiag">
<div class="dbox d-A">TinyGPT: 842,881 parameters θ, and AdamW</div>
<div class="loopgrp">
<div class="looplab">repeat 2,001 times</div>
<div class="dbox d-B">a batch: x, y (previous slide)</div>
<div class="dbox d-B">forward: logits → cross-entropy L(θ)</div>
<div class="dbox d-C">backward: the gradient ∇<sub>θ</sub>L</div>
<div class="dbox d-C">AdamW step: θ moves downhill</div>
<div class="dbox add d-D">every 250 steps: held-out loss, a sample</div>
</div>
<div class="cos">
<div class="co c1 f-A" data-marpit-fragment>The model, and AdamW: the optimizer of Lecture 12, learning rate 0.001</div>
<div class="co c2 f-B" data-marpit-fragment>A batch of windows, logits at every position, and the cross-entropy against the next characters: L(θ)</div>
<div class="co c3 f-C" data-marpit-fragment>Backpropagation gives the gradient ∇<sub>θ</sub>L. One AdamW step moves θ downhill</div>
<div class="co c4 f-D" data-marpit-fragment>Every 250 steps: the loss on held-out text, and a sample of what the model writes</div>
</div>
</div>
</div>


---

<!-- _class: demo -->

# Worked example

`l17-tiny-llm.ipynb`: train a tiny GPT on our own notes. On Colab, choose a GPU runtime first
