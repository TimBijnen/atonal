#!/usr/bin/env python3
# run_sim.py - run the Pico twelve-tone firmware on a desktop.
#
#   python3 run_sim.py                 # open a window (needs: pip install pygame)
#   python3 run_sim.py --snapshot 3    # headless: run 3s, write sim_out.png
#
# Window keys:
#   left / right   turn the encoder
#   space          click the encoder button      (hold = "long" = new row)
#   c              clock pulse (CLK in)           r  reset (RST in)
#   d              toggle DIR switch              m  toggle MODE switch
#   esc / close    quit
#
# It drops a fake `machine` and `framebuf` onto the import path and swaps
# the real SPI LCD for an in-memory one. Nothing in the firmware is modified.
import os
import sys
import time
import threading

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SIM_DIR)
sys.path.insert(0, SIM_DIR)                     # machine/framebuf/_font/simdisplay
sys.path.insert(0, ROOT_DIR)                     # the firmware modules

# --- 1. give CPython's `time` the MicroPython tick helpers ---------------
if not hasattr(time, "ticks_ms"):
    time.ticks_ms = lambda: int(time.monotonic() * 1000)
    time.ticks_add = lambda t, d: t + d
    time.ticks_diff = lambda a, b: a - b
    time.sleep_ms = lambda ms: time.sleep(ms / 1000.0)

import simdisplay

W, H = 320, 480
_lcd = {}          # shared handle to the SimLCD once the firmware builds it
sim_app = None


# --- 2. swap the real LCD for the in-memory one --------------------------
import display


def _sim_init():
    lcd = simdisplay.SimLCD(W, H)
    _lcd["lcd"] = lcd
    return display.Screen(lcd)


display.init = _sim_init

import machine                        # the fake one, for driving inputs


# --- 3. run the firmware's main loop on a worker thread ------------------
def _run_firmware():
    global sim_app
    try:
        import main
        sim_app = main.App()
        sim_app.run()
    except Exception:
        import traceback
        traceback.print_exc()
        os._exit(1)


def _start():
    t = threading.Thread(target=_run_firmware, daemon=True)
    t.start()
    for _ in range(500):              # wait for App.__init__ -> display.init
        if "lcd" in _lcd:
            return _lcd["lcd"]
        time.sleep(0.01)
    raise RuntimeError("firmware never initialised the screen")


# --- input helpers: drive the fake pins the firmware registered ----------
import config

_enc_states = [0b00, 0b10, 0b11, 0b01]   # one detent clockwise = +1 (see hw._T)


def _turn_encoder(direction):
    a = machine.pins.get(config.PIN_ENC_A)
    b = machine.pins.get(config.PIN_ENC_B)
    if not a or not b:
        return
    cur = (a.value() << 1) | b.value()
    try:
        idx = _enc_states.index(cur)
    except ValueError:
        idx = 0
    seq = _enc_states if direction > 0 else list(reversed(_enc_states))
    try:
        idx = seq.index(cur)
    except ValueError:
        idx = 0
    for _ in range(4):                # 4 quadrature edges = 1 click
        idx = (idx + 1) % 4
        s = seq[idx]
        a.drive((s >> 1) & 1)
        b.drive(s & 1)


def _pulse(pin_id):
    p = machine.pins.get(pin_id)
    if p:
        p.drive(1)
        p.drive(0)


def _set(pin_id, v):
    p = machine.pins.get(pin_id)
    if p:
        p.drive(v)


def _toggle(pin_id):
    p = machine.pins.get(pin_id)
    if p:
        p.drive(0 if p.value() else 1)


# --- headless snapshot mode ----------------------------------------------
def snapshot_mode(seconds):
    try:
        lcd = _start()
        time.sleep(seconds)
        out = os.path.join(ROOT_DIR, "sim_out.png")
        lcd.write_png(out)
        print("wrote", out)
    except KeyboardInterrupt:
        print("\nInterrupted; exiting simulator.")
        raise SystemExit(0)


# --- windowed mode (pygame) ----------------------------------------------
def window_mode():
    try:
        import pygame
    except ImportError:
        sys.exit("pygame not found. Install it with:  pip install pygame\n"
                 "(or run headless:  python3 run_sim.py --snapshot 3 )")
    try:
        lcd = _start()
        pygame.init()
        screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("atonal - Pico twelve-tone sequencer (sim)")
        surf = pygame.Surface((W, H))
        clock = pygame.time.Clock()
        running = True
        while running:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        running = False
                    elif e.key == pygame.K_LEFT:
                        _turn_encoder(-1)
                    elif e.key == pygame.K_RIGHT:
                        _turn_encoder(+1)
                    elif e.key == pygame.K_SPACE:
                        _set(config.PIN_ENC_SW, 0)    # active low
                    elif e.key == pygame.K_c:
                        _pulse(config.PIN_CLK_IN)
                    elif e.key == pygame.K_r:
                        _pulse(config.PIN_RST_IN)
                    elif e.key == pygame.K_d:
                        _toggle(config.PIN_SW_DIR)
                    elif e.key == pygame.K_m:
                        _toggle(config.PIN_SW_MODE)
                elif e.type == pygame.KEYUP:
                    if e.key == pygame.K_SPACE:
                        _set(config.PIN_ENC_SW, 1)
            if lcd.dirty:
                buf = lcd.snapshot()
                lcd.dirty = False
                img = pygame.image.frombuffer(buf, (W, H), "RGB")
                surf.blit(img, (0, 0))
            screen.blit(surf, (0, 0))
            pygame.display.flip()
            clock.tick(60)
    except KeyboardInterrupt:
        print("\nInterrupted; exiting simulator.")
        raise SystemExit(0)
    finally:
        try:
            pygame.quit()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        if len(sys.argv) >= 2 and sys.argv[1] == "--snapshot":
            snapshot_mode(float(sys.argv[2]) if len(sys.argv) > 2 else 3.0)
        else:
            window_mode()
    except KeyboardInterrupt:
        print("\nInterrupted; exiting simulator.")
        raise SystemExit(0)
