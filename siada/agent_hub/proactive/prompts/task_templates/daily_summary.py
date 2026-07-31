"""
Daily Summary Instruction Template

This instruction is sent by the scheduler to ask ProactiveAgent
to generate a summary of the most recent work day's activities.
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from siada.foundation.constants import SIADA_HOME


def _find_last_work_date(events_dir: Path, today: date) -> date:
    """Return the most recent date before today that has event files."""
    if events_dir.exists():
        dates: set[date] = set()
        for f in events_dir.iterdir():
            if not f.is_file():
                continue
            parts = f.name.split("-")
            if len(parts) >= 3:
                try:
                    d = date(int(parts[0]), int(parts[1]), int(parts[2]))
                    if d < today:
                        dates.add(d)
                except ValueError:
                    pass
        if dates:
            return max(dates)
    return today - timedelta(days=1)


def _get_preferred_language() -> str:
    """Read preferred_language from conf.yaml, default to 'en'."""
    try:
        from siada.config.config_loader import load_conf
        conf = load_conf()
        return conf.preferred_language or "en"
    except Exception:
        return "en"


# Base directory for all memory-related files (events, sessions, summaries)
_MEMORY_DIR = SIADA_HOME / "workspace" / "memory"


def get_last_work_date_str() -> str:
    """Return the last work date as a string (YYYY-MM-DD).

    This is the single source of truth for determining which date the daily
    summary should cover.  Uses local time so that the generation phase and
    the IM-send phase always agree on the same date, even when they straddle
    the UTC midnight boundary.
    """
    today = datetime.now().date()
    work_date = _find_last_work_date(_MEMORY_DIR / "events", today)
    return work_date.strftime("%Y-%m-%d")


def get_daily_summary_file_path(work_date_str: Optional[str] = None) -> Path:
    """Return the expected path of the daily summary file.

    Args:
        work_date_str: Date string in YYYY-MM-DD format.  When *None*,
            :func:`get_last_work_date_str` is called to determine the date.
    """
    if work_date_str is None:
        work_date_str = get_last_work_date_str()
    return _MEMORY_DIR / "summary" / f"{work_date_str}_summary.md"


def get_daily_summary_instruction(
    preferred_language: Optional[str] = None,
    work_date_str: Optional[str] = None,
) -> str:
    events_dir = _MEMORY_DIR / "events"
    session_dir = _MEMORY_DIR / "session"

    if work_date_str is None:
        work_date_str = get_last_work_date_str()
    summary_file = get_daily_summary_file_path(work_date_str)

    lang = preferred_language or _get_preferred_language()
    if lang.startswith("zh"):
        return _instruction_zh(work_date_str, events_dir, session_dir, summary_file)
    return _instruction_en(work_date_str, events_dir, session_dir, summary_file)


# ---------------------------------------------------------------------------
# English version
# ---------------------------------------------------------------------------

def _instruction_en(work_date_str: str, events_dir: Path, session_dir: Path, summary_file: Path) -> str:
    return f"""# Task: Generate Daily Work Summary

Work date: {work_date_str}

## Data Sources

1. **Events** (primary): `{events_dir}` — files prefixed `{work_date_str}`. Already distilled with structured fields.
2. **Sessions** (fallback): `{session_dir}` — only for sessions WITHOUT a corresponding event. Process one by one.

## Steps

1. List & sort event files for `{work_date_str}` chronologically.
2. Read each event incrementally. For each event, extract:
   - `## Repository Info` → `Repository name` (the top-level grouping key)
   - The event slug (from filename) → the topic name
   - Key outcome, decisions, blockers, and predicted next tasks
3. List session files for `{work_date_str}`; skip those with a matching event.
4. Read remaining sessions incrementally; extract key facts and repo info.
5. Group all entries by repository name, then write the summary and save to `{summary_file}`.

## Output Format

```markdown
# Daily Summary - {work_date_str}

## Overview
[≤ 3 sentences: how many projects, how many items, the most important 1-3 things today]

## [Repository A]  (N items)

### Progress
- **[topic from slug]**: [≤ 1 sentence outcome]. [optional status note].
- **[topic from slug]**: ...

### Decisions
- [key technical decision made today]

### Blockers / Risks
- [blockers or risks observed]

### Next Steps
- P0: [highest priority follow-up]
- P1: [medium priority]
- P2: [lower priority]

### Sources
- HH-MM-slug
- HH-MM-slug

## [Repository B]  (M items)
...

## Tools / Environment (optional — only for entries without a real repo)
- [lightweight entry, e.g., installed a CLI tool]

## Statistics
N projects · M sessions · K items
```

## Rules

### Grouping
- Top-level grouping = `Repository name` from each event's `## Repository Info` section.
- Each repository becomes one H2 section: `## [repo name]  (N items)`.
- If a repo name is missing or unclear, group as "Uncategorized".
- Trivial entries without a real repository (e.g., installing a tool) go into "## Tools / Environment".

### Per-Repository Structure
- Within each repository H2, use up to 5 H3 sub-sections in this order:
  `### Progress` / `### Decisions` / `### Blockers / Risks` / `### Next Steps` / `### Sources`
- Omit any sub-section that has no content (except Progress and Sources which must always exist).
- NEVER create cross-project sections like "Cross-Project Decisions". Decisions/blockers belong
  to the project that drove them.

### One Event = One Bullet
- Each event file = exactly ONE bullet under its repo's `### Progress`. Format:
  `- **<topic from slug>**: <≤ 1 sentence outcome>. <optional status note>.`
- Within the same repo, merge 2+ events sharing an obvious topic into ONE bullet.
- NEVER enumerate file paths, function names, or symbol names that already live inside event files.
  The summary is a reading guide, not a changelog.

### Sources Section
- DO NOT put source citations after each bullet in Progress/Decisions/Blockers.
- All sources for a repo are aggregated in that repo's `### Sources` sub-section, listed as:
  `- HH-MM-<slug>` (one per line, time-ascending, strip the `YYYY-MM-DD-` prefix).

### Length Budget
- Total ≤ 600 words. Per repo ≤ 5 Progress bullets (merge if more).

### Other
- Prefer events over sessions; use `predicted next tasks` as authoritative next-step source.
- Process files sequentially (oldest first).
- Save to: `{summary_file}`
"""


# ---------------------------------------------------------------------------
# Chinese version
# ---------------------------------------------------------------------------

def _instruction_zh(work_date_str: str, events_dir: Path, session_dir: Path, summary_file: Path) -> str:
    return f"""# 任务：生成每日工作总结

工作日期：{work_date_str}

## 数据来源

1. **事件**（主要）：`{events_dir}` — 以 `{work_date_str}` 为前缀的文件，已包含结构化字段。
2. **会话**（备选）：`{session_dir}` — 仅处理没有对应事件的会话，逐个读取。

## 执行步骤

1. 按时间顺序列出 `{work_date_str}` 的事件文件。
2. 逐个读取事件，提取以下信息：
   - `## Repository Info` → `Repository name`（顶层分组依据）
   - 文件名中的 slug → 该事件的主题名
   - 关键产出、决策、阻塞、预测的后续任务
3. 列出 `{work_date_str}` 的会话文件；跳过已有对应事件的。
4. 逐个读取剩余会话，提取关键事实和所属项目信息。
5. 按项目（Repository name）分组汇总，写入摘要并保存到 `{summary_file}`。

## 输出格式

```markdown
# 每日总结 - {work_date_str}

## 概览
[≤ 3 句话：今天涉及多少个项目、多少个事项、最重要的 1-3 件事]

## [项目 A]  (N 事项)

### 进展
- **[来自 slug 的主题]**：[≤ 1 句话结果]。[可选状态说明]。
- **[来自 slug 的主题]**：...

### 决策
- [今天做出的关键技术决策]

### 阻塞 / 风险
- [遇到的阻塞或风险]

### 后续优先级
- P0: [最高优先级的后续行动]
- P1: [中等优先级]
- P2: [较低优先级]

### 来源
- HH-MM-slug
- HH-MM-slug

## [项目 B]  (M 事项)
...

## 工具/环境（可选 — 仅放无所属项目的轻量条目）
- [轻量条目，例如安装了某个 CLI 工具]

## 数据
N 个项目 · M 个会话 · K 个事项
```

## 规则

### 分组
- 顶层分组依据 = 每个事件中 `## Repository Info` 段的 `Repository name`。
- 每个项目占一个 H2 章节：`## [项目名]  (N 事项)`。
- 如果项目名缺失或不清楚，归入"未分类"。
- 与代码项目无关的轻量条目（例如安装某个工具）归入底部 `## 工具/环境`。

### 每个项目的内部结构
- 每个项目 H2 下，最多使用 5 个 H3 子段，按此顺序：
  `### 进展` / `### 决策` / `### 阻塞 / 风险` / `### 后续优先级` / `### 来源`
- 无内容的子段直接省略（但"进展"和"来源"必须始终存在）。
- **禁止**创建"跨项目决策""跨项目阻塞"等跨项目章节。决策/阻塞归属于驱动它的项目。

### 一个事件 = 一条要点
- 每个事件文件 = 所属项目 `### 进展` 下的一条 bullet。格式：
  `- **<来自 slug 的主题>**：<≤ 1 句话结果>。<可选状态说明>。`
- 同项目内，2 个以上共享同一明显主题的事件合并为一条。
- **禁止**罗列文件路径、函数名、符号名等已在事件文件中存在的细节。
  日报是阅读指南，不是 changelog。

### 来源章节
- **禁止**在"进展 / 决策 / 阻塞"的每条 bullet 后附加来源标注。
- 每个项目的所有来源集中在该项目的 `### 来源` 子段中，格式为：
  `- HH-MM-<slug>`（每行一条，按时间升序，去掉 `YYYY-MM-DD-` 前缀）。

### 篇幅预算
- 总长 ≤ 600 字。每个项目 ≤ 5 条"进展"bullet（超过则合并）。

### 其他
- 优先使用事件；以事件中的 `predicted next tasks` 作为后续任务权威来源。
- 按时间顺序逐个处理文件。
- 保存位置：`{summary_file}`
"""
