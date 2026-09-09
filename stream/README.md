# The plant stream

A continuously running [Tennessee Eastman](https://github.com/jkitchin/tep-rust)
plant, published as MQTT messages over a lossy link, for A3 to collect and
analyse. Nothing here is published to the course site; students see a hostname,
a topic, and `course/assignments/a03-collect.py`.

```
tep-stream ──stdout NDJSON──▶ bridge.py ──MQTT/ws──▶ mosquitto ──wss:443──▶ nginx ──▶ student
 (Rust, no                    (paho, the             (127.0.0.1              (already
  network code)                only writer)           :9001)                  on the Pi)
```

The simulator has no network code in it at all: it writes lines to stdout, and
carrying them is the bridge's problem. That split is why the fault schedule and
the delivery model can be tested without a broker running, which is most of
what made the numbers below cheap to measure.

## Two clocks, and why they diverge

Every record carries an OPC UA
[`DataValue`](https://reference.opcfoundation.org/Core/Part4/v105/docs/7.11):
a value, a `StatusCode`, and a `SourceTimestamp`. The message around them is
Sparkplug-shaped: a rolling `seq`, a message `timestamp`, and `isHistorical`.
The message `timestamp` is the OPC UA `ServerTimestamp` for every `DataValue`
in the batch, carried once rather than fifty-three times, because a batch is
forwarded as a unit.

The plant keeps its own clock and runs it 144 times faster than the wall clock,
so ten minutes of collecting is a full plant day, and after an hour the plant
clock is six days past where it started. They are different clocks and
subtracting one from the other is meaningless. The birth message publishes
`accelerationFactor` and `plantEpoch` so a reader can convert. Event-time
reasoning happens entirely in the plant clock; the collector's `receivedAt` is
the only wall-clock stamp in the pipeline.

The third clock is the student's. `a03-collect.py` stamps `receivedAt` on each
landed message, which is what an OPC UA chain does anyway: each server in the
chain applies its own timestamp and the `SourceTimestamp` never changes.

## Sampled analysers, and ragged tags

`XMEAS(23..41)` are composition analysers, not instruments. They read on a
schedule (0.1 h for the two gas analysers, 0.25 h for the product one) and each
reports the composition from its *previous* sample. So an analyser tag's
`SourceTimestamp` lags the message it arrives in by up to a full analyser
interval, and holds still in between while the continuous tags move every
sample.

The publisher does not model that schedule; it detects it. The reported value
is latched between due times, so a change in the value *is* an update, exactly,
with no schedule arithmetic to get wrong. At 180-second sampling the fourteen
gas channels, on a 360-second interval, alternate between a lag of 0 and 180 s,
and the five product channels, on a 900-second interval, cycle 0, 180, ... 720
s. Measured over 6,000 messages that is a mean of 161 s across the nineteen,
which is exactly what those two duty cycles predict.

A student who assumes one timestamp per message gets the nineteen composition
channels wrong by up to twelve minutes, and every one of those channels is a
composition, so the error lands squarely on the variables a fault-detection
model would lean on.

## The delivery model

A per-message coin flip would scatter late records evenly through the stream,
which is not how a link fails. This models the link instead: it goes down, the
publisher buffers into a bounded queue, and when it comes back the backlog
drains alongside the live stream at a few messages per sample. Late data
therefore arrives in bursts, and the worst case a watermark has to tolerate is
the length of an outage rather than an average delay.

Measured over 6,000 messages at the defaults:

| | |
|---|---|
| records arriving after a newer one | 13.6% |
| lateness, plant minutes | median 51, p95 117, max 198 |
| samples never delivered at all | 20 in 5,961 |
| duplicate deliveries | 59 |
| `Uncertain` / `Bad` status codes | 648 / 146 in 318,000 |
| bytes per message | 6,194 (53 tags), about 3 MB per ten-minute collection |

`isHistorical` is honest: every late record carries it and every record
carrying it is late. That is what a well-behaved Sparkplug publisher does, and
it does not make the assignment trivial, because knowing a record is late does
not tell you what to do with it.

## The fault schedule

Exactly one fault episode per 12 plant hours, drawn from a seed, onset in the
first 7.5 hours of the block and lasting 1.5 to 4 hours. So any 12-hour window
contains at least one onset, whenever a student happens to run. At 144x a
block is five minutes of collecting, so the ten-minute collection the assignment
asks for spans two episodes wherever in the plant day it starts. The schedule is driven from the plant
clock through `request_disturbance` rather than through a `Scenario` schedule,
which holds 32 events and would run out after a day and a half.

Two of the twenty disturbances are excluded, for different reasons.

**IDV(6)**, a total loss of A feed, walks the plant into a shutdown.

**IDV(7)** is the interesting one. The plant rides it out fine and then trips
on reactor pressure about half an hour *after it clears*, because restoring the
C header pressure in one step over-pressures a reactor whose controllers have
wound up against the loss. No published TEP dataset shows this: they all start
a fault and run to the end of the file without ever switching one off. It was
found by running the schedule for 600 plant hours and noticing that all three
trips were IDV(7) and all three were after the clear, not during it.

With both excluded, the plant trips at most once per 3,000 plant hours across
four seeds, which is a hundred hours of wall clock. When it does trip the
publisher restarts it and emits a `restart` event, so the stream carries a real
gap and a marker rather than pretending the plant never stopped.

`cargo run --release --bin probe` prints which disturbances survive being
switched on and off; `--bin schedule` prints the episode plan for a seed;
`--bin trips` measures the trip rate over a long run.

## Watching it

`viewer.html` is a browser view of the live stream: open the file, no server and
no build step. It subscribes anonymously over the same `wss` endpoint students
use, waits for the retained birth message to learn the tag names, and then shows
all fifty-three tags updating with their status codes and their stamp lag. It is
not published to the course site, because a student watching a dashboard is not
collecting a file and A3 is about the file.

Two things it makes visible that a collected file makes you work for. The status
column goes amber and red on its own, and a `Bad_DeviceFailure` metric carries a
null value rather than a number, which is what a failed instrument should report
and what breaks a formatter written on the happy path. The stamp lag column is
empty for the continuous tags and counts up to 720 s on the nineteen composition
analysers, so the ragged timestamps are on screen rather than in a paragraph.

From a shell, `mosquitto_sub` speaks WebSockets from 2.1 onward. The path has to
arrive through `-L` while the topic arrives through `-t`, because the URL form
reads its path as a topic:

```bash
B=wss://kitchin-services.cheme.cmu.edu:443/mqtt

# the tag dictionary, retained, so it arrives immediately
mosquitto_sub -L $B -t plant/tep/birth -C 1 \
  | jq -r '"\(.accelerationFactor)x, \(.tags|length) tags"'

# three samples, three tags each
mosquitto_sub -L $B -t plant/tep/telemetry -C 3 | jq -r \
  '"seq \(.seq) \(.timestamp) late=\(.isHistorical) " +
   ([.metrics[] | select(.name|test("reactor_temperature|reactor_pressure"))]
    | map("\(.name):\(.value)") | join("  "))'
```

Debian's 2.0 line, which the Pi is pinned to for the reason above, has no `--ws`
in its clients, so this works from a laptop and not from the Pi itself. On the
Pi, subscribe with paho instead.

## Reusing it later

A3 uses the stream for collection and then processes the landed file, so
nothing a student writes for A3 runs continuously. The pieces that would make
a genuinely incremental exercise are already here and unused: the publisher
runs forever, the outage model produces late data in bursts rather than on a
per-message coin flip, and `--unpaced --max-samples N` replays twelve plant
days in a couple of seconds, which is what makes a windowing exercise
testable without waiting for wall clock.

Recorded as an option for the mini-project, which is currently a surrogate
model with uncertainty quantification and would need a real redesign rather
than an added task. The smallest version is A3's last stretch item promoted
to graded work: replay the raw file one message at a time through a bounded
buffer and report what a watermark would have emitted and when.

## Access control

There are no per-student credentials, because a hostname and a topic is the
whole thing a student should have to be told. Anonymous clients may read
`plant/#` and do nothing else. One authenticated account, `tep-publisher`, may
write, and it exists so that nobody can inject a fabricated reading into the
stream somebody else is collecting.

## Running it locally

The committed `mosquitto.conf` carries the paths it will have on the Pi, so a
one-time setup rewrites them for a laptop and creates the publisher's password
file. Everything it writes is gitignored.

```bash
stream/broker/dev-setup.sh

# broker
mosquitto -c stream/broker/mosquitto.dev.conf

# publisher, paced at 144x (the defaults: one message per 1.25 s)
cd stream/publisher && cargo run --release \
  | uv run ../bridge/bridge.py

# the student side
uv run --no-project course/assignments/a03-collect.py \
  --host 127.0.0.1 --port 9001 --no-tls --minutes 10
```

`--unpaced --max-samples N` runs the publisher flat out, which is how every
number above was measured: 6,000 messages, twelve plant days, take 2.4 s.

## Deploying it on the Pi

The whole thing is a git clone, a `cargo build --release`, and three config
files. `deploy/` holds the systemd unit and the nginx location block; the
broker configuration is in `broker/`.

One thing will waste an afternoon if nobody writes it down: **Debian's
`mosquitto` package is built without WebSocket support.** Bookworm ships
2.0.11 linked against no libwebsockets at all, so `protocol websockets` makes
the broker log `Unable to start any listening sockets` and exit 1, with no
message naming the actual cause. Install from Eclipse's own repository
instead, which is where the WebSocket-enabled builds live:

```bash
sudo curl -fsSL https://repo.mosquitto.org/debian/mosquitto-repo.gpg \
    -o /etc/apt/keyrings/mosquitto-repo.gpg
echo "deb [signed-by=/etc/apt/keyrings/mosquitto-repo.gpg] https://repo.mosquitto.org/debian bookworm main" \
    | sudo tee /etc/apt/sources.list.d/mosquitto.list
sudo apt-get update && sudo apt-get install mosquitto mosquitto-clients
```

Pin it to the 2.0 line, in `/etc/apt/preferences.d/mosquitto`:

```
Package: mosquitto mosquitto-clients libmosquitto1
Pin: version 2.0.*
Pin-Priority: 1001
```

2.1 replaced libwebsockets with libmicrohttpd and changed configuration
semantics, and an unattended upgrade that silently rewrites how the broker
authenticates students mid-semester is the same hazard that `Cargo.toml` pins
the simulator's revision against.

`broker/mosquitto.conf` goes to `/etc/mosquitto/conf.d/tep.conf`; the password
and ACL files must be owned by `mosquitto` (2.0.22 warns that a future version
will refuse to load them otherwise). The publisher's password is generated on
the Pi into `/etc/tep-stream/publisher.secret`, mode 640, root:tepstream, and
never goes near the repository.

nginx terminates TLS. `deploy/nginx-mqtt.conf` installs as a snippet and is
pulled into the existing 443 server block with a one-line `include`, rather
than by pasting it in, so this file stays the only copy. It sits alongside a
`location /` that proxies an unrelated application: nginx matches the longest
prefix, so `/mqtt` wins for the broker and everything else is untouched.

`bridge.py` needs `paho-mqtt`, and Debian's `python3-paho-mqtt` (1.6.1) is
enough. The bridge detects the 1.x callback API rather than requiring 2.x, so
the Pi needs no virtualenv.

The broker runs with `persistence false`, so it writes nothing to the SD card
and its retained messages live in RAM. The publisher emits the birth message
once at startup and never again, which means a broker restart underneath a
running publisher would drop the tag dictionary for good. Telemetry keeps
arriving, so nothing looks wrong from either end, and every student who
subscribes afterwards gets fifty-three unlabelled numbers and no way to build
the schema A3 asks them for. `Requires=mosquitto.service` does not help:
it propagates a stop, not a restart, and paho reconnects by itself.

The bridge therefore keeps the birth line and republishes it from `on_connect`,
which covers the cases a persistence file would not, among them a `kill -9`, an
OOM kill, a power cut, and a reinstall. Verified by killing the broker under a
running bridge and resubscribing: before the change the birth topic came back
empty while telemetry flowed; after it, the retained message is there again.
