"""Text and number normalization for the quiz validator.

This module is small and boring on purpose, and it is unit-tested separately in
tests/test_normalize.py, because every gap in it shows up as the validator
failing a *correct* item. That failure mode is worse than a missed check: it
trains authors to reach for `mode: manual`, which turns the grounding rule off
exactly where it was working.

Two jobs:

  norm_text  compare a quoted span against the source file it came from, across
             MyST emphasis markers, table pipes, line wrapping and Unicode.
  norm_num   pull the numeric tokens out of a string and canonicalize them, so
             that "7.5 x 10^-8", "7.5e-8" and "0.000000075" compare equal.

The hard cases here are real ones taken from the notes: `1,263` (thousands
separator inside a table cell), `7.5 x 10^-8` written with Unicode superscript
digits and a Unicode minus, `79.9%`, `$0.63`, and `2.22 bits`.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

__all__ = ["norm_text", "norm_num", "contains_text", "strip_nums", "approx_in"]


# --- text -----------------------------------------------------------------

# MyST/Markdown emphasis and code markers. Stripped rather than escaped: an
# author copying a quote out of a table should not have to decide whether the
# bold stars around a number are part of it.
_MARKUP = re.compile(r"[*`_]+")

# Table pipes and the |---|---| separator rows.
_TABLE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$", re.MULTILINE)


def norm_text(s: str) -> str:
    """Canonical form for comparing a quote against its source.

    Collapses all whitespace *including newlines*, so a quote may span a line
    break in the source. That matters: the notes are hard-wrapped at 95 columns,
    so most sentences worth quoting cross one.
    """
    if not s:
        return ""
    # NFKC folds the Unicode superscripts and the micro sign onto ASCII-ish
    # forms, which is what makes 10^-8 comparable across the notes and the
    # figure scripts.
    s = unicodedata.normalize("NFKC", s)
    s = _TABLE.sub(" ", s)
    s = _MARKUP.sub("", s)
    s = s.replace("|", " ")
    # Unicode minus, en dash and non-breaking hyphen all read as ASCII hyphen.
    s = s.replace("−", "-").replace("–", "-").replace("‑", "-")
    s = s.replace(" ", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip().casefold()


def contains_text(haystack: str, needle: str) -> bool:
    """Is `needle` present in `haystack`, both normalized?"""
    return norm_text(needle) in norm_text(haystack)


# --- numbers ---------------------------------------------------------------

# After NFKC the superscript digits in "10⁻⁸" become ordinary digits, so
# "7.5 × 10⁻⁸" arrives here as "7.5 × 10-8". Rewrite that into 7.5e-8 before
# tokenizing, or the exponent reads as a separate number.
_SCI = re.compile(
    r"(?P<mant>\d+(?:[.,]\d+)?)\s*[x×*]\s*10\s*\^?\s*(?P<exp>[-+]?\d+)",
    re.IGNORECASE,
)

# A number, optionally with thousands separators, optionally with an exponent,
# optionally followed by a percent sign.
_NUM = re.compile(
    r"(?<![\w.])"
    r"(?P<sign>[-+]?)"
    r"(?P<int>\d{1,3}(?:,\d{3})+|\d+)"
    r"(?P<frac>\.\d+)?"
    r"(?P<exp>[eE][-+]?\d+)?"
    r"(?P<pct>\s*%)?"
)


def _canon_sci(s: str) -> str:
    return _SCI.sub(
        lambda m: f"{m.group('mant').replace(',', '')}e{int(m.group('exp'))}", s
    )


def norm_num(s: str) -> set[Decimal]:
    """Every numeric value mentioned in `s`, canonicalized.

    Percentages are divided out, so "79.9%" and "0.799" compare equal. Thousands
    separators are removed, so "1,263" is 1263 and not {1, 263}.
    """
    if not s:
        return set()
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("−", "-")
    s = _canon_sci(s)

    out: set[Decimal] = set()
    for m in _NUM.finditer(s):
        raw = f"{m.group('sign')}{m.group('int').replace(',', '')}"
        raw += m.group("frac") or ""
        raw += m.group("exp") or ""
        try:
            value = Decimal(raw)
        except InvalidOperation:  # pragma: no cover - the regex forbids this
            continue
        if m.group("pct"):
            value = value / Decimal(100)
        out.add(value.normalize())
    return out


def num_sequence(s: str) -> list[Decimal]:
    """The numeric tokens of `s`, in the order they appear.

    Ordered, unlike `norm_num`, because order carries meaning. "0.694 against
    0.532" and "0.532 against 0.694" are opposite claims built from one pair of
    values, and a duplicate check on the unordered set would call them the same
    option. That is precisely the shape of a `direction` or `rank` distractor,
    so the set-based version deleted the good items.
    """
    if not s:
        return []
    s = unicodedata.normalize("NFKC", s).replace("−", "-")
    s = _canon_sci(s)
    out: list[Decimal] = []
    for m in _NUM.finditer(s):
        raw = f"{m.group('sign')}{m.group('int').replace(',', '')}"
        raw += m.group("frac") or ""
        raw += m.group("exp") or ""
        try:
            value = Decimal(raw)
        except InvalidOperation:  # pragma: no cover
            continue
        if m.group("pct"):
            value = value / Decimal(100)
        out.append(value.normalize())
    return out


def strip_nums(s: str) -> str:
    """`norm_text` with every numeric token removed.

    This is what separates "two options that are the same option" from "two
    options that share a number but say different things". A ranking item offers
    the same three values in different orders, and a direction item offers the
    same magnitude with opposite signs; in both the numbers are identical and
    the *text* carries the answer. Comparing on numbers alone would reject both,
    which is how a hygiene rule ends up deleting the good items.
    """
    return re.sub(r"\s+", " ", _NUM.sub(" ", norm_text(s))).strip()


def approx_in(value: Decimal, pool: set[Decimal], rel: float = 0.001) -> bool:
    """Is `value` within `rel` of anything in `pool`?

    Used for the "answer's numbers appear in the source" rule, where an author
    may reasonably write 63% for a measured 62.98%.
    """
    for other in pool:
        if other == value:
            return True
        if other != 0 and abs((value - other) / other) <= Decimal(str(rel)):
            return True
    return False
