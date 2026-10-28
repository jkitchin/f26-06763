---
marp: true
theme: course
paginate: true
header: "06-763 / L17"
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

/* round 6: the split word, Wikipedia's BPE example, the loss ruler, a table that builds, the post-training stages */
.cut .tk.split { outline: 2px solid #c41230; }
.wiki { display: flex; flex-direction: column; gap: 6px; margin: 0.3em auto 0.5em; width: 92%; }
.wiki .wrow { display: grid; grid-template-columns: 330px 1fr 90px; gap: 12px; align-items: center; font-size: 0.62em; }
.wiki .wl { color: #3c3c3c; text-align: right; }
.wiki .wt { display: flex; gap: 4px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 1.15em; }
.wiki .wt .tk { padding: 2px 8px; }
.wiki .wt .tk.new { outline: 2px solid #c41230; }
.wiki .wn { color: #5c5c5c; }
.ruler { margin-top: 0.5em; font-size: 0.95em; background: #f7f7f7; border-radius: 6px; padding: 6px 10px; }
.ruler .rh, .ruler .rr { display: grid; grid-template-columns: 3.2em 1fr 9.5em; gap: 8px; align-items: center; margin: 3px 0; }
.ruler .rh { font-weight: 700; color: #3c3c3c; }
.ruler .rr span:nth-child(2) { display: flex; align-items: center; gap: 6px; font-variant-numeric: tabular-nums; }
.ruler .rr i { display: block; height: 11px; background: #2e7d32; border-radius: 2px; min-width: 2px; }
.ruler .rr span:last-child { color: #5c5c5c; }
table.cmp.build tr[data-bespoke-marp-fragment="active"]:not(:has(~ tr[data-bespoke-marp-fragment="active"])) { background: #fff8e6 !important; }
table.cmp.build tr[data-bespoke-marp-fragment="active"]:not(:has(~ tr[data-bespoke-marp-fragment="active"])) td { font-weight: 600; }
.stages { display: grid; grid-template-columns: 1fr 28px 1fr 28px 1.15fr 28px 1fr; align-items: stretch; font-size: 0.6em; margin-top: 0.3em; }
.stages .st { background: #f7f7f7; border-radius: 10px; padding: 8px 10px; border-top: 6px solid #8a8a8a; transition: all 0.3s; }
.stages .st.dark { background: #2b2b2b; color: #fff; border-top-color: #2b2b2b; }
.stages .sh { font-weight: 800; font-size: 1.15em; margin-bottom: 4px; }
.stages .sd { margin-bottom: 6px; }
.stages .sx { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.88em; background: #fff; color: #1a1a1a; border-radius: 6px; padding: 5px 7px; }
.stages .sa { align-self: center; text-align: center; font-size: 1.8em; color: #5c5c5c; }
.stages .st:nth-child(1) { border-top-color: #1f5c99; } .stages .st:nth-child(3) { border-top-color: #2e7d32; } .stages .st:nth-child(5) { border-top-color: #b07d12; }
.cw.compact > img { max-height: 330px; width: auto; max-width: 100%; display: block; margin: 0 auto; }

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

</style>

<!-- _class: title -->

# Lecture 17: Large language models

## What they are, and how they are trained

---

## A chatbot, from the inside

<div class="readbox smaller">

- **What we did:** asked a real chat model one question, on a laptop: Qwen2.5-0.5B-Instruct, a small open model from Alibaba (0.49 billion parameters), built like a GPT
- **What you see:** the chat app (left), the text the model really reads and continues token by token (middle), its top guesses (right). Press play
- **The gray tags,** `<|im_start|>` and `<|im_end|>`: special tokens that open and close each message, so the model knows who speaks. The app hides them

</div>

<div class="cw compact" data-widget="llm-chat" data-source="l17"><img src="figures/widget-llm-chat.png" alt="A chat model's answer, the hidden script it completes, and its next-token probabilities"></div>

<!--
Picture a movie script with the AI's reply torn off, and a machine that predicts the next word. Run it again and again and the reply writes itself. That is all a chatbot is. The model was trained on chats written with these tags, so it expects them. How this was made: Hugging Face transformers, the model taking its most likely token at every step; the numbers come from figures/make_figures.py (group chat).
-->

---

## Today

<div class="road">
<div><img src="figures/widget-llm-sample.png" alt="GPT-2's next-token probabilities"><div><div class="n">1</div><b>From generative models to text</b><br>Text, one token at a time</div></div>
<div data-marpit-fragment><img src="figures/bpe.png" alt="A sentence split into tokens"><div><div class="n">2</div><b>Tokens</b><br>What the model reads, and what it costs</div></div>
<div data-marpit-fragment><img src="figures/look-back.png" alt="Attention looking back at earlier words"><div><div class="n">3</div><b>The model</b><br>A transformer that only looks back</div></div>
<div data-marpit-fragment><img src="figures/tiny-loss.png" alt="The loss of the tiny GPT falling"><div><div class="n">4</div><b>Training</b><br>Predict the next token, everywhere</div></div>
<div data-marpit-fragment><img src="figures/scale.png" alt="Parameters against training tokens"><div><div class="n">5</div><b>Data and scale</b><br>From our notes to trillions of tokens</div></div>
<div data-marpit-fragment><img src="figures/temperature.png" alt="Probabilities at three temperatures"><div><div class="n">6</div><b>Sampling</b><br>Temperature, and why fluent is not true</div></div>
</div>

---

## Today, our running example: a tiny GPT

<div class="flow">
<div class="box">Our notes<br><b>Lectures 1 to 16</b><br>668,651 characters</div><div class="arr">→</div>
<div class="box">Train<br><b>2,000 steps</b><br>about 2 minutes on a laptop GPU</div><div class="arr">→</div>
<div class="box dark">A tiny GPT<br><b>842,881 parameters</b><br>writes like our notes</div>
</div>

<div class="small">

- **GPT**, generative pretrained transformer: the model family behind ChatGPT. Ours is tiny, and we train it from scratch

* It reads and writes **one character at a time**
* Same recipe as GPT-3, about 200,000 times smaller. We trained it for this lecture, and it appears on many slides

</div>

<div class="cols cols-even small" data-marpit-fragment>
<div class="readbox bred"><b>Before training</b>, it writes:<br><code>The model l₂4zé&#x27;-(u↑Ly°⁷)aQ8d¹₆−wZ²t,&gt;zü4i{₂YGIkt└TR&gt;P×−t_ …</code></div>
<div class="readbox bgreen"><b>After training</b>, given the start of one term from each lecture, it finishes <b>15 of 16</b>: <code>Parqu<b>et</b></code> <code>regres<b>sion</b></code> <code>Bayesian opti<b>mization</b></code> <code>physics-in<b class=no>to a s</b></code></div>
</div>

<!--
GPU: graphics processing unit, the graphics card. 116 s on an Apple-silicon laptop. On Colab, choose a GPU runtime.
-->

---

<!-- _class: section -->

# From generative models to text

---

## From generative models to text, where Lecture 16 left us

<div class="flow">
<div class="box">Data<br><b>x</b></div><div class="arr">→</div>
<div class="box">Learn the distribution<br><b>p(x)</b></div><div class="arr">→</div>
<div class="box dark">Fix what you know,<br>sample the rest</div>
</div>

- **Lecture 16:** a generative model learns the distribution of the data, then samples new data from it

* There, x was a point in two dimensions: Gaussian mixtures, flows, diffusion
* **Today, x is a text:** a sequence of tokens $x_1, x_2, \dots, x_T$. For now, a token is a word or a piece of a word
* **A large language model (LLM) is a generative model of text.** Your prompt is the part you fix; it samples the rest

---

## From generative models to text, one variable at a time

<div class="cols cols-fig cols-top">
<div>

![w:700](figures/two-ways.png)

</div>
<div class="small">

- **Left, Lecture 16:** draw a whole point (x, y) at once

* **Right, the same distribution, one variable at a time:** first draw x, then y given that x. Same result: p(x, y) = p(x) p(y | x)
* **Text has too many possibilities to draw at once.** A 10-token text has 10 slots, each holding any of 50,257 tokens: 50,257 × 50,257 × … ten times = 50,257¹⁰ ≈ 10⁴⁷ texts. One token at a time, each step is one choice among 50,257

</div>
</div>

---

## From generative models to text, the chain rule

<div class="eqrow big">
<div class="term t-joint">

$p(x_1, \dots, x_T)$

</div>
<div>

$=$

</div>
<div class="term t-prod">

$\displaystyle\prod_{t=1}^{T}$

</div>
<div class="term t-cond">

$p(x_t \mid x_1, \dots, x_{t-1})$

</div>
</div>

<div class="cards">
<div class="card c-joint" data-marpit-fragment><h4>The whole text</h4><p>How likely this exact text is, all T tokens together</p></div>
<div class="card c-prod" data-marpit-fragment><h4>One factor per token</h4><p>Multiply: the 1st token, times the 2nd given the 1st, times the 3rd given the first two, and so on to the last</p></div>
<div class="card c-cond" data-marpit-fragment><h4>One next-token probability</h4><p>How likely token <i>t</i> is, given all the tokens before it. <b>This is the only thing an LLM learns</b></p></div>
</div>

<div class="example" data-marpit-fragment>

**Example: we ran GPT-2** (OpenAI, 2019, 124 million parameters) on "The pump stopped" and read its probability for each token, given the ones before it:

p("The pump stopped")<br> = p("The") × p("␣pump" | "The") × p("␣stopped" | "The pump")<br>= 0.038 × 8.5 × 10<sup>-6</sup> × 0.0019 = 5.9 × 10<sup>-10</sup>

</div>

<!--
The chain rule is exact: no assumption about which earlier tokens matter. ␣ marks a space: GPT-2's tokens carry their leading space. The product is tiny because so many texts are possible; "pump" right after "The" is the surprise, 8 in a million.
-->

---

<!-- _class: definition -->

## Language model

**Language model**: a model that gives the probability of the next token, $p(x_t \mid x_1, \dots, x_{t-1})$, from the tokens before it. By the chain rule, that is enough to score a whole text, and to write one.

**Large language model (LLM)**: a language model with billions of parameters, trained on trillions of tokens.

---

## From generative models to text, the generation loop

<div class="cycle">
<div>

<div class="n">1</div>

**Predict** the last factor of the chain rule, for every possible next token:

$p(x_{t+1} \mid x_1, \dots, x_t)$

<div class="mini">"The pump stopped because the" →<br>␣water 3.7% · ␣pump 2.9% · ␣gas 2.2% · …</div>

</div>
<div data-marpit-fragment><div class="n">2</div><b>Pick</b><br>One token from that distribution<div class="mini">Here, the most likely: <b>␣water</b>. Other ways to pick: Sampling section</div></div>
<div data-marpit-fragment><div class="n">3</div><b>Append</b><br>Add it to the end of the text<div class="mini">"The pump stopped because the <b>water</b>"</div></div>
<div data-marpit-fragment><div class="n">4</div><b>Repeat</b><br>Predict again, from the longer text<div class="mini">→ ␣was → ␣too → ␣hot → .</div></div>
</div>

<div class="chips" data-marpit-fragment>

<span class="ctx">The pump stopped because the</span><span class="g" data-marpit-fragment>␣water</span><span class="g" data-marpit-fragment>␣was</span><span class="g" data-marpit-fragment>␣too</span><span class="g" data-marpit-fragment>␣hot</span><span class="g" data-marpit-fragment>.</span>

</div>

<p class="small center" data-marpit-fragment>Each red token is one trip round the loop: GPT-2 predicted it, it was appended, and the next prediction started from the longer text. A model that uses its own outputs as its next inputs is <b>autoregressive</b>.</p>

<!--
How this was made: we ran GPT-2 (124 million parameters, Hugging Face transformers) on "The pump stopped because the" and, five times, took its single most likely next token and appended it. The probabilities on the cards are GPT-2's. The code: figures/make_figures.py, group gpt2. Click once per token: each click is one trip round the loop. The Sampling section steps through the same loop with GPT-2's real probabilities, and a temperature slider.
-->

---

## From generative models to text, autoregressive as in Lecture 8

<div class="cols cols-lc cols-top">
<div>

![w:540](figures/ar-recursive.png)

<p class="smaller center">Lecture 8's AR(10), reactor pressure, 2 hours ahead on one test run</p>

</div>
<div>

<table class="cmp build">
<tr><th></th><th>Lecture 8: AR(10)</th><th>An LLM</th></tr>
<tr data-marpit-fragment><td>Predicts</td><td>the next pressure</td><td>the next token</td></tr>
<tr data-marpit-fragment><td>From</td><td>the last 10 values</td><td>all the text so far</td></tr>
<tr data-marpit-fragment><td>Output</td><td>one number</td><td>a probability for every token</td></tr>
<tr data-marpit-fragment><td>Model</td><td>11 coefficients</td><td>billions of parameters</td></tr>
<tr data-marpit-fragment><td>Long outputs</td><td>feed each forecast back in</td><td>append each token: the same</td></tr>
</table>

</div>
</div>

<div class="readbox bred small" data-marpit-fragment>

**Same weakness:** both feed their own outputs back in, so an early mistake becomes an input for every later step. Lecture 8: after 2 hours, the forecast was worse than the plain mean. An LLM: one wrong token steers the rest of the answer

</div>

<!--
The analogy is between Lecture 8's autoregressive forecaster and an LLM writing text: same word, same idea. It is not a claim about RNNs, nor that LLMs lose accuracy over the years. Bengio et al. (2015) described the same effect for RNN text generators: trained on true previous tokens, run on their own, "errors that can accumulate quickly along the generated sequence".
-->

---

<!-- _class: section -->

# Tokens

---

## Tokens, what the model actually reads

<div class="definition small">

**Token**: a piece of text the model reads and writes: a character, a word, or part of a word.

**Vocabulary**: the list of every token the model knows, each with a number, its **token id**.

**Tokenizer**: the program that cuts text into tokens and looks up their ids.

</div>

<div class="tokviz"><table class="pipe"><tr><td class="lab">Text</td><td class="txt" colspan="4">The pump stopped.</td></tr><tr class="arrow" data-marpit-fragment><td></td><td class="al" colspan="4">↓ the tokenizer cuts the text into tokens</td></tr><tr data-marpit-fragment><td class="lab">Tokens</td><td><span class="tk" style="background:rgba(31,111,178,.18)">The</span></td><td><span class="tk" style="background:rgba(194,65,12,.18)">␣pump</span></td><td><span class="tk" style="background:rgba(43,138,62,.2)">␣stopped</span></td><td><span class="tk" style="background:rgba(196,18,48,.15)">.</span></td></tr><tr class="arrow" data-marpit-fragment><td></td><td class="al" colspan="4">↓ and looks up each token in the vocabulary</td></tr><tr data-marpit-fragment><td class="lab">Token ids</td><td><span class="idk">464</span></td><td><span class="idk">8901</span></td><td><span class="idk">5025</span></td><td><span class="idk">13</span></td></tr></table><div class="vocab" data-marpit-fragment><div class="vh">GPT-2's vocabulary, real ids (50,257 in all)</div><div class="vr"><span class="vid">0</span><span class="vt">!</span></div><div class="vr"><span class="vid">1</span><span class="vt">&quot;</span></div><div class="vr"><span class="vid">2</span><span class="vt">#</span></div><div class="vr dots">⋮</div><div class="vr" style="background:rgba(196,18,48,.15)"><span class="vid">13</span><span class="vt">.</span></div><div class="vr dots">⋮</div><div class="vr" style="background:rgba(31,111,178,.18)"><span class="vid">464</span><span class="vt">The</span></div><div class="vr dots">⋮</div><div class="vr" style="background:rgba(43,138,62,.2)"><span class="vid">5025</span><span class="vt">␣stopped</span></div><div class="vr dots">⋮</div><div class="vr" style="background:rgba(194,65,12,.18)"><span class="vid">8901</span><span class="vt">␣pump</span></div><div class="vr dots">⋮</div></div></div>

---

## Tokens, three ways to cut the same text

<div class="cut"><div class="row"><div class="lab"><b>Characters</b><br>29 tokens</div><div class="toks"><span class="tk" style="background:rgba(31,111,178,.18)">T</span><span class="tk" style="background:rgba(194,65,12,.18)">h</span><span class="tk" style="background:rgba(43,138,62,.2)">e</span><span class="tk" style="background:rgba(196,18,48,.15)">␣</span><span class="tk" style="background:rgba(120,80,170,.18)">p</span><span class="tk" style="background:rgba(20,140,150,.2)">u</span><span class="tk" style="background:rgba(31,111,178,.18)">m</span><span class="tk" style="background:rgba(194,65,12,.18)">p</span><span class="tk" style="background:rgba(43,138,62,.2)">␣</span><span class="tk" style="background:rgba(196,18,48,.15)">o</span><span class="tk" style="background:rgba(120,80,170,.18)">v</span><span class="tk" style="background:rgba(20,140,150,.2)">e</span><span class="tk" style="background:rgba(31,111,178,.18)">r</span><span class="tk" style="background:rgba(194,65,12,.18)">h</span><span class="tk" style="background:rgba(43,138,62,.2)">e</span><span class="tk" style="background:rgba(196,18,48,.15)">a</span><span class="tk" style="background:rgba(120,80,170,.18)">t</span><span class="tk" style="background:rgba(20,140,150,.2)">e</span><span class="tk" style="background:rgba(31,111,178,.18)">d</span><span class="tk" style="background:rgba(194,65,12,.18)">␣</span><span class="tk" style="background:rgba(43,138,62,.2)">a</span><span class="tk" style="background:rgba(196,18,48,.15)">t</span><span class="tk" style="background:rgba(120,80,170,.18)">␣</span><span class="tk" style="background:rgba(20,140,150,.2)">8</span><span class="tk" style="background:rgba(31,111,178,.18)">5</span><span class="tk" style="background:rgba(194,65,12,.18)">␣</span><span class="tk" style="background:rgba(43,138,62,.2)">°</span><span class="tk" style="background:rgba(196,18,48,.15)">C</span><span class="tk" style="background:rgba(120,80,170,.18)">.</span></div></div><div class="row" data-marpit-fragment><div class="lab"><b>Words</b><br>6 tokens</div><div class="toks"><span class="tk" style="background:rgba(31,111,178,.18)">The</span><span class="tk" style="background:rgba(194,65,12,.18)">pump</span><span class="tk" style="background:rgba(43,138,62,.2)">overheated</span><span class="tk" style="background:rgba(196,18,48,.15)">at</span><span class="tk" style="background:rgba(120,80,170,.18)">85</span><span class="tk" style="background:rgba(20,140,150,.2)">°C.</span></div></div><div class="row" data-marpit-fragment><div class="lab"><b>Subwords</b><br>9 tokens<br>GPT-2</div><div class="toks"><span class="tk" style="background:rgba(31,111,178,.18)">The</span><span class="tk" style="background:rgba(194,65,12,.18)">␣pump</span><span class="tk split" style="background:rgba(43,138,62,.2)">␣overhe</span><span class="tk split" style="background:rgba(196,18,48,.15)">ated</span><span class="tk" style="background:rgba(120,80,170,.18)">␣at</span><span class="tk" style="background:rgba(20,140,150,.2)">␣85</span><span class="tk" style="background:rgba(31,111,178,.18)">␣°</span><span class="tk" style="background:rgba(194,65,12,.18)">C</span><span class="tk" style="background:rgba(43,138,62,.2)">.</span></div></div></div>

<div class="cards">
<div class="card"><h4>Characters</h4><p>One token per letter, digit, space or symbol. A tiny vocabulary (our tiny GPT: <b>129</b>), but long sequences</p></div>
<div class="card" data-marpit-fragment><h4>Words</h4><p>One token per word. The vocabulary needs every word ever written, and a new one has no token: a pump tag like P-101A, a steel grade like AISI 4140</p></div>
<div class="card" data-marpit-fragment><h4>Subwords</h4><p>Pieces of words. Common words stay whole ("␣pump"), rarer ones split ("␣overhe" + "ated"), so any new word can be built. GPT-2: <b>50,257</b> tokens</p></div>
</div>

---

## Tokens, byte-pair encoding

<div class="definition">

**Byte-pair encoding (BPE)**: how a subword vocabulary is built. Find the pair of neighboring tokens that appears most often, merge it into one new token, repeat.

</div>

<div class="wiki"><div class="wrow"><span class="wl">start: one token per character</span><span class="wt"><span class="tk" style="background:#ececec">a</span><span class="tk" style="background:#ececec">a</span><span class="tk" style="background:#ececec">a</span><span class="tk" style="background:#ececec">b</span><span class="tk" style="background:#ececec">d</span><span class="tk" style="background:#ececec">a</span><span class="tk" style="background:#ececec">a</span><span class="tk" style="background:#ececec">a</span><span class="tk" style="background:#ececec">b</span><span class="tk" style="background:#ececec">a</span><span class="tk" style="background:#ececec">c</span></span><span class="wn">11 tokens</span></div><div class="wrow" data-marpit-fragment><span class="wl">1. most frequent pair: a + a (4 times)</span><span class="wt"><span class="tk new" style="background:rgba(31,111,178,.18)">aa</span><span class="tk" style="background:#ececec">a</span><span class="tk" style="background:#ececec">b</span><span class="tk" style="background:#ececec">d</span><span class="tk new" style="background:rgba(31,111,178,.18)">aa</span><span class="tk" style="background:#ececec">a</span><span class="tk" style="background:#ececec">b</span><span class="tk" style="background:#ececec">a</span><span class="tk" style="background:#ececec">c</span></span><span class="wn">9 tokens</span></div><div class="wrow" data-marpit-fragment><span class="wl">2. most frequent pair: a + b (2 times)</span><span class="wt"><span class="tk" style="background:rgba(31,111,178,.18)">aa</span><span class="tk new" style="background:rgba(43,138,62,.2)">ab</span><span class="tk" style="background:#ececec">d</span><span class="tk" style="background:rgba(31,111,178,.18)">aa</span><span class="tk new" style="background:rgba(43,138,62,.2)">ab</span><span class="tk" style="background:#ececec">a</span><span class="tk" style="background:#ececec">c</span></span><span class="wn">7 tokens</span></div><div class="wrow" data-marpit-fragment><span class="wl">3. most frequent pair: aa + ab (2 times)</span><span class="wt"><span class="tk new" style="background:rgba(196,18,48,.15)">aaab</span><span class="tk" style="background:#ececec">d</span><span class="tk new" style="background:rgba(196,18,48,.15)">aaab</span><span class="tk" style="background:#ececec">a</span><span class="tk" style="background:#ececec">c</span></span><span class="wn">5 tokens</span></div></div>

<div class="cards" data-marpit-fragment>
<div class="card"><h4>Why: fewer tokens</h4><p>Frequent pieces become one token. Shorter sequences: more text fits in the context window, fewer steps to write</p></div>
<div class="card"><h4>Why: nothing is unknown</h4><p>A new word can always be built from smaller pieces, down to single characters</p></div>
<div class="card"><h4>Why: learned from data</h4><p>The merges come from the training text, so its frequent words become single tokens</p></div>
</div>

<p class="source">Example from Wikipedia, <a href="https://en.wikipedia.org/wiki/Byte-pair_encoding">Byte-pair encoding</a>. The algorithm is Gage's (1994), adapted to building subword vocabularies by <a href="https://aclanthology.org/P16-1162/">Sennrich et al. (2016)</a>; GPT-2 starts from bytes and stops after 50,000 merges.</p>

<!--
Step 2 is a tie: "aa" + "a" also appears twice. Wikipedia's example takes "a" + "b". A real tokenizer learns its merges once, from a large text, and then applies them in the same order to any new text: the next slide.
-->

---

## Tokens, byte-pair encoding learned from our notes

<div class="readbox small">

- **What we did:** learned **600 merges** by BPE from our notes (Lectures 1 to 16), then applied them, in order, to one sentence. Press play. The last row is GPT-4o's tokenizer, learned the same way from far more text

* **The takeaway:** each merge makes tokens longer and fewer. 35 characters become **18 tokens** with our 600 merges, **10** with GPT-4o's. Fewer tokens: more text fits in the context window, and writing it takes fewer steps

</div>

<div class="cw compact" data-widget="llm-bpe" data-source="l17"><img src="figures/widget-llm-bpe.png" alt="Byte-pair encoding applied merge by merge to the sentence The pump temperature rose to 85 °C."></div>

<!--
The first merges our notes learn: " t", " a", "he", "in", "re". More merges, longer tokens, fewer of them.
-->

---

## Tokens, numbers and units cost more than words

<div class="cols cols-lc">
<div>

![w:640](figures/tokens.png)

</div>
<div class="small">

- **Same length, very different cost:** "heat exchanger" is 14 characters and **2 tokens**. "Q = 1.5e-3 m³/s" is 15 characters and **12 tokens**

* **The model reads numbers in pieces:** the tokenizer cuts "4140" (a steel grade) into two tokens, "414" and "0", the way it cuts a word into pieces. The model never sees the quantity four thousand one hundred forty
* **So numbers, units and part numbers (P-101A: a pump tag) are where LLMs slip.** Check them, and do the arithmetic in code

</div>
</div>

<p class="source">GPT-4o's tokenizer (o200k_base, in <code>tiktoken</code>).</p>

---

<!-- _class: definition -->

## Context window

**Context window**: the most tokens a model can take in at once: your prompt, any documents, and everything it has written so far. Text beyond it is not seen at all.

<div class="kpis" style="grid-template-columns: repeat(3, 1fr);">
<div class="kpi"><div class="v">128</div><div class="l">characters: our tiny GPT<br>about one sentence</div></div>
<div class="kpi" data-marpit-fragment><div class="v">2,048</div><div class="l">tokens: GPT-3 (<a href="https://arxiv.org/abs/2005.14165">Brown et al., 2020</a>)<br>a few pages</div></div>
<div class="kpi" data-marpit-fragment><div class="v">128,000</div><div class="l">tokens: Llama 3 (<a href="https://arxiv.org/abs/2407.21783">Llama Team, 2024</a>)<br>a long report, but not all our notes: <b>164,779 tokens</b></div></div>
</div>

<p class="takeaway" data-marpit-fragment>Too long to fit: cut it, summarize it, or search for the part that matters.</p>

<p class="source">GPT-3: "a context window of nctx = 2048 tokens". Llama 3: "a context window of up to 128K tokens". Our notes counted with GPT-4o's tokenizer (tiktoken, o200k_base).</p>

---

<!-- _class: section -->

# The model

---

## The model, the big picture

<div class="readbox smaller">

- **The case:** we gave GPT-2 the prompt "The plant shut down for maintenance" and asked for the next token. Watch "plant": alone, it could be a tree or a factory. The final probabilities are GPT-2's; the vectors and the map are a sketch. Press play

</div>

<div class="cw compact" data-widget="llm-flow" data-source="l17"><img src="figures/widget-llm-flow.png" alt="Tokens become vectors, attention mixes them, an MLP updates each, and the last vector gives probabilities"></div>

<p class="source">In Lecture 12 the tokens were cycles of a sensor window; the machinery is the same.</p>

<!--
Attention: the vectors talk to each other. MLP: each vector, alone, through the same small network. Repeat. Only the last vector predicts the next token. The next two slides open the two boxes: the attention equation and the final softmax.
-->

---

## The model, attention looks back

![w:1000](figures/look-back.png)

<div class="cards">
<div class="card" data-marpit-fragment><h4>1. Score</h4><p>The word "too" asks every earlier word: how useful are you for guessing what comes next?</p></div>
<div class="card" data-marpit-fragment><h4>2. Mix</h4><p>It takes a weighted average of what those words carry. Here, mostly "water"</p></div>
<div class="card" data-marpit-fragment><h4>3. No peeking</h4><p>Later words are hidden: the <b>causal mask</b>. In training the next word is the answer, so it must stay hidden</p></div>
</div>

<p class="source" data-marpit-fragment>In symbols, as in Lecture 12: softmax(QKᵀ/√d<sub>k</sub> + M) V. QKᵀ/√d<sub>k</sub> are the scores; the mask M is −∞ for later words, which sets their weight to 0. The weights in the picture are a sketch.</p>

---

<!-- _class: section -->

# Training

---

## Training, tuning the dials

<div class="readbox smaller">

- **One training step:** show the model some text with the next character hidden; it guesses; compare its guess with the true character; nudge every dial a little so the true one gets more likely. Repeat 2,000 times
- **What you see:** our tiny GPT on one example, "…learns the proba?". The true answer is "b". Press play

</div>

<div class="cw compact" data-widget="llm-dials" data-source="l17"><img src="figures/widget-llm-dials.png" alt="Dials, the model's top guesses for the next character, and the chance of the true one, during training"></div>

<p class="source">A straight-line fit (Lecture 9) has 2 dials; our tiny GPT has 842,881; GPT-3 has 175 billion. The nudge is a gradient step, with the gradient from backpropagation (Lecture 11).</p>

<!--
How this was made: we trained the tiny GPT for 2,000 steps and saved its guesses every 250 steps; the bars and the chart are those checkpoints. The dials are a drawing.
-->

---

## Training, the objective

<div class="small">

- **Training makes real text likely.** By the chain rule, a text's log-probability is a sum over its tokens. We want it large, so we minimize its negative

</div>

<div class="eqrow" data-marpit-fragment>
<div>

$\mathcal{L}(\theta) =$

</div>
<div class="term t-avg">

$-\dfrac{1}{T}\displaystyle\sum_{t=1}^{T}$

</div>
<div class="term t-logp">

$\log p_\theta(x_{t+1} \mid x_1, \dots, x_t)$

</div>
</div>

<div class="cols cols-cl cols-top">
<div class="cards one">
<div class="card c-logp" data-marpit-fragment><h4>log p of the true next token</h4><p>How much probability the model gave the token that really came next. θ: the dials</p></div>
<div class="card c-avg" data-marpit-fragment><h4>The minus, and the average</h4><p>The minus makes it a loss: near 0 when right and sure, large when surprised (the plot). 1/T Σ: the average over T positions. This is the cross-entropy of Lecture 10</p></div>
</div>
<div data-marpit-fragment>

![w:380](figures/neglog.png)

</div>
</div>

---

## Training, every position at once

<div class="readbox smaller">

- **What you see:** one sentence of 10 tokens turned into 9 guesses. Guess 1: from "The" alone, guess the next token. Guess 2: from "The pump". Each answer is just the next token of the text: nobody labels anything. Press play

</div>

<div class="cw compact" data-widget="llm-causal" data-source="l17"><img src="figures/widget-llm-causal.png" alt="One sentence, nine guesses: what each guess can see, and the token it must guess"></div>

<div class="readbox bgreen smaller" data-marpit-fragment>

**The point:** one sentence gives 9 training examples, all done at once, in one pass: **self-supervised** learning. Each guess sees only the tokens before it (the causal mask); otherwise the answer would be in plain sight

</div>

---

## Training, an optimization problem

$$
\min_{\theta}\;\; \mathcal{L}(\theta) = -\frac{1}{N} \sum_{n=1}^{N} \log p_\theta\big(\text{next token}_n \mid \text{the tokens before it}\big)
$$

<div class="cols cols-lc cols-top">
<div>

![w:560](figures/decision-map.png)

</div>
<div class="cards one">
<div class="card"><h4>Decision variables</h4><p>The parameters θ: <b>842,881</b> in our tiny GPT, 175 billion in GPT-3</p></div>
<div class="card" data-marpit-fragment><h4>Objective</h4><p>The loss over all N predictions: the same kind of data loss we minimized in Lecture 13</p></div>
<div class="card" data-marpit-fragment><h4>Method</h4><p>Gradient-based, by Lecture 15's map. AdamW (Lecture 12) for our tiny GPT and <a href="https://arxiv.org/abs/2407.21783">Llama 3</a>; Adam for <a href="https://arxiv.org/abs/2005.14165">GPT-3</a></p></div>
</div>
</div>

<!--
The reactor of Lecture 15 had 2 knobs and hours per experiment: Bayesian optimization. Our tiny GPT has 842,881 knobs and 58 ms per step: gradient descent. The map is Lecture 15's, with the tiny GPT added.
-->

---

## Training, reading the loss

<div class="cols cols-lc">
<div>

![w:600](figures/tiny-loss.png)

</div>
<div class="small">

<div class="readbox bgold">

**At the start, the dials are random:** each of the 129 characters gets about the same chance, 1/129. A blind guess has a loss of −ln(1/129) = 4.86: the dotted line

</div>

<div class="readbox bred" data-marpit-fragment>

**To read a loss, undo the ln.** The loss is the average of −ln p, so e<sup>−loss</sup> is the typical p. At the end, e<sup>−1.51</sup> = 0.22: the true next character typically gets **22%**

</div>

<div class="ruler" data-marpit-fragment><div class="rh"><span>loss</span><span>typical p = e<sup>−loss</sup></span><span></span></div><div class="rr"><span>4.86</span><span><i style="width:1%"></i>0.8%</span><span>a blind guess, 1/129</span></div><div class="rr"><span>1.51</span><span><i style="width:22%"></i>22%</span><span>our tiny GPT, at the end</span></div><div class="rr"><span>0.69</span><span><i style="width:50%"></i>50%</span><span>a coin flip</span></div><div class="rr"><span>0.00</span><span><i style="width:100%"></i>100%</span><span>sure and right</span></div></div>

</div>
</div>

<!--
"Typical" is the geometric mean of the probabilities given to the true characters. The blue curve, the training batches, ends lower (1.22) than the red, held-out text (1.51): it predicts text it has seen better than new text, the overfitting of Lecture 9.
-->

---

## Training, what it writes as it learns

<div class="readbox smaller">

- **What you see:** the loss (top), what it writes after "The model " at that step, and what changed. Press play. Trained only on our notes, it copies their style, LaTeX included: far more text and a bigger model turn style into meaning

</div>

<div class="cw compact" data-widget="llm-train" data-source="l17"><img src="figures/widget-llm-train.png" alt="Training and held-out loss of the tiny GPT, and what it writes every 250 steps"></div>

<!--
Random symbols, then letters and spaces, then short words, then the course's vocabulary, then LaTeX copied from our notes. It learns the style long before any meaning.
-->

---

## Training, what our tiny GPT learned

<p class="small">Give it the first 60% of one term from each lecture; it picks the most likely next character until the term ends.</p>

<div class="termgrid"><div class="tc"><span class="tl">L1</span><span class="tt">toolch<b>ain</b></span></div><div class="tc"><span class="tl">L2</span><span class="tt">environ<b>ment</b></span></div><div class="tc"><span class="tl">L3</span><span class="tt">datab<b>ase</b></span></div><div class="tc"><span class="tl">L4</span><span class="tt">Parqu<b>et</b></span></div><div class="tc"><span class="tl">L5</span><span class="tt">datafr<b>ame</b></span></div><div class="tc"><span class="tl">L6</span><span class="tt">valida<b>tion</b></span></div><div class="tc"><span class="tl">L7</span><span class="tt">steady s<b>tate</b></span></div><div class="tc"><span class="tl">L8</span><span class="tt">forec<b>ast</b></span></div><div class="tc"><span class="tl">L9</span><span class="tt">regres<b>sion</b></span></div><div class="tc"><span class="tl">L10</span><span class="tt">classific<b>ation</b></span></div><div class="tc"><span class="tl">L11</span><span class="tt">gradi<b>ent</b></span></div><div class="tc"><span class="tl">L12</span><span class="tt">convolu<b>tion</b></span></div><div class="tc miss"><span class="tl">L13</span><span class="tt">physics-in<b>to a s</b></span></div><div class="tc"><span class="tl">L14</span><span class="tt">uncerta<b>inty</b></span></div><div class="tc"><span class="tl">L15</span><span class="tt">Bayesian opti<b>mization</b></span></div><div class="tc"><span class="tl">L16</span><span class="tt">distribu<b>tion</b></span></div></div>

<div class="small" data-marpit-fragment>

- **15 of 16 right:** it learned our spelling and our vocabulary. The miss: "physics-in" → "to a s", because "into a" appears 58 times in our notes and "physics-informed" only 8

* **No sentences with meaning:** ask for one and it writes "and the same step of the same samples". Meaning takes far more parameters and data, next

</div>

---

<!-- _class: section -->

# Data and scale

---

## Data and scale, models over the years

<div class="readbox smaller">

- **What you see:** language models by year and size (log scale: each labeled line is 1,000 times the one below). Press play. Closed models (GPT-4 to GPT-6, Claude) publish no size: the strip at the top

</div>

<div class="cw compact" data-widget="llm-sizes" data-source="l17"><img src="figures/widget-llm-sizes.png" alt="Parameters of language models against release year, with closed models on a strip"></div>

<p class="source">Sizes from each model's paper or card: <a href="https://cdn.openai.com/better-language-models/language_models_are_unsupervised_multitask_learners.pdf">GPT-1, GPT-2</a> · <a href="https://arxiv.org/abs/2005.14165">GPT-3</a> · <a href="https://arxiv.org/abs/2112.11446">Gopher</a> · <a href="https://arxiv.org/abs/2203.15556">Chinchilla</a> · <a href="https://arxiv.org/abs/2204.02311">PaLM</a> · <a href="https://arxiv.org/abs/2307.09288">Llama 2</a> · <a href="https://arxiv.org/abs/2407.21783">Llama 3.1</a> · <a href="https://arxiv.org/abs/2412.19437">DeepSeek-V3</a> · <a href="https://arxiv.org/abs/2507.20534">Kimi K2</a> · <a href="https://api-docs.deepseek.com/news/news260424">DeepSeek-V4</a> · <a href="https://huggingface.co/moonshotai/Kimi-K3">Kimi K3</a>. No size given: <a href="https://arxiv.org/abs/2303.08774">GPT-4</a> · <a href="https://openai.com/index/gpt-6-astra/">GPT-6 Astra</a> · <a href="https://www.anthropic.com/news/claude-3-family">Claude 3</a> · <a href="https://www.anthropic.com/claude-opus-5-5">Claude Opus 5.5</a>.</p>

<!--
The GPT-4 technical report "contains no further details about the architecture (including model size)". Anthropic's model cards give no parameter counts. The mixture-of-experts models (DeepSeek, Kimi) only use a fraction of their parameters for each token: the hollow dots.
-->

---

## Data and scale, in human terms

<div class="cards four" style="margin-top: 0.6em;">
<div class="card" data-marpit-fragment><h4>Their data</h4><p>Mostly filtered web text, plus books, code and papers. Llama 3: "about 15T multilingual tokens"</p></div>
<div class="card" data-marpit-fragment><h4>Our data</h4><p>The notes of Lectures 1 to 16: 668,651 characters, each seen about 27 times in 2,000 steps</p></div>
<div class="card" data-marpit-fragment><h4>Reading it</h4><p>Our notes: about <b>7 hours</b> at 250 words a minute. GPT-3's training text: <b>about 1,300 years</b>, non-stop</p></div>
<div class="card" data-marpit-fragment><h4>Computing it</h4><p>Our tiny GPT needed about 8 × 10¹³ operations: 2 minutes on a laptop GPU (about 700 billion a second), but <b>23 hours</b> at a billion a second. GPT-3 needed 3.14 × 10²³: <b>about 10 million years</b> at a billion a second</p></div>
</div>

<!--
GPT-3's reading time uses our notes' 0.58 words per GPT-2 token (GPT-3 uses the same vocabulary) for its 300 billion tokens. GPT-3's compute is Table D.1 of Brown et al. (2020); ours is about 6 operations per parameter per token, 6 × 842,881 × 16.4 million. Same objective and same kind of model: Llama 3 has about 500,000 times the parameters of ours.
-->

---

## Data and scale, after pretraining

<div class="stages">
<div class="st"><div class="sh">1. Pretraining</div><div class="sd">Learns to <b>continue</b> text, from trillions of tokens</div><div class="sx">"What is the boiling point of water?" → "The boiling point of water is the point at which the water boils. …"</div></div>
<div class="sa" data-marpit-fragment>→</div>
<div class="st" data-marpit-fragment><div class="sh">2. SFT</div><div class="sd"><b>Supervised fine-tuning</b>: more training on examples of good answers, written by people</div></div>
<div class="sa" data-marpit-fragment>→</div>
<div class="st" data-marpit-fragment><div class="sh">3. RLHF or DPO</div><div class="sd">People pick the better of two answers, and the model learns their preference: by <b>reinforcement learning from human feedback</b> (RLHF) or <b>direct preference optimization</b> (DPO)</div></div>
<div class="sa" data-marpit-fragment>→</div>
<div class="st dark" data-marpit-fragment><div class="sh">Result: a chat model</div><div class="sd">The same network, now <b>answering</b></div><div class="sx">"In one sentence, what does a heat exchanger do?" → "A heat exchanger transfers heat from one medium to another."</div></div>
</div>

<p class="source" data-marpit-fragment>Still how it is done: each round of Llama 3's post-training was SFT, then DPO (<a href="https://arxiv.org/abs/2407.21783">Llama Team, 2024</a>). InstructGPT "hired a team of about 40 contractors" to write and rank answers (<a href="https://arxiv.org/abs/2203.02155">Ouyang et al., 2022</a>). Examples: GPT-2, a pretrained model, and Qwen2.5-0.5B-Instruct, a chat model, both run by us.</p>

---

<!-- _class: section -->

# Sampling

---

## Sampling, temperature

<div class="definition small">

**Temperature**: a knob for how adventurous the model is when it picks the next token.

**Low**: it almost always takes the most likely token.

**High**: less likely tokens get a real chance.

</div>

<div class="cols cols-even cols-top">
<div>

<div class="eqrow">
<div>

$p_\tau(v) = \mathrm{softmax}\Big($

</div>
<div class="term t-tz">

$z$

</div>
<div>

$/$

</div>
<div class="term t-tt">

$\tau$

</div>
<div>

$\Big)_v$

</div>
</div>

<div class="cards tight2">
<div class="card c-tz" data-marpit-fragment><h4>z: the logits</h4><p>The model's raw score for each token, before the softmax turns them into probabilities</p></div>
<div class="card c-tt" data-marpit-fragment><h4>τ (tau): the temperature</h4><p>Divide every logit by τ, then softmax. τ = 1: the model's own probabilities</p></div>
</div>

<div class="example" data-marpit-fragment>

**Two logits, 2 and 1.** τ = 1: 73% and 27%. τ = 0.5 doubles the gap: 88% and 12%. τ = 2 halves it: 62% and 38%.

</div>



</div>
<div data-marpit-fragment>

![w:520](figures/temperature.png)

<p class="smaller center">We ran GPT-2 on "…the water was too": "␣hot" gets <b>88%</b> at τ = 0.5, <b>42%</b> at τ = 1, <b>4%</b> at τ = 2.</p>

<p class="source">"Using a higher value for T produces a softer probability distribution over classes" (<a href="https://arxiv.org/abs/1503.02531">Hinton, Vinyals and Dean, 2015</a>).</p>

</div>
</div>

---

## Sampling, spin the wheel

<div class="cols cols-side cols-top">
<div class="cw compact" data-widget="llm-wheel" data-source="l17"><img src="figures/widget-llm-wheel.png" alt="A wheel with one slice per next token, sized by its probability at the chosen temperature"></div>
<div class="small">

<div class="readbox bgold">

**What you see:** GPT-2's next token after "…the water was too" as a wheel, one slice per token. Picking a token is a spin. Change τ, then spin

</div>

<div class="readbox" data-marpit-fragment>

**τ changes the wheel, the spin stays fair:** at τ = 0.5 "␣hot" takes 88% of it; at τ = 2, only 4%

</div>

<div class="readbox bred" data-marpit-fragment>

**Why "temperature":** the softmax is Boltzmann's distribution from thermodynamics.

$$p(\text{token } v) = \frac{e^{z_v/\tau}}{\sum_u e^{z_u/\tau}} \qquad p(\text{state } i) = \frac{e^{-E_i/k_BT}}{\sum_j e^{-E_j/k_BT}}$$

A logit $z$ plays minus an energy, and $\tau$ plays $k_BT$. Hot: every state gets visited. Cold: the lowest energy wins

<p class="source">"In statistical mechanics, the softmax function is known as the Boltzmann distribution" (<a href="https://en.wikipedia.org/wiki/Softmax_function">Wikipedia</a>, after <a href="http://yann.lecun.com/exdb/publis/pdf/lecun-06.pdf">LeCun et al., 2006</a>).</p>

</div>

</div>
</div>

<!--
For chemical engineers this is exactly the Boltzmann distribution, with the logit as minus an energy in units of k_B T.
-->

---

## Sampling, the loop with a temperature knob

<div class="cols cols-side cols-top">
<div class="cw compact" data-widget="llm-sample" data-source="l17"><img src="figures/widget-llm-sample.png" alt="GPT-2 next-token probabilities along a greedy continuation, with a temperature slider"></div>
<div class="small">

<div class="readbox bgold">

**What you see:** GPT-2's ten most likely next tokens at each step of the loop. Red: the one appended. Step through, then move τ

</div>

<div class="readbox">

**τ = 1:** GPT-2's own probabilities. At step 1, "␣water" gets 3.7%: many words could follow

</div>

<div class="readbox bgreen" data-marpit-fragment>

**Slide τ to 0.1:** "␣water" jumps to **89%**. Low temperature: nearly the same text every time

</div>

<div class="readbox bred" data-marpit-fragment>

**Slide τ to 2:** every bar flattens. At step 4, even "␣hot" falls to 4%: almost anything can come next

</div>

</div>
</div>

---

## Sampling, our tiny GPT at three temperatures

<div class="samples">
<div><h4>τ = 0.3</h4><pre>A Gaussian process in the data and a different statistical models.&#10;### A file section and layers&#10;A **fitted of stead of a column store and a strain of the same data is the same offf the same way th …</pre><p>Safe and repetitive: "the same … the same …", and a Markdown heading copied from our notes</p></div>
<div data-marpit-fragment><h4>τ = 0.8</h4><pre>A Gaussian process and the default does not exact the band file coefficients the wide, vector plant. The discipline for a strong by an Lecture 9.&#10;The log quantition and can we course at have you been …</pre><p>Varied words in our style, with no meaning</p></div>
<div data-marpit-fragment><h4>τ = 1.5</h4><pre>A Gaussian process cructor arNive,&quot; and a brieful mini-bassed flrecash uncaged defaularing most-is carryied outue: chan `y[desy&#x27;&#x27;](h✓dds#p.01├x, lipproduce.&#10;- [Slagáni lipyndbof/Jagimaus.ipynb) answer …</pre><p>Broken words and rare symbols (✓, ├): the tail of the distribution</p></div>
</div>

<p class="takeaway" data-marpit-fragment>All three start from the same prompt, "A Gaussian process", and the same model. Only τ changed.</p>

---

<!-- _class: definition -->

## Hallucination

**Hallucination**: fluent, confident text that is false: an invented number, unit, citation or fact.

<div data-marpit-fragment>
<div class="chips">

<span class="ctx">What is the boiling point of water at sea level?</span><span class="g">The boiling point of water at sea level is 100 degrees Fahrenheit.</span>

</div>
<div class="vs"><div class="vh">After "…100 degrees", the next token:</div><div class="vrow pick"><span>␣Fahrenheit</span><i style="width:100%"></i><em>58.6%</em></div><div class="vrow"><span>␣Celsius</span><i style="width:70%"></i><em>40.8%</em></div><div class="vrow"><span>␣F</span><i style="width:0%"></i><em>0.3%</em></div></div>
</div>

<div class="small">

- **What happened:** we ran a chat model on a laptop (Qwen2.5-0.5B-Instruct, 0.49 billion parameters, trained on 18 trillion tokens) and asked. It got the number right and the unit wrong: after "…100 degrees" it gave Fahrenheit 58.6% and Celsius 40.8%, and took the more likely one

* **Why:** the training loss rewards the likely next token. Nothing in it checks whether a sentence is true
* **So:** treat every number and unit from an LLM as unchecked. Check it against a measurement, a handbook or a calculation

</div>

---

## Limitations and trade-offs

<div class="fix">
<div class="hd">What goes wrong</div><div class="hd">What to do</div>
<div class="bad"><b>Invents sources and packages.</b> 5.2% of packages in GPT models' code do not exist; 21.7% for open models (<a href="https://arxiv.org/abs/2406.10279">Spracklen et al., 2025</a>)</div><div class="good">Check that each source and package exists before you cite or install it</div>
<div class="bad" data-marpit-fragment><b>Coding agents act on their guesses:</b> they edit files, install packages and run commands</div><div class="good" data-marpit-fragment>Review the diff and run the tests before you merge; keep secrets out of reach</div>
<div class="bad" data-marpit-fragment><b>Knows only its training data:</b> nothing after its cutoff date, nothing about your plant</div><div class="good" data-marpit-fragment>Put the documents it needs in the prompt. Do not ask it for current values</div>
<div class="bad" data-marpit-fragment><b>Long inputs:</b> answers get worse as inputs grow, well inside the advertised window (<a href="https://arxiv.org/abs/2404.06654">Hsieh et al., 2024</a>; <a href="https://arxiv.org/abs/2510.05381">Du et al., 2025</a>)</div><div class="good" data-marpit-fragment>Send only what matters: retrieve the relevant parts, ask it to quote its evidence, repeat the main instructions</div>
<div class="bad" data-marpit-fragment><b>Numbers and units:</b> it reads 4140 as two text pieces, "414" and "0", never as a quantity</div><div class="good" data-marpit-fragment>Do arithmetic and unit conversions in code</div>
<div class="bad" data-marpit-fragment><b>Not reproducible:</b> the same prompt can give another answer, even at temperature 0</div><div class="good" data-marpit-fragment>Save the output you used, with the model's name and the date</div>
<div class="bad" data-marpit-fragment><b>Your prompt leaves your machine</b> for the provider's servers</div><div class="good" data-marpit-fragment>Check your company's rules first, or run an open model locally</div>
</div>

<!--
The first two rows go together: an agent that installs what it writes can install a package an attacker registered under a hallucinated name (Spracklen et al. describe this attack).
-->

---

## Recap

<div class="pipeline">
<div class="pnode"><b>Text</b><div class="pv q">"The pump stopped"</div></div><div class="parr">→</div>
<div class="pnode" data-marpit-fragment><b>Tokens</b><div class="pv"><span class="tk" style="background:rgba(31,111,178,.18)">The</span> <span class="tk" style="background:rgba(194,65,12,.18)">␣pump</span> <span class="tk" style="background:rgba(43,138,62,.2)">␣stopped</span></div></div><div class="parr" data-marpit-fragment>→</div>
<div class="pnode" data-marpit-fragment><b>Transformer</b><img src="figures/look-back.png" alt="Attention looking back"></div><div class="parr" data-marpit-fragment>→</div>
<div class="pnode" data-marpit-fragment><b>Next-token probabilities</b><div class="pv bars"><div><span>␣water</span><i style="width:74%"></i></div><div><span>␣pump</span><i style="width:59%"></i></div><div><span>␣gas</span><i style="width:44%"></i></div></div></div><div class="parr" data-marpit-fragment>→</div>
<div class="pnode dark" data-marpit-fragment><b>Sample, append, repeat</b><div class="pv"><span class="tk g2">␣water</span> <span class="tk g2">␣was</span> …</div><div class="pv">temperature τ</div></div>
</div>

<div class="tiles four">
<div class="tile" data-marpit-fragment>

#### A generative model of text

$p(x_1, \dots, x_T) = \prod_t p(x_t \mid x_{<t})$

One token at a time, like Lecture 8's recursive forecast

</div>
<div class="tile" data-marpit-fragment>

#### Trained by

$\min_\theta\, -\frac{1}{T}\sum_t \log p_\theta(x_{t+1} \mid x_{\le t})$

<img src="figures/tiny-loss.png" alt="The loss falling">

</div>
<div class="tile" data-marpit-fragment>

#### At scale

<img src="figures/scale.png" alt="Parameters against training tokens">

Billions of parameters, trillions of tokens

</div>
<div class="tile" data-marpit-fragment>

#### Fluent is not true

<span class="tk g2">␣about 1,000 degrees Fahrenheit</span>

GPT-2 on water's boiling point (true: 212 °F). Check every number that matters

</div>
</div>

---

## Resources

<div class="thanks">
<div class="tk-h">With thanks to 3Blue1Brown</div>
<p>This lecture is built on Grant Sanderson's lessons on large language models, the clearest visual explanation of them we know. The chatbot as a script it completes, training as tuning dials, vectors that talk to each other and the temperature knob all come from there. Watch them before anything else on this slide.</p>
<p><a href="https://www.3blue1brown.com/lessons/mini-llm/">Large Language Models explained briefly</a> (8 min) · <a href="https://www.3blue1brown.com/lessons/gpt/">Transformers, the tech behind LLMs</a> · <a href="https://www.youtube.com/watch?v=eMlx5fFNoYc">Attention in transformers</a> · <a href="https://www.youtube.com/watch?v=9-Jl0dxWQs8">How might LLMs store facts</a></p>
</div>

<div class="cards">
<div class="card" data-marpit-fragment><h4>Watch</h4><p><a href="https://www.youtube.com/watch?v=zjkBMFhNj_g">Karpathy, Intro to LLMs</a> (1 h)</p><p><a href="https://www.youtube.com/watch?v=kCc8FmEb1nY">Karpathy, Let's build GPT</a> (2 h)</p></div>
<div class="card" data-marpit-fragment><h4>Play</h4><p><a href="https://poloclub.github.io/transformer-explainer/">Transformer Explainer</a>: GPT-2 in your browser</p><p><a href="https://bbycroft.net/llm">LLM Visualization</a>: every computation, in 3D</p><p><a href="https://tiktokenizer.vercel.app/">Tiktokenizer</a>: see your text as tokens</p></div>
<div class="card" data-marpit-fragment><h4>Read</h4><p><a href="https://jalammar.github.io/illustrated-gpt2/">The Illustrated GPT-2</a></p><p><a href="https://web.stanford.edu/~jurafsky/slp3/">Jurafsky and Martin, SLP3</a>, Chapters 2, 7, 8</p><p><a href="https://huggingface.co/learn/llm-course/chapter1/1">Hugging Face LLM Course</a></p></div>
</div>

---

## Before next time

- **Final project**: released today. Team agreement due Friday 10-30, proposal due Wednesday 11-04
- **Practice module** for this session, for participation credit

<script src="l17-widget-data.js"></script>
<script src="widgets.js"></script>
