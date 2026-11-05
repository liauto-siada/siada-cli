"""Check real composer borders, cursor and reserved rows in a private console."""

import ctypes
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from ctypes import wintypes
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[2] / "siada_cli_ui/tests/fixtures/windows-composer.mjs"


@unittest.skipUnless(sys.platform == "win32", "Windows console API")
class WindowsComposerTests(unittest.TestCase):
    def test_input_borders_cursor_and_bottom_row_remain_owned(self):
        self.run_console_case(False)

    def test_resize_preserves_the_bottom_input_region(self):
        self.run_console_case(True)

    def run_console_case(self, resize):
        if os.environ.get("SIADA_COMPOSER_TEST_CHILD") != "1":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()),
                 f"{type(self).__name__}.{self._testMethodName}"],
                env={**os.environ, "SIADA_COMPOSER_TEST_CHILD": "1"},
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                startupinfo=startup, capture_output=True, text=True, timeout=35,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        class Coord(ctypes.Structure):
            _fields_ = [("x", wintypes.SHORT), ("y", wintypes.SHORT)]

        class Rect(ctypes.Structure):
            _fields_ = [(name, wintypes.SHORT) for name in ("left", "top", "right", "bottom")]

        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.ReadConsoleOutputCharacterW.argtypes = [
            wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, Coord, ctypes.POINTER(wintypes.DWORD),
        ]
        kernel.WriteConsoleOutputCharacterW.argtypes = [
            wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD, Coord, ctypes.POINTER(wintypes.DWORD),
        ]
        kernel.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        kernel.SetConsoleWindowInfo.argtypes = [wintypes.HANDLE, wintypes.BOOL, ctypes.POINTER(Rect)]
        kernel.SetConsoleScreenBufferSize.argtypes = [wintypes.HANDLE, Coord]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        node = shutil.which("node")
        self.assertIsNotNone(node)
        with tempfile.TemporaryDirectory() as log_dir, open("CONOUT$", "wb", buffering=0) as output:
            process = subprocess.Popen([node, str(FIXTURE), sys.executable],
                stdin=subprocess.PIPE, stdout=output, stderr=subprocess.PIPE,
                env={**os.environ, "SIADA_CLI_LOG_DIR": log_dir})
            screen = None
            try:
                initial = json.loads(process.stderr.readline())
                self.assertTrue(initial["everyFrameHasInput"], initial.get("missingFrames"))
                screen = kernel.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None)
                self.assertNotEqual(screen, ctypes.c_void_p(-1).value)

                def row_text(row):
                    text = ctypes.create_unicode_buffer(initial["columns"] + 2)
                    count = wintypes.DWORD()
                    self.assertTrue(kernel.ReadConsoleOutputCharacterW(
                        screen, text, initial["columns"] + 1, Coord(0, row), ctypes.byref(count)))
                    return text.value.rstrip()

                self.assertTrue(any("▸" in row_text(row) for row in range(initial["rows"])))
                frame_rows = initial["rows"]
                if resize:
                    frame_rows = 20
                    rectangle = Rect(0, 0, initial["columns"], frame_rows - 1)
                    self.assertTrue(kernel.SetConsoleWindowInfo(screen, True, ctypes.byref(rectangle)))
                    self.assertTrue(kernel.SetConsoleScreenBufferSize(screen, Coord(initial["columns"] + 1, frame_rows)))
                count = wintypes.DWORD()
                stale = "STALE_BOTTOM"
                self.assertTrue(kernel.WriteConsoleOutputCharacterW(
                    screen, stale, len(stale), Coord(0, frame_rows - 1), ctypes.byref(count)))
                # Focus reports are ignored by the keyboard parser and can also
                # serve as harness signals without changing the input draft.
                process.stdin.write(b"\x1b[I")
                process.stdin.flush()
                updated = json.loads(process.stderr.readline())
                self.assertTrue(updated["everyFrameHasInput"])
                self.assertTrue(updated["stableInputRow"])
                self.assertEqual(updated["rows"], frame_rows)
                input_row = updated["inputRow"]
                self.assertGreater(input_row, frame_rows // 2)
                self.assertIn("DRAFT_MARKER", row_text(input_row))
                self.assertEqual(row_text(input_row - 1), "─" * initial["columns"])
                self.assertEqual(row_text(input_row + 3), "─" * initial["columns"])
                self.assertEqual(row_text(frame_rows - 1), "")
                info = ctypes.create_string_buffer(22)
                self.assertTrue(kernel.GetConsoleScreenBufferInfo(screen, info))
                values = struct.unpack("<11h", info.raw)
                self.assertGreaterEqual(values[3], input_row)
                self.assertLessEqual(values[3], input_row + 2)
                kernel.CloseHandle(screen)
                screen = None
                process.stdin.write(b"\x1b[O")
                process.stdin.flush()
                _, error = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, error.decode("utf-8"))
            finally:
                if screen is not None:
                    kernel.CloseHandle(screen)
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()