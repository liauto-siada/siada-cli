"""Theme resolution must never probe the terminal or operating system."""

from unittest.mock import patch

import pytest

from siada.io.system_theme_detector import SystemThemeDetector, resolve_theme_for_ui
from siada.entrypoint.args_parser.args import SiadaArgs, get_parser


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("dark", "dark"), ("light", "light"), ("auto", "dark"),
     (None, "dark"), ("", "dark"), ("default", "dark"), ("unknown", "dark")],
)
def test_theme_resolution_without_detection(configured, expected):
    with patch.object(
        SystemThemeDetector, "detect_theme", side_effect=AssertionError("unexpected detection")
    ) as detect:
        assert resolve_theme_for_ui(configured) == expected
        assert resolve_theme_for_ui(configured) == expected
    detect.assert_not_called()


@pytest.mark.parametrize(
    ("configured", "auto_follow", "expected"),
    [("auto", None, "dark"), (None, True, "dark"), ("light", True, "light"),
     ("dark", True, "dark"), ("default", None, "default")],
)
def test_legacy_config_resolution_without_detection(configured, auto_follow, expected):
    with patch.object(SystemThemeDetector, "detect_theme") as detect:
        assert SystemThemeDetector.get_theme_for_config(configured, auto_follow) == expected
    detect.assert_not_called()


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [([], "dark"), (["--theme", "auto"], "dark"),
     (["--theme", "dark"], "dark"), (["--theme", "light"], "light")],
)
def test_cli_theme_defaults_and_legacy_alias(arguments, expected):
    parsed = get_parser([], None).parse_args(arguments)
    assert parsed.theme == expected
    assert SiadaArgs(parsed).theme == expected