"""
Demo script to show what search results look like.
Tests both English and Chinese content.
"""

import tempfile
from pathlib import Path
from siada.services.memory import MemoryDatabase, MemorySearch
import json


def demo_search_results():
    """Demonstrate what search results look like."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        db_path = tmpdir / "demo.db"
        
        # Create test markdown files with different content
        
        # File 1: English content about Python
        file1 = tmpdir / "2024-01-15-10-30-python-basics.md"
        file1.write_text("""# Session: 2024-01-15 10:30:00

- **Session ID**: python-basics-123
- **Timestamp**: 2024-01-15 10:30:00

## Conversation Summary

user: Can you teach me about Python decorators?
assistant: Python decorators are a powerful feature that allows you to modify the behavior of functions or classes. They use the @ symbol and are very useful for adding functionality like logging, timing, or authentication.

user: Show me a simple example.
assistant: Here's a basic decorator example:

```python
def my_decorator(func):
    def wrapper(*args, **kwargs):
        print("Before function call")
        result = func(*args, **kwargs)
        print("After function call")
        return result
    return wrapper

@my_decorator
def say_hello(name):
    print(f"Hello, {name}!")

say_hello("Alice")
```

This will print:
- Before function call
- Hello, Alice!
- After function call

user: That's very helpful, thanks!
assistant: You're welcome! Decorators are commonly used for cross-cutting concerns in Python applications.
""", encoding='utf-8')
        
        # File 2: Chinese content about FastAPI
        file2 = tmpdir / "2024-01-16-fastapi-tutorial.md"
        file2.write_text("""# Session: 2024-01-16 14:20:00

- **Session ID**: fastapi-tutorial-456
- **Timestamp**: 2024-01-16 14:20:00

## Conversation Summary

user: 我想学习 FastAPI，它和 Flask 有什么区别？
assistant: FastAPI 是一个现代的、快速的 Web 框架，专门用于构建 API。与 Flask 相比，FastAPI 有以下优势：

1. 自动生成 API 文档（Swagger UI 和 ReDoc）
2. 基于类型提示的数据验证
3. 原生支持异步编程（async/await）
4. 更好的性能
5. 内置依赖注入系统

user: 能给我一个简单的例子吗？
assistant: 当然可以！这是一个基础的 FastAPI 应用：

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float
    description: str = None

@app.get("/")
def read_root():
    return {"message": "欢迎使用 FastAPI"}

@app.post("/items/")
def create_item(item: Item):
    return {"item_name": item.name, "price": item.price}
```

运行方式：uvicorn main:app --reload

user: 太棒了！谢谢你的帮助。
assistant: 不客气！FastAPI 是构建现代 Python API 的最佳选择之一，特别适合需要高性能和自动文档的项目。
""", encoding='utf-8')
        
        # File 3: Mixed content about async programming
        file3 = tmpdir / "2024-01-17-async-programming.md"
        file3.write_text("""# Session: 2024-01-17 09:15:00

- **Session ID**: async-programming-789
- **Timestamp**: 2024-01-17 09:15:00

## Conversation Summary

user: What is async/await in Python and when should I use it?
assistant: Async/await is Python's way of writing asynchronous code. It's particularly useful for I/O-bound operations like:
- Network requests (API calls, database queries)
- File operations
- Web scraping
- Concurrent tasks that wait for external resources

The key benefit is that while one task is waiting (e.g., for a network response), your program can work on other tasks instead of blocking.

user: 能给我一个实际的例子吗？
assistant: 当然！这是一个同时获取多个 API 的例子：

```python
import asyncio
import aiohttp

async def fetch_data(session, url):
    async with session.get(url) as response:
        return await response.json()

async def main():
    urls = [
        "https://api.example.com/users/1",
        "https://api.example.com/users/2",
        "https://api.example.com/users/3"
    ]
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_data(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
        return results

# Run the async function
results = asyncio.run(main())
print(results)
```

这样可以并发获取多个 URL，比顺序获取快得多。

user: Excellent explanation! This is exactly what I needed.
assistant: Glad I could help! Remember that async/await shines when you have multiple I/O operations that can run concurrently.
""", encoding='utf-8')
        
        # Index all files
        print("=" * 70)
        print("INDEXING FILES")
        print("=" * 70)
        
        db = MemoryDatabase(db_path)
        
        for file in [file1, file2, file3]:
            success = db.index_file(file, source='memory', model='none')
            print(f"✓ Indexed: {file.name} (Success: {success})")
        
        db.close()
        
        # Now perform searches
        search = MemorySearch(db_path)
        
        print("\n" + "=" * 70)
        print("SEARCH DEMO - ENGLISH QUERIES")
        print("=" * 70)
        
        # Test 1: Search for "decorator"
        print("\n[Query 1] 'decorator'")
        print("-" * 70)
        results = search.search("decorator", limit=3)
        display_results(results)
        
        # Test 2: Search for "FastAPI"
        print("\n[Query 2] 'FastAPI'")
        print("-" * 70)
        results = search.search("FastAPI", limit=3)
        display_results(results)
        
        # Test 3: Search for "async await"
        print("\n[Query 3] 'async await'")
        print("-" * 70)
        results = search.search("async await", limit=3)
        display_results(results)
        
        print("\n" + "=" * 70)
        print("SEARCH DEMO - CHINESE QUERIES")
        print("=" * 70)
        
        # Test 4: Search for Chinese - exact characters
        print("\n[Query 4] '学习' (Chinese: learning)")
        print("-" * 70)
        results = search.search("学习", limit=3)
        display_results(results)
        
        # Test 5: Search for "API"
        print("\n[Query 5] 'API'")
        print("-" * 70)
        results = search.search("API", limit=3)
        display_results(results)
        
        # Test 6: Mixed query
        print("\n[Query 6] 'Python API'")
        print("-" * 70)
        results = search.search("Python API", limit=5)
        display_results(results)
        
        print("\n" + "=" * 70)
        print("FTS5 QUERY BUILDING EXAMPLES")
        print("=" * 70)
        
        # Show how queries are transformed
        test_queries = [
            "Python decorator",
            "学习 FastAPI",
            "async/await programming",
            "中文测试 English test",
            "API design patterns"
        ]
        
        for query in test_queries:
            fts_query = search._build_fts_query(query)
            print(f"\nInput:  '{query}'")
            print(f"FTS5:   {fts_query}")
        
        search.close()
        
        print("\n" + "=" * 70)
        print("ANALYSIS & CONCLUSIONS")
        print("=" * 70)
        print("""
1. FTS5 Query Building:
   - Extracts only alphanumeric tokens (A-Z, a-z, 0-9, _)
   - Chinese characters are NOT extracted as tokens
   - Each token is quoted and joined with AND
   
2. Chinese Text Support:
   - Chinese characters are indexed in FTS5
   - BUT: FTS5 default tokenizer doesn't do Chinese word segmentation
   - Search for "学习" will only find exact character matches
   - No automatic word breaking (学习 vs 学 + 习)
   
3. Comparison with OpenClaw:
   - Same query building logic (alphanumeric extraction)
   - Same limitation: no Chinese word segmentation
   - Same BM25 scoring algorithm
   
4. Search Results Include:
   - id: Unique chunk identifier
   - path: Full path to markdown file
   - source: 'memory' or 'session'
   - start_line/end_line: Line numbers in original file
   - score: BM25 relevance score (0-1, higher is better)
   - snippet: Text preview (default 300 chars)
   
5. Recommendations for Chinese Support:
   - Use a Chinese tokenizer (e.g., jieba)
   - Create custom FTS5 tokenizer
   - Or use vector search with multilingual embeddings
        """)


def display_results(results):
    """Display search results in a readable format."""
    if not results:
        print("  No results found.")
        return
    
    print(f"  Found {len(results)} result(s):\n")
    
    for i, result in enumerate(results, 1):
        print(f"  Result #{i}:")
        print(f"    File: {Path(result.path).name}")
        print(f"    Lines: {result.start_line}-{result.end_line}")
        print(f"    Score: {result.score:.4f}")
        print(f"    Source: {result.source}")
        print(f"    Snippet (first 150 chars):")
        snippet_preview = result.snippet[:150].replace('\n', ' ')
        print(f"      {snippet_preview}...")
        print()


if __name__ == "__main__":
    demo_search_results()
