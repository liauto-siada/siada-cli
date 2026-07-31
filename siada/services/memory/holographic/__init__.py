"""Holographic structured fact memory.

A SQLite + FTS5 + HRR (phase-vector based) layer that stores atomic facts
with entity-binding and trust scoring. Complements the inline MEMORY.md /
USER.md store and the chunk-based memory.db search index.

Key components:
- ``hrr``           — phase-vector HRR algebra (encode_atom / bind / unbind / bundle).
- ``entity_extractor`` — jieba pos-tagging + regex double-track entity extraction.
- ``store.FactStore`` — SQLite-backed fact persistence with FTS5 (jieba-tokenized).
- ``retrieval.FactRetriever`` — 5 retrieval actions: search / probe / related / reason / contradict.
- ``provider.HolographicProvider`` — top-level façade for tool dispatch and prefetch.

See design_docs/siada-holographic-memory-introduction.md for the full design.
"""

# Lazy re-export to avoid forcing every importer to pull in the full
# stack (provider → store → numpy/jieba) when they only want, say, ``hrr``.
__all__ = ["HolographicProvider"]


def __getattr__(name: str):
    if name == "HolographicProvider":
        from siada.services.memory.holographic.provider import HolographicProvider
        return HolographicProvider
    raise AttributeError(f"module 'siada.services.memory.holographic' has no attribute {name!r}")
