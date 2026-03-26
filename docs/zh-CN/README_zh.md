# Siada CLI

**简体中文 | [English](../../README.md)**

[![PyPI version](https://img.shields.io/pypi/v/siada-cli)](https://pypi.org/project/siada-cli/)
[![Python Version](https://img.shields.io/badge/python-3.12+-blue)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](../../LICENSE)

![Siada CLI Screenshot](../assets/siada-cli-screenshot-zh.gif)

本仓库包含 **Siada CLI**，这是一个命令行 AI 工作流工具，为代码开发、调试和自动化任务提供专业化的智能代理。

Siada CLI 可感知用户的**项目上下文**、**计算机环境**与**跨会话持久记忆**，并支持 Terminal、飞书、Web 等多种入口，提供一致、可持续的个性化智能辅助。

> **当前最新版本：v1.7.0**

---

## Siada CLI 能做什么

- **代码生成** — 创建新功能、Web 界面、重构代码，支持多种编程语言
- **错误修复** — 自动识别、分析和修复大型代码库中的代码缺陷
- **长周期任务执行** — 通过 Spec 驱动执行与子 Agent 编排，稳定完成跨越多步骤、大量上下文切换的复杂开发任务，避免目标漂移
- **自我进化** — 持久记忆与定时主动任务，让助手持续进化
- **主机管理** — 支持对个人电脑、文档的远程管理与处理
- **多入口支持** — 终端（交互/非交互）、飞书远程控制、Web 界面，随你选择

---

## 安装与更新

### 系统要求

| 要求 | 详情 |
|---|---|
| 操作系统 | macOS、Linux |
| GCC | 11+ |
| 包管理器 | [uv](https://github.com/astral-sh/uv) |

### 安装

**第一步：安装 uv**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**第二步：安装 Siada CLI**
```bash
uv tool install --force --python python3.12 --compile --with pip siada-cli@latest
```

安装后若 `siada-cli` 不在 PATH 中，运行以下命令更新 shell：
```bash
uv tool update-shell
```

### 更新
```bash
uv tool upgrade siada-cli
```

### 卸载
```bash
uv tool uninstall siada-cli
```

---

## 开发者模式安装

1. **前提条件：** 确保已安装 [Python 3.12+](https://www.python.org/downloads/) 和 [Poetry](https://python-poetry.org/docs/#installation)。

2. **克隆并安装：**
   ```bash
   git clone https://github.com/liauto-siada/siada-cli.git
   cd siada-cli
   poetry install
   ```

3. **构建 UI（首次运行前必须）：**
   ```bash
   cd siada_cli_ui && npm ci && npm run build:all && cd ..
   ```

4. **运行 CLI：**
   ```bash
   # 方法1：使用 Poetry 运行
   poetry run siada-cli

   # 方法2：激活虚拟环境后使用（推荐）
   source $(poetry env info --path)/bin/activate
   siada-cli
   ```

---

## 配置

### 快速模型配置

首次启动时，Siada CLI 会引导你完成交互式配置——选择供应商、选择模型、输入 API Key，即可开始使用，无需手动编辑任何配置文件。

如需高级配置（配置文件、环境变量、命令行参数），请参阅[用户手册](./USERMANUAL_zh.md)。

如需配置自定义外部模型（私有化部署），请参阅[外部模型配置指南](./external_model_configuration_zh.md)。

---

## 使用模式

### 交互模式（持续对话）
```bash
siada-cli
```

### 非交互模式（脚本 / CI 集成）
```bash
siada-cli --no-interactive "修复 src/main.py 中的空指针异常"
```

### 飞书远程控制
将 Siada CLI 连接到飞书工作空间，通过消息远程下发任务。详见[飞书远程控制使用指南](./remote_control_lark_zh.md)。

---

## 核心特性

### 记忆系统
跨会话持久记忆让 Siada 记住你的偏好、代码库上下文和历史决策，每次交互都更加精准。

### Checkpoint 检查点
在关键决策点保存和恢复 Agent 状态，让你对长时任务保持完全掌控。

### Skills（技能系统）
以 `SKILL.md` 文件形式定义可复用的指令集和工作流，将其扩展为针对你的领域或团队规范的专用能力。详见 [Skills 文档](../SKILLS.md)。

### MCP 支持
通过 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 连接外部工具服务，按需扩展 Siada 的工具集。

### 守护进程与定时任务
以后台守护进程模式运行，执行主动式定时自动化任务。

### 指令上下文（规则文件）
在项目或家目录中放置 `siada_rule.md` 或 `.siadarules/` 文件，持久化设定 AI 行为规则，无需在每次对话中重复说明。

### 自动压缩
智能压缩对话历史，在不丢失关键上下文的前提下保持在模型上下文限制内。详见[压缩策略配置](./compaction_configuration_zh.md)。

---

## 文档目录

| 文档 | 说明 |
|---|---|
| [用户手册](./USERMANUAL_zh.md) | 完整使用指南、命令参考与配置说明 |
| [Skills 系统文档](../SKILLS.md) | 创建和管理可复用 AI 技能 |
| [外部模型配置](./external_model_configuration_zh.md) | 配置私有/自定义模型端点 |
| [飞书远程控制](./remote_control_lark_zh.md) | 通过飞书消息控制 Siada |
| [压缩策略配置](./compaction_configuration_zh.md) | 上下文压缩策略设置 |
| [贡献指南](./CONTRIBUTING_zh.md) | 如何为本项目做贡献 |

---

## 贡献指南

我们欢迎对 Siada CLI 的贡献！无论您想修复错误、添加新功能、改进文档还是提出改进建议，我们都非常感谢。

提交前请阅读[贡献指南](./CONTRIBUTING_zh.md)，其中包含：

- 项目愿景和开发目标
- 项目目录结构和开发规范
- Pull Request 指南和最佳实践
- 代码组织原则

---

## 致谢

Siada CLI 的建设离不开众多优秀开源项目的支持，我们对这些项目的贡献者深表敬意与感谢。

特别感谢：
- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) — 提供核心 Agent 框架
- [LiteLLM](https://github.com/BerriAI/litellm) — 统一的大模型提供商接口
- [OpenHands ACI](https://github.com/All-Hands-AI/OpenHands) — Agent 与计算机交互工具集
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) — 终端原生 AI Agent 设计的重要参考

有关 Siada CLI 中使用的完整开源项目和许可证清单，请查看 [CREDITS_zh.md](./CREDITS_zh.md)。

---

## 许可证

本项目采用 [Apache 2.0 许可证](../../LICENSE) 分发。

## 免责声明

请参阅 [disclaimers.md](../../docs/disclaimers.md)。

---

<div align="center">
由理想汽车代码智能团队和开源社区倾情打造
</div>
