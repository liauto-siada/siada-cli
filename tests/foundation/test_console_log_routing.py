"""File-only diagnostics reach log files without being printed on the console."""

import io
import logging

import pytest

from siada.foundation.log_category import LogCategory
from siada.foundation.logging import CategoryFilter, FilteredHandler


def make_record(category=None):
    record = logging.LogRecord(
        name="siada.synthetic", level=logging.INFO, pathname=__file__, lineno=1,
        msg="synthetic message", args=(), exc_info=None,
    )
    if category is not None:
        record.log_category = category
    return record


@pytest.mark.parametrize("category", [None, LogCategory.GENERAL])
def test_console_filter_keeps_regular_records(category):
    assert CategoryFilter.for_console().filter(make_record(category))


@pytest.mark.parametrize("category", [LogCategory.MODEL_ERROR, LogCategory.FILE_ONLY])
def test_console_filter_drops_file_diagnostics(category):
    assert not CategoryFilter.for_console().filter(make_record(category))


def test_general_log_file_keeps_file_only_diagnostics():
    assert CategoryFilter.for_general_logs().filter(make_record(LogCategory.FILE_ONLY))
    assert not CategoryFilter.for_general_logs().filter(make_record(LogCategory.MODEL_ERROR))


def test_error_log_file_keeps_model_errors_only():
    errors = CategoryFilter.for_model_errors()
    assert errors.filter(make_record(LogCategory.MODEL_ERROR))
    assert not errors.filter(make_record(LogCategory.FILE_ONLY))


def test_file_only_record_skips_console_and_reaches_log_file(tmp_path):
    console = io.StringIO()
    console_handler = logging.StreamHandler(console)
    console_handler.addFilter(CategoryFilter.for_console())

    target = tmp_path / "siada_cli.log"
    file_handler = FilteredHandler(
        logging.FileHandler(target, encoding="utf-8"), CategoryFilter.for_general_logs(),
    )

    logger = logging.Logger("synthetic-console-routing", logging.INFO)
    logger.propagate = False
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    try:
        logger.info("console and file", extra={"log_category": LogCategory.GENERAL})
        logger.info("file only", extra={"log_category": LogCategory.FILE_ONLY})
    finally:
        logger.removeHandler(console_handler)
        logger.removeHandler(file_handler)
        console_handler.close()
        file_handler.close()

    assert console.getvalue() == "console and file\n"
    written = target.read_text(encoding="utf-8")
    assert "console and file" in written
    assert "file only" in written
