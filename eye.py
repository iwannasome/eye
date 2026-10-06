#!/usr/bin/env python3
"""A rotating ASCII eyeball. Python standard library only."""

import argparse
import math
import os
import select
import shutil
import signal
import sys
import time
from contextlib import contextmanager
from functools import lru_cache


RAMP = " .,:;=+*#%@"
BACKGROUND = "\x1b[48;2;5;3;12m"


def make_palette():
    gradients = (
        ((17, 10, 33), (153, 107, 220)),   # distant halo / orbits
        ((30, 16, 54), (182, 147, 220)),   # matte violet sphere
        ((49, 18, 79), (168, 105, 213)),   # iris filaments
        ((49, 20, 65), (190, 119, 186)),   # muted inner iris
        ((88, 57, 129), (250, 239, 255)),  # glass highlights
        ((6, 3, 14), (55, 24, 86)),       # pupil
    )
    colors = [(5, 3, 12)]
    for start, end in gradients:
        for step in range(16):
            colors.append(tuple(round(a + (b - a) * step / 15) for a, b in zip(start, end)))
    return tuple(colors)


PALETTE = make_palette()
ANSI = tuple("\x1b[38;2;%d;%d;%dm" % rgb for rgb in PALETTE)


def shade(family, value):
    if 1 <= family <= 4:
        value = max(0.0, value) ** 0.65
    return 1 + family * 16 + max(0, min(15, int(value * 15)))


@lru_cache(maxsize=4)
def geometry(width, height):
    radius = max(0.5, min(width / 6.5, height / 3.15))
    center_x, center_y = (width - 1) / 2, (height - 1) / 2 + 0.5
    surface, stars = [], []
    for row in range(height):
        y = (center_y - row) / radius
        for col in range(width):
            x = (col - center_x) / (radius * 2)
            r2 = x * x + y * y
            if r2 < 1:
                surface.append((col, row, x, y, math.sqrt(1 - r2)))
    for index in range(max(8, width * height // 90)):
        col = (index * 97 + index * index * 31 + 17) % max(1, width)
        row = (index * 47 + index * index * 13 + 7) % max(1, height)
        if ((col - center_x) / (2 * radius)) ** 2 + ((row - center_y) / radius) ** 2 > 1.7:
            stars.append((col, row, index))
    return radius, center_x, center_y, surface, stars


def scene(width, height, angle, eco=False, hud=True, spin=False):
    """Return ASCII cells and palette indices; only the geometry is cached."""
    chars = [[" "] * width for _ in range(height)]
    colors = [[0] * width for _ in range(height)]
    radius, center_x, center_y, surface, stars = geometry(width, height)

    def put(col, row, char, color):
        if 0 <= col < width and 0 <= row < height:
            chars[row][col], colors[row][col] = char, color

    def label(row, text, color):
        if len(text) <= width - 4:
            left = (width - len(text)) // 2
            for index, char in enumerate(text):
                put(left + index, row, char, color)

    for col, row, index in stars:
        pulse = 0.5 + 0.5 * math.sin(angle * 0.9 + index * 2.7)
        put(col, row, "+" if pulse > 0.97 and index % 5 == 0 else ".", shade(0, 0.12 + 0.30 * pulse))

    def orbit(front, ring):
        rotation = (-0.38 if ring == 0 else 0.75) + 0.12 * math.sin(angle * 0.3)
        cr, sr = math.cos(rotation), math.sin(rotation)
        count = max(80, int(radius * (22 if not eco else 14)))
        for index in range(count):
            t = math.tau * index / count
            x, y = 1.48 * math.cos(t), 0.72 * math.sin(t)
            z = 1.29 * math.sin(t)
            if (z >= 0) != front:
                continue
            xx, yy = x * cr - y * sr, x * sr + y * cr
            phase = (t - angle * (0.65 if ring == 0 else -0.43)) % math.tau
            trail = max(0.0, 1 - phase / 0.48)
            brightness = (0.38 if front else 0.19) + trail * 0.25
            dx, dy = -1.48 * math.sin(t), 0.72 * math.cos(t)
            dx, dy = 2 * (dx * cr - dy * sr), -(dx * sr + dy * cr)
            stroke = "|" if abs(dy) > abs(dx) * 1.5 else ("-" if abs(dy) < abs(dx) * 0.25 else ("/" if dx * dy < 0 else "\\"))
            char = "@" if trail > 0.96 else ("*" if trail > 0.72 else (stroke if front else "."))
            col = round(center_x + xx * radius * 2)
            row = round(center_y - yy * radius)
            put(col, row, char, shade(3 if trail > 0.72 else 0, brightness))

    orbit(False, 0)
    if not eco:
        orbit(False, 1)
    yaw = angle if spin else 0.52 * math.sin(angle * 0.64)
    pitch = 0.17 * math.sin(angle * 0.43)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    roll = angle * 0.2
    pupil = 0.205 + 0.022 * math.sin(angle * 1.2)
    for col, row, x, y, z in surface:
        u, v0, w0 = cy * x - sy * z, y, sy * x + cy * z
        v, w = cp * v0 + sp * w0, -sp * v0 + cp * w0
        rho = math.hypot(u, v)
        phi = math.atan2(v, u) + roll
        light = max(0.0, -0.40 * x + 0.55 * y + 0.733 * z)
        rim = (1 - z) ** 2
        brightness = 0.12 + 0.58 * light + 0.12 * rim
        family = 1
        # Subtle flowing veins rather than noisy random text.
        vein = abs(math.sin(phi * 11 + rho * 7 + 0.7 * math.sin(rho * 19)))
        if vein < 0.065 and rho > 0.66:
            brightness *= 0.61
        if w > 0 and rho < 0.65:
            family = 2
            fiber = (math.sin(phi * 81 + rho * 26 + math.sin(phi * 13))
                     + 0.5 * math.sin(phi * 143 - rho * 31)) / 1.5
            rings = math.sin(rho * 73 + 0.9 * math.sin(phi * 9))
            brightness = (0.44 + 0.22 * fiber + 0.07 * rings) * (0.65 + 0.45 * light)
            if rho > 0.59:
                brightness *= 0.42
            elif rho > 0.565:
                brightness, family = 0.80, 2
            if pupil < rho < pupil + 0.09:
                family = 3
                brightness = 0.62 + 0.24 * fiber
            if rho < pupil:
                family = 5
                brightness = 0.05 + 0.12 * (rho / pupil) ** 5
        specular = max(0.0, -0.25 * x + 0.36 * y + 0.899 * z) ** 190
        if specular > 0.10 and family != 5:
            brightness = min(0.78, brightness + specular * 0.10)
        brightness = min(1.0, max(0.0, brightness))
        density = brightness ** 0.75 if family in (2, 3) else brightness
        char = RAMP[min(len(RAMP) - 1, max(1, round(density * (len(RAMP) - 1))))]
        if family == 5:
            char = " " if brightness < 0.12 else "."
        put(col, row, char, shade(family, brightness))
    orbit(True, 0)
    if not eco:
        orbit(True, 1)

    if hud and width >= 44 and height >= 18:
        edge = shade(0, 0.38)
        for col in (2, width - 3):
            for row in (1, height - 2):
                put(col, row, "+", edge)
                inward = 1 if col == 2 else -1
                for offset in range(1, 6):
                    put(col + offset * inward, row, "-", edge)
                put(col, row + (1 if row == 1 else -1), "|", edge)
        label(1, "N O C T I S", shade(4, 0.85))
        if height >= 28:
            label(3, "T H E   V I O L E T   E Y E", shade(0, 0.47))
        label(height - 2, "[  V I O L E T   O B S E R V E R  ]", shade(0, 0.62))
    return chars, colors


def render(width, height, angle, color=False, eco=False, hud=True, spin=False):
    chars, colors = scene(width, height, angle, eco, hud, spin)
    if not color:
        return "\n".join("".join(row) for row in chars)
    rows = []
    for row, shades in zip(chars, colors):
        line, previous = [BACKGROUND], None
        for char, tone in zip(row, shades):
            if char != " " and tone != previous:
                line.append(ANSI[tone])
                previous = tone
            line.append(char)
        rows.append("".join(line) + "\x1b[0m")
    return "\n".join(rows)


@contextmanager
def console_mode():
    """Enable native keyboard/ANSI support, restoring the original modes."""
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetConsoleMode.restype = wintypes.BOOL
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.SetConsoleMode.restype = wintypes.BOOL
        saved = []
        try:
            for stream, is_output in ((sys.stdout, True), (sys.stdin, False)):
                handle = msvcrt.get_osfhandle(stream.fileno())
                mode = wintypes.DWORD()
                if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                    raise ctypes.WinError(ctypes.get_last_error())
                # Output: processed output + virtual terminal sequences.
                # Input: Ctrl+C enabled; no echo, line buffering, Quick Edit,
                # or VT input (msvcrt reads native console key events).
                enabled = (mode.value | 0x0005) if is_output else ((mode.value | 0x0081) & ~0x0246)
                if not kernel.SetConsoleMode(handle, enabled):
                    raise ctypes.WinError(ctypes.get_last_error())
                saved.append((handle, mode.value))
            yield
        finally:
            for handle, mode in reversed(saved):
                kernel.SetConsoleMode(handle, mode)
    else:
        import termios
        import tty

        fd = sys.stdin.fileno()
        settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            yield
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, settings)


def read_keys(timeout):
    """Wait without busy-spinning; None means no key, not end of input."""
    if os.name == "nt":
        import msvcrt

        deadline = time.monotonic() + timeout
        while True:
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in ("\x00", "\xe0"):
                    msvcrt.getwch()  # Consume the scan code, not a letter.
                    return b""
                return key.encode("utf-8")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(remaining, 0.01))
    if select.select([sys.stdin], [], [], timeout)[0]:
        return os.read(sys.stdin.fileno(), 64) or b"q"
    return None


@contextmanager
def terminal():
    """Restore cursor, alternate screen, signal handler and keyboard on exit."""
    old_term = signal.getsignal(signal.SIGTERM)

    def terminate(signum, frame):
        raise KeyboardInterrupt

    with console_mode():
        try:
            signal.signal(signal.SIGTERM, terminate)
            sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
            sys.stdout.flush()
            yield
        finally:
            signal.signal(signal.SIGTERM, old_term)
            sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("ожидается положительное конечное число")
    return number


def finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("ожидается конечное число")
    return number


def main():
    parser = argparse.ArgumentParser(description="Вращающийся объёмный ASCII-глаз в терминале.")
    parser.add_argument("--speed", type=positive, default=0.65, help="скорость, рад/с (0.65)")
    parser.add_argument("--fps", type=positive, default=24, help="кадров в секунду, максимум 120 (24)")
    parser.add_argument("--mono", action="store_true", help="без цвета")
    parser.add_argument("--snapshot", action="store_true", help="один кадр 80×32, без ANSI-кодов")
    parser.add_argument("--angle", type=finite, default=0, help="начальный угол в градусах (0)")
    parser.add_argument("--eco", action="store_true", help="экономный режим: до 15 FPS, одна орбита")
    parser.add_argument("--spin", action="store_true", help="полный оборот вместо плавного движения взгляда")
    parser.add_argument("--no-hud", action="store_true", help="скрыть декоративную рамку и надписи")
    args = parser.parse_args()
    angle = math.radians(args.angle)
    if args.snapshot:
        print(render(80, 32, angle, eco=args.eco, hud=not args.no_hud, spin=args.spin))
        return 0
    if not sys.stdout.isatty() or not sys.stdin.isatty() or os.environ.get("TERM") == "dumb":
        parser.error("для анимации нужен интерактивный терминал; для текста используйте --snapshot")
    color = not args.mono and "NO_COLOR" not in os.environ
    paused, previous_state, previous_layout = False, None, None
    eco, hud, spin = args.eco, not args.no_hud, args.spin
    try:
        with terminal():
            last = time.monotonic()
            while True:
                started = time.monotonic()
                if not paused:
                    angle += (started - last) * args.speed
                last = started
                size = shutil.get_terminal_size((80, 36))
                width, height = max(1, size.columns - 1), max(1, size.lines - 2)
                # Cap rendering work in enormous terminals; still center the eye.
                rw, rh = min(width, 112 if eco else 176), min(height, 42 if eco else 60)
                left, top = (width - rw) // 2, (height - rh) // 2
                state = (angle, size, eco, hud, spin, paused)
                if state != previous_state:
                    frame = render(rw, rh, angle, color, eco, hud, spin)
                    layout = (size, rw, rh)
                    base = BACKGROUND if color else ""
                    clear = base + "\x1b[2J" if layout != previous_layout else ""
                    previous_layout, previous_state = layout, state
                    output = clear + "".join(
                        f"\x1b[{top + i + 1};{left + 1}H{line}" for i, line in enumerate(frame.split("\n"))
                    )
                    mode = "PAUSED" if paused else ("ECO" if eco else "LIVE")
                    motion = "gaze" if spin else "spin"
                    status = f"EYE  /  {mode}  |  SPACE pause  E eco  R {motion}  H hud  Q exit"
                    style = (BACKGROUND + ANSI[shade(0, 0.55)]) if color else ""
                    output += f"\x1b[{max(1, size.lines)};1H\x1b[0m{style}\x1b[K{status[:width]}"
                    sys.stdout.write(output)
                    sys.stdout.flush()
                interval = 0.1 if paused else 1 / min(args.fps, 15 if eco else 120)
                timeout = max(0.0, interval - (time.monotonic() - started))
                keys = read_keys(timeout)
                if keys is not None:
                    if b"q" in keys.lower() or b"\x1b" in keys or b"\x03" in keys:
                        break
                    if keys.count(b" ") % 2:
                        paused = not paused
                    if keys.lower().count(b"e") % 2:
                        eco = not eco
                    if keys.lower().count(b"h") % 2:
                        hud = not hud
                    if keys.lower().count(b"r") % 2:
                        spin = not spin
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print(f"Не удалось использовать консоль: {exc}\nЗапустите eye в Windows Terminal, CMD или PowerShell.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
