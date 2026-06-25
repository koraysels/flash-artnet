#!/usr/bin/env bash
# kiosk.sh - open de feed-URL fullscreen in Chromium (kiosk) op een Pi.
# Auto-herstart als Chromium sneuvelt.
#
# De URL wordt standaard AFGELEID UIT DE HOSTNAME, zodat exact dezelfde regel op
# alle Pi's werkt: FLASH-PI-02 -> .../display/flash-pi-2.
#
# Draaien:
#   ./deploy/kiosk.sh                       # leidt URL af uit hostname
#   ./deploy/kiosk.sh "http://host/pad"     # expliciete URL wint
#   KIOSK_URL="http://..." ./deploy/kiosk.sh
#   KIOSK_BASE="http://host:8080/display/flash-pi-" ./deploy/kiosk.sh   # andere base
#
# Autostart bij login (labwc, Bookworm desktop) - één regel op elke Pi:
#   mkdir -p ~/.config/labwc
#   echo '~/FLASH/flash-kiosk/deploy/kiosk.sh &' >> ~/.config/labwc/autostart
set -e

# Base-URL van de display-server (display-server draait op de rtx4090-bak, Tailscale).
KIOSK_BASE="${KIOSK_BASE:-http://100.71.177.9:8080/display/flash-pi-}"

URL="${1:-${KIOSK_URL:-}}"
if [ -z "$URL" ]; then
  # Leid het feed-nummer af uit de hostname (laatste cijfers, leading zeros weg).
  N="$(hostname | grep -oE '[0-9]+' | tail -1 | sed 's/^0*//')"
  if [ -z "$N" ]; then
    echo "Geen feed-nummer in hostname '$(hostname)'. Geef een URL mee: $0 <url>" >&2
    exit 1
  fi
  URL="${KIOSK_BASE}${N}"
fi

# Chromium heet chromium of chromium-browser, afhankelijk van de Pi OS-versie
CHROME="$(command -v chromium-browser || command -v chromium || true)"
if [ -z "$CHROME" ]; then
  echo "Chromium niet gevonden. Installeer: sudo apt install -y chromium-browser" >&2
  exit 1
fi

# Stille, geldige locale (anders: "Fontconfig warning: ignoring UTF-8")
export LC_ALL="${LC_ALL:-C.UTF-8}"
export LANG="${LANG:-C.UTF-8}"

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
    --check-for-update-interval=31536000 \
    --disable-background-networking --disable-sync \
    --disable-component-update --disable-breakpad \
    --disable-features=Translate,MediaRouter \
    --log-level=3 \
    2>/dev/null
  echo ">> Chromium gestopt, herstart over 2s..."
  sleep 2
done
