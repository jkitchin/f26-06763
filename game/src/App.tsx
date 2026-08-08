/**
 * Screen routing, and the only place the derivation is kicked off.
 *
 * Routes live in the hash so each module has a URL that can be linked from a
 * Canvas assignment; see route.ts for why hash and not path. A deep link to a
 * module from a student who has not identified themselves yet shows the
 * identity screen first and then continues to the module they asked for,
 * rather than dumping them on the list having forgotten where they were going.
 */

import { useEffect, useMemo, useState } from 'react'
import { loadBanks, poolOf } from './content/load.ts'
import { parseHash, toHash, type Route } from './route.ts'
import { derive } from './seed.ts'
import { entriesFor, newSessionId, openSessionFor, type LogEntry } from './store/log.ts'
import { useProgress } from './store/useProgress.ts'
import { Home } from './ui/Home.tsx'
import { Identity } from './ui/Identity.tsx'
import { SessionPlayer } from './ui/SessionPlayer.tsx'
import { Summary } from './ui/Summary.tsx'

export function App() {
  const banks = useMemo(() => loadBanks(), [])
  const { andrewId, displayName, log, storageOk, setIdentity, append } = useProgress()
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))

  // Keep the address bar and the screen in step, both ways, so the browser's
  // back button works and a copied URL reopens what is on screen.
  useEffect(() => {
    const onHash = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (next: Route) => {
    if (toHash(next) !== window.location.hash) window.location.hash = toHash(next)
    setRoute(next)
  }

  const servedFor = (id: string) => banks[id]?.serve ?? Infinity

  // A route to a lecture with no bank is a stale link; fall back rather than
  // rendering nothing.
  const target = route.name === 'home' ? null : banks[route.lecture]
  if (route.name !== 'home' && !target) {
    if (window.location.hash !== '#/') window.location.hash = '#/'
    return <Home banks={banks} log={log} andrewId={andrewId} storageOk={storageOk}
                 onStart={(l) => go({ name: 'session', lecture: l })}
                 onEvidence={(l) => go({ name: 'summary', lecture: l })} />
  }

  if (!andrewId) {
    // Identify first, then carry on to wherever the link pointed.
    return <Identity onDone={(id, name) => setIdentity(id, name)} />
  }

  if (route.name === 'session' && target) {
    const sessionId =
      openSessionFor(log, target.lecture, servedFor) ??
      newSessionId(andrewId, target.lecture, Date.now())
    const served = derive(andrewId, target.lecture, poolOf(target), target.pool_version, target.serve)
    const itemsById = Object.fromEntries(target.items.map((i) => [i.id, i]))
    return (
      <SessionPlayer
        key={`${target.lecture}/${sessionId}`}
        lecture={target.lecture}
        sessionId={sessionId}
        served={served}
        itemsById={itemsById}
        resumed={entriesFor(log, sessionId)}
        onAnswer={(entry: LogEntry) => append([entry])}
        onFinish={() => go({ name: 'summary', lecture: target.lecture })}
        onQuit={() => go({ name: 'home' })}
      />
    )
  }

  if (route.name === 'summary' && target) {
    return (
      <Summary
        bank={target}
        log={log}
        andrewId={andrewId}
        displayName={displayName}
        onHome={() => go({ name: 'home' })}
      />
    )
  }

  return (
    <Home
      banks={banks}
      log={log}
      andrewId={andrewId}
      storageOk={storageOk}
      onStart={(lecture) => go({ name: 'session', lecture })}
      onEvidence={(lecture) => go({ name: 'summary', lecture })}
    />
  )
}
