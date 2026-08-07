/**
 * "Pick one of N", shared by every choice-shaped item kind.
 *
 * Keyboard-first: digits and the home row both select. On a desktop reading app
 * that roughly halves the time a session takes, for the cost of one listener.
 *
 * Options arrive already shuffled into this student's served order. The index
 * passed to `onSelect` is a position in *that* order; the caller maps it back to
 * an option id before recording anything, because an option id has to index the
 * original pool order or the answer stops being checkable.
 */

import { useEffect } from 'react'

const HOME_ROW = ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l']

interface Props {
  options: string[]
  selected: number | null
  onSelect: (index: number) => void
  /** Once set the grid is read-only and paints the answer. */
  revealed: { answerIndex: number } | null
}

function isTypingTarget(e: KeyboardEvent): boolean {
  const el = e.target as HTMLElement | null
  return !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)
}

export function ChoiceGrid({ options, selected, onSelect, revealed }: Props) {
  useEffect(() => {
    if (revealed) return
    const onKey = (e: KeyboardEvent) => {
      if (isTypingTarget(e) || e.metaKey || e.ctrlKey || e.altKey) return
      let i = -1
      if (/^[1-9]$/.test(e.key)) i = Number(e.key) - 1
      else {
        const h = HOME_ROW.indexOf(e.key.toLowerCase())
        if (h >= 0) i = h
      }
      if (i >= 0 && i < options.length) {
        e.preventDefault()
        onSelect(i)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [options.length, onSelect, revealed])

  return (
    <div className="grid gap-3">
      {options.map((option, i) => {
        const isSelected = selected === i
        const isAnswer = revealed?.answerIndex === i
        const isWrongPick = revealed !== null && isSelected && !isAnswer

        let tone = 'border-[var(--border)] bg-[var(--surface-raised)]'
        if (isAnswer) tone = 'border-[var(--correct)] bg-[var(--correct-wash)]'
        else if (isWrongPick) tone = 'border-[var(--wrong)] bg-[var(--wrong-wash)]'
        else if (isSelected) tone = 'border-[var(--brand)] bg-[var(--brand-wash)]'

        return (
          <button
            key={option}
            type="button"
            disabled={revealed !== null}
            onClick={() => onSelect(i)}
            aria-pressed={isSelected}
            className={`flex items-start gap-3 rounded-xl border-2 px-4 py-3 text-left
                        transition-colors disabled:cursor-default ${tone}`}
          >
            <kbd
              className="mt-0.5 shrink-0 rounded border border-[var(--border)]
                         px-1.5 py-0.5 font-mono text-xs text-[var(--muted)]"
            >
              {HOME_ROW[i]?.toUpperCase() ?? i + 1}
            </kbd>
            <span className="text-[15px] leading-snug">{option}</span>
          </button>
        )
      })}
    </div>
  )
}
