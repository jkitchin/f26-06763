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
import { loadBanks } from './content/load.ts'
import { parseHash, toHash, type Route } from './route.ts'
import { useProgress } from './store/useProgress.ts'
import { Home } from './ui/Home.tsx'
import { Identity } from './ui/Identity.tsx'
import { SessionRoute } from './ui/SessionRoute.tsx'
import { Summary } from './ui/Summary.tsx'

export function App() {
  const banks = useMemo(() => loadBanks(), [])
  const { andrewId, displayName, log, storageOk, hydrated, setIdentity } = useProgress()
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

  // Nothing renders from the log until IndexedDB has been read. Without this
  // gate the first paint is computed from an empty log, so a returning student
  // sees a flash of the identity screen and a fast one can type into it, and
  // that write lands before hydration and takes their progress with it.
  if (!hydrated) return <p className="p-8 text-[var(--muted)]">Restoring your progress…</p>

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
    return (
      <SessionRoute
        key={target.lecture}
        bank={target}
        andrewId={andrewId}
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
