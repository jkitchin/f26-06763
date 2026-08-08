"""The hand-authored map corridors, and the checks that keep them honest.

tools/graph.py --check runs in CI and is the real guard. This pins the two
things in it that are subtle enough to regress silently.

The first is prefix collision. An edge's evidence has to name the lecture it
points at, and lecture numbers are prefixes of each other: L1 is a prefix of
L13 and L17, L2 of L20. A naive substring test would accept a quote about
surrogate models as evidence for an edge into the first week of the course, and
the resulting corridor would look exactly like the fifteen real ones.

The second is that the checks fail closed. Each of them was written after
watching it catch something, and a check that has quietly stopped firing is
worse than no check, because the file it guards keeps being trusted.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import graph  # noqa: E402

EDGES = yaml.safe_load((REPO / "game" / "content" / "map-edges.yml").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("lecture", "text", "expected"),
    [
        ("l01", "as introduced in L1", True),
        ("l01", "as introduced in L01", True),
        ("l07", "L7's Mars Climate Orbiter case", True),
        ("l09", "a harsher form than L9", True),
        ("l13", "refuse or flag rather than silently extrapolate (L7, L13)", True),
        ("l19", "L19's harness already logs everything", True),
        # The collisions. Each of these would create a corridor into the wrong
        # room, and it would look identical to a real one.
        ("l01", "the L13 surrogate", False),
        ("l01", "see L17 for RAG", False),
        ("l02", "every guardrail in L20 attaches", False),
        ("l02", "L21's bootstrap confidence interval", False),
    ],
)
def test_target_naming_survives_prefix_collision(lecture, text, expected):
    assert graph.names(lecture, text) is expected


def test_the_committed_graph_is_clean():
    """Everything in map-edges.yml holds up against the notes as they are now."""
    _, _, problems = graph.authored()
    assert problems == [], "\n".join(problems)


def test_every_edge_is_from_the_back_half():
    """These exist because extraction stops at L15. An authored edge between two
    lectures that link to each other is redundancy that will drift, and
    tools/graph.py rejects it, but the intent belongs here in writing."""
    linked = {(e["from"], e["to"]) for e in graph.scan()[0]}
    for e in EDGES["edges"]:
        assert (e["from"], e["to"]) not in linked, f"{e['from']} -> {e['to']} is already a link"


def test_l17_is_still_the_dead_end():
    """L17 cites nothing, by link or in prose. It is a true fact about the
    course and the map should show it, so an edge appearing out of L17 means
    somebody found a citation and this test should be updated deliberately."""
    out = {e["from"] for e in graph.build()["edges"]}
    assert "l17" not in out


def test_every_relation_is_documented():
    """The vocabulary is closed because the map draws each relation
    differently; an undocumented one renders as nothing."""
    assert set(EDGES["relations"]) == graph.RELATIONS
    for e in EDGES["edges"]:
        assert e["relation"] in EDGES["relations"]


def test_shutters_name_lectures_that_do_not_exist():
    written = set(graph.lectures())
    for sh in EDGES["shutters"]:
        assert sh["lecture"] not in written, f"{sh['lecture']} is written; it is a room now"
        assert sh["promised_by"] in written
