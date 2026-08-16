/**
 * The save format, and how an old one becomes a current one.
 *
 * Separate from the store on purpose. This is the part with rules a test needs
 * to pin down, and importing the store to reach it boots IndexedDB, which does
 * not exist under node. Keeping the format in its own module means
 * `tests/persistence.ts` can exercise every migration path without a browser.
 */

import type { Event } from './log.ts'

export const SAVE_VERSION = 2

export interface Settings {
  /** Off by default. Adult learners resent hearts; opt in, don't opt out. */
  hearts: boolean
  theme: 'system' | 'light' | 'dark'
}

export const DEFAULT_SETTINGS: Settings = { hearts: false, theme: 'system' }

/** A save that could not be understood, kept verbatim rather than discarded. */
export interface Quarantined {
  at: number
  from: number
  why: string
  blob: string
}

export interface SaveData {
  version: number
  /** Normalized Andrew ID. Drives the whole derivation, so it is confirmed
   *  back to the student before anything is built on it. */
  andrewId: string
  displayName: string
  log: Event[]
  settings: Settings
}

/**
 * A blank save. Also the floor every migration builds on, so a field added
 * here is a field an old save is guaranteed to come back with.
 */
export const initial = (): SaveData & {
  storageOk: boolean; hydrated: boolean; quarantine: Quarantined[]
} => ({
  storageOk: true,
  hydrated: false,
  quarantine: [],
  version: SAVE_VERSION,
  andrewId: '',
  displayName: '',
  log: [],
  settings: { ...DEFAULT_SETTINGS },
})

const isRec = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v)
const str = (v: unknown): string => (typeof v === 'string' ? v : '')
const clip = (v: unknown): string => {
  try { return JSON.stringify(v).slice(0, 20_000) } catch { return String(v).slice(0, 20_000) }
}

/**
 * Migrate a persisted save. Total: never throws, for any input.
 *
 * Two reasons it has to be total. zustand calls this inside its hydrate chain
 * and then destructures the result; a throw leaves it destructuring undefined,
 * which aborts hydration silently and lets the next setState write an empty log
 * over the real one. And with no `migrate` supplied at all, which is what this
 * store had, a version bump discards every student's log outright.
 *
 * Unmigratable means preserve and quarantine, not reset. A student's log may be
 * the only record that they did the work, and a version number is not entitled
 * to make that call.
 */
export function migrate(persisted: unknown, from: number): SaveData & { quarantine: Quarantined[] } {
  const base = () => ({ ...initial(), version: SAVE_VERSION })
  const quarantineOf = (why: string): SaveData & { quarantine: Quarantined[] } => ({
    ...base(),
    andrewId: isRec(persisted) ? str(persisted.andrewId) : '',
    displayName: isRec(persisted) ? str(persisted.displayName) : '',
    quarantine: [{ at: 0, from, why, blob: clip(persisted) }],
  })

  if (!isRec(persisted)) return quarantineOf('saved value was not an object')
  const carried = Array.isArray(persisted.quarantine)
    ? (persisted.quarantine as Quarantined[]) : []

  try {
    const log = Array.isArray(persisted.log) ? (persisted.log as Event[]) : []
    // A save from a newer build is copied through, not downgraded. Unknown
    // event kinds are ignored by every derivation, so an older build reading a
    // newer log shows less rather than wrong, and a stale cached tab cannot eat
    // a newer tab's work.
    return {
      ...base(),
      andrewId: str(persisted.andrewId),
      displayName: str(persisted.displayName),
      settings: isRec(persisted.settings)
        ? { ...DEFAULT_SETTINGS, ...(persisted.settings as Partial<Settings>) }
        : { ...DEFAULT_SETTINGS },
      // The log is carried whole, at every version, and this deliberately does
      // not branch on `from`.
      //
      // A v1 log is bare answers with no recorded plan, and an earlier draft
      // stripped anything that did not look like one. That was both lossy and
      // pointless: `sessionsOf` walks outward from `opened` events, so an answer
      // with no plan is already inert, and the filter only mattered when it
      // guessed wrong. It guessed wrong on the first save it met, because a save
      // that has lost its version field reads as NaN, fails `from >= 2`, and had
      // its plans deleted for it. The version field is a claim; the log is the
      // evidence, so the evidence is what survives.
      log,
      quarantine: carried,
    }
  } catch (err) {
    return { ...quarantineOf(`migration ${from} -> ${SAVE_VERSION} threw: ${String(err)}`),
             quarantine: [...carried, ...quarantineOf(String(err)).quarantine] }
  }
}


/**
 * Read whatever was persisted into a usable save, whatever it turns out to be.
 *
 * zustand runs `migrate` only when the stored blob carries a `version` field,
 * and a hand-edited or imported save is exactly the one that will not, so the
 * shape check cannot live in `migrate` alone. Everything goes through here, and
 * the store's `merge` does nothing but spread the result.
 */
export function readSave(persisted: unknown): SaveData & { quarantine: Quarantined[] } {
  if (!isRec(persisted)) return migrate(persisted, -1)
  const wellFormed =
    Array.isArray(persisted.log) &&
    persisted.log.every((e) => isRec(e) && typeof e.at === 'number')
  return wellFormed && typeof persisted.version === 'number'
    ? {
        ...initial(),
        ...(persisted as unknown as SaveData),
        version: SAVE_VERSION,
        quarantine: Array.isArray(persisted.quarantine)
          ? (persisted.quarantine as Quarantined[])
          : [],
      }
    : migrate(persisted, Number(persisted.version ?? -1))
}
