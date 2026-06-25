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
(`FLASH-PI-02` → `http://100.71.177.9:8080/display/flash-pi-2`), dus exact dezelfde
regel werkt op elke Pi. Eerst handmatig testen:
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

## Samengevat
| Pi | Clone-map | Draait | Autostart |
|----|-----------|--------|-----------|
| Strobe (Pi 5) | `~/FLASH/flash-artnet` | `strobe_service.py` | systemd (`strobe.service`) |
| Kiosk (scherm) | `~/FLASH/flash-kiosk` | `deploy/kiosk.sh` | labwc `~/.config/labwc/autostart` |
