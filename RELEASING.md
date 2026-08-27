# Releasing the course, one lecture at a time

The whole course is written and lives on `main` from the start, but the public
site only serves what has been **released**. Releasing is done one lecture at a
time, each through its own small pull request, so every release gets a review
before it goes public and a bad one can be reverted without taking its neighbour
with it.

Nothing about the plan is hidden: the syllabus, the schedule, and the course map
(with future lectures drawn as shuttered rooms) are visible from day one. Only the
**content** unlocks, lecture by lecture.

## What "released" means

A lecture is released when it is listed in `_toc.yml`. That single manifest drives
every public surface:

| Surface | Gated by |
|---|---|
| Lecture notes (the site) | `_toc.yml` (`only_build_toc_files: true`) |
| Slide deck (`/slides/lNN/`) | the slide-render CI step reads `_toc.yml` |
| Course map room | `tools/world.py` reads `_toc.yml` (unreleased = shuttered) |
| Quiz (practice module) | the lecture's bank `status:` (`published` shows it, `unwritten` hides it) |
| Assignment released with the lecture | `_toc.yml` (uncommented when that lecture releases) |
| Mini-project and final project | `_toc.yml` (the Projects part, released at L13 and L17) |

So releasing a lecture is a few edits: **uncomment it in `_toc.yml`**, **flip its
quiz bank to `published`**, and **uncomment any assignment it releases**. The
helper does all of them.

There is no PDF build. The course ships as online notes and slides only.

## The steps

```bash
git fetch origin && git checkout -b release-l03 origin/main

# Un-hide Lecture 3: uncomment it (and any assignment it releases) in _toc.yml,
# turn its quiz on, regenerate the map.
python tools/release_lecture.py 3
#   --check first if you want to see what it will touch without changing anything

# Fold in anything else you want to ship with it: a fix, a slide tweak, a
# clearer figure. It all rides in the same branch.

# Verify locally the way CI will:
python game/validate.py
python tools/world.py --check
python tools/pool_archive.py --check
jupyter-book build . --warningiserror   # builds only the released lectures

git add -A && git commit -m "Release Lecture 3"
git push -u origin release-l03
# open the PR, look at the preview, merge into main -> CI deploys L3
```

On merge, CI publishes Lecture 3's notes and deck, its map room opens, and its
practice module goes live. Everything not yet released stays hidden.

## What is due next

`tools/next_release.py` answers that from the schedule and from `_toc.yml`, and
names exactly one lecture:

```bash
python tools/next_release.py                 # the next one due, and the queue behind it
python tools/next_release.py --lecture 3     # what releasing L3 would cover
python tools/next_release.py --today 2026-10-19   # pretend, for testing
```

It picks the **earliest** unreleased lecture inside a one-week horizon rather than
the nearest, so a lecture that gets skipped stays at the front of the queue instead
of being left behind, and releases stay in lecture order.

`.github/workflows/release-lecture.yml` runs that at 5pm on Mondays and Wednesdays,
Pittsburgh time, and for the lecture it names it pushes a branch, runs the helper on
it, and opens a **draft** PR plus a reminder issue. Nothing is public until a human
takes the PR out of draft and merges it. Run the workflow by hand with a `lecture`
number to release one ahead of the calendar, or to catch up out of band.

Because the reminder always names the earliest unreleased lecture, and skips when
that lecture's branch or issue already exists, it will not open L4's release while
L3's is still sitting in draft.

## Notes

- **Order matters only for cross-references.** A released lecture must not link to
  an unreleased one, or the build fails. The course is written to reference only
  earlier lectures, so releasing in order (L1, L2, L3, ...) is always safe. See
  section 4 of `CLAUDE.md`: no forward references. `--lecture` is the one path that
  will hand you an out-of-order release, and it says so when it does.
- **A lecture can ship without its quiz.** If a lecture's bank has no items yet,
  `release_lecture.py` releases the notes and deck and leaves the quiz held. Re-run
  it once the quiz exists. Note what this does *not* do: the map room opens anyway.
  `released_ids()` in `tools/world.py` reads `_toc.yml` and nothing else, so the
  room follows the notes, not the bank. Only the practice module stays hidden.
  Six banks are empty today (L6, L8, L10, L12, L14, L16), so this is the normal
  case rather than an edge one.
- **Held banks read as `status: unwritten` even though they are written.** That is
  the flag the game uses to hide a module; the items are still in the file, waiting.
- **Assignments release with their lecture.** `release_lecture.py` uncomments the
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
  the helper.
- **To pull a lecture back**, reverse it by hand: re-comment its `_toc.yml` lines
  (and any assignment line the release uncommented), set its bank back to
  `status: unwritten`, and run `python tools/world.py --write`.
