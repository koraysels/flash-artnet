# highway-strobe

Snelweg-detectie → Art-Net DMX-stroboscoop. Bij een snelheidsovertreder (gedetecteerd
door de YOLO-pipeline op Krocky) flitst een BOTEX SP-1500. Drie Raspberry Pi's tonen
elk een live videofeed in kiosk-modus. Volledige context: zie `CLAUDE.md`.

## Keten in het kort

```
Krocky (YOLO + snelheid)
   │  MQTT  topic krocky/speed   (events, geen pixels)
   ▼
mosquitto-broker  100.71.177.9:1883   (Komodo-stack flash-mqtt, auth)
   │  MQTT
   ▼
Pi 5  strobe_service.py  → Art-Net (UDP) → Pknight CR021R @ 192.168.0.111
   │
   ▼
DMX  → BOTEX SP-1500  (universe 0, adres 10)
```

## Vereisten
- [uv](https://docs.astral.sh/uv/) (geen pip)
- DMX-keten: Pknight CR021R Art-Net-node @ `192.168.0.111` + BOTEX SP-1500 op DMX-adres 10
- Bereik tot de MQTT-broker (`100.71.177.9:1883`, via Tailscale)

## Config / secrets
Broker-credentials staan **niet** in de code. Kopieer `.env.example` naar `.env` en vul in:
```bash
cp .env.example .env            # zet MQTT_USER/MQTT_PASS; .env staat in .gitignore
```
Alle scripts laden `.env` automatisch (python-dotenv). Niks gevoeligs wordt gecommit.

## Fixture-feiten (fysiek geverifieerd)
BOTEX SP-1500, 2 DMX-kanalen vanaf adres 10:
- **slot 10 = Speed/rate** — `0` = uit (geen strobe), hoog = sneller. Dit is de master-trigger.
- **slot 11 = Dimmer** — fungeert als shutter/gate.

Eén flits-burst = speed op `230` zetten en de dimmer kort (`0.5s`) vol openen, dan beide
terug op 0. Geeft ~2 flitsen. Art-Net **universe = 0** (CR021R OUT01).

## 1. DMX-keten testen (los van MQTT)
```bash
uv sync
uv run flash_test.py --scan     # herverificatie universe (0 vuurt fysiek)
uv run flash_test.py            # interactief: Enter = flits, q = stop
uv run flash_test.py --hold     # dimmer continu aan (kanaal-/bekabeling-check)
```

Realtime speed/dimmer/flits tunen (curses TUI, in je eigen terminal):
```bash
uv run live_control.py          # f of spatie = flits-puls; pijltjes = speed/dimmer
```

## 2. MQTT-keten testen (zonder detectie)
Twee terminals — een listener die de strobe vuurt, en een sender die pulsen stuurt:
```bash
# terminal 1 — listener (op Pi 5 of een machine met Art-Net-bereik)
uv run mqtt_strobe.py

# terminal 2 — stuur flits-puls(en)
uv run mqtt_pulse.py                       # 1 puls
uv run mqtt_pulse.py --n 5 --interval 2    # 5 pulsen
uv run mqtt_pulse.py --speed 200 --duration 0.3
```
Topic = `flash/pulse`. `mqtt_strobe.py` houdt cooldown (WCAG) + fail-safe naar 0 aan.

## 3. Productie-service (Pi 5)
`strobe_service.py` luistert op `krocky/speed`. Per voertuig: drempel = `maxSpeedKmh`
uit de payload (fallback `SPEED_LIMIT_DEFAULT`, 120 km/u), ontdubbelen op `(feed, trackId)`,
en de flits wordt gepland op `ts + hls_latency_s` zodat hij samenvalt met het gebufferde
HLS-beeld. Config via env (zie `.env.example`); secrets via `.env`.

```bash
uv run strobe_service.py        # handmatig draaien om te testen
```

Een fake speeder publiceren om de drempel-keten te testen (creds uit `.env`):
```bash
uv run python -c "import os, json, time, paho.mqtt.publish as p; \
  from dotenv import load_dotenv; load_dotenv(); \
  p.single('krocky/speed', json.dumps({'feed':'A','location':'test','direction':'AB', \
  'trackId':99,'speedKmh':150.0,'maxSpeedKmh':120,'ts':time.time(),'hls_latency_s':2.0}), \
  hostname=os.environ['MQTT_HOST'], \
  auth={'username':os.environ['MQTT_USER'],'password':os.environ['MQTT_PASS']})"
```
150 > `maxSpeedKmh` 120 → de service plant de flits op `ts + hls_latency_s` (hier ~2s later).
In de log zie je eerst `GEPLAND: ...` en daarna `FLITS: ...`.

## MQTT-broker (mosquitto)
Draait als Komodo-stack **`flash-mqtt`** op rtx4090-win10. Compose ligt in
`deploy/flash-mqtt.compose.yaml`. Auth verplicht (user `flash`); wachtwoord in de Komodo
`.env`. Bereikbaar op `100.71.177.9:1883`.

## Uitrollen op de Pi 5 (strobe)
Aanname: OS (Bookworm) en Tailscale zijn al klaar. De videofeeds draaien via de eigen
kiosk/videostream-launcher (ander project) — dit repo doet enkel de Art-Net/MQTT-strobe
op de Pi 5.

```bash
bash deploy/install.sh          # uv sync + strobe.service installeren/starten
```

Daarna: `systemctl status strobe.service` / `journalctl -u strobe.service -f`.

## Detectiesoftware (aparte repo, op Krocky)
De MQTT-publisher voeg je daar toe — zie `DETECTION_PROMPT.md` voor de prompt.
