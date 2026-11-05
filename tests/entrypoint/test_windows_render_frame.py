"""Replay the actual patched Ink renderer into an isolated native console."""

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from ctypes import wintypes
from pathlib import Path

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "siada_cli_ui/tests/fixtures/windows-render-frame.mjs"
)


@unittest.skipUnless(sys.platform == "win32", "Windows console API")
class WindowsRenderFrameTests(unittest.TestCase):
    def test_streamed_frames_keep_rows_fixed_and_clear_wide_glyph_tails(self):
        if os.environ.get("SIADA_FRAME_TEST_CHILD") != "1":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve())],
                env={**os.environ, "SIADA_FRAME_TEST_CHILD": "1"},
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                startupinfo=startup, capture_output=True, text=True, timeout=25,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return

        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the real renderer test")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        kernel.CreateFileW.restype = wintypes.HANDLE

        class Coord(ctypes.Structure):
            _fields_ = [("x", wintypes.SHORT), ("y", wintypes.SHORT)]

        kernel.ReadConsoleOutputCharacterW.argtypes = [
            wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD,
            Coord, ctypes.POINTER(wintypes.DWORD),
        ]
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]

        def output_state():
            handle = kernel.CreateFileW("CONOUT$", 0x80000000, 3, None, 3, 0, None)
            self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
            try:
                mode = wintypes.DWORD()
                self.assertTrue(kernel.GetConsoleMode(handle, ctypes.byref(mode)))
                return mode.value, kernel.GetConsoleOutputCP()
            finally:
                kernel.CloseHandle(handle)

        original_state = output_state()
        with tempfile.TemporaryDirectory() as log_dir, open("CONOUT$", "wb", buffering=0) as output:
            process = subprocess.Popen(
                [node, str(FIXTURE), sys.executable],
                stdin=subprocess.PIPE, stdout=output, stderr=subprocess.PIPE,
                env={**os.environ, "SIADA_CLI_LOG_DIR": log_dir},
            )
            screen = None
            try:
                ready = process.stderr.readline().decode("utf-8")
                self.assertTrue(ready, "Renderer exited before the first frame")
                if not ready.startswith("{"):
                    _, error = process.communicate(timeout=5)
                    self.fail(ready + error.decode("utf-8"))
                profile = json.loads(ready)
                self.assertEqual(profile["stage"], "initial")
                screen = kernel.CreateFileW("CONOUT$", 0x80000000, 3, None, 3, 0, None)
                self.assertNotEqual(screen, ctypes.c_void_p(-1).value)

                def rows():
                    captured = []
                    for row in range(8):
                        text = ctypes.create_unicode_buffer(profile["columns"] + 2)
                        read = wintypes.DWORD()
                        success = kernel.ReadConsoleOutputCharacterW(
                            screen, text, profile["columns"] + 1, Coord(0, row), ctypes.byref(read),
                        )
                        self.assertTrue(success, ctypes.get_last_error())
                        captured.append(text.value.rstrip())
                    return captured

                initial = rows()
                self.assertIn("▆", initial[0])
                self.assertEqual(initial[1], "STATIC")
                self.assertEqual(initial[7], "INPUT")
                process.stdin.write(b"advance\n")
                process.stdin.flush()
                self.assertEqual(process.stderr.readline(), b"updated\n")
                updated = rows()
                self.assertEqual(updated[0], "A")
                self.assertEqual(updated[1], "STATIC")
                self.assertEqual(updated[2], "● 49")
                self.assertEqual(updated[7], "INPUT")
                self.assertEqual("\n".join(updated).count("STATIC"), 1)
                kernel.CloseHandle(screen)
                screen = None
                process.stdin.write(b"quit\n")
                process.stdin.flush()
                _, error = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, error.decode("utf-8"))
                restored = output_state()
                self.assertEqual(restored, (
                    profile["originalOutputState"]["mode"],
                    profile["originalOutputState"]["codePage"],
                ))
                # Node's TTY initialization may itself enable VT output.
                self.assertEqual((restored[0] & ~4, restored[1]),
                                 (original_state[0] & ~4, original_state[1]))
            finally:
                if screen is not None:
                    kernel.CloseHandle(screen)
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()