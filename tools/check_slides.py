#!/usr/bin/env python3
"""Find slides whose content does not fit, in a rendered MARP deck.

    uv run --no-project --with playwright python tools/check_slides.py lectures/l09/slides.md
    uv run --no-project --with playwright python tools/check_slides.py lectures/*/slides.md

It renders each deck the way CI does (the marp CLI from the repo root, with the course
theme and --html), opens it in headless Chrome, and measures every element on every
slide. A slide fails when anything in the normal flow of the page:

  * runs past the bottom of the slide's content box, or into the footer;
  * runs past the right edge of the content box;
  * is a code block, table, equation or image wider than its own box, so it is
    clipped or scrolls (the case a quick look at the slide misses most often).

Header, footer, page number and anything the author positioned absolutely are skipped,
because they are placed on purpose.

It also flags any bullet that starts with a lowercase letter, which the course's slide
style does not allow. A bullet that opens with code or math is exempt, and so is one that
opens with a name written lowercase on purpose (scikit-learn, nDCG, uv).

Why a separate checker from tools/check_slide_overflow.mjs: that one measures only
vertical overflow, and it reads the deck CI already built. This one renders the deck
itself, from the markdown you are editing, and checks both directions, so it can run
while you write. It needs a local Google Chrome (or set CHROME_PATH).

Two pitfalls it cannot see, and the reason it exists at all: the VS Code MARP preview
does not know `theme: course` unless .vscode/settings.json registers it, and without
the theme every slide is laid out in the default theme's larger type. What this script
measures is what the published deck shows.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SLACK = 4  # px of a 1280 x 720 slide; a descender or a rounded line box, not a lost line

CHROME = os.environ.get("CHROME_PATH") or next(
    (p for p in [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ] if Path(p).exists()), None)

MEASURE = """
(slack) => {
  const out = [];
  document.querySelectorAll('section').forEach((sec, i) => {
    const cs = getComputedStyle(sec);
    const R = sec.getBoundingClientRect();
    const scale = R.width / sec.offsetWidth || 1;
    const box = {
      left: parseFloat(cs.paddingLeft), top: parseFloat(cs.paddingTop),
      right: sec.offsetWidth - parseFloat(cs.paddingRight),
      bottom: sec.offsetHeight - parseFloat(cs.paddingBottom),
    };
    const footer = sec.querySelector('footer');
    const footerTop = footer ? (footer.getBoundingClientRect().top - R.top) / scale : Infinity;
    const heading = (sec.querySelector('h1, h2')?.textContent || '').replace(/\\s+/g, ' ').trim();
    const problems = [];
    const label = (el) => {
      const tag = el.tagName.toLowerCase();
      const img = el.tagName === 'IMG' ? el : el.querySelector && el.querySelector('img');
      const text = (el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 50);
      return '<' + tag + '>' + (img ? ' [img ' + img.getAttribute('src') + ']' : '') + (text ? ' "' + text + '"' : '');
    };
    const walk = (el) => {
      for (const c of el.children) {
        const s = getComputedStyle(c);
        if (s.display === 'none' || s.visibility === 'hidden') continue;
        if (s.position === 'absolute' || s.position === 'fixed') continue;
        if (['HEADER', 'FOOTER', 'SCRIPT', 'STYLE'].includes(c.tagName)) continue;
        const r = c.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) { walk(c); continue; }
        const top = (r.top - R.top) / scale, bottom = (r.bottom - R.top) / scale;
        const right = (r.right - R.left) / scale;
        if (bottom > Math.min(box.bottom, footerTop) + slack)
          problems.push(['bottom', Math.round(bottom - Math.min(box.bottom, footerTop)), label(c)]);
        else if (right > box.right + slack)
          problems.push(['right', Math.round(right - box.right), label(c)]);
        if (['PRE', 'TABLE', 'IMG', 'SVG', 'MJX-CONTAINER'].includes(c.tagName.toUpperCase())
            && c.scrollWidth > c.clientWidth + 2 && c.clientWidth > 0)
          problems.push(['clipped', c.scrollWidth - c.clientWidth, label(c)]);
        walk(c);
      }
    };
    walk(sec);
    // report the worst problem per kind, not every nested element that inherits it
    const worst = {};
    for (const [kind, px, what] of problems)
      if (!worst[kind] || px > worst[kind][0]) worst[kind] = [px, what];
    for (const kind in worst) out.push({slide: i + 1, heading, kind, px: worst[kind][0], what: worst[kind][1]});
  });
  return out;
}
"""


LOWERCASE = """
(allowed) => {
  const out = [];
  document.querySelectorAll('section').forEach((sec, i) => {
    const heading = (sec.querySelector('h1, h2')?.textContent || '').replace(/\\s+/g, ' ').trim();
    sec.querySelectorAll('li').forEach((li) => {
      if (li.closest('.clicker-opts')) return;
      // the first thing in the bullet that shows: a text node or an element
      let first = null;
      for (const n of li.childNodes) {
        if (n.nodeType === 3 && !n.textContent.trim()) continue;
        first = n; break;
      }
      while (first && first.nodeType === 1 && ['STRONG', 'EM', 'B', 'I', 'SPAN', 'A', 'P'].includes(first.tagName)) {
        let inner = null;
        for (const n of first.childNodes) {
          if (n.nodeType === 3 && !n.textContent.trim()) continue;
          inner = n; break;
        }
        first = inner;
      }
      if (!first) return;
      if (first.nodeType === 1) return;  // code, math, an image: exempt
      const text = first.textContent.trim();
      const word = text.split(/[\\s,:;]/)[0];
      if (/^[a-z]/.test(text) && !allowed.includes(word))
        out.push({slide: i + 1, heading, kind: 'lowercase', px: 0, what: '"' + text.slice(0, 50) + '"'});
    });
  });
  return out;
}
"""
ALLOWED_LOWERCASE = ["scikit-learn", "nDCG", "uv", "pandas", "numpy", "iPhone"]


def render(deck: Path, out: Path) -> Path:
    """Render one deck to out/index.html with its figures beside it, as CI does."""
    html = out / "index.html"
    cmd = ["npx", "-y", "@marp-team/marp-cli@latest", str(deck.relative_to(REPO)),
           "--html", "--template", "bare", "--no-stdin", "-o", str(html)]
    # --no-stdin and a closed stdin: when stdin is not a terminal, marp waits to read the
    # markdown from it and the check hangs forever.
    subprocess.run(cmd, cwd=REPO, check=True, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    figs = deck.parent / "figures"
    (out / "figures").mkdir(exist_ok=True)
    if figs.is_dir():
        for png in figs.glob("*.png"):
            shutil.copy(png, out / "figures" / png.name)
    qr = REPO / "clicker" / "figures" / "clicker-qr.png"
    if qr.exists():
        shutil.copy(qr, out / "figures" / qr.name)
    return html


def check(html: Path) -> list[dict]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(html.as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready.then(() => true)")
        page.wait_for_timeout(300)
        rows = page.evaluate(MEASURE, SLACK) + page.evaluate(LOWERCASE, ALLOWED_LOWERCASE)
        browser.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("decks", nargs="+", type=Path, help="slides.md files")
    args = ap.parse_args()
    if not CHROME:
        print("No Chrome found. Set CHROME_PATH.", file=sys.stderr)
        return 2
    failed = 0
    for deck in args.decks:
        deck = deck.resolve()
        with tempfile.TemporaryDirectory() as tmp:
            rows = check(render(deck, Path(tmp)))
        name = deck.parent.name
        if not rows:
            print(f"OK    {name}: every slide fits")
            continue
        failed += len({r['slide'] for r in rows})
        for r in rows:
            if r["kind"] == "lowercase":
                print(f"FAIL  {name} slide {r['slide']:>2} ({r['heading'][:55]}): bullet starts lowercase: {r['what']}")
                continue
            what = {"bottom": "runs off the bottom by", "right": "runs off the right by",
                    "clipped": "is wider than its box by"}[r["kind"]]
            print(f"FAIL  {name} slide {r['slide']:>2} ({r['heading'][:55]}): {r['what']} {what} {r['px']}px")
    if failed:
        print(f"\n{failed} slide(s) do not fit or break the bullet style.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
