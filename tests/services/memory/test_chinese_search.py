"""
Test suite for Chinese search with jieba word segmentation.

PyTest-compatible test cases demonstrating Chinese search capabilities
with jieba integration.
"""

import tempfile
from pathlib import Path

import pytest

from siada.services.memory import MemoryDatabase, MemorySearch


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def chinese_test_files(temp_dir):
    """Create test files with Chinese content."""
    files = {}
    
    # File 1: Python 教程
    files['python'] = temp_dir / "2024-01-15-10-00-python-tutorial.md"
    files['python'].write_text("""# Session: 2024-01-15 10:00:00

- **Session ID**: python-tutorial-001
- **Timestamp**: 2024-01-15 10:00:00

## Conversation Summary

user: 我想学习Python编程，应该从哪里开始？
assistant: 学习Python编程是一个很好的选择！我建议你从以下几个方面开始：

1. 基础语法：变量、数据类型、条件语句、循环
2. 函数和模块：理解如何组织代码
3. 面向对象编程：类和对象的概念
4. 常用库：requests、pandas、numpy等

你可以通过官方教程和实践项目来学习。
""", encoding='utf-8')
    
    # File 2: Web开发
    files['web'] = temp_dir / "2024-01-16-web-development.md"
    files['web'].write_text("""# Session: 2024-01-16 14:00:00

- **Session ID**: web-dev-002
- **Timestamp**: 2024-01-16 14:00:00

## Conversation Summary

user: 我想学习Web开发，应该选择Django还是FastAPI？
assistant: 这是一个很好的问题！Django和FastAPI各有优势：

**Django的优势：**
- 功能完整的全栈框架
- 自带管理后台
- ORM功能强大

**FastAPI的优势：**
- 现代异步框架
- 自动生成API文档
- 类型提示支持
- 性能优秀

对于学习Python编程和Web开发，我推荐从FastAPI开始。
""", encoding='utf-8')
    
    # File 3: 机器学习
    files['ml'] = temp_dir / "2024-01-17-machine-learning.md"
    files['ml'].write_text("""# Session: 2024-01-17 09:00:00

- **Session ID**: ml-003
- **Timestamp**: 2024-01-17 09:00:00

## Conversation Summary

user: 如何开始学习机器学习？
assistant: 学习机器学习需要以下基础：

1. Python编程基础
2. 数学基础（线性代数、概率论）
3. 常用库：numpy、pandas、scikit-learn
4. 深度学习框架：TensorFlow或PyTorch

建议先从Python基础开始，再学习机器学习算法。
""", encoding='utf-8')
    
    return files


@pytest.fixture
def indexed_chinese_db(temp_dir, chinese_test_files):
    """Create and index Chinese test files in database."""
    db_path = temp_dir / "test_chinese.db"
    db = MemoryDatabase(db_path, enable_chinese=True)
    
    # Index all files
    for file_path in chinese_test_files.values():
        db.index_file(file_path, source='memory', model='none')
    
    db.close()
    return db_path


class TestChineseSearch:
    """Test suite for Chinese search functionality."""
    
    def test_chinese_keyword_search(self, indexed_chinese_db):
        """Test searching with Chinese keywords."""
        search = MemorySearch(indexed_chinese_db, enable_chinese=True)
        
        # Search for "学习" (learning)
        results = search.search("学习", limit=10)
        assert len(results) > 0, "No results for Chinese keyword '学习'"
        
        # Should find multiple files
        assert len(results) >= 2, "Should find multiple files containing '学习'"
        
        search.close()
    
    def test_english_keyword_search(self, indexed_chinese_db):
        """Test searching with English keywords in Chinese content."""
        search = MemorySearch(indexed_chinese_db, enable_chinese=True)
        
        # Search for "Python"
        results = search.search("Python", limit=10)
        assert len(results) > 0, "No results for 'Python'"
        
        # Search for "FastAPI"
        results = search.search("FastAPI", limit=10)
        assert len(results) > 0, "No results for 'FastAPI'"
        
        # Verify FastAPI appears in web development file
        web_results = [r for r in results if 'web-development' in r.path]
        assert len(web_results) > 0, "FastAPI not found in web development file"
        
        search.close()
    
    def test_mixed_chinese_english_search(self, indexed_chinese_db):
        """Test searching with mixed Chinese-English query."""
        search = MemorySearch(indexed_chinese_db, enable_chinese=True)
        
        # Search for "学习 Python" (learn Python)
        results = search.search("学习 Python", limit=10)
        assert len(results) > 0, "No results for mixed query '学习 Python'"
        
        # Should find files discussing Python learning
        python_results = [r for r in results if 'python' in r.path.lower() or 'Python' in r.snippet]
        assert len(python_results) > 0, "No Python-related results found"
        
        search.close()
    
    def test_chinese_phrase_search(self, indexed_chinese_db):
        """Test searching with Chinese phrases."""
        search = MemorySearch(indexed_chinese_db, enable_chinese=True)
        
        # Search for "机器学习" (machine learning)
        results = search.search("机器学习", limit=10)
        assert len(results) > 0, "No results for '机器学习'"
        
        # Should find machine learning file
        ml_results = [r for r in results if 'machine-learning' in r.path]
        assert len(ml_results) > 0, "Machine learning file not found"
        
        # Search for "Web开发" (web development)
        results = search.search("Web开发", limit=10)
        assert len(results) > 0, "No results for 'Web开发'"
        
        search.close()
    
    def test_chinese_technical_terms(self, indexed_chinese_db):
        """Test searching with technical terms."""
        search = MemorySearch(indexed_chinese_db, enable_chinese=True)
        
        # These should work with default tech terms dictionary
        technical_queries = [
            ("FastAPI", 1),  # Should find at least 1 file
            ("Django", 1),   # Should find at least 1 file
            ("Python", 2),   # Should find at least 2 files
        ]
        
        for query, min_results in technical_queries:
            results = search.search(query, limit=10)
            assert len(results) >= min_results, f"Expected at least {min_results} results for '{query}', got {len(results)}"
        
        search.close()
    
    def test_search_without_chinese(self, temp_dir, chinese_test_files):
        """Test search behavior with Chinese disabled."""
        # Index with Chinese disabled
        db_path = temp_dir / "test_no_chinese.db"
        db = MemoryDatabase(db_path, enable_chinese=False)
        
        for file_path in chinese_test_files.values():
            db.index_file(file_path, source='memory', model='none')
        
        db.close()
        
        # Search with Chinese disabled
        search = MemorySearch(db_path, enable_chinese=False)
        
        # English keywords should still work
        results = search.search("Python", limit=10)
        assert len(results) > 0, "English search should work even with Chinese disabled"
        
        # Chinese keywords might not work well
        results = search.search("学习", limit=10)
        # We don't assert here as behavior without jieba is limited
        
        search.close()
    
    def test_search_result_scores(self, indexed_chinese_db):
        """Test that search results have valid scores."""
        search = MemorySearch(indexed_chinese_db, enable_chinese=True)
        
        results = search.search("Python", limit=10)
        
        assert len(results) > 0, "No results to test scores"
        
        for result in results:
            assert 0 <= result.score <= 1, f"Invalid score: {result.score}"
            assert len(result.snippet) > 0, "Empty snippet"
            assert result.path, "Empty path"
        
        # Scores should be in descending order
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True), "Results not sorted by score"
        
        search.close()


class TestChineseSegmentation:
    """Test Chinese word segmentation behavior."""
    
    def test_stopwords_filtering(self, indexed_chinese_db):
        """Test that stopwords are filtered from queries."""
        search = MemorySearch(indexed_chinese_db, enable_chinese=True)
        
        # Query with stopwords
        results1 = search.search("学习 Python", limit=10)
        results2 = search.search("学习的Python", limit=10)  # "的" is a stopword
        
        # Both should return similar results
        assert len(results1) > 0, "No results for query 1"
        assert len(results2) > 0, "No results for query 2"
        
        search.close()
    
    def test_custom_dictionary(self, temp_dir, chinese_test_files):
        """Test custom dictionary addition."""
        db_path = temp_dir / "test_custom_dict.db"
        db = MemoryDatabase(db_path, enable_chinese=True)
        
        for file_path in chinese_test_files.values():
            db.index_file(file_path, source='memory', model='none')
        
        db.close()
        
        # Create search with custom dictionary
        search = MemorySearch(
            db_path,
            enable_chinese=True,
            custom_dict=['自定义词汇', 'CustomTerm']
        )
        
        assert search.enable_chinese, "Chinese should be enabled"
        
        search.close()


# Standalone test for backward compatibility
def test_chinese_search_standalone():
    """Standalone test for Chinese search (pytest compatible)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        db_path = tmpdir / "test_standalone.db"
        
        # Create test file
        test_file = tmpdir / "test.md"
        test_file.write_text("# 测试\n\n这是一个Python编程教程。", encoding='utf-8')
        
        # Index
        db = MemoryDatabase(db_path, enable_chinese=True)
        db.index_file(test_file, source='test', model='none')
        db.close()
        
        # Search
        search = MemorySearch(db_path, enable_chinese=True)
        results = search.search("Python", limit=5)
        assert len(results) > 0, "No results found"
        
        results = search.search("编程", limit=5)
        assert len(results) > 0, "No Chinese results found"
        
        search.close()
