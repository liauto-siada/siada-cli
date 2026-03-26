"""
Test suite for smart memory search functionality.

This module provides tests to verify that the smart memory search agent
works correctly and provides better results than direct memory search.
"""

import asyncio
import logging
from unittest.mock import MagicMock
from siada.tools.memory.smart_memory_search import (
    get_memory_search_agent,
    _smart_search_memory_impl
)
from siada.foundation.code_agent_context import CodeAgentContext

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_mock_context():
    """Create a mock context for testing."""
    context = CodeAgentContext(root_dir="/tmp")
    # Mock the session and config
    mock_session = MagicMock()
    mock_config = MagicMock()
    mock_llm_config = MagicMock()
    mock_llm_config.model_name = "gpt-4o-mini"
    mock_llm_config.provider = "openai"
    mock_config.llm_config = mock_llm_config
    mock_session.siada_config = mock_config
    context.session = mock_session
    return context


async def test_memory_search_agent_creation():
    """Test that the memory search agent can be created successfully."""
    logger.info("Testing memory search agent creation...")
    
    try:
        context = create_mock_context()
        agent = get_memory_search_agent(context)
        assert agent is not None
        assert agent.name == "MemorySearchAgent"
        assert len(agent.tools) == 2  # search_memory and get_memory
        
        logger.info("✓ Memory search agent created successfully")
        logger.info(f"  - Agent name: {agent.name}")
        logger.info(f"  - Model: {agent.model}")
        logger.info(f"  - Tools: {[tool.name for tool in agent.tools]}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to create memory search agent: {e}")
        return False


async def test_smart_memory_search_basic():
    """Test basic smart memory search functionality."""
    logger.info("\nTesting basic smart memory search...")
    
    try:
        context = create_mock_context()
        # Test with a simple query
        query = "API design decisions"
        result = await _smart_search_memory_impl(
            context=context,
            query=query,
            max_tokens=1000,
            detail_level="brief"
        )
        
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
        
        logger.info("✓ Basic smart memory search completed")
        logger.info(f"  - Query: {query}")
        logger.info(f"  - Result length: {len(result)} characters")
        logger.info(f"  - Result preview: {result[:200]}...")
        return True
    except Exception as e:
        logger.error(f"✗ Basic smart memory search failed: {e}", exc_info=True)
        return False


async def test_smart_memory_search_detail_levels():
    """Test smart memory search with different detail levels."""
    logger.info("\nTesting smart memory search with different detail levels...")
    
    context = create_mock_context()
    query = "recent changes"
    detail_levels = ["brief", "medium", "detailed"]
    
    try:
        for level in detail_levels:
            result = await _smart_search_memory_impl(
                context=context,
                query=query,
                max_tokens=2000,
                detail_level=level
            )
            
            assert result is not None
            assert isinstance(result, str)
            
            logger.info(f"✓ Detail level '{level}' completed")
            logger.info(f"  - Result length: {len(result)} characters")
        
        logger.info("✓ All detail levels tested successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Detail level test failed: {e}", exc_info=True)
        return False


async def test_smart_memory_search_validation():
    """Test input validation for smart memory search."""
    logger.info("\nTesting input validation...")
    
    context = create_mock_context()
    test_cases = [
        # (query, max_tokens, detail_level, should_error)
        ("", 1000, "medium", True),  # Empty query
        ("test", -1, "medium", True),  # Negative max_tokens
        ("test", 1000, "invalid", True),  # Invalid detail_level
        ("valid query", 1000, "medium", False),  # Valid input
    ]
    
    passed = 0
    for query, max_tokens, detail_level, should_error in test_cases:
        try:
            result = await _smart_search_memory_impl(
                context=context,
                query=query,
                max_tokens=max_tokens,
                detail_level=detail_level
            )
            
            if should_error:
                # Should have returned an error message
                assert "Error:" in result
                passed += 1
                logger.info(f"✓ Validation test passed (expected error): {result[:50]}")
            else:
                # Should have succeeded
                assert "Error:" not in result or "No relevant" in result
                passed += 1
                logger.info(f"✓ Validation test passed (expected success)")
        except Exception as e:
            logger.error(f"✗ Validation test failed: {e}")
    
    logger.info(f"✓ Validation tests: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


async def test_smart_memory_search_chinese():
    """Test smart memory search with Chinese query."""
    logger.info("\nTesting smart memory search with Chinese query...")
    
    try:
        context = create_mock_context()
        query = "数据库设计方案"
        result = await _smart_search_memory_impl(
            context=context,
            query=query,
            max_tokens=1000,
            detail_level="medium"
        )
        
        assert result is not None
        assert isinstance(result, str)
        
        logger.info("✓ Chinese query test completed")
        logger.info(f"  - Query: {query}")
        logger.info(f"  - Result length: {len(result)} characters")
        return True
    except Exception as e:
        logger.error(f"✗ Chinese query test failed: {e}", exc_info=True)
        return False


async def run_all_tests():
    """Run all tests and report results."""
    logger.info("=" * 70)
    logger.info("Starting Smart Memory Search Tests")
    logger.info("=" * 70)
    
    tests = [
        ("Agent Creation", test_memory_search_agent_creation),
        ("Basic Search", test_smart_memory_search_basic),
        ("Detail Levels", test_smart_memory_search_detail_levels),
        ("Input Validation", test_smart_memory_search_validation),
        ("Chinese Query", test_smart_memory_search_chinese),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = await test_func()
            results.append((name, success))
        except Exception as e:
            logger.error(f"Test '{name}' crashed: {e}")
            results.append((name, False))
    
    # Print summary
    logger.info("\n" + "=" * 70)
    logger.info("Test Summary")
    logger.info("=" * 70)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        logger.info(f"{status}: {name}")
    
    logger.info("-" * 70)
    logger.info(f"Total: {passed}/{total} tests passed")
    logger.info("=" * 70)
    
    return passed == total


if __name__ == "__main__":
    # Run the tests
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
