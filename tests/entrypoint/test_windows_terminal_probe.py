"""Exercise the rendering probe in a private console, never the user's terminal."""

import ctypes
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from ctypes import wintypes
from pathlib import Path
from unittest.mock import patch

PROBE = Path(__file__).resolve().parents[2] / "siada/entrypoint/windows_terminal_probe.py"
SPEC = importlib.util.spec_from_file_location("windows_terminal_probe", PROBE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WindowsTerminalProbeTests(unittest.TestCase):
    def test_candidates_exclude_nonprinting_and_private_characters(self):
        candidates = set(MODULE.ambiguous_characters())
        self.assertTrue({"▆", "●", "☆", "─"}.issubset(candidates))
        self.assertNotIn("\u0301", candidates)
        self.assertNotIn("\ue000", candidates)

    def test_non_windows_probe_does_not_load_native_libraries(self):
        with patch.object(MODULE.sys, "platform", "linux"):
            self.assertEqual(MODULE.probe(0), {"renderer": "external-terminal", "widths": {}})

    def test_calibration_includes_the_neutral_width_banner_candidate(self):
        candidates = list(MODULE.calibration_characters())
        self.assertIn("\u25aa", candidates)
        self.assertIn("\u25fc", candidates)
        self.assertEqual(len(candidates), len(set(candidates)))
        self.assertTrue(set(MODULE.ambiguous_characters()).issubset(candidates))

    @unittest.skipUnless(sys.platform == "win32", "Windows console API")
    def test_native_probe_preserves_visible_buffer_and_modes(self):
        if os.environ.get("SIADA_PROBE_TEST_CHILD") != "1":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()),
                 "WindowsTerminalProbeTests.test_native_probe_preserves_visible_buffer_and_modes"],
                env={**os.environ, "SIADA_PROBE_TEST_CHILD": "1"},
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                startupinfo=startup, capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULE.BufferInfo)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        output = kernel.CreateFileW("CONOUT$", 0x80000000, 3, None, 3, 0, None)
        self.assertNotEqual(output, ctypes.c_void_p(-1).value)

        def snapshot():
            mode = wintypes.DWORD()
            info = MODULE.BufferInfo()
            self.assertTrue(kernel.GetConsoleMode(output, ctypes.byref(mode)))
            self.assertTrue(kernel.GetConsoleScreenBufferInfo(output, ctypes.byref(info)))
            return mode.value, bytes(info), kernel.GetConsoleOutputCP()

        try:
            before = snapshot()
            profile = MODULE.probe(os.getpid())
            self.assertEqual(profile["renderer"], "native-console")
            self.assertIn(profile["widths"]["▆"], (1, 2))
            self.assertEqual(profile["widths"]["─"], 1)
            self.assertIn(profile["widths"]["\u25aa"], (1, 2))
            self.assertIn(profile["widths"]["\u25fc"], (1, 2))
            self.assertEqual(snapshot(), before)
            prepared = MODULE.probe(os.getpid(), prepare_output=True)
            try:
                self.assertEqual(kernel.GetConsoleOutputCP(), 65001)
                self.assertTrue(snapshot()[0] & 0x0004)
                self.assertEqual(prepared["widths"], profile["widths"])
            finally:
                MODULE.probe(os.getpid(), restore_output=prepared["outputState"])
            self.assertEqual(snapshot(), before)
            # The CLI's JSON handshake must survive a legacy output code page.
            result = subprocess.run(
                [sys.executable, str(PROBE), "--parent-pid", str(os.getpid())],
                capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["widths"], profile["widths"])
        finally:
            kernel.CloseHandle(output)


if __name__ == "__main__":
    unittest.main()