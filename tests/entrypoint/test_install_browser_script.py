"""Run the public shell installer with synthetic uv/browser commands."""
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/install-browser.sh"


@pytest.mark.parametrize("fail_install", [False, True])
@pytest.mark.parametrize("version", ["latest", "1.7.37b1"])
def test_uv_installs_before_starting_browser(tmp_path, fail_install, version):
    commands = tmp_path / "commands"
    commands.mkdir()
    trace = tmp_path / "trace"
    uv = commands / "uv"
    uv.write_text(
        '#!/bin/sh\nprintf "uv:%s\\n" "$*" >> "$TRACE"\n'
        'if [ "$1 $2" = "tool dir" ]; then printf "%s\\n" "$TEST_BIN"; fi\n'
        'if [ "$1" = "run" ]; then printf "%s\\n" "https://test-files.pythonhosted.org/synthetic.whl"; fi\n'
        + ('if [ "$1 $2" = "tool install" ]; then exit 7; fi\n' if fail_install else "")
    )
    uv.chmod(0o755)
    browser = commands / "siada-browser"
    browser.write_text('#!/bin/sh\nprintf "browser:%s\\n" "$*" >> "$TRACE"\n')
    browser.chmod(0o755)
    env = dict(os.environ, PATH=f"{commands}:{os.environ['PATH']}", TRACE=str(trace), TEST_BIN=str(commands), SIADA_VERSION=version)
    result = subprocess.run(["sh", str(SCRIPT)], env=env, capture_output=True, text=True)
    lines = trace.read_text().splitlines()
    if fail_install:
        assert result.returncode == 7
        assert not any(line.startswith("browser:") for line in lines)
    else:
        assert result.returncode == 0, result.stderr
        install = next(line for line in lines if line.startswith("uv:tool install"))
        assert ("siada-cli@latest" if version == "latest" else "https://test-files.pythonhosted.org/synthetic.whl") in install
        assert "--default-index https://pypi.org/simple" in install
        assert "--index " not in install
        expected_setup = "browser:setup --no-wait --host 127.0.0.1"
        if version != "latest":
            expected_setup += f" --base-url https://github.com/liauto-siada/siada-cli/releases/download/v{version}"
        assert lines[-2:] == [expected_setup, "browser:start"]