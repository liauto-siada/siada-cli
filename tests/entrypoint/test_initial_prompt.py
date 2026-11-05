"""Positional messages launch the interactive UI without becoming --prompt."""

import shlex
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from siada.entrypoint import launch_ui_with_acp as launcher
from siada.entrypoint import siadahub
from siada.entrypoint.args_parser.args import SiadaArgs, get_parser


@pytest.fixture
def launch_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["siada-cli"])
    monkeypatch.delenv("SIADA_WORKSPACE", raising=False)
    monkeypatch.setattr(launcher, "_run_first_time_setup_if_needed", lambda: None)
    monkeypatch.setattr(launcher, "remove_console_handler", lambda: None)
    monkeypatch.setattr(launcher, "_check_resume_workspace", lambda *args: 0)
    monkeypatch.setattr(siadahub, "load_dotenv_files", lambda *args: [])
    monkeypatch.setattr(siadahub, "toggle_console_output", lambda *args: None)
    return tmp_path


@pytest.mark.parametrize("message", ["你好", "Inspect this project", "/goal Fix failing tests", "line one\nline two", 'Keep "quotes" and \'apostrophes\''])
def test_launcher_and_backend_parse_positional_message_as_interactive(launch_environment, monkeypatch, message):
    monkeypatch.setattr(sys, "argv", ["siada-cli", message])
    args = launcher._parse_args(None)
    backend_args, _, _, _, interactive = siadahub._parse_args_and_setup_environment([message])
    assert args.initial_prompt == backend_args.initial_prompt == message
    assert args.prompt is backend_args.prompt is None
    assert interactive is True
    assert SiadaArgs(args).initial_prompt == message


@pytest.mark.parametrize("argv", [
    ["你好"],
    ["--agent", "coder", "你好"],
    ["你好", "--model", "synthetic"],
    ["--resume", "saved-session", "你好"],
    ["--workspace", ".", "你好"],
])
def test_positional_message_opens_ui_and_does_not_delegate_to_backend(launch_environment, monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["siada-cli", *argv])
    launch_ui = Mock(return_value=0)
    backend = Mock(side_effect=AssertionError("Interactive messages must not use the headless entrypoint"))
    monkeypatch.setattr(launcher, "_launch_ui", launch_ui)
    monkeypatch.setattr(launcher, "_run_backend", backend)
    assert launcher.main() == 0
    assert launch_ui.call_args.args[1].initial_prompt == "你好"
    assert launch_ui.call_args.args[1].prompt is None
    backend.assert_not_called()


@pytest.mark.parametrize("message", ["--prompt", "--prompt=literal", "--acp", "-p"])
def test_separator_prevents_message_from_being_used_for_option_routing(launch_environment, monkeypatch, message):
    monkeypatch.setattr(sys, "argv", ["siada-cli", "--", message])
    launch_ui = Mock(return_value=0)
    monkeypatch.setattr(launcher, "_launch_ui", launch_ui)
    monkeypatch.setattr(launcher, "_run_backend", Mock(side_effect=AssertionError("Literal message routed as a flag")))
    assert launcher.main() == 0
    assert launch_ui.call_args.args[1].initial_prompt == message


@pytest.mark.parametrize("argv", [["--prompt", "你好"], ["-p", "你好"], ["--prompt=你好"], ["-p=你好"]])
def test_explicit_prompt_still_uses_noninteractive_backend(launch_environment, monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["siada-cli", *argv])
    backend = Mock(return_value=7)
    monkeypatch.setattr(launcher, "_run_backend", backend)
    monkeypatch.setattr(launcher, "_launch_ui", Mock(side_effect=AssertionError("--prompt must not launch UI")))
    assert launcher.main() == 7
    backend.assert_called_once()
    parsed = get_parser([], None).parse_args(argv)
    assert parsed.prompt == "你好"
    assert parsed.initial_prompt is None


@pytest.mark.parametrize("argv", [["first", "second"], ["--unknown-option", "你好"], ["你好", "--prompt", "other"], ["-p", "other", "你好"]])
def test_invalid_or_conflicting_messages_are_rejected(launch_environment, monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["siada-cli", *argv])
    with pytest.raises(SystemExit) as error:
        launcher._parse_args(None)
    assert error.value.code == 2


def test_default_interactive_start_has_no_initial_message(launch_environment):
    args = launcher._parse_args(None)
    assert args.initial_prompt is args.prompt is None
    assert SiadaArgs(SimpleNamespace()).initial_prompt is None


@pytest.mark.parametrize("message", ["你好", 'Use "quotes", \'apostrophes\', and\nnewlines', "--prompt"])
def test_ui_command_preserves_literal_message_without_forwarding_it_to_backend(launch_environment, monkeypatch, message):
    args = get_parser([], None).parse_args(["--", message])
    ui_launcher = launcher.UILauncher({"workspace": str(launch_environment), "args": args})
    monkeypatch.setattr(ui_launcher, "_find_local_node", lambda: "synthetic-node")
    command = ui_launcher._build_ui_command(Path(__file__).resolve().parents[2] / "siada_cli_ui")
    index = command.index("--initial-prompt")
    assert command[index + 1] == message
    assert command[-1] == str(launch_environment)
    backend_args = shlex.split(" ".join(ui_launcher._build_siada_args()))
    parsed = get_parser([], None).parse_args(backend_args)
    assert parsed.initial_prompt is parsed.prompt is None