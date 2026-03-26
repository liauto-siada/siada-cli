# Custom Commands 功能说明

## 概述

Custom Commands 允许用户创建可重用的提示词快捷方式，提高工作效率并确保提示词的一致性。命令可以是全局的（跨所有项目）或项目特定的，支持高级功能如参数注入、Shell 命令执行和文件内容嵌入。

## 核心特性

- ✅ **二级命令系统**: 用户全局命令、项目本地命令
- ✅ **动态参数注入**: 支持 `{{args}}` 占位符
- ✅ **Shell 命令执行**: 通过 `!{...}` 语法执行系统命令
- ✅ **文件内容注入**: 通过 `@{...}` 语法嵌入文件内容
- ✅ **命名空间**: 使用目录结构组织命令

## 命令目录结构

```
~/.siada-cli/commands/                # 用户全局命令
├── test.toml                         # /test
├── git/
│   ├── commit.toml                   # /git:commit
│   └── push.toml                     # /git:push
└── refactor/
    └── pure.toml                     # /refactor:pure

<project>/.siada-cli/commands/            # 项目本地命令
├── changelog.toml                    # /changelog (覆盖全局同名命令)
└── review.toml                       # /review
```

## TOML 文件格式

### 基础示例

```toml
# 最简单的命令
description = "问候用户"
prompt = "请用友好的方式问候用户，并询问今天可以帮助什么。"
```

### 多行提示词

```toml
description = "代码审查助手"
prompt = """
你是一位经验丰富的代码审查专家。

请审查当前上下文中的代码，重点关注：
1. 代码可读性和可维护性
2. 潜在的性能问题
3. 安全漏洞
4. 最佳实践的遵循情况

提供具体的改进建议，并附上代码示例。
"""
```

## 特殊语法

### 1. 参数占位符 `{{args}}`

用于在 prompt 中注入用户提供的参数。

```toml
description = "解释编程概念"
prompt = "请详细解释以下编程概念: {{args}}"
```

用法：
```bash
/explain "dependency injection"
```

实际发送给 AI 的内容：
```
请详细解释以下编程概念: dependency injection
```

### 2. 文件注入 `@{path}`

将文件或目录内容嵌入到 prompt 中。

```toml
description = "使用最佳实践审查代码"
prompt = """
请根据以下最佳实践指南审查代码:

@{docs/code-review-guidelines.md}

现在审查用户提供的代码。
"""
```

**支持的格式**：
- 单个文件：`@{src/main.py}`
- 目录：`@{src/}` （递归读取所有文件）
- 相对路径自动相对于工作区

### 3. Shell 命令执行 `!{command}`

执行 shell 命令并将输出注入到 prompt 中。

```toml
description = "根据 staged changes 生成 commit 消息"
prompt = """
请根据以下 git diff 生成一个符合 Conventional Commits 规范的提交消息:

```diff
!{git diff --staged}
```

要求:
- 使用合适的类型 (feat/fix/docs/etc.)
- 简洁描述变更内容
"""
```

### 4. 混合使用

```toml
description = "审查指定文件"
prompt = """
你是代码审查专家。请审查以下文件: {{args}}

文件内容:
!{cat {{args}}}

提供改进建议。
"""
```

用法：
```bash
/review "src/utils/helper.py"
```

**注意**：在 `!{...}` 内部的 `{{args}}` 会自动转义，防止命令注入攻击。

## 默认参数处理

如果 prompt 中**不包含** `{{args}}`，用户的完整命令会自动追加到 prompt 末尾，让 AI 自行解析。

```toml
description = "向 CHANGELOG 添加新条目"
prompt = """
你是本软件项目的专业维护者。用户执行了一个命令来添加 changelog 条目。

解析命令中的版本号、类型和消息，然后更新 CHANGELOG.md 文件。
"""
```

用法：
```bash
/changelog 1.2.0 added "Support for custom commands"
```

AI 实际收到：
```
你是本软件项目的专业维护者。用户执行了一个命令来添加 changelog 条目。

解析命令中的版本号、类型和消息，然后更新 CHANGELOG.md 文件。

/changelog 1.2.0 added "Support for custom commands"
```

## 命令示例

### 示例 1: Git Commit 消息生成

文件：`~/.siada-cli/commands/git/commit.toml`

```toml
description = "根据 staged changes 生成 commit 消息"
prompt = """
请根据以下 git diff 生成一个符合 Conventional Commits 规范的提交消息:

```diff
!{git diff --staged}
```

要求:
- 使用合适的类型 (feat/fix/docs/etc.)
- 简洁描述变更内容
- 如有必要，添加详细说明
"""
```

### 示例 2: 代码搜索和分析

文件：`~/.siada-cli/commands/search.toml`

```toml
description = "在代码中搜索指定模式并分析"
prompt = """
请分析以下搜索结果并总结关键发现:

搜索模式: {{args}}

搜索结果:
!{grep -r {{args}} ./src}

请指出:
1. 模式在哪些文件中出现
2. 使用场景和上下文
3. 潜在的重构机会
"""
```

### 示例 3: 项目文档生成

文件：`<project>/.siada-cli/commands/docs/api.toml`

```toml
description = "生成 API 文档"
prompt = """
请为以下 API 文件生成完整的文档:

@{src/api/}

生成的文档应包括:
1. 每个 API 端点的说明
2. 请求/响应格式
3. 错误处理
4. 使用示例
"""
```

### 示例 4: 测试生成

文件：`~/.siada-cli/commands/test.toml`

```toml
description = "为指定文件生成测试用例"
prompt = """
请为以下文件生成完整的单元测试:

文件路径: {{args}}

文件内容:
@{{{args}}}

要求:
- 使用项目现有的测试框架
- 覆盖主要功能和边界情况
- 包含适当的断言和错误测试
"""
```

## 安全机制

### 1. 路径访问控制

`@{...}` 语法的安全限制：
- 路径必须在工作区内
- 不能使用绝对路径访问工作区外的文件
- 自动跳过隐藏文件和目录（以 `.` 开头）

### 2. Shell 命令转义

`{{args}}` 在 `!{...}` 内部会自动转义，防止命令注入：

```bash
# 用户输入
/search "; rm -rf /"

# 实际执行的命令
grep -r '; rm -rf /' ./src   # 作为字面字符串搜索
```

## 使用技巧

### 1. 组织命令

使用目录结构组织相关命令：

```
~/.siada-cli/commands/
├── git/
│   ├── commit.toml
│   ├── review.toml
│   └── status.toml
├── docs/
│   ├── api.toml
│   └── readme.toml
└── test/
    ├── unit.toml
    └── integration.toml
```

### 2. 项目特定命令

在项目目录创建 `.siada-cli/commands/` 来定义项目特定的命令，这些命令会覆盖同名的全局命令。

### 3. 调试命令

使用 `-v` 或 `--verbose` 标志启动 Siada 可以看到命令加载和执行的详细信息：

```bash
siada -v
```

### 4. 重新加载命令

命令在首次使用时加载，如果修改了命令文件，需要重启 Siada 会话。

## 故障排除

### 命令未找到

1. 检查文件扩展名是否为 `.toml`
2. 检查文件是否在正确的目录 (`~/.siada-cli/commands/` 或 `<project>/.siada-cli/commands/`)
3. 使用 `-v` 标志查看加载日志

### Shell 命令执行失败

1. 确保命令在工作区目录下可以正常执行
2. 检查命令输出和错误信息
3. 考虑添加错误处理逻辑到 prompt 中

### 文件注入失败

1. 检查文件路径是否正确
2. 确保文件在工作区内
3. 检查文件编码（应为 UTF-8）
