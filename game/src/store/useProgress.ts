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
import type { LogEntry } from './log.ts'

export const SAVE_VERSION = 1
const STORAGE_KEY = 'f26-06763-game/progress'

export interface Settings {
  /** Off by default. Adult learners resent hearts; opt in, don't opt out. */
  hearts: boolean
  theme: 'system' | 'light' | 'dark'
}

export const DEFAULT_SETTINGS: Settings = { hearts: false, theme: 'system' }

export interface SaveData {
  version: number
  /** Normalized Andrew ID. Drives the whole derivation, so it is confirmed
   *  back to the student before anything is built on it. */
  andrewId: string
  displayName: string
  log: LogEntry[]
  settings: Settings
}

export interface ProgressState extends SaveData {
  /**
   * False once a read or write to IndexedDB has failed. Not persisted, for the
   * obvious reason. Surfaced in the UI rather than only in the console: Safari
   * in private mode rejects IndexedDB outright, and a student whose progress is
   * silently memory-only will lose a module to a refresh and have no idea why.
   */
  storageOk: boolean
  setIdentity: (andrewId: string, displayName: string) => void
  append: (entries: LogEntry[]) => void
  setSettings: (patch: Partial<Settings>) => void
  exportSave: () => string
  reset: () => void
}

const initial = (): SaveData & { storageOk: boolean } => ({
  storageOk: true,
  version: SAVE_VERSION,
  andrewId: '',
  displayName: '',
  log: [],
  settings: { ...DEFAULT_SETTINGS },
})

/**
 * IndexedDB is not always there: Safari in private mode rejects it, quotas run
 * out, and it does not exist under node. None of that should take down a
 * session in progress, so a storage failure degrades to memory-only and says so
 * once rather than throwing on every answer.
 */
let warned = false

function onStorageError(op: string, err: unknown): null {
  // Referenced lazily: this runs long after module init, so the store exists.
  useProgress?.setState({ storageOk: false })
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
      // storageOk is deliberately absent: a flag saying "saving is broken" has
      // no business being saved.
      partialize: ({ version, andrewId, displayName, log, settings }) => ({
        version,
        andrewId,
        displayName,
        log,
        settings,
      }),
    },
  ),
)
