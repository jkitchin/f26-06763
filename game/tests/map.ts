/** The map world and its walking rules. Run with `npm run map`. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  coverage, doorsOf, doorVisible, roomAt, roomById, signFor, step, world,
} from '../src/map/world.ts'
import {
  completedFor, firstVisits, levelFor, sessionsOf, visitedRooms,
  type Event,
} from '../src/store/log.ts'

let fails = 0
const check = (ok: boolean, label: string, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? `  ${detail}` : ''}`)
  if (!ok) fails++
}

console.log('map:')

// --- the generated world holds together ------------------------------------

check(world.rooms.length === 22, 'every session on the schedule is a room',
  `${world.rooms.length} rooms`)
// The written (open) rooms are exactly the lectures released in _toc.yml. The
// course ships one week at a time, so this set grows week by week; the test
// derives it from _toc.yml rather than hard-coding a count a release would break.
// (L18 keeps its notes and bank stub but has no schedule row now that it is
// folded into L17, so it is never a room and never released.)
const toc = readFileSync(new URL('../../_toc.yml', import.meta.url), 'utf8')
const releasedIds = new Set(
  [...toc.matchAll(/^\s*-\s*file:\s*lectures\/(l\d\d)\/notes/gm)].map((m) => m[1]))
const writtenIds = world.rooms.filter((r) => r.written).map((r) => r.id).sort()
const expectedWritten = world.rooms
  .filter((r) => releasedIds.has(r.id)).map((r) => r.id).sort()
check(JSON.stringify(writtenIds) === JSON.stringify(expectedWritten),
  'written rooms are exactly the lectures released in _toc.yml',
  `written: ${writtenIds.join(',') || '(none)'}`)

// Two rows carry a conference annotation in the schedule that an earlier parser
// silently dropped. The annotation belongs to the dates rather than the lectures,
// so dropping the mini-project days moved it from L18/L19 onto L21/L22. L21
// anchors authored corridors, so losing it would have left edges pointing out of
// a room that was not drawn.
for (const id of ['l21', 'l22']) {
  check(roomById(id) !== undefined, `${id} survived the schedule parse`)
}

const cells = new Set(world.rooms.map((r) => `${r.x},${r.y}`))
check(cells.size === world.rooms.length, 'no two rooms occupy the same cell',
  `${cells.size} cells for ${world.rooms.length} rooms`)

check(
  world.rooms.every((r) => r.x >= 0 && r.x < world.grid.width &&
                           r.y >= 0 && r.y < world.grid.height),
  'every room is inside the grid',
)

check(roomAt(world.spawn.x, world.spawn.y) === undefined,
  'the student spawns outside a room and walks in')

const ids = new Set(world.rooms.map((r) => r.id))
check(world.doors.every((d) => ids.has(d.from) && ids.has(d.to)),
  'every corridor connects two rooms that exist')
check(world.doors.every((d) => d.from !== d.to), 'no corridor loops back on itself')
check(world.signs.every((s) => roomById(s.lecture)?.written === false),
  'every signed shutter names a room that is genuinely unwritten')

// A corridor drawn out of L17 would contradict the finding that it cites
// nothing. See game/content/map-edges.yml.
check(!world.doors.some((d) => d.from === 'l17'), 'L17 is still the dead end')

// Ten, not the fifteen this asserted before: L23's five authored edges left with
// the lecture when MLOps moved to course/optional/. The count is hardcoded on
// purpose. Authored edges are hand-written content, each with the sentence that
// justifies it, and a regeneration that silently dropped some would otherwise
// look like a clean run.
const authored = world.doors.filter((d) => d.origin === 'authored')
check(authored.length === 10, 'the ten authored corridors made it through',
  `${authored.length}`)
check(authored.every((d) => d.why !== null && d.relation !== null),
  'and each carries the relation and the reason it exists')

// --- walking ---------------------------------------------------------------

check(step({ x: 3, y: 3 }, 1, 0).x === 4, 'a step moves one cell')
check(step({ x: 0, y: 0 }, -1, -1).x === 0 && step({ x: 0, y: 0 }, -1, -1).y === 0,
  'walking off the top-left edge stays put')
const far = { x: world.grid.width - 1, y: world.grid.height - 1 }
check(step(far, 1, 1).x === far.x && step(far, 1, 1).y === far.y,
  'and off the bottom-right edge too')

// Every room has to be walkable to from spawn, or the map has a room nobody can
// reach. Flood fill rather than assertion by inspection.
const seenCells = new Set<string>()
const queue = [world.spawn]
while (queue.length) {
  const p = queue.pop()!
  const k = `${p.x},${p.y}`
  if (seenCells.has(k)) continue
  seenCells.add(k)
  for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]] as const) {
    const n = step(p, dx, dy)
    if (!seenCells.has(`${n.x},${n.y}`)) queue.push(n)
  }
}
check(world.rooms.every((r) => seenCells.has(`${r.x},${r.y}`)),
  'every room is reachable on foot from spawn',
  `${seenCells.size} cells reachable`)

// --- what the map reveals --------------------------------------------------

const l21 = doorsOf('l21')
check(l21.length >= 5, 'standing in L21 shows what it builds on', `${l21.length} corridors`)
check(l21.some((d) => d.other.id === 'l13' && d.outbound),
  'including the strongest claim in the back half, L21 -> L13')

const none = new Set<string>()
const both = new Set(['l21', 'l13'])
const oneDoor = world.doors.find((d) => d.from === 'l21' && d.to === 'l13')!
check(!doorVisible(oneDoor, none), 'a corridor is hidden until both ends are visited')
check(!doorVisible(oneDoor, new Set(['l21'])), 'one end is not enough')
check(doorVisible(oneDoor, both), 'and drawn once both have been')

check(coverage(none).seen === 0 && coverage(none).total === 22, 'coverage starts at zero of 22')
check(coverage(both).seen === 2, 'and counts the rooms actually stood in')

// Shuttered rooms no longer carry a promise sign: the promises were forward
// references from earlier lectures, and the course no longer makes any.
check(signFor('l20') === undefined, 'a shuttered room carries no promise sign')
check(signFor('l01') === undefined, 'a written room has no shutter sign')

// --- visits are inert to everything that grades ----------------------------
//
// The whole point of adding an event kind to a shared log. Every derivation
// identifies its own events positively, so a new kind cannot be miscounted; a
// derivation written as "anything that is not an opened event" would have
// counted these as answered items and handed out credit for walking around.

const visits: Event[] = [
  { t: 'visited', room: 'l01', at: 10 },
  { t: 'visited', room: 'l21', at: 20 },
  { t: 'visited', room: 'l01', at: 30 },
]
check(sessionsOf(visits).length === 0, 'visits create no sittings')
check(levelFor(visits, 'l01') === 0, 'and no mastery level')
check(completedFor(visits, 'l01').length === 0, 'and no completed modules')

check(visitedRooms(visits).size === 2, 'a room visited twice is still one room')
check(firstVisits(visits).get('l01') === 10, 'and the first visit is the one recorded')

assert.equal(fails, 0, `${fails} failed`)
console.log('\nall checks passed')
