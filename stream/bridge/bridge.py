# /// script
# requires-python = ">=3.11"
# dependencies = ["paho-mqtt"]
# ///
"""Reads the publisher's NDJSON on stdin and puts each line on a topic.

Kept separate from the simulator so the simulator has no network code in it
at all: it writes lines, and what carries them is somebody else's problem.
"""
import json
import os
import pathlib
import sys

import paho.mqtt.client as mqtt

TOPIC = "plant/tep"
HOST = os.environ.get("TEP_BROKER_HOST", "127.0.0.1")
PORT = int(os.environ.get("TEP_BROKER_PORT", "9001"))
SECRET = pathlib.Path(
    os.environ.get("TEP_PUBLISHER_SECRET", "broker/publisher.secret")
).read_text().strip()

# paho 2.x wants an explicit callback API version and 1.x has never heard of
# one. Debian stable ships 1.6, and supporting both is three lines here
# against a virtualenv on the Pi that somebody has to remember to rebuild.
if hasattr(mqtt, "CallbackAPIVersion"):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
else:  # paho-mqtt 1.x
    client = mqtt.Client(transport="websockets")
client.ws_set_options(path="/mqtt")
# The one authenticated client on the broker. Students connect anonymously and
# can only read; nothing they can do puts a message on these topics.
client.username_pw_set("tep-publisher", SECRET)

# The publisher emits the birth message once, at startup, and never again. The
# broker holds it as a retained message in RAM, because `persistence false`
# keeps the Pi from writing anything to its SD card. So a broker restart while
# the publisher keeps running would drop the tag dictionary permanently, and
# every student who subscribed afterwards would get telemetry they cannot
# decode, with nothing anywhere reporting a fault. Keeping the line here and
# republishing it on connect covers that, and covers the cases a persistence
# file would not: a kill -9, an OOM kill, a power cut, a reinstall.
birth = None


def on_connect(client, userdata, *args):
    if birth is not None:
        client.publish(f"{TOPIC}/birth", birth, qos=1, retain=True)


# paho hands on_connect four arguments in 1.x and five in 2.x, hence *args.
client.on_connect = on_connect
client.connect(HOST, PORT, keepalive=60)
client.loop_start()

sent = 0
for line in sys.stdin:
    line = line.rstrip("\n")
    if not line:
        continue
    kind = json.loads(line).get("type")
    if kind == "birth":
        # Retained, so a subscriber joining mid-stream gets the tag dictionary
        # before it gets a value rather than after the next restart.
        birth = line
        client.publish(f"{TOPIC}/birth", line, qos=1, retain=True)
    elif kind == "event":
        client.publish(f"{TOPIC}/event", line, qos=1)
    else:
        # QoS 0. The delivery layer already models loss on purpose, and a
        # broker redelivering would undo it.
        client.publish(f"{TOPIC}/telemetry", line, qos=0)
    sent += 1
    if sent % 100 == 0:
        print(f"published {sent}", file=sys.stderr)
client.loop_stop()
client.disconnect()
