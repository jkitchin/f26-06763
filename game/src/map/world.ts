/**
 * The map world: types over the generated `world.json`, and the queries the
 * renderer needs.
 *
 * Nothing here decides where anything goes. `tools/world.py` builds the layout
 * from `course/schedule.md`, the arcs the notes declare, and the corridors
 * `tools/graph.py` verified, and CI fails if the committed JSON drifts from any
 * of the three. This file is the typed reader for that, and the place the
 * walking rules live.
 *
 * WHY THE MAP IS A VIEW AND NOT A REPLACEMENT. The list at `#/` stays exactly as
 * it is. The quiz is keyboard-first by design and every control carries a label,
 * and a sprite you drive with arrow keys is a poor substitute for that if you
 * are using a screen reader or simply prefer a list. Both read the same log, so
 * there is no second source of truth and no progress that exists in one view and
 * not the other.
 */

// The import attribute is required by node, which runs tests/map.ts directly
// with --experimental-strip-types. Vite and tsc both accept it.
import raw from './world.json' with { type: 'json' }

export interface Room {
  id: string
  /** The label used in the schedule: `L7`, `MP-1`. */
  session: string
  title: string
  date: string
  /** False for the twelve sessions with no notes yet. Drawn as a shutter. */
  written: boolean
  /** Whether the arc came from the lecture's own notes or from the one before. */
  arc_source: 'declared' | 'inherited'
  arc: string
  region: number
  x: number
  y: number
  /** Relative URL of the notes, or null for a shutter. */
  notes: string | null
}

export interface Door {
  from: string
  to: string
  /** `link` was extracted from a markdown cross-link; `authored` was written
   *  by hand in game/content/map-edges.yml with a cited sentence. */
  origin: 'link' | 'authored'
  relation: string | null
  why: string | null
  /** The sentence that created this corridor. Shown, because a corridor you
   *  cannot justify is exactly what the authored edges exist to avoid. */
  where: string
}

export interface Region {
  name: string
  x0: number
  rows: number
  rooms: string[]
}

export interface Sign {
  lecture: string
  promised_by: string
  where: string
}

export interface World {
  grid: { width: number; height: number; cols_per_region: number }
  spawn: { x: number; y: number }
  regions: Region[]
  rooms: Room[]
  doors: Door[]
  signs: Sign[]
}

export const world = raw as unknown as World

const byId = new Map(world.rooms.map((r) => [r.id, r]))
const byCell = new Map(world.rooms.map((r) => [`${r.x},${r.y}`, r]))

export const roomById = (id: string): Room | undefined => byId.get(id)
export const roomAt = (x: number, y: number): Room | undefined => byCell.get(`${x},${y}`)

/** Corridors touching a room, in either direction, with the far end resolved. */
export function doorsOf(id: string): { door: Door; other: Room; outbound: boolean }[] {
  return world.doors
    .filter((d) => d.from === id || d.to === id)
    .map((d) => {
      const outbound = d.from === id
      return { door: d, other: byId.get(outbound ? d.to : d.from)!, outbound }
    })
    .filter((d) => d.other !== undefined)
}

/** The sign on a shutter, if some lecture already promises it. */
export const signFor = (id: string): Sign | undefined =>
  world.signs.find((s) => s.lecture === id)

/**
 * Where a step lands.
 *
 * Movement is by whole cells and the whole grid is walkable, so there is no
 * collision to write and nothing to get stuck in. Nothing on this map is locked
 * behind a prerequisite on purpose: a student arriving in week 12 must not be
 * walled out of L23 because they skipped L9. What the map withholds is
 * structure, not access. Corridors appear once you have stood at both ends, so
 * exploring reveals how the course fits together rather than unlocking it.
 */
export function step(
  at: { x: number; y: number },
  dx: number,
  dy: number,
): { x: number; y: number } {
  return {
    x: Math.min(Math.max(at.x + dx, 0), world.grid.width - 1),
    y: Math.min(Math.max(at.y + dy, 0), world.grid.height - 1),
  }
}

/** A corridor is drawn once both of its rooms have been stood in. */
export const doorVisible = (d: Door, visited: ReadonlySet<string>): boolean =>
  visited.has(d.from) && visited.has(d.to)

/** How much of the map has been walked, for the one number worth showing. */
export function coverage(visited: ReadonlySet<string>): { seen: number; total: number } {
  return { seen: world.rooms.filter((r) => visited.has(r.id)).length, total: world.rooms.length }
}
