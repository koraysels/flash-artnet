#!/usr/bin/env bash
# kiosk.sh - open de feed-URL fullscreen in Chromium (kiosk) op een Pi.
# Auto-herstart als Chromium sneuvelt.
#
# De URL wordt standaard AFGELEID UIT DE HOSTNAME, zodat exact dezelfde regel op
# alle Pi's werkt: hostname FLASH-PI-01 -> .../display/FLASH-PI-01.
# De display-app matcht het laatste pad-segment (uppercase) op de feed; de
# hostname doorgeven is de veiligste keuze (de app accepteert FLASH-PI-1 zowel
# als FLASH-PI-01). We geven 'm dus ONGEWIJZIGD door.
#
# Draaien:
#   ./deploy/kiosk.sh                       # leidt URL af uit hostname
#   ./deploy/kiosk.sh "http://host/pad"     # expliciete URL wint
#   KIOSK_URL="http://..." ./deploy/kiosk.sh
#   KIOSK_BASE="http://host:8080/display/" ./deploy/kiosk.sh   # andere base
#
# Autostart bij login (labwc, Bookworm desktop) - één regel op elke Pi:
#   mkdir -p ~/.config/labwc
#   echo '~/FLASH/flash-kiosk/deploy/kiosk.sh &' >> ~/.config/labwc/autostart
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Base-URL van de display-server (display-server draait op de rtx4090-bak, Tailscale).
KIOSK_BASE="${KIOSK_BASE:-http://100.71.177.9:8080/display/}"

URL="${1:-${KIOSK_URL:-}}"
if [ -z "$URL" ]; then
  # Hostname ONGEWIJZIGD doorgeven; de display-app matcht erop (FLASH-PI-0N).
  HN="$(hostname)"
  if [ -z "$HN" ]; then
    echo "Geen hostname. Geef een URL mee: $0 <url>" >&2
    exit 1
  fi
  URL="${KIOSK_BASE}${HN}"
fi

# Fallback-loader: lokale pagina die de feed in een iframe laadt en bereikbaarheid
# pollt. Server down -> zwart scherm i.p.v. Chrome's error/Cloudflare-pagina.
# De loader wordt via een kleine lokale http-server (localhost) geserveerd, want
# vanaf file:// blokkeert Chromium de health-fetch naar http.
# Uitzetten met KIOSK_FALLBACK=0 (dan opent de feed-URL rechtstreeks).
OPEN_URL="$URL"
if [ "${KIOSK_FALLBACK:-1}" != "0" ] && [ -f "$SCRIPT_DIR/loader.html" ] \
   && command -v python3 >/dev/null; then
  PORT="${KIOSK_PORT:-8099}"
  python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$SCRIPT_DIR" \
    >/dev/null 2>&1 &
  SRV_PID=$!
  trap 'kill "$SRV_PID" 2>/dev/null' EXIT
  ENC="$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$URL")"
  OPEN_URL="http://127.0.0.1:$PORT/loader.html?url=$ENC"
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

# Scherm aan (Wayland/labwc): zet ELK aangesloten scherm aan, dynamisch.
# Sommige Pi's hangen op HDMI, andere op het DSI/ribbon-paneel. We lezen de
# kernel-DRM-status en mappen de connector-naam (card1-HDMI-A-1) op de
# wlr-randr-outputnaam (HDMI-A-1). Zo werkt dezelfde regel op elke Pi.
# Negeer stil als wlr-randr ontbreekt.
if command -v wlr-randr >/dev/null; then
  for s in /sys/class/drm/card*/status; do
    [ "$(cat "$s" 2>/dev/null)" = connected ] || continue
    name="$(basename "$(dirname "$s")")"   # bv. card1-HDMI-A-1 / card1-DSI-1
    out="${name#*-}"                        # -> HDMI-A-1 / DSI-1
    wlr-randr --output "$out" --on 2>/dev/null || true
  done
fi

# Verberg de muiscursor indien onclutter aanwezig is
command -v unclutter >/dev/null && unclutter -idle 0 &

echo ">> Kiosk start: $URL"
[ "$OPEN_URL" != "$URL" ] && echo ">> Via fallback-loader (zwart bij server down)"
while true; do
  "$CHROME" \
    --kiosk --app="$OPEN_URL" \
    --ozone-platform=wayland --enable-features=UseOzonePlatform \
    --start-fullscreen --noerrdialogs --disable-infobars \
    --disable-session-crashed-bubble --hide-scrollbars \
    --autoplay-policy=no-user-gesture-required \
    --password-store=basic \
    --check-for-update-interval=31536000 \
    --disable-background-networking --disable-sync \
    --disable-component-update --disable-breakpad \
    --disable-features=Translate,TranslateUI,MediaRouter,RemotePlayback,GlobalMediaControls,GlobalMediaControlsCastStartStop,Cast \
    --disable-translate --lang=en-US \
    --log-level=3 \
    2>/dev/null
  echo ">> Chromium gestopt, herstart over 2s..."
  sleep 2
done
