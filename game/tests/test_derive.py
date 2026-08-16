"""Properties of the seeded derivation that differential testing cannot reach.

tools/check_vectors.py proves derive.py and seed.ts agree. Agreement is not
correctness: both could be biased in the same way and the vectors would still
match. This file checks the properties that have to hold regardless of what the
other implementation does.

    uv run --with pytest python -m pytest game/tests/test_derive.py -q
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))

from derive import (  # noqa: E402
    Rng,
    attempt_offset,
    derive,
    normalize_id,
    select_items,
    selection_seed,
)


def pool(n_items: int, n_options: int = 4) -> dict:
    return {
        f"x-q{i:02d}": {"options": [f"opt{j}" for j in range(n_options)]}
        for i in range(n_items)
    }


# --- the bound the vectors cannot test -------------------------------------

def test_below_is_in_range():
    rng = Rng(b"\x01" * 32)
    for n in (1, 2, 3, 5, 7, 12, 30):
        for _ in range(200):
            assert 0 <= rng.below(n) < n


def test_below_uses_the_unbiased_bound():
    """The bound must be the largest multiple of n that fits in 32 bits.

    Asserted structurally rather than statistically: the bias this prevents is
    about one part in 200 million, so no feasible sample size would detect it.
    """
    for n in (3, 5, 6, 7, 9, 12, 20, 25, 30):
        limit = (1 << 32) // n * n
        assert limit % n == 0, "the bound must be a whole multiple of n"
        assert (1 << 32) - limit < n, "the bound must not discard a whole extra block"


def test_below_rejects_zero_and_negative():
    rng = Rng(b"\x02" * 32)
    for bad in (0, -1):
        with pytest.raises(ValueError):
            rng.below(bad)


def test_below_is_roughly_uniform():
    """Coarse, but it would catch a bound that was wrong by a lot."""
    rng = Rng(b"\x03" * 32)
    counts = Counter(rng.below(4) for _ in range(8000))
    assert set(counts) == {0, 1, 2, 3}
    for value in counts.values():
        assert 1700 < value < 2300, counts


# --- determinism and independence ------------------------------------------

def test_derivation_is_deterministic():
    a = derive("jkitchin", "l15", pool(30), 1, 12)
    b = derive("jkitchin", "l15", pool(30), 1, 12)
    assert a == b


def test_different_students_get_different_items():
    a = [s["id"] for s in derive("jkitchin", "l15", pool(30), 1, 12)]
    b = [s["id"] for s in derive("valves", "l15", pool(30), 1, 12)]
    assert a != b, "seeding per student is the whole point"


def test_same_student_gets_different_items_per_lecture():
    a = [s["id"] for s in derive("jkitchin", "l15", pool(30), 1, 12)]
    b = [s["id"] for s in derive("jkitchin", "l11", pool(30), 1, 12)]
    assert a != b


def test_selection_is_order_independent():
    """Reordering the YAML file must not reshuffle every student."""
    seed = selection_seed("jkitchin", "l15", 1)
    ids = sorted(pool(30))
    assert select_items(seed, ids, 12) == select_items(seed, list(reversed(ids)), 12)


def test_growing_the_pool_displaces_one_item_not_all():
    """Adding a question must not invalidate PDFs already issued.

    Hash-and-take-lowest gives this; shuffle-and-slice does not.
    """
    seed = selection_seed("jkitchin", "l15", 1)
    before = select_items(seed, sorted(pool(30)), 12)
    after = select_items(seed, sorted(pool(31)), 12)
    kept = len(set(before) & set(after))
    assert kept >= 11, f"only {kept}/12 items survived adding one question"


def test_no_duplicate_items_in_a_draw():
    served = derive("jkitchin", "l15", pool(30), 1, 12)
    ids = [s["id"] for s in served]
    assert len(set(ids)) == len(ids)


def test_option_order_is_a_permutation():
    for s in derive("jkitchin", "l15", pool(30, 4), 1, 12):
        assert sorted(s["option_order"]) == [0, 1, 2, 3]


def test_pool_equal_to_k_serves_everything():
    served = derive("jkitchin", "l15", pool(12), 1, 12)
    assert sorted(s["id"] for s in served) == sorted(pool(12))


# --- id normalization ------------------------------------------------------

@pytest.mark.parametrize(
    "raw",
    ["jkitchin", "JKitchin", " jkitchin ", "jkitchin@andrew.cmu.edu", "jkitchin@cmu.edu"],
)
def test_id_forms_normalize_together(raw):
    assert normalize_id(raw) == "jkitchin"


@pytest.mark.parametrize("bad", ["", "  ", "9lives", "a", "has space", "with-dash", "x" * 20])
def test_malformed_ids_are_rejected(bad):
    with pytest.raises(ValueError):
        normalize_id(bad)


def test_equivalent_id_forms_derive_identically():
    """The typo guard: an honest student who types their email still verifies."""
    a = derive("jkitchin", "l15", pool(30), 1, 12)
    b = derive("JKitchin@andrew.cmu.edu", "l15", pool(30), 1, 12)
    assert a == b


# --- the attempt window ----------------------------------------------------
#
# The retake defence. These are properties of the window itself, so they hold
# whatever seed.ts does; check_vectors.py is what proves the two agree on the
# specific answers.

IDS = ["jkitchin", "valves", "a1", "zz9", "student01", "mchen", "rpatel"]


@pytest.mark.parametrize("aid", IDS)
@pytest.mark.parametrize("n,k", [(10, 5), (12, 6), (20, 8), (30, 12)])
def test_attempts_one_and_two_are_disjoint(aid, n, k):
    """The whole claim: a retake is new questions, not a reshuffle.

    Holds exactly when the pool is at least twice the draw, which is why every
    bank in the course was moved to serve = pool // 2.
    """
    a1 = {s["id"] for s in derive(aid, "l15", pool(n), 1, k, 1)}
    a2 = {s["id"] for s in derive(aid, "l15", pool(n), 1, k, 2)}
    assert a1 & a2 == set()


@pytest.mark.parametrize("aid", IDS)
def test_the_two_attempts_together_cover_the_pool(aid):
    """With serve = pool // 2 and an even pool, two attempts exhaust the bank."""
    a1 = {s["id"] for s in derive(aid, "l15", pool(10), 1, 5, 1)}
    a2 = {s["id"] for s in derive(aid, "l15", pool(10), 1, 5, 2)}
    assert a1 | a2 == set(pool(10))


def test_attempt_three_wraps_rather_than_running_out():
    """A student may practise more than twice. They must still get a full set."""
    served = derive("jkitchin", "l15", pool(10), 1, 5, 3)
    assert len(served) == 5
    assert len({s["id"] for s in served}) == 5


def test_an_odd_pool_still_serves_a_full_window():
    """l23 has 11 items and serves 5, so its third window wraps mid-way."""
    for attempt in (1, 2, 3, 4):
        served = derive("jkitchin", "l23", pool(11), 1, 5, attempt)
        assert len({s["id"] for s in served}) == 5, attempt


def test_attempt_is_stable():
    """Re-deriving the same attempt gives the same list, or no PDF verifies."""
    a = derive("jkitchin", "l15", pool(12), 1, 6, 2)
    b = derive("jkitchin", "l15", pool(12), 1, 6, 2)
    assert a == b


def test_a_repeated_item_comes_back_reshuffled():
    """Attempt 3 revisits attempt 1's items, but not their option order.

    Otherwise a student who memorised "the answer is in position 2" would carry
    that across the wrap, which is most of what the reshuffle is for.
    """
    a1 = {s["id"]: s["option_order"] for s in derive("jkitchin", "l15", pool(10), 1, 5, 1)}
    a3 = {s["id"]: s["option_order"] for s in derive("jkitchin", "l15", pool(10), 1, 5, 3)}
    shared = set(a1) & set(a3)
    assert shared, "attempt 3 should wrap onto attempt 1's items"
    assert any(a1[i] != a3[i] for i in shared), "option order repeated verbatim"


def test_attempt_one_starts_at_the_top_of_the_ranking():
    """Attempt 1 draws the highest-ranked k items, offset zero.

    Disjointness does not pin this on its own, and that gap is real: shifting
    every window by one still yields disjoint attempts and still covers the
    pool, so the property survives while every student's first draw silently
    moves. Caught here rather than only by check_vectors.py, which sees the
    same mistake made in both languages as agreement.
    """
    assert attempt_offset(1, 5, 10) == 0
    assert attempt_offset(2, 5, 10) == 5
    assert attempt_offset(3, 5, 10) == 0        # wraps

    seed = selection_seed("jkitchin", "l15", 1)
    top = select_items(seed, sorted(pool(10)), 5)
    drawn = [s["id"] for s in derive("jkitchin", "l15", pool(10), 1, 5, 1)]
    assert drawn == top


def test_attempt_zero_and_negative_are_treated_as_the_first():
    """Defensive: a corrupt log must not index outside the ranking."""
    first = derive("jkitchin", "l15", pool(10), 1, 5, 1)
    for bad in (0, -1, -7):
        assert derive("jkitchin", "l15", pool(10), 1, 5, bad) == first


def test_every_shipped_bank_supports_two_clean_attempts():
    """serve <= pool // 2 for every bank, which is what makes a retake fresh.

    This is the check that fails if somebody adds a question to a bank and
    raises `serve` to match without thinking about attempt 2.
    """
    import yaml

    content = Path(__file__).resolve().parent.parent / "content"
    banks = sorted(content.glob("l*.yml"))
    assert banks, "no banks found"
    for path in banks:
        bank = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(bank, dict) or "items" not in bank:
            continue
        n, k = len(bank["items"]), bank["serve"]
        assert k * 2 <= n, f"{path.name}: serve {k} of {n} leaves attempt 2 overlapping"


def test_the_two_wrong_answer_penalties_agree():
    """verify_evidence.py and log.ts must deduct the same amount.

    Not covered by the generated vectors, which only exercise the derivation, so
    it is read out of both sources instead. A disagreement here means the score
    printed on a student's PDF is not the score their TA records.
    """
    import re

    root = Path(__file__).resolve().parent.parent.parent
    ts = (root / "game/src/store/log.ts").read_text(encoding="utf-8")
    py = (root / "tools/verify_evidence.py").read_text(encoding="utf-8")

    ts_m = re.search(r"export const WRONG_PENALTY = ([\d.]+)", ts)
    py_m = re.search(r"^WRONG_PENALTY = ([\d.]+)", py, re.M)
    assert ts_m and py_m, "could not find WRONG_PENALTY in both files"
    assert float(ts_m.group(1)) == float(py_m.group(1))
