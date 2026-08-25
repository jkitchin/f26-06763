/**
 * The security seal: the participation score, drawn rather than typeset.
 *
 * The number a TA reads off page 1 used to be a jsPDF text run, which meant it
 * sat in the content stream as the literal string `(95%)`. Changing it to
 * `(99%)` in a hex editor takes about ten seconds and needs no tools, and while
 * it never moved the grade (the gradebook column is recomputed from the payload
 * by tools/verify_evidence.py) it did make the printed page a bad thing to
 * trust in the thirty seconds before anybody runs the verifier.
 *
 * So the score is a picture now. Three things about how that is done matter
 * more than the fact that it is a picture at all, because a picture on its own
 * is obscurity and this course does not teach obscurity:
 *
 *   1. It is drawn from *modules*, small filled squares on a fixed grid, not
 *      from curves. That is what makes it machine-readable: the verifier parses
 *      the `re` operators back out of the content stream, rebuilds the bitmap,
 *      and compares it against the bitmap the payload's score would have drawn.
 *      Editing the seal is therefore caught, which is the whole point. Editing
 *      a JPEG of the number would not have been.
 *   2. The data block to the right encodes the MAC tag, so a seal lifted whole
 *      from a classmate's PDF carries their tag and mismatches this payload.
 *      Copying the picture is the obvious attack once the number stops being
 *      text, and this is the answer to it.
 *   3. The guilloche, the hatch and the microtext are derived from that same
 *      tag, so no two seals in the course look alike. Those are the parts a
 *      human notices. They are also the parts that are hardest to reproduce by
 *      hand and easiest to get subtly wrong, which is what security printing
 *      has always been for.
 *
 * Everything here is deterministic and DOM-free: no canvas, no Math.random, no
 * Date. game/tests/make_sample_pdfs.ts runs this file under plain node in CI,
 * and the same bytes have to come out there as in a browser or the verifier's
 * comparison is meaningless.
 */

import type { jsPDF } from 'jspdf'

/**
 * Module sizes, in points. Mirrored in tools/verify_evidence.py, and
 * game/tests/test_seal.py fails if the two drift, for the reason
 * WRONG_PENALTY is checked the same way: a disagreement here silently turns
 * every honest seal into a mismatch.
 *
 * The two differ so the parser can tell a digit module from a data module by
 * size alone, without needing to know where either block was placed.
 */
export const DIGIT_PT = 4.0
export const MODULE_PT = 2.6

/** Overall seal footprint, so the caller can lay out around it. */
export const SEAL_W = 252
export const SEAL_H = 72

/** 8x8 data block: an L-shaped finder down the left and along the bottom,
 *  leaving a 7x7 field, of which the low 49 bits of the MAC tag are drawn. */
export const GRID = 8
export const DATA_BITS = (GRID - 1) * (GRID - 1)

/**
 * A 5x7 bitmap font, one 5-bit row per byte, most significant bit leftmost.
 *
 * Mirrored in tools/verify_evidence.py. Hand-written rather than lifted from a
 * font file because the verifier has to render the same glyphs to compare
 * against, and a font file would put a rasterizer between the two sides.
 */
export const FONT: Record<string, number[]> = {
  '0': [0x0e, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0e],
  '1': [0x04, 0x0c, 0x04, 0x04, 0x04, 0x04, 0x0e],
  '2': [0x0e, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1f],
  '3': [0x1f, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0e],
  '4': [0x02, 0x06, 0x0a, 0x12, 0x1f, 0x02, 0x02],
  '5': [0x1f, 0x10, 0x1e, 0x01, 0x01, 0x11, 0x0e],
  '6': [0x06, 0x08, 0x10, 0x1e, 0x11, 0x11, 0x0e],
  '7': [0x1f, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
  '8': [0x0e, 0x11, 0x11, 0x0e, 0x11, 0x11, 0x0e],
  '9': [0x0e, 0x11, 0x11, 0x0f, 0x01, 0x02, 0x0c],
  '%': [0x18, 0x19, 0x02, 0x04, 0x08, 0x13, 0x03],
}

const CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'

/**
 * The printed verification code, back to the 10 tag bytes it was made from.
 *
 * Taking the tag from the code rather than from the attestation keeps this
 * module out of the MAC path entirely: it needs no key, and a hand-built
 * Attestation (the fabricated sample in make_sample_pdfs.ts is one) still draws
 * a plausible seal instead of throwing. Crockford's confusable folding is
 * applied so a code that has been through a human is still decodable.
 */
export function tagFromCode(code: string): Uint8Array {
  const s = code
    .toUpperCase()
    .replace(/[-\s]/g, '')
    .replace(/O/g, '0')
    .replace(/[IL]/g, '1')
    .replace(/U/g, 'V')
  const out = new Uint8Array(10)
  let bits = 0
  let value = 0
  let n = 0
  for (const ch of s) {
    const v = CROCKFORD.indexOf(ch)
    if (v < 0) continue
    value = (value << 5) | v
    bits += 5
    while (bits >= 8 && n < out.length) {
      out[n++] = (value >>> (bits - 8)) & 0xff
      bits -= 8
    }
  }
  return out
}

/** Which modules a string of digits sets, as [col, row] pairs on a 5x7 grid
 *  per glyph with one blank column between glyphs. Shared with the verifier
 *  by construction: it renders the same table the same way. */
export function glyphModules(text: string): Array<[number, number]> {
  const on: Array<[number, number]> = []
  let col = 0
  for (const ch of text) {
    const rows = FONT[ch]
    if (!rows) {
      col += 3
      continue
    }
    for (let r = 0; r < 7; r++) {
      for (let c = 0; c < 5; c++) {
        if ((rows[r]! >> (4 - c)) & 1) on.push([col + c, r])
      }
    }
    col += 6
  }
  return on
}

/** Data-block modules, including the L finder. */
export function dataModules(tag: Uint8Array): Array<[number, number]> {
  const on: Array<[number, number]> = []
  // Finder: solid left column and solid bottom row. Gives the parser an origin
  // and an orientation without a separate alignment convention.
  for (let r = 0; r < GRID; r++) on.push([0, r])
  for (let c = 1; c < GRID; c++) on.push([c, GRID - 1])
  for (let i = 0; i < DATA_BITS; i++) {
    const bit = (tag[(i >> 3) % tag.length]! >> (i & 7)) & 1
    if (bit) on.push([1 + (i % (GRID - 1)), Math.floor(i / (GRID - 1))])
  }
  return on
}

export interface SealInput {
  /** The printed verification code; every deterministic parameter comes from it. */
  code: string
  /** Whole percent, as printed. */
  percent: number
  /**
   * Repeated in the two microtext strips. It carries the score as extractable
   * text on purpose: `check_printed_text_agrees` in the verifier looks for
   * `"<percent>%"` in the page text, and moving the headline number into a
   * picture would otherwise blind the one check that costs nothing to run.
   */
  microtext: string
}

const SEAL_INK = '#7a0c1e'
const SEAL_HAIR = '#c9a3ab'
const SEAL_LINE = '#c98f9c'
const SEAL_HATCH = '#f0e3e6'

/** One modulated polyline, as jsPDF wants it: a start point and deltas. */
function polyline(
  doc: jsPDF,
  n: number,
  at: (i: number) => [number, number],
): void {
  const [sx, sy] = at(0)
  let px = sx
  let py = sy
  const deltas: number[][] = []
  for (let i = 1; i <= n; i++) {
    const [nx, ny] = at(i)
    deltas.push([nx - px, ny - py])
    px = nx
    py = ny
  }
  doc.lines(deltas, sx, sy, [1, 1], 'S', false)
}

/**
 * Draw the seal with its top-left corner at (x, y).
 *
 * Order is background to foreground, because jsPDF has no z-index: the hatch
 * and the guilloche must be laid down before the modules or they draw over the
 * number.
 */
export function drawSeal(doc: jsPDF, x: number, y: number, input: SealInput): void {
  const tag = tagFromCode(input.code)

  // --- engine-turned ground -----------------------------------------------
  // The wave field a banknote or a share certificate is printed on. Two
  // frequencies beat against each other, both taken from the tag, so the moire
  // this produces is particular to one PDF. It doubles as a void pantograph:
  // the spacing is chosen so that a photocopier or a screen grab resamples it
  // into visible banding, and a second-generation seal looks wrong beside a
  // first-generation one.
  const f1 = 0.055 + (tag[6]! % 7) * 0.006
  const f2 = 0.017 + (tag[7]! % 5) * 0.004
  const q1 = (tag[8]! / 255) * Math.PI * 2
  const x0 = x + 3.5
  const x1 = x + SEAL_W - 3.5
  const STEPS = 64
  doc.setDrawColor(SEAL_HATCH).setLineWidth(0.14)
  for (let row = 0; row < 16; row++) {
    const base = y + 5 + row * ((SEAL_H - 10) / 15)
    polyline(doc, STEPS, (i) => {
      const u = x0 + ((x1 - x0) * i) / STEPS
      return [u, base + 1.5 * Math.sin(f1 * (u - x0) + q1 + row * 0.4)
                    + 1.1 * Math.sin(f2 * (u - x0) - q1)]
    })
  }

  // --- guilloche rosette --------------------------------------------------
  // Three interwoven modulated circles. The frequencies and phases come from
  // the MAC tag, so the figure is a rendering of the tag: two students, or one
  // student's two attempts, never draw the same rosette.
  const cx = x + 40
  const cy = y + SEAL_H / 2
  const k1 = 5 + (tag[0]! % 8)
  const k2 = 13 + (tag[1]! % 12)
  const b1 = 2 + (tag[2]! % 5) * 0.55
  const b2 = 1 + (tag[3]! % 4) * 0.45
  const p1 = (tag[4]! / 255) * Math.PI * 2
  const p2 = (tag[5]! / 255) * Math.PI * 2

  doc.setDrawColor(SEAL_LINE).setLineWidth(0.16)
  const N = 140
  for (let ring = 0; ring < 6; ring++) {
    const R = 27 - ring * 3.4
    const shift = (ring * Math.PI * 2) / 11
    polyline(doc, N, (i) => {
      const t = (i / N) * Math.PI * 2
      const rad = R + b1 * Math.cos(k1 * t + p1 + shift) + b2 * Math.cos(k2 * t + p2 - shift)
      return [cx + rad * Math.cos(t), cy + rad * Math.sin(t)]
    })
  }

  // --- the number, as modules ---------------------------------------------
  // Not text. A hex editor sees a few dozen `re` operators and no digits, and
  // the verifier rebuilds this same bitmap from the payload and compares.
  const text = `${input.percent}%`
  const dx = x + 88
  const dy = y + 22
  doc.setFillColor(SEAL_INK)
  for (const [c, r] of glyphModules(text)) {
    doc.rect(dx + c * DIGIT_PT, dy + r * DIGIT_PT, DIGIT_PT, DIGIT_PT, 'F')
  }

  // --- the data block ------------------------------------------------------
  const gx = x + SEAL_W - 8 - GRID * MODULE_PT
  const gy = y + (SEAL_H - GRID * MODULE_PT) / 2
  for (const [c, r] of dataModules(tag)) {
    doc.rect(gx + c * MODULE_PT, gy + r * MODULE_PT, MODULE_PT, MODULE_PT, 'F')
  }

  // --- microtext -----------------------------------------------------------
  // 1.7pt, which is legible under a loupe and a grey smear at arm's length.
  // Repeated rather than written once so that removing it means finding every
  // copy, and extracted as ordinary text so the verifier can still read the
  // score it carries.
  // Deliberately no `maxWidth`: jsPDF would wrap the strip onto a second line
  // and draw it back over the first at this leading, which is a smear rather
  // than microtext. Fit by counting whole repetitions instead.
  doc.setFont('helvetica', 'normal').setFontSize(1.7).setTextColor(SEAL_INK)
  const unit = `${input.microtext}   `
  const span = SEAL_W - 16
  const reps = Math.max(1, Math.floor(span / Math.max(doc.getTextWidth(unit), 0.1)))
  const strip = unit.repeat(reps)
  doc.text(strip, x + 8, y + 6.6)
  doc.text(strip, x + 8, y + SEAL_H - 4.2)

  // --- label and frame -----------------------------------------------------
  doc.setFont('helvetica', 'bold').setFontSize(6).setTextColor(SEAL_INK)
  doc.text('PARTICIPATION SCORE', x + 88, y + 17)
  doc.setFont('helvetica', 'normal').setFontSize(4.6).setTextColor(SEAL_HAIR)
  doc.text('DRAWN FROM THE VERIFICATION DATA', x + 88, y + SEAL_H - 12)

  doc.setDrawColor(SEAL_INK).setLineWidth(0.9)
  doc.line(x, y, x + SEAL_W, y)
  doc.line(x, y + SEAL_H, x + SEAL_W, y + SEAL_H)
  doc.line(x, y, x, y + SEAL_H)
  doc.line(x + SEAL_W, y, x + SEAL_W, y + SEAL_H)
  doc.setDrawColor(SEAL_HAIR).setLineWidth(0.25)
  doc.line(x + 2.5, y + 2.5, x + SEAL_W - 2.5, y + 2.5)
  doc.line(x + 2.5, y + SEAL_H - 2.5, x + SEAL_W - 2.5, y + SEAL_H - 2.5)
  doc.line(x + 2.5, y + 2.5, x + 2.5, y + SEAL_H - 2.5)
  doc.line(x + SEAL_W - 2.5, y + 2.5, x + SEAL_W - 2.5, y + SEAL_H - 2.5)
}
