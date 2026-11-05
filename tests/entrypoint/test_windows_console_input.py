"""Exercise native mouse/key translation and console input ownership."""

import ctypes
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from ctypes import wintypes
from pathlib import Path

HELPER = Path(__file__).resolve().parents[2] / "siada/entrypoint/windows_console_input.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("windows_console_input", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DecoderTests(unittest.TestCase):
    def setUp(self):
        self.decoder = load_helper().InputDecoder()

    def test_click_and_release_use_viewport_coordinates(self):
        self.assertEqual(self.decoder.mouse(12, 23, 1, 0, 0, (10, 20)), "\x1b[<0;3;4M")
        self.assertEqual(self.decoder.mouse(12, 23, 0, 0, 0, (10, 20)), "\x1b[<0;3;4m")

    def test_motion_and_wheel_keep_modifiers(self):
        self.assertEqual(self.decoder.mouse(2, 3, 0, 1, 0x10, (0, 0)), "\x1b[<39;3;4M")
        self.assertEqual(self.decoder.mouse(2, 3, 120 << 16, 4, 0, (0, 0)), "\x1b[<64;3;4M")
        self.assertEqual(self.decoder.mouse(2, 3, (0x10000 - 120) << 16, 4, 0, (0, 0)), "\x1b[<65;3;4M")

    def test_right_button_release_does_not_become_left_click(self):
        self.assertEqual(self.decoder.mouse(0, 0, 2, 0, 0, (0, 0)), "\x1b[<2;1;1M")
        self.assertEqual(self.decoder.mouse(0, 0, 0, 0, 0, (0, 0)), "\x1b[<2;1;1m")

    def test_keyboard_preserves_submit_modifiers_and_control(self):
        self.assertEqual(self.decoder.key("\r", 13, 0x10), "\x1b[13;2u")
        self.assertEqual(self.decoder.key("\r", 13, 0), "\r")
        self.assertEqual(self.decoder.key("\x03", 67, 8), "\x03")
        self.assertEqual(self.decoder.key("", 37, 8), "\x1b[1;5D")

    def test_altgr_unicode_surrogates_repeat_and_keyup(self):
        self.assertEqual(self.decoder.key("@", 81, 9), "@")
        self.assertEqual(self.decoder.key("中", 0, 0, repeat=2), "中中")
        self.assertEqual(self.decoder.key("ß", 0, 8), "ß")
        self.assertEqual(self.decoder.key("x", 88, 0, down=False), "")
        self.assertEqual(self.decoder.key("\ud83d", 0, 0), "")
        self.assertEqual(self.decoder.key("\ude00", 0, 0), "😀")

    def test_backspace_and_tab_preserve_control_and_alt(self):
        self.assertEqual(self.decoder.key("\x7f", 8, 8), "\x1b[127;5u")
        self.assertEqual(self.decoder.key("\x08", 8, 2), "\x1b[127;3u")
        self.assertEqual(self.decoder.key("\t", 9, 8), "\x1b[9;5u")
        self.assertEqual(self.decoder.key("\t", 9, 0x10), "\x1b[Z")


@unittest.skipUnless(sys.platform == "win32", "Windows console API")
class NativeConsoleTests(unittest.TestCase):
    def test_real_node_ui_click_keyboard_and_editor_handoff(self):
        self.run_node_case(False)

    def test_node_crash_restores_console_input(self):
        self.run_node_case(True)

    def run_node_case(self, crash):
        if os.environ.get("SIADA_NATIVE_INPUT_TEST_CHILD") != "1":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()),
                 f"{type(self).__name__}.{self._testMethodName}"],
                env={**os.environ, "SIADA_NATIVE_INPUT_TEST_CHILD": "1"},
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                startupinfo=startup, capture_output=True, text=True, timeout=35,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return
        module = load_helper()
        api = module.ConsoleApi()
        handle = api.open_console("CONIN$")
        original = api.mode(handle)
        fixture = HELPER.parents[2] / "siada_cli_ui/tests/fixtures/windows-native-input.tsx"
        api.kernel.WriteConsoleInputW.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(module.InputRecord),
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]

        def inject(records):
            data = (module.InputRecord * len(records))(*records)
            count = wintypes.DWORD()
            self.assertTrue(api.kernel.WriteConsoleInputW(handle, data, len(data), ctypes.byref(count)))

        def key(char, virtual_key=0, control=0):
            record = module.InputRecord()
            record.event_type = 1
            record.key.down, record.key.repeat = True, 1
            record.key.char, record.key.virtual_key, record.key.control = char, virtual_key, control
            return record

        with tempfile.TemporaryDirectory() as logs, open("CONIN$", "rb", buffering=0) as stdin, \
                open("CONOUT$", "wb", buffering=0) as stdout:
            process = subprocess.Popen(
                [shutil.which("node"), "--import", "tsx", str(fixture), sys.executable],
                cwd=fixture.parents[2], stdin=stdin, stdout=stdout, stderr=subprocess.PIPE,
                env={**os.environ, "SIADA_CLI_LOG_DIR": logs, "TERM_PROGRAM": "", "WT_SESSION": ""},
            )
            try:
                received = []

                def await_stage(stage):
                    diagnostics = []
                    while True:
                        line = process.stderr.readline()
                        self.assertTrue(line, f"UI exited before {stage}: {received}\n{''.join(diagnostics)}")
                        try:
                            message = json.loads(line)
                        except ValueError:
                            diagnostics.append(line.decode("utf-8", "replace"))
                            continue
                        received.append(message)
                        if message.get("stage") == stage:
                            return message

                ready = await_stage("ready")
                self.assertTrue(ready["native"])
                if crash:
                    process.kill()
                    process.communicate(timeout=3)
                    deadline = time.monotonic() + 3
                    while api.mode(handle) != original and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertEqual(api.mode(handle), original)
                    return
                rect = api.viewport()
                point = (rect.left + ready["x"], rect.top + ready["y"])
                down = module.InputRecord()
                down.event_type = 2
                down.mouse.position = module.Coord(*point)
                down.mouse.buttons = 1
                up = module.InputRecord()
                up.event_type = 2
                up.mouse.position = module.Coord(*point)
                inject([down, up])
                await_stage("clicked")
                inject([key("中"), key("\r", 13, 0x10), key("\x03", 67, 8), key("e", 69)])
                await_stage("editor")
                self.assertEqual(api.mode(handle), original)
                inject([key(char) for char in "EDITOR_ONLY"] + [key("\r", 13)])
                edited = await_stage("editor-return")
                self.assertEqual(edited["text"], "EDITOR_ONLY")
                await_stage("resumed")
                inject([key("z", 90), key("\x04", 68, 8)])
                await_stage("finished")
                _, error = process.communicate(timeout=4)
                self.assertEqual(process.returncode, 0, error.decode("utf-8", "replace"))
                keys = [message for message in received if message.get("stage") == "key"]
                self.assertTrue(any(message["sequence"] == "中" for message in keys))
                self.assertTrue(any(message["name"] == "return" and message["shift"] for message in keys))
                self.assertTrue(any(message["sequence"] == "\x03" for message in keys))
                self.assertTrue(any(message["sequence"] == "z" for message in keys))
                self.assertFalse(any(message["sequence"] in "EDITOR_ONLY" for message in keys))
                self.assertEqual(api.mode(handle), original)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=3)
                api.kernel.SetConsoleMode(handle, original)
                api.kernel.CloseHandle(handle)

    def test_native_records_pause_resume_and_mode_restoration(self):
        self.run_helper_case(False)

    def test_control_break_does_not_kill_the_input_reader(self):
        self.run_helper_case(True)

    def run_helper_case(self, send_break):
        if os.environ.get("SIADA_NATIVE_INPUT_TEST_CHILD") != "1":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()),
                 f"{type(self).__name__}.{self._testMethodName}"],
                env={**os.environ, "SIADA_NATIVE_INPUT_TEST_CHILD": "1"},
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                startupinfo=startup, capture_output=True, text=True, timeout=25,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return
        module = load_helper()
        api = module.ConsoleApi()
        handle = api.open_console("CONIN$")
        original = api.mode(handle)
        name = f"siada-input-test-{os.getpid()}"
        process = subprocess.Popen(
            [sys.executable, "-I", str(HELPER), "--parent-pid", str(os.getpid()), "--name", name],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        try:
            ready = json.loads(process.stdout.readline())
            self.assertEqual(ready["type"], "ready", ready)
            self.assertTrue(api.mode(handle) & 0x10)
            self.assertFalse(api.mode(handle) & 0x240)
            if send_break:
                api.kernel.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
                self.assertTrue(api.kernel.GenerateConsoleCtrlEvent(1, process.pid))
                time.sleep(0.05)
                self.assertIsNone(process.poll(), "Ctrl+Break terminated the input owner")
            record = module.InputRecord()
            record.event_type = 1
            record.key.down = True
            record.key.repeat = 1
            record.key.virtual_key = 88
            record.key.char = "x"
            api.kernel.WriteConsoleInputW.argtypes = [
                wintypes.HANDLE, ctypes.POINTER(module.InputRecord),
                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ]

            def inject():
                count = wintypes.DWORD()
                self.assertTrue(api.kernel.WriteConsoleInputW(handle, ctypes.byref(record), 1, ctypes.byref(count)))

            inject()
            self.assertEqual(json.loads(process.stdout.readline()), {"type": "input", "data": "x"})

            def control(action):
                result = subprocess.run(
                    [sys.executable, "-I", str(HELPER), "--name", name, "--control", action],
                    capture_output=True, text=True, timeout=4,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            control("pause")
            self.assertEqual(api.mode(handle), original)
            inject()
            count = wintypes.DWORD()
            api.kernel.GetNumberOfConsoleInputEvents.argtypes = [
                wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
            ]
            self.assertTrue(api.kernel.GetNumberOfConsoleInputEvents(handle, ctypes.byref(count)))
            self.assertGreater(count.value, 0)
            control("resume")
            self.assertEqual(json.loads(process.stdout.readline()), {"type": "input", "data": "x"})
            control("stop")
            _, error = process.communicate(timeout=3)
            self.assertEqual(process.returncode, 0, error.decode())
            self.assertEqual(api.mode(handle), original)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=3)
            api.kernel.SetConsoleMode(handle, original)
            api.kernel.CloseHandle(handle)


if __name__ == "__main__":
    unittest.main()