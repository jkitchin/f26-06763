/**
 * The save file: one zustand store, persisted to IndexedDB.
 *
 * Everything the student has done lives in `log`, which is append-only. Levels,
 * completion and streaks are all recomputed from it (see log.ts for why).
 * Settings are the only mutable state, and nothing in the evidence PDF depends
 * on them.
 */

import { create } from 'zustand'
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware'
import { del, get, set } from 'idb-keyval'
import type { Event, PlannedItem, SessionOpened } from './log.ts'
import { openSessionFor } from './log.ts'
import {
  initial, migrate, readSave, SAVE_VERSION,
  type Quarantined, type SaveData, type Settings,
} from './migrate.ts'

export { migrate, SAVE_VERSION }
export { DEFAULT_SETTINGS } from './migrate.ts'
export type { Quarantined, SaveData, Settings }

const STORAGE_KEY = 'f26-06763-game/progress'

export interface ProgressState extends SaveData {
  /**
   * False once a read or write to IndexedDB has failed. Not persisted, for the
   * obvious reason. Surfaced in the UI rather than only in the console: Safari
   * in private mode rejects IndexedDB outright, and a student whose progress is
   * silently memory-only will lose a module to a refresh and have no idea why.
   */
  storageOk: boolean
  /**
   * False until IndexedDB has been read. Everything that renders from the log
   * waits for it: without a gate the first paint is computed from an empty log,
   * so a returning student sees a flash of the identity screen, and a fast one
   * can type into it and have that write land before hydration.
   */
  hydrated: boolean
  /** Saves that could not be migrated. Kept, never discarded. */
  quarantine: Quarantined[]
  setIdentity: (andrewId: string, displayName: string) => void
  append: (entries: Event[]) => void
  /**
   * Record the premise of a sitting, and return its id. Idempotent per lecture:
   * if an unfinished sitting exists its id comes back untouched, because a
   * second plan for the same sitting is how a student ends up half-answering
   * two different derivations.
   */
  openSession: (
    lecture: string,
    andrewId: string,
    plan: PlannedItem[],
    content: { pool_version: number; serve: number },
    attempt: number,
  ) => string
  setSettings: (patch: Partial<Settings>) => void
  exportSave: () => string
  reset: () => void
}


/**
 * IndexedDB is not always there: Safari in private mode rejects it, quotas run
 * out, and it does not exist under node. None of that should take down a
 * session in progress, so a storage failure degrades to memory-only and says so
 * once rather than throwing on every answer.
 */
let warned = false

/**
 * Set if storage fails before the store finishes being created, and applied the
 * moment it has been.
 *
 * This is not hypothetical tidiness. zustand's `persist` calls `getItem` from
 * inside `createStore`, so a storage layer that rejects immediately reports the
 * failure while `useProgress` is still in its temporal dead zone. Touching the
 * binding there threw a ReferenceError out of the hydrate chain, which took out
 * hydration itself and left `storageOk` stuck at true. The case that does
 * reject immediately is Safari in private mode, which is precisely the case
 * this flag exists to warn about, so the warning was broken exactly when it was
 * needed.
 */
let storageFailedEarly = false

function onStorageError(op: string, err: unknown): null {
  try {
    useProgress.setState({ storageOk: false })
  } catch {
    storageFailedEarly = true
  }
  if (!warned) {
    warned = true
    console.warn(
      `06-763 game: could not ${op} saved progress, continuing without saving. ` +
        `Finish the module in this tab and download the PDF before closing it.`,
      err,
    )
  }
  return null
}

const idbStorage: StateStorage = {
  getItem: async (name) => {
    try {
      return (await get<string>(name)) ?? null
    } catch (err) {
      return onStorageError('read', err)
    }
  },
  setItem: async (name, value) => {
    try {
      await set(name, value)
    } catch (err) {
      onStorageError('write', err)
    }
  },
  removeItem: async (name) => {
    try {
      await del(name)
    } catch (err) {
      onStorageError('clear', err)
    }
  },
}

export const useProgress = create<ProgressState>()(
  persist(
    (setState, getState) => ({
      ...initial(),

      setIdentity(andrewId, displayName) {
        setState({ andrewId, displayName })
      },

      /** The only way the log grows. Appends, never replaces. */
      append(entries) {
        if (!entries.length) return
        setState({ log: [...getState().log, ...entries] })
      },

      openSession(lecture: string, andrewId: string, plan: PlannedItem[],
                  content: { pool_version: number; serve: number },
                  attempt: number): string {
        const existing = openSessionFor(getState().log, lecture)
        if (existing) return existing.session
        const at = Date.now()
        const session = `${andrewId}/${lecture}/${at}`
        const opened: SessionOpened = {
          t: 'opened', session, lecture, andrewId, plan, attempt, content, at,
        }
        setState({ log: [...getState().log, opened] })
        return session
      },

      setSettings(patch) {
        setState({ settings: { ...getState().settings, ...patch } })
      },

      exportSave() {
        const { andrewId, displayName, log, settings, version } = getState()
        return JSON.stringify({ version, andrewId, displayName, log, settings }, null, 2)
      },

      reset() {
        setState(initial())
      },
    }),
    {
      name: STORAGE_KEY,
      version: SAVE_VERSION,
      storage: createJSONStorage(() => idbStorage),
      migrate,

      /**
       * Runs on every hydration, migrated or not. zustand skips `migrate`
       * entirely when the persisted value has no `version` field, which is what
       * a hand-edited or imported save looks like, so the shape check lives
       * here where nothing can route around it.
       */
      merge: (persisted: unknown, current: ProgressState): ProgressState =>
        ({ ...current, ...readSave(persisted) }),

      /** The hydration gate, and the only place storageOk can learn about a
       *  read failure: idbStorage.getItem swallows it to keep the app alive. */
      onRehydrateStorage: () => (_state: unknown, err?: unknown) => {
        useProgress.setState({ hydrated: true, storageOk: !err } as Partial<ProgressState>)
        if (err) console.warn('06-763 game: could not restore saved progress', err)
      },
      // hydrated and storageOk are deliberately absent. A flag saying "saving
      // is broken" has no business being saved, and a persisted `hydrated: true`
      // would disarm the gate on the very next load.
      partialize: ({ version, andrewId, displayName, log, settings, quarantine }: ProgressState) => ({
        version,
        andrewId,
        displayName,
        log,
        settings,
        quarantine,
      }),
    },
  ),
)

if (storageFailedEarly) useProgress.setState({ storageOk: false })
