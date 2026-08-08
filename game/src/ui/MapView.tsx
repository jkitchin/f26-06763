/**
 * The course as a place you walk around.
 *
 * WHY A MAP AT ALL. The list at `#/` is fourteen modules in a column, and it
 * tells a student nothing about why L11 assumes L9 or why L23 keeps citing L21.
 * That structure exists, in 34 verified cross-references, and it is not visible
 * anywhere else in the course. The landing page already tells students that when
 * they remember an idea but not which session covered it they should start at the
 * general index; that is a navigation problem, and a map answers it better than a
 * list does.
 *
 * WHAT IT DOES NOT DO. Nothing is locked behind a prerequisite. A student
 * arriving in week 12 must not be walled out of L23 because they skipped L9, and
 * a map that gates on completion is a compliance system wearing a costume. What
 * the map withholds is structure, not access: corridors are drawn once you have
 * stood at both ends, so exploring reveals how the course fits together. The
 * rooms themselves are always open.
 *
 * There is no score here, no streak and no leaderboard, and their absence is
 * deliberate. This course's own optional reading argues that feeling productive
 * is not the same as learning, and a number that rises when you show up is
 * precisely the fluency signal it tells students not to trust. The progress
 * indicator is the map filling in, which is information rather than a score, and
 * a drawn room means the student actually went there.
 *
 * DOM AND CSS, NOT CANVAS. Twenty-six rooms and a sprite is about forty
 * interactive objects, a scale at which canvas buys nothing and costs the
 * accessibility that comes free with real elements. Every room is a <button>, so
 * it is focusable, labelled and reachable by Tab without any of that being
 * designed. Arrow keys are the second way in, not the only one.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Bank } from '../content/load.ts'
import {
  coverage, doorsOf, doorVisible, roomAt, roomById, signFor, step, world,
  type Room,
} from '../map/world.ts'
import type { Event } from '../store/log.ts'
import { visitedRooms } from '../store/log.ts'

/**
 * Pixels per grid cell, chosen so the whole 16-wide grid fits a desktop
 * container without scrolling. At 96 the fifth region sat past the right edge
 * and the map silently looked like a four-arc course. It still scrolls on a
 * narrow screen, because a 16-wide grid squeezed onto a phone is unreadable and
 * a scrollbar is not.
 */
const CELL = 72

interface Props {
  banks: Record<string, Bank>
  log: Event[]
  onVisit: (room: string) => void
  onStart: (lecture: string) => void
  onList: () => void
}

/**
 * An extracted quote is raw markdown, and it shows.
 * "At the end of [L3](../l03/notes.md) we had the Intel Berkeley Lab readings"
 * is what the notes contain and not what anyone wants to read in a panel, so
 * links collapse to their text and the inline emphasis markers come off.
 */
function plain(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[`*_]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

const KEYS: Record<string, [number, number]> = {
  ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0],
  w: [0, -1], s: [0, 1], a: [-1, 0], d: [1, 0],
  k: [0, -1], j: [0, 1], h: [-1, 0], l: [1, 0],
}

export function MapView({ banks, log, onVisit, onStart, onList }: Props) {
  const [at, setAt] = useState(world.spawn)
  const boardRef = useRef<HTMLDivElement>(null)
  const visited = useMemo(() => visitedRooms(log), [log])
  const here = roomAt(at.x, at.y)
  const seen = coverage(visited)

  // Standing in a room is what records it. Doing this in an effect rather than
  // in the move handler means arriving by keyboard, by click and by a restored
  // position all count the same way.
  useEffect(() => {
    if (here && !visited.has(here.id)) onVisit(here.id)
  }, [here, visited, onVisit])

  const move = useCallback((dx: number, dy: number) => {
    setAt((p) => step(p, dx, dy))
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const d = KEYS[e.key]
      if (!d) return
      e.preventDefault()
      move(d[0], d[1])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [move])

  const W = world.grid.width * CELL
  const H = world.grid.height * CELL

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">The course, as a place</h1>
          <p className="text-sm text-[var(--muted)]">
            Arrow keys, <kbd>WASD</kbd> or <kbd>hjkl</kbd> to walk. Tab reaches every
            room too. Corridors appear once you have stood at both ends.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <p className="text-sm text-[var(--muted)]" aria-live="polite">
            {seen.seen} of {seen.total} rooms visited
          </p>
          <button type="button" onClick={onList} className="btn-secondary">
            Module list
          </button>
        </div>
      </header>

      <div className="overflow-x-auto rounded-2xl border border-[var(--border)] bg-[var(--bg)]">
        <div
          ref={boardRef}
          className="relative"
          style={{ width: W, height: H }}
          role="application"
          aria-label="Course map. Use the arrow keys to walk between sessions."
        >
          {world.regions.map((region) => (
            <div
              key={region.name}
              className="absolute rounded-xl border border-dashed border-[var(--border)]
                         bg-[var(--surface-raised)] opacity-40"
              style={{
                left: (region.x0 - 0.25) * CELL,
                top: 0.7 * CELL,
                width: (world.grid.cols_per_region + 0.5) * CELL,
                height: (region.rows + 0.5) * CELL,
              }}
            >
              <span className="absolute -top-1 left-2 text-[11px] font-medium uppercase
                               tracking-wide text-[var(--muted)]">
                {region.name}
              </span>
            </div>
          ))}

          <svg width={W} height={H} className="pointer-events-none absolute inset-0">
            {world.doors.map((d) => {
              const a = roomById(d.from)!
              const b = roomById(d.to)!
              const lit = here && (d.from === here.id || d.to === here.id)
              if (!lit && !doorVisible(d, visited)) return null
              return (
                <line
                  key={`${d.from}-${d.to}`}
                  x1={(a.x + 0.5) * CELL} y1={(a.y + 0.5) * CELL}
                  x2={(b.x + 0.5) * CELL} y2={(b.y + 0.5) * CELL}
                  stroke={lit ? 'var(--brand)' : 'var(--border)'}
                  strokeWidth={lit ? 2.5 : 1.5}
                  strokeDasharray={d.origin === 'authored' ? '5 4' : undefined}
                  opacity={lit ? 0.9 : 0.5}
                />
              )
            })}
          </svg>

          {world.rooms.map((room) => (
            <RoomTile
              key={room.id}
              room={room}
              visited={visited.has(room.id)}
              standing={here?.id === room.id}
              onClick={() => setAt({ x: room.x, y: room.y })}
            />
          ))}

          <div
            aria-hidden
            className="pointer-events-none absolute z-10 grid place-items-center
                       rounded-full border-2 border-[var(--brand)] bg-[var(--bg)]
                       text-sm shadow-lg transition-transform duration-100"
            style={{
              width: CELL * 0.34, height: CELL * 0.34,
              transform: `translate(${(at.x + 0.5) * CELL - CELL * 0.17}px, ${
                (at.y + 0.5) * CELL - CELL * 0.17}px)`,
            }}
          >
            ●
          </div>
        </div>
      </div>

      <RoomPanel room={here} banks={banks} visited={visited} onStart={onStart} />
    </div>
  )
}

function RoomTile({ room, visited, standing, onClick }: {
  room: Room; visited: boolean; standing: boolean; onClick: () => void
}) {
  // Every tile is opaque, which is what stops a corridor drawing itself across
  // a room label. The lines sit in an SVG behind the tiles, so an opaque tile
  // hides the segment that would otherwise strike through its own name.
  const tone = !room.written
    ? 'border-dashed border-[var(--border)] text-[var(--muted)]'
    : visited
      ? 'border-[var(--brand)] bg-[var(--brand-wash)]'
      : 'border-[var(--border)] bg-[var(--bg)] text-[var(--muted)]'

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={standing ? 'true' : undefined}
      className={`absolute grid place-items-center rounded-xl border-2 px-1 text-center
                  transition-colors ${tone} ${standing ? 'ring-2 ring-[var(--brand)]' : ''}`}
      style={{
        left: room.x * CELL + 6, top: room.y * CELL + 6,
        width: CELL - 12, height: CELL - 12,
        // Shutters get their own texture rather than only a dashed border,
        // which they would otherwise share with a written room nobody has
        // visited. Two different states must not look the same.
        background: room.written
          ? undefined
          : 'repeating-linear-gradient(135deg, var(--surface-raised) 0 6px, var(--bg) 6px 12px)',
      }}
      // The visible label is the session number; the full title and state go to
      // assistive technology, which is otherwise handed a grid of bare numbers.
      aria-label={`${room.session}, ${room.title}. ${
        room.written ? 'Notes available' : 'Not written yet'
      }.${visited ? ' Visited.' : ''}`}
    >
      <span className="text-[13px] font-semibold">{room.session}</span>
    </button>
  )
}

function RoomPanel({ room, banks, visited, onStart }: {
  room: Room | undefined
  banks: Record<string, Bank>
  visited: ReadonlySet<string>
  onStart: (lecture: string) => void
}) {
  if (!room) {
    return (
      <p className="mt-4 text-sm text-[var(--muted)]">
        Walk onto a session to see what it covers and what it connects to.
      </p>
    )
  }

  const bank = banks[room.id]
  const sign = signFor(room.id)
  const links = doorsOf(room.id)

  return (
    <section className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--surface-raised)] p-5">
      <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
        {room.arc} · {room.date}
      </p>
      <h2 className="mt-1 text-lg font-semibold">
        {room.session} · {room.title}
      </h2>

      <div className="mt-3 flex flex-wrap gap-2">
        {room.notes && (
          <a className="btn-secondary" href={room.notes}>Read the notes</a>
        )}
        {bank && (
          <button type="button" className="btn-primary" onClick={() => onStart(room.id)}>
            Practice this module
          </button>
        )}
        {!room.written && (
          <span className="self-center text-sm text-[var(--muted)]">
            Not written yet. It is on the schedule, so it is drawn.
          </span>
        )}
      </div>

      {sign && (
        <p className="mt-3 border-l-2 border-[var(--border)] pl-3 text-sm italic text-[var(--muted)]">
          {sign.promised_by.toUpperCase()} already promises it: “{plain(sign.where)}”
        </p>
      )}

      {links.length === 0 && (
        // Not every room connects, and saying nothing looks like a bug. L2
        // cites nothing and is cited by nothing, which is a real property of
        // the course worth stating rather than rendering as an absence.
        <p className="mt-4 text-sm text-[var(--muted)]">
          No session links to this one, and it links to none. That is a fact
          about the notes as they stand, not a gap in the map.
        </p>
      )}

      {links.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">
            Connects to {links.length} other session{links.length === 1 ? '' : 's'}
          </h3>
          <ul className="mt-2 grid gap-2">
            {links.map(({ door, other, outbound }) => (
              <li key={`${door.from}-${door.to}`} className="text-sm">
                <span className="text-[var(--muted)]">
                  {outbound ? 'cites' : 'cited by'}{' '}
                </span>
                <strong>{other.session}</strong>
                {door.relation && (
                  <span className="text-[var(--muted)]"> · {door.relation}</span>
                )}
                {!visited.has(other.id) && (
                  <span className="text-[var(--muted)]"> · not visited yet</span>
                )}
                <p className="mt-0.5 text-[var(--muted)]">
                  {door.why ?? `“${plain(door.where)}”`}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
