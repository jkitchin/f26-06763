# /// script
# requires-python = ">=3.11"
# dependencies = ["paho-mqtt>=2.1"]
# ///
"""Collect the plant stream to a file. This is the only networked part of A3.

Run it, leave it running, and it appends one line per message to
`raw/stream-<date>.ndjson`. Everything else you build reads that file, not the
network, which is what makes your pipeline re-runnable: a stream is gone once
it has gone past, so the first thing to do with it is write it down.

    uv run --no-project a03-collect.py --minutes 60

It lands what arrived, in the order it arrived, unaltered. It does not sort,
deduplicate, drop the late records, or parse the values. Those are decisions,
and decisions belong in the pipeline where they are visible and testable, not
in the collector where they would silently change the data before you ever saw
it.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import signal
import sys
import time

import paho.mqtt.client as mqtt

DEFAULT_HOST = "kitchin-services.cheme.cmu.edu"
DEFAULT_PATH = "/mqtt"
TOPIC = "plant/#"


def now_iso() -> str:
    """This machine's clock, in UTC, to the millisecond."""
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=443)
    p.add_argument("--path", default=DEFAULT_PATH)
    p.add_argument("--no-tls", action="store_true", help="plain ws, for a local broker")
    p.add_argument("--out", default=None, help="output file (default raw/stream-<date>.ndjson)")
    p.add_argument("--minutes", type=float, default=0, help="stop after this long; 0 runs until Ctrl-C")
    args = p.parse_args()

    out = pathlib.Path(args.out) if args.out else pathlib.Path(
        "raw"
    ) / f"stream-{datetime.date.today().isoformat()}.ndjson"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Append, never truncate. Running the collector twice should give you more
    # data, not silently replace what you spent an hour collecting.
    handle = out.open("a", encoding="utf-8")

    counts = {"telemetry": 0, "birth": 0, "event": 0, "other": 0}
    stopping = False

    def on_connect(client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            print(f"connect failed: {reason_code}", file=sys.stderr)
            return
        client.subscribe(TOPIC, qos=0)
        print(f"connected to {args.host}, subscribed to {TOPIC}", file=sys.stderr)

    def on_message(client, userdata, msg):
        # The payload is written through byte for byte inside the envelope.
        # Reformatting it here (json.loads then json.dumps) would reorder keys
        # and change the spacing, and anything computed over the exact bytes
        # the broker sent would stop matching.
        payload = msg.payload.decode("utf-8", errors="replace")
        handle.write(
            '{"receivedAt":"%s","topic":"%s","payload":%s}\n'
            % (now_iso(), msg.topic, payload)
        )
        kind = msg.topic.rsplit("/", 1)[-1]
        counts[kind if kind in counts else "other"] += 1
        total = sum(counts.values())
        if total % 25 == 0:
            handle.flush()
            print(
                f"\r{total} messages "
                f"({counts['telemetry']} telemetry, {counts['event']} events)",
                end="",
                file=sys.stderr,
            )

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
    client.ws_set_options(path=args.path)
    if not args.no_tls:
        client.tls_set()
    client.on_connect = on_connect
    client.on_message = on_message
    # The stream does not pause while you are disconnected, so anything that
    # happened during a reconnect is simply not in your file. That gap is data
    # about your collection, and the pipeline should be able to see it.
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(args.host, args.port, keepalive=60)

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    client.loop_start()
    deadline = time.monotonic() + args.minutes * 60 if args.minutes else None
    while not stopping and (deadline is None or time.monotonic() < deadline):
        time.sleep(0.2)
    client.loop_stop()
    client.disconnect()
    handle.flush()
    handle.close()

    print(
        f"\nwrote {sum(counts.values())} messages to {out} "
        f"({counts['telemetry']} telemetry, {counts['birth']} birth, {counts['event']} events)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
