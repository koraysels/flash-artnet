#!/usr/bin/env python3
"""
live_control.py - realtime DMX-control voor de BOTEX SP-1500 via Art-Net.
Geen chat, geen MQTT: pure hands-on tuning van speed/dimmer + flits.

Draaien (in je eigen terminal, curses heeft een TTY nodig):
  uv run live_control.py
  uv run live_control.py --ip 192.168.0.111 --universe 0

Model: SPEED = vaste flits-rate (0 = uit), DIMMER = shutter/gate.
Zet speed eenmalig, gate dan per flits met de dimmer (open -> dicht).

Toetsen:
  pijl Links/Rechts : speed  -/+
  pijl Omhoog/Omlaag: dimmer -/+ (handmatig niveau)
  spatie            : GATE - dimmer vol open voor 'open-duur', dan dicht
  f                 : continu open AAN/UIT (dimmer vol vasthouden)
  , / .             : open-duur -/+ (0.05s stappen)
  0                 : blackout (alles 0)
  1                 : dimmer vol (255)
  [ / ]             : stapgrootte -/+
  q                 : stoppen (altijd veilig op 0)

Ch10 = Speed (0 = uit, hoog = snel), Ch11 = Dimmer (0-255).
"""
import time
import curses
import argparse
from stupidArtnet import StupidArtnet

SPEED_CH, DIMMER_CH = 10, 11


def run(stdscr, node):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)

    speed = 230          # vaste flits-rate
    dimmer = 0           # shutter dicht = donker
    step = 16
    open_dur = 0.5       # gate open-tijd per flits
    hold_open = False
    msg = "f of spatie = flits-puls"

    def clamp(v):
        return max(0, min(255, v))

    def push():
        node.set_single_value(SPEED_CH, speed)
        node.set_single_value(DIMMER_CH, 255 if hold_open else dimmer)

    def gate():
        node.set_single_value(SPEED_CH, speed)
        node.set_single_value(DIMMER_CH, 255)
        time.sleep(open_dur)
        node.set_single_value(DIMMER_CH, dimmer)

    push()
    while True:
        stdscr.erase()
        stdscr.addstr(0, 0, "SP-1500 LIVE CONTROL   (q = stop, veilig op 0)")
        stdscr.addstr(2, 0, f"  SPEED  (ch{SPEED_CH}) : {speed:3d}   {'rate' if speed else 'uit'}")
        stdscr.addstr(3, 0, f"  DIMMER (ch{DIMMER_CH}) : {dimmer:3d}   (rust-niveau)")
        stdscr.addstr(4, 0, f"  open-duur      : {open_dur:.2f}s")
        stdscr.addstr(5, 0, f"  continu open   : {'AAN' if hold_open else 'uit'}")
        stdscr.addstr(6, 0, f"  stap           : {step}")
        stdscr.addstr(8, 0, "  f / spatie = FLITS-PULS   <-/-> speed   ^/v dimmer")
        stdscr.addstr(9, 0, "  , . open-duur   t=continu open   0=blackout  1=dimmer vol  [ ]=stap  q=stop")
        if msg:
            stdscr.addstr(11, 0, f"  {msg}")
        stdscr.refresh()

        c = stdscr.getch()
        if c == -1:
            time.sleep(0.02)
            continue
        msg = ""
        if c == curses.KEY_RIGHT:
            speed = clamp(speed + step); push()
        elif c == curses.KEY_LEFT:
            speed = clamp(speed - step); push()
        elif c == curses.KEY_UP:
            dimmer = clamp(dimmer + step); push()
        elif c == curses.KEY_DOWN:
            dimmer = clamp(dimmer - step); push()
        elif c in (ord('f'), ord(' ')):
            gate()
            msg = f"FLITS (gate {open_dur:.2f}s @ speed {speed})"
        elif c == ord(','):
            open_dur = max(0.05, round(open_dur - 0.05, 2))
        elif c == ord('.'):
            open_dur = min(3.0, round(open_dur + 0.05, 2))
        elif c == ord('t'):
            hold_open = not hold_open; push()
        elif c == ord('0'):
            speed = 0; dimmer = 0; hold_open = False; push(); msg = "blackout"
        elif c == ord('1'):
            dimmer = 255; hold_open = False; push(); msg = "dimmer vol"
        elif c == ord('['):
            step = max(1, step - 1)
        elif c == ord(']'):
            step = min(64, step + 1)
        elif c in (ord('q'), 27):
            break


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ip", default="192.168.0.111")
    p.add_argument("--universe", type=int, default=0)
    a = p.parse_args()
    node = StupidArtnet(a.ip, a.universe, 512, 40, even_packet_size=True, broadcast=False)
    node.start()
    node.set_single_value(SPEED_CH, 0)
    node.set_single_value(DIMMER_CH, 0)
    try:
        curses.wrapper(run, node)
    finally:
        node.set_single_value(SPEED_CH, 0)
        node.set_single_value(DIMMER_CH, 0)
        time.sleep(0.1)
        node.blackout()
        node.stop()
        print("Veilig afgesloten (DMX op 0).")


if __name__ == "__main__":
    main()
