#!/usr/bin/env python3
"""Check a folder of submitted module PDFs.

    python tools/verify_evidence.py submissions/l15/ \
        --pool game/content/l15.yml \
        --roster ~/private/f26-roster.csv \
        --csv out.csv

The semester MAC key is found automatically: --key, then $GAME_MAC_KEY, then
~/.config/f26-06763/mac-key, then the macOS keychain. Grading should not require
remembering a 64-character string.

`--pool` names the bank as it stands today, which is usually not the bank the
student was served. Item selection is a function of the whole pool, so adding
one item changes which items everybody gets. Each PDF says which pool_version it
was issued under, and anything older is checked against the snapshot in
`game/content/pools/`, printed as a `pool:` line. That archive is what keeps a
week-3 PDF verifiable in week 9; `tools/pool_archive.py` maintains it and CI
fails the build if a bank was edited without its version being bumped. If a
version is missing from it the derivation checks report `?` rather than a
mismatch, because that is a gap in this repository and not something a student
did.

Keep the roster outside the repository. The repository is private but the site
is public, and CLAUDE.md section 1 is unambiguous about student data.

WHAT THIS IS FOR, honestly. One module is worth a fraction of a percent of a
final grade. Nobody rational reverse-engineers a JavaScript bundle for that, and
any control costing more than an afternoon, or producing one false accusation,
is a net loss. So this is not built to be unforgeable, which a static
client-side app cannot be: every byte of the bundle, key included, is a
view-source away. It is built so that the cheapest successful forgery costs at
least as much as doing the module honestly, and so the thirty-second forgeries
are loud.

There already exists a forgery that costs exactly as much as compliance: run the
module under a classmate's Andrew ID. It verifies perfectly here, and in Canvas,
and it always will. That is the floor. Everything below exists so the forgeries
*cheaper* than that floor do not also work.

The secondary use is more valuable than the policing. First-try accuracy per
item, across a class and a semester, tells you which concepts are not landing.
That justifies the payload on its own.

Verdicts, and note that none of them is "cheater":

    PASS        credit.
    PASS*       credit, with an anomaly printed. Never a penalty: a student who
                already knew the material and one who guessed well are
                indistinguishable, and both did the module.
    UNREADABLE  credit after the student re-downloads. Preview, mobile share
                sheets and "compress PDF" all eat metadata. This is a
                false-positive bucket, not an accusation bucket.
    REVIEW      a sixty-second conversation. The overwhelmingly likely cause is
                a mistyped Andrew ID or a stale bundle, not fraud.

No thresholds and no automatic grade actions. The timing distribution is
printed, not judged: you have no idea what a normal completion time looks like
until after the first module, and a threshold picked in advance will fire on the
student who reads quickly.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import csv
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from derive import derive, normalize_id, selection_hash  # noqa: E402

#: Must match SCHEMA in game/src/evidence/payload.ts. Bumped to /2 when the
#: payload gained `derive.attempt` and a scored `score` block; a /1 file has no
#: attempt, so it cannot be re-derived and is reported as such rather than being
#: quietly mis-verified against attempt 1.
SCHEMA = "cmu-06763-attest/2"
KNOWN_OLD_SCHEMAS = {"cmu-06763-attest/1"}
BEGIN = "-----BEGIN 06763 ATTESTATION-----"
END = "-----END 06763 ATTESTATION-----"
DOMAIN = b"06763/attest/v1\x00"

# Must match game/src/evidence/payload.ts. Injected there at build time; this is
# the local-build fallback, and it is the literal string a bundle built without
# GAME_MAC_KEY ships with.
DEV_MAC_KEY = "dev-key-not-secret"

# Where the semester key lives on the grading machine. Outside the repository,
# owner-readable only. GitHub secrets are write-only, so the copy CI uses cannot
# be read back: if this file and the keychain entry are both lost, the only
# remaining copy is the one in the published JavaScript bundle, which is a
# fittingly awkward reminder of what this key is and is not.
POOL_ARCHIVE = Path(__file__).resolve().parent.parent / "game" / "content" / "pools"

KEY_FILE = Path.home() / ".config" / "f26-06763" / "mac-key"
KEYCHAIN_SERVICE = "f26-06763-game-mac-key"


def resolve_key(explicit: str | None) -> tuple[str, str]:
    """Find the semester MAC key. Returns (key, where it came from).

    Ordered so the least surprising source wins: an explicit flag, then the
    environment, then the two local stores. Grading should not require
    remembering a 64-character string.
    """
    if explicit:
        return explicit, "--key"

    from_env = os.environ.get("GAME_MAC_KEY")
    if from_env:
        return from_env.strip(), "$GAME_MAC_KEY"

    if KEY_FILE.is_file():
        mode = KEY_FILE.stat().st_mode & 0o077
        if mode:
            print(f"::warning::{KEY_FILE} is readable by others; chmod 600 it")
        return KEY_FILE.read_text(encoding="utf-8").strip(), str(KEY_FILE)

    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip(), "macOS keychain"
        except (OSError, subprocess.SubprocessError):
            pass

    return DEV_MAC_KEY, "development fallback"

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


# --- attestation -----------------------------------------------------------

def crockford(data: bytes) -> str:
    bits = value = 0
    out = []
    for byte in data:
        value = (value << 8) | byte
        bits += 8
        while bits >= 5:
            out.append(CROCKFORD[(value >> (bits - 5)) & 31])
            bits -= 5
    if bits:
        out.append(CROCKFORD[(value << (5 - bits)) & 31])
    return "".join(out)


def make_code(mac_key: str, payload: bytes) -> str:
    tag = hmac.new(mac_key.encode(), DOMAIN + payload, hashlib.sha256).digest()[:10]
    raw = crockford(tag)
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"


def canon_code(code: str) -> str:
    """Crockford's confusable folding, so a hand-typed code still matches."""
    s = code.upper().replace("-", "").replace(" ", "")
    return s.replace("O", "0").replace("I", "1").replace("L", "1").replace("U", "V")


def b64url_decode(s: str) -> bytes:
    s = re.sub(r"\s+", "", s)
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@dataclass
class Extract:
    payload_bytes: bytes | None = None
    payload: dict | None = None
    channel: str = "none"
    page_text: str = ""
    #: Filled rectangles on page 1, as (x, y, size). The seal is drawn out of
    #: these and is read back out of them; see check_seal.
    rects: list = field(default_factory=list)
    error: str = ""


#: Modules of the security seal, in points. Must match DIGIT_PT and MODULE_PT
#: in game/src/evidence/seal.ts, which game/tests/test_seal.py checks by reading
#: both files, the same way test_derive.py checks WRONG_PENALTY. The two sizes
#: differ so this side can tell a digit module from a data module without
#: knowing where either block was placed.
SEAL_DIGIT_PT = 4.0
SEAL_MODULE_PT = 2.6
SEAL_GRID = 8
SEAL_DATA_BITS = (SEAL_GRID - 1) * (SEAL_GRID - 1)

#: The 5x7 bitmap font the seal draws the score with, one 5-bit row per byte,
#: most significant bit leftmost. Mirrored from game/src/evidence/seal.ts and
#: checked against it by the same test. This side needs it because the check is
#: not "does the seal look like a seal" but "does it draw the number this
#: payload says", which means rendering the expected bitmap and comparing.
SEAL_FONT = {
    "0": (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E),
    "1": (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "2": (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F),
    "3": (0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E),
    "4": (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02),
    "5": (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E),
    "6": (0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E),
    "7": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    "8": (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E),
    "9": (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C),
    "%": (0x18, 0x19, 0x02, 0x04, 0x08, 0x13, 0x03),
}


def page_content(page) -> bytes:
    """Raw bytes of a page's content stream.

    Must be read *before* anything calls extract_text() on that page. pypdf
    leaves a parsed ContentStream behind the first time text is pulled out of a
    page, and that object's get_data() returns b"" rather than the stream it was
    built from. Asking in the wrong order does not raise: it hands back no
    rectangles, so every seal reports absent and the check quietly stops
    checking, which is the failure mode this file exists to avoid.
    """
    try:
        obj = page.get("/Contents")
        if obj is None:
            return b""
        obj = obj.get_object()
        parts = obj if isinstance(obj, list) else [obj]
        return b"\n".join(part.get_object().get_data() for part in parts)
    except Exception:  # noqa: BLE001  an unreadable seal is not a failed PDF
        return b""


def parse_rects(content: bytes) -> list:
    """Filled squares in a page content stream, as (x, y, size).

    Only `re` immediately followed by the fill operator, so the seal's stroked
    frame and the rules elsewhere on the page are not picked up. jsPDF emits a
    top-left origin as a negative height, hence the abs().
    """
    out = []
    for m in re.finditer(
        rb"(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+) re\s+f\b", content
    ):
        try:
            x, y, w, h = (float(g) for g in m.groups())
        except ValueError:
            continue
        if abs(abs(w) - abs(h)) < 0.01:
            out.append((x, y, abs(w)))
    return out


def modules_at(rects: list, size: float) -> set:
    """The squares of one module size, as (col, row) on their own grid.

    Row 0 is the top one. PDF space counts upward and the seal was drawn
    downward, so the vertical axis is flipped back here.
    """
    same = [(x, y) for x, y, s in rects if abs(s - size) < 0.05]
    if not same:
        return set()
    x0 = min(x for x, _ in same)
    y1 = max(y for _, y in same)
    return {(round((x - x0) / size), round((y1 - y) / size)) for x, y in same}


def at_origin(modules: set) -> set:
    """Shift a module set so its top-left occupied cell is (0, 0).

    Both sides go through this, and they have to. A drawn block is only
    locatable by the squares that are actually inked, so a glyph whose leftmost
    column is blank (a `1` is the one that bites) reports one column to the left
    of where it was drawn. Comparing a normalized set against an unnormalized
    one failed every seal that began with a 1, which is every seal reading 100%.
    """
    if not modules:
        return set()
    c0 = min(c for c, _ in modules)
    r0 = min(r for _, r in modules)
    return {(c - c0, r - r0) for c, r in modules}


def glyph_modules(text: str) -> set:
    """Mirror of glyphModules in seal.ts: 5x7 cells, one blank column between."""
    on = set()
    col = 0
    for ch in text:
        rows = SEAL_FONT.get(ch)
        if rows is None:
            col += 3
            continue
        for r in range(7):
            for c in range(5):
                if (rows[r] >> (4 - c)) & 1:
                    on.add((col + c, r))
        col += 6
    return on


def data_modules(tag: bytes) -> set:
    """Mirror of dataModules in seal.ts: an L finder plus the low tag bits."""
    on = {(0, r) for r in range(SEAL_GRID)}
    on |= {(c, SEAL_GRID - 1) for c in range(1, SEAL_GRID)}
    for i in range(SEAL_DATA_BITS):
        if (tag[(i >> 3) % len(tag)] >> (i & 7)) & 1:
            on.add((1 + i % (SEAL_GRID - 1), i // (SEAL_GRID - 1)))
    return on


def extract(path: Path) -> Extract:
    """Pull the attestation out, trying the sturdier channel first."""
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        sys.exit("pypdf is required: pip install pypdf")

    out = Extract()
    try:
        reader = PdfReader(str(path))
        # Before extract_text, deliberately. See page_content.
        out.rects = parse_rects(page_content(reader.pages[0])) if reader.pages else []
        out.page_text = "\n".join((p.extract_text() or "") for p in reader.pages)
        meta = reader.metadata or {}
        candidates = [("info", str(meta.get("/Keywords") or ""))]
    except Exception as exc:  # noqa: BLE001
        out.error = f"cannot read PDF: {exc}"
        return out

    # Whitespace inside the block must be stripped before decoding: extractors
    # insert newlines and sometimes spaces, and that is the single most common
    # reason a block like this fails to parse.
    match = re.search(re.escape(BEGIN) + r"(.*?)" + re.escape(END), out.page_text, re.S)
    if match:
        candidates.append(("text", match.group(1)))

    for channel, blob in candidates:
        blob = re.sub(r"\s+", "", blob or "")
        if not blob:
            continue
        try:
            raw = b64url_decode(blob)
            payload = json.loads(raw)
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("schema") == SCHEMA:
            out.payload_bytes, out.payload, out.channel = raw, payload, channel
            return out
        if payload.get("schema") in KNOWN_OLD_SCHEMAS:
            # Readable, just older than this verifier. Say so: dropping it into
            # the generic bucket below would tell a TA the student's file was
            # corrupt, when in fact the repository is what moved.
            out.error = (
                f"attestation is {payload.get('schema')}, this verifier reads {SCHEMA}. "
                "The PDF was issued by an older build of the game; re-run "
                "tools/verify_evidence.py from the commit that built it, or have "
                "the student redo the module on the current site."
            )
            return out

    if not out.error:
        out.error = "no readable attestation block"
    return out


# --- checks ----------------------------------------------------------------

@dataclass
class Result:
    path: Path
    verdict: str = "REVIEW"
    andrew_id: str = ""
    name: str = ""
    lecture: str = ""
    channel: str = "none"
    completed: int = 0
    first_try: int = 0
    #: 1-based, from the payload. A high attempt is not misconduct and is never
    #: treated as such here: it is printed so a grader can apply whatever retake
    #: policy the syllabus states, which is a decision for a human.
    attempt: int = 1
    #: Participation percent, recomputed from `items` rather than trusted.
    percent: "int | None" = None
    active_ms: int = 0
    elapsed_ms: int = 0
    code: str = ""
    #: Which pool this PDF was checked against: "current", "archived vN", or
    #: "vN (not archived)". Printed on its own line rather than pushed through
    #: `notes`, because `notes` is what promotes PASS to PASS*, and being
    #: checked against the archive is the correct path rather than an anomaly.
    #: Once a bank has been bumped it is the path every honest PDF takes, and a
    #: PASS* on all of them would leave PASS* meaning nothing.
    pool_source: str = "current"
    checks: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    problems: list = field(default_factory=list)


def check_printed_text_agrees(res: Result, ex: Extract) -> None:
    """The cheapest useful check: no key, no repo, no pool.

    Catches the realistic version of tampering, which is opening the PDF in an
    editor and changing the printed score or name. A text editor changes what is
    drawn on page 1, not the base64 on the last page.
    """
    p = ex.payload or {}
    text = re.sub(r"\s+", " ", ex.page_text)
    missing = []
    for label, value in (
        ("andrew id", p.get("student", {}).get("andrew_id", "")),
        ("name", p.get("student", {}).get("name", "")),
        ("code", res.code),
    ):
        if value and str(value) not in text:
            missing.append(label)

    score = p.get("score", {})
    printed_first_try = f"{score.get('first_try')} of {score.get('completed')}"
    if printed_first_try not in text:
        missing.append("first-try score")

    # The two numbers that leave this page: the one a TA types into a gradebook
    # and the one that says which run produced it. Both are drawn on page 1 and
    # both are in the MAC'd payload, so editing either in a text editor puts the
    # two out of step and lands here.
    percent = score.get("percent")
    if percent is not None and f"{percent}%" not in text:
        missing.append("participation score")
    attempt = p.get("derive", {}).get("attempt")
    if attempt is not None and f"Attempt {attempt}" not in text:
        missing.append("attempt")

    # The summary line under the item table states the score a second time, as
    # a sum and a divisor, so it is checked a second time. A page that prints
    # arithmetic contradicting its own payload is the same forgery as one that
    # prints the wrong percent, and pinning the sum and the count is what stops
    # the line from becoming a place to lie for free. Absent is skipped: PDFs
    # issued before the line existed are honest work and must not land here.
    graded_items = [i for i in p.get("items", []) if i.get("ans")]
    if graded_items and "graded item" in text:
        earned = sum(
            score_from_tries(i.get("tries", 1), bool(i.get("revealed")))
            for i in graded_items
        )
        if f"{earned:.2f} over {len(graded_items)} graded item" not in text:
            missing.append("average line")

    res.checks["txt"] = "ok" if not missing else "MISM"
    if missing:
        res.problems.append(f"printed page disagrees with payload: {', '.join(missing)}")


def check_mac(res: Result, ex: Extract, mac_key: str) -> None:
    """Does the code printed on page 1 match the embedded payload?

    Compares against the whole page rather than against a regex capture. Text
    extraction runs the code up against neighbouring labels often enough that
    anchoring on a word boundary produced a false BAD on every clean file, and a
    verifier that cries wolf on honest work is worse than no verifier.
    """
    expected = make_code(mac_key, ex.payload_bytes or b"")
    haystack = canon_code(re.sub(r"\s+", "", ex.page_text))
    ok = canon_code(expected) in haystack
    res.checks["mac"] = "ok" if ok else "BAD"
    if not ok:
        res.problems.append(
            f"the code printed on the page is not the one this payload implies "
            f"(expected {expected})"
        )


def check_seal(res: Result, ex: Extract, mac_key: str) -> None:
    """Read the security seal back and compare it to the payload.

    The score on page 1 is drawn as filled squares rather than typeset, so the
    thirty-second forgery (open the PDF, find `(95%)`, type `(99%)`) has nothing
    to find. That on its own would only be obscurity, and obscurity is not
    something this course should be teaching. What makes it a control is this
    function: the squares are on a fixed grid, so the number is machine-readable
    from the content stream, and it is compared against the number the payload
    computes. Editing the picture is therefore caught, not merely made tedious.

    The data block is checked the same way against the MAC tag. That covers the
    attack the drawn score invites, which is lifting a good-looking seal out of
    a classmate's PDF: their tag is not this payload's tag.

    Absent is `-`, never a problem. PDFs issued before the seal existed are
    honest work and must not land in REVIEW for it.
    """
    p = ex.payload or {}
    drawn_digits = modules_at(ex.rects, SEAL_DIGIT_PT)
    drawn_data = modules_at(ex.rects, SEAL_MODULE_PT)
    if not drawn_digits and not drawn_data:
        res.checks["seal"] = "-"
        return

    problems = []
    percent = res.percent
    if percent is not None and at_origin(glyph_modules(f"{percent}%")) != at_origin(drawn_digits):
        problems.append(f"the seal does not draw {percent}%")

    expected_tag = hmac.new(
        mac_key.encode(), DOMAIN + (ex.payload_bytes or b""), hashlib.sha256
    ).digest()[:10]
    if at_origin(data_modules(expected_tag)) != at_origin(drawn_data):
        problems.append("the seal's data block is not this payload's")

    res.checks["seal"] = "ok" if not problems else "BAD"
    for problem in problems:
        res.problems.append(problem)


def archived_bank(lecture: str, pool_version: int) -> dict | None:
    """The bank as it stood at `pool_version`, or None if it was never archived.

    Item selection is a function of the whole pool, so adding one item changes
    which items every student is served. Re-deriving a week-3 PDF against the
    week-9 bank compares it to a derivation that never existed, and the honest
    student comes back MISM. See tools/pool_archive.py for the archive this
    reads and the CI check that keeps it current.

    Shaped like a bank rather than like the archive, so the two checks
    downstream do not need to know which one they were handed.
    """
    p = POOL_ARCHIVE / f"{lecture}.json"
    if not p.is_file():
        return None
    try:
        snap = json.loads(p.read_text(encoding="utf-8")).get("versions", {}).get(str(pool_version))
    except (json.JSONDecodeError, OSError):
        return None
    if not snap:
        return None
    return {
        "lecture": lecture,
        "pool_version": pool_version,
        "serve": snap.get("serve"),
        "items": [{"id": i, **rec} for i, rec in sorted(snap.get("items", {}).items())],
    }


def resolve_bank(live: dict, payload: dict) -> tuple[dict | None, str]:
    """Which bank this PDF should be checked against, and where it came from.

    The live file is used only when the PDF was issued under the version it
    still carries. Otherwise the archived snapshot is authoritative, because it
    is the only thing that describes what the student was actually served.
    """
    lecture = payload.get("module", {}).get("lecture", "") or live.get("lecture", "")
    served_v = payload.get("module", {}).get("pool_version", live.get("pool_version", 1))
    if served_v == live.get("pool_version", 1):
        return live, "current"
    arch = archived_bank(lecture, served_v)
    if arch is None:
        return None, f"v{served_v} (not archived)"
    return arch, f"archived v{served_v}"


def check_derivation(res: Result, ex: Extract, pool: dict, pool_version: int) -> None:
    """The strongest layer, and it needs no secret.

    Re-derive the item set from the Andrew ID in the payload. A classmate's PDF
    re-issued under a different id carries the wrong items, and this catches it
    even if the MAC key has been extracted.
    """
    p = ex.payload or {}
    module = p.get("module", {})
    try:
        served = derive(
            p.get("student", {}).get("andrew_id", ""),
            module.get("lecture", ""),
            pool,
            module.get("pool_version", pool_version),
            module.get("serve", len(p.get("items", []))),
            # The attempt is part of the derivation, so it has to come from the
            # PDF. Defaulting to 1 rather than erroring keeps a schema/1 file
            # readable; it will simply fail `drv` if it was a real retake.
            p.get("derive", {}).get("attempt", 1),
        )
    except Exception as exc:  # noqa: BLE001
        res.checks["drv"] = "ERR"
        res.problems.append(f"cannot re-derive: {exc}")
        return

    got = [(i["id"], i.get("v", "-"), tuple(i.get("opts", []))) for i in p.get("items", [])]
    want = [(s["id"], s["variant"], tuple(s["option_order"])) for s in served]

    if got == want:
        res.checks["drv"] = "ok"
    else:
        res.checks["drv"] = "MISM"
        got_ids = {g[0] for g in got}
        want_ids = {w[0] for w in want}
        if got_ids != want_ids:
            extra = sorted(got_ids - want_ids)[:3]
            res.problems.append(
                f"item set is not the one {p.get('student', {}).get('andrew_id')} derives to "
                f"(e.g. {', '.join(extra) or 'ordering differs'})"
            )
        else:
            res.problems.append("item variants or option order do not match the derivation")

    reported = p.get("derive", {}).get("selection_hash")
    if reported and reported != selection_hash(served):
        res.notes.append("selection_hash disagrees with the re-derived list")


#: Deducted per wrong answer. Must equal WRONG_PENALTY in game/src/store/log.ts.
#: Unlike the derivation, this pair is not covered by the generated vectors, so
#: it is checked the only other way available: game/tests/test_derive.py asserts
#: the two constants agree by reading them out of both files.
WRONG_PENALTY = 0.25


def score_from_tries(tries: int, revealed: bool) -> float:
    """One point a question, less WRONG_PENALTY for each wrong answer.

    The mirror of `scoreFromTries` in game/src/store/log.ts. Kept as a function
    rather than inlined so the rule appears exactly once on this side too.
    """
    if revealed:
        return 0.0
    return max(0.0, 1.0 - WRONG_PENALTY * max(0, int(tries) - 1))


def participation_percent(items: list) -> "int | None":
    """Recompute the participation score from the per-item record.

    Recomputed, never read out of `score.percent`, and the difference matters:
    `tries` is cross-checked against the pool by `check_answers`, so a score
    derived from it inherits that check. A percent taken on trust would only
    ever prove that the payload agrees with itself.

    Items with no chosen option are the free-recall kind, which the student
    scores against a checklist. They are excluded here exactly as they are in
    the app, because counting them would hand everybody a free point.
    """
    graded = [i for i in items if i.get("ans")]
    if not graded:
        return None
    milli = sum(round(score_from_tries(i.get("tries", 1), bool(i.get("revealed"))) * 1000)
                for i in graded)
    return round(milli / len(graded) / 10)


def check_score(res: Result, ex: Extract) -> None:
    """Does the printed participation score match the items it was built from?"""
    p = ex.payload or {}
    recomputed = participation_percent(p.get("items", []))
    res.percent = recomputed
    claimed = (p.get("score") or {}).get("percent")

    if recomputed is None:
        res.checks["pct"] = "-"
        return
    if claimed is not None and int(claimed) != recomputed:
        res.checks["pct"] = "MISM"
        res.problems.append(
            f"payload claims {claimed}% but its own items compute to {recomputed}%"
        )
        return
    res.checks["pct"] = "ok"


def check_answers(res: Result, ex: Extract, bank: dict) -> None:
    """Recompute each item's first-try correctness from the pool.

    Per item rather than on the aggregate, because free-response kinds carry no
    options and are scored by the player. Comparing totals meant one
    mechanism_recall item in the draw silently disabled the whole check.

    An option id indexes the *original* pool order, never the shuffled display
    position, which is what keeps this checkable at all.
    """
    p = ex.payload or {}
    by_id = {i["id"]: i for i in bank.get("items", [])}

    gradeable = 0
    disagreed = []
    unknown = 0

    for rec in p.get("items", []):
        item = by_id.get(rec["id"])
        if item is None:
            unknown += 1
            continue
        options = item.get("options") or []
        if not options:
            continue                       # free response: the player scored it
        try:
            idxs = [int(c[3:]) for c in (rec.get("ans") or []) if c.startswith("opt")]
        except ValueError:
            idxs = []
        if not idxs:
            continue
        gradeable += 1
        chosen = [options[i] for i in idxs if 0 <= i < len(options)]
        should_be = bool(chosen) and chosen[0] == item.get("answer") and rec.get("tries") == 1
        if should_be != bool(rec.get("first_ok")):
            disagreed.append(rec["id"])

    if unknown:
        res.notes.append(f"{unknown} served item(s) are no longer in the pool")
    if gradeable == 0:
        res.checks["ans"] = "-"
        return

    res.checks["ans"] = "ok" if not disagreed else "MISM"
    if disagreed:
        res.problems.append(
            f"{len(disagreed)} of {gradeable} items claim a first-try result the "
            f"pool disagrees with (e.g. {', '.join(disagreed[:3])})"
        )


def verify_one(path: Path, bank: dict, mac_key: str) -> Result:
    res = Result(path=path)
    ex = extract(path)
    res.channel = ex.channel

    if ex.payload is None:
        res.verdict = "UNREADABLE"
        res.problems.append(ex.error or "no attestation")
        return res

    p = ex.payload
    student = p.get("student", {})
    res.andrew_id = student.get("andrew_id", "")
    res.name = student.get("name", "")
    res.lecture = p.get("module", {}).get("lecture", "")
    score = p.get("score", {})
    res.completed = score.get("completed", 0)
    res.first_try = score.get("first_try", 0)
    res.attempt = p.get("derive", {}).get("attempt", 1)
    session = p.get("session", {})
    res.active_ms = session.get("active_ms", 0)
    res.elapsed_ms = session.get("elapsed_ms", 0)

    # The code is printed on page 1; read it from there, since that is the thing
    # a tamperer would have had to keep consistent.
    #
    # Deliberately unanchored. This regex used to carry \b at both ends and
    # therefore matched nothing at all: extraction returns the code run up
    # against its own label, as `...QPQ3Verification`, and a word boundary
    # between `3` and `V` does not exist. `res.code` was the empty string on
    # every file ever checked, which cost three checks without failing anything
    # loudly: the code leg of check_printed_text_agrees skips a falsy value, and
    # both halves of find_duplicates key on the code, so a shared code and a
    # repeated attempt were equally invisible. check_mac had already met this
    # and worked around it by searching the whole page rather than a capture,
    # which is why it kept passing and nothing pointed at the cause.
    m = re.search(r"([0-9A-HJKMNP-TV-Z]{4}(?:-[0-9A-HJKMNP-TV-Z]{4}){3})", ex.page_text)
    res.code = m.group(1) if m else ""

    against, res.pool_source = resolve_bank(bank, p)

    check_printed_text_agrees(res, ex)
    check_mac(res, ex, mac_key)
    check_score(res, ex)
    # After check_score, which is what sets res.percent: the seal is compared
    # against the recomputed number, not against the payload's claim about it.
    check_seal(res, ex, mac_key)

    if against is None:
        # Never a REVIEW: the student did nothing. The pool they were served was
        # edited without being archived, so the evidence is simply not
        # re-derivable here. Fix the repository, not the grade.
        res.checks["drv"] = res.checks["ans"] = "?"
        res.notes.append(
            f"issued under pool {res.pool_source}; that version is not in "
            f"game/content/pools/, so the item set cannot be re-derived. "
            f"The MAC still covers this payload. Run: python tools/pool_archive.py"
        )
    else:
        pool = {
            i["id"]: {"options": i.get("options") or [], "variants": i.get("variants")}
            for i in against.get("items", [])
        }
        check_derivation(res, ex, pool, against.get("pool_version", 1))
        check_answers(res, ex, against)

    res.verdict = "REVIEW" if res.problems else "PASS"
    if res.verdict == "PASS" and res.notes:
        res.verdict = "PASS*"
    return res


def find_duplicates(results: list[Result]) -> None:
    """Two students cannot legitimately share a code or a timing vector."""
    by_code: dict[str, list[Result]] = defaultdict(list)
    for r in results:
        if r.code:
            by_code[canon_code(r.code)].append(r)
    for code, group in by_code.items():
        if len({r.andrew_id for r in group}) > 1:
            for r in group:
                r.problems.append(
                    f"verification code {code} also appears for "
                    f"{', '.join(sorted({g.andrew_id for g in group if g is not r}))}"
                )
                r.verdict = "REVIEW"

    # One student, one lecture, the same attempt number twice, two different
    # codes. Honest work cannot produce this: the attempt counter only advances,
    # so a repeated number means the counter went backwards, and the way it does
    # that is site data being cleared between two runs. Clearing storage also
    # re-serves that attempt's questions, which is the retake this design is
    # trying to make more expensive than simply answering.
    #
    # A NOTE rather than a REVIEW, and deliberately. There are innocent paths to
    # it: a student who cleared their browser, or one who genuinely lost their
    # save and redid the work. The note tells a grader where to look; it does not
    # decide anything, and nothing here is evidence of intent.
    by_attempt: dict[tuple, list[Result]] = defaultdict(list)
    for r in results:
        if r.andrew_id and r.lecture:
            by_attempt[(r.andrew_id, r.lecture, r.attempt)].append(r)
    for (aid, lec, att), group in by_attempt.items():
        if len(group) > 1 and len({canon_code(r.code) for r in group}) > 1:
            for r in group:
                r.notes.append(
                    f"{aid} submitted attempt {att} of {lec} {len(group)} times with "
                    f"different codes; the attempt counter does not repeat on its own"
                )
                if r.verdict == "PASS":
                    r.verdict = "PASS*"


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify submitted module PDFs.")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--pool", type=Path, required=True, help="game/content/lNN.yml")
    ap.add_argument("--key", help="semester MAC key; normally found automatically")
    ap.add_argument("--roster", type=Path, help="CSV with an andrew_id column")
    ap.add_argument("--csv", type=Path, help="write per-student rows here")
    args = ap.parse_args()

    mac_key, key_source = resolve_key(args.key)
    if key_source == "development fallback":
        print(
            "::warning::no semester key found, using the development key. Codes on "
            "PDFs built by CI will not match. Set GAME_MAC_KEY or write the key to "
            f"{KEY_FILE}."
        )
    else:
        print(f"key: {key_source}")

    bank = yaml.safe_load(args.pool.read_text(encoding="utf-8"))
    pdfs = sorted(args.folder.glob("*.pdf"))
    if not pdfs:
        print(f"no PDFs in {args.folder}")
        return 1

    results = [verify_one(p, bank, mac_key) for p in pdfs]
    find_duplicates(results)

    roster = set()
    if args.roster and args.roster.is_file():
        with args.roster.open() as fh:
            roster = {normalize_id(r["andrew_id"]) for r in csv.DictReader(fh) if r.get("andrew_id")}
    for r in results:
        if roster and r.andrew_id and r.andrew_id not in roster:
            r.notes.append("not on the roster")
            if r.verdict == "PASS":
                r.verdict = "PASS*"

    # `score` and `att` sit next to each other because they are read together:
    # a score means something different on a third attempt than on a first.
    head = (
        f"{'andrew_id':<12} {'name':<16} {'lec':<5} {'done':>5} {'1st':>5} "
        f"{'score':>6} {'att':>4} "
        f"{'active':>8} {'chan':<5} {'mac':<5} {'drv':<5} {'ans':<5} {'txt':<5} "
        f"{'pct':<5} {'seal':<5} verdict"
    )
    print(head)
    print("-" * len(head))
    for r in sorted(results, key=lambda x: (x.verdict != "PASS", x.andrew_id)):
        shown = f"{r.percent}%" if r.percent is not None else "-"
        print(
            f"{r.andrew_id or '?':<12} {r.name[:16]:<16} {r.lecture:<5} "
            f"{r.completed:>5} {r.first_try:>5} {shown:>6} {r.attempt:>4} "
            f"{r.active_ms / 1000:>7.0f}s "
            f"{r.channel:<5} {r.checks.get('mac', '-'):<5} {r.checks.get('drv', '-'):<5} "
            f"{r.checks.get('ans', '-'):<5} {r.checks.get('txt', '-'):<5} "
            f"{r.checks.get('pct', '-'):<5} {r.checks.get('seal', '-'):<5} {r.verdict}"
        )
        if r.pool_source != "current":
            print(f"{'':<12} pool: {r.pool_source}, the one this student was served")
        for note in r.notes:
            print(f"{'':<12} note: {note}")
        for problem in r.problems:
            print(f"{'':<12} !!   {problem}")

    tally = Counter(r.verdict for r in results)
    print("\n" + ", ".join(f"{n} {v}" for v, n in sorted(tally.items())))

    times = sorted(r.active_ms / 1000 for r in results if r.active_ms)
    if len(times) >= 5:
        def pct(p: float) -> float:
            return times[min(len(times) - 1, int(p * len(times)))]
        print(
            f"time on task (n={len(times)}): "
            f"p05 {pct(0.05):.0f}s  p50 {pct(0.5):.0f}s  p95 {pct(0.95):.0f}s"
        )
        print("Distribution printed, not judged. Do not set a threshold from one module.")

    if args.csv:
        with args.csv.open("w", newline="") as fh:
            w = csv.writer(fh)
            # `score` is the gradebook column. It is second after the id on
            # purpose: this file gets opened in a spreadsheet and the two
            # left-most useful columns are the ones that get pasted.
            w.writerow(["andrew_id", "score", "name", "lecture", "attempt",
                        "completed", "first_try", "active_s", "verdict", "problems"])
            for r in results:
                w.writerow([r.andrew_id, "" if r.percent is None else r.percent,
                            r.name, r.lecture, r.attempt, r.completed, r.first_try,
                            round(r.active_ms / 1000), r.verdict, "; ".join(r.problems)])
        print(f"wrote {args.csv}")

    # Exit 0 even with REVIEW rows: this is a triage aid for a human, not a gate.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
