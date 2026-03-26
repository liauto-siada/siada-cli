# Siada 主动性能力设计文档

## 目录

- [1. 概述](#1-概述)
- [2. 架构设计](#2-架构设计)
  - [2.1 整体架构](#21-整体架构)
  - [2.2 进程模型](#22-进程模型)
  - [2.3 通信机制](#23-通信机制)
- [3. 核心模块](#3-核心模块)
  - [3.1 ProactiveScheduler](#31-proactivescheduler)
  - [3.2 ProactiveAgent](#32-proactiveagent)
  - [3.3 SiadaDaemon](#33-siadadaemon)
  - [3.4 DaemonManager](#34-daemonmanager)
  - [3.5 TaskStorage](#35-taskstorage)
  - [3.6 CronTaskStorage](#36-crontaskstorage)
- [4. 文件结构](#4-文件结构)
- [5. 用户交互](#5-用户交互)
- [6. 配置](#6-配置)
- [7. Prompt 设计要点](#7-prompt-设计要点)
- [8. 待完成工作](#8-待完成工作)

---

## 1. 概述

为 Siada 增加主动发现工作任务的能力：基于记忆系统分析用户历史工作，在合适时间点主动发现和推荐待办任务，后台常驻运行，不影响前台使用。

**核心特性**：
- **智能发现**：基于记忆系统的上下文分析
- **时间驱动**：工作时段周期触发 + 每日总结与计划通知
- **后台常驻**：daemon 模式，与前端解耦

---

## 2. 架构设计

### 2.1 整体架构

```
┌────────────────────────────────────────┐
│       CLI Frontend 进程                 │
│  • 现有 agent 交互逻辑（保持不变）      │
│  • 启动时检查/启动 daemon               │
│  • 读取共享存储显示任务                 │
└──────────┬──────────────────▲──────────┘
           │启动/停止         │读取任务
           │                  │
           ▼                  │
┌────────────────────────────────────────┐
│       Daemon 进程（后台常驻）           │
│  ┌──────────────────────────────┐     │
│  │ Proactive Scheduler           │     │
│  │  • APScheduler 定时调度       │     │
│  │  • 工作/非工作时段判断         │     │
│  └──────────────────────────────┘     │
│  ┌──────────────────────────────┐     │
│  │ Proactive Agent               │     │
│  │  • 记忆系统分析                │     │
│  │  • 任务发现与优先级            │     │
│  └──────────────────────────────┘     │
│  ┌──────────────────────────────┐     │
│  │ Memory Service                │     │
│  │  • FTS5 搜索                  │     │
│  └──────────────────────────────┘     │
└──────────┬──────────────────────────────┘
           │写入任务
           ▼
┌────────────────────────────────────────┐
│       共享存储（文件系统）              │
│  ~/.siada-cli/workspace/task/          │
│      tasks_YYYY-MM-DD.json            │
└────────────────────────────────────────┘
```

### 2.2 进程模型

#### Daemon 进程
- **启动方式**：通过 `subprocess.Popen` 后台启动
- **生命周期**：
  - 由前端进程自动管理（首次启动时创建）
  - 通过 PID 文件跟踪（`~/.siada-cli/siada-daemon.pid`）
  - 通过信号停止（SIGTERM）
- **职责**：
  - 定时调度任务发现
  - 将结果写入共享存储
  - 独立日志：`~/.siada-cli/logs/daemon.log`
- **进程监控**：
  - 轻量级健康检查（检查 PID 是否存活）
  - 前端启动时检测并重启（如果需要）

#### CLI Frontend 进程
- **启动行为**：
  - 首次启动：检查 daemon，未运行则启动
  - 再次启动：检查 daemon，已运行则复用
  - 读取共享存储，显示待办任务
- **退出行为**：
  - Ctrl+C：仅关闭前端，daemon 继续运行
  - `siada-cli stop`：停止 daemon
- **职责**：
  - 保持现有 agent 交互逻辑
  - 管理 daemon 生命周期
  - 展示主动发现的任务

### 2.3 通信机制

**无需进程间通信**！通过共享文件系统实现数据交换：

#### 共享存储
- **文件位置**：`~/.siada-cli/workspace/task/tasks_YYYY-MM-DD.json`（按日期分文件）
- **访问模式**：
  - Daemon：ProactiveAgent 通过 `save_task_list` 工具写入（原子操作）
  - Frontend：启动和 `/tasks` 命令时读取当天文件
- **并发控制**：
  - 使用临时文件 + 重命名保证原子性
  - Frontend 读取失败时降级处理
- **格式**：JSON，包含任务列表（详见 3.5 节）

#### PID 文件
- **文件位置**：`~/.siada-cli/siada-daemon.pid`
- **内容**：进程 PID
- **用途**：
  - 检查 daemon 是否运行
  - 发送停止信号

---

## 3. 核心模块

### 3.1 ProactiveScheduler

**职责**：
- 管理定时任务注册和执行
- 区分工作/非工作时段
- 分三个独立层级调度任务
- 提供可扩展的任务注册机制

**三层调度架构**：

#### 第一层：工作时段周期任务（Part 1）
- 触发方式：每隔 `trigger_interval` 分钟触发一次，仅在工作时段内执行
- 任务序列（顺序执行，可通过 `add_periodic_job` 扩展）：
  1. **discover_tasks** — ProactiveAgent 从最近7天的记忆文件发现待办任务，写入**当天**任务文件
  2. **execute_pending_tasks** — CodeGenAgent 读取**当天**任务文件，执行不需要确认的 pending 任务
- 特性：系统固定任务，不可取消；工作时段外自动跳过

#### 第二层：每日固定任务（Part 2）
- 触发方式：每天 `daily_task_execution_time`（默认 08:30）触发一次 cron 作业
- 任务序列（顺序执行，可通过 `add_daily_job` 扩展）：
  1. **daily_summary** — ProactiveAgent 生成前一天的工作总结
  2. **discover_tasks** — 复用第一层的同一方法（代码无重复），写入**当天**任务文件
  3. **execute_pending_tasks** — CodeGenAgent 读取**前一天**的任务文件，执行不需要确认的 pending 任务
- 特性：系统固定任务，`cancellable=False`，不可取消

#### 第三层：Crontab 用户自定义任务（Part 3）
- 支持标准 Crontab 表达式（5 字段格式：`分 时 日 月 周`）
- 调度器启动时从 CronTaskStorage 加载所有启用的任务
- 每个 CronTask 注册为独立的 APScheduler 作业（使用 CronTrigger）
- 执行时调用 ProactiveAgent.run(instruction)，完成后更新 last_run / next_run
- 动态重载：通过信号文件 `~/.siada-cli/cron_tasks.reload` 触发，无需重启

**可扩展性**：
- `add_periodic_job(job: PeriodicJob)` — 运行时注册新的周期任务
- `add_daily_job(job: DailyJob)` — 运行时注册新的每日任务
- `PeriodicJob` / `DailyJob` 为注册表项类型，包含 `name` 和异步 `handler`

**关键配置**（来自 ProactiveConfig）：
- `work_hours`: 工作时段（默认 "09:00-18:00"）
- `trigger_interval`: 第一层触发间隔（默认 60 分钟）
- `daily_task_execution_time`: 第二层每日触发时间（默认 "08:30"）

**execute_pending_tasks 执行规则**：
- 仅执行 `status=pending` 且 `needs_confirmation=False` 的任务
- `needs_confirmation=True` 的任务暂时跳过（用户确认机制待设计）
- 第一层读取当天文件（`tasks_YYYY-MM-DD.json`，日期为今天）
- 第二层读取前一天文件（日期为昨天）

**APScheduler 作业 ID**：
- `work_hours_periodic` — 第一层周期触发器
- `daily_fixed` — 第二层每日触发器
- `cron_{task_id}` — 第三层各 CronTask 对应作业
- `check_reload_signal` — 信号文件轮询作业（每 30 秒）

**Crontab 任务模型（CronTask）**：
- `id`: 任务唯一标识（UUID）
- `name`: 任务名称
- `cron_expr`: Crontab 表达式（5字段格式）
- `instruction`: 传递给 ProactiveAgent 的任务指令
- `enabled`: 是否启用（默认 true）
- `created_at` / `updated_at`: 创建和更新时间
- `last_run` / `next_run`: 上次和下次执行时间（调度器维护）

### 3.2 ProactiveAgent

**职责**：
- 分析记忆系统历史会话
- 识别未完成任务和线索
- 生成任务建议和优先级

**架构**：
- 继承自 `SiadaAgent`，复用 `CodeAgentContext`（无需单独 ProactiveContext）
- 通过 `SiadaRunner.run_agent("proactive", instruction)` 执行，而非直接调用 `agent.run()`

**工具集**（6 个）：
1. `smart_search_memory` - 智能记忆搜索
2. `get_memory` - 读取记忆文件
3. `list_memory_files` - 列出时间范围内的文件
4. `search_memory_by_date` - 按日期范围搜索
5. `save_task_list` - 保存任务列表到共享存储
6. `manage_cron_task` - Crontab 任务管理（create/update/delete/list）

**System Prompt**：返回通用的 `PROACTIVE_SYSTEM_PROMPT`，定义角色和工作原则。不包含具体工具列表或能力范围限制。

**任务指令模板**（`prompts/task_templates/`）：
- `DISCOVER_TASKS_INSTRUCTION` - 任务发现
- `DAILY_SUMMARY_INSTRUCTION` - 日报总结
- `WORK_PLAN_INSTRUCTION` - 工作计划

调度系统将指令模板作为 user message 发送给 Agent，Agent 基于 system prompt + 任务指令 react 执行。

**Task 数据模型**（`models.py`）：
- `id` / `title` / `description`
- `priority`: high / medium / low
- `category`: feature / bug / refactor / doc
- `status`: pending / in_progress / completed / cancelled
- `needs_confirmation`: 是否需要人工确认
- `source_memories`: 来源记忆文件列表
- `confidence`: 置信度（0.0-1.0）
- `created_at` / `updated_at`

### 3.3 SiadaDaemon

**职责**：独立后台进程，负责启动并维持 ProactiveScheduler 运行，管理进程生命周期和日志。

**启动流程**：初始化日志 → 创建 PID 文件 → 设置信号处理（SIGTERM）→ 加载配置 → 初始化 Scheduler → 启动调度器 → 进入主循环

**停止流程**：接收 SIGTERM → 停止调度器 → 清理 PID 文件 → 优雅退出

**日志**：`~/.siada-cli/logs/daemon.log`（RotatingFileHandler，10MB，保留 5 个备份）

### 3.4 DaemonManager

**职责**：启动/停止 daemon 进程，健康检查，PID 文件管理。

**关键方法**：
- `start_daemon()` — 使用 `subprocess.Popen` 后台启动
- `stop_daemon()` — 发送 SIGTERM 信号
- `is_running()` — 检查 PID 是否存活
- `ensure_daemon()` — 幂等启动（已运行则跳过）

### 3.5 TaskStorage

**职责**：按日期分文件原子写入任务数据，线程安全读取。

**文件位置**：`~/.siada-cli/workspace/task/tasks_YYYY-MM-DD.json`

调度器读取时通过日期参数选择目标文件：第一层（周期任务）读当天文件，第二层（每日固定）读前一天文件。

**文件格式**：
```json
{
  "tasks": [
    {
      "id": "task-uuid",
      "title": "任务标题",
      "description": "详细描述",
      "priority": "high|medium|low",
      "category": "feature|bug|refactor|doc|test|other",
      "status": "pending|in_progress|completed|cancelled",
      "needs_confirmation": true,
      "confidence": 0.9,
      "source_memories": ["summary/2024-03-02_summary.md"],
      "suggested_actions": ["步骤1", "步骤2"],
      "created_at": "2024-03-03T14:00:00Z",
      "updated_at": "2024-03-03T14:00:00Z"
    }
  ]
}
```

### 3.6 CronTaskStorage

**职责**：持久化存储 Crontab 任务配置，提供 CRUD 接口，原子写入和线程安全读取。

**文件位置**：`~/.siada-cli/workspace/cron_tasks.json`

**文件格式**：
```json
{
  "version": "1.0",
  "last_updated": "2024-03-03T14:00:00Z",
  "tasks": [
    {
      "id": "cron-task-uuid",
      "name": "工作日早报",
      "cron_expr": "0 9 * * 1-5",
      "instruction": "生成今日工作计划和待办事项",
      "enabled": true,
      "created_at": "2024-03-03T14:00:00Z",
      "updated_at": "2024-03-03T14:00:00Z",
      "last_run": "2024-03-04T09:00:00Z",
      "next_run": "2024-03-05T09:00:00Z"
    },
    {
      "id": "cron-task-uuid-2",
      "name": "每日总结",
      "cron_expr": "30 18 * * *",
      "instruction": "总结今天的工作内容并保存",
      "enabled": true,
      "created_at": "2024-03-03T14:00:00Z",
      "updated_at": "2024-03-03T14:00:00Z",
      "last_run": "2024-03-03T18:30:00Z",
      "next_run": "2024-03-04T18:30:00Z"
    }
  ]
}
```

**关键方法**：`add` / `update` / `delete` / `get` / `load_all` / `get_enabled`

---

## 4. 文件结构

```
siada/agent_hub/proactive/
├── __init__.py
├── proactive_design.md        # 本文档
├── daemon.py                  # Daemon 主进程
├── daemon_manager.py          # Daemon 进程管理器
├── scheduler.py               # 定时任务调度器（三层架构）
├── proactive_agent.py         # 主动性 Agent
├── task_storage.py            # 按日期分文件的任务存储
├── cron_task_storage.py       # Crontab 任务持久化存储
├── models.py                  # 数据模型（Task、CronTask、TaskList）
├── prompts/
│   ├── system_prompt.py       # PROACTIVE_SYSTEM_PROMPT
│   └── task_templates/
│       ├── discover_tasks.py  # DISCOVER_TASKS_INSTRUCTION
│       └── daily_summary.py   # DAILY_SUMMARY_INSTRUCTION
└── utils/
    ├── pid_manager.py         # PID 文件管理
    └── time_utils.py          # 时间工具（parse_time_str, is_work_hours）

siada/tools/proactive/
└── manage_cron_task.py        # Crontab 任务管理工具（create/update/delete/list）

siada/tools/memory/
├── save_task_list.py          # 保存任务列表工具
├── list_memory_files.py       # 列出记忆文件工具
└── search_memory_by_date.py   # 按日期搜索记忆工具

siada/config/
└── config_loader.py           # 含 ProactiveConfig

siada/entrypoint/
└── siadahub.py                # CLI（已集成 daemon 管理）

tests/agent_hub/proactive/
├── test_daemon.py
├── test_daemon_manager.py
├── test_scheduler.py
├── test_proactive_agent.py
├── test_task_storage.py
└── test_cron_task_storage.py

tests/tools/proactive/
└── test_manage_cron_task.py
```

---

## 5. 用户交互

### 5.1 首次启动

```bash
$ siada-cli
✓ Starting Siada daemon... (PID: 12345)
✓ Proactive scheduler enabled
✓ CLI started

> You have 0 pending tasks.
> Proactive agent will check for tasks during work hours (09:00-18:00) every 60 minutes.
> Daily notification at 08:30.
```

### 5.2 再次启动（daemon 已运行）

```bash
$ siada-cli
✓ Daemon already running (PID: 12345)
✓ CLI started

> You have 3 pending tasks. Type '/tasks' to view.
```

### 5.3 退出前端（Ctrl+C）

```bash
> doing some work...

^C
✓ CLI closed (daemon still running in background)
```

### 5.4 停止 daemon

```bash
$ siada-cli stop
✓ Stopping daemon (PID: 12345)...
✓ Daemon stopped
```

### 5.5 查看主动发现的任务

```bash
> /tasks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Proactive Tasks (3)
 Last updated: 2024-03-03 14:00
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] 🔴 HIGH: Continue API authentication [Needs Confirmation]
    Based on yesterday's discussion, you need to:
    • Implement JWT token validation
    • Add rate limiting middleware
    
    Confidence: 90%
    Source: 2024-03-02-api-design.md
    Note: Needs confirmation - multiple implementation approaches
    
[2] 🟡 MEDIUM: Fix user registration bug
    You mentioned a validation error but haven't fixed it.
    
    Confidence: 75%
    Source: 2024-03-01-bug-fix.md
    Note: No confirmation needed - clear bug fix
    
[3] 🟢 LOW: Update documentation
    New payment module needs API docs.
    
    Confidence: 60%
    Source: 2024-02-28-feature.md
    Note: No confirmation needed - straightforward task

> /task 1
⚠️  This task requires confirmation. Proceed? [y/n]
> y
[Starting work on: Continue API authentication...]
```

### 5.6 检查 daemon 状态（可选）

```bash
$ siada-cli status
✓ Daemon: Running (PID: 12345)
  Uptime: 2h 34m
  Last task check: 14:00
  Pending tasks: 3
```

### 5.7 Crontab 任务管理（新增）

#### 5.7.1 创建 Crontab 任务

```bash
> 帮我创建一个定时任务，每个工作日早上9点生成今日工作计划

[ProactiveAgent 正在处理...]
✓ Crontab 任务已创建！

任务详情：
  ID: cron-abc123
  名称: 工作日早报
  Cron表达式: 0 9 * * 1-5
  指令: 分析今日待办事项，生成工作计划并推送通知
  状态: 已启用
  下次执行: 2024-03-05 09:00:00
```

#### 5.7.2 查看所有 Crontab 任务

```bash
> 列出所有定时任务

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Crontab 任务列表 (3个)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] ✅ 工作日早报
    Cron: 0 9 * * 1-5 (工作日早上9:00)
    指令: 分析今日待办事项，生成工作计划并推送通知
    下次执行: 2024-03-05 09:00:00
    上次执行: 2024-03-04 09:00:00

[2] ✅ 每日总结
    Cron: 30 18 * * * (每天下午6:30)
    指令: 总结今天的工作内容并保存到记忆
    下次执行: 2024-03-04 18:30:00
    上次执行: 2024-03-03 18:30:00

[3] ⏸️  周报生成（已禁用）
    Cron: 0 17 * * 5 (每周五下午5:00)
    指令: 生成本周工作总结报告
    下次执行: 2024-03-08 17:00:00
```

#### 5.7.3 更新 Crontab 任务

```bash
> 修改工作日早报的时间为8:30

[ProactiveAgent 正在处理...]
✓ Crontab 任务已更新！

任务详情：
  ID: cron-abc123
  名称: 工作日早报
  Cron表达式: 30 8 * * 1-5 (已修改)
  指令: 分析今日待办事项，生成工作计划并推送通知
  状态: 已启用
  下次执行: 2024-03-05 08:30:00
```

#### 5.7.4 删除 Crontab 任务

```bash
> 删除周报生成任务

[ProactiveAgent 正在处理...]
✓ Crontab 任务已删除！

已删除任务：周报生成 (cron-xyz789)
```

---

## 6. 配置

**配置文件**：`~/.siada-cli/conf.yaml`（复用现有配置文件）

```yaml
proactive:
  enabled: true                # 是否启用主动性功能
  work_hours: "09:00-18:00"    # 工作时段
  trigger_interval: 60         # 工作时段触发间隔（分钟）
  daily_task_execution_time: "08:30"   # 次日早晨推送时间
```

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | bool | `true` | 是否启用主动性功能 |
| `work_hours` | str | `"09:00-18:00"` | 工作时段定义（24小时制） |
| `trigger_interval` | int | `60` | 工作时段内任务发现触发间隔（分钟） |
| `daily_task_execution_time` | str | `"08:30"` | 次日早晨推送总结和计划的时间 |

配置通过 `siada.config.config_loader.load_conf()` 加载，访问路径：`config.proactive_config`。

---

## 7. Prompt 设计要点

### 7.1 任务发现
- 分析近期工作历史
- 识别 TODO、未完成工作、后续行动
- 输出结构化任务列表（JSON）
- 包含置信度和优先级
- **判断是否需要人工确认**

### 7.2 任务状态判断
- 判断任务状态：PENDING / IN_PROGRESS / COMPLETED
- 基于上下文推理
- 过滤已完成任务

### 7.3 人工确认判断
ProactiveAgent 需要识别任务是否需要人工确认：

**需要确认的任务类型**：
- 涉及重要决策（架构选择、技术方案）
- 可能有多种实现方式
- 需要用户输入额外信息
- 涉及敏感操作（删除、重构）
- 模糊或歧义的需求

**无需确认的任务类型**：
- 明确的后续步骤（用户已说明"下次要做XXX"）
- 简单的待办事项（写文档、更新依赖）
- 用户明确提到的 TODO
- 常规维护任务

**Prompt 中包含判断逻辑**：
```
For each task, determine if it needs_confirmation:
- true: If the task involves important decisions, unclear requirements, 
        or could be done in multiple ways
- false: If the task is clearly defined and the next steps are obvious
```

---

## 8. 待完成工作

**技术债务**
- `execute_pending_tasks` 中 `needs_confirmation=True` 的用户确认机制尚未设计

