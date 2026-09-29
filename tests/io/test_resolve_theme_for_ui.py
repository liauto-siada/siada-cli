"""Tests for ``siada.io.system_theme_detector.resolve_theme_for_ui``.

Regression context: ``Controller.show_announcements`` imports this helper to
turn the configured ``ui.theme`` (``'auto'`` by default) into a concrete
``'dark'``/``'light'`` for the frontend. The function was referenced before it
existed, which crashed startup with ``ImportError`` (ACP process exited and was
restarted, leaving the UI waiting for its ready signal).
"""

import pytest

from siada.io import system_theme_detector as detector_mod
from siada.io.system_theme_detector import SystemThemeDetector, resolve_theme_for_ui


@pytest.fixture(autouse=True)
def _reset_auto_theme_cache():
    """Clear the process-lifetime 'auto' cache around every test.

    ``resolve_theme_for_ui`` resolves 'auto' (and legacy/unknown values) once
    per process, because detection shells out to AppleScript/gsettings. The
    tests below monkeypatch the detector per case, so they must start from an
    empty cache — otherwise a value cached by an earlier test masks the
    detection they set up.
    """
    detector_mod._cached_auto_theme = None
    yield
    detector_mod._cached_auto_theme = None


def test_concrete_themes_pass_through():
    assert resolve_theme_for_ui("dark") == "dark"
    assert resolve_theme_for_ui("light") == "light"


def test_auto_uses_detected_theme(monkeypatch):
    monkeypatch.setattr(SystemThemeDetector, "detect_theme", staticmethod(lambda: "light"))

    assert resolve_theme_for_ui("auto") == "light"


def test_unknown_detection_falls_back_to_dark(monkeypatch):
    monkeypatch.setattr(
        SystemThemeDetector, "detect_theme", staticmethod(lambda: "unknown")
    )

    assert resolve_theme_for_ui("auto") == "dark"


def test_none_and_legacy_values_resolve_to_concrete(monkeypatch):
    monkeypatch.setattr(SystemThemeDetector, "detect_theme", staticmethod(lambda: "dark"))

    assert resolve_theme_for_ui(None) in ("dark", "light")
    assert resolve_theme_for_ui("") in ("dark", "light")


def test_detection_errors_fall_back_to_dark(monkeypatch):
    def boom():
        raise RuntimeError("no tty")

    monkeypatch.setattr(SystemThemeDetector, "detect_theme", staticmethod(boom))

    assert resolve_theme_for_ui("auto") == "dark"


def test_auto_resolution_is_cached_for_the_process(monkeypatch):
    """Detection shells out (~100 ms), so 'auto' resolves at most once."""
    detections = []

    def detect():
        detections.append(1)
        return "light"

    monkeypatch.setattr(SystemThemeDetector, "detect_theme", staticmethod(detect))

    assert resolve_theme_for_ui("auto") == "light"
    assert resolve_theme_for_ui("auto") == "light"
    assert len(detections) == 1


def test_controller_import_path_works():
    """The exact import performed by ``Controller.show_announcements``."""
    from siada.io.system_theme_detector import resolve_theme_for_ui as imported

    assert imported is detector_mod.resolve_theme_for_ui
    assert imported("auto") in ("dark", "light")