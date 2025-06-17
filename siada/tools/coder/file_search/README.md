# File Search - 高性能文件搜索工具

基于 ripgrep 的 Python 文件搜索模块，提供快速、准确的代码搜索功能。

## 功能特性

- **高性能搜索**: 使用 ripgrep 工具，比传统正则搜索快数倍
- **上下文信息**: 提供匹配行前后的上下文
- **文件过滤**: 支持 glob 模式过滤特定类型文件
- **跨平台支持**: 支持 Windows、macOS、Linux
- **打包友好**: 支持开发环境和打包分发
- **自动降级**: 优先使用内置二进制文件，可降级到系统安装

## 快速开始

### 基本用法

```python
from file_search import regex_search_files

# 搜索 TODO 注释
results = regex_search_files(
    cwd="/path/to/project",
    directory_path="/path/to/search", 
    regex=r"TODO:",
    file_pattern="*.py"
)
print(results)
```

### 类接口

```python
from file_search import RipgrepSearcher

searcher = RipgrepSearcher()
results = searcher.search_in_files(
    directory_path="./siada",
    regex=r"def\s+\w+\(",
    file_pattern="*.py",
    cwd="/path/to/project"
)
```

## 安装配置

### 自动配置（推荐）

工具会自动查找 ripgrep 二进制文件，按以下优先级：

1. `RIPGREP_BINARY_PATH` 环境变量
2. 内置二进制文件（开发/打包环境）
3. 系统 PATH 中的 ripgrep

### 手动配置

如需指定特定的 ripgrep 路径：

```bash
export RIPGREP_BINARY_PATH="/path/to/rg"
```

### 二进制文件

内置支持以下平台的二进制文件：
- Windows: `rg.exe`
- macOS Intel: `rg-macos-x64`
- macOS Apple Silicon: `rg-macos-arm64`
- Linux x64: `rg-linux-x64`
- Linux ARM64: `rg-linux-arm64`

## 使用示例

### 搜索代码注释
```python
# 搜索 TODO/FIXME 注释
regex_search_files(".", ".", r"TODO:|FIXME:|HACK:", "*.py")
```

### 搜索函数和类
```python
# 搜索函数定义
regex_search_files(".", ".", r"def\s+\w+\(", "*.py")

# 搜索类定义
regex_search_files(".", ".", r"class\s+\w+", "*.py")
```

### 搜索导入语句
```python
regex_search_files(".", ".", r"^import\s+|^from\s+\w+\s+import", "*.py")
```

### 多文件类型搜索
```python
regex_search_files(".", ".", r"console\.log", "*.{js,ts}")
```

## 输出格式

```
Found 2 results.

src/main.py
│----
│def process_data(data):
│    # TODO: Add error handling
│    return data
│----

src/utils.py
│----
│class Helper:
│    def __init__(self):
│        # TODO: Initialize properly
│        pass
│----
```

## 参数说明

- **cwd**: 当前工作目录，用于计算相对路径
- **directory_path**: 要搜索的目录路径
- **regex**: 正则表达式模式（Rust 语法）
- **file_pattern**: 文件模式过滤器（如 "*.py", "*.js", "*"）

## 正则表达式语法

使用 Rust 正则表达式语法，主要特性：
- 支持 Unicode
- 默认多行模式
- 支持前瞻和后顾断言
- 详细语法：https://docs.rs/regex/latest/regex/#syntax

## 性能特性

- **结果限制**: 最多返回 300 个结果
- **输出限制**: 防止内存占用过大
- **上下文控制**: 每个匹配提供前后各 1 行上下文

## 打包分发

### 打包配置

在 `pyproject.toml` 中添加：

```toml
[tool.setuptools.package-data]
"src.tools.coder.file_search" = ["bin/*", "README.md"]

[tool.setuptools.packages.find]
where = ["src"]
include = ["src.tools.coder.file_search*"]
```

### 验证打包

```bash
# 运行打包检查
python siada/tools/coder/file_search/setup_package.py

# 测试功能
python siada/tools/coder/file_search/test_search.py
```

## 故障排除

### 常见问题

**找不到 ripgrep 二进制文件**
- 设置环境变量：`export RIPGREP_BINARY_PATH="/path/to/rg"`
- 安装系统 ripgrep：`brew install ripgrep` (macOS) 或 `apt install ripgrep` (Ubuntu)

**权限错误**
- Unix 系统：`chmod +x file_search/bin/rg-*`

**搜索无结果**
- 检查搜索路径和正则表达式语法
- 确认文件模式匹配目标文件

### 调试

```python
from file_search.search import RipgrepSearcher

try:
    searcher = RipgrepSearcher()
    print(f"Ripgrep binary: {searcher.rg_path}")
except RuntimeError as e:
    print(f"Error: {e}")
```

## Docker 环境

```dockerfile
# 安装系统 ripgrep
RUN apt-get update && apt-get install -y ripgrep

# 或设置环境变量
ENV RIPGREP_BINARY_PATH=/usr/bin/rg
```

## 测试

运行测试用例：

```bash
python siada/tools/coder/file_search/test_search.py
```

测试包括：
- 二进制文件检测
- 基本搜索功能
- 文件类型过滤
- 错误处理机制

## 技术细节

- 基于 ripgrep 高性能搜索引擎
- 支持开发和打包环境的自动适配
- 自动权限修复机制
- 多路径搜索策略
- 优雅的错误处理和降级机制
