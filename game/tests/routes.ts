/** Per-module URLs: run with `npm run routes`. */
import { createServer } from 'node:http'
import { existsSync, readFileSync } from 'node:fs'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import puppeteer from 'puppeteer-core'

const DIST = fileURLToPath(new URL('../dist/', import.meta.url))
const BASE = '/f26-06763/game/'
const T: Record<string, string> = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }
const server = createServer((q, r) => {
  const p = (q.url ?? '/').split('?')[0]!
  if (!p.startsWith(BASE)) { r.writeHead(404).end(); return }
  const f = join(DIST, p.slice(BASE.length) || 'index.html')
  if (!existsSync(f)) { r.writeHead(404).end(); return }
  r.writeHead(200, { 'content-type': T[extname(f)] ?? 'application/octet-stream' }); r.end(readFileSync(f))
})
await new Promise<void>((r) => server.listen(8739, r))

let fails = 0
const check = (ok: boolean, label: string, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? `  ${detail}` : ''}`)
  if (!ok) fails++
}
const b = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true, args: ['--no-sandbox'],
})
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))
const url = `http://localhost:8739${BASE}`
console.log('routes:')

// A deep link from a student who has never used it before.
const ctx1 = await b.createBrowserContext()
const p1 = await ctx1.newPage()
await p1.goto(`${url}#/l13`, { waitUntil: 'networkidle0' }); await wait(400)
check(!!(await p1.$('#andrew')), 'a deep link asks who you are first')
await p1.type('#andrew', 'jkitchin'); await p1.type('#name', 'John Kitchin')
await p1.click('button.btn-primary'); await wait(500)
const heading = await p1.$eval('p.font-mono', (e) => e.textContent ?? '').catch(() => '')
const hash1 = await p1.evaluate(() => window.location.hash)
check(hash1 === '#/l13', 'and then goes to the module that was linked', hash1)
check(heading.length > 0, 'the session is running', heading.trim())

// A deep link from someone already signed in.
await p1.goto(`${url}#/l21`, { waitUntil: 'networkidle0' }); await wait(500)
check(!(await p1.$('#andrew')), 'a signed-in student goes straight in')
check((await p1.evaluate(() => window.location.hash)) === '#/l21', 'on the linked module')

// The address bar tracks navigation, so a copied URL is meaningful.
await p1.click('header button[aria-label="Leave this session"]'); await wait(400)
check((await p1.evaluate(() => window.location.hash)) === '#/', 'leaving returns to #/')
const cards = await p1.$$('li button.btn-primary')
await cards[0]?.click(); await wait(500)
const started = await p1.evaluate(() => window.location.hash)
check(/^#\/l\d\d$/.test(started), 'starting a module from the list sets its URL', started)

// Back button.
await p1.goBack({ waitUntil: 'domcontentloaded' }); await wait(400)
check((await p1.evaluate(() => window.location.hash)) === '#/', 'the browser back button works')

// A stale link to a lecture with no bank.
await p1.goto(`${url}#/l99`, { waitUntil: 'networkidle0' }); await wait(400)
check((await p1.evaluate(() => window.location.hash)) === '#/', 'a stale link falls back to the list')
check((await p1.$$('li')).length > 0, 'and the list renders')

await b.close(); server.close()
console.log(fails ? `\n${fails} failed` : '\nall checks passed')
process.exit(fails ? 1 : 0)
