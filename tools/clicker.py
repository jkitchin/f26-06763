#!/usr/bin/env python3
"""Read and archive in-class clicker results.

The clicker Worker is deliberately ignorant: it stores (timestamp, letter,
device-pseudonym) and nothing else, so it never needs redeploying when a question
changes. Everything that knows about lectures and questions lives here and in the
slides.

    python3 tools/clicker.py stats
    python3 tools/clicker.py show                 # live bars for the current burst
    python3 tools/clicker.py windows --date today # what the slides marked
    python3 tools/clicker.py questions --date today   # bursts, inferred from gaps
    python3 tools/clicker.py leaderboard --date today # standings for the day
    python3 tools/clicker.py archive l03 --date 2026-08-26

`archive` does not need you to have written down when each question ran. A slide
carrying data-tag records its own window when voting closes, which gives exact
boundaries plus the prompt and the answer. Failing that, the server infers a
question as a burst of votes separated from the next by a gap. `archive` prefers
the marks and falls back to the bursts, saying which it used.

`leaderboard` scores the day the same way the projector does, because it asks the
same endpoint: the standings a room saw at the end of a lecture are the standings
this prints afterwards. Only students who chose a nickname appear; the rest voted
anonymously and are counted in the bars but never in the board.

No dependencies beyond the standard library, matching the other tools here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zoneinfo

BASE = "https://clicker.f26-06763.workers.dev"
CAMPUS_TZ = zoneinfo.ZoneInfo("America/New_York")
OPTS = ("A", "B", "C", "D")

# The server clamps this to at least 5s. Two minutes comfortably separates two
# questions in a lecture while never splitting one, since a question window is
# a minute and stragglers arrive inside it.
DEFAULT_GAP_MS = 120_000

REPO = pathlib.Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- io

# Cloudflare's browser-integrity check answers "Python-urllib/3.x" with a 403 and
# error code 1010, so send a real one. Nothing here depends on pretending to be a
# browser beyond getting past that.
UA = "f26-06763-clicker-tool/1.0 (+https://github.com/jkitchin/f26-06763)"


def get(path: str, **params) -> dict:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"{url}\n  HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"{url}\n  unreachable: {e.reason}")


def day_bounds(spec: str) -> tuple[int, int, dt.date]:
    """Turn a local calendar date into an epoch-ms range.

    Time zones live here rather than in the Worker. The Worker takes from/to in
    epoch ms and stays ignorant of dates, which is what lets it be deployed once
    and never touched.
    """
    today = dt.datetime.now(CAMPUS_TZ).date()
    if spec in ("today", ""):
        d = today
    elif spec == "yesterday":
        d = today - dt.timedelta(days=1)
    else:
        try:
            d = dt.date.fromisoformat(spec)
        except ValueError:
            sys.exit(f"bad --date {spec!r}: use YYYY-MM-DD, 'today', or 'yesterday'")
    start = dt.datetime.combine(d, dt.time.min, CAMPUS_TZ)
    return int(start.timestamp() * 1000), int((start + dt.timedelta(days=1)).timestamp() * 1000), d


def bar(n: int, biggest: int, width: int = 34) -> str:
    return "#" * (0 if biggest <= 0 else round(width * n / biggest))


def render(counts: dict, title: str = "", answer: str | None = None) -> None:
    total = counts.get("total", 0)
    biggest = max((counts.get(o, 0) for o in OPTS), default=0)
    if title:
        print(title)
    for o in OPTS:
        n = counts.get(o, 0)
        pct = f"{round(100 * n / total):3d}%" if total else "   -"
        flag = " *" if answer and o == answer.upper() else "  "
        print(f"  {o}{flag} {bar(n, biggest):<34} {n:>3} {pct}")
    print(f"  {'':4}{'':34} {total:>3} total")


# ---------------------------------------------------------------- subcommands

def cmd_stats(args) -> None:
    s = get("/stats", days=args.days)
    if not s["votes"]:
        print("No votes recorded yet.")
        return
    print(f"{s['votes']} votes from {s['devices']} devices")
    print(f"first {s['first_iso']}")
    print(f"last  {s['last_iso']}")
    print()
    print(f"{'day (UTC)':<12}{'votes':>7}{'devices':>9}")
    for d in s["days"]:
        print(f"{d['day']:<12}{d['votes']:>7}{d['devices']:>9}")


def cmd_windows(args) -> None:
    lo, hi, d = day_bounds(args.date)
    ws = get("/windows", **{"from": lo, "to": hi})["windows"]
    if not ws:
        print(f"No marked windows on {d}. The slides may not carry data-tag; "
              "try `questions` to see the raw bursts.")
        return
    print(f"{d}: {len(ws)} marked window(s)\n")
    for w in ws:
        when = dt.datetime.fromtimestamp(w["from"] / 1000, CAMPUS_TZ).strftime("%H:%M:%S")
        head = f"{w['tag']}  round {w['round']}  {when}  ({w['seconds']}s)"
        if w.get("prompt"):
            head += f"\n  {w['prompt']}"
        render(w, title=head, answer=w.get("answer"))
        print()


def cmd_questions(args) -> None:
    lo, hi, d = day_bounds(args.date)
    r = get("/questions", **{"from": lo, "to": hi, "gap": args.gap})
    qs = r["questions"]
    if not qs:
        print(f"No votes on {d}.")
        return
    if r.get("truncated"):
        print("WARNING: row limit hit; results are incomplete.\n")
    print(f"{d}: {len(qs)} question window(s), gap {r['gap'] / 1000:g}s\n")
    for q in qs:
        when = dt.datetime.fromtimestamp(q["from"] / 1000, CAMPUS_TZ).strftime("%H:%M:%S")
        render(q, title=f"Q{q['n']}  {when}  ({q['seconds']}s, {q['raw_votes']} raw taps)")
        print()


def cmd_show(args) -> None:
    """Poll the last few minutes and redraw. A backstop for when the in-slide
    histogram misbehaves in front of a room."""
    try:
        while True:
            now = int(time.time() * 1000)
            c = get("/r", **{"from": now - args.window * 1000, "to": now})
            print("\033[2J\033[H", end="")
            render(c, title=f"last {args.window}s   (ctrl-c to stop)")
            time.sleep(args.every)
    except KeyboardInterrupt:
        print()


def render_board(d: dict, title: str = "") -> None:
    if title:
        print(title)
    rows = d.get("standings") or []
    if not rows:
        # Two different empties, and telling them apart is the difference between
        # "nobody played" and "the questions were opinion polls".
        print("  no standings: " + ("nobody chose a nickname" if d.get("questions")
                                    else "no scored questions in that range"))
        return
    print(f"  {'#':>3}  {'nickname':<26}{'right':>6}{'of':>4}{'time':>9}")
    for s in rows:
        print(f"  {s['rank']:>3}  {s['name']:<26}{s['correct']:>6}{s['answered']:>4}"
              f"{s['seconds']:>8.1f}s")
    print(f"\n  {d['players']} player(s) over {d['questions']} scored question(s)")


def cmd_leaderboard(args) -> None:
    lo, hi, d = day_bounds(args.date)
    board = get("/leaderboard", **{"from": lo, "to": hi, "top": args.top})
    render_board(board, title=f"{d}\n")


def cmd_archive(args) -> None:
    lo, hi, d = day_bounds(args.date)

    # Marks are exact and carry the prompt and answer, so prefer them. Burst
    # detection is the fallback for a deck whose slides had no data-tag.
    marked = get("/windows", **{"from": lo, "to": hi})["windows"]
    if marked and not args.force_bursts:
        qs, source = marked, "marked by the slides"
        for i, q in enumerate(qs, 1):
            q.setdefault("n", i)
    else:
        r = get("/questions", **{"from": lo, "to": hi, "gap": args.gap})
        qs, source = r["questions"], f"inferred from gaps of {r['gap'] / 1000:g}s"
        if r.get("truncated"):
            sys.exit("Row limit hit; refusing to write a partial archive.")
    if not qs:
        sys.exit(f"No votes on {d}; nothing to archive.")

    # Scored from the same endpoint the projector used, so the file agrees with
    # what the room saw. A day with no nicknames simply has an empty block.
    board = get("/leaderboard", **{"from": lo, "to": hi, "top": args.top})

    out = args.out or REPO / "course" / "clicker" / f"{args.lecture}.yml"
    out.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Clicker results. Generated by tools/clicker.py.",
        "#",
        f"# Question windows: {source}.",
        "# A slide carrying data-tag records its own window when voting closes, which gives",
        "# exact boundaries plus the prompt and the answer. Without that, a question is",
        "# inferred as a burst of votes separated from the next by a gap.",
        "#",
        "# Device pseudonyms are deliberately not carried over: they are random per-browser",
        "# strings, they identify nobody, and there is no reason to keep them here.",
        f"lecture: {args.lecture}",
        f"date: {d.isoformat()}",
        f"source: {BASE}",
        "questions:",
    ]
    for q in qs:
        when = dt.datetime.fromtimestamp(q["from"] / 1000, CAMPUS_TZ)
        lines += [
            f"  - n: {q['n']}",
            f"    at: {when.isoformat(timespec='seconds')}",
            f"    seconds: {q['seconds']}",
        ]
        if q.get("tag"):
            lines.append(f"    tag: {q['tag']}")
        if q.get("round"):
            lines.append(f"    round: {q['round']}")
        prompt = (q.get("prompt") or "").replace('"', "'")
        lines += [
            f'    prompt: "{prompt}"' if prompt
            else '    prompt: ""      # no slide mark; fill in from the slide',
            f'    answer: "{q["answer"]}"' if q.get("answer")
            else '    answer: ""      # empty for an opinion poll',
            "    counts:",
            *[f"      {o}: {q[o]}" for o in OPTS],
            f"    voters: {q['total']}",
        ]
        # Only the burst view knows how many taps produced those voters.
        if "raw_votes" in q:
            lines.append(f"    raw_taps: {q['raw_votes']}")

    # Nicknames are student-invented and identify nobody, which is the whole
    # premise of the board, so unlike the device pseudonyms they are worth
    # keeping. They are still self-reported strings: quote them, and do not
    # treat one that looks like an Andrew ID as being one.
    lines += [
        "",
        "# Standings, scored the same way the projector scored them: a point per",
        "# correct answer, time summed over correct answers only as the tiebreak.",
        "# Students who voted without a nickname are in the counts above and not here.",
        f"players: {board['players']}",
        "standings:",
    ]
    if not board["standings"]:
        lines.append("  []")
    for s in board["standings"]:
        name = (s["name"] or "").replace('"', "'")
        lines += [
            f"  - rank: {s['rank']}",
            f'    name: "{name}"',
            f"    correct: {s['correct']}",
            f"    answered: {s['answered']}",
            f"    seconds: {s['seconds']}",
        ]
    out.write_text("\n".join(lines) + "\n")
    print(f"{len(qs)} question(s), {board['players']} player(s), {source} "
          f"-> {out.relative_to(REPO)}")
    if source.startswith("inferred"):
        print("No slide marks found, so prompts and answers are blank; fill them in.")


def main() -> None:
    global BASE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=BASE, help="Worker base URL")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("stats", help="overall usage")
    p.add_argument("--days", type=int, default=30)
    p.set_defaults(fn=cmd_stats)

    p = sub.add_parser("windows", help="windows the slides marked for themselves")
    p.add_argument("--date", default="today")
    p.set_defaults(fn=cmd_windows)

    p = sub.add_parser("questions", help="question windows inferred from gaps")
    p.add_argument("--date", default="today")
    p.add_argument("--gap", type=int, default=DEFAULT_GAP_MS, help="ms between questions")
    p.set_defaults(fn=cmd_questions)

    p = sub.add_parser("leaderboard", help="standings for a day")
    p.add_argument("--date", default="today")
    p.add_argument("--top", type=int, default=20)
    p.set_defaults(fn=cmd_leaderboard)

    p = sub.add_parser("show", help="live bars, as a backstop for the slide")
    p.add_argument("--window", type=int, default=90, help="seconds to look back")
    p.add_argument("--every", type=float, default=2.0, help="seconds between polls")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("archive", help="write course/clicker/lNN.yml")
    p.add_argument("lecture")
    p.add_argument("--date", default="today")
    p.add_argument("--gap", type=int, default=DEFAULT_GAP_MS)
    p.add_argument("--top", type=int, default=50, help="standings rows to keep")
    p.add_argument("--out", type=pathlib.Path)
    p.add_argument("--force-bursts", action="store_true",
                   help="ignore slide marks and infer windows from gaps")
    p.set_defaults(fn=cmd_archive)

    args = ap.parse_args()
    BASE = args.base.rstrip("/")
    args.fn(args)


if __name__ == "__main__":
    main()
