/**
 * Generate game/tests/vectors.json from the TypeScript derivation.
 *
 *     cd game && npm run vectors
 *
 * The TypeScript side is the generator and the Python side is checked against
 * it, rather than both being written from the same prose spec, because a shared
 * prose spec is exactly how two implementations drift while both look correct.
 *
 * Regenerate whenever seed.ts changes, and let CI prove derive.py still
 * reproduces the result. If it does not, one of the two moved and the other did
 * not, and every PDF issued under the old behaviour is about to fail
 * verification.
 */

import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { derive, normalizeId, selectionHash, type PoolItem } from '../src/seed.ts'

/** A synthetic pool, so the vectors do not churn when a real item is edited. */
function pool(nItems: number, nOptions: number, nVariants = 1): Record<string, PoolItem> {
  const out: Record<string, PoolItem> = {}
  for (let i = 0; i < nItems; i++) {
    const id = `x-q${String(i).padStart(2, '0')}`
    const options = Array.from({ length: nOptions }, (_, j) => `opt${j}`)
    out[id] =
      nVariants > 1
        ? { variants: Array.from({ length: nVariants }, (_, v) => ({ id: `v${v}`, options })) }
        : { options }
  }
  return out
}

// Edge cases on purpose: a pool exactly the size of the draw, two-option items,
// multi-variant items, single-option items, and ids that sort differently as
// strings than as numbers.
const CASES = [
  { name: 'plain', pool: pool(30, 4), k: 12, version: 1 },
  { name: 'pool-equals-k', pool: pool(12, 4), k: 12, version: 1 },
  { name: 'two-options', pool: pool(30, 2), k: 8, version: 1 },
  { name: 'many-options', pool: pool(20, 9), k: 5, version: 1 },
  { name: 'single-option', pool: pool(15, 1), k: 6, version: 1 },
  { name: 'variants', pool: pool(25, 4, 3), k: 10, version: 1 },
  { name: 'version-2', pool: pool(30, 4), k: 12, version: 2 },
  { name: 'draw-one', pool: pool(30, 4), k: 1, version: 1 },
]

const IDS = [
  'jkitchin', 'valves', 'a1', 'zz9', 'qq', 'student01', 'x1y2z3',
  'aaaaaaaaaaaaaaaa', 'b2', 'mchen', 'osmith', 'rpatel', 'lnguyen', 'kwang',
  'JKitchin', ' jkitchin ', 'jkitchin@andrew.cmu.edu', 'jkitchin@cmu.edu',
  'agarcia', 'tokafor', 'yzhao', 'ndubois', 'pmehta', 'soconnor', 'ekim',
]

const vectors = []
for (const c of CASES) {
  for (const rawId of IDS) {
    const served = derive(rawId, 'l15', c.pool, c.version, c.k)
    vectors.push({
      case: c.name,
      raw_id: rawId,
      andrew_id: normalizeId(rawId),
      lecture: 'l15',
      pool_version: c.version,
      k: c.k,
      pool_ids: Object.keys(c.pool).sort(),
      n_options: c.pool[Object.keys(c.pool)[0]!]!.options?.length ?? 4,
      n_variants: c.pool[Object.keys(c.pool)[0]!]!.variants?.length ?? 1,
      served,
      selection_hash: selectionHash(served),
    })
  }
}

const out = fileURLToPath(new URL('./vectors.json', import.meta.url))
writeFileSync(out, JSON.stringify({ version: 1, vectors }, null, 2) + '\n')
console.log(`wrote ${vectors.length} vectors to ${out}`)
