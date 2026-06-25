#!/usr/bin/env bash
# kiosk.sh - open een URL fullscreen in Chromium (kiosk) op een Pi.
# Per Pi de juiste feed-URL meegeven. Auto-herstart als Chromium sneuvelt.
#
# Draaien:
#   ./deploy/kiosk.sh "http://<host>:1984/stream.html?src=feedA"
#   KIOSK_URL="http://..." ./deploy/kiosk.sh
#
# Autostart bij login (labwc, Bookworm desktop):
#   mkdir -p ~/.config/labwc
#   echo '~/FLASH/flash-artnet/deploy/kiosk.sh "http://<host>:1984/stream.html?src=feedA" &' \
#     >> ~/.config/labwc/autostart
set -e

URL="${1:-${KIOSK_URL:-}}"
if [ -z "$URL" ]; then
  echo "Gebruik: $0 <url>   (of zet KIOSK_URL)" >&2
  exit 1
fi

# Chromium heet chromium of chromium-browser, afhankelijk van de Pi OS-versie
CHROME="$(command -v chromium-browser || command -v chromium || true)"
if [ -z "$CHROME" ]; then
  echo "Chromium niet gevonden. Installeer: sudo apt install -y chromium-browser" >&2
  exit 1
fi

# Scherm aan (Wayland/labwc); negeer stil als wlr-randr ontbreekt
wlr-randr --output HDMI-A-1 --on 2>/dev/null || true

# Verberg de muiscursor indien onclutter aanwezig is
command -v unclutter >/dev/null && unclutter -idle 0 &

echo ">> Kiosk start: $URL"
while true; do
  "$CHROME" \
    --kiosk --app="$URL" \
    --ozone-platform=wayland --enable-features=UseOzonePlatform \
    --start-fullscreen --noerrdialogs --disable-infobars \
    --disable-session-crashed-bubble --hide-scrollbars \
    --autoplay-policy=no-user-gesture-required \
    --password-store=basic \
    --check-for-update-interval=31536000
  echo ">> Chromium gestopt, herstart over 2s..."
  sleep 2
done
