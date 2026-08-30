// Tests for Ship It's deploy evaluation, run with
// `node --test "arcade/test/*.test.mjs"`.
//
// Same approach as bossrush.test.mjs: the REAL file is read and evaluated with a
// stub Arcade global, and the pure function it hangs there is what is tested. It
// decides what a student is told they got wrong, which is worth testing for the
// same reason the clicker's scoring is.
//
// Two properties matter more than the rest, because they are what make this a
// toolchain rather than eight independent questions:
//
//   the same storage pick scores differently under different workloads
//   a right tool can still fail when the layer it depends on is wrong

import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const src = await readFile(new URL('../games/deploy.js', import.meta.url), 'utf8')
const Arcade = { register() {} }
// mount() is the only part that touches the DOM, and nothing here calls it.
new Function('Arcade', 'window', 'document', src)(Arcade, {}, undefined)
const evaluate = Arcade.deployEvaluate

const opt = (text, ok, because) => ({ text, ok, because: because || '', cite: 'lectures/l01/notes.md' })

const STACK = {
  layers: [
    { layer: 'Environments', prevents: 'rebuilds that are merely probable', case: 'Duke.',
      options: [opt('Python + uv', true), opt('requirements.txt', false, 'the resolver is free to pick')] },
    { layer: 'Storage', prevents: 'CSV sprawl, silent truncation', case: '15,841 cases.',
      options: [opt('PostgreSQL', true), opt('DuckDB', true), opt('a spreadsheet', false, 'no opinion')] },
    { layer: 'Tracking', prevents: 'results nobody can attribute',
      options: [opt('MLflow', true), opt('a notebook', false, 'unanswerable from memory')] },
  ],
  requires: [
    { layer: 'Tracking', needs: 'Environments', because: 'MLflow will record whatever you log.',
      cite: 'lectures/l02/notes.md' },
  ],
  epilogue: { text: 'reproduce the wrong answer', cite: 'lectures/l02/notes.md' },
}

const OLTP = {
  id: 'oltp', prefers: { Storage: ['PostgreSQL'] },
  penalises: { Storage: { because: 'a relational problem', from: 'lectures/l01/notes.md' } },
}
const OLAP = {
  id: 'olap', prefers: { Storage: ['DuckDB'] },
  penalises: { Storage: { because: 'the worst possible layout', from: 'lectures/l03/notes.md' } },
}
const ANY = { id: 'any', prefers: {}, penalises: {} }

const perfect = { Environments: 'Python + uv', Storage: 'PostgreSQL', Tracking: 'MLflow' }
const layerOf = (r, name) => r.layers.find((l) => l.layer === name)

/* ---- the workload is the whole point ----------------------------------- */

test('the same storage pick is right under one workload and wrong under another', () => {
  const under = (w) => layerOf(evaluate(STACK, w, perfect), 'Storage')
  assert.equal(under(OLTP).ok, true, 'PostgreSQL suits continuous writes')
  assert.equal(under(OLAP).ok, false, 'PostgreSQL is the wrong shape for a wide scan')
  // And the report must say WHY it was wrong here, in the notes' own words.
  assert.equal(under(OLAP).why, 'the worst possible layout')
  assert.equal(under(OLAP).cite, 'lectures/l03/notes.md')
})

test('a workload that expresses no preference accepts either right tool', () => {
  for (const pick of ['PostgreSQL', 'DuckDB']) {
    const r = evaluate(STACK, ANY, { ...perfect, Storage: pick })
    assert.equal(layerOf(r, 'Storage').ok, true, pick + ' should pass')
  }
})

test('being wrong for the workload is not the same as picking an anti-pattern', () => {
  const wrongShape = layerOf(evaluate(STACK, OLAP, perfect), 'Storage')
  const antiPattern = layerOf(evaluate(STACK, OLAP, { ...perfect, Storage: 'a spreadsheet' }), 'Storage')
  assert.equal(wrongShape.ok, false)
  assert.equal(antiPattern.ok, false)
  assert.notEqual(wrongShape.why, antiPattern.why, 'each failure explains itself differently')
  assert.equal(antiPattern.why, 'no opinion')
})

/* ---- layers depend on layers ------------------------------------------- */

test('MLflow does not buy attributable results without a locked environment', () => {
  const r = evaluate(STACK, OLTP, { ...perfect, Environments: 'requirements.txt' })
  // The Tracking pick itself was right, and still scores.
  assert.equal(layerOf(r, 'Tracking').ok, true)
  // But the dependency did not hold, so the failure reached production anyway.
  assert.equal(r.requires[0].held, false)
  assert.equal(r.reqsOk, 0)
  assert.equal(r.clean, false)
})

test('a dependency holds only when both ends are right', () => {
  assert.equal(evaluate(STACK, OLTP, perfect).requires[0].held, true)
  const trackingWrong = evaluate(STACK, OLTP, { ...perfect, Tracking: 'a notebook' })
  assert.equal(trackingWrong.requires[0].held, false, 'the dependent layer was wrong')
})

/* ---- scoring ------------------------------------------------------------ */

test('a clean deploy scores every layer, every dependency, and the bonus', () => {
  const r = evaluate(STACK, OLTP, perfect)
  assert.equal(r.clean, true)
  assert.equal(r.layersOk, 3)
  assert.equal(r.reqsOk, 1)
  assert.equal(r.points, 25 * 3 + 25 * 1 + 50)
})

test('the clean bonus is all or nothing', () => {
  const r = evaluate(STACK, OLTP, { ...perfect, Storage: 'a spreadsheet' })
  assert.equal(r.clean, false)
  assert.equal(r.points, 25 * 2 + 25 * 1, 'two layers and the dependency, no bonus')
})

/* ---- the sheet you did not finish --------------------------------------- */

test('an empty slot deploys as a failure rather than being skipped', () => {
  const r = evaluate(STACK, OLTP, { Environments: 'Python + uv', Tracking: 'MLflow' })
  const storage = layerOf(r, 'Storage')
  assert.equal(storage.ok, false)
  assert.equal(storage.pick, null)
  assert.match(storage.why, /Nothing was chosen/)
  assert.equal(r.layersOk, 2)
  assert.equal(r.clean, false)
})

test('deploying an entirely empty sheet scores nothing and blames nobody', () => {
  const r = evaluate(STACK, OLTP, {})
  assert.equal(r.points, 0)
  assert.equal(r.clean, false)
  assert.equal(r.requires[0].held, false)
  assert.equal(r.layers.every((l) => l.pick === null), true)
})

test('a pick that is not an option at all is treated as an empty slot', () => {
  // Belt and braces: the UI cannot produce this, a replayed transcript could.
  const r = evaluate(STACK, OLTP, { ...perfect, Storage: 'Kubernetes' })
  const storage = layerOf(r, 'Storage')
  assert.equal(storage.ok, false)
  // It keeps the pick, because the report should show what was actually
  // submitted, and says the accurate thing about it rather than "nothing".
  assert.equal(storage.pick, 'Kubernetes')
  assert.match(storage.why, /not one of the options/)
})

/* ---- the report carries what it needs to teach -------------------------- */

test('every failed layer names the failure it should have prevented', () => {
  const r = evaluate(STACK, OLAP, { Environments: 'requirements.txt', Storage: 'PostgreSQL' })
  r.layers.filter((l) => !l.ok).forEach((l) => {
    assert.ok(l.prevents, l.layer + ' must name its failure')
    assert.ok(l.why, l.layer + ' must say why this pick did not prevent it')
  })
})

test('a stack with no requires still evaluates and can be clean', () => {
  const bare = { layers: STACK.layers, requires: [] }
  const r = evaluate(bare, OLTP, perfect)
  assert.equal(r.clean, true)
  assert.equal(r.points, 75 + 50)
})
