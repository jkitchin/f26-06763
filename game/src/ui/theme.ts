/**
 * Light, dark, or whatever the system says, chosen on the map page.
 *
 * The choice is a per-viewer convenience, so it lives in localStorage, and every
 * read and write is guarded: a private window or blocked storage must leave the
 * page working on the system setting rather than throwing. Nothing graded
 * depends on it, which is why it is not in the IndexedDB log.
 */

import { useEffect, useState } from 'react'

export type ThemeChoice = 'system' | 'light' | 'dark'
const KEY = 'f26-theme'

function read(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

function apply(choice: ThemeChoice) {
  const root = document.documentElement
  if (choice === 'system') delete root.dataset.theme
  else root.dataset.theme = choice
}

const systemDark = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches

/** The choice, a setter, and the theme actually in effect. */
export function useTheme(): [ThemeChoice, (c: ThemeChoice) => void, 'light' | 'dark'] {
  const [choice, setChoice] = useState<ThemeChoice>(read)
  const [sysDark, setSysDark] = useState(systemDark)

  useEffect(() => { apply(choice) }, [choice])
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!mq) return
    const on = () => setSysDark(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  const set = (c: ThemeChoice) => {
    setChoice(c)
    try { localStorage.setItem(KEY, c) } catch { /* storage blocked: keep it for this visit */ }
  }
  const resolved = choice === 'system' ? (sysDark ? 'dark' : 'light') : choice
  return [choice, set, resolved]
}

/** Read the reduced-motion preference once per change, for the drawing loops. */
export function useReducedMotion(): boolean {
  const q = '(prefers-reduced-motion: reduce)'
  const [reduce, setReduce] = useState(() => window.matchMedia?.(q).matches ?? false)
  useEffect(() => {
    const mq = window.matchMedia?.(q)
    if (!mq) return
    const on = () => setReduce(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return reduce
}
