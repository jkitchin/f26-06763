"""Unit tests for the normalizer.

Every case here is taken from real text in the repository, because the failure
mode that matters is not "the normalizer is wrong in principle" but "the
normalizer chokes on how these particular notes are written, so the validator
rejects a correct item and the author reaches for mode: manual".
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from normalize import (  # noqa: E402
    norm_num,
    norm_text,
    num_sequence,
    strip_nums,
)


# --- text ------------------------------------------------------------------

def test_bold_markers_are_ignored():
    assert norm_text("Entropy rises to **2.22 bits**.") == norm_text("Entropy rises to 2.22 bits.")


def test_backticks_are_ignored():
    assert norm_text("`cl100k_base` (OpenAI)") == norm_text("cl100k_base (OpenAI)")


def test_table_pipes_do_not_block_a_match():
    row = "| Claude Opus 5 | 1,263 | **+63%** |"
    assert "claude opus 5" in norm_text(row)
    assert "1,263" in norm_text(row)


def test_a_quote_may_span_a_hard_wrap():
    """The notes wrap at ~95 columns, so most quotable sentences cross a line."""
    source = "one output token costs about as much wall-clock time as a thousand input\ntokens."
    quote = "as much wall-clock time as a thousand input tokens"
    assert norm_text(quote) in norm_text(source)


def test_unicode_superscripts_fold_onto_ascii():
    assert norm_text("7.5 × 10⁻⁸") == norm_text("7.5 × 10-8")


def test_unicode_minus_matches_ascii_hyphen():
    assert norm_text("−8") == norm_text("-8")


def test_case_is_ignored():
    assert norm_text("NOT FOUND") == norm_text("not found")


# --- numbers ---------------------------------------------------------------

def test_thousands_separator_is_one_number_not_two():
    assert norm_num("1,263") == {Decimal("1263")}


def test_percentages_are_divided_out():
    assert norm_num("79.9%") == norm_num("0.799")


def test_scientific_notation_forms_agree():
    assert norm_num("7.5 × 10⁻⁸") == norm_num("7.5e-8")


def test_currency_is_just_the_number():
    assert norm_num("$0.63") == {Decimal("0.63")}


def test_units_do_not_confuse_the_value():
    assert norm_num("2.22 bits") == {Decimal("2.22")}


def test_multiple_numbers_are_all_found():
    assert norm_num("776 tokens, 924 tokens, 1,263 tokens") == {
        Decimal("776"), Decimal("924"), Decimal("1263"),
    }


def test_version_like_strings_do_not_explode():
    # "Claude Haiku 4.5" is one number, not two.
    assert norm_num("Claude Haiku 4.5") == {Decimal("4.5")}


# --- ordering and stripping ------------------------------------------------

def test_num_sequence_preserves_order():
    assert num_sequence("0.694 against 0.532") == [Decimal("0.694"), Decimal("0.532")]
    assert num_sequence("0.532 against 0.694") == [Decimal("0.532"), Decimal("0.694")]


def test_num_sequence_distinguishes_orderings_that_norm_num_conflates():
    a, b = "0.694 against 0.532", "0.532 against 0.694"
    assert norm_num(a) == norm_num(b)          # the set is the same...
    assert num_sequence(a) != num_sequence(b)  # ...the claim is not


def test_strip_nums_leaves_the_words():
    assert strip_nums("1,263, about 63% more than the local count").endswith("more than the local count")
    assert not any(ch.isdigit() for ch in strip_nums("776 tokens and 1,263 tokens"))


def test_strip_nums_separates_direction_options():
    """The regression: these share a magnitude but say opposite things."""
    less = "The datasheet is less dense: more characters per token than prose, by about 1.6x"
    more = "The datasheet is more dense: fewer characters per token than prose, by about 1.6x"
    assert norm_num(less) == norm_num(more)
    assert strip_nums(less) != strip_nums(more)
