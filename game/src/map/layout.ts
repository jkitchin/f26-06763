/**
 * The two graphs as d3-force simulations, kept apart from drawing so that
 * tests/knowledge.ts can run them in node and check that they settle.
 *
 * LECTURES. One node per session on the map. Each arc pulls its lectures
 * towards its own point on a circle, in course order around the clock, so the
 * arcs read as territories; a faint trail through the lectures in order keeps
 * the course's sequence visible; and the citations from the notes are the
 * links that pull related lectures together across arcs. The wrap-up lecture
 * is pinned at the centre, since every other lecture is behind it.
 *
 * TOPICS. One heavy node per theme and one small node per index concept. A
 * concept is tied to the theme of the section that defines it, themes are tied
 * where their lectures cite each other, and each theme leans towards its arc's
 * territory so the topic view keeps the same geography as the lecture view.
 */

import {
  forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY,
  type Force, type Simulation, type SimulationLinkDatum, type SimulationNodeDatum,
} from 'd3-force'
import { arcIndex, isWrapUp, knowledge, type ConceptKind } from './knowledge.ts'

export type Mode = 'lectures' | 'topics'

export interface GNode extends SimulationNodeDatum {
  id: string
  kind: 'lecture' | 'theme' | 'concept'
  /** Colour slot: the arc index, or -1 for the wrap-up, drawn in course red. */
  slot: number
  r: number
  label: string
  sub: string
  released: boolean
  conceptKind?: ConceptKind
  /** Per-node phase for the idle drift, fixed so it does not jump on rerender. */
  phase: number
  /** A concept's distance from its theme, set when the rings are laid out. */
  ring?: number
}

export interface GLink extends SimulationLinkDatum<GNode> {
  kind: 'cite' | 'trail' | 'member' | 'theme'
  weight: number
  /** For a citation: the sentence from the citing lecture's notes. */
  where?: string
}

export interface Graph {
  nodes: GNode[]
  links: GLink[]
  sim: Simulation<GNode, GLink>
  /** Ids of each node's neighbours, for the hover highlight. */
  neighbours: Map<string, Set<string>>
  /** Runs once the simulation has settled, to place what the forces should not. */
  arrange?: () => void
}

/** Apply a force to some nodes only, by narrowing what it is initialised with. */
function only<F extends Force<GNode, GLink>>(f: F, keep: (n: GNode) => boolean): F {
  const init = f.initialize!.bind(f)
  f.initialize = (nodes: GNode[], random: () => number) => init(nodes.filter(keep), random)
  return f
}

/** Pull each node towards a ring of the given radius around its centre node. */
function orbit(ringOf: Map<GNode, GNode>, radius: (n: GNode, c: GNode) => number, strength: number) {
  let ns: GNode[] = []
  const force = (alpha: number) => {
    for (const n of ns) {
      const c = ringOf.get(n)!
      const dx = n.x! - c.x!, dy = n.y! - c.y!
      const d = Math.hypot(dx, dy) || 1e-6
      const k = ((radius(n, c) - d) / d) * alpha * strength
      n.vx = (n.vx ?? 0) + dx * k; n.vy = (n.vy ?? 0) + dy * k
      // Follow the centre as it moves, so a ring travels with its theme.
      n.vx += (c.vx ?? 0) * 0.5; n.vy += (c.vy ?? 0) * 0.5
    }
  }
  force.initialize = (nodes: GNode[]) => { ns = nodes.filter((n) => ringOf.has(n)) }
  return force
}

/** Where arc i sits: around a circle in course order, starting at ten o'clock. */
export function arcCentre(i: number, n: number, R: number): [number, number] {
  const a = -Math.PI * 0.8 + (i * 2 * Math.PI) / Math.max(n, 1)
  return [R * Math.cos(a), R * Math.sin(a)]
}

function hash(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return ((h >>> 0) % 10000) / 10000
}

/**
 * A label short enough to sit under a node. The part before a colon names the
 * lecture unless it is a series heading ("The machine learning workflow II"), in
 * which case the part after it does; a long remainder stops at its first comma
 * or "and". The full title is always in the tooltip and the panel.
 */
export function shortTitle(t: string, n = 30): string {
  let s = t.replace(/\s*\([^)]*\)/g, '')
  const [head, tail] = s.split(/:\s*/, 2)
  s = tail && /\b(I|II|III|IV)$/.test(head ?? '') ? tail : head ?? s
  if (s.length > n) s = s.split(/,| and | for /)[0]!
  s = s.charAt(0).toUpperCase() + s.slice(1)
  return s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s
}

const slotOf = (arc: string) => (isWrapUp(arc) ? -1 : arcIndex(arc))

/** The number of arcs that get a territory: all but the wrap-up. */
const TERRITORIES = Math.max(knowledge.arcs.length - 1, 1)

function neighbourMap(nodes: GNode[], links: GLink[], kinds: GLink['kind'][]) {
  const m = new Map(nodes.map((n) => [n.id, new Set<string>()]))
  for (const l of links) {
    if (!kinds.includes(l.kind)) continue
    const a = typeof l.source === 'object' ? (l.source as GNode).id : String(l.source)
    const b = typeof l.target === 'object' ? (l.target as GNode).id : String(l.target)
    m.get(a)?.add(b)
    m.get(b)?.add(a)
  }
  return m
}

export function lectureGraph(): Graph {
  const R = 470
  const degree = new Map<string, number>()
  for (const e of knowledge.edges) {
    degree.set(e.from, (degree.get(e.from) ?? 0) + 1)
    degree.set(e.to, (degree.get(e.to) ?? 0) + 1)
  }
  const nodes: GNode[] = knowledge.lectures.map((l) => {
    const slot = slotOf(l.arc)
    const [cx, cy] = slot < 0 ? [0, 0] : arcCentre(slot, TERRITORIES, R)
    const n: GNode = {
      id: l.id, kind: 'lecture', slot, released: l.released,
      r: slot < 0 ? 30 : 18 + 2.8 * Math.sqrt(degree.get(l.id) ?? 0),
      label: l.session, sub: shortTitle(l.title), phase: hash(l.id) * Math.PI * 2,
      x: cx + (hash(`${l.id}x`) - 0.5) * 80, y: cy + (hash(`${l.id}y`) - 0.5) * 80,
    }
    if (slot < 0) { n.fx = 0; n.fy = 0 }
    return n
  })

  const links: GLink[] = knowledge.edges.map((e) => ({
    source: e.from, target: e.to, kind: 'cite', weight: e.weight, where: e.where,
  }))
  const order = knowledge.lectures.filter((l) => !isWrapUp(l.arc))
  for (let i = 1; i < order.length; i++) {
    links.push({ source: order[i - 1]!.id, target: order[i]!.id, kind: 'trail', weight: 1 })
  }

  const target = (n: GNode, axis: 0 | 1) =>
    n.slot < 0 ? 0 : arcCentre(n.slot, TERRITORIES, R)[axis]
  const sim = forceSimulation<GNode, GLink>(nodes)
    .force('link', forceLink<GNode, GLink>(links).id((n) => n.id)
      .distance((l) => (l.kind === 'trail' ? 130 : 210))
      .strength((l) => (l.kind === 'trail' ? 0.3 : 0.03 + 0.02 * Math.min(l.weight, 3))))
    .force('charge', forceManyBody<GNode>().strength(-1700))
    .force('collide', forceCollide<GNode>().radius((n) => n.r + 72).strength(0.9))
    .force('x', forceX<GNode>((n) => target(n, 0)).strength(0.1))
    .force('y', forceY<GNode>((n) => target(n, 1)).strength(0.1))
    .stop()

  return { nodes, links, sim, neighbours: neighbourMap(nodes, links, ['cite']) }
}

export function topicGraph(): Graph {
  const R = 760
  const counts = new Map<string, number>()
  for (const c of knowledge.concepts) counts.set(c.theme, (counts.get(c.theme) ?? 0) + 1)
  const themeSlot = new Map(knowledge.themes.map((t) => [t.id, slotOf(t.arc)]))

  const nodes: GNode[] = knowledge.themes.map((t) => {
    const slot = themeSlot.get(t.id) ?? 0
    const [cx, cy] = slot < 0 ? [0, 0] : arcCentre(slot, TERRITORIES, R)
    return {
      id: `theme:${t.id}`, kind: 'theme', slot, released: true,
      r: 16 + 1.7 * Math.sqrt(counts.get(t.id) ?? 0),
      label: t.name, sub: t.lectures.map((l) => l.toUpperCase().replace('L0', 'L')).join(' '),
      phase: hash(t.id) * Math.PI * 2,
      x: cx + (hash(`${t.id}x`) - 0.5) * 160, y: cy + (hash(`${t.id}y`) - 0.5) * 160,
    }
  })
  const themeNode = new Map(nodes.map((n) => [n.id, n]))
  for (const c of knowledge.concepts) {
    const t = themeNode.get(`theme:${c.theme}`)!
    const a = hash(c.id) * Math.PI * 2
    nodes.push({
      id: `concept:${c.id}`, kind: 'concept', slot: t.slot, released: true,
      r: c.kind === 'concept' ? 3.4 : 4.6, conceptKind: c.kind,
      label: c.term, sub: '', phase: hash(`${c.id}p`) * Math.PI * 2,
      x: (t.x ?? 0) + Math.cos(a) * (t.r + 30), y: (t.y ?? 0) + Math.sin(a) * (t.r + 30),
    })
  }

  const links: GLink[] = knowledge.concepts.map((c) => ({
    source: `concept:${c.id}`, target: `theme:${c.theme}`, kind: 'member', weight: 1,
  }))
  for (const e of knowledge.theme_edges) {
    links.push({ source: `theme:${e.a}`, target: `theme:${e.b}`, kind: 'theme', weight: e.weight })
  }

  // Concepts orbit their own theme on a ring, and only themes push on themes.
  // A theme's repulsion acting on every concept would sweep its concepts into a
  // crescent on the side away from the other themes, which reads as a smear.
  const isTheme = (n: GNode) => n.kind === 'theme'
  const ringOf = new Map<GNode, GNode>()
  for (const n of nodes) {
    if (n.kind === 'concept') {
      const c = knowledge.concepts.find((x) => `concept:${x.id}` === n.id)!
      ringOf.set(n, themeNode.get(`theme:${c.theme}`)!)
    }
  }
  const target = (n: GNode, axis: 0 | 1) =>
    n.slot < 0 ? 0 : arcCentre(n.slot, TERRITORIES, R)[axis]
  const sim = forceSimulation<GNode, GLink>(nodes)
    .force('link', forceLink<GNode, GLink>(links).id((n) => n.id)
      .distance(270)
      .strength((l) => (l.kind === 'theme' ? 0.015 + 0.01 * Math.min(l.weight, 4) : 0)))
    .force('orbit', orbit(ringOf, (n, t) => n.ring ?? t.r + 30, 0.5))
    .force('charge', only(forceManyBody<GNode>().strength(-4200), isTheme))
    .force('collide', only(forceCollide<GNode>().radius((n) => n.r + 150), isTheme))
    .force('x', only(forceX<GNode>((n) => target(n, 0)).strength(0.07), isTheme))
    .force('y', only(forceY<GNode>((n) => target(n, 1)).strength(0.07), isTheme))
    .stop()

  // Once the themes have settled, each theme's concepts go evenly round it on
  // two rings, in the order the notes define them, so neighbours on a ring
  // tend to share a lecture section. The orbit force then only keeps the ring
  // with its theme when someone drags it.
  const arrange = () => {
    const byTheme = new Map<GNode, GNode[]>()
    for (const [n, t] of ringOf) {
      const list = byTheme.get(t) ?? []
      list.push(n); byTheme.set(t, list)
    }
    for (const [t, ns] of byTheme) {
      ns.forEach((n, i) => {
        const a = (2 * Math.PI * i) / ns.length + t.phase
        n.ring = t.r + 20 + (i % 2) * 15
        n.x = t.x! + Math.cos(a) * n.ring; n.y = t.y! + Math.sin(a) * n.ring
        n.vx = 0; n.vy = 0
      })
    }
  }

  return { nodes, links, sim, neighbours: neighbourMap(nodes, links, ['member', 'theme']), arrange }
}

/** Run a simulation to rest without drawing, so a view opens already settled. */
export function settle(g: Graph, ticks = 400): void {
  g.sim.alpha(1)
  for (let i = 0; i < ticks; i++) g.sim.tick()
  g.arrange?.()
  g.sim.alpha(0)
}
