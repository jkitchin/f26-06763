#!/usr/bin/env python3
"""Archive each item pool as it was served, so an old PDF stays verifiable.

    python tools/pool_archive.py            # show what is archived and what drifted
    python tools/pool_archive.py --write    # archive the current version of each bank
    python tools/pool_archive.py --check    # fail if a bank drifted without a bump

THE PROBLEM THIS SOLVES, which is the server-side twin of a bug already fixed
on the client.

`tools/verify_evidence.py` does not trust the item list printed in a student's
PDF. It re-derives that list from their Andrew ID and compares, which is the
one check in the whole scheme that needs no secret: a classmate's PDF re-issued
under a different id derives to different items, and that is caught even if the
MAC key has leaked. It is the strongest layer precisely because it is
independent of the payload.

It re-derives from `game/content/lNN.yml` *as it stands at verification time*.
Item selection is a function of the pool, so adding one item to a bank changes
which items every student is served. A PDF issued in week 3 and verified in
week 9 is then compared against a derivation that never existed when it was
issued, and an honest student's evidence comes back `drv: MISM`, reported as
"item set is not the one jkitchin derives to". The failure accuses the student,
arrives in a batch at grading time, and gets worse the more the course is
maintained during the semester, which is to say it is worst in exactly the
semester anyone is actually teaching from these files.

`game/content/l15.yml` already carries the note that would trigger it: a plan
to grow the pool past twenty items and put `serve` back to twelve.

WHAT IS ARCHIVED. Only the surface the verifier consumes: per item, the options
in their original pool order, the correct answer, and the variants if there are
any. Not the prompts, not the evidence, not the provenance. That keeps the file
small and keeps its diff readable, which matters because the diff is the only
thing standing between a legitimate bump and a quiet rewrite of history.

The answer key is part of that surface, and archiving it leaks nothing new: the
banks are bundled into the app the students download, and the syllabus says so.
The archive is deliberately NOT bundled. `game/src/content/load.ts` globs
`../../content/l*.yml`, so a `.json` file under `game/content/pools/` is not
picked up, and students do not download a copy of every retired version of
every bank.

DETERMINISM. A snapshot is a pure function of the bank, with no timestamp and
no author, so `--check` can regenerate and compare rather than trust. That is
the same standard `npm run vectors` and `tools/graph.py --check` hold: a
committed artifact nobody rebuilds is an artifact that keeps passing after the
thing it describes has moved.

APPEND-ONLY. `--write` never rewrites a version that is already archived, and
`--check` will not tell you if somebody hand-edits one. It cannot: with the
bank at v3, v1's snapshot is unreachable from anything in the working tree. The
protection there is that rewriting an archived version invalidates every PDF
issued under it, and that the diff says exactly that. Bump the version instead;
that is what the field is for.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CONTENT = REPO / "game" / "content"
POOLS = CONTENT / "pools"


def surface(bank: dict) -> dict:
    """The part of a bank that verification depends on, and nothing else.

    Two consumers, and this has to satisfy both. `derive()` needs the item ids
    (it sorts them), the variant list per item, and how many options each has,
    because the option order it produces is a permutation of that many indices.
    `check_answers()` needs the options themselves and the correct answer,
    because a recorded choice is an index into the *original* pool order, which
    is the property that keeps a shuffled answer checkable at all.
    """
    items: dict[str, dict] = {}
    for it in bank.get("items", []):
        rec: dict = {}
        if it.get("options"):
            rec["options"] = list(it["options"])
        if it.get("answer") is not None:
            rec["answer"] = it["answer"]
        if it.get("variants"):
            rec["variants"] = [
                {k: (list(v[k]) if k == "options" else v[k])
                 for k in ("id", "options") if k in v}
                for v in it["variants"]
            ]
        items[it["id"]] = rec
    return {"serve": bank.get("serve"), "items": items}


def archive_path(lecture: str) -> Path:
    return POOLS / f"{lecture}.json"


def load_archive(lecture: str) -> dict:
    p = archive_path(lecture)
    if not p.is_file():
        return {"lecture": lecture, "versions": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def dump_archive(arch: dict) -> str:
    """One canonical spelling, so a rewrite is always a real change."""
    return json.dumps(arch, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def banks() -> list[tuple[str, dict]]:
    out = []
    for p in sorted(CONTENT.glob("l*.yml")):
        bank = yaml.safe_load(p.read_text(encoding="utf-8"))
        out.append((bank["lecture"], bank))
    return out


def status() -> tuple[list[str], list[str]]:
    """(problems, lines). A problem is a bank whose archive is not usable."""
    problems, lines = [], []
    for lecture, bank in banks():
        v = str(bank.get("pool_version", 1))
        arch = load_archive(lecture)
        have = arch.get("versions", {})
        want = surface(bank)

        if v not in have:
            problems.append(
                f"{lecture}: pool_version {v} is not archived. "
                f"Run: python tools/pool_archive.py --write"
            )
            lines.append(f"  {lecture}  v{v}  NOT ARCHIVED  (archived: {sorted(have) or 'none'})")
        elif have[v] != want:
            n_now = len(want["items"])
            n_arch = len(have[v]["items"])
            added = sorted(set(want["items"]) - set(have[v]["items"]))[:3]
            gone = sorted(set(have[v]["items"]) - set(want["items"]))[:3]
            detail = []
            if added:
                detail.append(f"added {', '.join(added)}")
            if gone:
                detail.append(f"removed {', '.join(gone)}")
            if have[v].get("serve") != want.get("serve"):
                detail.append(f"serve {have[v].get('serve')} -> {want.get('serve')}")
            if not detail:
                detail.append("an option or answer changed")
            problems.append(
                f"{lecture}: the pool changed but pool_version stayed at {v} "
                f"({'; '.join(detail)}). Every PDF already issued under v{v} would "
                f"fail verification. Bump pool_version in game/content/{lecture}.yml, "
                f"then run: python tools/pool_archive.py --write"
            )
            lines.append(f"  {lecture}  v{v}  DRIFTED  ({n_arch} -> {n_now} items)")
        else:
            lines.append(f"  {lecture}  v{v}  ok  ({len(want['items'])} items, "
                         f"archived: {', '.join('v' + k for k in sorted(have))})")
    return problems, lines


def write() -> int:
    POOLS.mkdir(parents=True, exist_ok=True)
    added, kept, refused = 0, 0, []
    for lecture, bank in banks():
        v = str(bank.get("pool_version", 1))
        arch = load_archive(lecture)
        arch.setdefault("lecture", lecture)
        versions = arch.setdefault("versions", {})
        want = surface(bank)

        if v in versions:
            if versions[v] == want:
                kept += 1
                continue
            # Refuse rather than overwrite. Overwriting is the one operation
            # that silently invalidates PDFs already in students' hands, so it
            # is not something a --write should ever do for you.
            refused.append(
                f"{lecture}: refusing to overwrite the archived v{v}, which is "
                f"what every PDF issued under it was verified against. Bump "
                f"pool_version in game/content/{lecture}.yml instead."
            )
            continue

        versions[v] = want
        archive_path(lecture).write_text(dump_archive(arch), encoding="utf-8")
        added += 1
        print(f"  archived {lecture} v{v} ({len(want['items'])} items)")

    if refused:
        for r in refused:
            print(f"::error::{r}", file=sys.stderr)
        return 1
    print(f"{added} archived, {kept} already current")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.write:
        return write()

    problems, lines = status()
    if args.check:
        for p in problems:
            print(f"::error::{p}", file=sys.stderr)
        if problems:
            return 1
        print(f"OK: every bank's current pool_version is archived "
              f"({len(lines)} lectures)")
        return 0

    print("pool archive:")
    for line in lines:
        print(line)
    for p in problems:
        print(f"\n  ! {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
