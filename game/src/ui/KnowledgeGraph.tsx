/**
 * The course as a knowledge graph, drawn on a canvas.
 *
 * WHY CANVAS HERE, WHEN THE ROOMS ARE DOM. The rooms are twenty buttons. The
 * topic view is 17 themes and 435 concepts drifting every frame, which is past
 * the scale where SVG stays smooth on a student laptop. What canvas costs in
 * accessibility is paid back beside it: the panel lists every node as a real
 * button when nothing is selected, search reaches any concept by name, and the
 * canvas itself carries a text description. Nothing is reachable only by
 * pointing.
 *
 * WHAT MOVES AND WHY. The layout is a force simulation run to rest before the
 * first frame, so the graph opens settled rather than flying in. The idle
 * motion is drawn on top of the rest positions (see `drawnAt`), so the graph
 * looks alive without the layout ever changing under the reader's eye. Light
 * flows along a highlighted link from the lecture that explains an idea to the
 * lecture that uses it. With reduced motion asked for, none of that runs, and
 * the picture is the same, only still.
 *
 * TOUCH. On a phone or tablet there is no hover, so a tap opens a node, one
 * finger pans, two fingers pinch to zoom about their midpoint, and a double
 * tap on the sky zooms in. A finger does not pull nodes about, since in a
 * dense graph it would do that by accident more often than on purpose. On a
 * phone (`compact`) the nodes, labels and touch targets are drawn larger and
 * the graph is fitted with less margin, because the screen is the constraint.
 *
 * The canvas fills the page and the controls float over it, so the camera
 * fits the graph to the part of the screen the controls leave clear (`view`),
 * and keeps a selected node out from under the panel (`panel`).
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  KIND_LABEL, conceptById, knowledge, lectureById, themeById, type ConceptKind,
} from '../map/knowledge.ts'
import { lectureGraph, settle, topicGraph, type GLink, type GNode, type Graph, type Mode } from '../map/layout.ts'
import type { Focus } from './InfoPanel.tsx'
import type { Locate } from './MapGuide.tsx'

interface Palette {
  bg: string; edge: string; ink: string; muted: string; line: string; star: string
  arcs: string[]; here: string
}

function readPalette(el: Element): Palette {
  const cs = getComputedStyle(el)
  const v = (n: string) => cs.getPropertyValue(n).trim()
  return {
    bg: v('--kg-bg'), edge: v('--kg-bg-edge'), ink: v('--kg-ink'), muted: v('--kg-muted'),
    line: v('--kg-line'), star: v('--kg-star'),
    arcs: [v('--arc-0'), v('--arc-1'), v('--arc-2'), v('--arc-3')], here: v('--arc-here'),
  }
}

const colorOf = (p: Palette, slot: number) => (slot < 0 ? p.here : p.arcs[slot % p.arcs.length]!)

/** A soft round glow per colour, drawn once and stamped, since shadowBlur per node is slow. */
function glowSprite(color: string): HTMLCanvasElement {
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const g = c.getContext('2d')!
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64)
  grad.addColorStop(0, color)
  grad.addColorStop(0.25, color)
  grad.addColorStop(1, 'transparent')
  g.globalAlpha = 0.55
  g.fillStyle = grad
  g.fillRect(0, 0, 128, 128)
  return c
}

/** Stars for the dark sky (and a faint dot field in light), fixed per page load. */
const STARS = Array.from({ length: 280 }, (_, i) => {
  const s = Math.sin(i * 12.9898) * 43758.5453
  const r = Math.sin(i * 78.233) * 12345.6789
  return { x: s - Math.floor(s), y: r - Math.floor(r), z: 0.3 + ((i * 37) % 10) / 14, p: i * 1.7 }
})

/**
 * Where a node is drawn at time t: its rest position plus the idle motion.
 * Lectures and topics wander on a slow loop of two frequencies, each with its
 * own phase, so no two move in step. A concept's ring turns around its topic,
 * the inner ring faster than the outer and each topic its own way round, like
 * an orrery. At t = 0 every node sits at rest.
 */
export function drawnAt(n: GNode, t: number): [number, number] {
  const wobble = (a: number, ph: number): [number, number] => [
    a * (Math.sin(t * 0.00055 + ph) + 0.45 * Math.sin(t * 0.00121 + ph * 2.1)),
    a * (Math.cos(t * 0.00047 + ph * 1.3) + 0.45 * Math.cos(t * 0.00097 + ph * 1.7)),
  ]
  const c = n.centre
  if (c) {
    const [cx, cy] = drawnAt(c, t)
    const dx = n.x! - c.x!, dy = n.y! - c.y!
    const inner = (n.ring ?? 0) < c.r + 30
    const turn = (c.phase > Math.PI ? 1 : -1) * t * (inner ? 4.2e-5 : 2.9e-5)
    const a = Math.atan2(dy, dx) + turn, d = Math.hypot(dx, dy)
    const [wx, wy] = wobble(2.5, n.phase)
    return [cx + Math.cos(a) * d + wx, cy + Math.sin(a) * d + wy]
  }
  const [wx, wy] = wobble(n.kind === 'theme' ? 11 : 9, n.phase)
  return [n.x! + wx, n.y! + wy]
}

/** Pixels from each edge of the canvas that the floating controls cover. */
export interface View { t: number; r: number; b: number; l: number }
/** The info panel over the canvas, when open: the side it is on and how far in it reaches. */
export interface PanelBox { side: 'right' | 'bottom'; size: number }

export const nodeIdFor = (f: Focus, mode: Mode): string | null => {
  if (!f) return null
  if (f.type === 'lecture' && mode === 'lectures') return f.id
  if (f.type === 'theme' && mode === 'topics') return `theme:${f.id}`
  if (f.type === 'concept' && mode === 'topics') return `concept:${f.id}`
  return null
}

const focusFor = (n: GNode): Focus =>
  n.kind === 'lecture' ? { type: 'lecture', id: n.id }
    : n.kind === 'theme' ? { type: 'theme', id: n.id.slice(6) }
      : { type: 'concept', id: n.id.slice(8) }

const ends = (l: GLink) => [(l.source as GNode), (l.target as GNode)] as const

interface Cam { x: number; y: number; k: number }

interface Frame { w: number; h: number; view: View; panel: PanelBox | null; compact: boolean }

/** The screen point the camera centre maps to: the middle of the area the controls leave clear. */
function origin(s: Frame): { x: number; y: number } {
  return { x: s.view.l + (s.w - s.view.l - s.view.r) / 2, y: s.view.t + (s.h - s.view.t - s.view.b) / 2 }
}

/** The part of the screen nothing covers, the open panel included. */
function clearArea(s: Frame) {
  return {
    x0: s.view.l, y0: s.view.t,
    x1: s.panel?.side === 'right' ? s.w - s.panel.size : s.w - s.view.r,
    y1: s.panel?.side === 'bottom' ? s.h - s.panel.size : s.h - s.view.b,
  }
}

const fitView = (g: Graph, s: Frame): Cam =>
  fitCam(g, Math.max(160, s.w - s.view.l - s.view.r), Math.max(160, s.h - s.view.t - s.view.b), s.compact ? 30 : 90)

function fitCam(g: Graph, w: number, h: number, pad: number): Cam {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  for (const n of g.nodes) {
    x0 = Math.min(x0, n.x! - n.r); y0 = Math.min(y0, n.y! - n.r)
    x1 = Math.max(x1, n.x! + n.r); y1 = Math.max(y1, n.y! + n.r)
  }
  const k = Math.min(w / (x1 - x0 + pad * 2), h / (y1 - y0 + pad * 2))
  return { x: (x0 + x1) / 2, y: (y0 + y1) / 2, k: Math.max(0.15, Math.min(k, 1.6)) }
}

interface Props {
  mode: Mode
  focus: Focus
  onFocus: (f: Focus) => void
  theme: 'light' | 'dark'
  reduceMotion: boolean
  kindFilter: ConceptKind | null
  /** Bumped by the "reset view" button. */
  resetKey: number
  view: View
  panel: PanelBox | null
  /** A node to light as if hovered, for the guide to demonstrate with. */
  spotlight?: string | null
  /** Filled in with a function that finds a node on screen, for the guide to point at. */
  locate?: React.RefObject<Locate | null>
  /** A phone-sized screen: bigger nodes, labels and targets, a tighter fit. */
  compact?: boolean
}

export function KnowledgeGraph({
  mode, focus, onFocus, theme, reduceMotion, kindFilter, resetKey, view, panel, spotlight = null, locate,
  compact = false,
}: Props) {
  const boxRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const tipRef = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<GNode | null>(null)

  // Built and settled once each; the topic graph only when first opened.
  const cache = useRef<Partial<Record<Mode, Graph>>>({})
  const graph = useMemo(() => {
    if (!cache.current[mode]) {
      const g = mode === 'lectures' ? lectureGraph() : topicGraph()
      settle(g)
      cache.current[mode] = g
    }
    return cache.current[mode]!
  }, [mode])

  // Mutable drawing state lives in refs so the frame loop never waits on React.
  const st = useRef({
    cams: {} as Partial<Record<Mode, Cam>>, target: null as Cam | null,
    w: 0, h: 0, hover: null as GNode | null, drag: null as null | { node?: GNode; sx: number; sy: number; moved: boolean; cx: number; cy: number },
    clicked: null as string | null, palette: null as Palette | null, sprites: new Map<string, HTMLCanvasElement>(),
    view: view, panel: panel, compact: compact, t: 0, pos: new Map<GNode, [number, number]>(),
    /** Whether the reader (or a glide to a focus) has moved this mode's camera off its fit. */
    moved: {} as Partial<Record<Mode, boolean>>,
    focusFrom: 'outside' as 'canvas' | 'outside',
  })
  const props = useRef({ mode, focus, kindFilter, reduceMotion, theme, spotlight })
  props.current = { mode, focus, kindFilter, reduceMotion, theme, spotlight }
  st.current.view = view
  st.current.panel = panel
  st.current.compact = compact

  // Colours follow the theme; re-read them whenever it flips.
  useEffect(() => {
    if (!boxRef.current) return
    st.current.palette = readPalette(boxRef.current)
    st.current.sprites.clear()
  }, [theme])

  // Size the canvas to its box, at device resolution.
  useEffect(() => {
    const box = boxRef.current, canvas = canvasRef.current
    if (!box || !canvas) return
    const fit = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const w = box.clientWidth, h = box.clientHeight
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr)
      canvas.style.width = `${w}px`; canvas.style.height = `${h}px`
      const s = st.current
      s.w = w; s.h = h
      // A camera nobody has moved follows the window.
      const m = props.current.mode, g = cache.current[m]
      if (g && s.cams[m] && !s.moved[m]) s.cams[m] = fitView(g, s)
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(box)
    return () => ro.disconnect()
  }, [])

  // Each mode keeps its own camera, fitted the first time it opens, and refitted
  // when the controls change shape, until the reader moves it themselves.
  const viewKey = `${view.t},${view.r},${view.b},${view.l},${compact}`
  useEffect(() => {
    const s = st.current
    if (!s.w) return
    if (!s.cams[mode] || !s.moved[mode]) { s.cams[mode] = fitView(graph, s); s.target = null }
  }, [mode, graph, viewKey])
  useEffect(() => {
    const s = st.current
    if (resetKey && s.w) { s.target = fitView(graph, s); s.moved[mode] = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey, graph])

  // A focus that came from outside the canvas (the panel, search, the tour)
  // glides the camera to it. One that came from a click on the canvas glides
  // only if the panel that click opened now covers it: the reader is already
  // looking there. The panel opens a moment after the focus changes, so this
  // runs again when it does.
  useEffect(() => {
    const s = st.current
    s.focusFrom = s.clicked && s.clicked === nodeIdFor(focus, mode) ? 'canvas' : 'outside'
    s.clicked = null
  }, [focus, mode])
  const panelKey = panel ? `${panel.side}${panel.size}` : ''
  useEffect(() => {
    const s = st.current
    const id = nodeIdFor(focus, mode)
    const n = id ? graph.nodes.find((x) => x.id === id) : undefined
    const cam = s.cams[mode]
    if (!n || !cam || !s.w) return
    const [nx, ny] = s.pos.get(n) ?? drawnAt(n, s.t)
    const clear = clearArea(s)
    const k = s.focusFrom === 'outside' ? Math.max(cam.k, n.kind === 'lecture' ? 0.9 : 1.5) : cam.k
    if (s.focusFrom === 'canvas') {
      const o = origin(s)
      const x = (nx - cam.x) * cam.k + o.x, y = (ny - cam.y) * cam.k + o.y
      const m = 28
      if (x > clear.x0 + m && x < clear.x1 - m && y > clear.y0 + m && y < clear.y1 - m) return
    }
    const o = origin(s)
    s.target = { x: nx - ((clear.x0 + clear.x1) / 2 - o.x) / k, y: ny - ((clear.y0 + clear.y1) / 2 - o.y) / k, k }
    s.moved[mode] = true
  }, [focus, mode, graph, panelKey])

  // The frame loop.
  useEffect(() => {
    const canvas = canvasRef.current!
    const ctx = canvas.getContext('2d')!
    let raf = 0

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame)
      const s = st.current
      const { mode, focus, kindFilter, reduceMotion, theme, spotlight } = props.current
      const p = s.palette ?? (s.palette = readPalette(boxRef.current!))
      const g = cache.current[mode]
      if (!g || !s.w) return
      const cam = s.cams[mode] ?? (s.cams[mode] = fitView(g, s))
      if (s.target) {
        const e = reduceMotion ? 1 : 0.12
        cam.x += (s.target.x - cam.x) * e; cam.y += (s.target.y - cam.y) * e; cam.k += (s.target.k - cam.k) * e
        if (Math.abs(s.target.x - cam.x) < 0.5 && Math.abs(s.target.k - cam.k) < 0.002) s.target = null
      }
      const t = reduceMotion ? 0 : now
      s.t = t
      const dpr = canvas.width / s.w
      const W = s.w, H = s.h
      const dark = theme === 'dark'

      // Drawn positions, once per frame: the rest position plus the idle motion.
      // Hit-testing and the tooltip read the same map, so what you point at is
      // what is drawn there.
      const pos = s.pos
      pos.clear()
      for (const n of g.nodes) pos.set(n, drawnAt(n, t))
      const px = (n: GNode) => pos.get(n)![0]
      const py = (n: GNode) => pos.get(n)![1]
      const o = origin(s)
      const big = s.compact
      // Smallest drawn size, so a zoomed-out phone still shows a tappable mark.
      // A topic is not enlarged as much as a lecture, or it would cover its own ring of concepts.
      const minR = (n: GNode) => (n.kind === 'concept' ? (big ? 2.6 : 2.2) : n.kind === 'theme' ? (big ? 7 : 6) : big ? 13 : 6)
      if (canvas.dataset.k !== cam.k.toFixed(2)) canvas.dataset.k = cam.k.toFixed(2)
      const sx = (x: number) => (x - cam.x) * cam.k + o.x
      const sy = (y: number) => (y - cam.y) * cam.k + o.y

      // What is lit: the hovered or selected node and its neighbours, or a kind filter.
      const focusId = s.hover?.id ?? spotlight ?? nodeIdFor(focus, mode)
      let lit: Set<string> | null = null
      if (focusId) {
        lit = new Set([focusId, ...(g.neighbours.get(focusId) ?? [])])
        if (focusId.startsWith('concept:')) {
          const c = conceptById(focusId.slice(8))
          if (c) lit.add(`theme:${c.theme}`)
        }
      } else if (kindFilter && mode === 'topics') {
        lit = new Set()
        for (const n of g.nodes) {
          if (n.conceptKind === kindFilter) {
            lit.add(n.id)
            const c = conceptById(n.id.slice(8))
            if (c) lit.add(`theme:${c.theme}`)
          }
        }
      }
      const on = (id: string) => !lit || lit.has(id)

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

      // Sky.
      const bgGrad = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.hypot(W, H) / 1.6)
      bgGrad.addColorStop(0, p.bg); bgGrad.addColorStop(1, p.edge)
      ctx.fillStyle = bgGrad
      ctx.fillRect(0, 0, W, H)
      ctx.fillStyle = p.star
      for (const star of STARS) {
        const x = ((star.x * W - cam.x * 0.04 * star.z) % W + W) % W
        const y = ((star.y * H - cam.y * 0.04 * star.z) % H + H) % H
        ctx.globalAlpha = dark ? star.z * (0.55 + 0.45 * Math.sin(t * 0.0012 + star.p)) : 0.7
        ctx.beginPath(); ctx.arc(x, y, dark ? star.z * 1.1 : 0.9, 0, Math.PI * 2); ctx.fill()
      }
      ctx.globalAlpha = 1

      interface Lab {
        txt: string; x: number; y: number; size: number; weight: number; caps?: boolean; sub?: string
        /** A second place to try, above the node, when the first is taken. */
        altY?: number
        align: CanvasTextAlign; base: 'top' | 'middle'; color: string; alpha: number; pri: number; must: boolean
      }
      const labs: Lab[] = []

      // Territories: one soft wash per arc, named in small capitals.
      const groups = new Map<number, GNode[]>()
      for (const n of g.nodes) {
        if (n.slot < 0 || n.kind === 'concept') continue
        const list = groups.get(n.slot) ?? []
        list.push(n); groups.set(n.slot, list)
      }
      for (const [slot, ns] of groups) {
        const cx = ns.reduce((a, n) => a + px(n), 0) / ns.length
        const cy = ns.reduce((a, n) => a + py(n), 0) / ns.length
        const rad = Math.max(...ns.map((n) => Math.hypot(px(n) - cx, py(n) - cy) + n.r)) + (mode === 'topics' ? 120 : 70)
        const grad = ctx.createRadialGradient(sx(cx), sy(cy), 0, sx(cx), sy(cy), rad * cam.k)
        grad.addColorStop(0, colorOf(p, slot)); grad.addColorStop(1, 'transparent')
        ctx.globalAlpha = dark ? 0.13 : 0.08
        ctx.fillStyle = grad
        ctx.beginPath(); ctx.arc(sx(cx), sy(cy), rad * cam.k, 0, Math.PI * 2); ctx.fill()
        const d = Math.hypot(cx, cy) || 1
        const lx = cx + (cx / d) * rad * 0.82, ly = cy + (cy / d) * rad * 0.82
        labs.push({ txt: (knowledge.arcs[slot] ?? '').toUpperCase(), x: sx(lx), y: sy(ly), size: big ? 12 : 11, weight: 600,
                    caps: true, align: 'center', base: 'middle', color: p.muted, alpha: lit ? 0.35 : 0.8, pri: 5, must: false })
      }
      ctx.globalAlpha = 1

      // Links: curved, faint at rest, bright and flowing when lit.
      const curve = (l: GLink) => {
        const [a, b] = ends(l)
        const x0 = sx(px(a)), y0 = sy(py(a)), x1 = sx(px(b)), y1 = sy(py(b))
        const mx = (x0 + x1) / 2, my = (y0 + y1) / 2
        const bend = l.kind === 'member' ? 0 : l.kind === 'trail' ? 0.06 : 0.16
        const sign = (a.phase > b.phase ? 1 : -1)
        return { x0, y0, x1, y1, cx: mx - (y1 - y0) * bend * sign, cy: my + (x1 - x0) * bend * sign }
      }
      const touches = (l: GLink) => {
        if (!focusId) return false
        const [a, b] = ends(l)
        return a.id === focusId || b.id === focusId
      }
      for (const l of g.links) {
        const [a, b] = ends(l)
        const hot = touches(l)
        if (hot) continue
        const c = curve(l)
        const visible = on(a.id) && on(b.id)
        ctx.globalAlpha = l.kind === 'member' ? (visible ? (lit ? 0.35 : 0.18) : 0.04)
          : visible ? (l.kind === 'trail' ? 0.5 : 0.75) : 0.08
        ctx.strokeStyle = l.kind === 'member' ? colorOf(p, a.slot) : p.line
        ctx.lineWidth = (l.kind === 'cite' || l.kind === 'theme' ? 1.2 + 0.4 * Math.min(l.weight, 3) : 0.8) * (big ? 1.25 : 1)
        ctx.setLineDash(l.kind === 'trail' ? [2, 5] : [])
        ctx.beginPath(); ctx.moveTo(c.x0, c.y0); ctx.quadraticCurveTo(c.cx, c.cy, c.x1, c.y1); ctx.stroke()
      }
      ctx.setLineDash([])
      for (const l of g.links) {
        if (!touches(l)) continue
        const [a, b] = ends(l)
        const c = curve(l)
        const grad = ctx.createLinearGradient(c.x0, c.y0, c.x1, c.y1)
        grad.addColorStop(0, colorOf(p, a.slot)); grad.addColorStop(1, colorOf(p, b.slot))
        ctx.globalAlpha = 0.95
        ctx.strokeStyle = grad
        ctx.lineWidth = l.kind === 'member' ? 1.4 : 2.6
        ctx.beginPath(); ctx.moveTo(c.x0, c.y0); ctx.quadraticCurveTo(c.cx, c.cy, c.x1, c.y1); ctx.stroke()
        // Light travels from the lecture that explains (the cited end) to the one that uses it.
        if (!reduceMotion && l.kind !== 'member') {
          for (let i = 0; i < 3; i++) {
            const u = 1 - (((t * 0.00028) + i / 3) % 1)
            const x = (1 - u) ** 2 * c.x0 + 2 * (1 - u) * u * c.cx + u ** 2 * c.x1
            const y = (1 - u) ** 2 * c.y0 + 2 * (1 - u) * u * c.cy + u ** 2 * c.y1
            ctx.globalAlpha = 0.9
            ctx.fillStyle = dark ? '#ffffff' : colorOf(p, b.slot)
            ctx.beginPath(); ctx.arc(x, y, 2.4, 0, Math.PI * 2); ctx.fill()
          }
        }
      }
      ctx.globalAlpha = 1

      // Nodes.
      const sprite = (color: string) => {
        let sp = s.sprites.get(color)
        if (!sp) { sp = glowSprite(color); s.sprites.set(color, sp) }
        return sp
      }
      const order = [...g.nodes].sort((a, b) => (on(a.id) ? 1 : 0) - (on(b.id) ? 1 : 0) || a.r - b.r)
      for (const n of order) {
        const x = sx(px(n)), y = sy(py(n))
        const r = Math.max(minR(n), n.r * cam.k) * (s.hover?.id === n.id ? 1.18 : 1)
        if (x < -60 || y < -60 || x > W + 60 || y > H + 60) continue
        const col = colorOf(p, n.slot)
        const vis = on(n.id)
        ctx.globalAlpha = vis ? 1 : 0.13
        if (dark && n.released && n.kind !== 'concept') {
          ctx.drawImage(sprite(col), x - r * 2.6, y - r * 2.6, r * 5.2, r * 5.2)
        }
        if (!n.released) {
          ctx.fillStyle = p.bg
          ctx.strokeStyle = p.muted
          ctx.setLineDash([3, 3]); ctx.lineWidth = 1.5
          ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
          ctx.setLineDash([])
        } else if (n.kind === 'concept') {
          ctx.fillStyle = col
          ctx.beginPath()
          if (n.conceptKind === 'case') { ctx.moveTo(x, y - r * 1.3); ctx.lineTo(x + r * 1.3, y); ctx.lineTo(x, y + r * 1.3); ctx.lineTo(x - r * 1.3, y) }
          else if (n.conceptKind === 'failure') { ctx.moveTo(x, y - r * 1.4); ctx.lineTo(x + r * 1.3, y + r); ctx.lineTo(x - r * 1.3, y + r) }
          else if (n.conceptKind === 'metric') { ctx.rect(x - r, y - r, r * 2, r * 2) }
          else ctx.arc(x, y, r, 0, Math.PI * 2)
          ctx.closePath(); ctx.fill()
        } else {
          ctx.fillStyle = col
          ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill()
          // A surface ring separates overlapping marks; a brighter core reads as light in the dark.
          ctx.lineWidth = 2
          ctx.strokeStyle = dark ? 'rgba(255,255,255,0.35)' : p.bg
          ctx.stroke()
          if (dark) {
            ctx.globalAlpha *= 0.45
            ctx.fillStyle = '#fff'
            ctx.beginPath(); ctx.arc(x - r * 0.25, y - r * 0.25, r * 0.38, 0, Math.PI * 2); ctx.fill()
            ctx.globalAlpha = vis ? 1 : 0.13
          }
        }
        const sel = nodeIdFor(focus, mode) === n.id
        if (sel) {
          ctx.strokeStyle = p.ink; ctx.lineWidth = 2
          ctx.beginPath(); ctx.arc(x, y, r + 5 + (reduceMotion ? 0 : 1.5 * Math.sin(t * 0.004)), 0, Math.PI * 2); ctx.stroke()
        }
      }

      // Labels, in screen space so they stay readable at any zoom. Text wears
      // the ink colours; the node beside it carries the colour. They are placed
      // greedily in priority order, and one that would overlap a label already
      // placed is skipped, except the hovered or selected node's, which always
      // shows. The panel and the tooltip carry every name in full.
      const selId = nodeIdFor(focus, mode)
      const FONT = 'ui-sans-serif, system-ui, sans-serif'
      for (const n of g.nodes) {
        const x = sx(px(n)), y = sy(py(n))
        if (x < -80 || y < -80 || x > W + 80 || y > H + 80) continue
        const r = Math.max(minR(n), n.r * cam.k)
        const vis = on(n.id)
        const must = n.id === s.hover?.id || n.id === selId
        if (n.kind === 'lecture') {
          ctx.globalAlpha = vis ? 1 : 0.25
          ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
          ctx.font = `700 ${Math.max(big ? 11 : 10, Math.min(15, r * 0.75))}px ${FONT}`
          ctx.fillStyle = n.released ? '#fff' : p.muted
          ctx.fillText(n.label, x, y + 0.5)
          if (cam.k > (big ? 0.12 : 0.45) || must) {
            const date = lectureById(n.id)?.date.slice(5).replace('-', '/') ?? ''
            labs.push({ txt: n.released ? n.sub : `${n.sub} · opens ${date}`, x, y: y + r + 6, altY: y - r - 21, size: big ? 12.5 : 11.5,
                        weight: n.slot < 0 ? 650 : 500, align: 'center', base: 'top',
                        color: vis ? p.ink : p.muted, alpha: vis ? 1 : 0.35, pri: n.slot < 0 ? 90 : vis && lit ? 70 : 50, must })
          }
        } else if (n.kind === 'theme') {
          const below = Math.max(r, (n.r + 38) * cam.k) + 5
          labs.push({ txt: n.label, sub: n.sub, x, y: y + below, altY: y - below - 31, size: big ? 13.5 : 12.5, weight: 650, align: 'center', base: 'top',
                      color: p.ink, alpha: vis ? 1 : 0.35, pri: vis && lit ? 85 : 60, must })
        } else {
          const near = focusId && vis && (focusId.startsWith('theme:') || focusId === n.id)
          const kindLit = !focusId && kindFilter && n.conceptKind === kindFilter
          if (!(cam.k >= 1.5 && vis) && !near && !kindLit && !must) continue
          const right = !n.centre || px(n) >= px(n.centre)
          labs.push({ txt: n.label, x: x + (right ? r + 5 : -r - 5), y, size: big ? 12 : 11, weight: must ? 650 : 500,
                      align: right ? 'left' : 'right', base: 'middle', color: p.ink, alpha: 1,
                      pri: near ? 40 : 20, must })
        }
      }
      labs.sort((a, b) => Number(b.must) - Number(a.must) || b.pri - a.pri)
      // Lecture and theme nodes are obstacles too, so a label is
      // never printed across a node it does not belong to.
      const placed: [number, number, number, number][] = []
      for (const n of g.nodes) {
        if (n.kind === 'concept') continue
        const x = sx(px(n)), y = sy(py(n))
        const rr = Math.max(minR(n), n.r * cam.k)
        placed.push([x - rr, y - rr, x + rr, y + rr])
      }
      const clash = (b: [number, number, number, number]) =>
        placed.some((q) => b[0] < q[2] && b[2] > q[0] && b[1] < q[3] && b[3] > q[1])
      ctx.lineJoin = 'round'
      for (const L of labs) {
        ctx.font = `${L.weight} ${L.size}px ${FONT}`
        if ('letterSpacing' in ctx) (ctx as unknown as { letterSpacing: string }).letterSpacing = L.caps ? '1.5px' : '0px'
        let w = ctx.measureText(L.txt).width
        const h = L.size + 3 + (L.sub ? 14 : 0)
        if (L.sub) {
          ctx.font = `500 10.5px ${FONT}`
          w = Math.max(w, ctx.measureText(L.sub).width)
          ctx.font = `${L.weight} ${L.size}px ${FONT}`
        }
        let x0 = L.align === 'left' ? L.x : L.align === 'right' ? L.x - w : L.x - w / 2
        // Keep a label on screen when its node is, so an edge node is not
        // named with half a word.
        if (L.x >= 0 && L.x <= W) {
          const shift = x0 < 6 ? 6 - x0 : x0 + w > W - 6 ? W - 6 - (x0 + w) : 0
          L.x += shift; x0 += shift
        }
        const y0 = L.base === 'top' ? L.y : L.y - h / 2
        let box: [number, number, number, number] = [x0 - 2, y0 - 1, x0 + w + 2, y0 + h + 1]
        if (!L.must && clash(box)) {
          if (L.altY === undefined) continue
          const dy = L.altY - L.y
          box = [box[0], box[1] + dy, box[2], box[3] + dy]
          if (clash(box)) continue
          L.y = L.altY
        }
        placed.push(box)
        ctx.globalAlpha = L.alpha
        ctx.textAlign = L.align; ctx.textBaseline = L.base
        ctx.lineWidth = 3.5; ctx.strokeStyle = p.bg
        ctx.strokeText(L.txt, L.x, L.y)
        ctx.fillStyle = L.color
        ctx.fillText(L.txt, L.x, L.y)
        if (L.sub) {
          ctx.font = `500 10.5px ${FONT}`
          ctx.strokeText(L.sub, L.x, L.y + L.size + 3)
          ctx.fillStyle = p.muted
          ctx.fillText(L.sub, L.x, L.y + L.size + 3)
        }
      }
      if ('letterSpacing' in ctx) (ctx as unknown as { letterSpacing: string }).letterSpacing = '0px'
      ctx.globalAlpha = 1

      // The tooltip follows its node, including the drift.
      const tip = tipRef.current
      if (tip && s.hover) {
        const n = s.hover
        const x = sx(px(n)), y = sy(py(n))
        const c = clearArea(s)
        const left = Math.min(Math.max(x + 18, c.x0 + 8), c.x1 - tip.offsetWidth - 8)
        const top = y - tip.offsetHeight - 14 > c.y0 + 8 ? y - tip.offsetHeight - 14 : y + 22
        tip.style.transform = `translate(${left}px, ${top}px)`
      }
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [])

  const onFocusRef = useRef(onFocus)
  onFocusRef.current = onFocus

  // Pointer: hover, click, drag a node, drag the sky to pan, wheel to zoom.
  // A finger: tap to open, drag to pan, pinch with two to zoom, double tap
  // the sky to zoom in.
  useEffect(() => {
    const canvas = canvasRef.current!
    const s = st.current
    const camOf = () => s.cams[props.current.mode]
    const world = (e: { clientX: number; clientY: number }) => {
      const rect = canvas.getBoundingClientRect()
      const cam = camOf()!
      const o = origin(s)
      return { x: (e.clientX - rect.left - o.x) / cam.k + cam.x, y: (e.clientY - rect.top - o.y) / cam.k + cam.y }
    }
    /** Move the camera so that world point (wx, wy) sits under client point (cx, cy) at zoom k. */
    const pinTo = (wx: number, wy: number, cx: number, cy: number, k: number): Cam => {
      const rect = canvas.getBoundingClientRect()
      const o = origin(s)
      return { x: wx - (cx - rect.left - o.x) / k, y: wy - (cy - rect.top - o.y) / k, k }
    }
    const clampK = (k: number) => Math.max(0.15, Math.min(4, k))
    const hit = (e: PointerEvent) => {
      const g = cache.current[props.current.mode]
      const cam = camOf()
      if (!g || !cam) return null
      const w = world(e)
      const finger = e.pointerType === 'touch'
      let best: GNode | null = null, bd = Infinity
      for (const n of g.nodes) {
        const [nx, ny] = s.pos.get(n) ?? [n.x!, n.y!]
        const d = Math.hypot(nx - w.x, ny - w.y)
        // A fingertip is about 9 mm across, so its target is wider than a cursor's.
        const px = finger ? (n.kind === 'concept' ? 14 : 22) : n.kind === 'concept' ? 7 : 10
        const reach = Math.max(n.r, px / cam.k) + 2 / cam.k
        if (d <= reach && (d < bd || (best?.kind === 'concept' && n.kind !== 'concept'))) { best = n; bd = d }
      }
      return best
    }
    const setHov = (n: GNode | null) => {
      if (s.hover?.id === n?.id) return
      s.hover = n
      setHover(n)
      canvas.style.cursor = n ? 'pointer' : 'grab'
    }
    const letGo = () => {
      const node = s.drag?.node
      if (node && node.kind !== 'concept' && node.slot >= 0) {
        node.fx = null; node.fy = null
        cache.current[props.current.mode]!.sim.alphaTarget(0)
      }
    }

    const fingers = new Map<number, { x: number; y: number }>()
    let pinch: null | { d0: number; k0: number; wx: number; wy: number } = null
    let lastTap = { t: 0, x: 0, y: 0 }
    const twoFingers = () => {
      const [a, b] = [...fingers.values()] as [{ x: number; y: number }, { x: number; y: number }]
      return { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
    }

    const down = (e: PointerEvent) => {
      canvas.setPointerCapture(e.pointerId)
      const cam = camOf()!
      if (e.pointerType === 'touch') {
        fingers.set(e.pointerId, { x: e.clientX, y: e.clientY })
        if (fingers.size >= 2) {
          // A second finger turns the gesture into a pinch, and whatever the
          // first was doing stops.
          letGo(); s.drag = null; s.target = null
          const f = twoFingers(), w = world({ clientX: f.x, clientY: f.y })
          pinch = { d0: f.d, k0: cam.k, wx: w.x, wy: w.y }
          return
        }
      }
      // A finger pans wherever it lands; a cursor on a node pulls it.
      const n = e.pointerType === 'touch' ? null : hit(e)
      s.drag = { node: n ?? undefined, sx: e.clientX, sy: e.clientY, moved: false, cx: cam.x, cy: cam.y }
      // Lectures and topics can be pulled on; a concept rides its ring.
      if (n && n.kind !== 'concept' && n.slot >= 0 && n.fx == null) {
        n.fx = n.x; n.fy = n.y
        cache.current[props.current.mode]!.sim.alphaTarget(0.08).restart()
      }
      if (!n) canvas.style.cursor = 'grabbing'
    }
    const move = (e: PointerEvent) => {
      if (e.pointerType === 'touch' && fingers.has(e.pointerId)) fingers.set(e.pointerId, { x: e.clientX, y: e.clientY })
      const cam = camOf()
      if (pinch && cam && fingers.size >= 2) {
        const f = twoFingers()
        const next = pinTo(pinch.wx, pinch.wy, f.x, f.y, clampK(pinch.k0 * (f.d / pinch.d0)))
        cam.x = next.x; cam.y = next.y; cam.k = next.k
        s.moved[props.current.mode] = true
        return
      }
      const d = s.drag
      if (!d) { if (e.pointerType !== 'touch') setHov(hit(e)); return }
      const dx = e.clientX - d.sx, dy = e.clientY - d.sy
      if (Math.hypot(dx, dy) > (e.pointerType === 'touch' ? 8 : 4)) d.moved = true
      if (!cam) return
      if (d.node && d.node.kind !== 'concept' && d.node.slot >= 0) {
        const w = world(e)
        d.node.fx = w.x; d.node.fy = w.y
      } else if (!d.node && d.moved) {
        cam.x = d.cx - dx / cam.k; cam.y = d.cy - dy / cam.k
        s.target = null
        s.moved[props.current.mode] = true
      }
    }
    const up = (e: PointerEvent) => {
      if (e.pointerType === 'touch') {
        fingers.delete(e.pointerId)
        if (pinch) {
          // Lifting one finger of a pinch carries on as a pan with the other,
          // and never counts as a tap.
          if (fingers.size < 2) pinch = null
          const rest = [...fingers.values()][0]
          const cam = camOf()
          s.drag = rest && cam && !pinch ? { sx: rest.x, sy: rest.y, moved: true, cx: cam.x, cy: cam.y } : null
          return
        }
      }
      const d = s.drag
      letGo()
      s.drag = null
      canvas.style.cursor = s.hover ? 'pointer' : 'grab'
      if (!d || d.moved) return
      const n = hit(e)
      if (n) {
        s.clicked = n.id
        onFocusRef.current(focusFor(n))
        return
      }
      // A double tap on the sky zooms in on the spot, as maps do.
      const now = performance.now(), cam = camOf()
      if (e.pointerType === 'touch' && cam && now - lastTap.t < 320 && Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < 30) {
        const w = world(e)
        s.target = pinTo(w.x, w.y, e.clientX, e.clientY, clampK(cam.k * 1.8))
        s.moved[props.current.mode] = true
        lastTap = { t: 0, x: 0, y: 0 }
        return
      }
      lastTap = { t: now, x: e.clientX, y: e.clientY }
      onFocusRef.current(null)
    }
    const cancel = (e: PointerEvent) => {
      fingers.delete(e.pointerId)
      if (fingers.size < 2) pinch = null
      letGo(); s.drag = null
    }
    const leave = (e: PointerEvent) => { if (!s.drag && e.pointerType !== 'touch') setHov(null) }
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      const cam = camOf()
      if (!cam) return
      const before = world(e)
      cam.k = clampK(cam.k * Math.exp(-e.deltaY * 0.0016))
      const after = world(e)
      cam.x += before.x - after.x; cam.y += before.y - after.y
      s.target = null
      s.moved[props.current.mode] = true
    }
    canvas.addEventListener('pointerdown', down)
    canvas.addEventListener('pointermove', move)
    canvas.addEventListener('pointerup', up)
    canvas.addEventListener('pointercancel', cancel)
    canvas.addEventListener('pointerleave', leave)
    canvas.addEventListener('wheel', wheel, { passive: false })
    return () => {
      canvas.removeEventListener('pointerdown', down)
      canvas.removeEventListener('pointermove', move)
      canvas.removeEventListener('pointerup', up)
      canvas.removeEventListener('pointercancel', cancel)
      canvas.removeEventListener('pointerleave', leave)
      canvas.removeEventListener('wheel', wheel)
    }
  }, [])
  // Where a node is on screen right now, in client pixels, for the guide.
  useEffect(() => {
    if (!locate) return
    locate.current = (id) => {
      const s = st.current, m = props.current.mode
      const g = cache.current[m], cam = s.cams[m], c = canvasRef.current
      const n = g?.nodes.find((x) => x.id === id)
      if (!n || !cam || !c) return null
      const [x, y] = s.pos.get(n) ?? drawnAt(n, s.t)
      const o = origin(s), rect = c.getBoundingClientRect()
      return { x: rect.left + (x - cam.x) * cam.k + o.x, y: rect.top + (y - cam.y) * cam.k + o.y, r: Math.max(s.compact ? 13 : 6, n.r * cam.k) }
    }
    return () => { locate.current = null }
  }, [locate])

  // Moving between modes drops the hover, which belonged to the other graph.
  useEffect(() => { st.current.hover = null; setHover(null) }, [mode])

  const described = mode === 'lectures'
    ? `Knowledge graph of ${knowledge.lectures.length} lectures in ${knowledge.arcs.length} arcs, linked by ${knowledge.edges.length} citations between their notes. The index button above it lists every lecture as a button.`
    : `Knowledge graph of ${knowledge.themes.length} topics and ${knowledge.concepts.length} concepts from the index. The index button above it lists every topic as a button, and search finds any concept.`

  return (
    <div ref={boxRef} className="kg-canvas absolute inset-0 overflow-hidden">
      <canvas ref={canvasRef} role="img" aria-label={described} className="block touch-none" style={{ cursor: 'grab' }} />
      <div ref={tipRef} aria-hidden
           className={`glass pointer-events-none absolute left-0 top-0 z-10 max-w-[300px] rounded-xl px-3 py-2 text-sm transition-opacity duration-150
                       ${hover ? 'opacity-100' : 'opacity-0'}`}>
        {hover && <TipBody n={hover} />}
      </div>
    </div>
  )
}

function TipBody({ n }: { n: GNode }) {
  if (n.kind === 'lecture') {
    const l = lectureById(n.id)!
    return (
      <>
        <p className="text-[11px] uppercase tracking-wide text-[var(--muted)]">{l.arc}</p>
        <p className="font-semibold leading-snug">{l.session} · {l.title}</p>
        {l.released
          ? <>
              {l.takeaways?.[0] && <p className="mt-1 text-xs leading-relaxed">{l.takeaways[0]}</p>}
              <p className="mt-1.5 text-[11px] text-[var(--muted)]">Click for key points, concepts and applications</p>
            </>
          : <p className="mt-1 text-xs text-[var(--muted)]">Opens on {l.date}.</p>}
      </>
    )
  }
  if (n.kind === 'theme') {
    const t = themeById(n.id.slice(6))!
    return (
      <>
        <p className="text-[11px] uppercase tracking-wide text-[var(--muted)]">Topic</p>
        <p className="font-semibold leading-snug">{t.name}</p>
        <p className="mt-1 text-xs leading-relaxed">{t.blurb}</p>
      </>
    )
  }
  const c = conceptById(n.id.slice(8))!
  const l = lectureById(c.lecture)!
  return (
    <>
      <p className="text-[11px] uppercase tracking-wide text-[var(--muted)]">{KIND_LABEL[c.kind]}</p>
      <p className="font-semibold leading-snug">{c.term}</p>
      <p className="mt-1 text-xs text-[var(--muted)]">{l.session}{c.section ? ` · ${c.section}` : ''}</p>
    </>
  )
}
