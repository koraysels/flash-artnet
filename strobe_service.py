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

# Snelheidsdrempel - FALLBACK als de payload geen maxSpeedKmh meebrengt.
# De drempel hoort per voertuig in de payload te zitten (maxSpeedKmh); dit is enkel vangnet.
SPEED_LIMIT_DEFAULT = float(os.environ.get("SPEED_LIMIT_DEFAULT", 120))  # km/u

# Flits-offset: vertraag de flits zodat hij samenvalt met het GEBUFFERDE HLS-beeld
# op de schermen. We mikken op event-ts + FLASH_DELAY (event-ts = opnametijd op Krocky).
# Zet dit ~ gelijk aan de HLS-latency (paar sec). Klokken via NTP/Tailscale gelijk houden.
FLASH_DELAY = float(os.environ.get("FLASH_DELAY", 6.0))   # s offset

DEDUP_WINDOW = 10.0   # s: zelfde (feed, track_id) niet opnieuw flitsen binnen dit venster
COOLDOWN     = 1.0    # s: globale min. tijd tussen ECHTE flitsen (>= FLASH_DURATION).
                      #    Houdt < 3 flitsen/s -> WCAG/fotosensitiviteit-grens.

# Verwachte MQTT-payload (JSON) - exact zoals de publisher (work/flash) hem stuurt.
# LET OP: camelCase keys, behalve hls_latency_s. maxSpeedKmh mag null zijn.
#   {
#     "feed": "A",                 # camera/stream-id
#     "location": "E17 km42",      # plaats (logging/context)
#     "direction": "AB",           # rijrichting: "AB" | "BA" | null (logging/context)
#     "trackId": 1234,             # stabiele ByteTrack-id (dedup)
#     "speedKmh": 137.4,           # gedetecteerde snelheid
#     "maxSpeedKmh": 120,          # max op deze feed (drempel); null -> fallback config
#     "ts": 1719230000.0,          # opnametijd (unix epoch) op Krocky
#     "hls_latency_s": 6.0         # actuele HLS-buffer van deze feed; ontbreekt -> FLASH_DELAY
#   }
# Flits-moment = ts + hls_latency_s, zodat de flits samenvalt met het beeld op de schermen.
# -----------------------------------------------------------------------

artnet = StupidArtnet(ARTNET_IP, UNIVERSE, 512, ARTNET_FPS,
                      even_packet_size=True, broadcast=False)
flash_q = queue.Queue(maxsize=1)
recent = {}            # (feed, track_id) -> tijd van laatste flits (dedup)
last_flash = 0.0       # globale laatste ECHTE flits (cooldown)
state_lock = threading.Lock()
fire_lock = threading.Lock()   # beschermt last_flash (Timer-callbacks zijn threads)
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


def maybe_flash(d):
    """Drempel + dedup bij ontvangst; plan de flits uitgelijnd op het beeld.

    max_speed_kmh en hls_latency_s komen uit de payload (per feed),
    met de Pi-config als fallback.
    """
    now = time.time()
    feed = d.get("feed")
    track_id = d.get("trackId")
    speed = float(d["speedKmh"])
    # max-snelheid: payload wint (mag null zijn -> dan fallback per-feed config / default)
    raw_limit = d.get("maxSpeedKmh")
    limit = float(raw_limit) if raw_limit is not None else SPEED_LIMIT_DEFAULT
    if speed <= limit:                               # onder de drempel: niks
        return
    key = (feed, track_id)
    if track_id is not None and now - recent.get(key, 0) < DEDUP_WINDOW:
        return                                       # zelfde auto op deze feed, niet opnieuw
    recent[key] = now
    for k in [k for k, t in recent.items() if now - t > DEDUP_WINDOW]:
        recent.pop(k, None)                          # oude entries opruimen
    # Flits uitlijnen op het GEBUFFERDE HLS-beeld: opnametijd (ts) + actuele HLS-latency.
    # hls_latency_s komt uit de payload (per feed, mag ontbreken); FLASH_DELAY = fallback.
    ts = d.get("ts")
    raw_off = d.get("hls_latency_s")
    offset = float(raw_off) if raw_off is not None else FLASH_DELAY
    fire_at = (ts + offset) if ts else (now + offset)
    delay = max(0.0, fire_at - now)
    loc, direction = d.get("location", "?"), d.get("direction", "?")
    print(f"GEPLAND: feed {feed} ({loc} {direction}) track {track_id} "
          f"{speed:.1f} > {limit:.0f} km/u; flits over {delay:.1f}s (hls {offset:.1f}s)",
          flush=True)
    t = threading.Timer(delay, fire_flash, args=(feed, track_id, speed))
    t.daemon = True                                  # blokkeert shutdown niet
    t.start()


def fire_flash(feed, track_id, speed):
    """Vuurt de flits op het geplande moment; cooldown (fotosensitiviteit) hier afgedwongen."""
    global last_flash
    if not running:
        return
    with fire_lock:
        now = time.time()
        if now - last_flash < COOLDOWN:              # nooit < cooldown tussen flitsen
            print(f"SKIP (cooldown): feed {feed} track {track_id}", flush=True)
            return
        last_flash = now
    print(f"FLITS: feed {feed} track {track_id} {speed:.1f} km/u", flush=True)
    try:
        flash_q.put_nowait(True)
    except queue.Full:
        pass                                         # loopt al; cooldown vangt de rest


def on_message(client, userdata, msg):
    try:
        maybe_flash(json.loads(msg.payload))
    except (ValueError, KeyError, TypeError):
        pass                                         # ongeldige/onvolledige payload negeren


def on_connect(client, userdata, flags, rc, properties=None):
    print(f"MQTT verbonden (rc={rc}), subscribe '{MQTT_TOPIC}'", flush=True)
    client.subscribe(MQTT_TOPIC)


def on_disconnect(client, userdata, *args):
    print("MQTT disconnect -> fail-safe naar 0", flush=True)
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
    print(f"strobe_service: broker {MQTT_HOST}:{MQTT_PORT}, drempel-fallback "
          f"{SPEED_LIMIT_DEFAULT} km/u, flits-delay fallback {FLASH_DELAY}s, "
          f"Art-Net {ARTNET_IP} u{UNIVERSE}", flush=True)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_forever()


if __name__ == "__main__":
    main()
