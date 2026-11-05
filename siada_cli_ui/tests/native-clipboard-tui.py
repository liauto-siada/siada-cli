"""Drive real Ctrl+V/Ctrl+B input under an isolated Linux Xvfb display."""

import fcntl
import base64
import io
import json
import os
import pty
import re
import select
import shutil
import struct
import subprocess
import sys
import termios
import time
from PIL import Image


def run():
    for command in ("wl-paste", "wl-copy", "xclip", "xsel"):
        assert shutil.which(command) is None, f"{command} would mask native clipboard failures"
    node, harness, runtime = sys.argv[1:]
    text = "native中文 👩‍💻\nsecond line"
    producer_source = """
const {Clipboard} = require(process.argv[1]);
const clipboard = new Clipboard();
require('node:readline').createInterface({input:process.stdin}).on('line', line => {
  const value = JSON.parse(line);
  if (typeof value === 'string') clipboard.setText(value);
  else clipboard.setImage(value.width, value.height, Buffer.from(value.pixels));
  console.log('READY');
});
"""
    producer = subprocess.Popen(
        [node, "-e", producer_source, runtime],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
    ui = None
    raw = b""

    def copy(value):
        producer.stdin.write((json.dumps(value) + "\n").encode())
        producer.stdin.flush()
        assert select.select([producer.stdout], [], [], 5)[0], "clipboard owner timed out"
        assert producer.stdout.readline() == b"READY\n", "native clipboard owner failed"

    def wait_for(expected, timeout=8, raw_match=False):
        nonlocal raw
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    raw += os.read(master, 65536)
                except OSError as error:
                    raise AssertionError(raw.decode(errors="replace")[-3000:]) from error
            visible = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", raw.decode(errors="replace"))
            if expected in (raw.decode(errors="replace") if raw_match else visible):
                return
        raise AssertionError(f"TUI did not render {expected!r}: {visible[-2000:]}")

    try:
        copy(text)
        env = dict(os.environ, TERM="xterm-256color", TERM_PROGRAM="")
        ui = subprocess.Popen([node, harness], stdin=slave, stdout=slave, stderr=slave, env=env)
        os.close(slave)
        slave = None
        wait_for("Native clipboard test history.")
        wait_for("\x1b[?1006h", raw_match=True)
        os.write(master, b"\x1b[<1;4;22M")  # A real SGR middle press.
        wait_for("native中文")
        wait_for("second line")
        assert b"NATIVE_SUBMIT:" not in raw
        copy("clipboard changed externally")
        os.write(master, b"\x02")  # Ctrl+B copies the actual expanded input.
        wait_for("Copied to clipboard")
        consumer_source = "console.log(JSON.stringify(new (require(process.argv[1]).Clipboard)().getText()))"
        copied = subprocess.check_output([node, "-e", consumer_source, runtime], timeout=5)
        assert json.loads(copied) == text
        os.write(master, b"\x04")  # Clear the draft before image paste.
        time.sleep(0.2)
        pixels = [
            255, 0, 0, 255, 0, 255, 0, 128,
            0, 0, 255, 255, 255, 255, 0, 64,
            255, 0, 255, 255, 0, 255, 255, 255,
        ]
        copy({"width": 2, "height": 3, "pixels": pixels})
        os.write(master, b"\x1b[<1;4;22M")
        wait_for("[Image #1]")
        os.write(master, b"\x1b[<1;4;22m")  # Release must not paste a second image.
        time.sleep(0.2)
        assert b"NATIVE_SUBMIT:" not in raw
        assert b"[Image #2]" not in raw
        os.write(master, b"\x16")
        wait_for("[Image #2]")
        assert b"NATIVE_SUBMIT:" not in raw
        os.write(master, b"\r")  # Explicit submission exercises attachment expansion.
        wait_for("NATIVE_SUBMIT:")
        match = re.search(rb"NATIVE_SUBMIT:(\{[^\r\n]+\})", raw)
        assert match, "missing submitted image payload"
        submitted = json.loads(match.group(1))
        assert len(submitted["paths"]) == 2
        assert len(submitted["images"]) == 2
        for encoded in submitted["images"]:
            image = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGBA")
            assert image.size == (2, 3)
            assert list(image.tobytes()) == pixels
        print("PASS: native Linux middle text paste, middle/Ctrl+V image paste, PNG dimensions/pixels and submitted attachments")
    finally:
        if ui:
            ui.kill()
            ui.wait(timeout=5)
        producer.kill()
        producer.wait(timeout=5)
        os.close(master)
        if slave is not None:
            os.close(slave)


if __name__ == "__main__":
    run()