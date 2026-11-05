# Archive

Material taken off the schedule but kept so it can come back. Nothing here is published:
`_config.yml` lists `archive` in `exclude_patterns`, nothing here is in `_toc.yml`, and CI
renders decks only from `lectures/*/slides.md`.

This is different from `course/optional/`, which is published reading. A lecture that leaves
the schedule but should still reach students is rewritten into `course/optional/` (the old
L23 became `course/optional/mlops.md`). A lecture that is simply not being taught this year
comes here intact.

## `l21-evaluation/`

**Evaluating ML and LLM/agent systems; observability.** Planned as L21 (Wednesday
2026-11-11) and removed on 2026-11-04, when the deployment session moved from L22 to L21 as an
optional lecture and L22 became the course wrap-up. It was never released: the notes were
commented out of `_toc.yml` and the practice bank was `status: unwritten`.

| File here | Where it came from |
|---|---|
| `notes.md`, `slides.md`, `l21-eval.ipynb` | `lectures/l21/` |
| `practice-bank.yml` | `game/content/l21.yml` (ten items, pool version 2) |
| `objectives.yml` | the `l21-o1` to `l21-o3` entries of `game/content/objectives.yml` |
| `sections.lock` | the `l21-q*` entries of `game/content/sections.lock` |
| `map-edges.yml` | the four authored corridors out of L21 in `game/content/map-edges.yml` |
| `module-spec.md` | the L21 block of `course/modules/wk12.md`, plus its evaluation-only objectives, assignment and pitfalls |
| `a11.md` | `course/assignments/a11.md` (eval harness plus deployed API), dropped with the lecture |

`game/content/pools/l21.json` stays where it is. It archives the pool versions that were
served, and no student was ever served one, so it is inert; keep it so a future L21 bank
starts at pool version 3 and cannot collide with these.

### Restoring it

The lecture number it returns under decides most of the work. In order:

1. Move `notes.md`, `slides.md` and the notebook to `lectures/lNN/`. The notes say "Lecture 21"
   and "Week 12" in the opening block and cite L3, L4, L13 and L19 in prose; check every
   number against the schedule of the year you restore it in.
2. Paste the objectives back into `game/content/objectives.yml`, renumbered to `lNN-o*`, and
   move `practice-bank.yml` to `game/content/lNN.yml` with its ids, `lecture:` field and
   `source.file` paths changed. Bump `pool_version` past every version in
   `game/content/pools/lNN.json`, then run `python tools/pool_archive.py --write`.
3. Paste the edges back into `game/content/map-edges.yml`, retargeted, and update the
   authored-corridor count in `game/tests/map.ts`, which is hardcoded on purpose. Then
   `python tools/graph.py --write` and `python tools/world.py --write`.
4. Run `python game/validate.py`, re-read the cited sections, and record their hashes.
5. Put the module block back in `course/modules/`, add the schedule row and the `_toc.yml`
   entry, and decide whether A11 returns; if it does, `tools/release_lecture.py` needs it in
   `LECTURE_ASSIGNMENTS` again. Its deployment half now overlaps the deployment lecture.
