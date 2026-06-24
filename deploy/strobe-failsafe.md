# Strobe fail-safe — DMX naar 0 bij uitval

De strobe is publiek toegankelijk → een vasthangende/continue flits is een
fotosensitiviteits-risico (WCAG: < 3 flitsen/s). Daarom willen we dat de lamp
**altijd** uitgaat als er iets misgaat, op meerdere lagen.

## Laag 1 — Software (KLAAR)
`strobe_service.py` (en `mqtt_strobe.py`) zetten DMX op 0:
- bij nette stop (SIGTERM/SIGINT — systemd gebruikt SIGTERM),
- bij MQTT-disconnect (`on_disconnect` → `set_safe()`),
- en de flits zelf sluit de dimmer + speed na `FLASH_DURATION` weer op 0.

Dekt: service-crash, netjes stoppen, broker/link weg. Dekt **niet**: harde kill
van de Pi (stroomuitval, freeze, kabel eruit) — dan vertrekken er geen 0-frames meer.

## Laag 2 — Hardware (node) — NIET BESCHIKBAAR op de CR021R
Onderzocht in de CR021R-manual (Ver1.0, Table 3 "menu presentation for output mode").
Het volledige menu heeft maar 7 items:

| Menu | Item |
|------|------|
| 1 | IP address |
| 2 | Subnet Mask |
| 3 | Output Port universe |
| 4 | Output Port net |
| 5 | Output Port subnet |
| 6 | Ethernet MAC |
| 7 | Default Set |

→ **Er is geen "signal loss" / "hold last" / "blackout na timeout"-optie.** De
Pknight CR021R kan dus niet ingesteld worden om bij Art-Net-verlies zelf naar 0
te gaan. Standaardgedrag bij signaalverlies staat niet in de manual (waarschijnlijk
"hold last frame", typisch voor goedkope nodes) — **moet empirisch getest worden.**

## Het reële risico
Klein tijdvenster: enkel als de Pi **exact tijdens de 0.5s flits-gate** hard sterft
(dimmer=255, speed=230 nog actief) en de node + lamp dat frame vasthouden → continu
strobe. Buiten dat venster staat DMX toch al op 0.

## TODO — empirische test (ter plekke)
1. Start de strobe-service, forceer een flits (fake event) en **trek tijdens de flits
   de netwerkkabel van de Pi** (of kill de Pi hard).
2. Observeer:
   - **Lamp gaat uit** → CR021R of SP-1500 zerot bij signaalverlies. Klaar, geen extra
     hardware nodig. Noteer welk van de twee.
   - **Lamp blijft (continu) flitsen** → hold-last. Mitigatie nodig (zie onder).
3. Herhaal met de lamp in rust (dimmer 0) om te bevestigen dat een 0-frame ook
   vastgehouden wordt (dan is rust-toestand veilig, enkel het flits-venster riskant).

## Mitigaties als het "hold-last" blijkt
- **SP-1500 eigen gedrag**: check of de strobe zelf blackt bij DMX-verlies (sommige
  fixtures doen dat). Als ja → voldoende.
- **Kortere gate**: `FLASH_DURATION` verkleinen verkleint het risicovenster (maar
  raakt het gewenste ~2-flits-effect).
- **Inline DMX-failsafe**: een DMX-merger/failsafe-module die bij DMX-loss naar 0 gaat,
  tussen CR021R en SP-1500. Extra hardware.
- **Aparte node**: een Art-Net-node die signal-loss→0 wél ondersteunt i.p.v. de CR021R.

## Bronnen
- CR021R manual: https://pknight.cc/myfiles/usermanual/CR021R_Manual_book.pdf
