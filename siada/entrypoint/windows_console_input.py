"""Bridge native Win32 console records to terminal input without a second reader."""

import argparse
import ctypes
import json
import os
import queue
import re
import sys
import threading
from ctypes import wintypes


class Coord(ctypes.Structure):
    _fields_ = [("x", wintypes.SHORT), ("y", wintypes.SHORT)]


class Rect(ctypes.Structure):
    _fields_ = [(name, wintypes.SHORT) for name in ("left", "top", "right", "bottom")]


class BufferInfo(ctypes.Structure):
    _fields_ = [
        ("size", Coord), ("cursor", Coord), ("attributes", wintypes.WORD),
        ("window", Rect), ("maximum_size", Coord),
    ]


class KeyRecord(ctypes.Structure):
    _fields_ = [
        ("down", wintypes.BOOL), ("repeat", wintypes.WORD),
        ("virtual_key", wintypes.WORD), ("scan_code", wintypes.WORD),
        ("char", wintypes.WCHAR), ("control", wintypes.DWORD),
    ]


class MouseRecord(ctypes.Structure):
    _fields_ = [
        ("position", Coord), ("buttons", wintypes.DWORD),
        ("control", wintypes.DWORD), ("flags", wintypes.DWORD),
    ]


class RecordUnion(ctypes.Union):
    _fields_ = [("key", KeyRecord), ("mouse", MouseRecord), ("size", Coord)]


class InputRecord(ctypes.Structure):
    _anonymous_ = ("event",)
    _fields_ = [("event_type", wintypes.WORD), ("event", RecordUnion)]


class InputDecoder:
    """Preserve the existing SGR/CSI keyboard contract, including key releases."""

    def __init__(self):
        self.buttons = 0
        self.high_surrogate = ""

    @staticmethod
    def modifiers(control):
        # Right Alt + Left Ctrl is AltGr, which produces printable Unicode.
        altgr = control & 9 == 9
        return bool(control & 0x10), bool(control & 3) and not altgr, bool(control & 12) and not altgr

    def key(self, char, virtual_key, control, repeat=1, down=True):
        if not down:
            return ""
        shift, alt, ctrl = self.modifiers(control)
        modifier = 1 + shift + 2 * alt + 4 * ctrl
        repeat = max(1, min(repeat, 1024))
        if virtual_key == 13:
            text = "\r" if modifier == 1 else f"\x1b[13;{modifier}u"
        elif virtual_key == 9:
            text = (f"\x1b[9;{modifier}u" if alt or ctrl else "\x1b[Z" if shift else "\t")
        elif virtual_key == 8:
            text = "\x7f" if modifier == 1 else f"\x1b[127;{modifier}u"
        elif virtual_key == 27:
            text = "\x1b"
        elif virtual_key in (37, 38, 39, 40, 36, 35):
            suffix = {37: "D", 38: "A", 39: "C", 40: "B", 36: "H", 35: "F"}[virtual_key]
            text = f"\x1b[{suffix}" if modifier == 1 else f"\x1b[1;{modifier}{suffix}"
        elif virtual_key in (45, 46, 33, 34) or 112 <= virtual_key <= 123:
            code = {45: 2, 46: 3, 33: 5, 34: 6}.get(virtual_key)
            if code is None:
                if virtual_key <= 115 and modifier == 1:
                    return f"\x1bO{'PQRS'[virtual_key - 112]}" * repeat
                code = (11, 12, 13, 14, 15, 17, 18, 19, 20, 21, 23, 24)[virtual_key - 112]
            text = f"\x1b[{code}~" if modifier == 1 else f"\x1b[{code};{modifier}~"
        elif char and char != "\x00":
            point = ord(char)
            if 0xD800 <= point <= 0xDBFF:
                self.high_surrogate = char
                return ""
            if 0xDC00 <= point <= 0xDFFF:
                if not self.high_surrogate:
                    return ""
                text = (self.high_surrogate + char).encode("utf-16-le", "surrogatepass").decode("utf-16-le")
            else:
                text = char
            self.high_surrogate = ""
            upper = text.upper()
            if ctrl and len(upper) == 1 and "@" <= upper <= "_":
                text = chr(ord(upper) & 31)
            if alt:
                text = "\x1b" + text
        else:
            return ""
        return text * repeat

    def mouse(self, x, y, buttons, flags, control, viewport):
        shift, alt, ctrl = self.modifiers(control)
        modifier = 4 * shift + 8 * alt + 16 * ctrl
        x, y = x - viewport[0] + 1, y - viewport[1] + 1
        held = buttons & 0xFFFF
        previous, self.buttons = self.buttons, held
        if x < 1 or y < 1:
            return ""

        def sgr(button, ending="M"):
            return f"\x1b[<{button + modifier};{x};{y}{ending}"

        if flags & (4 | 8):
            delta = ctypes.c_short(buttons >> 16).value
            if not delta:
                return ""
            return sgr((64 if delta > 0 else 65) + (2 if flags & 8 else 0)) * max(1, abs(delta) // 120)
        mapping = ((1, 0), (4, 1), (2, 2))
        if flags & 1:
            button = next((code for mask, code in mapping if held & mask), 3)
            return sgr(32 + button)
        # DOUBLE_CLICK is an additional record while already pressed.
        return "".join(
            sgr(code, "M" if held & mask else "m")
            for mask, code in mapping if bool(previous & mask) != bool(held & mask)
        )


class ConsoleApi:
    """Declare pointer-sized handle signatures explicitly on 64-bit Windows."""

    def __init__(self):
        if sys.platform != "win32":
            raise OSError("Native console input is only supported on Windows")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateFileW": ([wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                             wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE], wintypes.HANDLE),
            "GetConsoleMode": ([wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            "SetConsoleMode": ([wintypes.HANDLE, wintypes.DWORD], wintypes.BOOL),
            "GetConsoleScreenBufferInfo": ([wintypes.HANDLE, ctypes.POINTER(BufferInfo)], wintypes.BOOL),
            "ReadConsoleInputW": ([wintypes.HANDLE, ctypes.POINTER(InputRecord), wintypes.DWORD,
                                   ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            "CreateEventW": ([ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            "OpenEventW": ([wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetEvent": ([wintypes.HANDLE], wintypes.BOOL),
            "ResetEvent": ([wintypes.HANDLE], wintypes.BOOL),
            "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            "WaitForMultipleObjects": ([wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
                                        wintypes.BOOL, wintypes.DWORD], wintypes.DWORD),
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "AttachConsole": ([wintypes.DWORD], wintypes.BOOL),
            "FreeConsole": ([], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = args, result

    @staticmethod
    def check(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    def open_console(self, name):
        result = self.kernel.CreateFileW(name, 0xC0000000, 3, None, 3, 0, None)
        if result in (None, ctypes.c_void_p(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    def mode(self, handle):
        result = wintypes.DWORD()
        self.check(self.kernel.GetConsoleMode(handle, ctypes.byref(result)))
        return result.value

    def viewport(self):
        # CONOUT$ must be reopened: Ink can switch the active screen buffer.
        output = self.open_console("CONOUT$")
        try:
            info = BufferInfo()
            self.check(self.kernel.GetConsoleScreenBufferInfo(output, ctypes.byref(info)))
            return info.window
        finally:
            self.kernel.CloseHandle(output)

    def wait(self, handles, timeout=0xFFFFFFFF):
        array = (wintypes.HANDLE * len(handles))(*handles)
        result = self.kernel.WaitForMultipleObjects(len(handles), array, False, timeout)
        if result == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        return result


EVENTS = ("stop", "pause", "resume", "paused", "running", "stopped")


def event_name(name, event):
    if not re.fullmatch(r"[a-zA-Z0-9-]{1,96}", name):
        raise ValueError("Invalid input bridge name")
    return f"Local\\{name}-{event}"


def control(name, action):
    api = ConsoleApi()
    handles = []
    try:
        for event in EVENTS:
            handle = api.check(api.kernel.OpenEventW(0x100002, False, event_name(name, event)))
            handles.append(handle)
        events = dict(zip(EVENTS, handles))
        request, acknowledgement = {
            "pause": ("pause", "paused"), "resume": ("resume", "running"), "stop": ("stop", "stopped"),
        }[action]
        if action == "pause":
            api.check(api.kernel.ResetEvent(events["running"]))
        api.check(api.kernel.SetEvent(events[request]))
        if api.kernel.WaitForSingleObject(events[acknowledgement], 1500) != 0:
            raise TimeoutError(f"Native input {action} acknowledgement timed out")
    finally:
        for handle in handles:
            api.kernel.CloseHandle(handle)


def bridge(parent_pid, name):
    api = ConsoleApi()
    handles = []
    input_handle = None
    original = None
    events = {}
    control_handler = None
    try:
        # Piped/no-window children can inherit a windowless console of their own.
        api.kernel.FreeConsole()
        api.check(api.kernel.AttachConsole(parent_pid))
        input_handle = api.open_console("CONIN$")
        handles.append(input_handle)
        original = api.mode(input_handle)
        parent = api.check(api.kernel.OpenProcess(0x100000, False, parent_pid))
        handles.append(parent)
        for event in EVENTS:
            handle = api.check(api.kernel.CreateEventW(None, True, False, event_name(name, event)))
            handles.append(handle)
            events[event] = handle
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
        api.kernel.SetConsoleCtrlHandler.argtypes = [callback_type, wintypes.BOOL]
        api.kernel.SetConsoleCtrlHandler.restype = wintypes.BOOL

        def on_console_control(event):
            # AttachConsole resets Python's handler table. Ctrl+Break is
            # broadcast even in raw mode; editor Ctrl+C must not kill this
            # paused input owner either. The foreground process handles both.
            if event in (0, 1):
                return True
            if event in (2, 5, 6):
                api.kernel.SetEvent(events["stop"])
                api.kernel.WaitForSingleObject(events["stopped"], 1500)
                return True
            return False

        control_handler = callback_type(on_console_control)
        api.check(api.kernel.SetConsoleCtrlHandler(control_handler, True))
        native_mode = (original & ~0x267) | 0x98
        api.check(api.kernel.SetConsoleMode(input_handle, native_mode))
        api.check(api.kernel.SetEvent(events["running"]))
        decoder = InputDecoder()
        messages = queue.Queue(maxsize=512)

        def write_messages():
            try:
                while True:
                    message = messages.get()
                    data = (json.dumps(message, ensure_ascii=True) + "\n").encode("ascii")
                    while data:
                        data = data[os.write(sys.stdout.fileno(), data):]
            except (OSError, ValueError):
                api.kernel.SetEvent(events["stop"])

        threading.Thread(target=write_messages, daemon=True).start()
        messages.put_nowait({"type": "ready"})
        while True:
            selected = api.wait([events["stop"], parent, events["pause"], input_handle])
            if selected in (0, 1):
                break
            if selected == 2:
                api.check(api.kernel.ResetEvent(events["running"]))
                api.check(api.kernel.SetConsoleMode(input_handle, original))
                api.check(api.kernel.SetEvent(events["paused"]))
                if api.wait([events["stop"], parent, events["resume"]]) != 2:
                    break
                api.check(api.kernel.ResetEvent(events["pause"]))
                api.check(api.kernel.ResetEvent(events["resume"]))
                api.check(api.kernel.ResetEvent(events["paused"]))
                decoder.buttons = 0
                api.check(api.kernel.SetConsoleMode(input_handle, native_mode))
                api.check(api.kernel.SetEvent(events["running"]))
                continue
            record = InputRecord()
            count = wintypes.DWORD()
            api.check(api.kernel.ReadConsoleInputW(input_handle, ctypes.byref(record), 1, ctypes.byref(count)))
            if not count.value:
                continue
            if record.event_type == 1:
                key = record.key
                data = decoder.key(key.char, key.virtual_key, key.control, key.repeat, key.down)
            elif record.event_type == 2:
                mouse = record.mouse
                rect = api.viewport()
                data = decoder.mouse(mouse.position.x, mouse.position.y, mouse.buttons,
                                     mouse.flags, mouse.control, (rect.left, rect.top))
            elif record.event_type == 4:
                rect = api.viewport()
                messages.put_nowait({"type": "resize", "columns": rect.right - rect.left + 1,
                                     "rows": rect.bottom - rect.top + 1})
                continue
            else:
                continue
            if data:
                # A stalled consumer must fail explicitly rather than drop keys.
                messages.put_nowait({"type": "input", "data": data})
    finally:
        try:
            if original is not None:
                api.check(api.kernel.SetConsoleMode(input_handle, original))
            if events.get("stopped"):
                api.check(api.kernel.SetEvent(events["stopped"]))
        finally:
            if control_handler is not None:
                api.kernel.SetConsoleCtrlHandler(control_handler, False)
            for handle in reversed(handles):
                api.kernel.CloseHandle(handle)
            api.kernel.FreeConsole()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--name", required=True)
    parser.add_argument("--control", choices=("pause", "resume", "stop"))
    args = parser.parse_args()
    try:
        if args.control:
            control(args.name, args.control)
        elif args.parent_pid and args.parent_pid > 0:
            bridge(args.parent_pid, args.name)
        else:
            raise ValueError("A parent process is required")
    except (OSError, ValueError, TimeoutError, queue.Full) as error:
        # No key contents or credentials are included in diagnostics.
        print(json.dumps({"type": "error", "error": str(error)}, ensure_ascii=True), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())