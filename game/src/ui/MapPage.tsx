/**
 * The course map, as three tabs over the same course.
 *
 *   #/map         the knowledge graph: lectures, or topics and concepts
 *   #/map/system  Lecture 1's system figure, live, with the course mapped onto it
 *   #/map/rooms   the walkable rooms, unchanged
 *
 * The graph and the system figure record nothing, so they open without an
 * Andrew ID: they are for review and for projecting in class, and a login in
 * front of a picture is friction with no purpose. The rooms record visits in
 * the student's log, so that tab still asks who you are.
 *
 * The graph and the figure fill the window, and every control floats over them
 * on frosted glass. The controls report how much of the screen they cover
 * (`view` and `panel`), and the graph fits itself to what is left. A first
 * visit to the graph opens a short guide (MapGuide.tsx), which the Guide
 * button replays.
 *
 * Like the rooms, nothing here scores, streaks or ranks: the course's own
 * reading on generating versus learning is why. What the page offers instead is
 * structure, and a tour that walks the course in order for a quick review.
 */

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Bank } from '../content/load.ts'
import { knowledge, type ConceptKind } from '../map/knowledge.ts'
import type { Mode } from '../map/layout.ts'
import type { MapTab } from '../route.ts'
import { InfoPanel, arcVar, type Focus } from './InfoPanel.tsx'
import { KnowledgeGraph, type PanelBox, type View } from './KnowledgeGraph.tsx'
import { MapGuide, guideSeen, type GuideStep, type Locate } from './MapGuide.tsx'
import { SystemView } from './SystemView.tsx'
import { useReducedMotion, useTheme, type ThemeChoice } from './theme.ts'

const COURSE = 'Systems and Toolchains for AI Engineers'

function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: { v: T; label: string }[]; onChange: (v: T) => void; label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex gap-0.5">
      {options.map((o) => (
        <button key={o.v} type="button" role="radio" aria-checked={value === o.v} onClick={() => onChange(o.v)}
                className="glass-btn">
          {o.label}
        </button>
      ))}
    </div>
  )
}

interface Hit { focus: Focus & object; label: string; kind: string }

function search(q: string): Hit[] {
  const s = q.trim().toLowerCase()
  if (s.length < 2) return []
  const out: Hit[] = []
  for (const l of knowledge.lectures) {
    if (`${l.session} ${l.title}`.toLowerCase().includes(s)) {
      out.push({ focus: { type: 'lecture', id: l.id }, label: `${l.session} · ${l.title}`, kind: 'Lecture' })
    }
  }
  for (const t of knowledge.themes) {
    if (t.name.toLowerCase().includes(s)) out.push({ focus: { type: 'theme', id: t.id }, label: t.name, kind: 'Topic' })
  }
  for (const c of knowledge.concepts) {
    if (c.term.toLowerCase().includes(s)) {
      out.push({ focus: { type: 'concept', id: c.id }, label: c.term, kind: c.lecture.toUpperCase().replace('L0', 'L') })
    }
  }
  return out.slice(0, 9)
}

const KINDS: { v: ConceptKind; label: string; shape: string }[] = [
  { v: 'failure', label: 'Failure modes', shape: '▲' },
  { v: 'case', label: 'Case studies', shape: '◆' },
  { v: 'metric', label: 'Metrics', shape: '■' },
]

/** The released lecture with the most links, which the guide demonstrates on. */
function hubLecture(): string {
  const deg = new Map<string, number>()
  for (const e of knowledge.edges) {
    deg.set(e.from, (deg.get(e.from) ?? 0) + 1)
    deg.set(e.to, (deg.get(e.to) ?? 0) + 1)
  }
  const released = knowledge.lectures.filter((l) => l.released)
  released.sort((a, b) => (deg.get(b.id) ?? 0) - (deg.get(a.id) ?? 0))
  return released[0]?.id ?? knowledge.lectures[0]!.id
}

const WIDE = '(min-width: 1024px)'
function useWide(): boolean {
  const [wide, setWide] = useState(() => window.matchMedia(WIDE).matches)
  useEffect(() => {
    const m = window.matchMedia(WIDE)
    const on = () => setWide(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return wide
}

const NO_VIEW: View = { t: 0, r: 0, b: 0, l: 0 }

export function MapPage({ tab, banks, rooms, onTab, onPractice, onList }: {
  tab: MapTab
  banks: Record<string, Bank>
  rooms: React.ReactNode
  onTab: (t: MapTab) => void
  onPractice: (lecture: string) => void
  onList: () => void
}) {
  const [themeChoice, setThemeChoice, resolved] = useTheme()
  const reduceMotion = useReducedMotion()
  const wide = useWide()
  const [mode, setMode] = useState<Mode>('lectures')
  const [focus, setFocus] = useState<Focus>(null)
  const [indexOpen, setIndexOpen] = useState(false)
  const [kindFilter, setKindFilter] = useState<ConceptKind | null>(null)
  const [resetKey, setResetKey] = useState(0)
  const [showTools, setShowTools] = useState(false)
  const [q, setQ] = useState('')
  const [touring, setTouring] = useState(false)
  const [guideOpen, setGuideOpen] = useState(false)
  const [spotlight, setSpotlight] = useState<string | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const locate = useRef<Locate | null>(null)
  const hits = useMemo(() => search(q), [q])

  const stageRef = useRef<HTMLDivElement>(null)
  const headRef = useRef<HTMLElement>(null)
  const footRef = useRef<HTMLDivElement>(null)
  const paneRef = useRef<HTMLDivElement>(null)
  const [view, setView] = useState<View>(NO_VIEW)
  const [panelBox, setPanelBox] = useState<PanelBox | null>(null)
  const panelOpen = tab !== 'rooms' && (!!focus || indexOpen)

  // Selecting something moves to the view that shows it.
  const select = (f: Focus) => {
    if (f?.type === 'lecture') setMode('lectures')
    if (f?.type === 'theme' || f?.type === 'concept') { setMode('topics'); setKindFilter(null) }
    if (f && f.type !== 'box' && tab === 'system') onTab('graph')
    setFocus(f)
  }
  const closePanel = () => { setFocus(null); setIndexOpen(false) }
  const toggleIndex = () => {
    if (!focus && indexOpen) setIndexOpen(false)
    else { setFocus(null); setIndexOpen(true) }
  }

  // How much of the stage the floating controls cover, so the graph can fit
  // itself to the rest and keep a selected node out from under the panel.
  useLayoutEffect(() => {
    const stage = stageRef.current
    if (!stage) return
    const measure = () => {
      const S = stage.getBoundingClientRect()
      const head = headRef.current?.getBoundingClientRect()
      const foot = footRef.current?.getBoundingClientRect()
      const pane = paneRef.current?.getBoundingClientRect()
      const v: View = {
        t: head ? Math.round(head.bottom - S.top + 4) : 0,
        b: foot ? Math.round(S.bottom - foot.top + 4) : 0,
        r: 0, l: 0,
      }
      setView((p) => (p.t === v.t && p.b === v.b ? p : v))
      const pb: PanelBox | null = !pane || pane.width === 0 ? null
        : pane.left > S.left + 40 ? { side: 'right', size: Math.round(S.right - pane.left + 6) }
          : { side: 'bottom', size: Math.round(S.bottom - pane.top + 6) }
      setPanelBox((p) => (p?.side === pb?.side && p?.size === pb?.size ? p : pb))
    }
    measure()
    const ro = new ResizeObserver(measure)
    for (const el of [stage, headRef.current, footRef.current, paneRef.current]) if (el) ro.observe(el)
    return () => ro.disconnect()
  }, [tab, panelOpen, mode, focus, wide])

  // The tour walks the released lectures in course order, one every few seconds,
  // for a quick review or to project at the start of a class. Any key or click
  // on the page stops it.
  useEffect(() => {
    if (!touring) return
    const stops = knowledge.lectures.filter((l) => l.released)
    let i = 0
    setMode('lectures')
    const next = () => {
      const stop = stops[i++]
      if (!stop) { setTouring(false); return }
      setFocus({ type: 'lecture', id: stop.id })
    }
    next()
    const timer = window.setInterval(next, 5200)
    const stopTour = () => setTouring(false)
    const t0 = window.setTimeout(() => {
      window.addEventListener('keydown', stopTour)
      window.addEventListener('pointerdown', stopTour)
    }, 100)
    return () => {
      window.clearInterval(timer); window.clearTimeout(t0)
      window.removeEventListener('keydown', stopTour)
      window.removeEventListener('pointerdown', stopTour)
    }
  }, [touring])

  // A first visit to the graph opens the guide once the page has settled.
  const guideShown = useRef(false)
  useEffect(() => {
    if (tab !== 'graph' || guideShown.current || guideSeen()) return
    const t = window.setTimeout(() => { guideShown.current = true; setGuideOpen(true) }, 700)
    return () => window.clearTimeout(t)
  }, [tab])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) {
        if (e.key === 'Escape') { setQ(''); el.blur() }
        return
      }
      if (e.key === 'Escape') closePanel()
      if (e.key === '/' && tab === 'graph') { e.preventDefault(); searchRef.current?.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tab])

  useEffect(() => {
    setFocus((f) => (tab === 'graph' && f?.type === 'box') || (tab === 'system' && f && f.type !== 'box') ? null : f)
    if (tab !== 'graph') setGuideOpen(false)
  }, [tab])

  const hub = useMemo(hubLecture, [])
  const hubName = knowledge.lectures.find((l) => l.id === hub)?.session ?? 'a lecture'
  const guide: GuideStep[] = [
    {
      title: 'The course as a map',
      body: 'Each circle is a lecture, coloured by the part of the course it belongs to. A line joins two lectures when the notes of one cite the other. Seven short steps show you around.',
      anchor: { kind: 'page' },
      enter: () => {
        setTouring(false); setSpotlight(null); setFocus(null); setIndexOpen(false)
        setMode('lectures'); setKindFilter(null); setResetKey((k) => k + 1)
      },
    },
    {
      title: 'Point at a lecture',
      body: `Hovering lights up what a lecture builds on and what builds on it, shown here for ${hubName}. The moving dots run from the lecture that explains an idea to the one that uses it.`,
      anchor: { kind: 'node', id: hub },
      dim: false,
      enter: () => { setFocus(null); setSpotlight(hub) },
    },
    {
      title: 'Click to open it',
      body: 'The panel shows the lecture\'s takeaways, its key points, where its ideas are applied, and the sentence behind each link. Its notes, slides and practice module are one click away.',
      anchor: { kind: 'control', name: 'panel', inner: 'aside' },
      enter: () => { setSpotlight(null); setFocus({ type: 'lecture', id: hub }) },
    },
    {
      title: 'By lecture or by topic',
      body: 'By topic regroups the course into themes, with every concept from the index on a ring around its theme. Chips there light up every failure mode, case study or metric in the course at once.',
      anchor: { kind: 'control', name: 'modes' },
      enter: () => { setSpotlight(null); setFocus(null); setResetKey((k) => k + 1) },
    },
    {
      title: 'Find anything',
      body: 'Search for a lecture, a topic or a concept, and the map moves to it. Press / anywhere on the page to jump to the search box.',
      anchor: { kind: 'control', name: 'search' },
    },
    {
      title: 'Review the whole course',
      body: 'Tour the course opens each lecture in order, a few seconds each, which makes a quick review before an exam. Press any key or click to stop it.',
      anchor: { kind: 'control', name: 'tour' },
    },
    {
      title: 'Two more views',
      body: 'The system is Lecture 1\'s figure, with the lectures and tools behind each part. Rooms is the walkable map. Drag the sky to pan, scroll to zoom, and reopen this guide from the Guide button.',
      anchor: { kind: 'control', name: 'tabs' },
    },
  ]
  const closeGuide = () => {
    setGuideOpen(false); setSpotlight(null); setFocus(null); setIndexOpen(false); setResetKey((k) => k + 1)
  }

  const counts = Object.fromEntries(KINDS.map((k) => [k.v, knowledge.concepts.filter((c) => c.kind === k.v).length]))
  const indexLabel = tab === 'system' ? 'All parts' : mode === 'topics' ? 'All topics' : 'All lectures'
  const Title = tab === 'rooms' ? 'p' : 'h1'

  const topRow = (
    <div className="flex flex-wrap items-center gap-2">
      <div className="glass pointer-events-auto rounded-2xl px-4 py-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)] max-sm:hidden">06-763 · Fall 2026 · Course map</p>
        <Title className="text-base font-bold leading-tight sm:text-lg">
          <a href="../" className="hover:underline hover:decoration-[var(--brand)] hover:underline-offset-4">{COURSE}</a>
        </Title>
      </div>
      <nav aria-label="Course map views" data-guide="tabs" className="glass pointer-events-auto flex gap-0.5 rounded-full p-1">
        {([['graph', 'Knowledge graph'], ['system', 'The system'], ['rooms', 'Rooms']] as [MapTab, string][]).map(([t, label]) => (
          <button key={t} type="button" aria-current={tab === t ? 'page' : undefined} onClick={() => onTab(t)}
                  className="glass-btn">
            {label}
          </button>
        ))}
      </nav>
      <div className="glass pointer-events-auto ml-auto flex items-center gap-1 rounded-full p-1 max-sm:hidden">
        <Segmented<ThemeChoice> label="Colour theme" value={themeChoice} onChange={setThemeChoice}
                                options={[{ v: 'system', label: 'Auto' }, { v: 'light', label: 'Light' }, { v: 'dark', label: 'Dark' }]} />
        <span aria-hidden className="mx-1 h-5 w-px bg-[var(--glass-edge)]" />
        <button type="button" onClick={onList} className="glass-btn">Module list</button>
      </div>
    </div>
  )

  if (tab === 'rooms') {
    return (
      <div className="min-h-dvh">
        <header className="sticky top-0 z-30 p-3">{topRow}</header>
        <div className="mx-auto max-w-[1400px] px-4 pb-6">{rooms}</div>
      </div>
    )
  }

  const indexButton = (
    <button type="button" className="glass-btn" aria-expanded={panelOpen && !focus} onClick={toggleIndex}>
      <span aria-hidden className="mr-1">☰</span>{indexLabel}
    </button>
  )
  const panelBody = (
    <InfoPanel focus={tab === 'system' ? (focus?.type === 'box' ? focus : null) : focus}
               mode={tab === 'system' ? 'system' : mode} banks={banks} onSelect={select}
               onPractice={onPractice} onClose={closePanel} />
  )
  const systemRow = (
    <div className="flex flex-wrap items-start gap-2">
      <div className="glass pointer-events-auto flex flex-wrap items-center gap-x-3 rounded-3xl py-1 pl-4 pr-1">
        <p className="text-sm text-[var(--muted)]">Lecture 1's picture of a production ML system, with the course mapped onto it.</p>
        <label className="glass-btn flex cursor-pointer items-center gap-2 !font-medium">
          <input type="checkbox" checked={showTools} onChange={(e) => setShowTools(e.target.checked)} />
          Show the toolchain
        </label>
      </div>
      <div className="glass pointer-events-auto ml-auto flex rounded-full p-1">{indexButton}</div>
    </div>
  )

  // On a narrow screen the figure, which is wide and short, needs the height
  // the floating panel would take, so the system tab becomes an ordinary page:
  // controls, then the figure, then the panel, scrolling together.
  if (tab === 'system' && !wide) {
    return (
      <div className="kg-sky min-h-dvh">
        <header className="flex flex-col gap-2 p-3">{topRow}{systemRow}</header>
        <div className="px-3">
          <SystemView focus={focus} onFocus={select} showTools={showTools} reduceMotion={reduceMotion} />
        </div>
        {panelOpen && <div className="p-3">{panelBody}</div>}
      </div>
    )
  }

  return (
    <div ref={stageRef} className="kg-sky fixed inset-0 overflow-hidden">
      {tab === 'graph' && (
        <KnowledgeGraph mode={mode} focus={focus} onFocus={select} theme={resolved}
                        reduceMotion={reduceMotion} kindFilter={kindFilter} resetKey={resetKey}
                        view={view} panel={panelBox} spotlight={spotlight} locate={locate} />
      )}

      {tab === 'system' && (
        <div className="absolute transition-[right,bottom] duration-300"
             style={{
               top: view.t + 8, left: 16,
               right: panelBox?.side === 'right' ? panelBox.size + 8 : 16,
               bottom: panelBox?.side === 'bottom' ? panelBox.size + 8 : 16,
             }}>
          <SystemView focus={focus} onFocus={select} showTools={showTools} reduceMotion={reduceMotion} />
        </div>
      )}

      <header ref={headRef} className="pointer-events-none absolute inset-x-0 top-0 z-20 flex flex-col gap-2 p-3">
        {topRow}

        {tab === 'graph' && (
          <div className="flex flex-wrap items-start gap-2">
            <div className="glass pointer-events-auto flex flex-wrap items-center gap-1.5 rounded-3xl p-1">
              <div data-guide="modes">
                <Segmented<Mode> label="Navigate by" value={mode} onChange={(m) => { setMode(m); setFocus(null) }}
                                 options={[{ v: 'lectures', label: 'By lecture' }, { v: 'topics', label: 'By topic' }]} />
              </div>
              <div className="relative" data-guide="search">
                <input ref={searchRef} value={q} onChange={(e) => setQ(e.target.value)} type="search"
                       placeholder="Find a lecture, topic or concept  ( / )" aria-label="Search the course"
                       onKeyDown={(e) => { if (e.key === 'Enter' && hits[0]) { select(hits[0].focus); setQ('') } }}
                       className="w-64 rounded-full border border-[var(--glass-edge)] bg-transparent px-4 py-1.5 text-sm
                                  placeholder:text-[var(--muted)] sm:w-72" />
                {hits.length > 0 && (
                  <ul className="glass absolute z-30 mt-2 w-[22rem] overflow-hidden rounded-xl">
                    {hits.map((h) => (
                      <li key={`${h.focus.type}-${h.focus.id}`}>
                        <button type="button" className="flex w-full items-baseline justify-between gap-3 px-3 py-1.5 text-left text-sm hover:bg-[var(--glass-hover)]"
                                onClick={() => { select(h.focus); setQ('') }}>
                          <span>{h.label}</span><span className="shrink-0 text-xs text-[var(--muted)]">{h.kind}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {mode === 'topics' && (
                <div className="flex flex-wrap gap-0.5" role="group" aria-label="Highlight a kind of concept">
                  {KINDS.map((k) => (
                    <button key={k.v} type="button" aria-pressed={kindFilter === k.v} className="glass-btn !font-medium"
                            onClick={() => {
                              setFocus(null)
                              setKindFilter(kindFilter === k.v ? null : k.v)
                              setResetKey((n) => n + 1)
                            }}>
                      <span aria-hidden className="mr-1 text-[10px]">{k.shape}</span>{k.label} {counts[k.v]}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="glass pointer-events-auto ml-auto flex flex-wrap gap-0.5 rounded-full p-1">
              {indexButton}
              <button type="button" data-guide="tour" className="glass-btn" aria-pressed={touring}
                      onClick={() => setTouring(!touring)}>
                {touring ? 'Stop the tour' : 'Tour the course'}
              </button>
              <button type="button" className="glass-btn max-sm:hidden" onClick={() => setResetKey((k) => k + 1)}>Reset view</button>
              <button type="button" className="glass-btn" aria-pressed={guideOpen}
                      onClick={() => (guideOpen ? closeGuide() : setGuideOpen(true))}>
                <span aria-hidden className="mr-1">?</span>Guide
              </button>
            </div>
          </div>
        )}

        {tab === 'system' && systemRow}
      </header>

      {tab === 'graph' && !(panelOpen && !wide) && (
        <div ref={footRef} className="glass absolute bottom-3 left-3 z-20 rounded-2xl px-4 py-2.5"
             style={{ maxWidth: panelOpen ? 'calc(100% - 420px)' : 'calc(100% - 24px)' }}>
          <Legend mode={mode} />
        </div>
      )}

      {panelOpen && (
        <div ref={paneRef} data-guide="panel"
             className={`pointer-events-none absolute z-20 flex flex-col ${wide ? 'bottom-3 right-3 w-[380px]' : 'inset-x-3 bottom-3'}`}
             style={wide ? { top: view.t + 4 } : undefined}>
          {panelBody}
        </div>
      )}

      {guideOpen && tab === 'graph' && <MapGuide steps={guide} locate={locate} onClose={closeGuide} />}
    </div>
  )
}

function Legend({ mode }: { mode: Mode }) {
  return (
    <div className="text-xs text-[var(--muted)]">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {knowledge.arcs.map((a) => (
            <li key={a} className="flex items-center gap-2 text-[var(--ink)]">
              <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: arcVar(a) }} />{a}
            </li>
          ))}
        </ul>
        {mode === 'topics' && <p>● concept ◆ case study ▲ failure mode ■ metric</p>}
        {mode === 'lectures' && <p>┄ course order · ─ one cites the other</p>}
      </div>
      <p className="mt-1 max-sm:hidden">
        Drag the sky to pan, scroll to zoom, drag a node to pull on it. Every link is a place where one
        lecture's notes cite another.
      </p>
    </div>
  )
}
