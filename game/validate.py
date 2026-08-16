#!/usr/bin/env python3
"""Check the quiz bank against the lecture material it claims to test.

Run from the repository root:

    python game/validate.py                  # check everything, exit 1 on any error
    python game/validate.py --review l15     # review cards for a human pass
    python game/validate.py --accept-sections  # after re-reading changed sections

This exists because the material has already drifted once without a quiz. The
figure-script headers in L11 and L13 disagreed with their own notes for weeks,
and one *published* page contradicted another. A question bank drafted against
either side would have shipped a wrong answer and nothing would have noticed.

So the rule the whole file is built around:

    source.quote  must appear verbatim in source.file
    verify.needle must appear inside source.quote

which gives an unbroken chain from a student's answer to a byte range in a
published page. Break the chain and the build fails.

That rule catches deletion and rewording, which is most of what happens to a
lecture, and it does not catch a rewrite that leaves the quoted sentence
standing while changing the argument around it. So each item also records a
hash of its enclosing section in content/sections.lock, and a change there is
reported rather than fatal: the list of affected items lands in the CI log of
the pull request that edited the lecture, and again as a diff on the lockfile.
Two further rules close the coverage direction, where the bank could previously
fail open: a published lecture with no bank at all, and an objective the notes
declare that objectives.yml has never heard of.

Deliberately pure text: no notebook execution, no network, no imports beyond
PyYAML. It runs in well under a second on the whole bank, which is why it is its
own CI job ahead of the book build rather than a step inside it.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from normalize import approx_in, norm_num, norm_text, num_sequence, strip_nums  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
CONTENT = Path(__file__).parent / "content"

KINDS = {
    "predict_measure", "direction", "rank", "mcq", "numeric_band",
    "spot_the_defect", "claim_vs_source", "notebook_run", "locus_of_control",
    "mechanism_recall", "teach_prompt",
}
# Kinds where the player picks from `options`, so the MCQ hygiene rules apply.
CHOICE_KINDS = {
    "predict_measure", "direction", "rank", "mcq", "spot_the_defect",
    "claim_vs_source", "notebook_run", "locus_of_control",
}
# Kinds a human scores. `answer` may be null.
FREE_KINDS = {"mechanism_recall", "teach_prompt"}

VOLATILITY = {"stable", "measured", "dated"}

MIN_ITEMS_PER_LECTURE = 10
LENGTH_BIAS_THRESHOLD = 0.60


@dataclass
class Issue:
    level: str          # "error" | "warn"
    where: str
    message: str


@dataclass
class Bank:
    lectures: dict = field(default_factory=dict)
    objectives: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)

    def err(self, where: str, message: str) -> None:
        self.issues.append(Issue("error", where, message))

    def warn(self, where: str, message: str) -> None:
        self.issues.append(Issue("warn", where, message))


# --- source access ---------------------------------------------------------

_source_cache: dict[Path, str] = {}


def read_source(rel: str) -> str | None:
    path = REPO / rel
    if path not in _source_cache:
        if not path.is_file():
            return None
        _source_cache[path] = path.read_text(encoding="utf-8")
    return _source_cache[path]


def headings_of(text: str) -> set[str]:
    return {
        norm_text(m.group(1))
        for m in re.finditer(r"^#{2,4}\s+(.+?)\s*$", text, re.MULTILINE)
    }


def toc_files() -> set[str]:
    """Every document listed in _toc.yml, as a repo-relative .md path.

    Used by the privacy rule: an item may only cite a page a student can
    actually open, since the item's whole promise is "go read the source".
    """
    raw = (REPO / "_toc.yml").read_text(encoding="utf-8")
    return {f"{m.group(1)}.md" for m in re.finditer(r"^\s*-?\s*file:\s*(\S+)", raw, re.MULTILINE)}


def toc_lectures() -> list[str]:
    """Lecture ids published in _toc.yml, in course order."""
    raw = (REPO / "_toc.yml").read_text(encoding="utf-8")
    return [m.group(1) for m in re.finditer(r"lectures/(l\d\d)/notes", raw)]


# --- sections --------------------------------------------------------------
#
# The quote check anchors an item to a *string*. That catches deletion and
# rewording, which is most of what happens, and it does not catch a rewrite that
# leaves the quoted sentence standing while changing the argument around it.
# Inserting "the advice below is superseded" directly above a quoted span passes
# every other rule in this file.
#
# So each item also records a hash of the section its quote lives in, in
# content/sections.lock. When that section changes, the item is reported. It is
# a warning and not an error on purpose: a rule that forced a re-review of every
# affected item on every edit is friction, and friction gets switched off. What
# it buys is a list, printed in the CI log of the pull request that made the
# change and visible again as a diff on the lockfile, saying "you edited these
# sections; these items depend on them".

LOCK = Path(__file__).parent / "content" / "sections.lock"


def sections_of(text: str) -> list[tuple[str, str]]:
    """Split a notes file into (heading, normalized body) at H2/H3 boundaries.

    Splitting on headings rather than tracking byte offsets means a hash is
    stable when something *elsewhere* in the file reflows, which is the common
    case and would otherwise make every hash churn on every edit.
    """
    out: list[tuple[str, list[str]]] = [("(preamble)", [])]
    for line in text.split("\n"):
        m = re.match(r"^(#{2,3})\s+(.+?)\s*$", line)
        if m:
            # The heading goes into its own section's body as well as being its
            # label. Some items quote the heading itself, and more importantly
            # renaming a heading *is* a change to the section, so it belongs
            # inside the hash rather than beside it.
            out.append((m.group(2), [m.group(2)]))
        else:
            out[-1][1].append(line)
    return [(h, norm_text("\n".join(body))) for h, body in out]


def section_for(text: str, quote: str) -> tuple[str, str] | None:
    """The (heading, body) whose body contains `quote`."""
    needle = norm_text(quote)
    if not needle:
        return None
    for heading, body in sections_of(text):
        if needle in body:
            return heading, body
    return None


def enclosing_h2(text: str, heading: str) -> str | None:
    """The H2 a given section sits under, or None if it is itself an H2."""
    current: str | None = None
    for line in text.split("\n"):
        m = re.match(r"^(#{2,3})\s+(.+?)\s*$", line)
        if not m:
            continue
        if norm_text(m.group(2)) == norm_text(heading):
            return None if len(m.group(1)) == 2 else current
        if len(m.group(1)) == 2:
            current = m.group(2)
    return None


def section_sha(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def load_lock() -> dict:
    if not LOCK.is_file():
        return {}
    return yaml.safe_load(LOCK.read_text(encoding="utf-8")) or {}


# --- rules -----------------------------------------------------------------

def check_grounding(bank: Bank, item: dict, where: str) -> None:
    """The load-bearing rule. Everything else is hygiene."""
    src = item.get("source") or {}
    verify = item.get("verify") or {}
    rel = src.get("file")

    if not rel:
        bank.err(where, "no source.file; an item that cites nothing cannot be checked")
        return

    if rel.startswith("course/modules/"):
        bank.err(
            where,
            f"cites instructor-only material: {rel}. The module files are the spec, "
            "never the source. See CLAUDE.md section 1",
        )
        return
    if "solutions/" in rel:
        bank.err(where, f"cites solution material: {rel}")
        return

    text = read_source(rel)
    if text is None:
        bank.err(where, f'source file "{rel}" does not exist')
        return

    published = toc_files()
    if rel.endswith(".md") and rel not in published:
        bank.err(
            where,
            f"{rel} is not listed in _toc.yml, so it is not published and the "
            'item\'s "go read the source" link would 404',
        )

    quote = src.get("quote")
    if not quote:
        bank.err(where, "no source.quote; the quote is what proves the claim is still there")
        return

    if norm_text(quote) not in norm_text(text):
        bank.err(
            where,
            f"quote does not appear in {rel}\n"
            f'          quote: "{quote.strip()[:90]}"\n'
            "          The source has probably changed. Re-read the section and "
            "re-review this item rather than editing the quote to match.",
        )
        return

    needle = verify.get("needle")
    if not needle:
        bank.err(where, "no verify.needle")
    elif norm_text(needle) not in norm_text(quote):
        bank.err(
            where,
            f'needle "{needle}" is not inside the quoted span; '
            "widen source.quote or fix the needle",
        )

    heading = src.get("heading")
    if heading and norm_text(heading) not in headings_of(text):
        bank.err(where, f'heading "{heading}" does not exist in {rel}')
    elif heading:
        # ...and it has to be the section the quote is actually in, or the H2
        # enclosing it. Checking only that the heading exists let 22 items ship
        # pointing somewhere the quote does not appear, usually because a short
        # needle like "eval gate" matched the objectives bullet at the top of
        # the file rather than the passage the item is about. The heading is
        # what a student is shown as the source, so a heading that is merely a
        # real heading is not good enough.
        found = section_for(text, quote)
        if found and norm_text(found[0]) != norm_text(heading):
            parent = enclosing_h2(text, found[0])
            if not parent or norm_text(parent) != norm_text(heading):
                bank.err(
                    where,
                    f'heading "{heading}" is not where the quote lives '
                    f'(it is in "{found[0]}"). Point the heading there, or '
                    "quote something distinctive from the section you meant: a "
                    "short quote matches its first occurrence in the file, "
                    "which is often the intro.",
                )

    # Every number in the answer has to be findable in the source. This is the
    # rule that would have caught the L11/L13 drift.
    answer = item.get("answer")
    if isinstance(answer, str):
        in_source = norm_num(text)
        for value in norm_num(answer):
            if not approx_in(value, in_source):
                bank.err(
                    where,
                    f"answer contains {value}, which does not appear anywhere in {rel}",
                )


def check_volatility(bank: Bank, item: dict, where: str) -> None:
    verify = item.get("verify") or {}
    vol = verify.get("volatility")
    src = (item.get("source") or {}).get("file", "")

    if vol not in VOLATILITY:
        bank.err(where, f"verify.volatility must be one of {sorted(VOLATILITY)}, got {vol!r}")
        return

    if src.endswith("make_figures.py") and vol == "stable":
        bank.err(
            where,
            "numbers in a figure script's docstring are measured on the author's "
            "machine; declare volatility: measured",
        )

    # A measured quantity may not be asked for as an exact value, because the
    # next re-measure moves it. What counts as "asking for the value" is narrow
    # on purpose: a numeric_band always does, and a choice item does only when
    # its options are distinguished by nothing but their numbers. An item whose
    # options carry real text is asking the player to pick a category, and the
    # number is a label on that category rather than the answer.
    if vol == "measured" and not item.get("tolerance"):
        kind = item.get("kind")
        asks_for_value = kind == "numeric_band"
        if kind == "mcq":
            bare = {strip_nums(o) for o in (item.get("options") or [])}
            asks_for_value = len(bare) == 1
        if asks_for_value:
            bank.err(
                where,
                "asks for an exact measured value with no tolerance. Measured "
                "numbers are machine-dependent: use kind: direction or rank, ask "
                "for a ratio, or set a tolerance",
            )

    expires = verify.get("expires")
    if vol == "dated" and not expires:
        bank.err(where, "dated items need verify.expires; prices and model ids move")
    if expires:
        if not isinstance(expires, date):
            bank.err(where, f"verify.expires must be a date, got {expires!r}")
        elif expires < date.today():
            bank.err(where, f"expired on {expires}; the answer may no longer be true")
        elif (expires - date.today()).days < 60:
            bank.warn(where, f"expires {expires}, within 60 days. Re-measure or convert to a direction item")


def check_choices(bank: Bank, item: dict, where: str) -> None:
    kind = item.get("kind")
    if kind not in CHOICE_KINDS:
        return

    options = item.get("options") or []
    if len(options) < 3:
        bank.err(where, f"needs at least 3 options, has {len(options)}")
        return

    answer = item.get("answer")
    if answer not in options:
        bank.err(where, "answer is not one of the options")

    seen: dict[str, int] = {}
    for i, opt in enumerate(options):
        key = norm_text(opt)
        if key in seen:
            bank.err(where, f"options {seen[key] + 1} and {i + 1} are identical after normalization")
        seen[key] = i

    # Numeric duplicates: two options that reduce to the same value AND say the
    # same thing are one option written twice. Sharing a number is not enough --
    # a rank item offers one set of values in several orders, and a direction
    # item offers one magnitude with opposite signs. In both the text is the
    # answer, so compare with the numbers stripped out.
    # Ordered, so that "A (0.97) > B (0.69)" and "B (0.97) > A (0.69)" stay
    # distinct. Its unique job is formatting variants of one option, e.g.
    # "1,263 tokens" against "1263 tokens", which the text rules miss.
    nums = [num_sequence(o) for o in options]
    bare = [strip_nums(o) for o in options]
    for i in range(len(options)):
        for j in range(i + 1, len(options)):
            if nums[i] and nums[i] == nums[j] and bare[i] == bare[j]:
                bank.err(
                    where,
                    f"options {i + 1} and {j + 1} are the same option twice "
                    f"({nums[i]}); one of them is not a distractor",
                )

    # Containment: an option contained in another can be eliminated by shape
    # rather than by knowing anything.
    for i in range(len(options)):
        for j in range(len(options)):
            if i == j:
                continue
            a, b = norm_text(options[i]), norm_text(options[j])
            if a and b and a != b and a in b:
                bank.err(
                    where,
                    f'option "{options[i][:50]}" is contained in '
                    f'"{options[j][:50]}"; eliminable by containment',
                )

    if kind == "predict_measure":
        predict = item.get("predict") or {}
        if not predict.get("common_prior"):
            bank.err(
                where,
                "predict_measure needs predict.common_prior: the naive expectation "
                "is the item's whole point and its best distractor",
            )


def check_shape(bank: Bank, item: dict, where: str) -> None:
    kind = item.get("kind")
    if kind not in KINDS:
        bank.err(where, f'unknown kind "{kind}"; expected one of {sorted(KINDS)}')

    rung = item.get("rung")
    if not isinstance(rung, int) or not 0 <= rung <= 7:
        bank.err(
            where,
            f"rung {rung!r} is not on the ladder (0-7); see "
            "course/optional/generating-is-not-learning.md",
        )

    if not (item.get("evidence") or "").strip():
        bank.err(
            where,
            "evidence is empty; it is the only thing a player sees on a miss, so "
            "it has to say why, not restate the answer",
        )

    if kind not in FREE_KINDS and not item.get("answer"):
        bank.err(where, "no answer")

    if kind in FREE_KINDS and not item.get("checklist"):
        bank.err(where, f"{kind} needs a checklist for the player to self-score against")

    verify = item.get("verify") or {}
    if verify.get("mode") == "manual" and not verify.get("exempt_reason"):
        bank.err(where, "mode: manual requires exempt_reason saying how the item is grounded instead")


def check_objectives(bank: Bank, item: dict, where: str, lecture: str) -> None:
    objs = item.get("objectives") or []
    if not objs:
        bank.err(where, "no learning objective; every item earns its place against one")
    for oid in objs:
        obj = bank.objectives.get(oid)
        if obj is None:
            bank.err(where, f'unknown objective "{oid}"')
        elif obj["lecture"] != lecture:
            bank.err(where, f'objective "{oid}" belongs to lecture {obj["lecture"]}, not {lecture}')


def check_objectives_match_notes(bank: Bank) -> None:
    """Objectives must still match the bullets in the notes they were lifted from."""
    for oid, obj in bank.objectives.items():
        text = read_source(f"lectures/{obj['lecture']}/notes.md")
        if text is None:
            continue
        section = re.search(
            r"^## Learning objectives\s*(.+?)^## ", text, re.MULTILINE | re.DOTALL
        )
        if not section:
            bank.warn(oid, f"no '## Learning objectives' section in lectures/{obj['lecture']}/notes.md")
            continue
        if norm_text(obj["text"]) not in norm_text(section.group(1)):
            bank.err(
                oid,
                f"objective text no longer matches lectures/{obj['lecture']}/notes.md. "
                "The notes were edited and objectives.yml was not.",
            )

    # ...and the other direction. The loop above only proves that objectives we
    # already know about still exist. Adding a bullet to the notes and not to
    # objectives.yml was silent, so a whole objective could go untested without
    # anything noticing, which is the coverage rule quietly failing open.
    for lecture in sorted({o["lecture"] for o in bank.objectives.values()} | set(bank.lectures)):
        text = read_source(f"lectures/{lecture}/notes.md")
        if text is None:
            continue
        section = re.search(
            r"^## Learning objectives\s*(.+?)^## ", text, re.MULTILINE | re.DOTALL
        )
        if not section:
            continue
        known = [norm_text(o["text"]) for o in bank.objectives.values() if o["lecture"] == lecture]
        for bullet in objective_bullets(section.group(1)):
            if norm_text(bullet) not in known:
                bank.err(
                    lecture,
                    f"lectures/{lecture}/notes.md declares an objective that "
                    f"objectives.yml does not have, so nothing tests it:\n"
                    f'          "{" ".join(bullet.split())[:110]}"',
                )


def objective_bullets(section: str) -> list[str]:
    """The objective bullets, rejoined across the hard wrap the notes use."""
    out: list[str] = []
    for line in section.split("\n"):
        if line.strip().startswith("- "):
            out.append(line.strip()[2:])
        elif out and line.startswith("  ") and line.strip():
            out[-1] += " " + line.strip()
    return out


def check_sections(bank: Bank, lock: dict) -> list[str]:
    """Report items whose cited section has changed since it was last accepted.

    Returns the ids that moved, so --accept-sections can name them.
    """
    moved: list[str] = []
    for lecture, data in bank.lectures.items():
        if data.get("status") == "unwritten":
            continue
        for item in data.get("items") or []:
            iid = item.get("id", f"{lecture}/<no id>")
            src = item.get("source") or {}
            text = read_source(src.get("file", ""))
            if text is None or not src.get("quote"):
                continue                      # check_grounding already said so
            found = section_for(text, src["quote"])
            if found is None:
                continue                      # ditto: the quote is not there
            heading, body = found
            now = section_sha(body)
            was = lock.get(iid)
            if was is None:
                moved.append(iid)
                bank.warn(iid, f'no accepted section hash yet (section "{heading}")')
            elif was != now:
                moved.append(iid)
                bank.warn(
                    iid,
                    f'the cited section "{heading}" in {src["file"]} has changed '
                    f"since this item was reviewed ({was} -> {now}). Re-read it, "
                    "then run: python game/validate.py --accept-sections",
                )
    return moved


def check_lecture_coverage(bank: Bank) -> None:
    """Every published lecture needs a bank, or an explicit unwritten stub.

    Without this a new lecture merges with no items and nothing says so, which
    is not hypothetical: L06 is in flight as this is written.
    """
    have = set(bank.lectures)
    for lecture in toc_lectures():
        if lecture not in have:
            bank.err(
                lecture,
                f"lectures/{lecture}/notes.md is published in _toc.yml but "
                f"game/content/{lecture}.yml does not exist. Author a bank, or "
                "add a stub with status: unwritten to say so deliberately.",
            )


def check_bank_level(bank: Bank) -> None:
    """Rules that need the whole bank, not one item."""
    seen_ids: dict[str, str] = {}
    longest_is_answer = 0
    total_choice = 0

    for lecture, data in bank.lectures.items():
        items = data.get("items") or []
        if data.get("status") == "published" and len(items) < MIN_ITEMS_PER_LECTURE:
            bank.warn(
                lecture,
                f"{len(items)} items; the floor is {MIN_ITEMS_PER_LECTURE} per published lecture",
            )

        # Serving the whole pool makes the item-set half of the anti-forgery
        # design inert: every student gets every item, so a copied PDF carries a
        # perfectly ordinary item set. Only the ordering would still differ.
        serve = data.get("serve")
        if isinstance(serve, int) and items:
            if serve > len(items):
                bank.err(
                    lecture,
                    f"serve: {serve} exceeds the {len(items)}-item pool",
                )
            elif serve == len(items):
                bank.err(
                    lecture,
                    f"serve: {serve} equals the pool size, so every student is "
                    "served every item and item-set personalization does nothing. "
                    "Lower serve or add items.",
                )
            elif len(items) < 1.5 * serve:
                bank.warn(
                    lecture,
                    f"pool of {len(items)} against serve of {serve}: two students "
                    "will share most of their items. Aim for at least 2x, "
                    "ideally 3x.",
                )

        covered: set[str] = set()
        for item in items:
            iid = item.get("id", "<no id>")
            if iid in seen_ids:
                bank.err(iid, f"duplicate item id (also in {seen_ids[iid]})")
            seen_ids[iid] = lecture
            if not iid.startswith(f"{lecture}-"):
                bank.err(iid, f'id does not start with "{lecture}-" but is declared in {lecture}.yml')
            covered.update(item.get("objectives") or [])

            if item.get("kind") in CHOICE_KINDS:
                options = item.get("options") or []
                answer = item.get("answer")
                if options and answer in options:
                    total_choice += 1
                    if len(answer) == max(len(o) for o in options):
                        longest_is_answer += 1

        for oid, obj in bank.objectives.items():
            if obj["lecture"] != lecture:
                continue
            if data.get("status") == "unwritten":
                # An unwritten bank covers nothing by definition, and it already
                # says so. The objectives are still registered, because the
                # notes declare them and this file checks that objectives.yml
                # matches the notes; requiring coverage from a bank that
                # announces it has no items would leave the only two ways out
                # being to delete the objectives or to write the bank under
                # deadline. Neither is what "unwritten" is for.
                continue
            n = sum(1 for it in items if oid in (it.get("objectives") or []))
            if n == 0:
                bank.err(oid, f"no items cover this objective; {lecture} leaves it untested")
            elif n == 1:
                bank.warn(oid, "covered by 1 item; a single item is a coin flip, not coverage")

    # Length bias, measured in the course's own content. L21 teaches that this is
    # a real systematic error in judges; it is one in humans too.
    if total_choice >= 20:
        share = longest_is_answer / total_choice
        if share > LENGTH_BIAS_THRESHOLD:
            bank.err(
                "<bank>",
                f"length bias: the correct answer is the longest option in "
                f"{share:.0%} of {total_choice} choice items (threshold "
                f"{LENGTH_BIAS_THRESHOLD:.0%}). Pad the distractors or trim the answers.",
            )


# --- driver ----------------------------------------------------------------

def load(bank: Bank) -> None:
    objs = yaml.safe_load((CONTENT / "objectives.yml").read_text(encoding="utf-8")) or []
    for obj in objs:
        bank.objectives[obj["id"]] = obj

    for path in sorted(CONTENT.glob("l*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        lecture = data.get("lecture") or path.stem
        if data.get("lecture") != path.stem:
            bank.err(path.name, f'lecture "{data.get("lecture")}" does not match filename')
        bank.lectures[lecture] = data


def validate(lock: dict | None = None) -> tuple[Bank, list[str]]:
    bank = Bank()
    load(bank)
    check_lecture_coverage(bank)
    check_objectives_match_notes(bank)

    for lecture, data in bank.lectures.items():
        if data.get("status") == "unwritten":
            continue
        for item in data.get("items") or []:
            where = item.get("id", f"{lecture}/<no id>")
            check_shape(bank, item, where)
            check_grounding(bank, item, where)
            check_volatility(bank, item, where)
            check_choices(bank, item, where)
            check_objectives(bank, item, where, lecture)

    check_bank_level(bank)
    moved = check_sections(bank, load_lock() if lock is None else lock)
    return bank, moved


def accept_sections(bank: Bank, moved: list[str]) -> int:
    """Record the current section hashes.

    Run this *after* re-reading the sections that changed, not instead of. The
    resulting diff on content/sections.lock is the review artifact: one line per
    item whose source moved, which is exactly the list somebody should have
    looked at.
    """
    lock = load_lock()
    for lecture, data in bank.lectures.items():
        if data.get("status") == "unwritten":
            continue
        for item in data.get("items") or []:
            src = item.get("source") or {}
            text = read_source(src.get("file", ""))
            if text is None or not src.get("quote"):
                continue
            found = section_for(text, src["quote"])
            if found:
                lock[item["id"]] = section_sha(found[1])

    # Drop entries for items that no longer exist, so the lock does not grow
    # a tail of ids nobody can trace.
    live = {i["id"] for d in bank.lectures.values() for i in (d.get("items") or [])}
    stale = [k for k in lock if k not in live]
    for k in stale:
        del lock[k]

    LOCK.write_text(
        "# Hash of the notes section each item's quote lives in.\n"
        "# Regenerate with: python game/validate.py --accept-sections\n"
        "# A change here means a cited section was edited; the diff is the list\n"
        "# of items somebody should have re-read.\n"
        + yaml.safe_dump(dict(sorted(lock.items())), sort_keys=False),
        encoding="utf-8",
    )
    print(f"recorded {len(lock)} section hashes ({len(moved)} changed, {len(stale)} removed)")
    return 0


def review(bank: Bank, lecture: str) -> None:
    """Four-line cards for the human pass.

    The reviewer never opens the notes, because validate() has already proved
    the quoted line is in the file. What is left is only what a checker cannot
    decide: is the distractor tempting, is the evidence a mechanism or a
    restatement, and is the rung honest.
    """
    data = bank.lectures.get(lecture)
    if not data:
        print(f"no bank for {lecture}")
        return
    for item in data.get("items") or []:
        src = item.get("source") or {}
        objs = ", ".join(item.get("objectives") or [])
        print(f"\n\033[1m{item['id']}\033[0m  {item['kind']}  rung {item.get('rung')}")
        print(f"  Q  {' '.join((item.get('prompt') or '').split())[:150]}")
        print(f"  A  {item.get('answer')}")
        print(f"  S  {src.get('file')} :: {src.get('heading')}")
        print(f"     \"{(src.get('quote') or '').strip()[:110]}\"")
        print(f"  O  {objs}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--review", metavar="LECTURE", help="print review cards and exit")
    ap.add_argument(
        "--accept-sections",
        action="store_true",
        help="record the current section hashes, after re-reading the sections",
    )
    args = ap.parse_args()

    bank, moved = validate()

    if args.accept_sections:
        return accept_sections(bank, moved)

    if args.review:
        review(bank, args.review)
        return 0

    items = sum(len(d.get("items") or []) for d in bank.lectures.values())
    print(f"{len(bank.lectures)} lecture(s), {items} items, {len(bank.objectives)} objectives")

    warns = [i for i in bank.issues if i.level == "warn"]
    errors = [i for i in bank.issues if i.level == "error"]

    for issue in warns:
        print(f"\033[33mwarn\033[0m  {issue.where}: {issue.message}")
    for issue in errors:
        print(f"\033[31merror\033[0m {issue.where}: {issue.message}")

    if errors:
        print(f"\n\033[31m{len(errors)} error(s), {len(warns)} warning(s)\033[0m")
        return 1
    print(f"\n\033[32mOK\033[0m ({len(warns)} warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
