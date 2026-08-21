# Releasing the course, one week at a time

The whole course is written and lives on `main` from the start, but the public
site only serves what has been **released**. Releasing is done one lecture (or
one week's lectures) at a time, each through its own small pull request, so every
release gets a review before it goes public.

Nothing about the plan is hidden: the syllabus, the schedule, and the course map
(with future lectures drawn as shuttered rooms) are visible from day one. Only the
**content** unlocks week by week.

## What "released" means

A lecture is released when it is listed in `_toc.yml`. That single manifest drives
every public surface:

| Surface | Gated by |
|---|---|
| Lecture notes (the site) | `_toc.yml` (`only_build_toc_files: true`) |
| Slide deck (`/slides/lNN/`) | the slide-render CI step reads `_toc.yml` |
| Course map room | `tools/world.py` reads `_toc.yml` (unreleased = shuttered) |
| Quiz (practice module) | the lecture's bank `status:` (`published` shows it, `unwritten` hides it) |
| Weekly assignment | `_toc.yml` (uncommented the week its lecture releases it) |
| Mini-project and final project | `_toc.yml` (the Projects part, released at L13 and L17) |

So releasing a lecture is a few edits: **uncomment it in `_toc.yml`**, **flip its
quiz bank to `published`**, and **uncomment any assignment released that week**.
The helper does all of them.

There is no PDF build. The course ships as online notes and slides only.

## The weekly steps

```bash
git fetch origin && git checkout -b release-week-3 origin/main

# Un-hide Lecture 3: uncomment it (and any assignment it releases) in _toc.yml,
# turn its quiz on, regenerate the map.
python tools/release_week.py 3
#   --check first if you want to see what it will touch without changing anything

# Fold in anything else you want to ship this week: a fix, a slide tweak, a
# clearer figure. It all rides in the same branch.

# Verify locally the way CI will:
python game/validate.py
python tools/world.py --check
python tools/pool_archive.py --check
jupyter-book build . --warningiserror   # builds only the released lectures

git add -A && git commit -m "Release Lecture 3"
git push -u origin release-week-3
# open the PR, look at the preview, merge into main -> CI deploys week 3
```

On merge, CI publishes Lecture 3's notes and deck, its map room opens, and its
practice module goes live. Everything not yet released stays hidden.

## Notes

- **Order matters only for cross-references.** A released lecture must not link to
  an unreleased one, or the build fails. The course is written to reference only
  earlier lectures, so releasing in order (L1, L2, L3, ...) is always safe. See
  section 4 of `CLAUDE.md`: no forward references.
- **A lecture can ship without its quiz.** If a lecture's bank has no items yet,
  `release_week.py` releases the notes and deck and leaves the quiz held, so the
  room stays shuttered until the quiz is written. Re-run it once the quiz exists.
- **Held banks read as `status: unwritten` even though they are written.** That is
  the flag the game uses to hide a module; the items are still in the file, waiting.
- **Assignments release with their lecture.** `release_week.py` uncomments the
  assignment listed for that lecture in its `LECTURE_ASSIGNMENTS` map, taken from
  the schedule's "Assignment N released" markers (A1 with L1, A2 with L3, and so
  on). A lecture that releases no assignment simply skips this.
- **Projects release the same way.** The mini-project (A7) is uncommented at L13
  and the final project at L17, from `LECTURE_PROJECTS`. Their whole Projects
  part stays commented out until the first one releases, because a part with no
  chapters will not build, so releasing the mini-project also restores the part
  header.
- **Optional material is held separately.** The Optional part of `_toc.yml` is
  commented out pending review; release it by hand when ready rather than through
  the weekly helper.
- **To pull a lecture back**, reverse it by hand: re-comment its `_toc.yml` lines
  (and any assignment line the release uncommented), set its bank back to
  `status: unwritten`, and run `python tools/world.py --write`.
