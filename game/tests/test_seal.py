"""The security seal: do both sides draw the same picture?

The seal is drawn in TypeScript (game/src/evidence/seal.ts) and read back in
Python (tools/verify_evidence.py). The Python side does not merely look for a
seal; it renders the bitmap the payload's score *should* have produced and
compares. So the two files carry the same module sizes and the same 5x7 font,
and a disagreement in either would not fail loudly: every honest PDF would come
back with the seal reporting BAD, which is the accusation bucket, aimed at
students who did nothing.

Read alongside test_derive.py's WRONG_PENALTY check, which exists for the same
reason and is written the same way: a constant duplicated across a language
boundary is checked by reading both copies, because nothing else will.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import verify_evidence as V  # noqa: E402

SEAL_TS = (ROOT / "game/src/evidence/seal.ts").read_text(encoding="utf-8")


def test_module_sizes_agree():
    for ts_name, py_value in (
        ("DIGIT_PT", V.SEAL_DIGIT_PT),
        ("MODULE_PT", V.SEAL_MODULE_PT),
        ("GRID", V.SEAL_GRID),
    ):
        m = re.search(rf"export const {ts_name} = ([\d.]+)", SEAL_TS)
        assert m, f"could not find {ts_name} in seal.ts"
        assert float(m.group(1)) == float(py_value), ts_name


def test_the_two_module_sizes_stay_distinguishable():
    """The parser separates digit modules from data modules by size alone.

    Nothing else tells them apart: both blocks are filled squares in the same
    content stream, and the seal may be laid out anywhere on the page. Bring the
    two sizes within the parser's tolerance and the two blocks merge into one
    unreadable set.
    """
    assert abs(V.SEAL_DIGIT_PT - V.SEAL_MODULE_PT) > 0.2


def test_font_tables_agree():
    ts_font = {}
    for m in re.finditer(r"'(.)': \[([^\]]+)\]", SEAL_TS):
        ts_font[m.group(1)] = tuple(int(v, 16) for v in m.group(2).split(","))
    assert ts_font, "could not parse the font out of seal.ts"
    assert ts_font == {k: tuple(v) for k, v in V.SEAL_FONT.items()}


def test_every_digit_is_distinct():
    """Two glyphs that draw the same modules would make two scores identical.

    A seal reading 68% and one reading 88% have to differ, or the check that
    reads the number back cannot tell them apart and the whole thing is
    decoration.
    """
    drawn = {ch: frozenset(V.glyph_modules(ch)) for ch in V.SEAL_FONT}
    assert len(set(drawn.values())) == len(drawn)


def test_a_changed_score_changes_the_bitmap():
    for a, b in (("95%", "99%"), ("100%", "10%"), ("0%", "8%"), ("75%", "76%")):
        assert V.at_origin(V.glyph_modules(a)) != V.at_origin(V.glyph_modules(b))


def test_a_changed_tag_changes_the_data_block():
    """One flipped bit anywhere in the tag has to move a module.

    Otherwise a seal lifted from a classmate's PDF could pass, which is the
    attack drawing the score invites in the first place.
    """
    base = bytes(range(10))
    seen = {frozenset(V.data_modules(base))}
    for i in range(10):
        for bit in range(8):
            other = bytearray(base)
            other[i] ^= 1 << bit
            got = frozenset(V.data_modules(bytes(other)))
            # Only the low 49 bits are drawn; the rest of the tag is not in the
            # picture and is not claimed to be.
            if i * 8 + bit < V.SEAL_DATA_BITS:
                assert got not in seen, f"byte {i} bit {bit} draws nothing"
                seen.add(got)


def test_the_finder_is_always_drawn():
    """The L finder gives the parser an origin, so it cannot be data-dependent."""
    for tag in (bytes(10), b"\xff" * 10, bytes(range(10))):
        drawn = V.data_modules(tag)
        assert all((0, r) in drawn for r in range(V.SEAL_GRID))
        assert all((c, V.SEAL_GRID - 1) in drawn for c in range(V.SEAL_GRID))
