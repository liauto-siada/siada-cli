# Skills 系统文档

Skills 是存储在 `SKILL.md` 文件中的可复用指令集，用于扩展 Siada AI Agent 的能力。通过 Skill，您可以定义专业的工作流程、最佳实践和领域特定知识，AI 可以在执行任务时应用这些内容。

## 目录

- [概述](#概述)
- [创建 Skill](#创建-skill)
- [Skill 文件结构](#skill-文件结构)
- [Skill 作用域](#skill-作用域)
- [优先级与去重](#优先级与去重)
- [使用 Skill](#使用-skill)
- [最佳实践](#最佳实践)
- [示例](#示例)

## 概述

Skills 系统提供以下功能：

- **定义可复用工作流** - 将重复性流程封装为 Skill
- **共享领域知识** - 编码团队规范和最佳实践
- **扩展 AI 能力** - 为特定任务提供专业指导
- **按作用域组织** - 创建项目级、用户级或系统级 Skill

## 创建 Skill

### 步骤 1：选择位置

Skill 根据其作用域存储在特定目录中：

| 作用域 | 目录位置 | 优先级 |
|-------|---------|-------|
| 用户级 | `~/.siada-cli/skills/<skill-name>/` | 最高 |
| 仓库级 | `<项目>/.siada-cli/skills/<skill-name>/` | 中等 |
| 系统级 | 内置 | 最低 |

### 步骤 2：创建目录结构

```bash
# 创建仓库级 Skill
mkdir -p .siada-cli/skills/my-skill

# 创建用户级 Skill
mkdir -p ~/.siada-cli/skills/my-skill
```

### 步骤 3：创建 SKILL.md

在 Skill 目录中创建 `SKILL.md` 文件：

```bash
touch .siada-cli/skills/my-skill/SKILL.md
```

## Skill 文件结构

每个 `SKILL.md` 文件必须包含 YAML frontmatter 头部和 Skill 内容：

```markdown
---
name: my-skill
description: 详细描述这个 Skill 的功能以及何时使用它
---

# My Skill

此处编写 Skill 的具体指令和工作流程...
```

### 必填字段

| 字段 | 类型 | 最大长度 | 描述 |
|-----|------|---------|-----|
| `name` | string | 64 字符 | Skill 的唯一标识符 |
| `description` | string | 1024 字符 | 用于触发匹配的完整描述 |

### 字段指南

- **name**：使用小写字母和连字符（如 `code-review`、`deploy-script`）
- **description**：编写清晰、详细的描述，帮助 AI 理解何时使用此 Skill

## Skill 作用域

Skill 存在于三个级别，具有不同的优先级：

### 用户级（最高优先级）

**位置**：`~/.siada-cli/skills/`

- 跨所有项目的个人 Skill
- 覆盖同名的仓库级和系统级 Skill

```bash
~/.siada-cli/
└── skills/
    ├── my-personal-workflow/
    │   └── SKILL.md
    └── common-patterns/
        └── SKILL.md
```

### 仓库级（中等优先级）

**位置**：`<项目>/.siada-cli/skills/`

- 项目特定的 Skill
- 通过版本控制与团队共享
- 覆盖同名的系统级 Skill

```bash
my-project/
├── .siada-cli/
│   └── skills/
│       ├── build-script/
│       │   └── SKILL.md
│       └── test-workflow/
│           └── SKILL.md
```

### 系统级（最低优先级）

Siada 提供的内置 Skill。可被同名的用户级或仓库级 Skill 覆盖。

## 优先级与去重

当多个作用域存在同名 Skill 时：

1. **用户级 Skill** 优先于所有其他 Skill
2. **仓库级 Skill** 优先于系统级 Skill
3. **系统级 Skill** 仅在没有更高优先级 Skill 时使用

示例：
```
用户级: deploy-app (描述: "我的个人部署")
仓库级: deploy-app (描述: "团队部署流程")
系统级: deploy-app (描述: "通用部署")
→ 结果: 使用用户级版本
```

## 使用 Skill

### 自动触发

Skill 在以下情况下自动触发：

1. **明确提及**：用户在请求中提到 Skill 名称
2. **上下文匹配**：任务明显符合 Skill 的描述

### 手动调用

您可以显式请求使用 Skill：

```
使用 code-review Skill 检查我的代码更改
```

```
应用 deploy-script Skill 进行此次部署
```

### Skill 工作原理

当 Skill 被触发时：

1. AI 读取 `SKILL.md` 文件
2. 按照定义的指令和工作流程执行
3. 应用 Skill 指导完成任务
4. 如果 Skill 失败，回退到通用方法

## 最佳实践

### Skill 设计

1. **单一职责**：每个 Skill 应专注于一种任务类型
2. **清晰触发**：编写能明确指示何时使用 Skill 的描述
3. **完整流程**：包含所有必要的步骤和考虑因素
4. **提供示例**：给出具体的使用示例

### Skill 文件夹结构

Skill 通过 `SKILL.md` 文件中的 Markdown 指令表达一种能力。Skill 文件夹还可以包含脚本、资源和素材，供 AI 执行特定任务时使用。

```bash
my-skill/
├── SKILL.md           # 必需：指令 + 元数据
├── scripts/           # 可选：可执行代码
├── references/        # 可选：参考文档
└── assets/            # 可选：模板、资源
```

| 组件 | 是否必需 | 描述 |
|-----|---------|-----|
| `SKILL.md` | ✅ 是 | 主 Skill 定义文件，包含 YAML frontmatter 和指令 |
| `scripts/` | ❌ 否 | 可执行脚本（Shell、Python 等），AI 可以运行 |
| `references/` | ❌ 否 | 参考文档、指南或相关资料 |
| `assets/` | ❌ 否 | 模板、配置文件或其他资源 |

### 命名约定

- 使用描述性的小写名称
- 使用连字符分隔单词
- 避免特殊字符
- 保持名称简洁但有意义

好的命名：`code-review`、`api-design`、`bug-triage`
差的命名：`CodeReview`、`my_skill_v2`、`do-stuff`

### 内容指南

- 编写清晰、可操作的指令
- 包含何时使用 Skill 的上下文
- 记录任何先决条件
- 提供预期输入/输出的示例

## 示例

### 示例 1：代码审查 Skill

```markdown
---
name: code-review
description: 按照团队标准进行全面代码审查，包括检查安全问题、性能问题和代码风格
---

# Code Review Skill

## 概述

此 Skill 指导按照团队标准进行系统性代码审查。

## 检查清单

1. **安全性**
   - 检查 SQL 注入漏洞
   - 验证输入校验
   - 审查认证/授权

2. **性能**
   - 查找 N+1 查询
   - 检查不必要的计算
   - 审查内存使用

3. **代码质量**
   - 验证命名规范
   - 检查代码重复
   - 审查错误处理

## 输出格式

按以下格式提供反馈：
- 类别：[安全/性能/质量]
- 严重程度：[严重/警告/信息]
- 描述：问题是什么
- 建议：如何修复
```

### 示例 2：API 设计 Skill

```markdown
---
name: api-design
description: 按照公司规范设计 RESTful API，包括端点命名、请求/响应格式和错误处理模式
---

# API Design Skill

## 原则

- 使用 RESTful 规范
- 一致的命名模式
- 正确的 HTTP 方法
- 结构化的错误响应

## 端点命名

- 使用复数名词：`/users`、`/products`
- 使用 kebab-case：`/user-profiles`
- 嵌套相关资源：`/users/{id}/orders`

## 响应格式

```json
{
  "data": {},
  "meta": {
    "page": 1,
    "total": 100
  }
}
```

## 错误格式

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "可读的错误消息",
    "details": []
  }
}
```
```

### 示例 3：部署 Skill

```markdown
---
name: deploy-production
description: 指导生产环境部署，包括部署前检查、部署步骤和部署后验证
---

# Production Deployment Skill

## 部署前检查清单

- [ ] 所有测试通过
- [ ] 代码已审查并批准
- [ ] 数据库迁移已准备好
- [ ] 回滚计划已记录

## 部署步骤

1. 在 #deployments 频道通知团队
2. 创建发布标签
3. 运行数据库迁移
4. 部署应用程序
5. 验证健康检查

## 部署后

1. 监控错误率
2. 检查性能指标
3. 验证关键用户流程
4. 更新部署日志

## 回滚流程

如果检测到问题：
1. 恢复到上一版本
2. 如需要回滚数据库
3. 通知团队回滚
4. 创建事故报告
```

## 故障排除

### 常见问题

**Skill 未被检测到：**
- 验证文件名是否为 `SKILL.md`
- 检查目录结构是否正确
- 确保 YAML frontmatter 有效

**Skill 未触发：**
- 使描述更具体
- 在请求中明确使用 Skill 名称
- 检查是否有同名的更高优先级 Skill

**解析错误：**
- 验证 YAML frontmatter 以 `---` 开始和结束
- 检查必填字段（name、description）是否存在
- 确保字段长度不超过限制

### 调试

通过检查 AI 系统提示中的"可用 Skills"部分来查看已加载的 Skill。

## Skill 命令

Siada 提供斜杠命令来管理 Skills：

### `/skill-list`

列出所有可用的 Skills（仓库级、用户级、系统级）。

```
/skill-list
```

输出包括：
- Skill 名称
- 描述
- 来源作用域（REPO/USER/SYSTEM）

### `/skill-reload`

从磁盘重新加载所有 Skills。在添加、修改或删除 Skill 文件后使用此命令。

```
/skill-reload
```

此命令将：
- 重新扫描所有 Skill 目录
- 解析和验证 SKILL.md 文件
- 更新可用 Skills 列表
- 报告任何解析错误
