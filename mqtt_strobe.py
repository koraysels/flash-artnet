#!/usr/bin/env python3
"""
mqtt_strobe.py - MQTT-listener die de BOTEX SP-1500 via Art-Net laat flitsen.

Simpeler dan strobe_service.py: GEEN snelheids-drempel, GEEN track-dedup.
Eén binnenkomend bericht op MQTT_TOPIC = één flits-burst. Bedoeld om de
keten MQTT -> Art-Net -> strobe te testen (samen met mqtt_pulse.py).

Veiligheid blijft staan: globale cooldown (< 3 flitsen/s, WCAG-grens) en
fail-safe naar 0 bij stop / disconnect.

Payload (optioneel, alle velden mogen weg -> defaults):
  {"speed": 230, "duration": 0.5}

Draaien (Pi 5 of testmachine):
  uv run mqtt_strobe.py
  MQTT_HOST=100.71.177.9 MQTT_USER=flash MQTT_PASS=... uv run mqtt_strobe.py
"""

import os
import json
import time
import queue
import signal
import threading
import atexit

import paho.mqtt.client as mqtt
from stupidArtnet import StupidArtnet
from dotenv import load_dotenv

load_dotenv()                   # leest .env (secrets), niet in git

# ---- Config -----------------------------------------------------------
ARTNET_IP   = os.environ.get("ARTNET_IP", "192.168.0.111")  # Pknight CR021R
UNIVERSE    = int(os.environ.get("ARTNET_UNIVERSE", 0))     # OUT01 = 0 (geverifieerd)
ARTNET_FPS  = 40

SPEED_CH    = 10                # fixture-kanaal 1 (Speed/rate); 0 = uit
DIMMER_CH   = 11                # fixture-kanaal 2 (Dimmer = shutter/gate)
FLASH_SPEED = 230               # rate tijdens flits
FLASH_LEVEL = 255               # dimmer-niveau tijdens flits
FLASH_DURATION = 0.5            # s dat de dimmer-gate open staat

MQTT_HOST   = os.environ.get("MQTT_HOST", "100.71.177.9")
MQTT_PORT   = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USER   = os.environ.get("MQTT_USER", "flash")
MQTT_PASS   = os.environ.get("MQTT_PASS", "")              # NOOIT hardcoden - zet in .env
MQTT_TOPIC  = os.environ.get("MQTT_TOPIC", "flash/pulse")

COOLDOWN    = 1.0               # s: globale min. tijd tussen flitsen (WCAG-grens)
# -----------------------------------------------------------------------

artnet = StupidArtnet(ARTNET_IP, UNIVERSE, 512, ARTNET_FPS,
                      even_packet_size=True, broadcast=False)
flash_q = queue.Queue(maxsize=1)
last_flash = 0.0
state_lock = threading.Lock()
running = True


def set_safe():
    """Alles veilig uit: dimmer 0 (shutter dicht) en speed 0 (geen strobe)."""
    with state_lock:
        artnet.set_single_value(DIMMER_CH, 0)
        artnet.set_single_value(SPEED_CH, 0)


def flash_worker():
    while running:
        try:
            speed, duration = flash_q.get(timeout=0.5)
        except queue.Empty:
            continue
        with state_lock:
            artnet.set_single_value(SPEED_CH, speed)         # rate aan
            artnet.set_single_value(DIMMER_CH, FLASH_LEVEL)  # shutter open
        time.sleep(duration)
        with state_lock:
            artnet.set_single_value(DIMMER_CH, 0)            # shutter dicht
            artnet.set_single_value(SPEED_CH, 0)             # rate uit


def trigger(speed, duration):
    global last_flash
    now = time.time()
    if now - last_flash < COOLDOWN:        # fotosensitiviteit: nooit < cooldown
        return
    last_flash = now
    try:
        flash_q.put_nowait((speed, duration))
    except queue.Full:
        pass                               # loopt al; cooldown vangt de rest


def on_message(client, userdata, msg):
    speed, duration = FLASH_SPEED, FLASH_DURATION
    try:
        d = json.loads(msg.payload) if msg.payload else {}
        speed = int(d.get("speed", FLASH_SPEED))
        duration = float(d.get("duration", FLASH_DURATION))
    except (ValueError, TypeError):
        pass                               # ongeldige payload -> defaults
    speed = max(0, min(255, speed))
    duration = max(0.0, min(2.0, duration))
    trigger(speed, duration)


def on_connect(client, userdata, flags, rc, properties=None):
    print(f"MQTT verbonden (rc={rc}), subscribe '{MQTT_TOPIC}'")
    client.subscribe(MQTT_TOPIC)


def on_disconnect(client, userdata, *args):
    set_safe()                             # link weg -> geen blijvende flits


def shutdown(*_):
    global running
    running = False
    set_safe()
    time.sleep(3.0 / ARTNET_FPS)
    artnet.blackout()
    artnet.stop()


def main():
    atexit.register(shutdown)
    signal.signal(signal.SIGTERM, lambda *a: (shutdown(), exit(0)))
    signal.signal(signal.SIGINT, lambda *a: (shutdown(), exit(0)))

    artnet.start()
    set_safe()
    threading.Thread(target=flash_worker, daemon=True).start()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    print(f"Verbinden met {MQTT_HOST}:{MQTT_PORT} ...")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_forever()


if __name__ == "__main__":
    main()
