/**
 * A first-visit guide to the knowledge graph: a few steps, each pointing at
 * one thing on the page and saying what it does.
 *
 * Each step names what it points at: a control on the page (by its
 * `data-guide` attribute), a node on the canvas (located through the graph,
 * since a node is pixels rather than an element), or nothing, for the opening
 * card. A step can also set the page up before it shows, for example lighting
 * a lecture's links or opening its panel, so the guide demonstrates each move
 * as it describes it.
 *
 * The node drifts and the panel can resize, so the spotlight and the card are
 * placed every animation frame rather than once. They are written straight to
 * the elements' styles, so following a moving node never re-renders React.
 *
 * Whether the guide has been seen is a per-viewer convenience, so it lives in
 * localStorage, guarded, like the theme choice. Blocked storage means the guide
 * opens again next visit, which is the safe way to fail.
 */

import { useEffect, useRef, useState } from 'react'

export type Anchor =
  | { kind: 'page' }
  | { kind: 'control'; name: string; inner?: string }
  | { kind: 'node'; id: string }

export interface GuideStep {
  title: string
  body: string
  anchor: Anchor
  /** Dim the page around the anchor. Off where the point is what lights up around it. */
  dim?: boolean
  /** Set the page up for this step: light a node, open a panel, close one. */
  enter?: () => void
}

export interface Located { x: number; y: number; r: number }
export type Locate = (id: string) => Located | null

const KEY = 'f26-map-guide-seen'

export function guideSeen(): boolean {
  try { return localStorage.getItem(KEY) === '1' } catch { return false }
}
function markSeen() {
  try { localStorage.setItem(KEY, '1') } catch { /* storage blocked: show it again next visit */ }
}

interface Box { left: number; top: number; width: number; height: number; round: boolean }

function anchorBox(a: Anchor, locate: Locate | null): Box | null {
  if (a.kind === 'page') return null
  if (a.kind === 'node') {
    const p = locate?.(a.id)
    if (!p) return null
    const r = p.r + 10
    return { left: p.x - r, top: p.y - r, width: r * 2, height: r * 2, round: true }
  }
  const host = document.querySelector(`[data-guide="${a.name}"]`)
  const el = a.inner ? host?.querySelector(a.inner) : host
  if (!el) return null
  const b = el.getBoundingClientRect()
  if (b.width === 0) return null
  const pad = 6
  return { left: b.left - pad, top: b.top - pad, width: b.width + pad * 2, height: b.height + pad * 2, round: false }
}

type Side = 'below' | 'above' | 'left' | 'right'

/**
 * Put the card beside the box on the first side in `order` with room. A
 * control prefers below; a node prefers the side, so the card does not cover
 * the links the step is pointing at.
 */
function place(box: Box | null, cw: number, ch: number, order: Side[]): { x: number; y: number } {
  const W = window.innerWidth, H = window.innerHeight, gap = 14, m = 12
  const clampX = (x: number) => Math.min(Math.max(x, m), W - cw - m)
  const clampY = (y: number) => Math.min(Math.max(y, m), H - ch - m)
  if (!box) return { x: clampX((W - cw) / 2), y: clampY((H - ch) / 2) }
  const cx = box.left + box.width / 2, cy = box.top + box.height / 2
  const right = box.left + box.width, bottom = box.top + box.height
  for (const side of order) {
    if (side === 'below' && H - bottom >= ch + gap + m) return { x: clampX(cx - cw / 2), y: bottom + gap }
    if (side === 'above' && box.top >= ch + gap + m) return { x: clampX(cx - cw / 2), y: box.top - gap - ch }
    if (side === 'left' && box.left >= cw + gap + m) return { x: box.left - gap - cw, y: clampY(cy - ch / 2) }
    if (side === 'right' && W - right >= cw + gap + m) return { x: right + gap, y: clampY(cy - ch / 2) }
  }
  return { x: clampX(cx - cw / 2), y: clampY(H - ch - m) }
}
const CONTROL_SIDES: Side[] = ['below', 'above', 'left', 'right']
const NODE_SIDES: Side[] = ['left', 'right', 'below', 'above']

export function MapGuide({ steps, locate, onClose }: {
  steps: GuideStep[]
  locate: React.RefObject<Locate | null>
  onClose: () => void
}) {
  const [i, setI] = useState(0)
  const step = steps[i]!
  const last = i === steps.length - 1
  const cardRef = useRef<HTMLDivElement>(null)
  const spotRef = useRef<HTMLDivElement>(null)
  const nextRef = useRef<HTMLButtonElement>(null)
  const stepsRef = useRef(steps)
  stepsRef.current = steps

  const finish = () => { markSeen(); onClose() }

  // Each step sets the page up as it opens.
  useEffect(() => {
    stepsRef.current[i]?.enter?.()
    nextRef.current?.focus({ preventScroll: true })
  }, [i])

  // Follow the anchor every frame: nodes drift, and panels open and resize.
  useEffect(() => {
    let raf = 0
    const tick = () => {
      raf = requestAnimationFrame(tick)
      const card = cardRef.current, spot = spotRef.current
      if (!card || !spot) return
      const box = anchorBox(stepsRef.current[i]!.anchor, locate.current)
      spot.dataset.page = box ? '' : '1'
      spot.dataset.dim = stepsRef.current[i]!.dim === false ? '0' : '1'
      if (box) {
        spot.style.opacity = '1'
        spot.style.transform = `translate(${box.left}px, ${box.top}px)`
        spot.style.width = `${box.width}px`
        spot.style.height = `${box.height}px`
        spot.style.borderRadius = box.round ? '9999px' : '16px'
      } else {
        // No anchor: dim the whole page evenly behind the card.
        spot.style.opacity = '1'
        spot.style.transform = `translate(${window.innerWidth / 2}px, ${window.innerHeight / 2}px)`
        spot.style.width = '0px'; spot.style.height = '0px'
      }
      const order = stepsRef.current[i]!.anchor.kind === 'node' ? NODE_SIDES : CONTROL_SIDES
      const { x, y } = place(box, card.offsetWidth, card.offsetHeight, order)
      card.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [i, locate])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); finish() }
      if (e.key === 'ArrowRight') setI((n) => Math.min(n + 1, stepsRef.current.length - 1))
      if (e.key === 'ArrowLeft') setI((n) => Math.max(n - 1, 0))
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <>
      <div ref={spotRef} aria-hidden className="kg-guide-spot pointer-events-none fixed left-0 top-0 z-40 opacity-0" />
      <div ref={cardRef} role="dialog" aria-modal="false" aria-labelledby="kg-guide-title"
           className="glass fixed left-0 top-0 z-50 w-[min(320px,calc(100vw-24px))] rounded-2xl p-4 text-sm">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]">
          Guide · {i + 1} of {steps.length}
        </p>
        <h2 id="kg-guide-title" className="mt-1 text-base font-semibold leading-snug">{step.title}</h2>
        <p className="mt-1.5 leading-relaxed">{step.body}</p>
        <div className="mt-3 flex items-center gap-1">
          {steps.map((_, n) => (
            <span key={n} aria-hidden
                  className={`h-1.5 rounded-full transition-all ${n === i ? 'w-4 bg-[var(--brand)]' : 'w-1.5 bg-[var(--muted)] opacity-40'}`} />
          ))}
          <div className="ml-auto flex items-center gap-1">
            {!last && <button type="button" className="glass-btn !font-medium text-[var(--muted)]" onClick={finish}>Skip</button>}
            {i > 0 && <button type="button" className="glass-btn" onClick={() => setI(i - 1)}>Back</button>}
            <button ref={nextRef} type="button" className="btn-primary !rounded-full !px-4 !py-1.5 text-sm"
                    onClick={() => (last ? finish() : setI(i + 1))}>
              {last ? 'Start exploring' : 'Next'}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
