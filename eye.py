#!/usr/bin/env python3
"""just spinning eye in your terminal"""

import argparse
import math
import os
import re
import select
import shutil
import signal
import sys
import time
from contextlib import contextmanager
from functools import lru_cache

__version__ = "0.2.0"
COLORS = {
    "purple": (182, 147, 220),
    "blue": (115, 155, 225),
    "cyan": (105, 200, 210),
    "green": (115, 190, 140),
    "lime": (170, 200, 105),
    "yellow": (215, 195, 110),
    "orange": (225, 160, 100),
    "red": (215, 115, 120),
    "pink": (215, 140, 185),
    "white": (195, 195, 195),
}
RAMP = " .,:;=+*#%@"
BACKGROUND = "\x1b[40m"
RESET = "\x1b[0m"


@lru_cache(maxsize=10)
def palette(color: str) -> tuple[str, ...]:
    """Four muted material ramps: surface, iris, inner rim, pupil."""
    base = COLORS[color]
    codes = []
    for low, high in ((0.12, 1.0), (0.18, 0.95), (0.25, 1.05), (0.02, 0.22)):
        for step in range(16):
            gain = low + (high - low) * step / 15
            rgb = tuple(min(255, round(channel * gain)) for channel in base)
            codes.append("\x1b[38;2;%d;%d;%dm" % rgb)
    return tuple(codes)


@lru_cache(maxsize=4)
def geometry(width: int, height: int) -> tuple:
    """Cache visible sphere normals until the terminal size changes."""
    radius = max(0.5, min(width / 4.4, height / 2.2))
    points = []
    for row in range(height):
        y = (height / 2 - row - 0.5) / radius
        for col in range(width):
            x = (col + 0.5 - width / 2) / (2 * radius)
            squared = x * x + y * y
            if squared < 1:
                points.append((col, row, x, y, math.sqrt(1 - squared)))
    return tuple(points)


def render(
    width: int, height: int, angle: float, *, color: str = "purple", mono: bool = False
) -> str:
    """Render just the eye; no clock, terminal I/O, or random state."""
    chars = [[" "] * width for _ in range(height)]
    shades = [[0] * width for _ in range(height)]
    cy, sy = math.cos(angle), math.sin(angle)
    pitch = 0.17 * math.sin(angle)
    cp, sp = math.cos(pitch), math.sin(pitch)
    pupil = 0.205 + 0.022 * math.sin(angle * 2)
    for col, row, x, y, z in geometry(width, height):
        u, w0 = cy * x - sy * z, sy * x + cy * z
        v, w = cp * y + sp * w0, -sp * y + cp * w0
        rho = math.hypot(u, v)
        phi = math.atan2(v, u) + angle * 0.2
        light = max(0.0, -0.40 * x + 0.55 * y + 0.733 * z)
        brightness = 0.12 + 0.58 * light + 0.12 * (1 - z) ** 2
        family = 0
        vein = abs(math.sin(phi * 11 + rho * 7 + 0.7 * math.sin(rho * 19)))
        if vein < 0.065 and rho > 0.66:
            brightness *= 0.61
        if w > 0 and rho < 0.65:
            family = 1
            fiber = (
                math.sin(phi * 81 + rho * 26 + math.sin(phi * 13))
                + 0.5 * math.sin(phi * 143 - rho * 31)
            ) / 1.5
            rings = math.sin(rho * 73 + 0.9 * math.sin(phi * 9))
            brightness = (0.44 + 0.22 * fiber + 0.07 * rings) * (0.65 + 0.45 * light)
            if rho > 0.59:
                brightness *= 0.42
            elif rho > 0.565:
                brightness = 0.80
            if pupil < rho < pupil + 0.09:
                family, brightness = 2, 0.62 + 0.24 * fiber
            if rho < pupil:
                family, brightness = 3, 0.05 + 0.12 * (rho / pupil) ** 5
        specular = max(0.0, -0.25 * x + 0.36 * y + 0.899 * z) ** 190
        if specular > 0.10 and family != 3:
            brightness = min(0.78, brightness + specular * 0.10)
        brightness = min(1.0, max(0.0, brightness))
        density = brightness**0.75 if family in (1, 2) else brightness
        char = RAMP[max(1, round(density * (len(RAMP) - 1)))]
        if family == 3:
            char = " " if brightness < 0.12 else "."
        chars[row][col] = char
        tone = brightness**0.65 if family != 3 else brightness
        shades[row][col] = family * 16 + int(tone * 15)
    if mono:
        return "\n".join("".join(row) for row in chars)
    codes, rows = palette(color), []
    for row, tones in zip(chars, shades):
        line, previous = [BACKGROUND], None
        for char, tone in zip(row, tones):
            if char != " " and tone != previous:
                line.append(codes[tone])
                previous = tone
            line.append(char)
        rows.append("".join(line) + RESET)
    return "\n".join(rows)


@contextmanager
def console_mode():
    """Enable native keyboard/ANSI support, restoring the original modes."""
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetConsoleMode.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
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
                enabled = (
                    (mode.value | 0x0005)
                    if is_output
                    else ((mode.value | 0x0081) & ~0x0246)
                )
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


def read_keys(timeout: float) -> str:
    """Wait for native console input without busy-spinning."""
    if os.name == "nt":
        import msvcrt

        deadline = time.monotonic() + timeout
        while True:
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in ("\x00", "\xe0"):
                    msvcrt.getwch()  # Discard the scan code of a special key.
                    return ""
                return key
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return ""
            time.sleep(min(remaining, 0.01))
    if not select.select([sys.stdin], [], [], timeout)[0]:
        return ""
    data = os.read(sys.stdin.fileno(), 64)
    if not data:
        return "q"
    if data == b"\x1b" and select.select([sys.stdin], [], [], 0.01)[0]:
        data += os.read(sys.stdin.fileno(), 64)
    # Arrow/function keys must not be mistaken for Q, H, or Escape.
    text = data.decode("utf-8", errors="ignore")
    return re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|O.)", "", text)


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


def finite(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("expected a finite number")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--color", choices=COLORS, default="purple", help="eye color (purple)"
    )
    parser.add_argument("--colors", action="store_true", help="list the ten colors")
    parser.add_argument("--no-hud", action="store_true", help="show only the eye")
    parser.add_argument(
        "--speed",
        type=finite,
        default=0.65,
        help="radians per second, 0 < speed <= 10 (0.65)",
    )
    parser.add_argument(
        "--fps", type=finite, default=24, help="frames per second, 1 to 120 (24)"
    )
    parser.add_argument("--mono", action="store_true", help="disable colors")
    parser.add_argument(
        "--snapshot", action="store_true", help="print one plain-text frame"
    )
    parser.add_argument(
        "--angle", type=finite, default=0, help="initial angle in degrees (0)"
    )
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    if not 0 < args.speed <= 10:
        parser.error("--speed must be greater than 0 and at most 10")
    if not 1 <= args.fps <= 120:
        parser.error("--fps must be between 1 and 120")
    if args.colors:
        print(" ".join(COLORS))
        return 0
    angle = math.radians(args.angle % 360)
    if args.snapshot:
        print(render(80, 32, angle, mono=True))
        return 0
    if (
        not sys.stdout.isatty()
        or not sys.stdin.isatty()
        or os.environ.get("TERM") == "dumb"
    ):
        parser.error("animation needs an interactive terminal; use --snapshot for text")
    mono = args.mono or "NO_COLOR" in os.environ
    hud, paused, color = not args.no_hud, False, args.color
    previous_state = None
    color_names = tuple(COLORS)
    try:
        with terminal():
            last = time.monotonic()
            while True:
                started = time.monotonic()
                if not paused:
                    angle = (angle + (started - last) * args.speed) % (math.tau * 5)
                last = started
                size = shutil.get_terminal_size((80, 34))
                state = (angle, size, color, hud, paused)
                if state != previous_state:
                    width = max(1, min(size.columns - 1, 176))
                    height = max(1, min(size.lines - (2 if hud else 1), 60))
                    left = max(0, (size.columns - 1 - width) // 2)
                    top = max(0, (size.lines - (2 if hud else 1) - height) // 2)
                    frame = render(width, height, angle, color=color, mono=mono)
                    clear = previous_state is None or (size, hud) != (
                        previous_state[1],
                        previous_state[3],
                    )
                    base = "" if mono else BACKGROUND
                    output = (base + "\x1b[2J") if clear else ""
                    output += "".join(
                        f"\x1b[{top + row + 1};{left + 1}H{line}"
                        for row, line in enumerate(frame.split("\n"))
                    )
                    if hud:
                        label = "paused" if paused else color
                        status = (
                            f"eye / {label} / space pause / c color / h hide / q quit"
                        )
                        style = "" if mono else BACKGROUND + palette(color)[9]
                        output += f"\x1b[{max(1, size.lines)};1H{RESET}{style}\x1b[K{status[: max(0, size.columns - 1)]}"
                    sys.stdout.write(output)
                    sys.stdout.flush()
                    previous_state = state
                interval = 0.1 if paused else 1 / args.fps
                keys = read_keys(
                    max(0.0, interval - (time.monotonic() - started))
                ).lower()
                if any(key in keys for key in ("q", "\x1b", "\x03")):
                    break
                if keys.count(" ") % 2:
                    paused = not paused
                if keys.count("h") % 2:
                    hud = not hud
                if "c" in keys:
                    color = color_names[
                        (color_names.index(color) + keys.count("c")) % len(color_names)
                    ]
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print(f"eye: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
