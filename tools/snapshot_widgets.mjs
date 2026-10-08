/**
 * Write a static PNG of every interactive figure in a deck, for viewers that
 * do not run scripts.
 *
 *     node tools/snapshot_widgets.mjs 12
 *
 * A widget slide is `<div class="cw compact" data-widget="...">` with widgets.js
 * building the figure at load. The VS Code Marp preview never runs a deck's
 * <script> tags, and neither does a PDF export, so there the div is empty and
 * the slide looks blank. Each div therefore carries an <img> of the figure,
 * which widgets.js removes when it does run:
 *
 *     <div class="cw compact" data-widget="conv2d" data-mode="kernel">
 *       <img src="figures/widget-conv2d-kernel.png" alt="..."></div>
 *
 * This script makes those images by rendering the deck with marp, opening each
 * widget slide in Chrome at the deck's own 1280×720 size, and screenshotting
 * the live figure in its initial state. The file name is widget-<name>.png, or
 * widget-<name>-<mode>.png when the div has a data-mode. Rerun it whenever
 * widgets.js or a lecture's widget data changes, the same rule the figure
 * scripts follow.
 *
 * Needs marp on PATH, puppeteer-core from `game/node_modules`, and a local
 * Chrome, the same as tools/check_slide_overflow.mjs.
 */
import { copyFileSync, existsSync, mkdtempSync, readdirSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '..')

const PUPPETEER = resolve(REPO, 'game/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js')
if (!existsSync(PUPPETEER)) {
  console.error('puppeteer-core not found. Run `npm ci` in game/ first.')
  process.exit(2)
}
const puppeteer = (await import(pathToFileURL(PUPPETEER).href)).default

const CHROME = process.env.CHROME_PATH
  || [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium-browser',
    '/usr/bin/chromium',
  ].find(existsSync)
if (!CHROME) {
  console.error('No Chrome found. Set CHROME_PATH.')
  process.exit(2)
}

const arg = process.argv[2]
if (!arg || !/^\d+[a-z]?$/.test(arg)) {
  console.error('usage: node tools/snapshot_widgets.mjs <lecture number>')
  process.exit(2)
}
const lec = 'l' + arg.padStart(2, '0')
const deck = join(REPO, 'lectures', lec, 'slides.md')
const figures = join(REPO, 'lectures', lec, 'figures')

// Render the way CI does: from the repo root, so .marprc.yml finds the theme,
// with the widget scripts copied beside the output.
const out = mkdtempSync(join(tmpdir(), 'widgets-'))
execFileSync('marp', [deck, '-o', join(out, 'index.html')], { cwd: REPO, stdio: ['ignore', 'inherit', 'inherit'] })  // marp reads a non-TTY stdin as input
for (const f of readdirSync(join(REPO, '_static'))) {
  if (f.endsWith('.js')) copyFileSync(join(REPO, '_static', f), join(out, f))
}

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
})
const page = await browser.newPage()
const errors = []
page.on('pageerror', e => errors.push(e.message))
await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: 1 })
const url = pathToFileURL(join(out, 'index.html')).href
await page.goto(url, { waitUntil: 'load' })

const slides = await page.$$eval('section', ss => ss
  .map((s, i) => {
    const w = s.querySelector('.cw[data-widget]')
    if (!w) return null
    const mode = w.getAttribute('data-mode')
    return { n: i + 1, name: w.getAttribute('data-widget') + (mode ? '-' + mode : '') }
  })
  .filter(Boolean))

let failed = 0
for (const { n, name } of slides) {
  await page.goto(url + '#' + n, { waitUntil: 'load' })
  // MARP's on-screen navigation bar shows for a moment after every slide change and
  // would land in the screenshot over the widget.
  await page.addStyleTag({ content: '.bespoke-marp-osc { display: none !important; }' })
  await new Promise(r => setTimeout(r, 400))
  // Each MARP slide sits in its own <svg>, so :nth-of-type counts 1 for every
  // section; index the full list instead.
  const node = (await page.evaluateHandle(
    k => document.querySelectorAll('section')[k - 1].querySelector('.cw[data-widget]'), n)).asElement()
  const ready = node && await node.evaluate(e => !!e.getAttribute('data-ready') && !e.querySelector('.cw-missing'))
  if (!ready) {
    console.error(`slide ${n}: ${name} did not render`)
    failed++
    continue
  }
  const file = join(figures, `widget-${name}.png`)
  await node.screenshot({ path: file })
  console.log(`slide ${n}: ${file.slice(REPO.length + 1)}`)
}
await browser.close()
if (errors.length) console.error('page errors:\n  ' + errors.join('\n  '))
process.exit(failed || errors.length ? 1 : 0)
