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

const sessionRooms = world.rooms.filter((r) => r.kind === 'session')
// 20: the schedule has 22 lecture rows. L20 is cancelled and L21 has no topic, so
// neither has a room.
check(sessionRooms.length === 20, 'every session on the schedule with a topic is a room',
  `${sessionRooms.length} rooms`)
check(roomById('l21') === undefined, 'L21, which has no topic, is not drawn')
check(roomById('l20') === undefined, 'L20, which is cancelled, is not drawn')

// The written (open) rooms are exactly the lectures released in _toc.yml. The
// course ships one week at a time, so this set grows week by week; the test
// derives it from _toc.yml rather than hard-coding a count a release would break.
// (L18 keeps its notes and bank stub but has no schedule row now that it is
// folded into L17, so it is never a room and never released.)
const toc = readFileSync(new URL('../../_toc.yml', import.meta.url), 'utf8')
const releasedIds = new Set(
  [...toc.matchAll(/^\s*-\s*file:\s*lectures\/(l\d\d)\/notes/gm)].map((m) => m[1]))
// Pages are released the same way, by an uncommented _toc.yml entry.
const PAGES: Record<string, string> = { built: 'course/optional/how-this-course-was-built' }
const pageListed = (id: string) =>
  new RegExp(`^\\s*-\\s*file:\\s*${PAGES[id]}\\s*$`, 'm').test(toc)

// The optional page gets a room only once it is published in _toc.yml, and then
// it sits in an Optional region of its own, with no date.
const built = roomById('built')
if (pageListed('built')) {
  check(built?.kind === 'page' && built.arc === 'Optional' && built.date === '',
    'the published optional page is a room in the Optional region, with no date')
  check(world.regions.filter((g) => g.name === 'Optional').length === 1,
    'and there is one Optional region')
} else {
  check(built === undefined, 'the unpublished optional page has no room')
  check(world.regions.every((g) => g.name !== 'Optional'), 'and there is no Optional region')
}
const writtenIds = world.rooms.filter((r) => r.written).map((r) => r.id).sort()
const expectedWritten = world.rooms
  .filter((r) => (r.kind === 'page' ? pageListed(r.id) : releasedIds.has(r.id)))
  .map((r) => r.id).sort()
check(JSON.stringify(writtenIds) === JSON.stringify(expectedWritten),
  'written rooms are exactly the lectures released in _toc.yml',
  `written: ${writtenIds.join(',') || '(none)'}`)

// Two rows carry a conference annotation in the schedule that an earlier parser
// silently dropped. The annotation belongs to the dates rather than the lectures,
// so dropping the mini-project days moved it from L18/L19 onto L21/L22. L21
// anchors authored corridors, so losing it would have left edges pointing out of
// a room that was not drawn.
check(roomById('l22') !== undefined, 'l22 survived the schedule parse')

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

// L19 was the dead end while it was the RAG lecture, which cited nothing. Rewritten as the
// agents lecture (2026-11-03), it opens from L18's single tool call, and its notes link L18.
check(world.doors.some((d) => d.from === 'l19' && d.to === 'l18'), 'L19 builds on L18')

// None drawn. The four authored edges all leave L21, which has no room while it
// has no topic; they stay in game/content/map-edges.yml and return with it. The
// count is hardcoded on purpose: authored edges are hand-written content, and a
// regeneration that silently changed them would otherwise look like a clean run.
const authored = world.doors.filter((d) => d.origin === 'authored')
check(authored.length === 0, 'no authored corridor is drawn while L21 has no room',
  `${authored.length}`)

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

const l11 = doorsOf('l11')
check(l11.length >= 4, 'standing in L11 shows what it connects to', `${l11.length} corridors`)
check(l11.some((d) => d.other.id === 'l09' && d.outbound), 'including L11 -> L9')

const none = new Set<string>()
const both = new Set(['l11', 'l09'])
const oneDoor = world.doors.find((d) => d.from === 'l11' && d.to === 'l09')!
check(!doorVisible(oneDoor, none), 'a corridor is hidden until both ends are visited')
check(!doorVisible(oneDoor, new Set(['l11'])), 'one end is not enough')
check(doorVisible(oneDoor, both), 'and drawn once both have been')

// 20 sessions with a topic, plus the optional page once it is published.
const roomsTotal = 20 + (pageListed('built') ? 1 : 0)
check(coverage(none).seen === 0 && coverage(none).total === roomsTotal,
  `coverage starts at zero of ${roomsTotal}`)
check(coverage(both).seen === 2, 'and counts the rooms actually stood in')

// Shuttered rooms no longer carry a promise sign: the promises were forward
// references from earlier lectures, and the course no longer makes any.
check(signFor('l22') === undefined, 'a shuttered room carries no promise sign')
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
