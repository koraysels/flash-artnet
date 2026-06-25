#!/usr/bin/env python3
"""
mqtt_speed_test.py - publiceert een fake SpeedEvent op krocky/speed om de
PRODUCTIE-service (strobe_service.py) te triggeren. Test de echte keten:
drempel (maxSpeedKmh) + flits-planning (ts + hls_latency_s).

Payload = exact het publisher-schema (camelCase, hls_latency_s snake_case).

Draaien (creds/host uit .env):
  uv run mqtt_speed_test.py                       # 150 > 120, flits over ~1s
  uv run mqtt_speed_test.py --speed 200 --max 120
  uv run mqtt_speed_test.py --max null            # geen limiet mee -> Pi-fallback 120
  uv run mqtt_speed_test.py --latency 6           # flits over ~6s (echte HLS-latency)
  uv run mqtt_speed_test.py --n 5 --interval 2    # 5 voertuigen
"""

import os
import json
import time
import random
import argparse

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default=os.environ.get("MQTT_HOST", "100.71.177.9"))
    p.add_argument("--port", type=int, default=int(os.environ.get("MQTT_PORT", 1883)))
    p.add_argument("--user", default=os.environ.get("MQTT_USER", "flash"))
    p.add_argument("--password", default=os.environ.get("MQTT_PASS", ""))
    p.add_argument("--topic", default=os.environ.get("MQTT_TOPIC", "krocky/speed"))
    p.add_argument("--feed", default="A")
    p.add_argument("--location", default="testlocatie")
    p.add_argument("--direction", default="AB", help="AB | BA | null")
    p.add_argument("--track", type=int, default=None, help="trackId (default: willekeurig)")
    p.add_argument("--speed", type=float, default=150.0, help="speedKmh")
    p.add_argument("--max", default="120", help="maxSpeedKmh getal, of 'null'")
    p.add_argument("--latency", type=float, default=1.0, help="hls_latency_s (flits-offset)")
    p.add_argument("--n", type=int, default=1, help="aantal voertuigen")
    p.add_argument("--interval", type=float, default=2.0, help="s tussen voertuigen")
    a = p.parse_args()

    direction = None if a.direction.lower() == "null" else a.direction
    max_speed = None if str(a.max).lower() == "null" else float(a.max)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(a.user, a.password)
    client.connect(a.host, a.port, 10)
    client.loop_start()
    try:
        for i in range(1, a.n + 1):
            track_id = a.track if a.track is not None else random.randint(1, 999999)
            event = {
                "feed": a.feed,
                "location": a.location,
                "direction": direction,
                "trackId": track_id,
                "speedKmh": a.speed,
                "maxSpeedKmh": max_speed,
                "ts": time.time(),
                "hls_latency_s": a.latency,
            }
            body = json.dumps(event)
            info = client.publish(a.topic, body, qos=0)
            info.wait_for_publish(timeout=5)
            print(f"[{i}/{a.n}] -> {a.topic}  {body}")
            if i < a.n:
                time.sleep(a.interval)
    finally:
        client.loop_stop()
        client.disconnect()
    print("klaar. Kijk in de strobe-log: GEPLAND ... -> FLITS ...")


if __name__ == "__main__":
    main()
