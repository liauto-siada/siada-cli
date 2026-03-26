"""
Integration test for analyze_and_update_memory.

Uses the real model (no mocking). Verifies that the full 4-task memory
pipeline completes and writes an event file to disk.
"""

import asyncio
import pytest
from pathlib import Path

from siada.foundation.context import set_context_var, LLM_CONFIG
from siada.models.model_run_config import ModelRunConfig
from siada.services.memory.memory_agent import analyze_and_update_memory


pytestmark = pytest.mark.integration


# A realistic session: discussion about refining memory agent task instructions
SESSION_CONTENT = """\
user: 我想给 memory_agent.py 增加一个新的 task instruction，用于提取用户的工作习惯

assistant: 好的。我先看看现有的 task_instructions 目录结构。

[edit_file view task_instructions/]
→ personal_style.py, experience.py, recent_task.py, structured_event.py, system_prompt.py

现有的 personal_style.py 已经涵盖了工作习惯的提取，包含 Work Habits、Technical Preferences 等章节。
如果要新增独立的 task instruction，建议聚焦在"沟通模式"上，因为 personal_style 篇幅有限。

user: 不用了，personal_style 里已经有 Communication Patterns 章节了。
我想问能否把 experience 的内容拆分成多个主题文件分别存储？

assistant: 可以的。拆分思路：让 agent 自行决定 category name，每个主题一个文件。
目前 INSTRUCTION 已经说明 agent 会自己决定 category name，但描述不够明确。
建议在 INSTRUCTION 里增加规则：每个主题创建独立文件 <category>.md，跨 session 合并到已有文件。

已修改 experience.py，新增以下规则：
- 每个主题创建独立文件 <category>.md
- 跨 session 合并到已有文件，而不是每次新建

user: 好的，这个方向正确。structured_event 是不是必须写文件？

assistant: 是的，structured_event task 会调用 edit_file create 把 event 写到 events/ 目录下。
这是整个 pipeline 的第一步，后续 experience、personal_style、recent_task 都从这个 event 中提取信息。
修改后的 experience.py 已通过 str_replace 更新，路径为：
siada/services/memory/task_instructions/experience.py

user: 明白了，谢谢。
"""


@pytest.mark.asyncio
@pytest.mark.slow  # LLM calls can take several minutes
async def test_analyze_and_update_memory_writes_event_file():
    """
    Full pipeline runs end-to-end with the real model and writes an event file to disk.
    """
    events_dir = Path.home() / ".siada-cli" / "workspace" / "memory" / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    before = set(events_dir.glob("*.md"))

    llm_config = ModelRunConfig.get_default_config()
    set_context_var(LLM_CONFIG, llm_config)

    result = await analyze_and_update_memory(SESSION_CONTENT)

    assert result["success"] is True
    assert result["completed_tasks"] == [
        "structured_event", "experience", "personal_style", "recent_task"
    ]

    after = set(events_dir.glob("*.md"))
    new_files = after - before
    assert len(new_files) >= 1, "Expected at least one new event file written to events/"

    event_content = next(iter(new_files)).read_text(encoding="utf-8")
    for section in ["Background", "Implementation Summary", "Artifacts", "Predicted Next Tasks"]:
        assert section in event_content, f"Event file is missing required section: {section}"


# ---- Edge Case Tests ----


# Minimal session: very short, single-turn conversation
MINIMAL_SESSION = """\
user: 你好

assistant: 你好！有什么可以帮助你的吗？

user: 没事了
"""


# Session with no actionable content
NO_CONTENT_SESSION = """\
user: 今天天气不错

assistant: 是的，很适合出门散步。

user: 嗯，我去吃饭了

assistant: 好的，慢慢享用！
"""


# Session with only trivial task content (no structured design/implementation)
TRIVIAL_TASK_SESSION = """\
user: 帮我查一下当前时间

assistant: 当前时间是 2026-03-11 18:00。

user: 谢谢
"""


@pytest.mark.asyncio
@pytest.mark.slow
async def test_analyze_and_update_memory_minimal_session():
    """
    Very short session: verify pipeline completes without failure.
    
    Expected: structured_event may be minimal, but all 4 tasks still run.
    """
    llm_config = ModelRunConfig.get_default_config()
    set_context_var(LLM_CONFIG, llm_config)

    result = await analyze_and_update_memory(MINIMAL_SESSION)

    assert result["success"] is True
    assert result["completed_tasks"] == [
        "structured_event", "experience", "personal_style"
    ]


@pytest.mark.asyncio
@pytest.mark.slow
async def test_analyze_and_update_memory_no_actionable_content():
    """
    Session with no technical content: verify graceful handling.
    
    Expected: structured_event may produce a minimal event, experience/personal_style/recent_task
    may have nothing to extract, but the pipeline should not crash.
    """
    llm_config = ModelRunConfig.get_default_config()
    set_context_var(LLM_CONFIG, llm_config)

    result = await analyze_and_update_memory(NO_CONTENT_SESSION)

    assert result["success"] is True
    # All tasks should attempt to run, even if they produce minimal/empty output
    assert result["completed_tasks"] == [
        "structured_event", "experience"
    ]


@pytest.mark.asyncio
@pytest.mark.slow
async def test_analyze_and_update_memory_trivial_task():
    """
    Session with trivial task (no design/implementation): verify no exception.
    
    Expected: structured_event may note the trivial query; experience/personal_style
    likely have nothing to extract; recent_task may record it or skip it.
    """
    llm_config = ModelRunConfig.get_default_config()
    set_context_var(LLM_CONFIG, llm_config)

    result = await analyze_and_update_memory(TRIVIAL_TASK_SESSION)

    assert result["success"] is True
    assert result["completed_tasks"] == [
        "structured_event", "experience"
    ]


# ---------------------------------------------------------------------------
# Production smoke test – no fixture session content, uses real latest file
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.slow
class TestAnalyzeAndUpdateMemoryProduction:
    """
    Smoke test: reads the most recently modified session file from the real
    production directory and runs analyze_and_update_memory on it directly.

    No files are created or deleted. Useful for observing the full pipeline
    against real session content.

    Run:
        python -m pytest tests/services/memory/test_memory_agent.py::TestAnalyzeAndUpdateMemoryProduction -v -s
    """

    def test_run_on_latest_production_session(self):
        session_dir = Path.home() / ".siada-cli" / "workspace" / "memory" / "session"
        assert session_dir.exists(), f"Session directory not found: {session_dir}"

        sessions = sorted(
            (f for f in session_dir.iterdir() if f.is_file() and f.name.endswith(".md") and not f.name.startswith(".")),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        assert sessions, f"No session files found in {session_dir}"

        latest = sessions[0]
        content = latest.read_text(encoding="utf-8")

        llm_config = ModelRunConfig.get_default_config()
        set_context_var(LLM_CONFIG, llm_config)

        result = asyncio.run(analyze_and_update_memory(session_content=content))

        assert result["success"] is True
