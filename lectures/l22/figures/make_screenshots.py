#!/usr/bin/env python3
"""Screenshots of the course map's knowledge graph and system figure, for the L22 deck.

Both are live pages, so the deck shows a still of each and links to the real thing. The
stills are taken from a running copy of the map, so they are retaken whenever the map changes
rather than edited by hand. Reduced motion is on, which stops the idle drift, so two runs on
the same map give the same pictures.

    cd game && npm run dev                                    # a local copy of the map
    uv run --no-project --with playwright python lectures/l22/figures/make_screenshots.py

    # or against the published site
    uv run --no-project --with playwright python lectures/l22/figures/make_screenshots.py \\
        --url https://kitchingroup.cheme.cmu.edu/f26-06763/game/
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
CHROME = os.environ.get("CHROME_PATH") or next(
    (p for p in [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ] if Path(p).exists()),
    None,
)
SKIP_GUIDE = "try { localStorage.setItem('f26-map-guide-seen', '1') } catch (e) {}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://localhost:5173/f26-06763/game/")
    args = ap.parse_args()
    base = args.url.rstrip("/") + "/"

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])

        def page_at(width: int, height: int, *, phone: bool = False, guide: bool = False):
            ctx = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=2 if phone else 1.25,
                is_mobile=phone, has_touch=phone,
                color_scheme="dark", reduced_motion="reduce",
            )
            if not guide:
                ctx.add_init_script(SKIP_GUIDE)
            return ctx.new_page()

        def shot(page, name: str, wait: int = 900) -> None:
            page.wait_for_timeout(wait)
            page.screenshot(path=str(HERE / f"{name}.png"))
            print(f"wrote {name}.png")

        # The knowledge graph, by lecture: the whole course at a glance.
        page = page_at(1600, 900)
        page.goto(base + "#/map", wait_until="networkidle")
        shot(page, "kg-lectures", 1500)

        # One lecture open: its links lit, and its panel of takeaways and key points.
        page.get_by_role("button", name="All lectures").click()
        page.locator("aside button", has_text="L10 ·").first.click()
        shot(page, "kg-lecture-panel", 1500)

        # By topic: themes, with the index's concepts on rings around them.
        page.get_by_role("button", name="Close").click()
        page.get_by_role("radio", name="By topic").click()
        shot(page, "kg-topics", 1500)

        # Every failure mode in the course at once, for a quick review.
        page.get_by_role("button", name="Failure modes").click()
        shot(page, "kg-failures", 1500)

        # Lecture 1's figure, live, with one part open and its toolchain shown.
        page.goto(base + "#/map/system", wait_until="networkidle")
        shot(page, "system", 1200)
        page.locator('g[role="button"][aria-label^="Data verification"]').click()
        page.get_by_text("Show the toolchain").click()
        shot(page, "system-panel", 1200)

        # The same map on a phone.
        page = page_at(393, 852, phone=True)
        page.goto(base + "#/map", wait_until="networkidle")
        shot(page, "kg-phone", 1500)

        browser.close()


if __name__ == "__main__":
    main()
