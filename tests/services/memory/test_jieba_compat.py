"""Keep jieba usable without masking unrelated deprecation warnings."""

import subprocess
import sys


def test_memory_callers_share_the_original_jieba_module():
    from siada.services.memory import memory_db, memory_search
    from siada.services.memory.holographic import entity_extractor, hrr, retrieval, store
    from siada.services.memory.jieba_compat import import_posseg, jieba
    from siada.tools.memory import memory_tool

    for module in (memory_db, memory_search, entity_extractor, hrr, retrieval, store, memory_tool):
        assert module.jieba is jieba
    assert entity_extractor.pseg is import_posseg()


def test_plain_jieba_import_does_not_eagerly_import_posseg():
    script = """
import sys

from siada.services.memory.jieba_compat import jieba

assert 'jieba.posseg' not in sys.modules
assert list(jieba.cut('中文分词'))
"""
    result = subprocess.run(
        [sys.executable, "-W", "error::DeprecationWarning", "-c", script],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_jieba_import_is_quiet_when_deprecations_are_errors():
    script = """
import warnings

from siada.services.memory.jieba_compat import import_posseg, jieba

assert list(jieba.cut('中文分词'))
posseg = import_posseg()
assert list(posseg.cut('中文分词'))
try:
    warnings.warn('unrelated deprecation', DeprecationWarning)
except DeprecationWarning:
    pass
else:
    raise AssertionError('unrelated deprecations must not be suppressed')
"""
    result = subprocess.run(
        [sys.executable, "-W", "error::DeprecationWarning", "-c", script],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
