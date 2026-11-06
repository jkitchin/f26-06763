/** The knowledge graph's data and layouts. Run with `npm run knowledge`. */

import assert from 'node:assert/strict'
import { world } from '../src/map/world.ts'
import { knowledge, lectureById } from '../src/map/knowledge.ts'
import { lectureGraph, settle, topicGraph, type GNode } from '../src/map/layout.ts'

let fails = 0
const check = (ok: boolean, label: string, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? `  ${detail}` : ''}`)
  if (!ok) fails++
}

console.log('knowledge:')

// --- the data agrees with the walkable map ------------------------------------

const sessions = world.rooms.filter((r) => r.kind === 'session').map((r) => r.id).sort()
const lectures = knowledge.lectures.map((l) => l.id).sort()
check(JSON.stringify(sessions) === JSON.stringify(lectures),
  'the graph has exactly the sessions the walkable map has', lectures.join(','))
check(knowledge.lectures.every((l) => l.released === world.rooms.find((r) => r.id === l.id)?.written),
  'and opens or shuts each one by the same _toc.yml rule')

// An unreleased lecture is public as a title only: the site ships one lecture at
// a time, and nothing in the bundle may show the content of one not out yet.
const shut = knowledge.lectures.filter((l) => !l.released)
check(shut.every((l) => !l.takeaways && !l.objectives && !l.notes && !l.themes),
  'an unreleased lecture carries no takeaways, objectives or links',
  shut.map((l) => l.id).join(',') || '(none unreleased)')
check(knowledge.concepts.every((c) => lectureById(c.lecture)?.released),
  'every concept comes from a released lecture')
check(knowledge.edges.every((e) => lectureById(e.from)?.released && lectureById(e.to)),
  'every link quotes a released lecture and points at a session on the map')
check(knowledge.themes.every((t) => t.lectures.length > 0 && t.lectures.every((l) => lectureById(l)?.released)),
  'every theme shown has released lectures, and only those')

const released = knowledge.lectures.filter((l) => l.released)
check(released.every((l) => (l.takeaways?.length ?? 0) > 0), 'every released lecture has a takeaway')
check(released.every((l) => l.themes?.includes(l.theme)), 'and belongs to its own primary theme')

const themeIds = new Set(knowledge.themes.map((t) => t.id))
check(knowledge.concepts.every((c) => themeIds.has(c.theme)), 'every concept sits in a theme that is shown')
check(knowledge.concepts.every((c) => c.href.startsWith(`../lectures/${c.lecture}/notes.html`)),
  'every concept links to the notes that define it')

// --- the system figure --------------------------------------------------------

const [W, H] = knowledge.system.canvas
const area = knowledge.system.boxes.reduce((s, b) => s + b.w * b.h, 0)
check(area === W * H, 'the system boxes tile the canvas exactly, so the areas compare honestly',
  `${area} of ${W * H}`)
const ml = knowledge.system.boxes.find((b) => b.id === 'ml')
check(ml !== undefined && Math.abs((ml.w * ml.h) / area - 0.0365) < 0.001,
  'and ML code is the 3.7% of it that Lecture 1 says it is')
check(knowledge.system.boxes.every((b) => b.lectures.every((l) => lectureById(l)?.released)),
  'every lecture a box names is released')

// --- the layouts settle -------------------------------------------------------

function finite(nodes: GNode[]) {
  return nodes.every((n) => Number.isFinite(n.x) && Number.isFinite(n.y))
}

const lg = lectureGraph()
settle(lg)
check(finite(lg.nodes), 'the lecture graph settles to finite positions')
let overlap = 0
for (let i = 0; i < lg.nodes.length; i++) {
  for (let j = i + 1; j < lg.nodes.length; j++) {
    const a = lg.nodes[i]!, b = lg.nodes[j]!
    if (Math.hypot(a.x! - b.x!, a.y! - b.y!) < a.r + b.r) overlap++
  }
}
check(overlap === 0, 'with no two lectures on top of each other', `${overlap} overlaps`)
const centre = lg.nodes.find((n) => n.slot < 0)
check(!centre || (centre.x === 0 && centre.y === 0), 'and the wrap-up lecture at the centre')

const tg = topicGraph()
settle(tg)
check(finite(tg.nodes), 'the topic graph settles to finite positions',
  `${tg.nodes.length} nodes`)
const suns = tg.nodes.filter((n) => n.kind === 'theme')
let close = 0
for (let i = 0; i < suns.length; i++) {
  for (let j = i + 1; j < suns.length; j++) {
    const a = suns[i]!, b = suns[j]!
    if (Math.hypot(a.x! - b.x!, a.y! - b.y!) < a.r + b.r + 20) close++
  }
}
check(close === 0, 'with no two themes on top of each other', `${close} too close`)

assert.equal(fails, 0, `${fails} failed`)
console.log('\nall checks passed')
