#!/usr/bin/env python3
"""Serve the whole course site locally, exactly as CI publishes it.

    python3 tools/preview.py                 # build everything, then serve
    python3 tools/preview.py --fast          # serve what is already built
    python3 tools/preview.py --only l07      # rebuild one lecture's deck only
    python3 tools/preview.py --port 9000

`jupyter-book build .` gets you the notes and nothing else. The decks, the
practice game, the clicker and the arcade are assembled by separate steps in
`.github/workflows/book.yml`, so a local book build shows a lecture with a dead
"Deck for this session" link and a dead practice-module link. This script runs
those same steps into the same `_build/html` and then serves the result, so what
you read locally is what the site will serve.

**It serves the site under /f26-06763/, and that is not cosmetic.** The game is a
Vite app built with `base: '/f26-06763/game/'`, which is an absolute path. Served
from the root of a local server, every one of its assets 404s and the page comes
back blank while `index.html` still exists, which is the same failure mode
`vite.config.ts` warns about. So the handler below mounts `_build/html` at that
prefix and redirects `/` to it.

Nothing here is a second implementation of the deploy. The slide rendering and the
asset copying mirror the workflow step by step, and the comments say which step.
If the workflow changes, change this too; the slide-asset check at the end is the
thing that will notice.

Not served: the vote endpoint behind the clicker slides, which is a Cloudflare
Worker. Clicker slides render and the QR is there, but voting needs the deployed
worker, so a local deck shows the question and the timer and never counts a vote.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import os
import re
import shutil
import socketserver
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

# The URL list below is the only output that matters, and a piped run buffers it
# out of existence otherwise. Flushing every print costs nothing here.
print = functools.partial(print, flush=True)  # noqa: A001

REPO = Path(__file__).resolve().parent.parent
HTML = REPO / "_build" / "html"

#: The deployed subpath. The game's Vite base hardcodes it, so the local server
#: has to hand it back or the game renders blank. See the module docstring.
BASE = "/f26-06763"

MARP = ["npx", "-y", "@marp-team/marp-cli@latest"]


def sh(cmd: list[str], cwd: Path = REPO, **kw) -> int:
    """Run a command, from the repo root unless told otherwise."""
    return subprocess.call(cmd, cwd=cwd, **kw)


def released_lectures() -> list[str]:
    """The lecture ids uncommented in _toc.yml.

    The same lever CI reads, so a lecture that is not released locally is not
    rendered locally either. Otherwise the preview would show next week's deck
    and nobody would notice it had leaked until it was on the public site.
    """
    toc = (REPO / "_toc.yml").read_text()
    return re.findall(
        r"^\s*-\s*file:\s*lectures/(l\d\d)/notes\s*$", toc, flags=re.MULTILINE
    )


def build_book() -> bool:
    print("==> jupyter-book build")
    return sh(["jupyter-book", "build", ".", "--warningiserror", "--keep-going"]) == 0


def render_deck(lecture_id: str) -> None:
    """One lecture deck into slides/<id>/index.html, with everything it references.

    MARP does not inline local images; it emits <img src="figures/x.png">. So the
    deck's own figures, the clicker driver and QR, and the whole arcade directory
    are copied in beside it, which is what makes the relative paths resolve the
    same here as in production.
    """
    deck = REPO / "lectures" / lecture_id / "slides.md"
    if not deck.exists():
        print(f"    {lecture_id}: no slides.md, skipped")
        return
    out = HTML / "slides" / lecture_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "figures").mkdir(exist_ok=True)

    # Rendered from the repo root on purpose: .marprc.yml sets themeSet: ./themes
    # relative to the working directory, and running marp from inside the deck's
    # own directory silently drops the course theme.
    sh(MARP + [str(deck.relative_to(REPO)), "--html", "-o", str(out / "index.html")],
       stdout=subprocess.DEVNULL)

    for png in (REPO / "lectures" / lecture_id / "figures").glob("*.png"):
        shutil.copy(png, out / "figures" / png.name)
    shutil.copy(REPO / "clicker" / "clicker-slide.js", out)
    shutil.copy(REPO / "clicker" / "figures" / "clicker-qr.png", out / "figures")
    for name in ("arcade.js", "arcade.css"):
        shutil.copy(REPO / "arcade" / name, out)
    for sub, pat in (("games", "*.js"), ("rounds", "*.json")):
        (out / sub).mkdir(exist_ok=True)
        for f in (REPO / "arcade" / sub).glob(pat):
            shutil.copy(f, out / sub / f.name)
    print(f"    {lecture_id} -> {BASE}/slides/{lecture_id}/")


def render_standalone_decks() -> None:
    """The clicker shakedown and the arcade demo, neither gated on _toc.yml."""
    out = HTML / "slides" / "clicker"
    (out / "figures").mkdir(parents=True, exist_ok=True)
    sh(MARP + ["clicker/shakedown.md", "--html", "-o", str(out / "index.html")],
       stdout=subprocess.DEVNULL)
    for png in (REPO / "clicker" / "figures").glob("*.png"):
        shutil.copy(png, out / "figures" / png.name)
    shutil.copy(REPO / "clicker" / "clicker-slide.js", out)

    out = HTML / "slides" / "arcade"
    (out / "games").mkdir(parents=True, exist_ok=True)
    (out / "rounds").mkdir(parents=True, exist_ok=True)
    sh(MARP + ["arcade/demo.md", "--html", "-o", str(out / "index.html")],
       stdout=subprocess.DEVNULL)
    for name in ("arcade.js", "arcade.css"):
        shutil.copy(REPO / "arcade" / name, out)
    for sub, pat in (("games", "*.js"), ("rounds", "*.json")):
        for f in (REPO / "arcade" / sub).glob(pat):
            shutil.copy(f, out / sub / f.name)
    print(f"    clicker and arcade -> {BASE}/slides/clicker/, {BASE}/slides/arcade/")


def build_game() -> bool:
    """`npm run build` into _build/html/game.

    Slow (it typechecks first), so --fast skips it. The built bundle is what the
    notes' practice-module link points at, and it is the only way to see a real
    sitting end to end, including the evidence PDF.
    """
    if not (REPO / "game" / "node_modules").exists():
        print("    game: no node_modules, run `npm ci` in game/ first. Skipped.")
        return False
    print("==> npm run build (game)")
    if sh(["npm", "run", "build"], cwd=REPO / "game") != 0:
        print("    game build failed")
        return False
    dest = HTML / "game"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(REPO / "game" / "dist", dest)
    print(f"    game -> {BASE}/game/")
    return True


def check_slide_assets() -> bool:
    """Every <img src> and <script src> in a rendered deck resolves to a file.

    The same check CI runs, and worth having locally for the reason CI has it: a
    missing figure is a silent broken image, and a missing clicker-slide.js is a
    question whose button does nothing. Both are only visible in front of a room.
    """
    bad = []
    for html in sorted((HTML / "slides").glob("*/index.html")):
        text = html.read_text(errors="ignore")
        for src in re.findall(r'src="([^"]*\.(?:png|js))"', text):
            if not (html.parent / src).is_file():
                bad.append(f"{html.parent.name}: missing {src}")
    for line in bad:
        print(f"    ASSET MISSING  {line}")
    return not bad


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serve _build/html under BASE, with caching off.

    Caching off because the whole point is to rebuild and reload. Without it a
    browser happily keeps showing the previous build of a page you just changed,
    which wastes the time this script is meant to save.
    """

    def translate_path(self, path: str) -> str:
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith(BASE):
            path = path[len(BASE):] or "/"
        return super().translate_path(path)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", f"{BASE}/")
            self.end_headers()
            return
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_request(self, code="-", size="-"):
        # Successful requests are noise; a 404 is the whole reason you are
        # looking at this window, because it is what a missing figure or a
        # wrong base path looks like from the server side.
        if str(code) != "200":
            print(f"    {code}  {self.requestline}", flush=True)

    def log_message(self, fmt, *args):
        pass


def serve(port: int, open_at: str | None) -> None:
    os.chdir(HTML)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler) as httpd:
        url = f"http://localhost:{port}{BASE}/"
        print(f"\n  Site     {url}")
        print(f"  L7 notes {url}lectures/l07/notes.html")
        print(f"  L7 deck  {url}slides/l07/")
        print(f"  Practice {url}game/#/l07")
        print(f"  Map      {url}game/#/map")
        print(f"  Index    {url}genindex.html")
        print("\n  Ctrl-C to stop. Rebuild in another shell and reload; caching is off.\n")
        if open_at:
            threading.Timer(0.5, webbrowser.open, [url + open_at]).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--fast", action="store_true",
                    help="serve what is already in _build/html, build nothing")
    ap.add_argument("--only", metavar="lNN",
                    help="render just this lecture's deck, skip the book and the game")
    ap.add_argument("--no-game", action="store_true", help="skip the slow game build")
    ap.add_argument("--no-book", action="store_true", help="skip jupyter-book")
    ap.add_argument("--open", metavar="PATH", nargs="?", const="",
                    help="open a browser at BASE/PATH once the server is up")
    args = ap.parse_args()

    if args.only:
        HTML.mkdir(parents=True, exist_ok=True)
        print("==> decks")
        render_deck(args.only)
    elif not args.fast:
        if not args.no_book and not build_book():
            print("\nbook build failed; fix it or rerun with --fast to serve the last build")
            return 1
        print("==> decks")
        for lid in released_lectures():
            render_deck(lid)
        render_standalone_decks()
        if not check_slide_assets():
            print("    (serving anyway, but those would fail CI)")
        if not args.no_game:
            build_game()

    if not HTML.exists():
        print(f"nothing built at {HTML}. Run without --fast.")
        return 1
    serve(args.port, args.open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
