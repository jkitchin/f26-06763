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
 * first frame, so the graph opens settled rather than flying in. The idle drift
 * is drawn on top of the rest positions, a slow wobble per node with its own
 * phase, so the graph looks alive without the layout ever changing under the
 * reader's eye. Light flows along a highlighted link from the lecture that
 * explains an idea to the lecture that uses it. With reduced motion asked for,
 * none of that runs, and the picture is the same, only still.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  KIND_LABEL, conceptById, knowledge, lectureById, themeById, type ConceptKind,
} from '../map/knowledge.ts'
import { lectureGraph, settle, topicGraph, type GLink, type GNode, type Graph, type Mode } from '../map/layout.ts'
import type { Focus } from './InfoPanel.tsx'

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
const STARS = Array.from({ length: 170 }, (_, i) => {
  const s = Math.sin(i * 12.9898) * 43758.5453
  const r = Math.sin(i * 78.233) * 12345.6789
  return { x: s - Math.floor(s), y: r - Math.floor(r), z: 0.3 + ((i * 37) % 10) / 14, p: i * 1.7 }
})

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

function fitCam(g: Graph, w: number, h: number): Cam {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  for (const n of g.nodes) {
    x0 = Math.min(x0, n.x! - n.r); y0 = Math.min(y0, n.y! - n.r)
    x1 = Math.max(x1, n.x! + n.r); y1 = Math.max(y1, n.y! + n.r)
  }
  const pad = 90
  const k = Math.min(w / (x1 - x0 + pad * 2), h / (y1 - y0 + pad * 2))
  return { x: (x0 + x1) / 2, y: (y0 + y1) / 2, k: Math.max(0.25, Math.min(k, 1.6)) }
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
}

export function KnowledgeGraph({ mode, focus, onFocus, theme, reduceMotion, kindFilter, resetKey }: Props) {
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
  })
  const props = useRef({ mode, focus, kindFilter, reduceMotion, theme })
  props.current = { mode, focus, kindFilter, reduceMotion, theme }

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
      st.current.w = w; st.current.h = h
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(box)
    return () => ro.disconnect()
  }, [])

  // Each mode keeps its own camera, fitted the first time it opens.
  useEffect(() => {
    const s = st.current
    if (!s.cams[mode] && s.w) s.cams[mode] = fitCam(graph, s.w, s.h)
  }, [mode, graph])
  useEffect(() => {
    const s = st.current
    if (resetKey && s.w) s.target = fitCam(graph, s.w, s.h)
  }, [resetKey, graph])

  // A focus that came from outside the canvas (the panel, search, the tour)
  // glides the camera to it. One that came from a click on the canvas does not:
  // the reader is already looking there.
  useEffect(() => {
    const s = st.current
    const id = nodeIdFor(focus, mode)
    if (!id || s.clicked === id) { s.clicked = null; return }
    const n = graph.nodes.find((x) => x.id === id)
    const cam = s.cams[mode]
    if (n && cam) s.target = { x: n.x!, y: n.y!, k: Math.max(cam.k, n.kind === 'lecture' ? 0.9 : 1.5) }
  }, [focus, mode, graph])

  // The frame loop.
  useEffect(() => {
    const canvas = canvasRef.current!
    const ctx = canvas.getContext('2d')!
    let raf = 0

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame)
      const s = st.current
      const { mode, focus, kindFilter, reduceMotion, theme } = props.current
      const p = s.palette ?? (s.palette = readPalette(boxRef.current!))
      const g = cache.current[mode]
      if (!g || !s.w) return
      const cam = s.cams[mode] ?? (s.cams[mode] = fitCam(g, s.w, s.h))
      if (s.target) {
        const e = reduceMotion ? 1 : 0.12
        cam.x += (s.target.x - cam.x) * e; cam.y += (s.target.y - cam.y) * e; cam.k += (s.target.k - cam.k) * e
        if (Math.abs(s.target.x - cam.x) < 0.5 && Math.abs(s.target.k - cam.k) < 0.002) s.target = null
      }
      const t = reduceMotion ? 0 : now
      const dpr = canvas.width / s.w
      const W = s.w, H = s.h
      const dark = theme === 'dark'

      // Rendered position: the rest position plus the idle drift.
      const amp = (n: GNode) => (n.kind === 'concept' ? 2.6 : n.kind === 'theme' ? 6 : 5)
      const px = (n: GNode) => n.x! + amp(n) * Math.sin(t * 0.00042 + n.phase)
      const py = (n: GNode) => n.y! + amp(n) * Math.cos(t * 0.00035 + n.phase * 1.3)
      const sx = (x: number) => (x - cam.x) * cam.k + W / 2
      const sy = (y: number) => (y - cam.y) * cam.k + H / 2

      // What is lit: the hovered or selected node and its neighbours, or a kind filter.
      const focusId = s.hover?.id ?? nodeIdFor(focus, mode)
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
        const cx = ns.reduce((a, n) => a + n.x!, 0) / ns.length
        const cy = ns.reduce((a, n) => a + n.y!, 0) / ns.length
        const rad = Math.max(...ns.map((n) => Math.hypot(n.x! - cx, n.y! - cy) + n.r)) + (mode === 'topics' ? 120 : 70)
        const grad = ctx.createRadialGradient(sx(cx), sy(cy), 0, sx(cx), sy(cy), rad * cam.k)
        grad.addColorStop(0, colorOf(p, slot)); grad.addColorStop(1, 'transparent')
        ctx.globalAlpha = dark ? 0.13 : 0.08
        ctx.fillStyle = grad
        ctx.beginPath(); ctx.arc(sx(cx), sy(cy), rad * cam.k, 0, Math.PI * 2); ctx.fill()
        const d = Math.hypot(cx, cy) || 1
        const lx = cx + (cx / d) * rad * 0.82, ly = cy + (cy / d) * rad * 0.82
        labs.push({ txt: (knowledge.arcs[slot] ?? '').toUpperCase(), x: sx(lx), y: sy(ly), size: 11, weight: 600,
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
        ctx.lineWidth = l.kind === 'cite' || l.kind === 'theme' ? 1.2 + 0.4 * Math.min(l.weight, 3) : 0.8
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
        const r = Math.max(n.kind === 'concept' ? 2.2 : 6, n.r * cam.k) * (s.hover?.id === n.id ? 1.18 : 1)
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
        const r = Math.max(n.kind === 'concept' ? 2.2 : 6, n.r * cam.k)
        const vis = on(n.id)
        const must = n.id === s.hover?.id || n.id === selId
        if (n.kind === 'lecture') {
          ctx.globalAlpha = vis ? 1 : 0.25
          ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
          ctx.font = `700 ${Math.max(10, Math.min(15, r * 0.75))}px ${FONT}`
          ctx.fillStyle = n.released ? '#fff' : p.muted
          ctx.fillText(n.label, x, y + 0.5)
          if (cam.k > 0.45 || must) {
            const date = lectureById(n.id)?.date.slice(5).replace('-', '/') ?? ''
            labs.push({ txt: n.released ? n.sub : `${n.sub} · opens ${date}`, x, y: y + r + 6, altY: y - r - 21, size: 11.5,
                        weight: n.slot < 0 ? 650 : 500, align: 'center', base: 'top',
                        color: vis ? p.ink : p.muted, alpha: vis ? 1 : 0.35, pri: n.slot < 0 ? 90 : vis && lit ? 70 : 50, must })
          }
        } else if (n.kind === 'theme') {
          const below = Math.max(r, (n.r + 38) * cam.k) + 5
          labs.push({ txt: n.label, sub: n.sub, x, y: y + below, altY: y - below - 31, size: 12.5, weight: 650, align: 'center', base: 'top',
                      color: p.ink, alpha: vis ? 1 : 0.35, pri: vis && lit ? 85 : 60, must })
        } else {
          const near = focusId && vis && (focusId.startsWith('theme:') || focusId === n.id)
          const kindLit = !focusId && kindFilter && n.conceptKind === kindFilter
          if (!(cam.k >= 1.5 && vis) && !near && !kindLit && !must) continue
          const c = conceptById(n.id.slice(8))
          const t0 = c ? themePos(g, c.theme) : null
          const right = !t0 || n.x! >= t0[0]
          labs.push({ txt: n.label, x: x + (right ? r + 5 : -r - 5), y, size: 11, weight: must ? 650 : 500,
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
        const rr = Math.max(6, n.r * cam.k)
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
        const x0 = L.align === 'left' ? L.x : L.align === 'right' ? L.x - w : L.x - w / 2
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
        const left = Math.min(Math.max(x + 18, 8), W - tip.offsetWidth - 8)
        const top = y - tip.offsetHeight - 14 > 8 ? y - tip.offsetHeight - 14 : y + 22
        tip.style.transform = `translate(${left}px, ${top}px)`
      }
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [])

  const onFocusRef = useRef(onFocus)
  onFocusRef.current = onFocus

  // Pointer: hover, click, drag a node, drag the sky to pan, wheel to zoom.
  useEffect(() => {
    const canvas = canvasRef.current!
    const s = st.current
    const world = (e: { clientX: number; clientY: number }) => {
      const rect = canvas.getBoundingClientRect()
      const cam = s.cams[props.current.mode]!
      return { x: (e.clientX - rect.left - s.w / 2) / cam.k + cam.x, y: (e.clientY - rect.top - s.h / 2) / cam.k + cam.y }
    }
    const hit = (e: PointerEvent) => {
      const g = cache.current[props.current.mode]
      const cam = s.cams[props.current.mode]
      if (!g || !cam) return null
      const w = world(e)
      let best: GNode | null = null, bd = Infinity
      for (const n of g.nodes) {
        const d = Math.hypot(n.x! - w.x, n.y! - w.y)
        const reach = Math.max(n.r, (n.kind === 'concept' ? 7 : 10) / cam.k) + 2 / cam.k
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
    const down = (e: PointerEvent) => {
      canvas.setPointerCapture(e.pointerId)
      const n = hit(e)
      const cam = s.cams[props.current.mode]!
      s.drag = { node: n ?? undefined, sx: e.clientX, sy: e.clientY, moved: false, cx: cam.x, cy: cam.y }
      if (n && n.fx === undefined || n && n.fx === null) {
        n.fx = n.x; n.fy = n.y
        cache.current[props.current.mode]!.sim.alphaTarget(0.08).restart()
      }
      if (!n) canvas.style.cursor = 'grabbing'
    }
    const move = (e: PointerEvent) => {
      const d = s.drag
      if (!d) { setHov(hit(e)); return }
      const dx = e.clientX - d.sx, dy = e.clientY - d.sy
      if (Math.hypot(dx, dy) > 4) d.moved = true
      const cam = s.cams[props.current.mode]!
      if (d.node && d.node.slot >= 0) {
        const w = world(e)
        d.node.fx = w.x; d.node.fy = w.y
      } else if (!d.node) {
        cam.x = d.cx - dx / cam.k; cam.y = d.cy - dy / cam.k
        s.target = null
      }
    }
    const up = (e: PointerEvent) => {
      const d = s.drag
      s.drag = null
      canvas.style.cursor = s.hover ? 'pointer' : 'grab'
      if (!d) return
      if (d.node && d.node.slot >= 0) {
        d.node.fx = null; d.node.fy = null
        cache.current[props.current.mode]!.sim.alphaTarget(0)
      }
      if (d.moved) return
      const n = hit(e)
      if (n) {
        s.clicked = n.id
        onFocusRef.current(focusFor(n))
      } else onFocusRef.current(null)
    }
    const leave = () => { if (!s.drag) setHov(null) }
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      const cam = s.cams[props.current.mode]
      if (!cam) return
      const before = world(e)
      cam.k = Math.max(0.25, Math.min(4, cam.k * Math.exp(-e.deltaY * 0.0016)))
      const after = world(e)
      cam.x += before.x - after.x; cam.y += before.y - after.y
      s.target = null
    }
    canvas.addEventListener('pointerdown', down)
    canvas.addEventListener('pointermove', move)
    canvas.addEventListener('pointerup', up)
    canvas.addEventListener('pointerleave', leave)
    canvas.addEventListener('wheel', wheel, { passive: false })
    return () => {
      canvas.removeEventListener('pointerdown', down)
      canvas.removeEventListener('pointermove', move)
      canvas.removeEventListener('pointerup', up)
      canvas.removeEventListener('pointerleave', leave)
      canvas.removeEventListener('wheel', wheel)
    }
  }, [])
  // Moving between modes drops the hover, which belonged to the other graph.
  useEffect(() => { st.current.hover = null; setHover(null) }, [mode])

  const described = mode === 'lectures'
    ? `Knowledge graph of ${knowledge.lectures.length} lectures in ${knowledge.arcs.length} arcs, linked by ${knowledge.edges.length} citations between their notes. The panel beside it lists every lecture as a button.`
    : `Knowledge graph of ${knowledge.themes.length} topics and ${knowledge.concepts.length} concepts from the index. The panel beside it lists every topic as a button, and search finds any concept.`

  return (
    <div ref={boxRef} className="kg-canvas relative h-[min(74vh,760px)] min-h-[420px] w-full overflow-hidden rounded-2xl border border-[var(--border)]">
      <canvas ref={canvasRef} role="img" aria-label={described} className="block touch-none" style={{ cursor: 'grab' }} />
      <div ref={tipRef} aria-hidden
           className={`pointer-events-none absolute left-0 top-0 max-w-[300px] rounded-xl border border-[var(--border)]
                       bg-[var(--surface-raised)] px-3 py-2 text-sm shadow-xl transition-opacity duration-150
                       ${hover ? 'opacity-100' : 'opacity-0'}`}>
        {hover && <TipBody n={hover} />}
      </div>
    </div>
  )
}

function themePos(g: Graph, theme: string): [number, number] | null {
  const n = g.nodes.find((x) => x.id === `theme:${theme}`)
  return n ? [n.x!, n.y!] : null
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
