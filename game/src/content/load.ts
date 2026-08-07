/**
 * Load the item bank.
 *
 * YAML is the authoring format because items carry a lot of prose and need
 * comments, and JSON has neither. Vite inlines the files at build time via
 * `import.meta.glob(eager)`, so the shipped bundle makes no network request for
 * content and the app works offline and off a file:// URL.
 *
 * The same parsing runs under plain Node for the test fixtures, which is what
 * keeps the sample PDFs and the verifier looking at one pool rather than two.
 */

import { parse } from 'yaml'

export interface Item {
  id: string
  kind: string
  rung: number
  objectives: string[]
  prompt: string
  predict?: { ask: string; common_prior: string }
  options?: string[]
  answer?: string | null
  checklist?: { text: string; needle: string }[]
  evidence: string
  source: { file: string; heading?: string; quote: string }
  verify: { mode: string; needle: string; volatility: string; expires?: string }
  tags?: string[]
}

export interface Bank {
  schema: number
  lecture: string
  title: string
  source_notes: string
  status: string
  serve: number
  pool_version: number
  items: Item[]
}

/** id -> the shape derive() needs. Keep in step with tools/derive.py. */
export function poolOf(bank: Bank): Record<string, { options?: string[] }> {
  const pool: Record<string, { options?: string[] }> = {}
  for (const item of bank.items) pool[item.id] = { options: item.options ?? [] }
  return pool
}

export function parseBank(text: string): Bank {
  return parse(text) as Bank
}

/** Every bank, keyed by lecture id. Browser build only. */
export function loadBanks(): Record<string, Bank> {
  const files = import.meta.glob('../../content/l*.yml', {
    eager: true,
    query: '?raw',
    import: 'default',
  }) as Record<string, string>

  const banks: Record<string, Bank> = {}
  for (const text of Object.values(files)) {
    const bank = parseBank(text)
    if (bank?.lecture && bank.status !== 'unwritten') banks[bank.lecture] = bank
  }
  return banks
}
