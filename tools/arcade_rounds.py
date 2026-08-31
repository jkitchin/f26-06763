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

Three shapes come out of a bank, and a game uses whichever it understands:

    claims    the already-published option text, rearranged into
              (context, one true claim, three false ones)
    sequence  an ordered process, for a game that tests ORDER, which the
              multiple-choice format structurally cannot ask about
    terms     short words, for a game that needs something that fits on a
              pellet -- no bank option is under 49 characters, and that is
              structural rather than accidental, because validate.py's
              check_choices errors when one option contains another and so
              pushes every author toward long differentiated prose
    stack     a toolchain to assemble: layers, the options for each, and the
              failure each layer's right answer prevents

`sequence` and `terms` are OPTIONAL KEYS ON EXISTING ITEMS, never new items.
That distinction is load-bearing. tools/pool_archive.py snapshots a surface of
`serve` plus each item's options, answer and variants; a new item changes that
surface, which changes which items every student is served and can make an
honestly-earned evidence PDF verify as `drv: MISM` months later. An extra key
on an item that already exists touches none of it. validate.py has no key
whitelist -- every field is read with .get(), and `difficulty` is already
carried by every item and never read -- so both keys pass validation untouched.

THE GROUNDING RULE, which is what stops these keys from becoming a second,
unchecked bank:

    every `sequence` step and every `terms.correct` MUST appear in the item's
    source.file, and no `terms.wrong` may appear in it

The negative half is the one that earns its keep: a distractor that is actually
in the notes is a broken distractor, and a game built on one teaches the
opposite of what it meant to. Both halves reuse game/normalize.py, the same
normalization validate.py uses for source.quote, so a step may span the notes'
95-column hard wrap and still match.

`stack` INVERTS that rule, deliberately, and the reason is worth stating because
the two rules look contradictory side by side:

    every option must appear in the notes -- the WRONG ones especially

A wrong term in a maze is a word the course does not use. A wrong tool in a
toolchain is the opposite: it is `requirements.txt`, a spreadsheet, "works on my
machine" -- things the notes name precisely in order to argue against them.
Requiring their absence would reject exactly the distractors worth having.

`stack` also spans lectures, because the argument about any one layer is rarely
in the lecture that tabulates it: the table is in l01 and the case against
`requirements.txt` is in l02. So every quote may carry `from:` naming the notes
file it came out of, defaulting to the item's own source.file, and that file must
belong to a PUBLISHED lecture -- otherwise a slide could quote a lecture the
students have not been given.

Scenario prose -- the brief, and the workload descriptions -- is framing rather
than a claim about the course, and is not grounded. Every engineering assertion
is.

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
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BANKS = ROOT / "game" / "content"
OUT = ROOT / "arcade" / "rounds"

sys.path.insert(0, str(ROOT / "game"))
from normalize import contains_text, norm_text  # noqa: E402

# A claim longer than this cannot be read while it moves, and a game that shows
# it is asking the player to guess rather than to judge. Better to leave the
# item out of the arcade and say which, so the author can shorten it on purpose,
# than to truncate it here and put half a sentence on a screen.
MAX_CLAIM = 180

# A pellet has to carry its word at a legible size on a projector.
MAX_TERM = 24

# A deploy report is read after the clock has stopped, so a quote there can be a
# whole sentence. It still has to fit on a slide beside seven others.
MAX_BECAUSE = 260

_notes_cache: dict[str, str] = {}

# Filled in main() from the banks, so a `from:` cannot cite a lecture that has
# not been released. A slide quoting notes the students cannot read is worse
# than no quote at all.
PUBLISHED_NOTES: set[str] = set()

NOTES_RE = re.compile(r"^lectures/l\d\d/notes\.md$")


def notes_text(rel: str) -> str:
    """The normalized text of a source file, read once."""
    if rel not in _notes_cache:
        path = ROOT / rel
        _notes_cache[rel] = norm_text(path.read_text(encoding="utf-8")) if path.is_file() else ""
    return _notes_cache[rel]


def notes_raw(rel: str) -> str:
    """The file as written. contains_text normalizes both sides itself."""
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def mentions(haystack_norm: str, term: str) -> bool:
    """Does the source use this term, as a word rather than as a fragment?

    Word boundaries matter here in a way they do not for a quoted sentence. A
    distractor like "ray" is not present in the notes just because "array" is,
    and rejecting it on that would push an author toward worse distractors for
    no reason.
    """
    t = norm_text(term)
    if not t:
        return False
    return re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", haystack_norm) is not None


def build_claims(item: dict, warnings: list[str]) -> dict | None:
    iid = item.get("id", "?")
    answer = item.get("answer")
    options = item.get("options") or []

    if answer is None or len(options) < 2:
        return None
    if answer not in options:
        # validate.py already enforces this; a bank that fails it should fail
        # loudly here too rather than produce a round with no truth in it,
        # which would be unplayable in a way that looks like a bug.
        warnings.append(f"{iid}: answer is not one of the options, claims skipped")
        return None

    longest = max(len(o) for o in options)
    if longest > MAX_CLAIM:
        warnings.append(f"{iid}: an option is {longest} characters, over {MAX_CLAIM}, claims skipped")
        return None

    return {"true": answer, "false": [o for o in options if o != answer]}


def build_sequence(item: dict, source: str, errors: list[str]) -> dict | None:
    seq = item.get("sequence")
    if not seq:
        return None
    iid = item.get("id", "?")
    steps = seq.get("steps") or []
    if len(steps) < 3:
        errors.append(f"{iid}: a sequence needs at least three steps")
        return None

    body = notes_text(source)
    for step in steps:
        if not contains_text(body, step):
            errors.append(f"{iid}: sequence step {step!r} does not appear in {source}")

    return {
        "prompt": (seq.get("prompt") or "").strip(),
        "steps": [str(s) for s in steps],
        "why": (seq.get("why") or "").strip(),
    }


def build_terms(item: dict, source: str, errors: list[str]) -> dict | None:
    terms = item.get("terms")
    if not terms:
        return None
    iid = item.get("id", "?")
    correct = terms.get("correct") or []
    wrong = terms.get("wrong") or []
    if len(correct) < 3 or len(wrong) < 3:
        errors.append(f"{iid}: terms needs at least three correct and three wrong")
        return None

    body = notes_text(source)
    for t in correct:
        if len(t) > MAX_TERM:
            errors.append(f"{iid}: term {t!r} is over {MAX_TERM} characters")
        if not mentions(body, t):
            errors.append(f"{iid}: correct term {t!r} does not appear in {source}")
    for t in wrong:
        if len(t) > MAX_TERM:
            errors.append(f"{iid}: term {t!r} is over {MAX_TERM} characters")
        if mentions(body, t):
            # The whole point of the negative check. A distractor the notes
            # actually use is not a distractor, and a maze built on one
            # punishes the student who read them.
            errors.append(f"{iid}: wrong term {t!r} DOES appear in {source}, so it is not wrong")

    return {
        "prompt": (terms.get("prompt") or "").strip(),
        "correct": [str(t) for t in correct],
        "wrong": [str(t) for t in wrong],
    }


def build_stack(item: dict, source: str, errors: list[str]) -> dict | None:
    st = item.get("stack")
    if not st:
        return None
    iid = item.get("id", "?")

    def grounded(text: str, frm: str | None, what: str) -> str:
        """Check a quote against the file it says it came from, and return that file."""
        f = frm or source
        if not NOTES_RE.match(f):
            errors.append(f"{iid}: {what} cites {f!r}, which is not a lecture's notes")
        elif f not in PUBLISHED_NOTES:
            errors.append(f"{iid}: {what} cites {f}, whose lecture is not published")
        elif not contains_text(notes_raw(f), text):
            errors.append(f"{iid}: {what} {text!r} does not appear in {f}")
        return f

    layers = []
    for spec in st.get("layers") or []:
        name = spec.get("layer", "?")
        grounded(name, spec.get("from"), f"layer {name}")
        grounded(spec.get("prevents", ""), spec.get("from"), f"{name} prevents")

        options = []
        for opt in spec.get("options") or []:
            text = opt.get("text", "")
            grounded(text, opt.get("from"), f"{name} option")
            because = (opt.get("because") or "").strip()
            if because:
                if len(because) > MAX_BECAUSE:
                    errors.append(f"{iid}: {name} option {text!r} explains itself in "
                                  f"{len(because)} characters, over {MAX_BECAUSE}")
                grounded(because, opt.get("because_from") or opt.get("from"),
                         f"{name} option {text!r} because")
            elif not opt.get("ok"):
                errors.append(f"{iid}: {name} option {text!r} is wrong but says nothing about why")
            options.append({
                "text": text,
                "ok": bool(opt.get("ok")),
                "because": because,
                "cite": opt.get("because_from") or opt.get("from") or source,
            })

        if not any(o["ok"] for o in options):
            errors.append(f"{iid}: layer {name} has no right answer")
        layers.append({
            "layer": name,
            "prevents": spec.get("prevents", ""),
            "case": (spec.get("case") or "").strip(),
            "options": options,
        })

    if len(layers) < 3:
        errors.append(f"{iid}: a stack needs at least three layers")

    known = {l["layer"] for l in layers}

    workloads = []
    for w in st.get("workloads") or []:
        # `prefers` narrows a layer's right answers for this workload. It is how
        # the same storage pick scores differently under a streaming write load
        # and a wide analytical scan, which is the notes' own position: the
        # question is not which database is best but what access pattern you have.
        prefers = w.get("prefers") or {}
        for layer, picks in prefers.items():
            if layer not in known:
                errors.append(f"{iid}: workload {w.get('id')} prefers unknown layer {layer!r}")
                continue
            texts = {o["text"] for l in layers if l["layer"] == layer for o in l["options"]}
            for pick in picks:
                if pick not in texts:
                    errors.append(f"{iid}: workload {w.get('id')} prefers {pick!r}, "
                                  f"which is not an option under {layer}")
        for layer, spec in (w.get("penalises") or {}).items():
            grounded(spec.get("because", ""), spec.get("from"), f"workload {w.get('id')} {layer}")
        workloads.append({
            "id": w.get("id", ""),
            "text": (w.get("text") or "").strip(),
            "prefers": prefers,
            "penalises": w.get("penalises") or {},
        })

    requires = []
    for r in st.get("requires") or []:
        for side in ("layer", "needs"):
            if r.get(side) not in known:
                errors.append(f"{iid}: requires names unknown layer {r.get(side)!r}")
        grounded(r.get("because", ""), r.get("from"), f"requires {r.get('layer')}")
        requires.append({
            "layer": r.get("layer"),
            "needs": r.get("needs"),
            "because": (r.get("because") or "").strip(),
            "cite": r.get("from") or source,
        })

    epilogue = st.get("epilogue") or {}
    if epilogue:
        grounded(epilogue.get("text", ""), epilogue.get("from"), "epilogue")

    return {
        "brief": (st.get("brief") or "").strip(),
        "layers": layers,
        "workloads": workloads,
        "requires": requires,
        "epilogue": {
            "text": (epilogue.get("text") or "").strip(),
            "cite": epilogue.get("from") or source,
        },
    }


def build(bank: dict, lecture: str) -> tuple[dict, list[str], list[str]]:
    """Return (round file, warnings, errors)."""
    warnings: list[str] = []
    errors: list[str] = []
    items = []

    for item in bank.get("items") or []:
        source = (item.get("source") or {}).get("file", "")
        claims = build_claims(item, warnings)
        sequence = build_sequence(item, source, errors)
        terms = build_terms(item, source, errors)
        stack = build_stack(item, source, errors)

        # An item earns a place if any game can render it. A mechanism_recall
        # item has no options and used to be dropped here; carrying a sequence
        # is now reason enough to keep it.
        if not (claims or sequence or terms or stack):
            continue

        rec = {
            "id": item.get("id", "?"),
            "kind": item.get("kind", "mcq"),
            "lecture": lecture,
            # The prompt is the context a claim is judged against, code fence
            # and all. The arcade renders it as markdown.
            "context": (item.get("prompt") or "").strip(),
            # Shown after a run, not during it. A game that only says "wrong"
            # teaches nobody, which is the same reason the clicker slide
            # carries data-why.
            "why": (item.get("evidence") or "").strip(),
            "objectives": item.get("objectives") or [],
            "tags": [t for t in (item.get("tags") or []) if t],
        }
        if claims:
            rec.update(claims)
        if sequence:
            rec["sequence"] = sequence
        if terms:
            rec["terms"] = terms
        if stack:
            rec["stack"] = stack
        items.append(rec)

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
        errors,
    )


def render(rounds: dict) -> str:
    return json.dumps(rounds, indent=2, ensure_ascii=False) + "\n"


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

    # Every published lecture's notes, so a `from:` cannot cite an unreleased one.
    for path in paths:
        with path.open() as fh:
            head = yaml.safe_load(fh) or {}
        if head.get("status") == "published" and head.get("source_notes"):
            PUBLISHED_NOTES.add(head["source_notes"])

    stale: list[str] = []
    problems: list[str] = []
    written = 0
    merged: list[dict] = []

    for path in paths:
        lecture = path.stem
        if wanted and lecture not in wanted:
            continue

        with path.open() as fh:
            bank = yaml.safe_load(fh) or {}
        if bank.get("status", "unwritten") != "published" and not args.all:
            continue

        rounds, warnings, errors = build(bank, lecture)
        for w in warnings:
            print(f"{lecture}: {w}", file=sys.stderr)
        for e in errors:
            print(f"{lecture}: ERROR {e}", file=sys.stderr)
        problems.extend(errors)

        if not rounds["items"]:
            print(f"{lecture}: no playable items, nothing written", file=sys.stderr)
            continue

        merged.extend(rounds["items"])
        outputs = [(OUT / f"{lecture}.json", render(rounds))]

        for dest, text in outputs:
            if args.check:
                if (dest.read_text() if dest.exists() else "") != text:
                    stale.append(dest.name)
                continue
            OUT.mkdir(parents=True, exist_ok=True)
            dest.write_text(text)
            written += 1
            print(f"{lecture}: {len(rounds['items'])} items -> {dest.relative_to(ROOT)}")

    # One lecture carries at most a couple of sequences, which is fifteen
    # seconds of play. A game that needs a full minute of ordering asks for
    # data-lecture="all" and gets every published lecture at once.
    if not wanted:
        every = render(
            {
                "lecture": "all",
                "title": "Every published lecture",
                "generated_by": "tools/arcade_rounds.py",
                "items": merged,
            }
        )
        dest = OUT / "all.json"
        if args.check:
            if (dest.read_text() if dest.exists() else "") != every:
                stale.append(dest.name)
        elif merged:
            dest.write_text(every)
            print(f"all: {len(merged)} items -> {dest.relative_to(ROOT)}")

    if problems:
        print(f"\n{len(problems)} grounding problem(s); nothing is trustworthy until they are fixed",
              file=sys.stderr)
        return 1

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
