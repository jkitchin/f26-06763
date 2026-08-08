/**
 * Hash routing, so every module has a URL you can put in a Canvas assignment.
 *
 *   .../game/#/          the module list
 *   .../game/#/map       the course map
 *   .../game/#/l09       start or resume L09
 *   .../game/#/l09/done  the summary for L09
 *
 * Hash rather than path segments because the site is static: a path route would
 * need the server to rewrite /game/l09 back to index.html, and GitHub Pages will
 * not do that. A hash costs nothing, survives a hard refresh, and makes the
 * browser's back button work for free.
 *
 * The lecture id is the whole route. It does not carry a student, a session or
 * any progress, so a link is safe to post publicly and means the same thing for
 * everyone who opens it, while still serving each of them their own questions.
 */

export type Route =
  | { name: 'home' }
  | { name: 'map' }
  | { name: 'session'; lecture: string }
  | { name: 'summary'; lecture: string }

const LECTURE = /^l\d\d$/

/**
 * Routes with no lecture id, widened deliberately.
 *
 * Every non-home route used to be filtered through LECTURE, so any route whose
 * first segment was not a lecture fell silently back to home. That is the right
 * default for a stale link and the wrong one for a new screen: adding `#/map`
 * without adding it here would have shown the module list with no error, which
 * is the sort of bug you chase in the renderer for an hour.
 */
const STANDALONE = new Set(['map'])

export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const [head, tail] = parts
  if (!head) return { name: 'home' }
  if (STANDALONE.has(head)) return { name: head as 'map' }
  if (!LECTURE.test(head)) return { name: 'home' }
  return tail === 'done' ? { name: 'summary', lecture: head } : { name: 'session', lecture: head }
}

export function toHash(route: Route): string {
  if (route.name === 'home') return '#/'
  if (route.name === 'map') return '#/map'
  return route.name === 'summary' ? `#/${route.lecture}/done` : `#/${route.lecture}`
}

/** The link to hand a student for one module. */
export function urlFor(lecture: string): string {
  const { origin, pathname } = window.location
  return `${origin}${pathname}#/${lecture}`
}
