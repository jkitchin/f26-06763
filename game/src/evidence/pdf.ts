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

import type { jsPDF } from 'jspdf'
import { scoreFromTries, WRONG_PENALTY } from '../store/log.ts'
import { attestationLines, percentOf, type Attestation, type ItemRecord } from './payload.ts'
import { drawSeal, SEAL_H } from './seal.ts'

export interface PdfInput {
  attestation: Attestation
  name: string
  andrewId: string
  lecture: string
  lectureTitle: string
  /** 1-based, from the sitting's opened event. Printed, and inside the MAC. */
  attempt: number
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

/**
 * Async because jsPDF is loaded on demand.
 *
 * It is a third of the bundle and is needed only on the last screen of a
 * module, so importing it eagerly makes every student pay for it on first load
 * whether or not they finish. Vite splits it into its own chunk.
 */
export async function buildPdf(input: PdfInput): Promise<jsPDF> {
  const { jsPDF } = await import('jspdf')
  // `compress` Flates the content streams. It halves the file a student
  // uploads, which the seal's line work would otherwise have tripled, and it
  // has a second effect worth naming: the page is no longer a plaintext
  // content stream, so the squares the score is drawn from cannot be found in
  // a hex editor at all. That is obscurity rather than a control, and the
  // control is still seal.ts being machine-readable, but it costs nothing.
  const doc = new jsPDF({ unit: 'pt', format: 'letter', compress: true })
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
  const percent = percentOf(input.items)
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
    // The attempt sits directly above the score because the two are read
    // together or not at all: a 100% on attempt 3 and a 100% on attempt 1 are
    // different facts, and a grader scanning a stack of these should not have
    // to hunt for the second one.
    ['Attempt', String(input.attempt)],
  ]
  doc.setFontSize(10)
  for (const [label, value] of rows) {
    doc.setFont('helvetica', 'normal').setTextColor(MUTED).text(label, L, y)
    doc.setFont('helvetica', 'bold').setTextColor(INK).text(value, L + 108, y)
    y += 16
  }

  // The participation score, in a drawn seal rather than a text run, because it
  // is the one number on this page a reader is tempted to trust before anybody
  // runs the verifier. See seal.ts for what the picture is made of and why it
  // is made of squares. The rule is spelled out underneath so a student
  // querying their score can check the arithmetic against the SCORE column in
  // the per-item table without asking anybody.
  if (percent !== null) {
    y += 4
    drawSeal(doc, L, y, {
      code: input.attestation.code,
      percent,
      microtext:
        `${input.andrewId} \u00b7 ${input.lecture} \u00b7 ${percent}% \u00b7 ` +
        `attempt ${input.attempt} \u00b7 ${input.attestation.code}`,
    })
    y += SEAL_H + 13
    doc.setFont('helvetica', 'normal').setFontSize(8).setTextColor(MUTED)
    doc.text(
      `one point per question, less ${WRONG_PENALTY.toFixed(2)} per wrong answer, averaged` +
        ' over the questions with a chosen answer. The score column below is that arithmetic.',
      L,
      y,
    )
    y += 14
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
  doc.text('1ST', W - 186, y)
  doc.text('TRIES', W - 154, y)
  doc.text('SCORE', W - 114, y)
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
    // Free-recall items carry no chosen option, are scored by the student
    // against a checklist, and are excluded from the average. They print a dash
    // rather than a 1.00, so the column averages to the number in the seal
    // instead of to something a student can reasonably dispute.
    const graded = item.ans.length > 0

    doc.setFont('courier', 'normal').setTextColor(INK).text(tag, L, y)
    doc.setFont('helvetica', 'normal').setTextColor(INK)
    doc.text(doc.splitTextToSize(label.chosen, W - L - 96 - 200)[0] ?? '', L + 96, y)
    doc.setTextColor(item.first_ok ? '#2b7a4b' : MUTED)
    doc.text(item.first_ok ? 'yes' : 'no', W - 184, y)
    doc.setTextColor(MUTED)
    doc.text(String(item.tries), W - 148, y)
    doc.setTextColor(graded ? INK : MUTED)
    doc.text(graded ? scoreFromTries(item.tries, item.revealed).toFixed(2) : '-', W - 112, y)
    doc.setTextColor(MUTED)
    doc.text(`${Math.round(item.total_ms / 1000)} s`, W - 62, y)
    if (item.revealed) {
      y += 10
      doc.setFontSize(7).setTextColor(MUTED).text('    answer revealed', L + 96, y)
      doc.setFontSize(8.5)
    }
    y += 15
  }

  // --- where the seal's number came from -----------------------------------
  // The seal is a rounded whole percent, and this is the arithmetic behind it:
  // the SCORE column's sum, the count it was divided by, and the mean. A
  // student querying their score should be able to follow it from the rows
  // above without asking anybody, and a TA should be able to see at a glance
  // which items were left out of the divisor.
  if (percent !== null) {
    const graded = input.items.filter((i) => i.ans.length > 0)
    const earned = graded.reduce((n, i) => n + scoreFromTries(i.tries, i.revealed), 0)
    const ungraded = input.items.length - graded.length
    const plural = (n: number) => (n === 1 ? '' : 's')
    if (y > doc.internal.pageSize.getHeight() - 96) {
      doc.addPage()
      y = 64
    }
    y += 2
    doc.setDrawColor(RULE).setLineWidth(0.5).line(W - 190, y, W - L, y)
    y += 13
    doc.setFont('helvetica', 'normal').setFontSize(8.5).setTextColor(MUTED)
    doc.text('Average', L, y)
    doc.setFont('helvetica', 'bold').setTextColor(INK)
    doc.text((earned / graded.length).toFixed(2), W - 112, y)
    y += 11
    doc.setFont('helvetica', 'normal').setFontSize(7).setTextColor(MUTED)
    doc.text(
      `${earned.toFixed(2)} over ${graded.length} graded item${plural(graded.length)}, ` +
        `which is the ${percent}% in the seal above.` +
        (ungraded
          ? ` ${ungraded} item${plural(ungraded)} with no chosen answer ${
              ungraded === 1 ? 'is' : 'are'
            } scored by you and left out.`
          : ''),
      L,
      y,
    )
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
