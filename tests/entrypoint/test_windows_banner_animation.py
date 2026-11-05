"""Inspect real banner characters before, during and after conhost lighting."""

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

from test_windows_console_input import load_helper

FIXTURE = Path(__file__).resolve().parents[2] / "siada_cli_ui/tests/fixtures/windows-banner-animation.tsx"


@unittest.skipUnless(sys.platform == "win32", "Windows console API")
class WindowsBannerAnimationTests(unittest.TestCase):
    def test_animation_preserves_characters_and_restores_the_frame(self):
        if os.environ.get("SIADA_BANNER_ANIMATION_CHILD") != "1":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve())],
                env={**os.environ, "SIADA_BANNER_ANIMATION_CHILD": "1"},
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                startupinfo=startup, capture_output=True, text=True, timeout=25,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())
            return
        module = load_helper()
        api = module.ConsoleApi()
        api.kernel.CreateConsoleScreenBuffer.argtypes = [
            wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
        ]
        api.kernel.CreateConsoleScreenBuffer.restype = wintypes.HANDLE
        api.kernel.SetConsoleCursorPosition.argtypes = [wintypes.HANDLE, module.Coord]
        api.kernel.WriteConsoleW.argtypes = [
            wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
        ]
        scratch = api.kernel.CreateConsoleScreenBuffer(0xC0000000, 3, None, 1, None)
        self.assertNotEqual(scratch, ctypes.c_void_p(-1).value)
        candidates = []
        try:
            api.check(api.kernel.SetConsoleMode(scratch, 3))
            for character in ("\u2586", "\u2588", "\u25fc", "\u25aa", "\u25a0", "\u28ff", "#"):
                api.check(api.kernel.SetConsoleCursorPosition(scratch, module.Coord(0, 0)))
                written = wintypes.DWORD()
                api.check(api.kernel.WriteConsoleW(scratch, character, 1, ctypes.byref(written), None))
                info = module.BufferInfo()
                api.check(api.kernel.GetConsoleScreenBufferInfo(scratch, ctypes.byref(info)))
                candidates.append([ord(character), info.cursor.x])
        finally:
            api.kernel.CloseHandle(scratch)
        input_handle = api.open_console("CONIN$")
        api.kernel.WriteConsoleInputW.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(module.InputRecord),
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]
        api.kernel.ReadConsoleOutputCharacterW.argtypes = [
            wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, module.Coord,
            ctypes.POINTER(wintypes.DWORD),
        ]
        original = api.mode(input_handle)
        with tempfile.TemporaryDirectory() as logs, open("CONIN$", "rb", buffering=0) as stdin, \
                open("CONOUT$", "wb", buffering=0) as stdout:
            process = subprocess.Popen(
                [shutil.which("node"), "--import", "tsx", str(FIXTURE), sys.executable],
                cwd=FIXTURE.parents[2], stdin=stdin, stdout=stdout, stderr=subprocess.PIPE,
                env={**os.environ, "TERM_PROGRAM": "", "WT_SESSION": "", "NO_COLOR": "",
                     "SIADA_CLI_LOG_DIR": logs},
            )
            screen = None
            try:
                def stage():
                    line = process.stderr.readline()
                    self.assertTrue(line, "Animation exited before reporting a frame")
                    return json.loads(line)

                ready = stage()
                self.assertEqual(ready["stage"], "ready")
                measured = dict(candidates)
                expected = "\u2586"
                if measured[0x2586] == 2:
                    expected = next((chr(point) for point in (0x25FC, 0x25AA) if measured[point] == 1), "#")
                self.assertEqual(ready["selectedBlock"], expected)
                self.assertTrue(all(width == 1 for _, width in ready["artWidths"]))
                self.assertEqual(ready["letterStarts"], [[2, 10, 13, 21, 29, 41, 49, 57]] * 6)
                screen = api.open_console("CONOUT$")

                def capture():
                    rows = []
                    for row in range(ready["rows"]):
                        text = ctypes.create_unicode_buffer(ready["columns"] + 2)
                        count = wintypes.DWORD()
                        api.check(api.kernel.ReadConsoleOutputCharacterW(
                            screen, text, ready["columns"] + 1, module.Coord(0, row), ctypes.byref(count)))
                        rows.append(text[:count.value])
                    return rows

                def inject(record):
                    count = wintypes.DWORD()
                    api.check(api.kernel.WriteConsoleInputW(input_handle, ctypes.byref(record), 1, ctypes.byref(count)))

                initial = capture()
                self.assertTrue(any(expected in line for line in initial))
                motion = module.InputRecord()
                motion.event_type = 2
                rect = api.viewport()
                motion.mouse.position = module.Coord(rect.left + ready["point"]["x"], rect.top + ready["point"]["y"])
                motion.mouse.flags = 1
                inject(motion)
                self.assertEqual(stage()["stage"], "animated")
                during = capture()
                self.assertEqual(during, initial, "Lighting changed physical banner characters")
                motion.mouse.position = module.Coord(rect.left, rect.top)
                inject(motion)
                self.assertEqual(stage()["stage"], "settled")
                self.assertEqual(capture(), initial)
                print(json.dumps({"widths": ready["widths"], "letterStarts": ready["letterStarts"],
                                  "candidateBlockWidths": candidates,
                                  "charactersStableDuringAnimation": True}, ensure_ascii=True))
                quit_record = module.InputRecord()
                quit_record.event_type = 1
                quit_record.key.down, quit_record.key.repeat = True, 1
                quit_record.key.virtual_key, quit_record.key.char, quit_record.key.control = 68, "\x04", 8
                inject(quit_record)
                _, error = process.communicate(timeout=3)
                self.assertEqual(process.returncode, 0, error.decode("utf-8", "replace"))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=3)
                if screen is not None:
                    api.kernel.CloseHandle(screen)
                api.kernel.SetConsoleMode(input_handle, original)
                api.kernel.CloseHandle(input_handle)


if __name__ == "__main__":
    unittest.main()