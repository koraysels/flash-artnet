#!/bin/bash
# install.sh - strobe-service uitrollen op de Pi 5 (uv-native).
#
# AANNAME: Pi OS Bookworm 64-bit + Tailscale zijn AL geconfigureerd. De
# videofeeds draaien via de eigen kiosk/videostream-launcher (ander project) -
# dit repo doet ENKEL de Art-Net/MQTT-strobe op de Pi 5.
#
# Draaien vanuit de repo-root op de Pi 5:  bash deploy/install.sh
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

# 1. uv (indien nog niet aanwezig)
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# 2. venv uit de lockfile, met de systeem-Python (geen managed build downloaden)
uv sync --python /usr/bin/python3

# 2b. .env met broker-credentials (niet in git) - aanmaken indien afwezig
if [ ! -f .env ]; then
  cp .env.example .env
  echo ">> .env aangemaakt uit .env.example - vul MQTT_USER/MQTT_PASS in vóór start!"
fi

# 3. Strobe-service installeren + starten
sudo cp deploy/strobe.service /etc/systemd/system/
# pad + gebruiker in de unit afstemmen op deze machine
sudo sed -i "s#/home/pi/highway-strobe#$REPO_DIR#g; s#^User=pi#User=$USER#" \
  /etc/systemd/system/strobe.service
sudo systemctl daemon-reload
sudo systemctl enable --now strobe.service

echo ">> strobe.service draait. Config (MQTT_HOST/USER/PASS, SPEED_LIMIT) staat in"
echo "   strobe_service.py of via env; na wijziging: sudo systemctl restart strobe.service"
echo ">> Status: systemctl status strobe.service   Logs: journalctl -u strobe.service -f"
