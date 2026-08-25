#!/usr/bin/env python3
"""Generate the clicker QR code.

The vote URL is the same for every question and every lecture, so this runs once
and its PNG is reused by every clicker slide for the rest of the course. Rerun it
only if the Worker's hostname changes, which also invalidates every printed deck.

    uv run --with segno clicker/make_qr.py
"""
import argparse
import pathlib

import segno

VOTE_URL = "https://clicker.f26-06763.workers.dev"
OUT = pathlib.Path(__file__).resolve().parents[1] / "lectures" / "l03" / "figures" / "clicker-qr.png"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=VOTE_URL)
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    args = ap.parse_args()

    # Error correction "M" tolerates a projector's glare and a phone camera at the
    # back of a lecture hall without inflating the module count the way "H" does.
    qr = segno.make(args.url, error="m")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    qr.save(args.out, scale=12, border=3, dark="#14171a", light="#ffffff")

    print(f"{args.url}\n  -> {args.out}  (version {qr.version}, {qr.error} correction)")


if __name__ == "__main__":
    main()
