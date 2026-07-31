"""Integration tests covering FactStore + HolographicProvider end-to-end."""

import json
from pathlib import Path

import pytest

from siada.config.config_loader import HolographicConfig
from siada.services.memory.holographic.provider import HolographicProvider


@pytest.fixture
def provider(tmp_path):
    cfg = HolographicConfig(
        enabled=True,
        hrr_dim=1024,          # 1024 provides high SNR for complex unbind actions
        db_path=str(tmp_path / "facts.db"),
        prefetch_limit=3,
        min_trust_threshold=0.0,  # tests don't seed feedback signal
    )
    p = HolographicProvider.from_config(cfg)
    p.initialize()
    yield p
    p.shutdown()


def _call(provider, **args) -> dict:
    """Helper: invoke fact_store and decode the JSON wrapper."""
    return json.loads(provider.handle_tool_call("fact_store", args))


# --------------------------------------------------------------------- #
# add / list / dedup
# --------------------------------------------------------------------- #

def test_add_returns_fact_id_and_extracts_entities(provider):
    res = _call(
        provider, action="add",
        content='Phoenix uses "Postgres" 14 for backend',
        category="project",
    )
    assert res["success"] is True
    assert res["created"] is True
    assert res["fact_id"] >= 1
    # Postgres should be picked up as a tech entity (jieba tech-dict),
    # 'Postgres' as the quoted token.
    names = [n.lower() for n in res["entities"]]
    assert "postgres" in names


def test_add_is_idempotent_on_exact_duplicate(provider):
    a = _call(provider, action="add", content="Identical fact", category="general")
    b = _call(provider, action="add", content="Identical fact", category="general")
    assert a["fact_id"] == b["fact_id"]
    assert b["created"] is False
    assert b.get("duplicate") is True


def test_list_facts_filters_by_category(provider):
    _call(provider, action="add", content="A user pref", category="user_pref")
    _call(provider, action="add", content="A project fact", category="project")
    res = _call(provider, action="list", category="user_pref")
    assert all(r["category"] == "user_pref" for r in res["results"])
    assert any("user pref" in r["content"] for r in res["results"])


# --------------------------------------------------------------------- #
# search / probe / reason
# --------------------------------------------------------------------- #

def test_search_finds_keyword_match(provider):
    _call(provider, action="add",
          content="Phoenix project uses Postgres 14",
          category="project")
    _call(provider, action="add",
          content="We chose Redis for cache layer",
          category="project")
    res = _call(provider, action="search", query="Postgres")
    assert res["success"] is True
    assert len(res["results"]) >= 1
    assert "Postgres" in res["results"][0]["content"]


def test_reason_returns_results_for_known_entities(provider):
    _call(provider, action="add",
          content='In "Phoenix" we picked Postgres', category="project")
    _call(provider, action="add",
          content="Vim is faster than VS Code", category="user_pref")
    res = _call(provider, action="reason", entities=["Phoenix", "Postgres"])
    assert res["success"] is True
    # reason returns scored results — sanity-check shape, not absolute scores.
    assert isinstance(res["results"], list)


# --------------------------------------------------------------------- #
# feedback / trust
# --------------------------------------------------------------------- #

def test_feedback_helpful_raises_trust(provider):
    add = _call(provider, action="add", content="Some fact", category="general")
    fid = add["fact_id"]
    out = json.loads(provider.handle_tool_call(
        "fact_feedback", {"fact_id": fid, "action": "helpful"},
    ))
    assert out["success"] is True
    # Default trust 0.5 + 0.05 helpful delta.
    assert out["trust_score"] == pytest.approx(0.55, abs=1e-6)


def test_feedback_unhelpful_lowers_trust_twice_as_fast(provider):
    add = _call(provider, action="add", content="Some fact", category="general")
    fid = add["fact_id"]
    out = json.loads(provider.handle_tool_call(
        "fact_feedback", {"fact_id": fid, "action": "unhelpful"},
    ))
    # 0.5 - 0.10 = 0.40 (asymmetric step on purpose).
    assert out["trust_score"] == pytest.approx(0.40, abs=1e-6)


# --------------------------------------------------------------------- #
# update / remove
# --------------------------------------------------------------------- #

def test_update_changes_content_and_keeps_fact_id(provider):
    add = _call(provider, action="add",
                content="Original content", category="general")
    fid = add["fact_id"]
    out = _call(provider, action="update", fact_id=fid, content="New content")
    assert out["success"] is True
    assert out["fact_id"] == fid


def test_remove_deletes_fact(provider):
    add = _call(provider, action="add",
                content="To be deleted", category="general")
    fid = add["fact_id"]
    out = _call(provider, action="remove", fact_id=fid)
    assert out["success"] is True
    # list should no longer return it
    listed = _call(provider, action="list")
    assert all(r["fact_id"] != fid for r in listed["results"])


# --------------------------------------------------------------------- #
# prefetch + on_memory_write
# --------------------------------------------------------------------- #

def test_prefetch_returns_markdown_block(provider):
    _call(provider, action="add",
          content="Phoenix uses Postgres 14", category="project")
    out = provider.prefetch("Postgres")
    assert out.startswith("## Holographic Memory")
    assert "Postgres" in out
    # Each fact line shows trust and fact_id.
    assert "[" in out and "#" in out


def test_prefetch_empty_on_no_match(provider):
    _call(provider, action="add",
          content="Some unrelated fact", category="general")
    out = provider.prefetch("zzz_unmatched_query")
    # No FTS hits → empty string (caller skips injection).
    assert out == ""


# --------------------------------------------------------------------- #
# Chinese recall — both write and query sides go through jieba
#
# Write side: ``store._siada_jieba_tokenize`` segments and space-joins
# ``content`` so the FTS5 index for "凤凰项目使用 Postgres 14 作为主数据库"
# carries jieba words like ["凤凰", "项目", "使用", "postgres", "14", ...].
#
# Query side: ``retrieval._build_fts_match_query`` mirrors that — it cuts
# the query with jieba and emits an OR-of-quoted-tokens FTS5 expression.
# This keeps Chinese phrasal queries usable, e.g. "凤凰项目用什么数据库"
# becomes ``"凤凰" OR "项目" OR "用" OR "什么" OR "数据库"`` and recalls.
# --------------------------------------------------------------------- #

def test_prefetch_recalls_chinese_single_jieba_word(provider):
    """A single Chinese word aligned with a jieba-indexed token recalls."""
    _call(
        provider, action="add",
        content="凤凰项目使用 Postgres 14 作为主数据库",
        category="project",
    )
    out = provider.prefetch("凤凰")
    assert out.startswith("## Holographic Memory")
    assert "凤凰项目" in out
    assert "Postgres" in out


def test_prefetch_recalls_chinese_with_whitespace_separated_tokens(provider):
    """Whitespace-separated Chinese phrase recalls — each chunk hits a token."""
    _call(
        provider, action="add",
        content="凤凰项目使用 Postgres 14 作为主数据库",
        category="project",
    )
    # Pre-split is also fine — jieba on the query side is idempotent for
    # already-split inputs.
    out = provider.prefetch("凤凰 项目 数据库")
    assert out.startswith("## Holographic Memory")
    assert "Postgres" in out


def test_prefetch_recalls_chinese_continuous_phrase(provider):
    """A natural continuous Chinese phrase recalls — query-side jieba tokenization
    realigns it with the indexed jieba words written at insert time.
    """
    _call(
        provider, action="add",
        content="凤凰项目使用 Postgres 14 作为主数据库",
        category="project",
    )
    out = provider.prefetch("凤凰项目用什么数据库")
    assert out.startswith("## Holographic Memory")
    assert "凤凰项目" in out
    assert "Postgres" in out


def test_prefetch_empty_on_chinese_unrelated_query(provider):
    """Unrelated Chinese query yields zero FTS candidates → empty injection."""
    _call(
        provider, action="add",
        content="凤凰项目使用 Postgres 14 作为主数据库",
        category="project",
    )
    out = provider.prefetch("今天天气怎么样")
    assert out == ""


def test_on_memory_write_mirrors_add(provider):
    before = provider.fact_count()
    provider.on_memory_write("add", "user", "User likes concise emails")
    after = provider.fact_count()
    assert after == before + 1
    cats = dict(provider.store.categories())
    # 'user' target maps to 'user_pref' category per provider convention.
    assert cats.get("user_pref", 0) >= 1


def test_on_memory_write_ignores_replace_and_remove(provider):
    before = provider.fact_count()
    provider.on_memory_write("replace", "user", "anything")
    provider.on_memory_write("remove", "user", "anything")
    assert provider.fact_count() == before


# --------------------------------------------------------------------- #
# disabled provider returns errors gracefully
# --------------------------------------------------------------------- #

def test_handle_tool_call_unknown_tool(provider):
    out = json.loads(provider.handle_tool_call("not_a_tool", {}))
    assert out["success"] is False
    assert "unknown" in out["error"]


def test_fact_store_action_validation(provider):
    out = _call(provider, action="add")  # missing content
    assert out["success"] is False
    assert "content" in out["error"]


