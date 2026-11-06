/**
 * Lecture 1's figure, live: a production ML system sized by the code each part
 * requires, with the course mapped onto it.
 *
 * The boxes are the same rectangles `lectures/l01/figures/make_figures.py`
 * draws, read from knowledge.json, so the live figure and the PNG in the notes
 * cannot disagree about the one thing the figure argues, that the red box is
 * about 3.7% of the area. Hover a part to see what it is and which lectures
 * cover it; click it for the lectures, the tools the course used for it, and
 * the case studies where it mattered.
 *
 * A reading travels through the system in the order knowledge.yml gives, from
 * collection to verification to features to the model to serving to
 * monitoring, and each part lights as the reading reaches it: the figure's
 * argument, that most of the journey happens outside the red box, told as
 * motion. It stops when reduced motion is asked for.
 *
 * SVG rather than canvas: ten boxes is a scale where real elements cost
 * nothing, and each box is then a focusable button for free.
 *
 * On a phone held upright the figure is drawn transposed (`tall`), columns
 * becoming rows, so it fills the screen's height instead of shrinking to a
 * strip across its width. A transpose keeps every box's area, so the red box
 * is still 3.7% of the whole, and the reading still travels the same parts in
 * the same order. Labels wrap to the width of their box in both orientations.
 */

import { useEffect, useRef, useState } from 'react'
import { knowledge, lectureById, type Box } from '../map/knowledge.ts'
import { arcVar, type Focus } from './InfoPanel.tsx'

const S = 10 // viewBox units per figure unit
const LEG = 1900 // milliseconds the reading spends travelling between two parts

type R = { x: number; y: number; w: number; h: number }

/** Split a label into lines that fit a width, at an estimated glyph width. */
function wrap(text: string, width: number, size: number): string[] {
  const per = Math.max(4, Math.floor(width / (size * 0.56)))
  const lines: string[] = []
  let line = ''
  for (const word of text.split(' ')) {
    if (line && (line + ' ' + word).length > per) { lines.push(line); line = word }
    else line = line ? `${line} ${word}` : word
  }
  if (line) lines.push(line)
  return lines
}

export function SystemView({ focus, onFocus, showTools, reduceMotion, tall = false }: {
  focus: Focus
  onFocus: (f: Focus) => void
  showTools: boolean
  reduceMotion: boolean
  /** Draw the figure transposed, for a phone held upright. */
  tall?: boolean
}) {
  const { canvas, boxes, flow, caption } = knowledge.system
  const [W0, H] = canvas
  const [VW, VH] = tall ? [H * S, W0 * S] : [W0 * S, H * S]
  const [hover, setHover] = useState<string | null>(null)
  const [visiting, setVisiting] = useState<string | null>(null)
  const dotRef = useRef<SVGCircleElement>(null)
  const trailRef = useRef<SVGCircleElement>(null)
  const active = hover ?? (focus?.type === 'box' ? focus.id : null)

  // Figure units have y up from the bottom, as matplotlib draws them. Tall
  // swaps the screen axes, so the left column becomes the top row.
  const rect = (b: Box): R => {
    const r = { x: b.x * S, y: (H - b.y - b.h) * S, w: b.w * S, h: b.h * S }
    return tall ? { x: r.y, y: r.x, w: r.h, h: r.w } : r
  }
  const box = (id: string) => boxes.find((b) => b.id === id)!
  // Where the reading stops in each part: the lower left corner, clear of the
  // label and the lecture chips in the middle.
  const stop = (id: string): [number, number] => {
    const r = rect(box(id))
    return [r.x + 22, r.y + r.h - 22]
  }

  useEffect(() => {
    if (reduceMotion) { setVisiting(null); return }
    let raf = 0
    const t0 = performance.now()
    let last = ''
    const legs = flow.length - 1
    const tick = (now: number) => {
      raf = requestAnimationFrame(tick)
      // The first frame's timestamp can precede t0 by a fraction of a millisecond.
      const u = (Math.max(0, now - t0) / LEG) % legs
      const i = Math.floor(u)
      const f = u - i
      // Ease in and out of each part, and dwell a moment at each stop.
      const e = f < 0.35 ? 0 : (1 - Math.cos(Math.PI * Math.min(1, (f - 0.35) / 0.65))) / 2
      const [x0, y0] = stop(flow[i]!)
      const [x1, y1] = stop(flow[i + 1]!)
      const x = x0 + (x1 - x0) * e, y = y0 + (y1 - y0) * e
      dotRef.current?.setAttribute('cx', x.toFixed(1)); dotRef.current?.setAttribute('cy', y.toFixed(1))
      const e2 = Math.max(0, e - 0.08)
      trailRef.current?.setAttribute('cx', (x0 + (x1 - x0) * e2).toFixed(1))
      trailRef.current?.setAttribute('cy', (y0 + (y1 - y0) * e2).toFixed(1))
      const here = f < 0.35 ? flow[i]! : e > 0.9 ? flow[i + 1]! : ''
      if (here !== last) { last = here; setVisiting(here || null) }
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduceMotion, tall])

  const chip = tall ? 15 : 13
  const ml = boxes.find((b) => b.id === 'ml')
  const share = ml ? (100 * ml.w * ml.h) / boxes.reduce((s, b) => s + b.w * b.h, 0) : 0
  const lower = (s: string) => (/^[A-Z]{2}/.test(s) ? s : s.charAt(0).toLowerCase() + s.slice(1))

  return (
    <figure className="kg-system m-0 flex h-full w-full flex-col items-center gap-3">
      <div className="flex min-h-0 w-full flex-1 items-center justify-center">
        <svg viewBox={`-4 -4 ${VW + 8} ${VH + 8}`} className="block h-full max-h-full w-full"
             preserveAspectRatio="xMidYMid meet" role="group"
             aria-label="A production machine-learning system, sized by the code each part requires. Each part is a button.">
          <defs>
            <filter id="sys-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          {boxes.map((b) => {
            const r = rect(b)
            const isMl = b.id === 'ml'
            const on = !active || active === b.id
            const lit = visiting === b.id && !active
            const lecs = b.lectures.map((l) => lectureById(l)!).filter(Boolean)
            const fs = isMl ? (tall ? 21 : 19) : tall ? 19 : 17
            const lines = wrap(b.label, r.w - 20, fs)
            // The label block sits above the lecture chips, centred in the box together.
            const block = (n: number) => (n - 1) * fs * 1.2 + (lecs.length && !showTools && !isMl ? chip * 2 + 10 : 0)
            const labelY = (rr: R, n: number) => (showTools && !isMl ? rr.y + 30 : rr.y + rr.h / 2 - block(n) / 2)
            return (
              <g key={b.id} role="button" tabIndex={0} aria-label={`${b.label}. ${b.blurb}`}
                 className="cursor-pointer outline-none [&:focus-visible>rect]:stroke-[var(--brand)]"
                 onMouseEnter={() => setHover(b.id)} onMouseLeave={() => setHover(null)}
                 onFocus={() => setHover(b.id)} onBlur={() => setHover(null)}
                 onClick={() => onFocus({ type: 'box', id: b.id })}
                 onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFocus({ type: 'box', id: b.id }) } }}
                 style={{ opacity: on ? 1 : 0.35, transition: 'opacity 200ms' }}>
                <rect x={r.x + 3} y={r.y + 3} width={r.w - 6} height={r.h - 6} rx={10}
                      fill={isMl ? 'var(--arc-here)' : 'var(--surface-raised)'}
                      fillOpacity={isMl ? 1 : active === b.id ? 1 : 0.75}
                      stroke={active === b.id ? 'var(--kg-ink)' : lit ? 'var(--arc-1)' : 'var(--border)'}
                      strokeWidth={active === b.id || lit ? 3 : 1.5}
                      style={{ transition: 'stroke 300ms, stroke-width 300ms' }}
                      filter={(active === b.id || lit) && !reduceMotion ? 'url(#sys-glow)' : undefined} />
                <text x={r.x + r.w / 2} y={labelY(r, lines.length)}
                      textAnchor="middle" dominantBaseline="middle"
                      fill={isMl ? '#fff' : 'var(--kg-ink)'} fontSize={fs} fontWeight={isMl ? 700 : 600}>
                  {lines.map((ln, i) => <tspan key={i} x={r.x + r.w / 2} dy={i === 0 ? 0 : fs * 1.2}>{ln}</tspan>)}
                </text>
                {!showTools && lecs.length > 0 && !isMl && (
                  <g>
                    {lecs.map((l, i) => {
                      const cx = r.x + r.w / 2 + (i - (lecs.length - 1) / 2) * (chip * 2 + 8)
                      const cy = labelY(r, lines.length) + (lines.length - 1) * fs * 1.2 + fs * 0.6 + chip + 10
                      return (
                        <g key={l.id}>
                          <circle cx={cx} cy={cy} r={chip} fill={arcVar(l.arc)} />
                          <text x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="middle"
                                fill="#fff" fontSize={chip * 0.8} fontWeight={700}>{l.session}</text>
                        </g>
                      )
                    })}
                  </g>
                )}
                {isMl && (
                  <text x={r.x + r.w / 2} y={labelY(r, lines.length) + (lines.length - 1) * fs * 1.2 + 24}
                        textAnchor="middle" fill="#fff" fontSize={tall ? 13 : 11}>
                    {share.toFixed(1)}% of the area
                  </text>
                )}
                {showTools && !isMl && <ToolChips box={b} r={r} top={labelY(r, lines.length) + (lines.length - 1) * fs * 1.2 + 22} />}
              </g>
            )
          })}

          {!reduceMotion && (
            <g pointerEvents="none">
              <circle ref={trailRef} r={4} fill="var(--arc-1)" opacity={0.35} />
              <circle ref={dotRef} r={6} fill="var(--arc-1)" filter="url(#sys-glow)" />
            </g>
          )}
        </svg>
      </div>
      <figcaption className="glass max-w-3xl rounded-xl px-4 py-2 text-xs leading-relaxed text-[var(--muted)]">
        {caption} The blue light is a reading on its way through the system: {flow.map((id) => lower(box(id).label)).join(', then ')}.
      </figcaption>
    </figure>
  )
}

/** The tool names inside a box, wrapped into rows that fit its width. */
function ToolChips({ box, r, top }: { box: Box; r: R; top: number }) {
  const chips: { t: string; x: number; y: number; w: number; l: string }[] = []
  let x = r.x + 14, y = top
  for (const tool of box.tools) {
    const l = lectureById(tool.lecture)?.session ?? ''
    const room = Math.floor((r.w - 28 - l.length * 6.5 - 30) / 7.3)
    const term = tool.term.length > room ? `${tool.term.slice(0, Math.max(3, room - 1))}…` : tool.term
    const w = term.length * 7.3 + l.length * 6.5 + 30
    if (x + w > r.x + r.w - 10) { x = r.x + 14; y += 30 }
    if (y > r.y + r.h - 24) break
    chips.push({ t: term, x, y, w, l })
    x += w + 8
  }
  return (
    <g pointerEvents="none">
      {chips.map((c) => (
        <g key={c.t}>
          <rect x={c.x} y={c.y} width={c.w} height={22} rx={11} fill="var(--kg-bg)" stroke="var(--border)" />
          <text x={c.x + 11} y={c.y + 11.5} dominantBaseline="middle" fontSize={11.5} fill="var(--kg-ink)">
            {c.t} <tspan fill="var(--kg-muted)" fontSize={10}>{c.l}</tspan>
          </text>
        </g>
      ))}
    </g>
  )
}
