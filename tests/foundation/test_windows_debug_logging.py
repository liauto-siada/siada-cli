"""Exercise Windows logger selection without changing the host platform."""

import importlib
import logging
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from concurrent_log_handler import ConcurrentRotatingFileHandler


@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("filtered", [False, True])
def test_windows_file_handler_honors_debug_and_releases_file(tmp_path, monkeypatch, debug, fallback, filtered):
    module = importlib.import_module("siada.foundation.logging")
    folder = tmp_path / "synthetic 调试 logs"
    folder.mkdir()
    target = folder / "siada_cli.log"
    monkeypatch.setattr(module, "log_file", str(target))
    monkeypatch.setattr(module, "DEBUG", debug)
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(module, "_shared_file_handler", None)
    if fallback:
        monkeypatch.setattr(module, "_create_concurrent_file_handler", Mock(side_effect=ImportError("synthetic")))
        with pytest.warns(RuntimeWarning, match="Windows"):
            handler = module.get_file_handler()
        assert isinstance(handler, module.SafeTimedRotatingFileHandler)
    else:
        handler = module.get_file_handler()
        assert isinstance(handler, ConcurrentRotatingFileHandler)
    attached = module.FilteredHandler(handler, module.CategoryFilter.for_general_logs()) if filtered else handler
    logger = logging.Logger("synthetic-windows-budget", logging.DEBUG if debug else logging.INFO)
    logger.addHandler(attached)
    try:
        assert module.get_file_handler() is handler
        assert handler.level == (logging.DEBUG if debug else logging.INFO)
        logger.debug("[CTX-BUILD][effective] token_mode=delta_only total=915")
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(logger.debug, "[CTX-BUILD][anchor] stage=response_committed anchored=True").result()
        logger.info("[CTX-BUILD][effective] token_mode=recount_all reason=no_baseline total=210")
        handler.flush()
        text = target.read_text(encoding="utf-8")
        assert ("token_mode=delta_only" in text) is debug
        assert ("stage=response_committed" in text) is debug
        assert "token_mode=recount_all" in text
    finally:
        logger.removeHandler(attached)
        if filtered:
            attached.close()
        handler.close()
    target.replace(folder / "closed.log")
    (folder / "closed.log").unlink()