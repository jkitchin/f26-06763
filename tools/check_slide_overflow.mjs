/**
 * Fail when a rendered slide's content runs off the bottom of the slide.
 *
 *     node tools/check_slide_overflow.mjs _build/html/slides/l07/index.html
 *     node tools/check_slide_overflow.mjs _build/html/slides/*\/index.html
 *
 * The existing CI step checks that every <img src> in a deck resolves to a
 * file. That catches a missing figure and nothing else. A figure that resolves
 * and is simply too tall pushes the rest of the slide past the bottom edge,
 * where MARP clips it without a word: no warning, no error, a green build, and
 * a projected slide whose x-axis and closing line are gone. L7 shipped twelve
 * of those before anyone rendered it, which is why this exists.
 *
 * Only VERTICAL overflow is checked, deliberately. Horizontal measurement is
 * unreliable here because the clicker panel and the `source` span sit in flex
 * and absolute contexts whose offsetWidth does not mean what it looks like it
 * means, and every horizontal "hit" during development was a false positive.
 * A slide too wide is also visible at a glance; a slide too tall is not,
 * because the top of it looks perfect.
 *
 * Header, footer and the page number are absolutely positioned by the theme
 * and are skipped, along with anything else the author took out of flow.
 *
 * Needs puppeteer-core, which `game/node_modules` already carries for the
 * game's browser tests, and a local Chrome.
 */
import { existsSync } from 'node:fs'
import { resolve, dirname, basename } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '..')

const PUPPETEER = resolve(REPO, 'game/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js')
if (!existsSync(PUPPETEER)) {
  console.error('puppeteer-core not found. Run `npm ci` in game/ first.')
  process.exit(2)
}
const puppeteer = (await import(pathToFileURL(PUPPETEER).href)).default

/** Chrome, wherever this is running. CI sets CHROME_PATH. */
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

/**
 * Slack, in px of a 720px-tall slide.
 *
 * Not zero. A descender on the last line of a list, or a rounded line-height,
 * routinely puts a few px past the padding box without anything being visibly
 * cut. Eight px is below one line of body text at this theme's size, so a real
 * clipped line always beats it, and the course's other six decks pass.
 */
const SLACK = 8

const files = process.argv.slice(2)
if (!files.length) {
  console.error('usage: node tools/check_slide_overflow.mjs <rendered deck index.html> ...')
  process.exit(2)
}

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
})

let failures = 0
let checked = 0

for (const file of files) {
  const path = resolve(file)
  if (!existsSync(path)) {
    console.error(`::error::${file} does not exist`)
    failures++
    continue
  }
  const deck = basename(dirname(path))
  const page = await browser.newPage()
  await page.setViewport({ width: 1280, height: 720 })
  await page.goto(pathToFileURL(path).href, { waitUntil: 'networkidle0' })
  // Web fonts change line boxes, and a deck measured before they land reports
  // overflow that is not there (and misses overflow that is).
  await page.evaluateHandle('document.fonts.ready')

  const rows = await page.evaluate((slack) => {
    const out = []
    document.querySelectorAll('section').forEach((sec, i) => {
      const cs = getComputedStyle(sec)
      const padTop = parseFloat(cs.paddingTop) || 0
      const padBottom = parseFloat(cs.paddingBottom) || 0
      // The box the author's content is supposed to live in.
      const limit = sec.offsetHeight - padBottom
      let lowest = padTop
      let culprit = ''
      const walk = (el) => {
        for (const c of el.children) {
          const s = getComputedStyle(c)
          const out_of_flow = s.position === 'absolute' || s.position === 'fixed'
          if (s.display === 'none' || s.visibility === 'hidden' || out_of_flow) {
            continue // header, footer, page number, and anything deliberately placed
          }
          const bottom = c.offsetTop + c.offsetHeight
          if (bottom > lowest) {
            lowest = bottom
            const tag = c.tagName.toLowerCase()
            const cls = typeof c.className === 'string' && c.className ? '.' + c.className.split(' ')[0] : ''
            const text = (c.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60)
            const img = c.querySelector && c.querySelector('img')
            culprit = `<${tag}${cls}>` + (img ? ` [img ${img.getAttribute('src')}]` : '') + (text ? ` "${text}"` : '')
          }
          walk(c)
        }
      }
      walk(sec)
      const over = Math.round(lowest - limit)
      if (over > slack) {
        out.push({
          n: i + 1,
          over,
          culprit,
          heading: (sec.querySelector('h1, h2')?.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 70),
        })
      }
    })
    return out
  }, SLACK)

  await page.close()
  checked++

  for (const r of rows) {
    failures++
    console.error(
      `::error::${deck} slide ${r.n} ("${r.heading}") overflows the bottom of the slide by ${r.over}px.\n` +
      `         lowest element: ${r.culprit}\n` +
      `         fix: shrink the figure's w: value, cut a line, or split the slide.`
    )
  }
}

await browser.close()

if (failures) {
  console.error(`\n${failures} slide(s) overflow across ${checked} deck(s).`)
  process.exit(1)
}
console.log(`OK: no slide overflows in ${checked} deck(s)`)
