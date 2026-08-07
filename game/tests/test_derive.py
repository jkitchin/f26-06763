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
