/**
 * Where Chrome is, for the three tests that drive a real browser.
 *
 * This exists because `routes.ts` and `nav.ts` each hardcoded
 * `/Applications/Google Chrome.app/...`, which meant they could only ever run
 * on a Mac. That was invisible for as long as they ran only on a Mac, and it is
 * exactly why they had never been added to CI: the first run that tried failed
 * with "Browser was not found at the configured executablePath". `smoke.ts` had
 * the right list all along, so the fix is one copy of it rather than a third.
 *
 * puppeteer-core deliberately downloads no browser, so the system one has to be
 * found. On the GitHub runner that is `google-chrome-stable`, the same browser
 * the slides PDF step already depends on, which is why none of this adds a
 * download to CI.
 */

import { existsSync } from 'node:fs'

const CANDIDATES = [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium-browser',
  '/usr/bin/chromium',
]

export const CHROME = CANDIDATES.find(existsSync)

/**
 * The path, or a message explaining what to install.
 *
 * Callers should fail rather than skip. A browser test that quietly passes
 * because it found no browser is worse than one that is absent: it reports
 * green for a thing it never checked.
 */
export function requireChrome(): string {
  if (CHROME) return CHROME
  throw new Error(
    'no Chrome found for the browser tests. Looked in:\n' +
      CANDIDATES.map((c) => `  ${c}`).join('\n') +
      '\nInstall Google Chrome, or set one of these paths.',
  )
}
