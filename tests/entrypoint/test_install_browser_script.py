"""Run the public shell installer with synthetic uv/browser commands."""
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/install-browser.sh"


@pytest.mark.parametrize("fail_install", [False, True])
def test_uv_installs_before_starting_browser(tmp_path, fail_install):
    commands = tmp_path / "commands"
    commands.mkdir()
    trace = tmp_path / "trace"
    uv = commands / "uv"
    uv.write_text(
        '#!/bin/sh\nprintf "uv:%s\\n" "$*" >> "$TRACE"\n'
        'if [ "$1 $2" = "tool dir" ]; then printf "%s\\n" "$TEST_BIN"; fi\n'
        + ('if [ "$1 $2" = "tool install" ]; then exit 7; fi\n' if fail_install else "")
    )
    uv.chmod(0o755)
    browser = commands / "siada-browser"
    browser.write_text('#!/bin/sh\nprintf "browser:%s\\n" "$*" >> "$TRACE"\n')
    browser.chmod(0o755)
    env = dict(os.environ, PATH=f"{commands}:{os.environ['PATH']}", TRACE=str(trace), TEST_BIN=str(commands))
    result = subprocess.run(["sh", str(SCRIPT)], env=env, capture_output=True, text=True)
    lines = trace.read_text().splitlines()
    if fail_install:
        assert result.returncode == 7
        assert not any(line.startswith("browser:") for line in lines)
    else:
        assert result.returncode == 0, result.stderr
        assert "siada-cli@latest" in lines[0]
        assert lines[-2:] == ["browser:setup --no-wait --host 127.0.0.1", "browser:start"]