"""Negative tests for the quiz validator.

A checker that only ever passes is indistinguishable from no checker. Every rule
that can fail the build gets a test here that breaks a real item in exactly that
way and asserts the specific message fires.

Run from the repository root:

    uv run --with pyyaml,pytest python -m pytest game/tests/ -q
"""

from __future__ import annotations

import copy
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

GAME = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GAME))

import validate as V  # noqa: E402


@pytest.fixture
def bank():
    """A real, loaded, passing bank. Tests mutate copies of its items."""
    b = V.validate()
    assert not [i for i in b.issues if i.level == "error"], (
        "the committed bank must be clean before negative tests mean anything"
    )
    return b


@pytest.fixture
def item():
    data = yaml.safe_load((GAME / "content" / "l15.yml").read_text(encoding="utf-8"))
    return copy.deepcopy(data["items"][0])   # l15-q01, a predict_measure


def errors_for(check, item, *args):
    b = V.Bank()
    b.objectives = V.validate().objectives
    check(b, item, "test-item", *args)
    return [i.message for i in b.issues if i.level == "error"]


# --- the load-bearing rule -------------------------------------------------

def test_committed_bank_is_clean(bank):
    assert not [i for i in bank.issues if i.level == "error"]


def test_quote_that_is_not_in_the_source_fails(item):
    item["source"]["quote"] = "| Claude Opus 5 | 1,270 | **+64%** |"
    msgs = errors_for(V.check_grounding, item)
    assert any("quote does not appear in" in m for m in msgs)


def test_needle_outside_the_quote_fails(item):
    item["verify"]["needle"] = "924"          # true in the notes, not in this quote
    msgs = errors_for(V.check_grounding, item)
    assert any("is not inside the quoted span" in m for m in msgs)


def test_answer_number_absent_from_source_fails(item):
    item["answer"] = "4,096 tokens, about 428% more than the local count"
    item["options"] = item["options"] + [item["answer"]]
    msgs = errors_for(V.check_grounding, item)
    assert any("does not appear anywhere in" in m for m in msgs)


def test_heading_that_does_not_exist_fails(item):
    item["source"]["heading"] = "Count, don't estimate"
    msgs = errors_for(V.check_grounding, item)
    assert any("does not exist in" in m for m in msgs)


def test_missing_source_file_fails(item):
    item["source"]["file"] = "lectures/l99/notes.md"
    msgs = errors_for(V.check_grounding, item)
    assert any("does not exist" in m for m in msgs)


# --- privacy: the non-negotiable one ---------------------------------------

def test_citing_instructor_only_material_fails(item):
    item["source"]["file"] = "course/modules/wk09.md"
    msgs = errors_for(V.check_grounding, item)
    assert any("instructor-only" in m for m in msgs)


def test_citing_a_solutions_path_fails(item):
    item["source"]["file"] = "course/solutions/a08.md"
    msgs = errors_for(V.check_grounding, item)
    assert any("solution material" in m for m in msgs)


def test_citing_an_unpublished_page_fails(item):
    # CLAUDE.md is real and readable but is not in _toc.yml, so a student
    # following the citation would 404.
    item["source"]["file"] = "CLAUDE.md"
    item["source"]["quote"] = "the contract for how lecture material is structured"
    item["verify"]["needle"] = "contract"
    msgs = errors_for(V.check_grounding, item)
    assert any("not listed in _toc.yml" in m for m in msgs)


# --- MCQ hygiene -----------------------------------------------------------

def test_duplicate_options_fail(item):
    item["options"][1] = item["options"][0]
    msgs = errors_for(V.check_choices, item)
    assert any("identical after normalization" in m for m in msgs)


def test_near_duplicate_option_is_rejected(item):
    """Trailing punctuation is not a distractor. Containment is what catches it."""
    item["options"][1] = "1,263, about 63% more than the local count."
    msgs = errors_for(V.check_choices, item)
    assert msgs, "a near-duplicate option must be rejected by some rule"
    assert any("contained in" in m for m in msgs)


def test_formatting_variant_of_the_same_number_fails(item):
    """The one case only the numeric rule catches: same value, different spelling."""
    item["options"] = ["1,263 tokens", "1263 tokens", "924 tokens", "776 tokens"]
    item["answer"] = "1,263 tokens"
    msgs = errors_for(V.check_choices, item)
    assert any("same option twice" in m for m in msgs)


def test_same_values_in_a_different_order_are_distinct(item):
    """The false positive that made the rule order-sensitive.

    Two options built from one pair of values but asserting opposite orderings
    are opposite claims, not one option written twice.
    """
    item["options"] = [
        "0.694 against 0.532",
        "0.532 against 0.694",
        "0.971 against 0.361",
    ]
    item["answer"] = "0.694 against 0.532"
    msgs = errors_for(V.check_choices, item)
    assert not any("same option twice" in m for m in msgs)


def test_option_contained_in_another_fails(item):
    item["options"][1] = "1,263"
    msgs = errors_for(V.check_choices, item)
    assert any("contained in" in m for m in msgs)


def test_answer_not_among_options_fails(item):
    item["answer"] = "something else entirely"
    msgs = errors_for(V.check_choices, item)
    assert any("not one of the options" in m for m in msgs)


def test_too_few_options_fails(item):
    item["options"] = item["options"][:2]
    msgs = errors_for(V.check_choices, item)
    assert any("at least 3 options" in m for m in msgs)


def test_predict_measure_without_common_prior_fails(item):
    del item["predict"]["common_prior"]
    msgs = errors_for(V.check_choices, item)
    assert any("common_prior" in m for m in msgs)


def test_rank_permutations_are_not_flagged_as_duplicates():
    """The regression this rule was loosened for.

    A ranking item offers the same values in different orders. Comparing on
    numbers alone rejected every one of them.
    """
    data = yaml.safe_load((GAME / "content" / "l15.yml").read_text(encoding="utf-8"))
    rank = next(i for i in data["items"] if i["kind"] == "rank")
    assert not errors_for(V.check_choices, rank)


def test_direction_options_sharing_a_magnitude_are_not_flagged():
    data = yaml.safe_load((GAME / "content" / "l15.yml").read_text(encoding="utf-8"))
    nb = next(i for i in data["items"] if i["id"] == "l15-q12")
    assert not errors_for(V.check_choices, nb)


# --- volatility ------------------------------------------------------------

def test_measured_value_asked_exactly_fails(item):
    item["kind"] = "numeric_band"
    item["verify"]["volatility"] = "measured"
    item["verify"].pop("expires", None)
    msgs = errors_for(V.check_volatility, item)
    assert any("exact measured value" in m for m in msgs)


def test_mcq_whose_options_differ_only_by_number_fails(item):
    item["kind"] = "mcq"
    item["verify"]["volatility"] = "measured"
    item["verify"].pop("expires", None)
    item["options"] = ["776 tokens", "924 tokens", "1,263 tokens", "1,270 tokens"]
    item["answer"] = "1,263 tokens"
    msgs = errors_for(V.check_volatility, item)
    assert any("exact measured value" in m for m in msgs)


def test_figure_script_number_declared_stable_fails(item):
    item["source"]["file"] = "lectures/l15/figures/make_figures.py"
    item["verify"]["volatility"] = "stable"
    msgs = errors_for(V.check_volatility, item)
    assert any("measured on the author's machine" in m for m in msgs)


def test_dated_without_expiry_fails(item):
    item["verify"]["volatility"] = "dated"
    item["verify"].pop("expires", None)
    msgs = errors_for(V.check_volatility, item)
    assert any("expires" in m for m in msgs)


def test_expired_item_fails(item):
    item["verify"]["volatility"] = "dated"
    item["verify"]["expires"] = date.today() - timedelta(days=1)
    msgs = errors_for(V.check_volatility, item)
    assert any("expired on" in m for m in msgs)


# --- shape -----------------------------------------------------------------

def test_unknown_kind_fails(item):
    item["kind"] = "predict_reveal"
    msgs = errors_for(V.check_shape, item)
    assert any("unknown kind" in m for m in msgs)


def test_rung_off_the_ladder_fails(item):
    item["rung"] = 8
    msgs = errors_for(V.check_shape, item)
    assert any("not on the ladder" in m for m in msgs)


def test_empty_evidence_fails(item):
    item["evidence"] = "   "
    msgs = errors_for(V.check_shape, item)
    assert any("evidence is empty" in m for m in msgs)


def test_manual_mode_without_a_reason_fails(item):
    item["verify"]["mode"] = "manual"
    item["verify"].pop("exempt_reason", None)
    msgs = errors_for(V.check_shape, item)
    assert any("exempt_reason" in m for m in msgs)


# --- objectives ------------------------------------------------------------

def test_unknown_objective_fails(item, bank):
    item["objectives"] = ["l15-o9"]
    b = V.Bank()
    b.objectives = bank.objectives
    V.check_objectives(b, item, "test-item", "l15")
    assert any("unknown objective" in i.message for i in b.issues)


def test_objective_from_another_lecture_fails(item, bank):
    b = V.Bank()
    b.objectives = dict(bank.objectives)
    b.objectives["l11-o1"] = {"id": "l11-o1", "lecture": "l11", "text": "x"}
    item["objectives"] = ["l11-o1"]
    V.check_objectives(b, item, "test-item", "l15")
    assert any("belongs to lecture" in i.message for i in b.issues)


def test_objective_text_must_still_match_the_notes(bank):
    b = V.Bank()
    b.objectives = {
        "l15-o1": {
            "id": "l15-o1",
            "lecture": "l15",
            "text": "Build a mental model of an encoder-only LLM.",   # wrong
        }
    }
    V.check_objectives_match_notes(b)
    assert any("no longer matches" in i.message for i in b.issues)
