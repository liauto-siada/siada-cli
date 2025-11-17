# Siada CLI

**简体中文 | [English](../../README.md)**

![Siada CLI Screenshot](../assets/siada-cli-screenshot-zh.png)

本仓库包含 Siada CLI，这是一个命令行 AI 工作流工具，为代码开发、调试和自动化任务提供专业化的智能代理。

使用 Siada CLI 您可以：

- 通过智能分析和自动化解决方案修复大型代码库中的错误。
- 使用专业化的前端和后端代理生成新的应用程序和组件。
- 通过智能代码生成和测试自动化开发工作流程。
- 执行系统命令并与开发环境交互。
- 无缝支持多种编程语言和框架。

## 安装/更新

### 安装

1. 安装 uv
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. 安装 siada-cli
   ```bash
   uv tool install --force --python python3.12 --compile --with pip siada-cli@latest
   ```
   如果 siada-cli 目录不在 PATH 中，运行以下命令更新 shell
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
   

## 安装（开发者模式）

1. **前提条件：** 确保您已安装 [Python 3.12](https://www.python.org/downloads/) 或更高版本以及 [Poetry](https://python-poetry.org/docs/#installation)。

2. **克隆并安装：**
   ```bash
   git clone https://github.com/your-org/siada-agenthub.git
   cd siada-agenthub
   poetry install
   ```

3. **运行 CLI：**
   ```bash
   # 方法1：使用 Poetry 运行
   poetry run siada-cli
   
   # 方法2：激活虚拟环境后使用（推荐）
   source $(poetry env info --path)/bin/activate
   siada-cli
   ```

## 使用指南

如需了解详细的使用方法和高级功能，请参阅我们的[用户手册](./USERMANUAL_zh.md)，其中包含：

- 详细的配置说明
- 使用模式和命令行选项
- 斜杠命令使用指南
- 代理类型详解
- 实际使用示例
- 故障排除指南


## 贡献指南

我们欢迎对 Siada CLI 的贡献！无论您想修复错误、添加新功能、改进文档还是提出改进建议，我们都非常感谢您的贡献。

要开始贡献，请阅读我们的[贡献指南](./docs/zh-CN/CONTRIBUTING_zh.md)，其中包括：

- 我们的项目愿景和开发目标
- 项目目录结构和开发指南
- 拉取请求指南和最佳实践
- 代码组织原则

在提交任何更改之前，请确保检查我们的问题跟踪器并遵循指南中概述的贡献工作流程。

## 致谢

Siada CLI 的建设离不开众多开源项目的支持，我们对这些项目的贡献者深表敬意与感谢。

特别感谢 [OpenAI Agent SDK](https://github.com/openai/openai-agent-sdk) 为我们的智能代理功能提供了基础框架支持。

有关 Siada CLI 中使用的开源项目和许可证清单，请查看我们的[CREDITS_zh.md](./CREDITS_zh.md)文件。

## 许可证

本项目采用 Apache-2.0 许可证分发。更多信息请参见 [`LICENSE`](../../LICENSE)。

## 免责声明
请参阅 [disclaimers.md](../../disclaimers.md)

----
<div align="center">
由理想汽车代码智能团队和开源社区倾情打造
</div>
