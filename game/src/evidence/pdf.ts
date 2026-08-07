/**
 * The evidence PDF.
 *
 * jsPDF rather than print CSS, because the student has to upload a *file*.
 * `window.print()` makes the margins, the headers and "did you actually pick
 * Save as PDF" into their problem, at 11pm, and a module they cannot hand in is
 * a module they did not get credit for.
 *
 * Two channels carry the attestation: a drawn text block on the last page, and
 * the same string in the PDF /Info Keywords field. Two is redundancy; three
 * would be maintenance. The verifier tries Keywords first because it survives
 * some transforms that text extraction does not.
 *
 * Page 1 is written for a human grader and deliberately prints the questions
 * and the chosen answers. The bank is public anyway, and printing them means
 * that two PDFs side by side visibly differ, which is the cheapest possible
 * demonstration that the per-student seeding is doing something.
 */

import { jsPDF } from 'jspdf'
import { attestationLines, type Attestation, type ItemRecord } from './payload.ts'

export interface PdfInput {
  attestation: Attestation
  name: string
  andrewId: string
  lecture: string
  lectureTitle: string
  finishedAtLocal: string
  elapsedMs: number
  activeMs: number
  resumes: number
  items: ItemRecord[]
  /** id -> short prompt and the text of the option the student chose. */
  labels: Record<string, { prompt: string; chosen: string }>
}

const INK = '#1a1a1a'
const MUTED = '#5c5c5c'
const RULE = '#d8d8d8'
const CMU_RED = '#c41230'

function hms(ms: number): string {
  const s = Math.round(ms / 1000)
  const m = Math.floor(s / 60)
  return m ? `${m} min ${String(s % 60).padStart(2, '0')} s` : `${s} s`
}

export function buildPdf(input: PdfInput): jsPDF {
  const doc = new jsPDF({ unit: 'pt', format: 'letter' })
  const L = 56
  const W = doc.internal.pageSize.getWidth()
  let y = 64

  doc.setFont('helvetica', 'normal').setFontSize(8).setTextColor(MUTED)
  doc.text('06-763 / 14-763 / 18-763   Systems & Toolchains for AI in Engineering', L, y)

  y += 22
  doc.setFont('helvetica', 'bold').setFontSize(16).setTextColor(INK)
  doc.text('Module completion record', L, y)

  y += 8
  doc.setDrawColor(CMU_RED).setLineWidth(1.5).line(L, y, W - L, y)

  // --- the facts a grader reads -------------------------------------------
  y += 26
  const firstTry = input.items.filter((i) => i.first_ok).length
  const rows: [string, string][] = [
    ['Student', `${input.name}  (${input.andrewId})`],
    ['Module', `${input.lecture.toUpperCase()}  ${input.lectureTitle}`],
    ['Completed', input.finishedAtLocal],
    [
      'Time on task',
      `${hms(input.activeMs)}  (${hms(input.elapsedMs)} elapsed` +
        `${input.resumes ? `, ${input.resumes} pause${input.resumes > 1 ? 's' : ''}` : ''})`,
    ],
    ['Items', `${input.items.length} completed`],
    ['First-try correct', `${firstTry} of ${input.items.length}`],
  ]
  doc.setFontSize(10)
  for (const [label, value] of rows) {
    doc.setFont('helvetica', 'normal').setTextColor(MUTED).text(label, L, y)
    doc.setFont('helvetica', 'bold').setTextColor(INK).text(value, L + 108, y)
    y += 16
  }

  y += 6
  doc.setFont('courier', 'bold').setFontSize(12).setTextColor(CMU_RED)
  doc.text(input.attestation.code, L + 108, y)
  doc.setFont('helvetica', 'normal').setFontSize(10).setTextColor(MUTED)
  doc.text('Verification', L, y)
  y += 24

  // --- per item ------------------------------------------------------------
  doc.setDrawColor(RULE).setLineWidth(0.5).line(L, y, W - L, y)
  y += 14
  doc.setFont('helvetica', 'bold').setFontSize(8).setTextColor(MUTED)
  doc.text('ITEM', L, y)
  doc.text('ANSWER CHOSEN', L + 96, y)
  doc.text('1ST', W - 132, y)
  doc.text('TRIES', W - 104, y)
  doc.text('TIME', W - 62, y)
  y += 6
  doc.line(L, y, W - L, y)
  y += 14

  doc.setFontSize(8.5)
  for (const item of input.items) {
    if (y > doc.internal.pageSize.getHeight() - 72) {
      doc.addPage()
      y = 64
    }
    const label = input.labels[item.id] ?? { prompt: item.id, chosen: item.ans.join(', ') }
    const tag = item.v && item.v !== '-' ? `${item.id}#${item.v}` : item.id

    doc.setFont('courier', 'normal').setTextColor(INK).text(tag, L, y)
    doc.setFont('helvetica', 'normal').setTextColor(INK)
    doc.text(doc.splitTextToSize(label.chosen, W - L - 96 - 148)[0] ?? '', L + 96, y)
    doc.setTextColor(item.first_ok ? '#2b7a4b' : MUTED)
    doc.text(item.first_ok ? 'yes' : 'no', W - 132, y)
    doc.setTextColor(MUTED)
    doc.text(String(item.tries), W - 100, y)
    doc.text(`${Math.round(item.total_ms / 1000)} s`, W - 62, y)
    if (item.revealed) {
      y += 10
      doc.setFontSize(7).setTextColor(MUTED).text('    answer revealed', L + 96, y)
      doc.setFontSize(8.5)
    }
    y += 15
  }

  // --- the machine-readable block -----------------------------------------
  doc.addPage()
  y = 64
  doc.setFont('helvetica', 'normal').setFontSize(8).setTextColor(MUTED)
  doc.text(
    'Verification data. Do not edit: it is checked against the record above.',
    L,
    y,
  )
  y += 18
  doc.setFont('courier', 'normal').setFontSize(6).setTextColor(INK)
  for (const line of attestationLines(input.attestation.b64)) {
    doc.text(line, L, y)
    y += 7.4
  }

  // Second channel. One line of code, tried first by the verifier.
  doc.setProperties({
    title: `${input.lecture} module record, ${input.andrewId}`,
    subject: input.attestation.code,
    keywords: input.attestation.b64,
    creator: '06-763 practice game',
  })

  return doc
}

export function filenameFor(lecture: string, andrewId: string): string {
  return `${lecture}-evidence-${andrewId}.pdf`
}
