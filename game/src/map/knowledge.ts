/**
 * The knowledge graph and the live system figure: types over the generated
 * `knowledge.json`, and the lookups the two views share.
 *
 * Nothing here is authored. `tools/knowledge.py` extracts the lectures, links,
 * objectives, concepts and case studies from the notes, takes the themes,
 * takeaways and system boxes from `game/content/knowledge.yml`, and CI fails if
 * the committed JSON drifts from either. An unreleased lecture arrives with its
 * number, title, date and arc only, so nothing here can show it early.
 */

// The import attribute is required by node, which runs tests/knowledge.ts
// directly with --experimental-strip-types. Vite and tsc both accept it.
import raw from './knowledge.json' with { type: 'json' }

export interface Lecture {
  id: string
  session: string
  title: string
  date: string
  arc: string
  released: boolean
  theme: string
  notes?: string
  slides?: string
  takeaways?: string[]
  data?: string
  objectives?: string[]
  themes?: string[]
  cases?: string[]
}

export interface Link { from: string; to: string; weight: number; where: string }

export interface Theme { id: string; name: string; blurb: string; lectures: string[]; arc: string }

export type ConceptKind = 'concept' | 'case' | 'failure' | 'metric'

export interface Concept {
  id: string
  term: string
  kind: ConceptKind
  lecture: string
  section: string
  href: string
  theme: string
  also: string[]
}

export interface CaseStudy { id: string; title: string; field: string; lectures: string[]; href: string }

export interface Box {
  id: string
  label: string
  x: number; y: number; w: number; h: number
  blurb: string
  lectures: string[]
  tools: { term: string; concept: string; lecture: string }[]
}

export interface Knowledge {
  arcs: string[]
  lectures: Lecture[]
  edges: Link[]
  themes: Theme[]
  theme_edges: { a: string; b: string; weight: number }[]
  concepts: Concept[]
  cases: CaseStudy[]
  system: { canvas: [number, number]; caption: string; boxes: Box[]; flow: string[] }
}

export const knowledge = raw as unknown as Knowledge

const byId = <T extends { id: string }>(xs: T[]) => new Map(xs.map((x) => [x.id, x]))
const lectures = byId(knowledge.lectures)
const themes = byId(knowledge.themes)
const concepts = byId(knowledge.concepts)
const cases = byId(knowledge.cases)

export const lectureById = (id: string) => lectures.get(id)
export const themeById = (id: string) => themes.get(id)
export const conceptById = (id: string) => concepts.get(id)
export const caseById = (id: string) => cases.get(id)

/** The arc's index in course order, which is its colour slot. */
export const arcIndex = (arc: string) => knowledge.arcs.indexOf(arc)

/** The last arc is the wrap-up, drawn in the course red at the centre. */
export const isWrapUp = (arc: string) => arc === knowledge.arcs[knowledge.arcs.length - 1]

/** What a lecture builds on, and what builds on it, each with its sentence. */
export function linksOf(id: string) {
  const buildsOn = knowledge.edges.filter((e) => e.from === id)
    .map((e) => ({ other: lectures.get(e.to)!, where: e.where }))
  const usedBy = knowledge.edges.filter((e) => e.to === id)
    .map((e) => ({ other: lectures.get(e.from)!, where: e.where }))
  return { buildsOn, usedBy }
}

export const conceptsOfLecture = (id: string) => knowledge.concepts.filter((c) => c.lecture === id)
export const conceptsOfTheme = (id: string) => knowledge.concepts.filter((c) => c.theme === id)

/** Case studies that connect to any of these lectures. */
export const casesFor = (ids: string[]) =>
  knowledge.cases.filter((c) => c.lectures.some((l) => ids.includes(l)))

export function themeNeighbours(id: string): Theme[] {
  return knowledge.theme_edges
    .filter((e) => e.a === id || e.b === id)
    .sort((x, y) => y.weight - x.weight)
    .map((e) => themes.get(e.a === id ? e.b : e.a)!)
}

export const KIND_LABEL: Record<ConceptKind, string> = {
  concept: 'Concept', case: 'Case study', failure: 'Failure mode', metric: 'Metric',
}
