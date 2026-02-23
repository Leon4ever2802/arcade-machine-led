import time
import math
import colorsys
import threading
import signal
import sys

import select
from apa102_pi.driver import apa102

from evdev import InputDevice, ecodes

# ----------------------------
# CONFIG
# ----------------------------
NUM_LEDS = 30
BRIGHTNESS = 0.3

DEVICE_PATH = "/dev/input/by-id/usb-DragonRise_Inc._Generic_USB_Joystick-event-joystick"
LED_BUTTON_CODE = 292  # BTN_TOP2

strip = apa102.APA102(num_led=NUM_LEDS)

# 0 = Colorful, 1 = Static, 2 = Off
mode = 0
current_mode_type = 0
mode_lock = threading.Lock()

static_colors = [(255, 0, 0), (255, 255, 0), (0, 255, 0), (0, 255, 255), (0, 0, 255), (255, 0, 255)]

running = True


# ----------------------------
# CLEANUP
# ----------------------------
def cleanup(signum=None, frame=None):
    global running
    print("Service stopping, turning off LEDs...")
    running = False
    strip.clear_strip()
    strip.show()
    sys.exit(0)


signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)


# ----------------------------
# HELPER
# ----------------------------
def hsv_color(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


# ----------------------------
# EFFECTS
# ----------------------------
def rainbow(step):
    for pixel in range(NUM_LEDS):
        hue = (pixel / NUM_LEDS + step) % 1.0
        r, g, b = hsv_color(hue)
        strip.set_pixel(pixel, r, g, b)
    strip.show()


def breathe_outwards(t, base_hue):
    center = (NUM_LEDS - 1) / 2
    breath = (math.sin(t) + 1) / 2
    base_r, base_g, base_b = hsv_color(base_hue)
    for pixel in range(NUM_LEDS):
        dist = abs(pixel - center)
        falloff = max(0.0, 1.0 - (dist / center))
        brightness = breath * falloff
        r = int(base_r * brightness)
        g = int(base_g * brightness)
        b = int(base_b * brightness)
        strip.set_pixel(pixel, r, g, b)
    strip.show()


def scanner(position, hue):
    strip.clear_strip()
    main_r, main_g, main_b = hsv_color(hue)
    pos = int(position) % NUM_LEDS
    strip.set_pixel(pos, main_r, main_g, main_b)
    for offset in range(1, 6):
        fade = max(0.0, 1.0 - (offset / 6))
        r = int(main_r * fade)
        g = int(main_g * fade)
        b = int(main_b * fade)
        if pos - offset >= 0:
            strip.set_pixel((pos - offset), r, g, b)
        if pos + offset < NUM_LEDS:
            strip.set_pixel((pos + offset), r, g, b)
    strip.show()


# ----------------------------
# INPUT THREAD (nur BTN_BASE5)
# ----------------------------
def input_listener():
    global mode, current_mode_type, running
    device = InputDevice(DEVICE_PATH)
    last_press = 0
    last_release = 0

    while running:
        read, write, execute = select.select([device], [], [], 0.01)

        if device not in read:
            continue

        try:
            for event in device.read():

                # Alle anderen Buttons ausser LED-Button ignorieren
                if event.type != ecodes.EV_KEY or event.code != LED_BUTTON_CODE:
                    continue

                now = time.time()

                if event.value == 1 and now - last_press > 0.25:
                    last_press = now

                elif event.value == 4 and now - last_release > 0.25:
                    last_release = now

                    if last_release - last_press > 2:
                        with mode_lock:
                            mode = (mode + 1) % 3
                            current_mode_type = 0

                    else:
                        if mode == 0:
                            with mode_lock:
                                current_mode_type = (current_mode_type + 1) % 3
                        elif mode == 1:
                            with mode_lock:
                                current_mode_type = (current_mode_type + 1) % 6

        except OSError as e:
            if e.errno != 11:  # Resource temporarily unavailable
                print("Fehler im Input Listener:", e)


# ----------------------------
# MAIN LOOP
# ----------------------------
def main():
    global mode, current_mode_type, running
    rainbow_step = 0.0
    breath_t = 0.0
    breath_hue = 0.0
    last_breath = 0.0
    scanner_pos = 0.0
    scanner_hue = 0.0

    current_static_color = (0, 0, 0)

    while running:
        with mode_lock:
            current_mode = mode
            current_mode_type = current_mode_type

        if current_mode == 0:
            if current_mode_type == 0:
                rainbow(rainbow_step)
                rainbow_step += 0.002  # Geschwindigkeit Rainbow

            elif current_mode_type == 1:
                breathe_outwards(breath_t, breath_hue)
                current_breath = (math.sin(breath_t) + 1) / 2
                if current_breath < 0.05 <= last_breath:
                    breath_hue += 0.12  # Farbwechsel pro Zyklus
                last_breath = current_breath
                breath_t += 0.06  # Geschwindigkeit Breath

            elif current_mode_type == 2:
                scanner(scanner_pos, scanner_hue)
                scanner_pos += 0.3  # Geschwindigkeit Scanner
                scanner_hue += 0.002  # Farbshift

        elif current_mode == 1 and current_static_color != static_colors[current_mode_type]:
            strip.clear_strip()
            for pixel in range(NUM_LEDS):
                r, g, b = static_colors[current_mode_type]
                strip.set_pixel(pixel, r, g, b)
            strip.show()
            current_static_color = static_colors[current_mode_type]

        elif current_mode == 2 and current_static_color != (0, 0, 0):
            strip.clear_strip()
            strip.show()
            current_static_color = (0, 0, 0)

        time.sleep(0.02)


# ----------------------------
# START
# ----------------------------
if __name__ == "__main__":
    threading.Thread(target=input_listener, daemon=True).start()
    try:
        main()
    except KeyboardInterrupt:
        cleanup()
