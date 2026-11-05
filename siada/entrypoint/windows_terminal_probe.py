"""Inspect native console glyph widths without touching its visible contents."""

import argparse
import ctypes
import json
import sys
import time
import unicodedata
from ctypes import wintypes


def ambiguous_characters():
    """Exclude unassigned, private-use, surrogate and combining characters."""
    return (
        chr(point)
        for point in range(0x10000)
        if unicodedata.east_asian_width(chr(point)) == "A"
        and unicodedata.category(chr(point))[0] not in ("C", "M")
    )

def calibration_characters():
    """Also measure neutral-width blocks used by the native banner."""
    yield from ambiguous_characters()
    for character in ("\u25fc", "\u25aa"):
        if unicodedata.east_asian_width(character) != "A":
            yield character


class Coord(ctypes.Structure):
    _fields_ = [("x", wintypes.SHORT), ("y", wintypes.SHORT)]


class SmallRect(ctypes.Structure):
    _fields_ = [(name, wintypes.SHORT) for name in ("left", "top", "right", "bottom")]


class BufferInfo(ctypes.Structure):
    _fields_ = [
        ("size", Coord),
        ("cursor", Coord),
        ("attributes", wintypes.WORD),
        ("window", SmallRect),
        ("maximum_size", Coord),
    ]


class FontInfo(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.ULONG),
        ("index", wintypes.DWORD),
        ("cell_size", Coord),
        ("family", wintypes.UINT),
        ("weight", wintypes.UINT),
        ("face", wintypes.WCHAR * 32),
    ]


def probe(
    parent_pid: int,
    timeout: float = 2.0,
    prepare_output: bool = False,
    restore_output: dict | None = None,
) -> dict:
    """Use an inactive buffer that inherits the visible console's font."""
    if sys.platform != "win32":
        return {"renderer": "external-terminal", "widths": {}}

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel.GetConsoleWindow.restype = wintypes.HWND
    kernel.AttachConsole.argtypes = [wintypes.DWORD]
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CreateConsoleScreenBuffer.argtypes = [
        wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
    ]
    kernel.CreateConsoleScreenBuffer.restype = wintypes.HANDLE
    kernel.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(BufferInfo)]
    kernel.GetCurrentConsoleFontEx.argtypes = [
        wintypes.HANDLE, wintypes.BOOL, ctypes.POINTER(FontInfo),
    ]
    kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.SetConsoleOutputCP.argtypes = [wintypes.UINT]
    kernel.SetConsoleCursorPosition.argtypes = [wintypes.HANDLE, Coord]
    kernel.WriteConsoleW.argtypes = [
        wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

    handles = []
    attached = False

    def checked(success):
        if not success:
            raise ctypes.WinError(ctypes.get_last_error())

    def handle(value):
        if value in (None, ctypes.c_void_p(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        handles.append(value)
        return value

    try:
        if not kernel.GetConsoleWindow():
            # CREATE_NO_WINDOW can leave a child attached to a windowless console.
            # AttachConsole reports access denied until that attachment is released.
            kernel.FreeConsole()
            checked(kernel.AttachConsole(parent_pid))
            attached = True
        name = ctypes.create_unicode_buffer(64)
        checked(user.GetClassNameW(kernel.GetConsoleWindow(), name, len(name)))
        # ConPTY's font and palette do not describe the external renderer.
        if name.value != "ConsoleWindowClass":
            return {"renderer": "external-terminal", "widths": {}}

        access = 0xC0000000 if prepare_output or restore_output is not None else 0x80000000
        output = handle(kernel.CreateFileW("CONOUT$", access, 3, None, 3, 0, None))
        if restore_output is not None:
            mode = restore_output.get("mode")
            code_page = restore_output.get("codePage")
            if not isinstance(mode, int) or not isinstance(code_page, int):
                raise ValueError("Invalid saved console output state")
            if not 0 <= mode <= 0xFFFF or not 0 < code_page <= 0xFFFF:
                raise ValueError("Saved console output state is out of range")
            checked(kernel.SetConsoleMode(output, mode))
            checked(kernel.SetConsoleOutputCP(code_page))
            return {"renderer": "native-console", "widths": {}, "restored": True}
        info = BufferInfo()
        checked(kernel.GetConsoleScreenBufferInfo(output, ctypes.byref(info)))
        font = FontInfo()
        font.size = ctypes.sizeof(font)
        checked(kernel.GetCurrentConsoleFontEx(output, False, ctypes.byref(font)))
        scratch = handle(kernel.CreateConsoleScreenBuffer(0xC0000000, 3, None, 1, None))
        # An inactive VT-enabled buffer does not process writes on older conhost.
        # Processed output suffices to measure Unicode without interpreting ANSI.
        checked(kernel.SetConsoleMode(scratch, 3))
        deadline = time.monotonic() + timeout
        widths = {}
        for character in calibration_characters():
            if time.monotonic() >= deadline:
                raise TimeoutError("Console width calibration exceeded its time budget")
            checked(kernel.SetConsoleCursorPosition(scratch, Coord(0, 0)))
            written = wintypes.DWORD()
            checked(kernel.WriteConsoleW(scratch, character, 1, ctypes.byref(written), None))
            checked(kernel.GetConsoleScreenBufferInfo(scratch, ctypes.byref(info)))
            if written.value != 1 or info.cursor.y != 0 or info.cursor.x not in (1, 2):
                raise ValueError("Unexpected native console glyph width")
            widths[character] = info.cursor.x
        result = {
            "renderer": "native-console",
            "widths": widths,
            "font": font.face,
            "fontSize": [font.cell_size.x, font.cell_size.y],
            "outputCodePage": kernel.GetConsoleOutputCP(),
        }
        if prepare_output:
            mode = wintypes.DWORD()
            checked(kernel.GetConsoleMode(output, ctypes.byref(mode)))
            original_code_page = kernel.GetConsoleOutputCP()
            try:
                # Node writes UTF-8 ANSI frames. Both decoding and VT processing
                # must be enabled before Ink enters the alternate screen.
                checked(kernel.SetConsoleOutputCP(65001))
                checked(kernel.SetConsoleMode(output, mode.value | 0x0005))
            except OSError:
                kernel.SetConsoleMode(output, mode.value)
                kernel.SetConsoleOutputCP(original_code_page)
                raise
            result["outputState"] = {"mode": mode.value, "codePage": original_code_page}
            result["outputCodePage"] = 65001
        return result
    finally:
        for value in reversed(handles):
            kernel.CloseHandle(value)
        if attached:
            kernel.FreeConsole()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--prepare-output", action="store_true")
    parser.add_argument("--restore-output")
    args = parser.parse_args()
    try:
        state = json.loads(args.restore_output) if args.restore_output else None
        if state is not None and not isinstance(state, dict):
            raise ValueError("Saved console output state must be an object")
        result = probe(args.parent_pid, prepare_output=args.prepare_output, restore_output=state)
    except (OSError, TimeoutError, ValueError, TypeError) as error:
        result = {"renderer": "unavailable", "widths": {}, "error": str(error)}
    # ASCII JSON remains safe with a legacy console code page and a piped stdout.
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()