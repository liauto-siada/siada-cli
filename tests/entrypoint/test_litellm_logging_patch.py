"""Tests for LiteLLM logging serializer patch functionality."""

from __future__ import annotations

import importlib

import pytest

pytest.importorskip("litellm")


def _reset_patch_state():
    """Reset the patch state on litellm_logging module to allow re-patching."""
    try:
        litellm_logging = importlib.import_module("litellm.litellm_core_utils.litellm_logging")
        if hasattr(litellm_logging, "_siada_patched_serializer_warnings"):
            delattr(litellm_logging, "_siada_patched_serializer_warnings")
    except Exception:
        pass


def test_litellm_logging_patch_applied_on_li_provider_import():
    """Assert the serializer patch is applied when li_provider module is imported."""
    _reset_patch_state()
    
    litellm_logging = importlib.import_module("litellm.litellm_core_utils.litellm_logging")
    
    # Ensure LiteLLM has the function we're patching
    assert hasattr(
        litellm_logging,
        "_extract_response_obj_and_hidden_params",
    ), "LiteLLM removed _extract_response_obj_and_hidden_params; revisit warning patch."
    
    # Verify patch state is initially false
    _reset_patch_state()
    assert getattr(litellm_logging, "_siada_patched_serializer_warnings", False) is False
    
    # Import li_provider which should apply the patch
    li_provider = importlib.import_module("siada.provider.li.li_provider")
    importlib.reload(li_provider)
    
    # Verify patch was applied
    assert getattr(litellm_logging, "_siada_patched_serializer_warnings", False) is True


def test_litellm_logging_patch_double_import_safe():
    """Assert the patch doesn't re-apply on multiple imports (double-patch guard)."""
    _reset_patch_state()
    
    litellm_logging = importlib.import_module("litellm.litellm_core_utils.litellm_logging")
    li_provider = importlib.import_module("siada.provider.li.li_provider")
    
    # First reload to apply patch
    importlib.reload(li_provider)
    assert getattr(litellm_logging, "_siada_patched_serializer_warnings", False) is True
    
    # Second reload should not cause issues (double-patch guard)
    importlib.reload(li_provider)
    assert getattr(litellm_logging, "_siada_patched_serializer_warnings", False) is True
