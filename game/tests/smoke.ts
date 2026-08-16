/**
 * End-to-end smoke test: does a student can actually finish a module?
 *
 *     cd game && npm run build && npm run smoke
 *
 * Everything else in this repository tests a layer. This drives the built
 * bundle in a real browser, through the real screens, and asserts the things
 * that only break once assembled:
 *
 *   - the app mounts at the deployed base path rather than white-screening,
 *     which is the failure a wrong Vite `base` produces and which every
 *     file-exists check happily passes
 *   - a session can be completed start to finish
 *   - two Andrew IDs are served different items
 *   - the evidence PDF actually downloads, with bytes in it
 *   - the map renders, walks, and remembers where you have been
 *   - nothing lands in the console
 *
 * Uses puppeteer-core against the system Chrome, so there is no browser
 * download in CI or on a laptop.
 */

import { createServer } from 'node:http'
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync } from 'node:fs'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import puppeteer, { type Browser, type Page } from 'puppeteer-core'
import { CHROME } from './chrome.ts'

const DIST = fileURLToPath(new URL('../dist/', import.meta.url))
const DOWNLOADS = fileURLToPath(new URL('./downloads/', import.meta.url))
const BASE = '/f26-06763/game/'
const PORT = 8732



const TYPES: Record<string, string> = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
}

let failures = 0
function check(ok: boolean, label: string, detail = '') {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? `  ${detail}` : ''}`)
  if (!ok) failures++
}

/** Serve dist/ under the deployed base, so the built asset paths resolve. */
function serve() {
  return createServer((req, res) => {
    const path = (req.url ?? '/').split('?')[0]!
    if (!path.startsWith(BASE)) {
      res.writeHead(404).end()
      return
    }
    let rel = path.slice(BASE.length) || 'index.html'
    if (rel.endsWith('/')) rel += 'index.html'
    const file = join(DIST, rel)
    if (!existsSync(file)) {
      res.writeHead(404).end()
      return
    }
    res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' })
    res.end(readFileSync(file))
  })
}

/** Play one module to completion, returning the item ids in served order. */
async function playModule(page: Page, andrewId: string, name: string): Promise<string[]> {
  await page.goto(`http://localhost:${PORT}${BASE}`, { waitUntil: 'networkidle0' })

  // The identity form appears only until it has been answered. A second run in
  // the same browser goes straight to the module list, which is the whole point
  // of the retake test below.
  const idForm = await page.$('#andrew')
  if (idForm) {
    await page.type('#andrew', andrewId)
    await page.type('#name', name)
    await page.click('button.btn-primary')
  }

  // Home -> start the first module.
  await page.waitForSelector('button.btn-primary')
  await page.click('button.btn-primary')

  const seen: string[] = []
  for (let guard = 0; guard < 60; guard++) {
    const done = await page.$('h1')
    if (done) {
      const text = await page.evaluate((el) => el.textContent ?? '', done)
      if (text.includes('complete')) break
    }

    // The kind/rung line is the only per-item marker in the DOM; the item id
    // is not rendered, so record the prompt's first line instead.
    const prompt = await page.$eval('.prose-tight', (el) => el.textContent ?? '').catch(() => '')
    if (prompt) seen.push(prompt.slice(0, 60))

    // Predict items gate on a written prediction.
    const textarea = await page.$('textarea')
    const isPredict = await page.$eval('button.btn-primary', (el) => el.textContent ?? '')
    if (textarea && isPredict.includes('Lock it in')) {
      await textarea.type('my expectation')
      await page.click('button.btn-primary')
      await new Promise((r) => setTimeout(r, 60))
    }

    // Free-response items have a textarea and a "Show the checklist" button.
    const label = await page.$eval('button.btn-primary', (el) => el.textContent ?? '')
    if (label.includes('Show the checklist')) {
      await page.click('button.btn-primary')
      await new Promise((r) => setTimeout(r, 60))
      await page.click('button.btn-primary')
      await new Promise((r) => setTimeout(r, 60))
      continue
    }

    // Choice item. Wrong answers rule an option out and hand control straight
    // back, so an attempt is "click a live option, Check" with no second button.
    if ((await page.$$('div.grid button')).length) {
      for (let attempt = 0; attempt < 8; attempt++) {
        const fresh = await page.$$('div.grid button')
        let clicked = false
        for (const o of fresh) {
          if (!(await page.evaluate((e) => (e as HTMLButtonElement).disabled, o))) {
            await o.click(); clicked = true; break
          }
        }
        if (!clicked) break
        await page.click('button.btn-primary')
        await new Promise((r) => setTimeout(r, 80))
        const label = await page.$eval('button.btn-primary', (el) => el.textContent ?? '')
        if (label.includes('Continue') || label.includes('Finish')) {
          await page.click('button.btn-primary')
          await new Promise((r) => setTimeout(r, 120))
          break
        }
      }
    }
  }
  return seen
}

async function main() {
  if (!CHROME) {
    console.log('no system Chrome found; skipping smoke test')
    return 0
  }
  rmSync(DOWNLOADS, { recursive: true, force: true })
  mkdirSync(DOWNLOADS, { recursive: true })

  const server = serve()
  await new Promise<void>((r) => server.listen(PORT, r))

  let browser: Browser | undefined
  try {
    browser = await puppeteer.launch({
      executablePath: CHROME,
      headless: true,
      args: ['--no-sandbox', '--disable-dev-shm-usage'],
    })

    const errors: string[] = []
    const page = await browser.newPage()
    // Record the URL, not just "404": an anonymous failed-resource message is
    // undiagnosable, and the first run of this test spent a while on one.
    const watch = (p: Page) => {
      p.on('console', (m) => {
        if (m.type() === 'error') errors.push(m.text())
      })
      p.on('pageerror', (e) => errors.push(String(e)))
      p.on('requestfailed', (r) => errors.push(`request failed: ${r.url()}`))
      p.on('response', (r) => {
        if (r.status() >= 400) errors.push(`HTTP ${r.status()}: ${r.url()}`)
      })
    }
    watch(page)

    console.log('smoke:')

    const first = await playModule(page, 'jkitchin', 'John Kitchin')
    check(first.length > 0, 'a module can be completed', `${first.length} items answered`)

    const heading = await page.$eval('h1', (el) => el.textContent ?? '').catch(() => '')
    check(heading.includes('complete'), 'reaches the summary screen', heading)

    // The summary must say which attempt this was, because that number is what
    // a grader reads next to the score.
    const firstSummary = await page.$eval('body', (el) => el.textContent ?? '')
    check(/This is attempt 1\b/.test(firstSummary), 'the first run reports attempt 1')
    check(/scored \d+%/.test(firstSummary), 'and reports a participation score',
      (firstSummary.match(/scored \d+%/) ?? [''])[0])

    // THE RETAKE. This is the one seam the unit tests cannot reach: the app has
    // to count the completed sitting, derive the next attempt from it, and store
    // that number on the new sitting. Same browser, same student, same module,
    // straight after finishing it once.
    const retake = await playModule(page, 'jkitchin', 'John Kitchin')
    const repeated = retake.filter((q) => first.includes(q))
    check(retake.length > 0, 'the module can be played a second time',
      `${retake.length} items answered`)
    check(repeated.length === 0,
      'a retake serves entirely different questions',
      `${repeated.length} of ${retake.length} repeated from the first run`)

    const retakeSummary = await page.$eval('body', (el) => el.textContent ?? '')
    check(/This is attempt 2\b/.test(retakeSummary), 'and the summary says attempt 2')

    // The retake left us on its own summary, whose primary button is already
    // "Download the PDF". Go back to the module list and re-enter through the
    // "Download PDF" button instead, because that is the path a student
    // actually uses the next day, and it is the one that regenerates a PDF from
    // the log rather than from anything still in component state.
    await page.goto(`http://localhost:${PORT}${BASE}`, { waitUntil: 'networkidle0' })
    await page.waitForSelector('button.btn-quiet')
    await page.click('button.btn-quiet')
    await page.waitForSelector('button.btn-primary')

    // The PDF download.
    const client = await page.createCDPSession()
    await client.send('Page.setDownloadBehavior', {
      behavior: 'allow',
      downloadPath: DOWNLOADS,
    })
    await page.click('button.btn-primary')
    await new Promise((r) => setTimeout(r, 2500))
    const files = readdirSync(DOWNLOADS).filter((f) => f.endsWith('.pdf'))
    const size = files[0] ? readFileSync(join(DOWNLOADS, files[0])).length : 0
    check(files.length === 1, 'the evidence PDF downloads', files[0] ?? '(none)')
    check(size > 5000, 'the PDF has real content', `${size} bytes`)
    // Pattern, not a literal: which module comes first depends on how many
    // banks are published, and an assertion on "l15" quietly became wrong the
    // day L01 was authored.
    check(
      /^l\d\d-evidence-jkitchin\.pdf$/.test(files[0] ?? ''),
      'the filename identifies student and module',
      files[0] ?? '',
    )

    // A second student needs an isolated browser context: progress lives in
    // IndexedDB, so a plain new tab is still signed in as the first student and
    // never sees the identity screen at all.
    const context = await browser.createBrowserContext()
    const page2 = await context.newPage()
    watch(page2)
    const second = await playModule(page2, 'valves', 'Victor Alves')
    const samePosition = first.filter((p, i) => p === second[i]).length
    check(
      samePosition < first.length,
      'two students are served different items',
      `${samePosition}/${first.length} positions match`,
    )

    // --- the map ----------------------------------------------------------
    //
    // Walking is the one thing no unit test can reach: tests/map.ts proves the
    // world holds together and that a visit is inert to grading, but only a
    // browser proves an arrow key moves a sprite, that standing somewhere
    // records it, and that the record survives a reload. The last of those is
    // the requirement the whole persistence commit exists for, checked here
    // end to end rather than in a simulation.
    await page.goto(`http://localhost:${PORT}${BASE}#/map`, { waitUntil: 'networkidle0' })
    await page.waitForSelector('[role="application"]')

    const roomCount = await page.$$eval('[role="application"] button', (b) => b.length)
    check(roomCount === 25, 'every session on the schedule is drawn', `${roomCount} rooms`)

    const coverageOf = () =>
      page.$$eval('p', (ps) =>
        ps.map((p) => p.textContent ?? '').find((t) => /rooms visited/.test(t)) ?? '')
    const before = await coverageOf()

    // Up from spawn into L1, then right along the top row as far as L3.
    //
    // L3 specifically, and this is not arbitrary. The first version stopped at
    // L2 and asserted a corridor was lit, which failed: L2 has no corridors at
    // all, citing nothing and cited by nothing. That is a true fact about the
    // course rather than a bug, and the assertion was the thing that was wrong.
    const walk = ['ArrowUp', 'ArrowUp', 'ArrowUp', 'ArrowUp',
                  'ArrowRight', 'ArrowRight', 'ArrowRight'] as const
    for (const key of walk) {
      await page.keyboard.press(key)
      await new Promise((r) => setTimeout(r, 60))
    }
    const after = await coverageOf()
    check(before !== after, 'walking visits rooms', `${before.trim()} -> ${after.trim()}`)

    const panel = await page.$eval('section h2', (h) => h.textContent ?? '')
    check(/^L\d/.test(panel), 'standing in a room shows what it covers', panel.slice(0, 48))

    // A corridor is the point of the map, so an empty one is a silent failure.
    const lines = await page.$$eval('svg line', (l) => l.length)
    check(lines > 0, 'corridors are drawn from the room you are standing in', `${lines} lit`)

    // Reload: visits are events in the same IndexedDB log as answers, so if
    // this resets, so does everything else.
    await page.reload({ waitUntil: 'networkidle0' })
    await page.waitForSelector('[role="application"]')
    const restored = await coverageOf()
    check(restored === after, 'visited rooms survive a reload', `${restored.trim()}`)

    check(errors.length === 0, 'no console errors', errors.slice(0, 2).join(' | '))
  } finally {
    await browser?.close()
    server.close()
  }

  console.log(failures ? `\n${failures} check(s) failed` : '\nall checks passed')
  return failures ? 1 : 0
}

process.exit(await main())
