"""Behavior checks for the public CLI and pure renderer."""

import contextlib
import io
import math
import os
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

import eye

ANSI = re.compile(r"\x1b\[[0-9;]*m")


class RenderTests(unittest.TestCase):
    def test_ten_distinct_color_choices(self):
        names = (
            "purple",
            "blue",
            "cyan",
            "green",
            "lime",
            "yellow",
            "orange",
            "red",
            "pink",
            "white",
        )
        self.assertEqual(set(getattr(eye, "COLORS", {})), set(names))
        frames = [eye.render(80, 32, 0.4, color=name) for name in names]
        self.assertEqual(len(set(frames)), 10)
        self.assertEqual(len({ANSI.sub("", frame) for frame in frames}), 1)

    def test_small_and_large_frames_fit_without_decoration(self):
        for width, height in ((1, 1), (20, 8), (80, 32), (176, 60)):
            for angle in (0, 0.7, math.pi):
                with self.subTest(size=(width, height), angle=angle):
                    frame = eye.render(width, height, angle, mono=True)
                    rows = frame.split("\n")
                    self.assertEqual(len(rows), height)
                    self.assertTrue(all(len(row) == width for row in rows))
                    self.assertTrue(frame.isascii())
                    if width >= 20:
                        self.assertTrue(all(row[0] == row[-1] == " " for row in rows))
                        self.assertNotIn("EYE", frame)
                        self.assertNotIn("NOCTIS", frame)

    def test_rotation_changes_pixels_and_is_repeatable(self):
        first = eye.render(80, 32, 0, mono=True)
        self.assertNotEqual(first, eye.render(80, 32, 0.8, mono=True))
        self.assertEqual(first, eye.render(80, 32, 0, mono=True))


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "eye", *args],
            text=True,
            capture_output=True,
            timeout=5,
        )

    def test_snapshot_is_plain_ascii_without_a_terminal(self):
        result = self.run_cli("--snapshot", "--color", "cyan", "--no-hud")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("\x1b", result.stdout)
        self.assertTrue(result.stdout.isascii())
        self.assertEqual(len(result.stdout.splitlines()), 32)

    def test_colors_can_be_listed_without_a_terminal(self):
        result = self.run_cli("--colors")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.split()), 10)

    def test_invalid_inputs_fail_cleanly(self):
        for args in (
            ("--color", "invalid"),
            ("--fps", "nan"),
            ("--fps", "inf"),
            ("--fps", "0"),
            ("--fps", "121"),
            ("--speed", "-1"),
            ("--speed", "1e308"),
            ("--angle", "nan"),
        ):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)

    def test_animation_requires_a_terminal(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("--snapshot", result.stderr)

    def test_hidden_hud_writes_only_the_eye(self):
        class Console(io.StringIO):
            def isatty(self):
                return True

        output = Console()
        with (
            patch.object(eye, "terminal", contextlib.nullcontext),
            patch.object(eye, "read_keys", return_value="q"),
            patch.object(sys, "stdin", Console()),
            patch.object(sys, "stdout", output),
            patch.dict(os.environ, {"TERM": "xterm"}, clear=True),
        ):
            self.assertEqual(eye.main(["--no-hud"]), 0)
        self.assertNotIn("pause", output.getvalue())
        self.assertNotIn("eye /", output.getvalue())
        self.assertIn("\x1b[38;2;", output.getvalue())


if __name__ == "__main__":
    unittest.main()
