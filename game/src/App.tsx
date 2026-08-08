/**
 * Screen routing, and the only place the derivation is kicked off.
 *
 * No router: four screens and no URLs worth linking to. A hash router would add
 * a dependency and a class of bug (a deep link into a half-finished session)
 * for no benefit.
 */

import { useMemo, useState } from 'react'
import { loadBanks, poolOf } from './content/load.ts'
import { derive } from './seed.ts'
import { entriesFor, newSessionId, openSessionFor, type LogEntry } from './store/log.ts'
import { useProgress } from './store/useProgress.ts'
import { Home } from './ui/Home.tsx'
import { Identity } from './ui/Identity.tsx'
import { SessionPlayer } from './ui/SessionPlayer.tsx'
import { Summary } from './ui/Summary.tsx'

type Screen =
  | { name: 'home' }
  | { name: 'session'; lecture: string; sessionId: string }
  | { name: 'summary'; lecture: string }

export function App() {
  const banks = useMemo(() => loadBanks(), [])
  const { andrewId, displayName, log, setIdentity, append } = useProgress()
  const [screen, setScreen] = useState<Screen>({ name: 'home' })

  if (!andrewId) return <Identity onDone={setIdentity} />

  if (screen.name === 'session') {
    const bank = banks[screen.lecture]
    if (!bank) return null
    const served = derive(andrewId, bank.lecture, poolOf(bank), bank.pool_version, bank.serve)
    const itemsById = Object.fromEntries(bank.items.map((i) => [i.id, i]))
    return (
      <SessionPlayer
        lecture={bank.lecture}
        sessionId={screen.sessionId}
        served={served}
        itemsById={itemsById}
        resumed={entriesFor(log, screen.sessionId)}
        onAnswer={(entry: LogEntry) => append([entry])}
        onFinish={() => setScreen({ name: 'summary', lecture: bank.lecture })}
        onQuit={() => setScreen({ name: 'home' })}
      />
    )
  }

  if (screen.name === 'summary') {
    const bank = banks[screen.lecture]
    if (!bank) return null
    return (
      <Summary
        bank={bank}
        log={log}
        andrewId={andrewId}
        displayName={displayName}
        onHome={() => setScreen({ name: 'home' })}
      />
    )
  }

  return (
    <Home
      banks={banks}
      log={log}
      andrewId={andrewId}
      onStart={(lecture) => {
        // Rejoin an unfinished sitting rather than starting a second one, so a
        // student who quit or refreshed at item six carries on from item six.
        const servedFor = (id: string) => banks[id]?.serve ?? Infinity
        const open = openSessionFor(log, lecture, servedFor)
        setScreen({
          name: 'session',
          lecture,
          sessionId: open ?? newSessionId(andrewId, lecture, Date.now()),
        })
      }}
      onEvidence={(lecture) => setScreen({ name: 'summary', lecture })}
    />
  )
}
