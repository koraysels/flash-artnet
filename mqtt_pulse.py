#!/usr/bin/env python3
"""
mqtt_pulse.py - stuurt een flits-puls over MQTT (test-trigger voor mqtt_strobe.py).

Publiceert op MQTT_TOPIC ('flash/pulse'). De listener (mqtt_strobe.py) vuurt
daarop de Art-Net-strobe. Optioneel speed/duration meesturen om live te tunen.

Draaien:
  uv run mqtt_pulse.py                    # 1 puls
  uv run mqtt_pulse.py --n 5 --interval 2 # 5 pulsen, 2s ertussen
  uv run mqtt_pulse.py --speed 200 --duration 0.3
  MQTT_HOST=100.71.177.9 MQTT_USER=flash MQTT_PASS=... uv run mqtt_pulse.py
"""

import os
import json
import time
import argparse

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()                   # leest .env (secrets), niet in git


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default=os.environ.get("MQTT_HOST", "100.71.177.9"))
    p.add_argument("--port", type=int, default=int(os.environ.get("MQTT_PORT", 1883)))
    p.add_argument("--user", default=os.environ.get("MQTT_USER", "flash"))
    p.add_argument("--password", default=os.environ.get("MQTT_PASS", ""))
    p.add_argument("--topic", default=os.environ.get("MQTT_TOPIC", "flash/pulse"))
    p.add_argument("--n", type=int, default=1, help="aantal pulsen")
    p.add_argument("--interval", type=float, default=1.5, help="s tussen pulsen")
    p.add_argument("--speed", type=int, default=None, help="speed-override (0-255)")
    p.add_argument("--duration", type=float, default=None, help="gate-duur override (s)")
    a = p.parse_args()

    payload = {}
    if a.speed is not None:
        payload["speed"] = a.speed
    if a.duration is not None:
        payload["duration"] = a.duration
    body = json.dumps(payload) if payload else "{}"

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(a.user, a.password)
    client.connect(a.host, a.port, 10)
    client.loop_start()
    try:
        for i in range(1, a.n + 1):
            info = client.publish(a.topic, body, qos=0)
            info.wait_for_publish(timeout=5)
            print(f"puls {i}/{a.n} -> {a.topic}  {body}")
            if i < a.n:
                time.sleep(a.interval)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
