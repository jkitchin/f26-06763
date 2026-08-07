/**
 * Ask for the Andrew ID, once, and confirm the normalized form back.
 *
 * This screen exists because of the single most likely operational failure in
 * the whole design. The ID seeds the derivation byte for byte, so a typo here
 * produces a PDF that fails verification for a student who did the work
 * honestly, and the failure surfaces days later at grading time when it is
 * expensive and confusing to unpick.
 *
 * So: normalize, show what was understood, and make them agree with it. The
 * confirmation step is not friction to be optimized away.
 */

import { useState } from 'react'
import { normalizeId } from '../seed.ts'

interface Props {
  onDone: (andrewId: string, displayName: string) => void
}

export function Identity({ onDone }: Props) {
  const [raw, setRaw] = useState('')
  const [name, setName] = useState('')

  let normalized: string | null = null
  let problem: string | null = null
  if (raw.trim()) {
    try {
      normalized = normalizeId(raw)
    } catch {
      problem = 'That does not look like an Andrew ID. Letters and digits, starting with a letter.'
    }
  }

  const ready = !!normalized && name.trim().length > 1

  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col justify-center px-4 py-10">
      <h1 className="mb-2 text-2xl font-bold">Practice modules</h1>
      <p className="mb-8 text-[15px] leading-relaxed text-[var(--muted)]">
        06-763 · Systems &amp; Toolchains for AI in Engineering. Short practice
        sets tied to each lecture. Finish one and download the PDF to upload.
      </p>

      <label className="mb-1 block text-sm font-medium" htmlFor="andrew">
        Andrew ID
      </label>
      <input
        id="andrew"
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        autoFocus
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        placeholder="jkitchin"
        className="w-full rounded-xl border-2 border-[var(--border)] bg-[var(--surface-raised)]
                   p-3 font-mono outline-none focus:border-[var(--brand)]"
      />

      {problem && <p className="mt-2 text-sm text-[var(--wrong)]">{problem}</p>}
      {normalized && (
        <p className="mt-2 text-sm">
          <span className="text-[var(--muted)]">Your questions will be chosen for </span>
          <strong className="font-mono">{normalized}</strong>
          <span className="text-[var(--muted)]">. Check that is right.</span>
        </p>
      )}

      <label className="mt-6 mb-1 block text-sm font-medium" htmlFor="name">
        Name, as it should appear on the PDF
      </label>
      <input
        id="name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Jane Doe"
        className="w-full rounded-xl border-2 border-[var(--border)] bg-[var(--surface-raised)]
                   p-3 outline-none focus:border-[var(--brand)]"
      />

      <button
        type="button"
        disabled={!ready}
        onClick={() => onDone(normalized!, name.trim())}
        className="btn-primary mt-8"
      >
        Start
      </button>

      <p className="mt-6 text-xs leading-relaxed text-[var(--muted)]">
        Everything stays in this browser. Nothing is uploaded from here: you
        download a PDF and hand that in. Your questions are selected from your
        Andrew ID, so they differ from your neighbour's.
      </p>
    </div>
  )
}
