/**
 * The panel a click opens, shared by the knowledge graph and the system figure.
 *
 * It answers the three questions a student reviewing a session has: what were
 * the main ideas (the takeaways, then the objectives as "you should be able
 * to"), what does it connect to (the sentences from the notes that link it to
 * other lectures), and where is it used (the data it works on and the case
 * studies in other fields). Every chip is a way to move: a lecture chip selects
 * that lecture, a concept chip switches to the topic view and finds it.
 */

import { useState } from 'react'
import type { Bank } from '../content/load.ts'
import {
  KIND_LABEL, caseById, casesFor, conceptById, conceptsOfLecture, conceptsOfTheme,
  arcIndex, isWrapUp, knowledge, lectureById, linksOf, themeById, themeNeighbours,
  type Concept, type ConceptKind, type Lecture,
} from '../map/knowledge.ts'

export type Focus =
  | { type: 'lecture'; id: string }
  | { type: 'theme'; id: string }
  | { type: 'concept'; id: string }
  | { type: 'box'; id: string }
  | null

export const arcVar = (arc: string) =>
  isWrapUp(arc) ? 'var(--arc-here)' : `var(--arc-${arcIndex(arc)})`

const fmtDate = (iso: string) => {
  if (!iso) return ''
  const d = new Date(`${iso}T12:00:00`)
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
}

function Dot({ arc }: { arc: string }) {
  return <span aria-hidden className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
               style={{ background: arcVar(arc) }} />
}

function Chip({ children, onClick, title }: {
  children: React.ReactNode; onClick?: () => void; title?: string
}) {
  return (
    <button type="button" onClick={onClick} title={title}
            className="kg-chip inline-flex items-center gap-1.5 rounded-full border border-[var(--border)]
                       bg-[var(--surface-raised)] px-2.5 py-1 text-xs hover:border-[var(--brand)]">
      {children}
    </button>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]">{title}</h3>
      <div className="mt-1.5">{children}</div>
    </section>
  )
}

/** Objectives quote the notes, backticks and all; show those as code. */
function Inline({ text }: { text: string }) {
  const parts = text.split('`')
  return <>{parts.map((s, i) => (i % 2 ? <code key={i} className="kg-code">{s}</code> : s))}</>
}

const SHAPE: Record<ConceptKind, string> = { concept: '●', case: '◆', failure: '▲', metric: '■' }

function ConceptChips({ items, onSelect, limit = 14 }: {
  items: Concept[]; onSelect: (f: Focus) => void; limit?: number
}) {
  const [all, setAll] = useState(false)
  const shown = all ? items : items.slice(0, limit)
  return (
    <div className="flex flex-wrap gap-1.5">
      {shown.map((c) => (
        <Chip key={c.id} onClick={() => onSelect({ type: 'concept', id: c.id })}
              title={`${KIND_LABEL[c.kind]} · ${c.section}`}>
          <span aria-hidden className="text-[9px] text-[var(--muted)]">{SHAPE[c.kind]}</span>{c.term}
        </Chip>
      ))}
      {items.length > limit && (
        <button type="button" className="text-xs text-[var(--brand)] underline"
                onClick={() => setAll(!all)}>
          {all ? 'Show fewer' : `Show all ${items.length}`}
        </button>
      )}
    </div>
  )
}

function LectureLinks({ lec, bank, onPractice }: {
  lec: Lecture; bank: Bank | undefined; onPractice: (id: string) => void
}) {
  if (!lec.released) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {lec.notes && <a className="btn-quiet !px-3 !py-1.5 text-sm" href={lec.notes}>Read the notes</a>}
      {lec.slides && <a className="btn-quiet !px-3 !py-1.5 text-sm" href={lec.slides}>Slides</a>}
      {bank && (
        <button type="button" className="btn-primary !px-3 !py-1.5 text-sm" onClick={() => onPractice(lec.id)}>
          Practice
        </button>
      )}
    </div>
  )
}

function LecturePanel({ lec, banks, onSelect, onPractice }: {
  lec: Lecture; banks: Record<string, Bank>; onSelect: (f: Focus) => void; onPractice: (id: string) => void
}) {
  const { buildsOn, usedBy } = linksOf(lec.id)
  const concepts = conceptsOfLecture(lec.id)
  const general = concepts.filter((c) => c.kind === 'concept')
  const special = concepts.filter((c) => c.kind !== 'concept')
  const cases = (lec.cases ?? []).map((id) => caseById(id)!).filter(Boolean)

  return (
    <>
      <p className="flex items-center gap-2 pr-6 text-xs uppercase tracking-wide text-[var(--muted)]">
        <Dot arc={lec.arc} /> {lec.arc} · {fmtDate(lec.date)}
      </p>
      <h2 className="mt-1 text-lg font-semibold leading-snug">{lec.session} · {lec.title}</h2>
      <LectureLinks lec={lec} bank={banks[lec.id]} onPractice={onPractice} />

      {!lec.released && (
        <p className="mt-3 text-sm text-[var(--muted)]">
          This lecture opens on {fmtDate(lec.date)}. Its ideas join the graph when its notes are released.
        </p>
      )}

      {lec.takeaways && (
        <Section title="Main takeaways">
          <ul className="grid gap-2">
            {lec.takeaways.map((t) => (
              <li key={t} className="border-l-2 pl-3 text-sm leading-relaxed"
                  style={{ borderColor: arcVar(lec.arc) }}><Inline text={t} /></li>
            ))}
          </ul>
        </Section>
      )}

      {lec.objectives && lec.objectives.length > 0 && (
        <Section title="Key points: you should be able to">
          <ol className="grid list-decimal gap-1.5 pl-5 text-sm leading-relaxed text-[var(--ink)]">
            {lec.objectives.map((o) => <li key={o}><Inline text={o} /></li>)}
          </ol>
        </Section>
      )}

      {(lec.data || cases.length > 0 || special.some((c) => c.kind === 'case')) && (
        <Section title="Applications">
          {lec.data && <p className="text-sm"><span className="text-[var(--muted)]">Data in class: </span>{lec.data}</p>}
          {cases.length > 0 && (
            <ul className="mt-2 grid gap-1.5">
              {cases.map((c) => (
                <li key={c.id} className="text-sm">
                  <a className="font-medium underline decoration-[var(--border)] underline-offset-2 hover:decoration-[var(--brand)]"
                     href={c.href}>{c.title}</a>
                  <span className="block text-xs text-[var(--muted)]">{c.field}</span>
                </li>
              ))}
            </ul>
          )}
          {special.some((c) => c.kind === 'case') && (
            <div className="mt-2">
              <p className="mb-1 text-xs text-[var(--muted)]">Real cases discussed in the notes</p>
              <ConceptChips items={special.filter((c) => c.kind === 'case')} onSelect={onSelect} />
            </div>
          )}
        </Section>
      )}

      {special.some((c) => c.kind !== 'case') && (
        <Section title="Failure modes and metrics">
          <ConceptChips items={special.filter((c) => c.kind !== 'case')} onSelect={onSelect} />
        </Section>
      )}

      {general.length > 0 && (
        <Section title={`Concepts defined here (${general.length})`}>
          <ConceptChips items={general} onSelect={onSelect} />
        </Section>
      )}

      {(buildsOn.length > 0 || usedBy.length > 0) && (
        <Section title="Connections, in the notes' own words">
          <ul className="grid gap-2.5">
            {buildsOn.map(({ other, where }) => (
              <li key={`b-${other.id}`} className="text-sm">
                <button type="button" className="font-medium hover:text-[var(--brand)]"
                        onClick={() => onSelect({ type: 'lecture', id: other.id })}>
                  <span className="text-[var(--muted)]">Builds on </span>{other.session} · {other.title}
                </button>
                <p className="mt-0.5 text-xs italic leading-relaxed text-[var(--muted)]">“{where}”</p>
              </li>
            ))}
            {usedBy.map(({ other, where }) => (
              <li key={`u-${other.id}`} className="text-sm">
                <button type="button" className="font-medium hover:text-[var(--brand)]"
                        onClick={() => onSelect({ type: 'lecture', id: other.id })}>
                  <span className="text-[var(--muted)]">Used by </span>{other.session} · {other.title}
                </button>
                <p className="mt-0.5 text-xs italic leading-relaxed text-[var(--muted)]">“{where}”</p>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {lec.themes && (
        <Section title="Topics">
          <div className="flex flex-wrap gap-1.5">
            {lec.themes.map((t) => (
              <Chip key={t} onClick={() => onSelect({ type: 'theme', id: t })}>{themeById(t)?.name}</Chip>
            ))}
          </div>
        </Section>
      )}
    </>
  )
}

function ThemePanel({ id, onSelect }: { id: string; onSelect: (f: Focus) => void }) {
  const t = themeById(id)!
  const concepts = conceptsOfTheme(id)
  const by = (k: ConceptKind) => concepts.filter((c) => c.kind === k)
  const cases = casesFor(t.lectures)
  return (
    <>
      <p className="flex items-center gap-2 pr-6 text-xs uppercase tracking-wide text-[var(--muted)]">
        <Dot arc={t.arc} /> Topic · {t.arc}
      </p>
      <h2 className="mt-1 text-lg font-semibold leading-snug">{t.name}</h2>
      <p className="mt-2 text-sm leading-relaxed">{t.blurb}</p>

      <Section title="Lectures">
        <ul className="grid gap-2">
          {t.lectures.map((lid) => {
            const l = lectureById(lid)!
            return (
              <li key={lid}>
                <button type="button" className="text-left text-sm font-medium hover:text-[var(--brand)]"
                        onClick={() => onSelect({ type: 'lecture', id: lid })}>
                  {l.session} · {l.title}
                </button>
                {l.takeaways?.[0] && <p className="text-xs leading-relaxed text-[var(--muted)]">{l.takeaways[0]}</p>}
              </li>
            )
          })}
        </ul>
      </Section>

      {by('concept').length > 0 && (
        <Section title={`Concepts (${by('concept').length})`}>
          <ConceptChips items={by('concept')} onSelect={onSelect} />
        </Section>
      )}
      {by('failure').length > 0 && (
        <Section title="Failure modes"><ConceptChips items={by('failure')} onSelect={onSelect} /></Section>
      )}
      {by('metric').length > 0 && (
        <Section title="Metrics"><ConceptChips items={by('metric')} onSelect={onSelect} /></Section>
      )}
      {(by('case').length > 0 || cases.length > 0) && (
        <Section title="Applications">
          {cases.map((c) => (
            <p key={c.id} className="text-sm">
              <a className="font-medium underline decoration-[var(--border)] underline-offset-2 hover:decoration-[var(--brand)]"
                 href={c.href}>{c.title}</a>
              <span className="block text-xs text-[var(--muted)]">{c.field}</span>
            </p>
          ))}
          {by('case').length > 0 && <div className="mt-2"><ConceptChips items={by('case')} onSelect={onSelect} /></div>}
        </Section>
      )}

      {themeNeighbours(id).length > 0 && (
        <Section title="Connected topics">
          <div className="flex flex-wrap gap-1.5">
            {themeNeighbours(id).map((n) => (
              <Chip key={n.id} onClick={() => onSelect({ type: 'theme', id: n.id })}>
                <Dot arc={n.arc} />{n.name}
              </Chip>
            ))}
          </div>
        </Section>
      )}
    </>
  )
}

function ConceptPanel({ id, onSelect }: { id: string; onSelect: (f: Focus) => void }) {
  const c = conceptById(id)!
  const lec = lectureById(c.lecture)!
  const theme = themeById(c.theme)
  const siblings = knowledge.concepts.filter((x) => x.lecture === c.lecture && x.section === c.section && x.id !== c.id)
  return (
    <>
      <p className="flex items-center gap-2 pr-6 text-xs uppercase tracking-wide text-[var(--muted)]">
        <Dot arc={lec.arc} /> {KIND_LABEL[c.kind]}
      </p>
      <h2 className="mt-1 text-lg font-semibold leading-snug">{c.term}</h2>
      <p className="mt-2 text-sm">
        Explained in <button type="button" className="font-medium hover:text-[var(--brand)]"
                             onClick={() => onSelect({ type: 'lecture', id: lec.id })}>{lec.session}</button>
        {c.section && <>, in “{c.section}”</>}.
      </p>
      <div className="mt-3"><a className="btn-quiet !px-3 !py-1.5 text-sm" href={c.href}>Read that section</a></div>
      {c.also.length > 0 && (
        <Section title="Also indexed in">
          <div className="flex flex-wrap gap-1.5">
            {c.also.map((l) => (
              <Chip key={l} onClick={() => onSelect({ type: 'lecture', id: l })}>
                {lectureById(l)?.session} · {lectureById(l)?.title}
              </Chip>
            ))}
          </div>
        </Section>
      )}
      {theme && (
        <Section title="Topic">
          <Chip onClick={() => onSelect({ type: 'theme', id: theme.id })}><Dot arc={theme.arc} />{theme.name}</Chip>
        </Section>
      )}
      {siblings.length > 0 && (
        <Section title="Explained alongside">
          <ConceptChips items={siblings} onSelect={onSelect} limit={12} />
        </Section>
      )}
    </>
  )
}

function BoxPanel({ id, onSelect }: { id: string; onSelect: (f: Focus) => void }) {
  const b = knowledge.system.boxes.find((x) => x.id === id)!
  const cases = casesFor(b.lectures)
  return (
    <>
      <p className="text-xs uppercase tracking-wide text-[var(--muted)]">Part of the system</p>
      <h2 className="mt-1 text-lg font-semibold leading-snug">{b.label}</h2>
      <p className="mt-2 text-sm leading-relaxed">{b.blurb}</p>
      <Section title="Where the course covers it">
        <ul className="grid gap-2">
          {b.lectures.map((lid) => {
            const l = lectureById(lid)!
            return (
              <li key={lid}>
                <button type="button" className="text-left text-sm font-medium hover:text-[var(--brand)]"
                        onClick={() => onSelect({ type: 'lecture', id: lid })}>
                  <span className="mr-1.5 inline-block align-middle"><Dot arc={l.arc} /></span>
                  {l.session} · {l.title}
                </button>
                {l.takeaways?.[0] && <p className="text-xs leading-relaxed text-[var(--muted)]">{l.takeaways[0]}</p>}
              </li>
            )
          })}
        </ul>
      </Section>
      {b.tools.length > 0 && (
        <Section title="Toolchain">
          <div className="flex flex-wrap gap-1.5">
            {b.tools.map((t) => (
              <Chip key={t.term} onClick={() => onSelect({ type: 'concept', id: t.concept })}
                    title={`Explained in ${lectureById(t.lecture)?.session}`}>
                {t.term}<span className="text-[var(--muted)]">{lectureById(t.lecture)?.session}</span>
              </Chip>
            ))}
          </div>
        </Section>
      )}
      {cases.length > 0 && (
        <Section title="Applications">
          {cases.map((c) => (
            <p key={c.id} className="text-sm">
              <a className="font-medium underline decoration-[var(--border)] underline-offset-2 hover:decoration-[var(--brand)]"
                 href={c.href}>{c.title}</a>
              <span className="block text-xs text-[var(--muted)]">{c.field}</span>
            </p>
          ))}
        </Section>
      )}
    </>
  )
}

/** With nothing selected, the panel is an index: every node, as a button. */
function IndexPanel({ mode, onSelect }: { mode: 'lectures' | 'topics' | 'system'; onSelect: (f: Focus) => void }) {
  if (mode === 'system') {
    return (
      <>
        <h2 className="text-base font-semibold">The system, part by part</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">Hover a part to light it up, click it for the lectures and tools behind it.</p>
        <ul className="mt-3 grid gap-1">
          {knowledge.system.boxes.map((b) => (
            <li key={b.id}><button type="button" className="text-sm hover:text-[var(--brand)]"
                                   onClick={() => onSelect({ type: 'box', id: b.id })}>{b.label}</button></li>
          ))}
        </ul>
      </>
    )
  }
  if (mode === 'topics') {
    return (
      <>
        <h2 className="text-base font-semibold">Topics</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">Each sun is a topic, each small mark a concept from the index. Hover to see what connects, click to open.</p>
        <ul className="mt-3 grid gap-1">
          {knowledge.themes.map((t) => (
            <li key={t.id}><button type="button" className="flex items-center gap-2 text-left text-sm hover:text-[var(--brand)]"
                                   onClick={() => onSelect({ type: 'theme', id: t.id })}><Dot arc={t.arc} />{t.name}</button></li>
          ))}
        </ul>
      </>
    )
  }
  return (
    <>
      <h2 className="text-base font-semibold">Lectures</h2>
      <p className="mt-1 text-sm text-[var(--muted)]">Hover a lecture to light up what it builds on and what builds on it. Click to open its takeaways, key points and applications.</p>
      {knowledge.arcs.map((arc) => (
        <div key={arc} className="mt-3">
          <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]"><Dot arc={arc} />{arc}</p>
          <ul className="mt-1 grid gap-0.5">
            {knowledge.lectures.filter((l) => l.arc === arc).map((l) => (
              <li key={l.id}><button type="button" className="text-left text-sm hover:text-[var(--brand)]"
                                     onClick={() => onSelect({ type: 'lecture', id: l.id })}>
                {l.session} · {l.title}{!l.released && <span className="text-[var(--muted)]"> (opens {fmtDate(l.date)})</span>}
              </button></li>
            ))}
          </ul>
        </div>
      ))}
    </>
  )
}

export function InfoPanel({ focus, mode, banks, onSelect, onPractice, onClose }: {
  focus: Focus
  mode: 'lectures' | 'topics' | 'system'
  banks: Record<string, Bank>
  onSelect: (f: Focus) => void
  onPractice: (id: string) => void
  onClose: () => void
}) {
  const lec = focus?.type === 'lecture' ? lectureById(focus.id) : undefined
  return (
    <aside className="kg-panel glass pointer-events-auto relative max-h-full overflow-y-auto rounded-2xl p-5 max-lg:max-h-[46vh]"
           aria-live="polite">
      <button type="button" onClick={onClose} aria-label="Close"
              className="absolute right-3 top-3 rounded-full px-2 text-lg leading-none text-[var(--muted)] hover:text-[var(--ink)]">×</button>
      {!focus && <IndexPanel mode={mode} onSelect={onSelect} />}
      {lec && <LecturePanel lec={lec} banks={banks} onSelect={onSelect} onPractice={onPractice} />}
      {focus?.type === 'theme' && themeById(focus.id) && <ThemePanel id={focus.id} onSelect={onSelect} />}
      {focus?.type === 'concept' && conceptById(focus.id) && <ConceptPanel id={focus.id} onSelect={onSelect} />}
      {focus?.type === 'box' && <BoxPanel id={focus.id} onSelect={onSelect} />}
    </aside>
  )
}
