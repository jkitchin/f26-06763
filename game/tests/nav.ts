/** Resume-after-reload and review-only back navigation, in a real browser. */
import { createServer } from 'node:http'
import { requireChrome } from './chrome.ts'
import { existsSync, readFileSync } from 'node:fs'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import puppeteer from 'puppeteer-core'

const DIST = fileURLToPath(new URL('../dist/', import.meta.url))
const BASE = '/f26-06763/game/'
const T: Record<string, string> = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }
const server = createServer((req, res) => {
  const p = (req.url ?? '/').split('?')[0]!
  if (!p.startsWith(BASE)) { res.writeHead(404).end(); return }
  const f = join(DIST, p.slice(BASE.length) || 'index.html')
  if (!existsSync(f)) { res.writeHead(404).end(); return }
  res.writeHead(200, { 'content-type': T[extname(f)] ?? 'application/octet-stream' })
  res.end(readFileSync(f))
})
await new Promise<void>((r) => server.listen(8736, r))

let fails = 0
const check = (ok: boolean, label: string, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? `  ${detail}` : ''}`)
  if (!ok) fails++
}

const b = await puppeteer.launch({
  executablePath: requireChrome(),
  headless: true, args: ['--no-sandbox'],
})
const page = await b.newPage()
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))
const btn = () => page.$eval('button.btn-primary', (e) => e.textContent ?? '')
const counter = () => page.$eval('header span.font-mono', (e) => e.textContent ?? '')

async function answerOne() {
  if (!(await page.$$('div.grid button')).length) {           // free-response
    await page.click('button.btn-primary'); await wait(80)
    await page.click('button.btn-primary'); await wait(120)
    return
  }
  // Wrong answers no longer stop on a screen: the grid stays live and ruled-out
  // options go disabled, so an attempt is "click a live option, Check".
  for (let attempt = 0; attempt < 8; attempt++) {
    const fresh = await page.$$('div.grid button')
    let clicked = false
    for (const o of fresh) {
      if (!(await page.evaluate((e) => (e as HTMLButtonElement).disabled, o))) {
        await o.click(); clicked = true; break
      }
    }
    if (!clicked) return
    await page.click('button.btn-primary'); await wait(100)   // Check
    const label = await btn()
    if (label.includes('Continue') || label.includes('Finish')) {
      await page.click('button.btn-primary'); await wait(150)
      return
    }
  }
}

console.log('nav:')
await page.goto(`http://localhost:8736${BASE}`, { waitUntil: 'networkidle0' })
await page.waitForSelector('#andrew')
await page.type('#andrew', 'jkitchin'); await page.type('#name', 'John Kitchin')
await page.click('button.btn-primary'); await wait(300)
await page.click('button.btn-primary'); await wait(400)        // start first module

for (let i = 0; i < 3; i++) {
  const t = await btn()
  if (t.includes('Lock it in')) { await page.type('textarea', 'guess'); await page.click('button.btn-primary'); await wait(120) }
  await answerOne()
}
const afterThree = await counter()
check(afterThree.startsWith('4/'), 'three items answered', afterThree)

// --- resume ---------------------------------------------------------------
await page.reload({ waitUntil: 'networkidle0' }); await wait(500)
await page.click('button.btn-primary'); await wait(500)        // Practise again / Start
const resumed = await counter()
check(resumed === afterThree, 'reload resumes where it left off', `${afterThree} -> ${resumed}`)

// --- review-only back -----------------------------------------------------
await page.click('header button[aria-label="Previous question"]'); await wait(250)
const banner = await page.$$eval('p', (ps) => ps.map((p) => p.textContent ?? '').join(' '))
check(banner.includes('cannot be changed'), 'back shows the review banner')

const disabled = await page.$$eval('div.grid button', (bs) =>
  bs.every((x) => (x as HTMLButtonElement).disabled))
check(disabled, 'a reviewed item is read-only')

const backBtn = await btn()
check(backBtn.startsWith('Back to question'), 'offers a way back to the current item', backBtn)

const evidence = await page.$$eval('aside', (a) => a.map((x) => x.textContent ?? '').join(' '))
check(evidence.length > 80, 'the evidence is shown on review', `${evidence.length} chars`)

await page.click('button.btn-primary'); await wait(250)
check((await counter()) === resumed, 'returns to the current item', await counter())

// --- a wrong answer does not park you on a one-button screen ---------------
await page.click('button.btn-primary'); await wait(250)      // back to current
// Find a question with options and deliberately answer it wrong.
for (let guard = 0; guard < 8; guard++) {
  const label = await btn()
  if (label.includes('Lock it in')) { await page.type('textarea', 'g'); await page.click('button.btn-primary'); await wait(150) }
  if ((await page.$$('div.grid button')).length) break
  await answerOne()
}
const before = await counter()
const opts = await page.$$('div.grid button')
// Click each option until one is wrong, i.e. the item does not advance.
for (let k = 0; k < opts.length; k++) {
  const fresh = await page.$$('div.grid button')
  const enabled: number[] = []
  for (let j = 0; j < fresh.length; j++) {
    if (!(await page.evaluate((e) => (e as HTMLButtonElement).disabled, fresh[j]!))) enabled.push(j)
  }
  await fresh[enabled[0]!]?.click()
  await page.click('button.btn-primary'); await wait(200)     // Check
  if ((await btn()).includes('Continue') || (await btn()).includes('Finish')) break
  // Wrong: this is the state the report was about.
  const labels = await page.$$eval('footer button', (bs) => bs.map((x) => x.textContent ?? ''))
  check(!labels.some((l) => l.includes('Try again')), 'no "Try again" button after a wrong answer', labels.join(' | '))
  check(labels.some((l) => l.includes('Show me')), '"Show me" is on screen when it is offered', labels.join(' | '))
  const stillThere = await page.$$eval('div.grid button', (bs) =>
    bs.filter((x) => !(x as HTMLButtonElement).disabled).length)
  check(stillThere > 0, 'other options stay clickable, so a retry is one click', `${stillThere} live`)
  const ruledOut = await page.$$eval('div.grid button', (bs) =>
    bs.filter((x) => (x as HTMLButtonElement).disabled).length)
  check(ruledOut > 0, 'the wrong option is ruled out', `${ruledOut} disabled`)
  check((await counter()) === before, 'still on the same question', await counter())
  break
}

await b.close(); server.close()
console.log(fails ? `\n${fails} failed` : '\nall checks passed')
process.exit(fails ? 1 : 0)
