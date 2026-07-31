"""Unit tests for HRR phase-vector algebra."""

import math
import numpy as np
import pytest

from siada.services.memory.holographic import hrr


def test_encode_atom_shape_and_dtype():
    v = hrr.encode_atom("hello", 1024)
    assert v.shape == (1024,)
    assert v.dtype == np.float64
    # All phases live in [0, 2pi).
    assert np.all(v >= 0.0)
    assert np.all(v < 2.0 * math.pi + 1e-9)


def test_encode_atom_is_deterministic_across_calls():
    a = hrr.encode_atom("hello", 1024)
    b = hrr.encode_atom("hello", 1024)
    np.testing.assert_array_equal(a, b)


def test_encode_atom_different_words_quasi_orthogonal():
    a = hrr.encode_atom("hello", 1024)
    b = hrr.encode_atom("world", 1024)
    # Distinct atoms should be near-zero similarity (quasi-orthogonal).
    assert abs(hrr.similarity(a, b)) < 0.1


def test_bind_unbind_exact_recovery():
    a = hrr.encode_atom("alpha", 512)
    b = hrr.encode_atom("beta", 512)
    bound = hrr.bind(a, b)
    recovered = hrr.unbind(bound, a)
    # Exact algebraic invertibility (no bundle in between).
    assert hrr.similarity(recovered, b) == pytest.approx(1.0, abs=1e-9)


def test_similarity_range():
    a = hrr.encode_atom("foo", 256)
    assert hrr.similarity(a, a) == pytest.approx(1.0, abs=1e-9)
    # Anti-phase via shifting by pi.
    flipped = (a + math.pi) % (2 * math.pi)
    assert hrr.similarity(a, flipped) == pytest.approx(-1.0, abs=1e-9)


def test_encode_text_empty_fallback():
    # Empty/whitespace input falls back to the EMPTY_ATOM.
    empty = hrr.encode_text("", 256)
    np.testing.assert_array_equal(empty, hrr.encode_atom(hrr.EMPTY_ATOM, 256))


def test_encode_text_uses_jieba_for_chinese():
    # Chinese text should produce a non-empty bundle (jieba splits to multi-char tokens).
    cn = hrr.encode_text("李想 喜欢 简洁", 256)
    assert cn.shape == (256,)


def test_encode_fact_round_trip_serialization():
    v = hrr.encode_fact("Phoenix uses Postgres", ["Phoenix", "Postgres"], 512)
    blob = hrr.phases_to_bytes(v)
    restored = hrr.bytes_to_phases(blob)
    np.testing.assert_array_almost_equal(v, restored)


def test_snr_estimate_monotonic():
    # SNR drops as items grow.
    assert hrr.snr_estimate(1024, 4) > hrr.snr_estimate(1024, 16)
    assert hrr.snr_estimate(1024, 0) == float("inf")


def test_entity_extractor_mixed_and_deduplicate():
    # Regular expressions extract 'VS Code' and 'John Doe'.
    # jieba pos-tag extracts '北京' (place/ns) and 'Postgres' (tech dict).
    # Single character words like '在' or '用' are dropped to avoid noise.
    from siada.services.memory.holographic.entity_extractor import extract_entities
    raw = '北京 的 Phoenix 项目用 Postgres 数据库, John Doe prefers "VS Code"'
    ents = extract_entities(raw)
    
    names = [e[0] for e in ents]
    # Check that both English regex tracks and Chinese jieba tracks worked
    assert "John Doe" in names
    assert "VS Code" in names
    assert "Postgres" in names
    assert "北京" in names
    
    # Check deduplication case insensitivity
    # 'postgres' vs 'Postgres' deduplicated keeping first case
    dup_raw = "Postgres uses Postgres with postgres"
    ents_dup = extract_entities(dup_raw)
    postgres_matches = [e for e in ents_dup if e[0].lower() == "postgres"]
    assert len(postgres_matches) == 1
    assert postgres_matches[0][0] == "Postgres"  # first case preserved
