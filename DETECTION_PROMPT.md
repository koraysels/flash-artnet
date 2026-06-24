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
- Payload (JSON):
  {"feed": "<camera/stream id>", "track_id": <int>, "speed_kmh": <float>, "ts": <unix epoch float>}
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
  publish_speed(feed, track_id, speed_kmh), en roep die op één plek aan: waar de snelheid
  van een track definitief/confident wordt.
- Gebruik uv voor dependencies (uv add paho-mqtt), niet pip. Documenteer de env vars in de README.

Let op: "stabiele snelheid" is de sleutel. Publiceer pas wanneer de homografie-snelheid
geconvergeerd is; te vroeg geeft rammelende waarden en valse flitsen. De track_id-dedup
downstream vangt dubbels, maar garbage-in blijft garbage-out.
