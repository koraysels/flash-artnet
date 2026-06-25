# Snelweg-detectie → strobe (project context)

Kunstinstallatie (Onder Stroom, Ieper). Camera's langs een snelweg, YOLO-detectie
met snelheidsschatting; bij snelheidsovertreders flitst een DMX-stroboscoop.
Drie schermen tonen elk een live, geannoteerde videofeed.

## Topologie
- **Remote site** — GPU-server "Krocky" (Windows, Ryzen 9 + RTX 3060): YOLOv8-detectie +
  ByteTrack/Kalman-tracking + homografie-snelheid op meerdere streams. Aan Tailscale.
  Brandt de detectie-boxes server-side in de video (NVENC H.264).
- **Transport** — Tailscale-mesh. Ieper-kant achter 5G/CGNAT; Tailscale doet de
  NAT-traversal. Verifieer `tailscale ping <peer>` = "direct", niet "relay".
- **Ieper LAN (192.168.0.x)** — 3 Raspberry Pi's + Art-Net-node + strobe:
  - 2× Pi 4: feed A en B (HW H.264-decode via V3D).
  - 1× Pi 5: feed C (software-decode) + strobe-service in de achtergrond.
- **Strobe-keten** — Pi 5 → Art-Net (UDP) → Pknight CR021R @ 192.168.0.111 → DMX → BOTEX SP-1500.

## Latency / flits-timing
Video = gewone HLS via go2rtc/MediaMTX (paar sec buffer = robuuster over 5G).
De flits wordt **zacht uitgelijnd** op het beeld: niet vrij vurend, maar gepland op
`ts + hls_latency_s` (opnametijd + actuele HLS-buffer, beide uit de payload). Zo valt de
flits ongeveer samen met het moment dat de overtreder op de schermen verschijnt. Geen
harde frame-sync — een offset die de buffer compenseert. Klokken via NTP/Tailscale gelijk.

## Twee datastromen vanaf Krocky (nooit vermengen)
1. **Videopad** (pixels, voor mensen): 3× HLS-stream → 3 kiosk-schermen. De kiosk/
   videostream-launcher leeft in een **apart project** (niet dit repo).
2. **Eventpad** (data, voor de strobe): MQTT-snelheidsevents → Pi 5 strobe-service (dit repo).
De strobe triggert op event-data, niet op pixels.

## MQTT-broker (mosquitto)
- Draait als Komodo-stack **`flash-mqtt`** op server **rtx4090-win10**, bereikbaar op
  **`100.71.177.9:1883`** (Tailscale-IP). `eclipse-mosquitto:2`, persistence aan.
- **Auth verplicht** (`allow_anonymous false`): user `flash`, wachtwoord in de Komodo
  `.env` (`MQTT_USER`/`MQTT_PASS`). Anonymous = geweigerd.
- Compose ligt in de repo: `deploy/flash-mqtt.compose.yaml` (reproduceerbaar via Komodo).
- Port staat op alle interfaces (Docker Desktop/WSL2 kan niet op het Tailscale-IP binden);
  publiek internet komt er niet bij (geen port-forward), LAN + Tailscale-peers wel.
- Clients (`strobe_service.py`, `mqtt_strobe.py`, `mqtt_pulse.py`) lezen
  `MQTT_HOST/PORT/USER/PASS` uit env, met deze broker als default.

## MQTT-payload (Krocky publiceert, Pi 5 consumeert)
Topic `krocky/speed`, per getrackt voertuig met stabiele snelheid:
```jsonc
{
  "feed": "A",                 // camera/stream-id
  "location": "E17 km42",      // plaats (context/logging)
  "direction": "AB",           // rijrichting: "AB" | "BA" | null (context/logging)
  "trackId": 1234,             // stabiele ByteTrack-id (dedup)
  "speedKmh": 137.4,           // gedetecteerde snelheid
  "maxSpeedKmh": 120,          // max op DEZE feed (drempel); null -> Pi-fallback. Per camera.
  "ts": 1719230000.0,          // opnametijd (unix epoch)
  "hls_latency_s": 6.0         // actuele HLS-buffer van deze feed (flits-offset)
}
```
NB: camelCase keys (publisher in work/flash), behalve `hls_latency_s`. `maxSpeedKmh` mag null.
- `trackId` is essentieel: de strobe ontdubbelt op `(feed, trackId)` (1 flits per voertuig).
- **Drempel**: `maxSpeedKmh` komt uit de payload (per voertuig). Is die null/afwezig, dan
  valt de Pi terug op één algemene `SPEED_LIMIT_DEFAULT` (120 km/u, env-override).
- **Flits-timing**: gepland op `ts + hls_latency_s` (zie Latency-sectie). Fallback `FLASH_DELAY`.
- Test-trigger los van de detectie: topic `flash/pulse` → `mqtt_strobe.py` vuurt direct
  (zie `mqtt_pulse.py`). Payload optioneel: `{"speed": 230, "duration": 0.5}`.

## Hardware-specifics (BOTEX SP-1500) — fysiek geverifieerd 2026-06-24
- 2-kanaals strobe. Vanaf DMX-adres 10:
  - slot 10 = **Speed/rate** — **0 = uit (geen strobe)**, hoog = sneller. Master-trigger.
  - slot 11 = **Dimmer** (0-255) — fungeert als **shutter/gate**.
- **Flits-burst (productie-aanpak)**: speed op `FLASH_SPEED` (230), dimmer kort vol
  openen (`FLASH_DURATION` 0.5s), dan dimmer + speed terug op 0. Geeft ~2 flitsen per
  trigger — gewenst, en onder de WCAG 3/s grens dankzij cooldown. **LET OP:** de oude
  "speed 0 + dimmer pulse = 1 flits"-truc werkt NIET; speed 0 = lamp helemaal uit.
- Tunen: `uv run live_control.py` (curses TUI, eigen terminal) — f/spatie = flits-puls,
  live speed/dimmer/open-duur regelen.
- Art-Net **universe = 0** (bevestigd: CR021R OUT01 staat op `00`, kabel in OUT01).
  Fysiek herverifiëren kan met `uv run flash_test.py --scan`.

## Veiligheid (NIET weglaten / niet versoepelen)
- **Dedup per (feed, track_id)** + **globale cooldown** (default 1s, afgedwongen op
  vuur-moment) → houdt < 3 flitsen/s, de WCAG/fotosensitiviteits-grens. Publiek
  toegankelijk: waarschuwing aan de ingang.
- **Fail-safe naar 0** bij stop, MQTT-disconnect en linkverlies (software).
- **Hardware-vangnet bij harde kill**: de CR021R kan dit NIET (geen signal-loss-optie in
  het menu — geverifieerd in de manual). Zie `deploy/strobe-failsafe.md` voor de analyse
  + empirische test (gedrag CR021R/SP-1500 bij Art-Net-verlies) en mitigaties.

## Repo-layout
```
flash_test.py        standalone DMX-tester (geen MQTT) - eerst de keten valideren
live_control.py      curses TUI: realtime speed/dimmer/flits tunen (eigen terminal)
mqtt_strobe.py       MQTT-listener (topic flash/pulse) -> Art-Net-flits. Test/los van detectie
mqtt_pulse.py        MQTT-sender: publiceert flits-puls(en) op flash/pulse (test-trigger)
mqtt_speed_test.py   MQTT-sender: fake SpeedEvent op krocky/speed -> test de PRODUCTIE-service
strobe_service.py    productie-service Pi 5: MQTT krocky/speed → drempel → dedup → flits → fail-safe
pyproject.toml       deps (stupidArtnet, paho-mqtt)
uv.lock              vastgepinde versies - meecommitten
deploy/
  strobe.service     systemd-unit (alleen Pi 5), wijst naar .venv-interpreter
  install.sh         strobe-service uitrollen op de Pi 5 (OS/Tailscale al geconfigureerd)
  flash-mqtt.compose.yaml  mosquitto-broker (Komodo-stack flash-mqtt, rtx4090-win10)
  strobe-failsafe.md  analyse + test DMX→0 bij uitval (CR021R heeft geen signal-loss-optie)
DETECTION_PROMPT.md  prompt voor de MQTT-publisher in de Krocky-repo (aparte repo)
```

## Werkconventies (voor Claude Code)
- **uv, nooit pip.** `uv add` / `uv sync` / `uv run`. `uv.lock` meecommitten.
- Op de Pi: `uv sync --python /usr/bin/python3` (systeem-Python, geen managed download).
- **Test de DMX-keten met `flash_test.py`** los van MQTT. Universe is bekend (0);
  `--scan` is enkel nog voor herverificatie, `--hold` checkt kanaal/bekabeling.
  Live tunen van speed/dimmer/flits gaat met `live_control.py`.
- De **veiligheidsinvarianten hierboven blijven staan** bij elke wijziging.
- **Slechts ÉÉN proces mag Art-Net naar de node sturen.** Draait `strobe_service.py`
  (systemd) + tegelijk `mqtt_strobe.py`/`flash_test.py`/`live_control.py`, dan vechten
  hun frames (continue 0 vs flits-255) → lamp blijft donker. Stop de service vóór je een
  los testtool draait: `sudo systemctl stop strobe.service`.
- **Raak de detectie-/tracking-/snelheidslogica niet aan** — die leeft in het aparte
  project `/Users/koraysels/work/flash` (repo `koraysels/flash`, op Krocky). Daar voeg je
  enkel de MQTT-publisher toe (zie DETECTION_PROMPT.md). Dit strobe-repo wijzigt dat nooit.
- OS = Raspberry Pi OS **Bookworm** 64-bit desktop (NIET Trixie: V3D-GPU-hang op Pi 4 +
  wisselvallige Pi Connect-schermdeling medio 2026).

## Status / TODO
- [x] strobe-service + flash_test + kiosk-autostart + uv-packaging
- [x] DMX-keten fysiek gevalideerd (universe 0, OUT01). Flits-model: speed 230 + dimmer-gate 0.5s
- [x] MQTT-broker (mosquitto) live op Komodo (rtx4090-win10, 100.71.177.9, auth) + getest
- [x] End-to-end MQTT → Art-Net → strobe getest (mqtt_pulse.py → mqtt_strobe.py)
- [x] strobe_service.py draait als systemd-service op de Pi 5 (FLASH-PI-02),
      end-to-end geverifieerd via journald (connect + FLITS op fake speed-event)
- [x] Payload uitgebreid: per-feed `max_speed_kmh` (drempel) + `ts`/`hls_latency_s`
      (flits gepland op ts + latency), + location/direction. Consumer aangepast.
- [ ] go2rtc/MediaMTX-config op Krocky (3 feeds, HLS op Tailscale-adres) + meet de
      werkelijke `hls_latency_s` per feed (gaat in de payload)
- [x] MQTT-publisher in `/Users/koraysels/work/flash` draait + echte events stromen binnen
- [x] Volledige keten LIVE end-to-end fysiek bevestigd (echte publisher → flits op de lamp)
- [ ] Hardware-failsafe testen (DMX→0 bij harde kill) — zie `deploy/strobe-failsafe.md`
      (CR021R heeft geen signal-loss-instelling; empirische test + evt. mitigatie)
