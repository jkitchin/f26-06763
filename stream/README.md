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

The plant keeps its own clock and runs it 30 times faster than the wall clock,
so after an hour of collecting, the plant clock is thirty hours past where it
started and the two are a day apart. They are different clocks and subtracting
one from the other is meaningless. The birth message publishes
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
minute.

The publisher does not model that schedule; it detects it. The reported value
is latched between due times, so a change in the value *is* an update, exactly,
with no schedule arithmetic to get wrong. Measured against a 360-second gas
analyser interval at 60-second sampling, the lag cycles 0, 60, ... 300 s with a
mean of 149 s, which is the model.

A student who assumes one timestamp per message gets the nineteen composition
channels wrong by up to fifteen minutes, and every one of those channels is a
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
| lateness, plant minutes | median 17, p95 39, max 66 |
| samples never delivered at all | 20 in 5,961 |
| duplicate deliveries | 59 |
| `Uncertain` / `Bad` status codes | 648 / 146 in 318,000 |
| bytes per message | 6,195 (53 tags), about 11 MB per hour collected |

`isHistorical` is honest: every late record carries it and every record
carrying it is late. That is what a well-behaved Sparkplug publisher does, and
it does not make the assignment trivial, because knowing a record is late does
not tell you what to do with it.

## The fault schedule

Exactly one fault episode per 12 plant hours, drawn from a seed, onset in the
first 7.5 hours of the block and lasting 1.5 to 4 hours. So any 12-hour window
contains at least one onset, whenever a student happens to run. At 30x that is
one episode per 24 minutes of collecting. The schedule is driven from the plant
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

# publisher, paced at 30x
cd stream/publisher && cargo run --release -- --speed 30 \
  | uv run ../bridge/bridge.py

# the student side
uv run --no-project course/assignments/a03-collect.py \
  --host 127.0.0.1 --port 9001 --no-tls --minutes 10
```

`--unpaced --max-samples N` runs the publisher flat out, which is how every
number above was measured: 6,000 messages take about half a second.
