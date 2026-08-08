"""The pool archive: does a PDF stay verifiable after its bank is edited?

The property under test is narrow and load-bearing. `verify_evidence.py` proves
a student's item set by re-deriving it, and item selection is a function of the
whole pool, so adding one item to a bank changes what every student is served.
The archive is what lets a week-3 PDF be checked in week 9. If the archived
snapshot is missing anything `derive()` reads, the archive looks fine, the CI
check passes, and honest evidence fails at grading time.

So the central test is not that the archive round-trips as JSON. It is that
deriving from the archived snapshot produces the same list, item for item,
variant for variant, option order for option order, as deriving from the live
YAML. That is checked across all fourteen banks rather than on a fixture,
because the thing most likely to break it is a field somebody adds to one bank.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from derive import derive  # noqa: E402
import pool_archive  # noqa: E402
import verify_evidence  # noqa: E402


def banks():
    for p in sorted((REPO / "game" / "content").glob("l*.yml")):
        yield yaml.safe_load(p.read_text(encoding="utf-8"))


def pool_of(bank: dict) -> dict:
    """The pool shape verify_evidence.py builds, from a bank-shaped dict."""
    return {
        i["id"]: {"options": i.get("options") or [], "variants": i.get("variants")}
        for i in bank.get("items", [])
    }


ALL = list(banks())
IDS = [b["lecture"] for b in ALL]


@pytest.mark.parametrize("bank", ALL, ids=IDS)
def test_archive_derives_identically_to_the_live_bank(bank):
    """The whole point. A missing field here is invisible until grading."""
    lecture, version = bank["lecture"], bank.get("pool_version", 1)
    arch = verify_evidence.archived_bank(lecture, version)
    assert arch is not None, f"{lecture} v{version} is not archived"

    # Several ids, because selection is seeded per student and a surface can be
    # wrong in a way one draw happens not to touch.
    for andrew in ("jkitchin", "valves", "aa", "zzzz9"):
        live = derive(andrew, lecture, pool_of(bank), version, bank["serve"])
        kept = derive(andrew, lecture, pool_of(arch), version, bank["serve"])
        assert live == kept, f"{lecture}: {andrew} derives differently from the archive"


@pytest.mark.parametrize("bank", ALL, ids=IDS)
def test_archive_carries_the_answer_key(bank):
    """check_answers regrades from the pool, so the archive needs answers too."""
    arch = verify_evidence.archived_bank(bank["lecture"], bank.get("pool_version", 1))
    by_id = {i["id"]: i for i in arch["items"]}
    for item in bank["items"]:
        got = by_id[item["id"]]
        if item.get("options"):
            # Order matters and is not incidental: a recorded choice is an index
            # into the original pool order, which is what keeps a shuffled
            # answer checkable at all.
            assert got["options"] == list(item["options"]), item["id"]
        else:
            assert "options" not in got, f"{item['id']} is free response"
        assert got.get("answer") == item.get("answer"), item["id"]


def test_check_passes_on_the_committed_state():
    r = subprocess.run([sys.executable, str(REPO / "tools" / "pool_archive.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_surface_ignores_everything_verification_does_not_read():
    """Prompts and provenance are excluded on purpose: the diff has to stay
    readable, because reviewing it is the only guard on rewriting history."""
    s = pool_archive.surface({
        "serve": 2,
        "items": [{
            "id": "x", "options": ["a", "b"], "answer": "a",
            "prompt": "long text", "evidence": "more", "source": {"file": "..."},
        }],
    })
    assert s == {"serve": 2, "items": {"x": {"options": ["a", "b"], "answer": "a"}}}


def test_surface_keeps_variants():
    s = pool_archive.surface({
        "serve": 1,
        "items": [{"id": "x", "answer": "a",
                   "variants": [{"id": "v1", "options": ["a", "b"]}, {"id": "v2"}]}],
    })
    assert s["items"]["x"]["variants"] == [{"id": "v1", "options": ["a", "b"]}, {"id": "v2"}]


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A throwaway content tree, so drift tests never touch the real banks."""
    content = tmp_path / "content"
    content.mkdir()
    bank = {
        "lecture": "l99", "pool_version": 1, "serve": 2,
        "items": [{"id": f"l99-q{n:02d}", "options": ["a", "b"], "answer": "a"}
                  for n in range(1, 5)],
    }
    (content / "l99.yml").write_text(yaml.safe_dump(bank), encoding="utf-8")
    monkeypatch.setattr(pool_archive, "CONTENT", content)
    monkeypatch.setattr(pool_archive, "POOLS", content / "pools")
    return content, bank


def test_drift_without_a_bump_is_caught(sandbox):
    content, bank = sandbox
    assert pool_archive.write() == 0
    problems, _ = pool_archive.status()
    assert problems == []

    grown = copy.deepcopy(bank)
    grown["items"].append({"id": "l99-q05", "options": ["a", "b"], "answer": "b"})
    (content / "l99.yml").write_text(yaml.safe_dump(grown), encoding="utf-8")

    problems, _ = pool_archive.status()
    assert len(problems) == 1
    assert "stayed at 1" in problems[0] and "l99-q05" in problems[0]


def test_a_bump_resolves_it_and_keeps_the_old_version(sandbox):
    content, bank = sandbox
    pool_archive.write()

    grown = copy.deepcopy(bank)
    grown["pool_version"] = 2
    grown["items"].append({"id": "l99-q05", "options": ["a", "b"], "answer": "b"})
    (content / "l99.yml").write_text(yaml.safe_dump(grown), encoding="utf-8")

    assert pool_archive.write() == 0
    assert pool_archive.status()[0] == []
    arch = json.loads((content / "pools" / "l99.json").read_text())
    assert sorted(arch["versions"]) == ["1", "2"]
    assert len(arch["versions"]["1"]["items"]) == 4, "v1 must survive the bump untouched"
    assert len(arch["versions"]["2"]["items"]) == 5


def test_write_refuses_to_overwrite_an_archived_version(sandbox):
    """The one operation that silently invalidates PDFs already in hand."""
    content, bank = sandbox
    pool_archive.write()

    edited = copy.deepcopy(bank)
    edited["items"][0]["answer"] = "b"           # same version, different key
    (content / "l99.yml").write_text(yaml.safe_dump(edited), encoding="utf-8")

    assert pool_archive.write() == 1
    arch = json.loads((content / "pools" / "l99.json").read_text())
    assert arch["versions"]["1"]["items"]["l99-q01"]["answer"] == "a"


def test_write_is_deterministic_and_idempotent(sandbox):
    """--check regenerates rather than trusts, so a timestamp would break it."""
    content, _ = sandbox
    pool_archive.write()
    once = (content / "pools" / "l99.json").read_text()
    pool_archive.write()
    assert (content / "pools" / "l99.json").read_text() == once


def test_the_archive_is_not_shipped_to_students():
    """It is only ever read by the Python verifier. The app globs
    `../../content/l*.yml`, so a .json under content/pools/ is not bundled, and
    students do not download every retired version of every bank."""
    glob = (REPO / "game" / "src" / "content" / "load.ts").read_text(encoding="utf-8")
    assert "'../../content/l*.yml'" in glob
    for p in (REPO / "game" / "content" / "pools").glob("*"):
        assert p.suffix == ".json", f"{p.name} would be picked up by the bank glob"
