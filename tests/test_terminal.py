"""Terminal state, native input, and interactive lifecycle checks."""

import ctypes
import os
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

import eye


class WindowsBindingsTests(unittest.TestCase):
    def test_special_keys_do_not_become_commands(self):
        chars = iter(["\xe0", "Q", " ", "q", "й"])
        keyboard = types.SimpleNamespace(kbhit=lambda: True, getwch=lambda: next(chars))
        with (
            patch.object(eye.os, "name", "nt"),
            patch.dict(sys.modules, {"msvcrt": keyboard}),
        ):
            self.assertEqual(eye.read_keys(0), "")
            self.assertEqual(eye.read_keys(0), " ")
            self.assertEqual(eye.read_keys(0), "q")
            self.assertEqual(eye.read_keys(0), "й")

    def test_empty_keyboard_does_not_block(self):
        keyboard = types.SimpleNamespace(kbhit=lambda: False)
        with (
            patch.object(eye.os, "name", "nt"),
            patch.dict(sys.modules, {"msvcrt": keyboard}),
        ):
            self.assertEqual(eye.read_keys(0), "")

    def test_console_modes_restored_after_render_or_setup_failure(self):
        class Function:
            def __init__(self, call):
                self.call = call

            def __call__(self, *args):
                return self.call(*args)

        for fail_setup in (False, True):
            modes = {100: 0x01F7, 101: 0x0003}
            original = modes.copy()

            def get_mode(handle, pointer):
                pointer._obj.value = modes[handle]
                return 1

            def set_mode(handle, mode):
                if fail_setup and handle == 100 and mode != original[100]:
                    return 0
                modes[handle] = mode
                return 1

            kernel = types.SimpleNamespace(
                GetConsoleMode=Function(get_mode), SetConsoleMode=Function(set_mode)
            )
            keyboard = types.SimpleNamespace(get_osfhandle=lambda fd: fd + 100)
            with (
                patch.object(eye.os, "name", "nt"),
                patch.dict(sys.modules, {"msvcrt": keyboard}),
                patch.object(ctypes, "WinDLL", return_value=kernel, create=True),
                patch.object(ctypes, "get_last_error", return_value=6, create=True),
                patch.object(
                    ctypes,
                    "WinError",
                    side_effect=lambda code: OSError(code, "setup failed"),
                    create=True,
                ),
                patch.object(sys, "stdin", types.SimpleNamespace(fileno=lambda: 0)),
                patch.object(sys, "stdout", types.SimpleNamespace(fileno=lambda: 1)),
            ):
                with self.assertRaises(OSError if fail_setup else RuntimeError):
                    with eye.console_mode():
                        self.assertEqual(modes[101] & 5, 5)
                        self.assertEqual(modes[100] & 0x246, 0)
                        self.assertEqual(modes[100] & 1, 1)
                        raise RuntimeError("render failed")
            self.assertEqual(modes, original)


@unittest.skipUnless(os.name == "posix", "POSIX pseudo-terminal")
class InteractiveTests(unittest.TestCase):
    def test_pause_color_hud_resize_and_cleanup(self):
        import fcntl
        import pty
        import select
        import signal
        import struct
        import termios
        import time

        def drain(fd, seconds):
            data = b""
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                if select.select([fd], [], [], max(0, end - time.monotonic()))[0]:
                    try:
                        data += os.read(fd, 65536)
                    except OSError:
                        break
            return data

        for exit_mode in ("q", "interrupt", "terminate"):
            with self.subTest(exit=exit_mode):
                master, slave = pty.openpty()
                original = termios.tcgetattr(slave)
                fcntl.ioctl(
                    slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 80, 0, 0)
                )
                proc = subprocess.Popen(
                    [sys.executable, eye.__file__],
                    stdin=slave,
                    stdout=slave,
                    stderr=slave,
                    env={**os.environ, "TERM": "xterm-256color"},
                )
                try:
                    output = drain(master, 0.35)
                    self.assertGreaterEqual(output.count(b"eye /"), 2)
                    os.write(master, b" ")
                    self.assertIn(b"paused", drain(master, 0.18))
                    self.assertEqual(drain(master, 0.22), b"")
                    os.write(master, b"c")
                    self.assertIn(b"eye /", drain(master, 0.15))
                    os.write(master, b"h")
                    hidden = drain(master, 0.15)
                    self.assertTrue(hidden)
                    self.assertNotIn(b"eye /", hidden)
                    os.write(master, b"\x1b[H")  # Home is not H or Escape.
                    self.assertEqual(drain(master, 0.15), b"")
                    self.assertIsNone(proc.poll())
                    os.write(master, b"h")
                    self.assertIn(b"eye /", drain(master, 0.15))
                    fcntl.ioctl(
                        slave, termios.TIOCSWINSZ, struct.pack("HHHH", 16, 45, 0, 0)
                    )
                    self.assertIn(b"\x1b[16;1H", drain(master, 0.18))
                    if exit_mode == "q":
                        os.write(master, b"q")
                    else:
                        proc.send_signal(
                            signal.SIGINT
                            if exit_mode == "interrupt"
                            else signal.SIGTERM
                        )
                    output = drain(master, 0.2)
                    self.assertEqual(proc.wait(timeout=3), 0)
                    self.assertIn(b"\x1b[?25h\x1b[?1049l", output)
                    self.assertEqual(termios.tcgetattr(slave), original)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()
                    os.close(master)
                    os.close(slave)


if __name__ == "__main__":
    unittest.main()
