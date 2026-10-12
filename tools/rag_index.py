#!/usr/bin/env python3
"""Chunk the released lecture notes and slides for the L18 "chat with the course" capstone.

    python tools/rag_index.py                      # released lectures -> chat/build/chunks.json
    python tools/rag_index.py --lectures l01-l17   # an explicit range, for local testing
    python tools/rag_index.py --stats              # print counts and sizes, write nothing
    python tools/rag_index.py --lectures l01-l17 --notes-only --out lectures/l18/data/notes-l01-l17.json
                                                   # the frozen snapshot the L18 notebook measures

Then `node chat/embed.mjs` adds one embedding per chunk, with the same model and settings the
browser uses to embed a query, and writes chat/build/rag-index.json. CI runs both at deploy time
and copies the result beside the L18 deck, so nothing here is committed: the index always
matches whatever is released, and a release cannot leave it stale.

WHAT IS INDEXED, and why it is safe. Only lectures released in _toc.yml (the same rule
tools/world.py uses), and for each only `notes.md` and `slides.md`. Never course/modules/,
never solutions, never an unreleased lecture. That keeps the instructor-only material out by
construction, and it also keeps the course's no-forward-reference rule: the chat cannot know
about a lecture that is not out yet.

CHUNKING. Notes are split at H2 and H3 headings, which is where the notes put one idea each, and
any section longer than MAX_WORDS is split again at paragraph boundaries with the heading
repeated, so a chunk always says what it is about. Slides are split at `---`, one chunk per
slide, keeping the slide number so a citation can link straight to it. MyST directives that carry
no prose (index entries, figure options, raw HTML, MARP comments) are removed; equations and code
stay, because "zero_grad" and "k1" are exactly what keyword search is for.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOC = REPO / "_toc.yml"
OUT = REPO / "chat" / "build" / "chunks.json"
SITE = "https://kitchingroup.cheme.cmu.edu/f26-06763"

# A chunk of 350 words is about 450 tokens. The embedding model truncates its input at 256 word
# pieces, so it sees roughly the first 200 words of a full chunk; keyword search sees all of it.
# Repeating the heading at the top of every piece is what keeps a truncated embedding on topic.
MAX_WORDS = 350
MIN_WORDS = 25


def released_ids() -> list[str]:
    """Lecture ids released in _toc.yml: uncommented `- file: lectures/lNN/notes` entries."""
    text = TOC.read_text(encoding="utf-8")
    return sorted(set(re.findall(r"^\s*-\s*file:\s*lectures/(l\d\d)/notes\b", text, re.M)))


def parse_range(spec: str) -> list[str]:
    a, b = spec.split("-")
    return [f"l{i:02d}" for i in range(int(a[1:]), int(b[1:]) + 1)]


def clean_markdown(text: str) -> str:
    """Strip the markup that carries no prose; keep equations, code and table text."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)                     # comments, speaker notes
    text = re.sub(r"^```\{index\}.*?\n```", " ", text, flags=re.M | re.S)  # index entries
    text = re.sub(r"^```\{figure\}\s*(\S+)\n(?::[^\n]*\n)*", " ", text, flags=re.M)  # figure head
    text = re.sub(r"^:::\{admonition\}\s*(.*)$", r"\1", text, flags=re.M)   # keep the box title
    text = re.sub(r"^:class:.*$|^:::$|^```$", " ", text, flags=re.M)
    text = re.sub(r"<style>.*?</style>|<script.*?</script>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)                                    # raw HTML tags
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)                       # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)                    # links -> link text
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def slugify(heading: str) -> str:
    """Sphinx's anchor for a heading, near enough for a link (lowercase, hyphens)."""
    s = re.sub(r"[^\w\s-]", "", heading.lower())
    return re.sub(r"[\s_]+", "-", s).strip("-")


def split_long(words_text: str) -> list[str]:
    """Split a long section at paragraph boundaries into pieces of at most MAX_WORDS."""
    paras = [p for p in words_text.split("\n\n") if p.strip()]
    out, cur, n = [], [], 0
    for p in paras:
        w = len(p.split())
        if cur and n + w > MAX_WORDS:
            out.append("\n\n".join(cur))
            cur, n = [], 0
        cur.append(p)
        n += w
    if cur:
        out.append("\n\n".join(cur))
    return out


def chunk_notes(lid: str) -> list[dict]:
    path = REPO / "lectures" / lid / "notes.md"
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8")
    title = re.search(r"^#\s+(.+)$", raw, re.M).group(1).strip()
    parts = re.split(r"^(#{2,3})\s+(.+)$", raw, flags=re.M)
    chunks = []
    # parts = [preamble, level, heading, body, level, heading, body, ...]
    h2 = None
    for i in range(1, len(parts), 3):
        level, heading, body = parts[i], parts[i + 1].strip(), parts[i + 2]
        if level == "##":
            h2 = heading
        if heading in {"Resources", "Assignment", "Practice module", "Learning objectives"}:
            continue
        section = heading if level == "##" else f"{h2} / {heading}"
        text = clean_markdown(body)
        for k, piece in enumerate(split_long(text)):
            if len(piece.split()) < MIN_WORDS:
                continue
            chunks.append({
                "id": f"{lid}-n-{slugify(heading)}" + (f"-{k + 1}" if k else ""),
                "lecture": lid, "kind": "notes", "title": title, "section": section,
                "url": f"{SITE}/lectures/{lid}/notes.html#{slugify(heading)}",
                "text": f"{section}\n\n{piece}",
            })
    return chunks


def chunk_slides(lid: str) -> list[dict]:
    path = REPO / "lectures" / lid / "slides.md"
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"^---\n.*?\n---\n", "", raw, count=1, flags=re.S)        # front matter
    slides = re.split(r"^---\s*$", raw, flags=re.M)
    chunks = []
    for n, s in enumerate(slides, start=1):
        if "clicker-opts" in s or "clicker-leaderboard" in s:
            continue                                                       # never index answers
        m = re.search(r"^#{1,2}\s+(.+)$", s, re.M)
        heading = m.group(1).strip() if m else f"slide {n}"
        text = clean_markdown(s)
        if len(text.split()) < 12:
            continue
        chunks.append({
            "id": f"{lid}-s-{n:02d}", "lecture": lid, "kind": "slides",
            "title": f"{lid.upper()} slides", "section": heading,
            "url": f"{SITE}/slides/{lid}/#{n}", "text": text,
        })
    return chunks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lectures", help="explicit range such as l01-l17 instead of _toc.yml")
    ap.add_argument("--stats", action="store_true", help="print counts, write nothing")
    ap.add_argument("--notes-only", action="store_true", help="skip slides (the L18 notebook's snapshot)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    ids = parse_range(args.lectures) if args.lectures else released_ids()
    chunks = [c for lid in ids for c in chunk_notes(lid) + ([] if args.notes_only else chunk_slides(lid))]
    words = [len(c["text"].split()) for c in chunks]
    print(f"{len(ids)} lectures, {len(chunks)} chunks "
          f"({sum(c['kind'] == 'notes' for c in chunks)} notes, {sum(c['kind'] == 'slides' for c in chunks)} slides), "
          f"{sum(words):,} words, median {sorted(words)[len(words) // 2]} words per chunk", file=sys.stderr)
    if args.stats:
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"lectures": ids, "chunks": chunks}, ensure_ascii=False))
    print(f"wrote {args.out.resolve().relative_to(REPO)} ({args.out.stat().st_size / 1e6:.1f} MB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
