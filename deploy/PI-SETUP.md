# Pi-setup (van nul)

Volledige uitrol op een Raspberry Pi. Twee rollen, dezelfde repo:
- **Strobe-Pi (Pi 5)** → draait `strobe_service.py` als systemd-service. Clone: `~/FLASH/flash-artnet`.
- **Kiosk-Pi (schermen)** → draait `deploy/kiosk.sh` (Chromium fullscreen). Clone: `~/FLASH/flash-kiosk`.

Een Pi die beide doet (Pi 5 = feed-scherm + strobe) zet gewoon beide clones + autostarts.

---

## 0. Voorwaarden (eenmalig, per Pi)
- Raspberry Pi OS **Bookworm** 64-bit **desktop** (labwc/Wayland).
- **Tailscale** verbonden (`tailscale status` = online; check `tailscale ping <peer>` = direct).
- `sudo raspi-config`:
  - **System Options → Boot/Auto Login → Desktop Autologin** (nodig voor kiosk-autostart).
  - **Display Options → Screen Blanking → Off** (scherm blijft aan).
- `git` aanwezig (`git --version`). `chromium-browser` enkel op kiosk-Pi's
  (`sudo apt install -y chromium-browser`).

---

## 1. SSH-key → GitHub (per Pi)
```bash
ssh-keygen -t ed25519 -C "$(hostname)" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```
Plak die publieke key op **https://github.com/settings/ssh/new**
(Title = de hostname, Key type = Authentication). Test:
```bash
ssh -T git@github.com      # verwacht: "Hi koraysels! You've successfully authenticated"
```
(Repo is publiek; HTTPS-clone kan ook zonder key. SSH = aanrader voor pull-gemak.)

---

## 2. Strobe-Pi (Pi 5) — Art-Net/MQTT-service

```bash
mkdir -p ~/FLASH && cd ~/FLASH
git clone git@github.com:koraysels/flash-artnet.git flash-artnet
cd flash-artnet

# uv installeren (indien nog niet aanwezig)
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; \
  source "$HOME/.local/bin/env"; }

# secrets: .env aanmaken en MQTT_PASS invullen
cp .env.example .env
nano .env                 # zet MQTT_PASS (zie Komodo flash-mqtt .env)

# deps + service installeren/starten (systemd = autostart bij boot)
bash deploy/install.sh
```

`install.sh` doet: `uv sync` → `.env` (blijft) → `strobe.service` installeren →
`enable --now` (start nu + bij elke boot, auto-restart bij crash, fail-safe op stop).

Verifiëren:
```bash
systemctl status strobe.service          # "active (running)"
journalctl -u strobe.service -f          # live logs; verwacht "MQTT verbonden (rc=Success)"
```

Testen zonder echte detectie (lamp flitst fysiek!):
```bash
uv run mqtt_speed_test.py                # fake overtreder -> GEPLAND ... -> FLITS ...
```

Na een code-update:
```bash
cd ~/FLASH/flash-artnet && git pull && sudo systemctl restart strobe.service
```

---

## 3. Kiosk-Pi (scherm) — videofeed fullscreen

```bash
mkdir -p ~/FLASH && cd ~/FLASH
git clone git@github.com:koraysels/flash-artnet.git flash-kiosk
cd flash-kiosk

sudo apt install -y chromium-browser     # indien nog niet aanwezig
```

`deploy/kiosk.sh` leidt de feed-URL af uit de **hostname**
(`FLASH-PI-02` → `http://100.71.177.9:8080/display/FLASH-PI-02`), dus exact dezelfde
regel werkt op elke Pi. De display-app matcht op de hostname; geef 'm dus
ongewijzigd door (niet het kale nummer `flash-pi-2` → lege route → "zwart").
Het script zet ook elk **aangesloten** scherm aan (HDMI óf DSI/ribbon, dynamisch)
en wacht bij boot op de Wayland-socket (anti-flapping). Eerst handmatig testen:
```bash
./deploy/kiosk.sh                        # of: ./deploy/kiosk.sh "http://host/pad"
```

**Autostart bij boot** (labwc) — één regel, identiek op elke kiosk-Pi:
```bash
mkdir -p ~/.config/labwc
echo '/home/flashpi/FLASH/flash-kiosk/deploy/kiosk.sh &' >> ~/.config/labwc/autostart
```
Testen zonder reboot: `sh ~/.config/labwc/autostart` — of gewoon `sudo reboot`.

> Let op: voeg de regel maar **één keer** toe (`cat ~/.config/labwc/autostart` om te checken).
> Dubbel = twee browsers.

Na een update:
```bash
cd ~/FLASH/flash-kiosk && git pull        # daarna reboot of herstart de kiosk
```

---

## Troubleshooting (uit de praktijk)

**Zwart/leeg scherm terwijl de kiosk lijkt te draaien.** Twee onafhankelijke
oorzaken, los uit te sluiten:
- **Verkeerde feed-URL** → display-app rendert een lege route. Check wat chromium
  echt laadt: `tr '\0' '\n' < /proc/$(pgrep -f -- --app | head -1)/cmdline | grep -- --app=`.
  Moet `.../display/$(hostname)` zijn (volle hostname, hoofdletters).
- **Je kijkt via VNC/Pi Connect en de capture is grijs/zwart** terwijl de Pi prima
  draait. De compositor leeft (bewijs: `grim` direct, zie hieronder), maar de
  wayvnc-GPU-capture hing. Fix:
  ```bash
  systemctl --user restart rpi-connect-wayvnc.service rpi-connect.service
  ```

**Sanity-check of de desktop/feed écht rendert (los van VNC):** maak een screenshot
direct uit de compositor-buffer:
```bash
XDG_RUNTIME_DIR=/run/user/$(id -u) WAYLAND_DISPLAY=wayland-0 grim /tmp/shot.png
```
Haal op met `scp`. Toont de echte schermbuffer, ook als VNC grijs is.

> ⚠️ **NOOIT `grim` draaien tegelijk met chromium-GPU-opstart op een Pi 4.**
> De V3D-GPU hangt dan: twee GPU-capture-consumenten tegelijk → processen in
> D-state → load schiet naar 50+ → de Pi is minutenlang onbereikbaar (tot de
> OOM-killer chromium reapt). Test de kiosk dus zonder gelijktijdige `grim`/VNC-grab,
> of grim pas nadat chromium volledig idle is.

**Hoge load vlak na boot is normaal** (chromium-GPU-init); zakt binnen ~1 min.
Een echte hang klimt richting 50+ en blijft. Onderscheid via `uptime` (1/5/15-min avg).

**Reboot via ssh:** sudo is passwordless → gewoon `sudo reboot`. Vermijd het
wachtwoord in de commandline (de `!` in het wachtwoord triggert zsh-history-expansion
lokaal en mangle't het commando).

**Autostart-regel staat er maar één keer in?** `cat ~/.config/labwc/autostart`.
Tijdelijk uitzetten zonder te wissen: regel prefixen met `# DISABLED ` (en weer aan
met `sed -i 's/^# DISABLED //' ~/.config/labwc/autostart`).

---

## Samengevat
| Pi | Clone-map | Draait | Autostart |
|----|-----------|--------|-----------|
| Strobe (Pi 5) | `~/FLASH/flash-artnet` | `strobe_service.py` | systemd (`strobe.service`) |
| Kiosk (scherm) | `~/FLASH/flash-kiosk` | `deploy/kiosk.sh` | labwc `~/.config/labwc/autostart` |
