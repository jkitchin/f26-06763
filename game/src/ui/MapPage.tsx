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
 * Like the rooms, nothing here scores, streaks or ranks: the course's own
 * reading on generating versus learning is why. What the page offers instead is
 * structure, and a tour that walks the course in order for a quick review.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import type { Bank } from '../content/load.ts'
import { knowledge, type ConceptKind } from '../map/knowledge.ts'
import type { Mode } from '../map/layout.ts'
import type { MapTab } from '../route.ts'
import { InfoPanel, arcVar, type Focus } from './InfoPanel.tsx'
import { KnowledgeGraph } from './KnowledgeGraph.tsx'
import { SystemView } from './SystemView.tsx'
import { useReducedMotion, useTheme, type ThemeChoice } from './theme.ts'

function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: { v: T; label: string }[]; onChange: (v: T) => void; label: string
}) {
  return (
    <div role="radiogroup" aria-label={label}
         className="inline-flex rounded-full border border-[var(--border)] bg-[var(--surface-raised)] p-0.5">
      {options.map((o) => (
        <button key={o.v} type="button" role="radio" aria-checked={value === o.v} onClick={() => onChange(o.v)}
                className={`rounded-full px-3 py-1 text-sm transition-colors ${
                  value === o.v ? 'bg-[var(--ink)] text-[var(--bg)]' : 'text-[var(--muted)] hover:text-[var(--ink)]'}`}>
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
  const [mode, setMode] = useState<Mode>('lectures')
  const [focus, setFocus] = useState<Focus>(null)
  const [kindFilter, setKindFilter] = useState<ConceptKind | null>(null)
  const [resetKey, setResetKey] = useState(0)
  const [showTools, setShowTools] = useState(false)
  const [q, setQ] = useState('')
  const [touring, setTouring] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)
  const hits = useMemo(() => search(q), [q])

  // Selecting something moves to the view that shows it.
  const select = (f: Focus) => {
    if (f?.type === 'lecture') setMode('lectures')
    if (f?.type === 'theme' || f?.type === 'concept') { setMode('topics'); setKindFilter(null) }
    if (f && f.type !== 'box' && tab === 'system') onTab('graph')
    setFocus(f)
  }

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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) {
        if (e.key === 'Escape') { setQ(''); el.blur() }
        return
      }
      if (e.key === 'Escape') setFocus(null)
      if (e.key === '/' && tab === 'graph') { e.preventDefault(); searchRef.current?.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tab])

  useEffect(() => {
    setFocus((f) => (tab === 'graph' && f?.type === 'box') || (tab === 'system' && f && f.type !== 'box') ? null : f)
  }, [tab])

  const counts = Object.fromEntries(KINDS.map((k) => [k.v, knowledge.concepts.filter((c) => c.kind === k.v).length]))

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-5">
      <header className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <nav aria-label="Course map views" className="flex flex-wrap items-center gap-1">
          {([['graph', 'Knowledge graph'], ['system', 'The system'], ['rooms', 'Rooms']] as [MapTab, string][]).map(([t, label]) => (
            <button key={t} type="button" aria-current={tab === t ? 'page' : undefined} onClick={() => onTab(t)}
                    className={`rounded-xl px-3.5 py-2 text-sm font-semibold transition-colors ${
                      tab === t ? 'bg-[var(--surface-raised)] text-[var(--ink)] shadow-sm ring-1 ring-[var(--border)]'
                                : 'text-[var(--muted)] hover:text-[var(--ink)]'}`}>
              {label}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Segmented<ThemeChoice> label="Colour theme" value={themeChoice} onChange={setThemeChoice}
                                  options={[{ v: 'system', label: 'Auto' }, { v: 'light', label: 'Light' }, { v: 'dark', label: 'Dark' }]} />
          <button type="button" onClick={onList} className="btn-quiet !px-3 !py-1.5 text-sm">Module list</button>
        </div>
      </header>

      {tab === 'rooms' && rooms}

      {tab === 'graph' && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Segmented<Mode> label="Navigate by" value={mode} onChange={(m) => { setMode(m); setFocus(null) }}
                             options={[{ v: 'lectures', label: 'By lecture' }, { v: 'topics', label: 'By topic' }]} />
            <div className="relative">
              <input ref={searchRef} value={q} onChange={(e) => setQ(e.target.value)} type="search"
                     placeholder="Find a lecture, topic or concept  ( / )" aria-label="Search the course"
                     onKeyDown={(e) => { if (e.key === 'Enter' && hits[0]) { select(hits[0].focus); setQ('') } }}
                     className="w-72 rounded-full border border-[var(--border)] bg-[var(--surface-raised)] px-4 py-1.5 text-sm" />
              {hits.length > 0 && (
                <ul className="absolute z-20 mt-1 w-[22rem] overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-raised)] shadow-xl">
                  {hits.map((h) => (
                    <li key={`${h.focus.type}-${h.focus.id}`}>
                      <button type="button" className="flex w-full items-baseline justify-between gap-3 px-3 py-1.5 text-left text-sm hover:bg-[var(--bg)]"
                              onClick={() => { select(h.focus); setQ('') }}>
                        <span>{h.label}</span><span className="shrink-0 text-xs text-[var(--muted)]">{h.kind}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {mode === 'topics' && (
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Highlight a kind of concept">
                {KINDS.map((k) => (
                  <button key={k.v} type="button" aria-pressed={kindFilter === k.v}
                          onClick={() => {
                            setFocus(null)
                            setKindFilter(kindFilter === k.v ? null : k.v)
                            setResetKey((n) => n + 1)
                          }}
                          className={`rounded-full border px-3 py-1 text-sm ${kindFilter === k.v
                            ? 'border-[var(--ink)] bg-[var(--ink)] text-[var(--bg)]' : 'border-[var(--border)] text-[var(--muted)] hover:text-[var(--ink)]'}`}>
                    <span aria-hidden className="mr-1 text-[10px]">{k.shape}</span>{k.label} {counts[k.v]}
                  </button>
                ))}
              </div>
            )}
            <div className="ml-auto flex gap-2">
              <button type="button" className="btn-quiet !px-3 !py-1.5 text-sm" onClick={() => setTouring(!touring)}>
                {touring ? 'Stop the tour' : 'Tour the course'}
              </button>
              <button type="button" className="btn-quiet !px-3 !py-1.5 text-sm" onClick={() => setResetKey((k) => k + 1)}>
                Reset view
              </button>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
            <div>
              <KnowledgeGraph mode={mode} focus={focus} onFocus={select} theme={resolved}
                              reduceMotion={reduceMotion} kindFilter={kindFilter} resetKey={resetKey} />
              <Legend mode={mode} />
            </div>
            <InfoPanel focus={focus} mode={mode} banks={banks} onSelect={select}
                       onPractice={onPractice} onClose={() => setFocus(null)} />
          </div>
          <p className="mt-2 text-xs text-[var(--muted)]">
            Drag the sky to pan, scroll to zoom, drag a node to pull on it. Links are the places where one
            lecture's notes cite another, so every line here is a sentence you can read.
          </p>
        </>
      )}

      {tab === 'system' && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <p className="text-sm text-[var(--muted)]">
              Lecture 1's picture of a production ML system, with the course mapped onto it.
            </p>
            <label className="ml-auto flex items-center gap-2 text-sm">
              <input type="checkbox" checked={showTools} onChange={(e) => setShowTools(e.target.checked)} />
              Show the toolchain
            </label>
          </div>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
            <SystemView focus={focus} onFocus={select} showTools={showTools} reduceMotion={reduceMotion} />
            <InfoPanel focus={focus?.type === 'box' ? focus : null} mode="system" banks={banks} onSelect={select}
                       onPractice={onPractice} onClose={() => setFocus(null)} />
          </div>
        </>
      )}
    </div>
  )
}

function Legend({ mode }: { mode: Mode }) {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--muted)]">
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        {knowledge.arcs.map((a) => (
          <li key={a} className="flex items-center gap-2">
            <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: arcVar(a) }} />{a}
          </li>
        ))}
      </ul>
      {mode === 'topics' && (
        <p>● concept ◆ case study ▲ failure mode ■ metric</p>
      )}
      {mode === 'lectures' && (
        <p>┄ course order · ─ one cites the other</p>
      )}
    </div>
  )
}
