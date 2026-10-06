"""Exercise real Windows console modes and keyboard input on the CI runner."""

import ctypes
import sys
from ctypes import wintypes
from unittest.mock import patch

import eye


class Char(ctypes.Union):
    _fields_ = [("UnicodeChar", wintypes.WCHAR), ("AsciiChar", wintypes.CHAR)]


class KeyEvent(ctypes.Structure):
    _fields_ = [
        ("down", wintypes.BOOL),
        ("repeat", wintypes.WORD),
        ("virtual_key", wintypes.WORD),
        ("scan", wintypes.WORD),
        ("char", Char),
        ("control", wintypes.DWORD),
    ]


class Event(ctypes.Union):
    _fields_ = [("key", KeyEvent), ("padding", ctypes.c_byte * 16)]


class InputRecord(ctypes.Structure):
    _fields_ = [("type", wintypes.WORD), ("event", Event)]


def check():
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.AllocConsole()  # It may already have an attached console.
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.WriteConsoleInputW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(InputRecord),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.FlushConsoleInputBuffer.argtypes = [wintypes.HANDLE]
    with open("CONIN$", "r") as stdin, open("CONOUT$", "w") as stdout:
        handles = [msvcrt.get_osfhandle(stream.fileno()) for stream in (stdin, stdout)]

        def modes():
            result = []
            for handle in handles:
                value = wintypes.DWORD()
                if not kernel.GetConsoleMode(handle, ctypes.byref(value)):
                    raise ctypes.WinError(ctypes.get_last_error())
                result.append(value.value)
            return result

        def press(char):
            record = InputRecord()
            record.type = 1  # KEY_EVENT
            record.event.key = KeyEvent(
                True, 1, ord(char.upper()), 0, Char(UnicodeChar=char), 0
            )
            written = wintypes.DWORD()
            if not kernel.WriteConsoleInputW(
                handles[0], ctypes.byref(record), 1, ctypes.byref(written)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            assert written.value == 1

        original = modes()
        with patch.object(sys, "stdin", stdin), patch.object(sys, "stdout", stdout):
            kernel.FlushConsoleInputBuffer(handles[0])
            with eye.terminal():
                press(" ")
                assert eye.read_keys(0.5) == " "
                press("c")
                assert eye.read_keys(0.5) == "c"
            assert modes() == original
            press("q")
            assert eye.main(["--no-hud", "--color", "cyan"]) == 0
            assert modes() == original
            try:
                with eye.terminal():
                    raise KeyboardInterrupt
            except KeyboardInterrupt:
                pass
            assert modes() == original
    print("PASS: native Windows input, rendering, VT modes and cleanup")


if __name__ == "__main__":
    check()
