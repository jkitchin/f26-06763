#!/usr/bin/env python3
"""Turn the quiz banks into the round files the arcade plays.

Run from the repository root:

    python tools/arcade_rounds.py                # every published bank
    python tools/arcade_rounds.py l03            # just one
    python tools/arcade_rounds.py --all --check  # CI: rebuild and diff, never write

The arcade does not have content of its own, and that is the point. A minigame
is a *renderer* over `game/content/lNN.yml`, so the bank stays the one place a
claim about this course is written down, `game/validate.py` stays the one thing
that checks a claim against the notes, and a new minigame costs no new authoring
and cannot quietly introduce an unsourced assertion.

What a round file is, and what it deliberately is not:

    it is      the already-published option text, rearranged into
               (context, one true claim, three false ones) per item
    it is not  a new bank, a new schema, or anywhere an author edits

So nothing here invents, rewords, shortens or reorders anything. It copies. An
author who wants a better claim edits the YAML and reruns this, which is the
same loop `game/content/pools/` already uses.

`answer` is the true claim and every other option is a false one, which is what
the MCQ format already asserts -- a distractor that were merely "less good"
would be a broken item and validate.py would have said so.

Published banks only, by default. The arcade follows the same release
discipline as everything else: a lecture that has not been released cannot be
played, so an unfinished bank cannot leak out through a slide. --all is for
working on a bank before it ships and should not be committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BANKS = ROOT / "game" / "content"
OUT = ROOT / "arcade" / "rounds"

# A claim longer than this cannot be read while it moves, and a game that shows
# it is asking the player to guess rather than to judge. Better to leave the
# item out of the arcade and say which, so the author can shorten it on purpose,
# than to truncate it here and put half a sentence on a screen.
MAX_CLAIM = 180


def load_bank(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def build(bank: dict, lecture: str) -> tuple[dict, list[str]]:
    """Return (round file, warnings)."""
    warnings: list[str] = []
    items = []

    for item in bank.get("items") or []:
        iid = item.get("id", "?")
        answer = item.get("answer")
        options = item.get("options") or []

        # Not every item kind is claim-shaped. mechanism_recall asks a student
        # to write down what they remember and grades itself against a
        # checklist, so there is no true statement here to judge and nothing
        # for this game to render. Skipping it is correct rather than a gap.
        if answer is None and item.get("checklist"):
            continue
        if not answer or len(options) < 2:
            warnings.append(f"{iid}: kind {item.get('kind', '?')} has no answer and no checklist, skipped")
            continue
        if answer not in options:
            # validate.py already enforces this; a bank that fails it should
            # fail loudly here too rather than produce a round with no truth in
            # it, which would be unplayable in a way that looks like a bug.
            warnings.append(f"{iid}: answer is not one of the options, skipped")
            continue

        false = [o for o in options if o != answer]
        longest = max(len(o) for o in options)
        if longest > MAX_CLAIM:
            warnings.append(f"{iid}: an option is {longest} characters, over {MAX_CLAIM}, skipped")
            continue

        items.append(
            {
                "id": iid,
                "kind": item.get("kind", "mcq"),
                # The prompt is the context a claim is judged against, code
                # fence and all. The arcade renders it as markdown.
                "context": (item.get("prompt") or "").strip(),
                "true": answer,
                "false": false,
                # Shown after a run, not during it. A game that only says
                # "wrong" teaches nobody, which is the same reason the clicker
                # slide carries data-why.
                "why": (item.get("evidence") or "").strip(),
                "objectives": item.get("objectives") or [],
                "tags": item.get("tags") or [],
            }
        )

    return (
        {
            "lecture": lecture,
            "title": bank.get("title", ""),
            "pool_version": bank.get("pool_version"),
            "source_notes": bank.get("source_notes", ""),
            "generated_by": "tools/arcade_rounds.py",
            "items": items,
        },
        warnings,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("lecture", nargs="*", help="lNN, or nothing for all of them")
    ap.add_argument("--all", action="store_true", help="include banks that are not published yet")
    ap.add_argument("--check", action="store_true", help="do not write; exit 1 if anything is stale")
    args = ap.parse_args(argv)

    wanted = set(args.lecture)
    paths = sorted(BANKS.glob("l*.yml"))
    if not paths:
        print(f"no banks under {BANKS}", file=sys.stderr)
        return 1

    stale: list[str] = []
    written = 0

    for path in paths:
        lecture = path.stem
        if wanted and lecture not in wanted:
            continue

        bank = load_bank(path)
        status = bank.get("status", "unwritten")
        if status != "published" and not args.all:
            continue

        rounds, warnings = build(bank, lecture)
        for w in warnings:
            print(f"{lecture}: {w}", file=sys.stderr)

        if not rounds["items"]:
            print(f"{lecture}: no playable items, nothing written", file=sys.stderr)
            continue

        text = json.dumps(rounds, indent=2, ensure_ascii=False) + "\n"
        dest = OUT / f"{lecture}.json"

        if args.check:
            current = dest.read_text() if dest.exists() else ""
            if current != text:
                stale.append(lecture)
            continue

        OUT.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        written += 1
        print(f"{lecture}: {len(rounds['items'])} items -> {dest.relative_to(ROOT)}")

    if args.check:
        if stale:
            print(
                "stale round files: " + ", ".join(stale) + "\nrun: python tools/arcade_rounds.py",
                file=sys.stderr,
            )
            return 1
        print("round files are up to date")
        return 0

    if not written:
        print("nothing to do (published banks only; --all to include the rest)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
