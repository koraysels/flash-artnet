#!/usr/bin/env python3
"""
Strobe service - Pi 5 (Ieper)
Luistert naar snelheids-events van Krocky (MQTT over Tailscale) en vuurt
een ENKELE flits op de BOTEX SP-1500 via Art-Net -> Pknight CR021R.

Fixture: BOTEX SP-1500, 2 kanalen, DMX-adres 10
  DMX-slot 10 = Speed   (0 = uit/geen strobe, hoog = sneller; rate-kanaal)
  DMX-slot 11 = Dimmer  (0-255, fungeert als shutter/gate)
Flits-model (fysiek geverifieerd 2026-06-24): speed is de master-trigger.
Speed=0 = lamp uit. Voor een korte flits-burst: zet speed op FLASH_SPEED en
open de dimmer (shutter) kort -> FLASH_DURATION; bij speed 230 / 0.5s = ~2
flitsen, daarna dimmer dicht. (De oude "speed 0 + dimmer pulse"-truc werkt
NIET op deze fixture: speed 0 = helemaal geen flits.)

Draaien (Pi 5):  via systemd (deploy/strobe.service) of  uv run strobe_service.py
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

# ---- Config (pas aan) -------------------------------------------------
ARTNET_IP   = "192.168.0.111"   # Pknight CR021R (lokale hop, kruist nooit 5G)
UNIVERSE    = 0                  # geverifieerd: CR021R OUT01 = universe 0
ARTNET_FPS  = 40                # continue DMX-stroom om de waarde vast te houden

SPEED_CH    = 10                # DMX-slot fixture-kanaal 1 (Speed/rate); 0 = uit
DIMMER_CH   = 11                # DMX-slot fixture-kanaal 2 (Dimmer = shutter/gate)
FLASH_SPEED = 230               # rate tijdens flits (fysiek getuned: ~2 flitsen/0.5s)
FLASH_LEVEL = 255               # flits-intensiteit (0-255)
FLASH_DURATION = 0.5            # s dat de dimmer-gate open staat

MQTT_HOST   = os.environ.get("MQTT_HOST", "100.71.177.9")  # Tailscale-IP mosquitto (rtx4090-win10)
MQTT_PORT   = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USER   = os.environ.get("MQTT_USER", "flash")          # broker auth; secrets via .env
MQTT_PASS   = os.environ.get("MQTT_PASS", "")               # NOOIT hardcoden - zet in .env
MQTT_TOPIC  = "krocky/speed"    # Krocky publiceert hier per voertuig
SPEED_LIMIT = 120               # km/u - drempel HIER (niet op Krocky)

DEDUP_WINDOW = 10.0   # s: zelfde track_id niet opnieuw flitsen binnen dit venster
COOLDOWN     = 1.0    # s: globale min. tijd tussen flitsen (>= FLASH_DURATION).
                      #    Houdt < 3 flitsen/s -> WCAG/fotosensitiviteit-grens.

# Verwachte MQTT-payload (JSON), per getrackt voertuig dat Krocky publiceert:
#   {"feed": "A", "track_id": 1234, "speed_kmh": 137.4, "ts": 1719230000.0}
# -----------------------------------------------------------------------

artnet = StupidArtnet(ARTNET_IP, UNIVERSE, 512, ARTNET_FPS,
                      even_packet_size=True, broadcast=False)
flash_q = queue.Queue(maxsize=1)
recent = {}            # track_id -> tijd van laatste flits
last_flash = 0.0       # globale laatste flits (cooldown)
state_lock = threading.Lock()
running = True


def set_safe():
    """Alles veilig uit: dimmer 0 (shutter dicht) en speed 0 (geen strobe)."""
    with state_lock:
        artnet.set_single_value(DIMMER_CH, 0)
        artnet.set_single_value(SPEED_CH, 0)


def flash_worker():
    """Voert flitsen serieel uit zodat de MQTT-callback nooit blokkeert."""
    while running:
        try:
            flash_q.get(timeout=0.5)
        except queue.Empty:
            continue
        with state_lock:
            artnet.set_single_value(SPEED_CH, FLASH_SPEED)   # rate aan
            artnet.set_single_value(DIMMER_CH, FLASH_LEVEL)  # shutter open
        time.sleep(FLASH_DURATION)
        with state_lock:
            artnet.set_single_value(DIMMER_CH, 0)            # shutter dicht
            artnet.set_single_value(SPEED_CH, 0)            # rate uit (geen naloop)


def maybe_flash(track_id, speed):
    global last_flash
    now = time.time()
    if speed <= SPEED_LIMIT:
        return
    if now - last_flash < COOLDOWN:                  # fotosensitiviteit + leesbaarheid
        return
    if track_id is not None and now - recent.get(track_id, 0) < DEDUP_WINDOW:
        return                                       # zelfde auto, niet opnieuw
    recent[track_id] = now
    last_flash = now
    for tid in [t for t, ts in recent.items() if now - ts > DEDUP_WINDOW]:
        recent.pop(tid, None)                        # oude track_ids opruimen
    try:
        flash_q.put_nowait(True)
    except queue.Full:
        pass                                         # loopt al; cooldown vangt de rest


def on_message(client, userdata, msg):
    try:
        d = json.loads(msg.payload)
        maybe_flash(d.get("track_id"), float(d["speed_kmh"]))
    except (ValueError, KeyError, TypeError):
        pass


def on_connect(client, userdata, flags, rc, properties=None):
    client.subscribe(MQTT_TOPIC)


def on_disconnect(client, userdata, *args):
    set_safe()                                       # link weg -> geen blijvende flits


def shutdown(*_):
    global running
    running = False
    set_safe()
    time.sleep(3.0 / ARTNET_FPS)                     # laat een paar 0-frames vertrekken
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
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_forever()


if __name__ == "__main__":
    main()
