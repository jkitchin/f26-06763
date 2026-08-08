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

SCHEMA = "cmu-06763-attest/1"
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
    error: str = ""


def extract(path: Path) -> Extract:
    """Pull the attestation out, trying the sturdier channel first."""
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        sys.exit("pypdf is required: pip install pypdf")

    out = Extract()
    try:
        reader = PdfReader(str(path))
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
        if isinstance(payload, dict) and payload.get("schema") == SCHEMA:
            out.payload_bytes, out.payload, out.channel = raw, payload, channel
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
    session = p.get("session", {})
    res.active_ms = session.get("active_ms", 0)
    res.elapsed_ms = session.get("elapsed_ms", 0)

    # The code is printed on page 1; read it from there, since that is the thing
    # a tamperer would have had to keep consistent.
    m = re.search(r"\b([0-9A-HJKMNP-TV-Z]{4}(?:-[0-9A-HJKMNP-TV-Z]{4}){3})\b", ex.page_text)
    res.code = m.group(1) if m else ""

    against, res.pool_source = resolve_bank(bank, p)

    check_printed_text_agrees(res, ex)
    check_mac(res, ex, mac_key)

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

    head = (
        f"{'andrew_id':<12} {'name':<16} {'lec':<5} {'done':>5} {'1st':>5} "
        f"{'active':>8} {'chan':<5} {'mac':<5} {'drv':<5} {'ans':<5} {'txt':<5} verdict"
    )
    print(head)
    print("-" * len(head))
    for r in sorted(results, key=lambda x: (x.verdict != "PASS", x.andrew_id)):
        print(
            f"{r.andrew_id or '?':<12} {r.name[:16]:<16} {r.lecture:<5} "
            f"{r.completed:>5} {r.first_try:>5} {r.active_ms / 1000:>7.0f}s "
            f"{r.channel:<5} {r.checks.get('mac', '-'):<5} {r.checks.get('drv', '-'):<5} "
            f"{r.checks.get('ans', '-'):<5} {r.checks.get('txt', '-'):<5} {r.verdict}"
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
            w.writerow(["andrew_id", "name", "lecture", "completed", "first_try",
                        "active_s", "verdict", "problems"])
            for r in results:
                w.writerow([r.andrew_id, r.name, r.lecture, r.completed, r.first_try,
                            round(r.active_ms / 1000), r.verdict, "; ".join(r.problems)])
        print(f"wrote {args.csv}")

    # Exit 0 even with REVIEW rows: this is a triage aid for a human, not a gate.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
