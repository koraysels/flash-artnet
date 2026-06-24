# Prompt: MQTT-publisher in de detectiesoftware

De detectie + livefeed zijn een **apart project**: `/Users/koraysels/work/flash`
(repo `koraysels/flash`, draait op Krocky). Dit strobe-repo raakt dat NIET aan.
Geef onderstaande prompt aan Claude Code dáár.

---

Voeg een MQTT-publisher toe aan deze YOLO-detectie + snelheidsschatting-app. Raak de
detectie-, tracking- of snelheidslogica NIET aan — voeg enkel een side-channel toe dat
snelheidsevents publiceert.

Eisen:
- Publiceer één MQTT-bericht per voertuig zodra de tracker een stabiele/betrouwbare
  snelheid heeft (gebruik de bestaande ByteTrack track_id). Eén keer per track wanneer
  de schatting confident is (bv. na N consistente frames), niet elk frame.
- Payload (JSON) - alle velden:
  ```jsonc
  {
    "feed": "A",                 // camera/stream-id (= deze instantie, env FEED_ID)
    "location": "E17 km42",      // plaats van de camera (context/logging)
    "direction": "noord",        // rijrichting (context/logging)
    "track_id": 1234,            // stabiele ByteTrack-id (downstream dedup)
    "speed_kmh": 137.4,          // gedetecteerde snelheid
    "max_speed_kmh": 120,        // toegelaten max op DEZE feed/locatie (de drempel)
    "ts": 1719230000.0,          // OPNAMETIJD (unix epoch, seconden) van dit voertuig
    "hls_latency_s": 6.0         // ACTUELE HLS-buffer/latency van deze feed, in seconden
  }
  ```
  Belangrijk:
  - `ts` = het moment van detectie/opname (niet publicatietijd). Downstream plant de flits
    op `ts + hls_latency_s` zodat de flits samenvalt met het gebufferde beeld op de schermen.
    Klokken gelijk houden via NTP/Tailscale.
  - `max_speed_kmh` = de snelheidslimiet per camera/locatie. Verschilt per feed (niet altijd
    120). Mag uit config/env komen (`MAX_SPEED_KMH` per instantie).
  - `hls_latency_s` = de huidige end-to-end latency van go2rtc/MediaMTX voor deze feed. Zo
    exact mogelijk (meet of configureer per feed); de flits-timing hangt hiervan af.
  - `feed`, `location`, `direction` zijn per instantie configureerbaar (env).
- Topic: configureerbaar, default "krocky/speed".
- Broker: mosquitto op `100.71.177.9:1883` (Tailscale-IP, Komodo-stack flash-mqtt).
  Auth verplicht. Via env vars met deze defaults: MQTT_HOST=100.71.177.9, MQTT_PORT=1883,
  MQTT_USER=flash, MQTT_PASS=<zie Komodo flash-mqtt .env>. Anonymous wordt geweigerd, dus
  username_pw_set is verplicht.
- paho-mqtt, non-blocking: één keer connecten bij startup met loop_start(), QoS 0, met
  automatische reconnect. Publiceren mag de detectie-loop NOOIT blokkeren of vertragen —
  broker plat? Event droppen, niet wachten.
- Optionele grove voorfilter tegen verkeer: enkel publiceren als speed_kmh > een lage
  drempel (env MQTT_SPEED_FLOOR, default 0 = alles). De echte limiet staat downstream,
  dus houd deze floor laag of uit.
- Elke draaiende instantie verzorgt één feed; maak de feed-id configureerbaar (env FEED_ID).
- Isoleer alles in een eigen module (mqtt_publisher.py) met een functie
  publish_speed(track_id, speed_kmh, ts), en roep die op één plek aan: waar de snelheid
  van een track definitief/confident wordt. `feed`, `location`, `direction`,
  `max_speed_kmh` en `hls_latency_s` komen uit de config van de instantie.
- Gebruik uv voor dependencies (uv add paho-mqtt), niet pip. Documenteer de env vars in de README.

Let op: "stabiele snelheid" is de sleutel. Publiceer pas wanneer de homografie-snelheid
geconvergeerd is; te vroeg geeft rammelende waarden en valse flitsen. De track_id-dedup
downstream vangt dubbels, maar garbage-in blijft garbage-out.
