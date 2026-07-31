"""
Memory Tools for Agent

Provides search and retrieval tools for accessing historical conversation memory.
Compatible with OpenClaw's memory search approach.
"""

import asyncio
import logging
import time
import warnings
from pathlib import Path
from typing import Literal, Optional

from agents import function_tool, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.global_cache import get_global_cache, LAST_MEMORY_NAME
from siada.services.memory import MemorySearch, SearchResult, DEFAULT_CHUNK_SIZE

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="pkg_resources is deprecated", category=UserWarning)
    warnings.filterwarnings("ignore", category=SyntaxWarning, module="jieba")
    import jieba


logger = logging.getLogger(__name__)


# ---- System Prompt Guidance ----------------------------
#
# Inserted into the agent's system prompt by
# ``siada.services.memory.combined_memory.build_combined_memory`` whenever
# inline memory is configured. Mirrors hermes' SESSION_SEARCH_GUIDANCE:
# a single nudge so the agent recalls past sessions instead of asking the
# user to repeat themselves. Kept passive — does not push the agent to
# call ``search_memory`` on every turn.

SESSION_SEARCH_GUIDANCE = (
    "====\n"
    "Session Search\n"
    "\n"
    "When the user references something from a past conversation or you\n"
    "suspect relevant cross-session context exists, use `search_memory`\n"
    "to recall it before asking them to repeat themselves.\n"
    "===="
)


# ---- Tool Documentation --------------------------------

SEARCH_MEMORY_DOCS = """Search through past session history for relevant information.

Mandatory recall step: search memory before answering questions about prior work,
decisions, dates, preferences, bugs, or anything that might have been discussed before.

Args:
    query (str): Search query (English or Chinese). Leave empty to list recent sessions.
    detail_level (str, optional): Summary detail level. One of "brief", "medium", "detailed".
                                  Defaults to "medium".

Returns:
    str: LLM-summarized session history focused on the query topic.

Examples:
    search_memory("API design decisions")
    search_memory("上次讨论的数据库方案")
    search_memory("")  # list recent sessions
    search_memory("docker issue", detail_level="detailed")
"""


GET_MEMORY_DOCS = """Read specific content from a memory file.

Use this tool after search_memory to get more detailed context from
relevant memory files. Reads the entire file or a specific line range.

Args:
    path (str): Relative path to the memory file (e.g., "session/2024-01-15-14-30-api-design.md" or "personal_style.md")
    start_line (int, optional): Starting line number (1-indexed)
    line_count (int, optional): Number of lines to read from start_line

Returns:
    str: The requested file content, or an error message if file not found.

Examples:
    get_memory("session/2024-01-15-14-30-api-design.md")
    get_memory("personal_style.md")
    get_memory("session/2024-01-15-14-30-api-design.md", start_line=10, line_count=20)
"""


# ---- Implementation Functions --------------------------------

def search_memory_impl(
    query: str,
    max_results: int = 5,
    min_score: float = 0.0
) -> str:
    """
    Internal implementation of memory search.
    
    This function performs the actual search logic and is intended to be tested directly.
    The public search_memory function wraps this with the function_tool decorator.
    
    Args:
        query: Search query string (supports both English and Chinese)
        max_results: Maximum number of results to return (default: 5)
        min_score: Minimum relevance score threshold (default: 0.0)
    
    Returns:
        Formatted search results as string
    """
    memory_search = None
    try:
        # Validate inputs
        if not query or not query.strip():
            return "Error: Search query cannot be empty"
        
        if max_results <= 0:
            return "Error: max_results must be greater than 0"
        
        # Initialize memory search
        memory_search = MemorySearch()
        
        if not memory_search.fts_available:
            return "Memory search is not available. The memory database may not be initialized yet."
        
        # Perform search
        results = memory_search.search(
            query=query.strip(),
            limit=max_results,
            snippet_max_chars=DEFAULT_CHUNK_SIZE
        )
        
        # Filter by minimum score
        if min_score > 0:
            results = [r for r in results if r.score >= min_score]
        
        # Format results
        if not results:
            return f"No results found for query: {query}"
        
        formatted_output = []
        formatted_output.append(f"Found {len(results)} result(s) for query: {query}\n")
        
        for i, result in enumerate(results, 1):
            formatted_output.append(f"--- Result {i} ---")
            formatted_output.append(f"File: {result.path}")
            formatted_output.append(f"Lines: {result.start_line}-{result.end_line}")
            formatted_output.append(f"Score: {result.score:.3f}")
            formatted_output.append(f"Source: {result.source}")
            formatted_output.append(f"\nSnippet:")
            formatted_output.append(result.snippet)
            formatted_output.append("")  # Empty line between results
        
        return "\n".join(formatted_output)
        
    except Exception as e:
        error_msg = f"Error searching memory: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg
    finally:
        # Clean up connection
        if memory_search is not None:
            try:
                memory_search.close()
            except Exception:
                pass


def read_memory_content(
    path: str,
    start_line: Optional[int] = None,
    line_count: Optional[int] = None
) -> str:
    """
    Read memory file content without header.
    
    This is a helper function that returns only the file content without any header information.
    Used internally by get_memory_impl to separate content reading from formatting.
    
    Args:
        path: Relative path to the memory file
        start_line: Starting line number (1-indexed, optional)
        line_count: Number of lines to read from start_line (optional)
    
    Returns:
        File content as string (without header)
    """
    # Validate path
    if not path or not path.strip():
        return "Error: File path cannot be empty"
    
    # Construct full path
    memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
    file_path = memory_dir / path.strip()
    
    # Security check: ensure path is within memory directory
    try:
        file_path = file_path.resolve()
        memory_dir = memory_dir.resolve()
        if not str(file_path).startswith(str(memory_dir)):
            return f"Error: Access denied. Path must be within memory directory: {path}"
    except Exception:
        return f"Error: Invalid file path: {path}"
    
    # Check if file exists
    if not file_path.exists():
        return f"Error: File not found: {path}"
    
    if not file_path.is_file():
        return f"Error: Path is not a file: {path}"
    
    # Read file content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        return f"Error: File is not a valid text file: {path}"
    
    # Handle line range selection
    if start_line is not None:
        if start_line < 1:
            return "Error: start_line must be >= 1"
        
        # Convert to 0-indexed
        start_idx = start_line - 1
        
        if start_idx >= len(lines):
            return f"Error: start_line {start_line} exceeds file length ({len(lines)} lines)"
        
        if line_count is not None:
            if line_count < 1:
                return "Error: line_count must be >= 1"
            end_idx = start_idx + line_count
            selected_lines = lines[start_idx:end_idx]
        else:
            # Read from start_line to end
            selected_lines = lines[start_idx:]
        
        return "".join(selected_lines)
    else:
        # Read entire file
        return "".join(lines)


def get_memory_impl(
    path: str,
    start_line: Optional[int] = None,
    line_count: Optional[int] = None
) -> str:
    """
    Internal implementation of memory file reading.
    
    This function performs the actual file reading logic and is intended to be tested directly.
    The public get_memory function wraps this with the function_tool decorator.
    
    Args:
        path: Relative path to the memory file
        start_line: Starting line number (1-indexed, optional)
        line_count: Number of lines to read from start_line (optional)
    
    Returns:
        File content with header as string
    """
    try:
        # Get the content without header
        content = read_memory_content(path=path, start_line=start_line, line_count=line_count)
        
        # If content is an error message, return it directly
        if content.startswith("Error:"):
            return content
        
        # Construct full path to get line count for header
        memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
        file_path = memory_dir / path.strip()
        
        with open(file_path, 'r', encoding='utf-8') as f:
            total_lines = len(f.readlines())
        
        # Generate appropriate header
        if start_line is not None:
            actual_lines = len(content.splitlines())
            if not content.endswith('\n') and actual_lines > 0:
                # Adjust if last line doesn't have newline
                actual_lines = len(content.split('\n'))
            header = f"File: {path} (lines {start_line}-{start_line + actual_lines - 1} of {total_lines})\n\n"
        else:
            header = f"File: {path} ({total_lines} lines)\n\n"
        
        return header + content
        
    except Exception as e:
        error_msg = f"Error reading memory file: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# ---- Public Tool Functions --------------------------------

@function_tool(
    name_override="get_memory", description_override=GET_MEMORY_DOCS
)
def get_memory(
    context: RunContextWrapper[CodeAgentContext],
    path: str,
    start_line: Optional[int] = None,
    line_count: Optional[int] = None
) -> str:

    return get_memory_impl(path=path, start_line=start_line, line_count=line_count)


# ---- Session Search: private helpers --------------------------------

SUMMARIZE_SYSTEM_PROMPT = """You are reviewing a past conversation transcript to help recall what happened.
Summarize the conversation with a focus on the search topic. Include:
1. What the user asked about or wanted to accomplish
2. What actions were taken and what the outcomes were
3. Key decisions, solutions found, or conclusions reached
4. Any specific commands, files, URLs, or technical details that were important
5. Anything left unresolved or notable
Be thorough but concise. Preserve specific details. Write in past tense."""


def _extract_date_from_path(path: str) -> str:
    """'session/2025-03-15-14-30-foo.md' → '2025-03-15'"""
    parts = Path(path).stem.split("-")
    if len(parts) >= 3:
        return f"{parts[0]}-{parts[1]}-{parts[2]}"
    return Path(path).stem


def _group_session_hits(hits, current_session_path=None):
    """去重并保留 FTS ORDER BY rank 的原始顺序，排除当前 session，最多 5 个。"""
    seen = set()
    ordered = []
    for hit in hits:
        if hit.path == current_session_path:
            continue
        if hit.path not in seen:
            seen.add(hit.path)
            ordered.append(hit.path)
    return ordered[:5]


def _truncate_around_matches(content: str, query: str, max_chars: int = 80_000) -> str:
    """截断到 max_chars，优先保留 query 关键词命中密集区域。用 jieba 分词支持中文。"""
    if len(content) <= max_chars:
        return content

    tokens = [t.strip() for t in jieba.cut_for_search(query) if len(t.strip()) >= 2]

    if not tokens:
        return content[:max_chars]

    # 收集所有命中位置
    positions = []
    for token in tokens:
        start = 0
        while True:
            idx = content.find(token, start)
            if idx == -1:
                break
            positions.append(idx)
            start = idx + 1

    if not positions:
        return content[:max_chars]

    positions.sort()

    # 滑动窗口找命中最密集的区域
    best_start = 0
    best_count = 0
    left = 0
    for right in range(len(positions)):
        while positions[right] - positions[left] >= max_chars:
            left += 1
        count = right - left + 1
        if count > best_count:
            best_count = count
            # bias 前 25%：让窗口稍早开始，保留更多后续上下文
            bias = max_chars // 4
            best_start = max(0, positions[left] - bias)

    truncated = content[best_start: best_start + max_chars]
    if best_start > 0:
        truncated = "...[earlier content truncated]...\n" + truncated
    return truncated


async def _summarize_session(content: str, query: str, path: str, detail_level: str) -> str:
    """调用 fast_completion 对单个 session 生成摘要，失败时降级为原文前 500 字。"""
    from siada.provider.fast_llm import fast_completion

    date_str = _extract_date_from_path(path)
    user_prompt = (
        f"Search topic: {query}\n"
        f"Session date: {date_str}\n\n"
        f"CONVERSATION TRANSCRIPT:\n{content}\n\n"
        f"Summarize this conversation with focus on: {query}"
    )
    max_tokens = 800 if detail_level == "brief" else 2000
    try:
        response = await fast_completion(
            "",
            agent_name="search_memory",
            messages=[
                {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        if response and hasattr(response, "choices") and response.choices:
            return response.choices[0].message.content.strip()
        raise ValueError("Empty response from LLM")
    except Exception as e:
        logger.warning(f"[search_memory] LLM summary failed for {path}: {e}")
        return content[:500] + "\n\n[LLM summary unavailable]"


async def _summarize_sessions_parallel(
    tasks: list,
    query: str,
    detail_level: str,
    max_concurrency: int = 3,
) -> list:
    """并行摘要多个 session，返回 List[(path, summary_text)]"""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _bounded(path: str, content: str):
        async with semaphore:
            summary = await _summarize_session(content, query, path, detail_level)
            return path, summary

    results = await asyncio.gather(
        *[_bounded(p, c) for p, c in tasks],
        return_exceptions=True,
    )
    return [(p, s) for p, s in results if not isinstance(p, BaseException)]


def _get_recent_sessions(limit: int = 10) -> str:
    """列出 session/ 目录最近 N 个文件，返回格式化字符串（零 LLM 调用）。"""
    session_dir = Path.home() / ".siada-cli" / "workspace" / "memory" / "session"
    if not session_dir.exists():
        return "No session history found."

    files = sorted(session_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return "No session history found."

    lines = ["# Recent Sessions\n"]
    for i, f in enumerate(files[:limit], 1):
        date_str = _extract_date_from_path(f"session/{f.name}")
        try:
            preview = f.read_text(encoding="utf-8")[:300].replace("\n", " ").strip()
        except Exception:
            preview = "(unreadable)"
        lines.append(f"{i}. **{date_str}** session/{f.name}")
        lines.append(f"   预览：{preview}\n")

    return "\n".join(lines)


async def _search_memory_impl_v2(context, query: str, detail_level: str) -> str:
    """新版 search_memory 主实现：FTS → session 分组 → 并行 LLM 摘要。"""
    start = time.time()
    logger.info(f"[SearchMemory] START query={query!r} detail_level={detail_level}")

    # recent 模式：query 为空时列出最近 session
    if not query or not query.strip():
        result = _get_recent_sessions()
        logger.debug(f"[SearchMemory] DONE (recent mode) elapsed={time.time()-start:.1f}s")
        return result

    # 获取当前 session 相对路径，用于排除自身
    memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
    abs_path = get_global_cache(LAST_MEMORY_NAME)
    current_session_rel = None
    if abs_path:
        try:
            current_session_rel = str(Path(abs_path).relative_to(memory_dir))
        except ValueError:
            pass

    # FTS 检索
    memory_search = None
    try:
        memory_search = MemorySearch()
        if not memory_search.fts_available:
            return "Memory search is not available. The memory database may not be initialized yet."
        results = memory_search.search(query=query.strip(), limit=20)
    finally:
        if memory_search is not None:
            memory_search.close()

    if not results:
        return f"No results found for query: {query}"

    # session 分组，保留 FTS 相关度顺序
    session_paths = _group_session_hits(results, current_session_path=current_session_rel)
    if not session_paths:
        return f"No results found for query: {query}"

    # 加载文件内容并截断
    tasks = []
    for rel_path in session_paths:
        full_path = memory_dir / rel_path
        try:
            content = full_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"[search_memory] Failed to read {rel_path}: {e}")
            continue
        truncated = _truncate_around_matches(content, query)
        tasks.append((rel_path, truncated))

    if not tasks:
        return f"No results found for query: {query}"

    # 并行 LLM 摘要
    summaries = await _summarize_sessions_parallel(tasks, query, detail_level)

    # 格式化输出
    lines = [f"# Memory Search Results\n", f"**Query:** {query}\n", "## Session History\n"]
    for path, summary in summaries:
        date_str = _extract_date_from_path(path)
        lines.append(f"### Session: {date_str} ({path})")
        lines.append(summary)
        lines.append("")

    elapsed = time.time() - start
    logger.debug(f"[SearchMemory] DONE elapsed={elapsed:.1f}s sessions={len(summaries)}")
    return "\n".join(lines)


@function_tool(
    name_override="search_memory", description_override=SEARCH_MEMORY_DOCS
)
async def search_memory(
    context: RunContextWrapper[CodeAgentContext],
    query: str,
    detail_level: Literal["brief", "medium", "detailed"] = "medium",
) -> str:
    return await _search_memory_impl_v2(context, query, detail_level)
