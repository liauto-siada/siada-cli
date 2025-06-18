# Agent配置文件使用说明

## 概述

本项目使用配置文件 `agent_config.yaml` 来管理Agent的注册和配置，实现了灵活的Agent管理机制。

## 配置文件结构

配置文件位于项目根目录：`agent_config.yaml`

```yaml
agents:
  # Agent名称（小写，支持下划线）
  agent_name:
    class: "完整的类导入路径"
    description: "Agent描述信息"
    enabled: true/false
```

## 当前支持的Agent

### BugFixAgent
- **名称**: `bugfix`
- **类路径**: `siada.agent_hub.coder.bug_fix_agent.BugFixAgent`
- **描述**: 专门用于代码bug修复的Agent
- **状态**: 已启用

### CoderAgent (计划中)
- **名称**: `coder`
- **类路径**: 暂未实现
- **描述**: 通用代码开发Agent
- **状态**: 已禁用

## 使用方法

### 基本用法

```python
from siada.services.siada_runner import SiadaRunner

# 获取BugFixAgent实例
agent = await SiadaRunner.get_agent("bugfix")

# 支持多种名称格式
agent = await SiadaRunner.get_agent("BugFix")    # 大写
agent = await SiadaRunner.get_agent("bug_fix")   # 下划线
agent = await SiadaRunner.get_agent("bug-fix")   # 连字符
```

### 错误处理

```python
try:
    agent = await SiadaRunner.get_agent("unknown")
except ValueError as e:
    print(f"Agent不存在: {e}")

try:
    agent = await SiadaRunner.get_agent("coder")  # 禁用的Agent
except ValueError as e:
    print(f"Agent已禁用: {e}")
```

## 添加新Agent

要添加新的Agent，只需要：

1. **实现Agent类**：创建继承自 `Agent` 的新类
2. **更新配置文件**：在 `agent_config.yaml` 中添加配置

### 示例：添加新的Agent

1. 创建Agent类文件：`siada/agent_hub/new_agent.py`
```python
from agents import Agent

class NewAgent(Agent):
    def __init__(self):
        super().__init__(name="NewAgent", ...)
```

2. 更新 `agent_config.yaml`：
```yaml
agents:
  bugfix:
    class: "siada.agent_hub.coder.bug_fix_agent.BugFixAgent"
    description: "专门用于代码bug修复的Agent"
    enabled: true
  
  # 新增的Agent
  newagent:
    class: "siada.agent_hub.new_agent.NewAgent"
    description: "新功能Agent"
    enabled: true
```

3. 使用新Agent：
```python
agent = await SiadaRunner.get_agent("newagent")
```

## 配置选项说明

- **class**: Agent类的完整导入路径
  - 格式：`模块路径.类名`
  - 如果为 `null`，表示Agent尚未实现
  
- **description**: Agent的描述信息
  - 用于文档和调试
  
- **enabled**: 是否启用该Agent
  - `true`: 启用，可以通过 `get_agent()` 获取
  - `false`: 禁用，调用时会抛出异常

## 特性

- ✅ **动态加载**: 支持运行时动态导入Agent类
- ✅ **名称灵活**: 支持多种名称格式（大小写、下划线、连字符）
- ✅ **状态管理**: 支持启用/禁用Agent
- ✅ **错误处理**: 完善的异常处理机制
- ✅ **扩展性**: 易于添加新的Agent类型
- ✅ **配置驱动**: 无需修改代码，只需更新配置文件

## 注意事项

1. **配置文件路径**: 配置文件必须位于项目根目录
2. **类导入路径**: 确保Agent类的导入路径正确
3. **依赖管理**: 新Agent的依赖需要正确安装
4. **命名规范**: Agent名称建议使用小写字母和下划线
