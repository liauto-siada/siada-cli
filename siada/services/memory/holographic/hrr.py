"""Phase-vector Holographic Reduced Representations (HRR).

A Vector Symbolic Architecture (VSA) variant where every "atom" is a vector
of phases in [0, 2pi)^dim. Bind / unbind / bundle become trivial elementwise
operations on phases, and similarity reduces to ``mean(cos(a-b))`` in [-1, 1].

Adapted from hermes-agent/plugins/memory/holographic/holographic.py with
two siada-specific tweaks:
  1. ``encode_text`` uses jieba (Chinese-aware) instead of ``str.split``.
  2. ``snr_estimate`` warning becomes a debug-level log to avoid noise.

NumPy is a hard dependency in siada-agenthub (see pyproject.toml), so we
don't carry a "numpy missing" fallback here — callers should still gate
on ``HolographicConfig.hrr_enabled`` to allow runtime opt-out.
"""

from __future__ import annotations

import hashlib
import logging
import math
import struct
import warnings
from typing import Iterable, List

import numpy as np

# Reuse the same jieba initialization pattern memory_db.py uses, so we
# don't pay the import cost twice and stay quiet about pkg_resources.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore", message="pkg_resources is deprecated", category=UserWarning,
    )
    warnings.filterwarnings("ignore", category=SyntaxWarning, module="jieba")
    import jieba

logger = logging.getLogger("siada.holographic.hrr")

# Silence jieba's startup banner.
jieba.setLogLevel(logging.WARNING)

_TWO_PI = 2.0 * math.pi

# Special atoms used as "roles" in compositional encodings. Their string
# bodies must stay stable across versions or HRR vectors written to disk
# in older versions become unreadable.
ROLE_CONTENT = "__hrr_role_content__"
ROLE_ENTITY = "__hrr_role_entity__"
EMPTY_ATOM = "__hrr_empty__"


def encode_atom(word: str, dim: int = 1024) -> np.ndarray:
    """Map a string to a deterministic phase vector of length ``dim``.

    Uses chained SHA-256 over ``f"{word}:{i}"`` so the result is reproducible
    across processes / Python versions / machines (no NumPy RNG involved).
    Each 16-bit unsigned slice of the digest scales to a phase in [0, 2pi),
    yielding a quasi-uniform distribution: distinct atoms are near-orthogonal
    under ``similarity``.
    """
    if dim <= 0:
        raise ValueError(f"dim must be positive, got {dim}")
    values_per_block = 16
    blocks_needed = math.ceil(dim / values_per_block)
    uint16_values: List[int] = []
    for i in range(blocks_needed):
        digest = hashlib.sha256(f"{word}:{i}".encode("utf-8")).digest()
        # 16 unsigned 16-bit ints, little-endian, exhausts the 32-byte digest.
        uint16_values.extend(struct.unpack("<16H", digest))
    phases = np.asarray(uint16_values[:dim], dtype=np.float64) * (_TWO_PI / 65536.0)
    return phases


def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Bind two phase vectors: elementwise addition modulo 2pi.

    Result is dissimilar to both ``a`` and ``b`` (phase sums randomize).
    Inverse is ``unbind`` thanks to mod-2pi commutativity.
    """
    return np.mod(a + b, _TWO_PI)


def unbind(memory: np.ndarray, key: np.ndarray) -> np.ndarray:
    """Unbind a key from memory: elementwise subtraction modulo 2pi.

    ``unbind(bind(a, b), a) == b`` exactly. When ``memory`` is a bundle of
    bound pairs, the result is ``b + noise`` whose magnitude is governed by
    ``snr_estimate(dim, n_items)``.
    """
    return np.mod(memory - key, _TWO_PI)


def bundle(*vectors: np.ndarray) -> np.ndarray:
    """Bundle (superpose) multiple phase vectors via circular mean.

    Maps each phase phi to its complex exponential e^{j phi}, sums, and
    extracts the angle. This is the statistically correct mean on the
    unit circle (a naive ``(a + b) % 2pi`` would be biased).
    """
    if not vectors:
        raise ValueError("bundle() requires at least one vector")
    # Stack to (n, dim) once and let numpy do the broadcast.
    stack = np.stack(vectors, axis=0)
    # complex64 is enough precision for circular mean and saves memory.
    complex_sum = np.sum(np.exp(1j * stack), axis=0)
    return np.mod(np.angle(complex_sum), _TWO_PI)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Phase-cosine similarity in [-1, 1].

    ``cos(0)=1``  → identical phases
    ``cos(pi/2)=0`` → unrelated
    ``cos(pi)=-1`` → anti-phase
    """
    return float(np.mean(np.cos(a - b)))


# --------------------------------------------------------------------- #
# Composite encodings
# --------------------------------------------------------------------- #

def _tokenize_text(text: str) -> List[str]:
    """jieba-segment text and keep non-empty tokens.

    Lowercased and stripped of common ASCII punctuation. Chinese punctuation
    is naturally dropped by jieba (it returns those as separate tokens that
    fail the ``isalnum``-style filter below).
    """
    if not text or not text.strip():
        return []
    try:
        raw = list(jieba.cut(text.lower()))
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("jieba.cut failed, falling back to whitespace split: %s", exc)
        raw = text.lower().split()
    tokens: List[str] = []
    for token in raw:
        token = token.strip(' .,!?;:"\'()[]{}<>，。！？；：（）【】《》、')
        if token:
            tokens.append(token)
    return tokens


def encode_text(text: str, dim: int = 1024) -> np.ndarray:
    """Bag-of-words bundle of token atoms.

    Word order is **not** preserved (HRR bundle is permutation-invariant).
    For atomic facts that's a tolerable trade-off.
    """
    tokens = _tokenize_text(text)
    if not tokens:
        return encode_atom("__hrr_empty__", dim)
    return bundle(*[encode_atom(t, dim) for t in tokens])


def encode_fact(content: str, entities: Iterable[str], dim: int = 1024) -> np.ndarray:
    """Encode a fact as a single HRR vector via role-binding.

    The resulting vector is::

        bundle(
            bind(content_vec, ROLE_CONTENT),
            bind(entity1_vec, ROLE_ENTITY),
            bind(entity2_vec, ROLE_ENTITY),
            ...
        )

    Unbinding ``bind(entity_X, ROLE_ENTITY)`` from the result recovers the
    content signal when ``entity_X`` is one of the bound entities, and
    recovers noise otherwise. This is the algebraic basis of probe / reason.
    """
    role_content = encode_atom(ROLE_CONTENT, dim)
    role_entity = encode_atom(ROLE_ENTITY, dim)

    components = [bind(encode_text(content, dim), role_content)]
    for entity in entities:
        if not entity:
            continue
        components.append(bind(encode_atom(entity.lower(), dim), role_entity))

    return bundle(*components)


# --------------------------------------------------------------------- #
# Serialization for SQLite BLOB storage
# --------------------------------------------------------------------- #

def phases_to_bytes(phases: np.ndarray) -> bytes:
    """Serialize a phase vector to bytes (float64, little-endian-native)."""
    if phases.dtype != np.float64:
        phases = phases.astype(np.float64)
    return phases.tobytes()


def bytes_to_phases(data: bytes) -> np.ndarray:
    """Deserialize bytes back to a writable float64 phase vector."""
    # ``np.frombuffer`` returns read-only views; ``.copy()`` makes the
    # caller's life easier (needed for in-place mod / bundle ops).
    return np.frombuffer(data, dtype=np.float64).copy()


# --------------------------------------------------------------------- #
# Capacity estimation
# --------------------------------------------------------------------- #

def snr_estimate(dim: int, n_items: int) -> float:
    """Approximate signal-to-noise ratio of unbinding from a bundle of N items.

    Classic HRR bound: SNR ~= sqrt(dim / N). When SNR < 2 the unbind residual
    is dominated by noise; the caller should consider raising ``hrr_dim``
    or partitioning facts across more categories.
    """
    if n_items <= 0:
        return float("inf")
    snr = math.sqrt(dim / n_items)
    if snr < 2.0:
        # Use debug, not warning — siada users normally stay well below the
        # 200-fact-per-bank threshold and we don't want chatty stderr.
        logger.debug(
            "[holographic] HRR bundle near capacity: dim=%d, n_items=%d, "
            "SNR=%.2f (consider raising hrr_dim or splitting categories)",
            dim, n_items, snr,
        )
    return snr
