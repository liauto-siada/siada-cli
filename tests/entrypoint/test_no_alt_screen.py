"""Native-history flags belong to the terminal UI, not the agent subprocess."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from siada.config import conf_store
from siada.entrypoint.args_parser.args import get_parser
from siada.entrypoint.launch_ui_with_acp import UILauncher


@pytest.fixture(autouse=True)
def isolated_conf(tmp_path, monkeypatch):
    """Keep launch tests independent of the user's terminal preferences."""
    config_path = tmp_path / "conf.yaml"
    monkeypatch.setattr(conf_store, "get_conf_path", lambda: config_path)
    monkeypatch.delenv("SIADA_NO_ALT_SCREEN", raising=False)
    return config_path


@pytest.mark.parametrize("enabled", [False, True])
def test_no_alt_screen_routes_to_ui_only(tmp_path, monkeypatch, enabled):
    args = get_parser([], None).parse_args(["--no-alt-screen"] if enabled else [])
    assert args.no_alt_screen is enabled
    launcher = UILauncher({"workspace": str(tmp_path), "args": args})
    monkeypatch.setattr(launcher, "_find_local_node", lambda: "synthetic-node")
    ui_dir = Path(__file__).resolve().parents[2] / "siada_cli_ui"
    command = launcher._build_ui_command(ui_dir)
    assert ("--no-alt-screen" in command) is enabled
    assert "--no-alt-screen" not in launcher._build_siada_args()
    assert command[-1] == str(tmp_path)


def test_no_alt_screen_preserves_literal_initial_prompt(tmp_path, monkeypatch):
    launcher = UILauncher({
        "workspace": str(tmp_path),
        "args": SimpleNamespace(no_alt_screen=True, initial_prompt="line one\nline two"),
    })
    monkeypatch.setattr(launcher, "_find_local_node", lambda: "synthetic-node")
    command = launcher._build_ui_command(Path(__file__).resolve().parents[2] / "siada_cli_ui")
    assert command[command.index("--initial-prompt") + 1] == "line one\nline two"
    assert command.count("--no-alt-screen") == 1


@pytest.mark.parametrize(
    ("config_text", "cli_enabled", "expected"),
    [
        ("", False, False),
        ("ui:\n  theme: light\n", False, False),
        ("ui:\n  no_alt_screen: true\n", False, True),
        ("ui:\n  no_alt_screen: false\n", False, False),
        ("ui:\n  no_alt_screen: false\n", True, True),
        ("ui:\n  no_alt_screen: true\n", True, True),
        ('ui:\n  no_alt_screen: "false"\n', False, False),
        ('ui:\n  no_alt_screen: "true"\n', False, False),
        ("ui:\n  no_alt_screen: null\n", False, False),
        ("ui:\n  no_alt_screen: 1\n", False, False),
        ("ui: invalid\n", False, False),
        ("ui: [\n", False, False),
        ("ui: [\n", True, True),
    ],
)
def test_native_history_config_routes_to_ui_only(
    tmp_path, monkeypatch, isolated_conf, config_text, cli_enabled, expected
):
    isolated_conf.write_text(config_text, encoding="utf-8")
    args = get_parser([], None).parse_args(["--no-alt-screen"] if cli_enabled else [])
    launcher = UILauncher({"workspace": str(tmp_path), "args": args})
    monkeypatch.setattr(launcher, "_find_local_node", lambda: "synthetic-node")
    command = launcher._build_ui_command(
        Path(__file__).resolve().parents[2] / "siada_cli_ui"
    )
    assert command.count("--no-alt-screen") == int(expected)
    assert "--no-alt-screen" not in launcher._build_siada_args()
    assert command[-1] == str(tmp_path)