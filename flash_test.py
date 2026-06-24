#!/usr/bin/env python3
"""
flash_test.py - DMX-flits tester voor de BOTEX SP-1500 via Art-Net.
Isoleert het DMX-stuk: GEEN MQTT, GEEN detectie. Test hiermee eerst de
hardware-keten (PC -> Art-Net -> Pknight CR021R -> SP-1500) voor je de rest
aankoppelt.

Draaien:
  uv run flash_test.py --scan          # universe 0 EN 1 flitsen -> welke is het?
  uv run flash_test.py                 # interactief: Enter = flits, q = stop
  uv run flash_test.py --ip 192.168.0.111
  uv run flash_test.py --hold          # dimmer vol AAN (kanaal-/bekabeling-check)
  uv run flash_test.py --burst 5

Fixture: BOTEX SP-1500, 2 kanalen vanaf --address (default 10):
  slot N   = Speed/rate  (0 = uit, hoog = sneller; master-trigger)
  slot N+1 = Dimmer      (0-255; shutter/gate)
Een flits = speed op --speed (230) zetten en de dimmer kort vol openen, dan
beide terug op 0. (Universe is geverifieerd 0; live tunen kan met live_control.py.)
"""

import time
import argparse
from stupidArtnet import StupidArtnet


def make_node(ip, universe):
    return StupidArtnet(ip, universe, 512, 40, even_packet_size=True, broadcast=False)


def flash(node, speed_ch, dimmer_ch, speed, level, duration):
    node.set_single_value(speed_ch, speed)        # rate aan
    node.set_single_value(dimmer_ch, level)       # shutter open
    time.sleep(duration)
    node.set_single_value(dimmer_ch, 0)           # shutter dicht
    node.set_single_value(speed_ch, 0)            # rate uit


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ip", default="192.168.0.111")
    p.add_argument("--universe", type=int, default=0)
    p.add_argument("--address", type=int, default=10, help="DMX-startadres fixture")
    p.add_argument("--speed", type=int, default=230, help="flits-rate (0=uit, hoog=snel)")
    p.add_argument("--level", type=int, default=255)
    p.add_argument("--duration", type=float, default=0.5, help="s dat de dimmer-gate open staat")
    p.add_argument("--burst", type=int, default=0, help="N flitsen, dan stoppen")
    p.add_argument("--cooldown", type=float, default=1.0, help="s tussen flitsen")
    p.add_argument("--hold", action="store_true", help="dimmer vol AAN houden")
    p.add_argument("--scan", action="store_true", help="universe 0 en 1 testen")
    args = p.parse_args()

    speed_ch = args.address
    dimmer_ch = args.address + 1

    universes = [0, 1] if args.scan else [args.universe]
    nodes = {u: make_node(args.ip, u) for u in universes}
    for n in nodes.values():
        n.start()

    def all_safe():
        for n in nodes.values():
            n.set_single_value(dimmer_ch, 0)
            n.set_single_value(speed_ch, 0)

    all_safe()
    print(f"node={args.ip}  speed=slot{speed_ch}  dimmer=slot{dimmer_ch}")
    try:
        if args.hold:
            print(f"Strobe AAN (universe {universes}, speed {args.speed}). Ctrl-C om te stoppen.")
            for n in nodes.values():
                n.set_single_value(speed_ch, args.speed)
                n.set_single_value(dimmer_ch, args.level)
            while True:
                time.sleep(1)

        elif args.scan:
            for u in universes:
                print(f"Flits op universe {u}...")
                flash(nodes[u], speed_ch, dimmer_ch, args.speed, args.level, args.duration)
                time.sleep(args.cooldown)
            print("Welke flitste? Gebruik die universe in strobe_service.py.")

        elif args.burst:
            for i in range(args.burst):
                print(f"Flits {i + 1}/{args.burst}")
                flash(nodes[universes[0]], speed_ch, dimmer_ch, args.speed, args.level, args.duration)
                time.sleep(args.cooldown)

        else:
            print("Enter = flits, q + Enter = stop.")
            while True:
                if input().strip().lower() == "q":
                    break
                flash(nodes[universes[0]], speed_ch, dimmer_ch, args.speed, args.level, args.duration)

    except KeyboardInterrupt:
        pass
    finally:
        all_safe()
        time.sleep(0.1)
        for n in nodes.values():
            n.blackout()
            n.stop()
        print("\nVeilig afgesloten (DMX op 0).")


if __name__ == "__main__":
    main()
