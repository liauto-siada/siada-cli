# 复杂仓库 RepoMap 测试结果

## 问题分析与解决方案

### 原始问题
用户配置了 tree-sitter 但生成的 repo map 只有文件名，没有方法名和变量名。

### 根本原因分析
通过对比简单项目和复杂项目的测试结果，我们发现问题的根本原因：

1. **文件内容质量**: 简单项目（siada-agenthub）中大部分文件是空的 `__init__.py` 或内容较少的文件
2. **Token 限制**: 默认的 token 限制（1024-4096）对于复杂项目来说太低
3. **Chat files 策略**: 将重要文件设置为 chat_files 会导致它们被排除在 repo map 之外
4. **文件选择策略**: 没有智能过滤，包含了太多空文件

### 解决方案

#### 1. 智能文件过滤
```python
# 过滤出有实际内容的文件（避免空的 __init__.py）
substantial_files = []
for filepath in python_files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read().strip()
        # 只包含有实际内容的文件（超过100个字符且不只是注释）
        if len(content) > 100:
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            non_comment_lines = [line for line in lines if not line.startswith('#')]
            if len(non_comment_lines) > 5:  # 至少有5行非注释代码
                substantial_files.append(filepath)
```

#### 2. 增加 Token 限制
```python
repo_map = RepoMap(
    root=complex_repo_root,
    main_model=mock_model,
    io=mock_io,
    verbose=True,
    map_tokens=8192,  # 增加 token 限制
    map_mul_no_files=16  # 增加无文件时的倍数
)
```

#### 3. 优化 Chat Files 策略
```python
# 只选择少量最重要的文件作为 chat_files，让更多文件出现在 repo map 中
for filepath in substantial_files:
    rel_path = os.path.relpath(filepath, complex_repo_root)
    # 只有非常核心的文件才作为 chat_files
    if any(core in rel_path.lower() for core in ['main.py', 'app.py', '__main__.py']):
        chat_files.append(filepath)
    else:
        other_files.append(filepath)
```

## 测试结果对比

### 简单项目 (siada-agenthub)
- **文件数**: 71 个 Python 文件
- **有效文件**: 很少（大部分是空的 `__init__.py`）
- **生成的 repo map**: 143 tokens，552 字符
- **内容**: 只有文件名列表
- **原因**: 文件内容太少，没有足够的函数和类定义

### 复杂项目 (siada)
- **文件数**: 1047 个 Python 文件
- **有效文件**: 805 个（过滤后 50 个）
- **生成的 repo map**: 7150 tokens，22751 字符
- **内容**: 包含详细的函数名、类名、方法名
- **成功因素**: 
  - 文件内容丰富
  - 足够的 token 限制
  - 智能的文件选择策略

## 生成的 Repo Map 示例

```
siada/core/compatibility/issue_transformer.py:
⋮
│def transform_issue(issue: Optional[Dict[str, any]], system_context: SystemContext) -> Issue:
⋮
│def transform_issues(issues: Optional[List[Dict[str, any]]], system_context: SystemContext) -> List
⋮
│def extract_line_number(location: str) -> int:
⋮

siada/core/config/config.py:
⋮
│class Config(BaseModel):
⋮
│def load_yaml_file(file_path: Optional[str] = None, config_cls=None):
⋮
│def load_config(repo_dir: Optional[str] = None) -> Config:
⋮
```

## 标签提取验证

从复杂文件中成功提取标签：
- **测试文件**: `siada/core/reviewer/base_impl_reviewer.py`
- **提取到**: 59 个标签
- **定义标签**: 13 个（函数、类定义）
- **引用标签**: 46 个（函数调用、变量引用）

定义标签示例：
- `BaseImplReviewer` (类)
- `get_review_codes` (方法)
- `do_review` (方法)
- `post_review_codes` (方法)

## 关键发现

1. **Tree-sitter 配置正常**: 标签提取功能完全正常，能够正确识别函数、类、方法
2. **PageRank 算法正常**: 能够根据代码关联性正确排序文件重要性
3. **问题在于输入质量**: 简单项目的文件内容太少，无法生成有意义的 repo map
4. **Token 限制很重要**: 足够的 token 限制是生成详细 repo map 的前提

## 建议

### 对于用户
1. **增加 token 限制**: 对于复杂项目，建议使用 8192 或更高的 token 限制
2. **智能文件选择**: 过滤掉空文件和内容很少的文件
3. **减少 chat_files**: 只将最核心的文件设置为 chat_files
4. **项目规模**: 确保项目有足够的代码内容

### 对于 RepoMap 改进
1. **自动文件过滤**: 内置智能文件过滤逻辑
2. **动态 token 调整**: 根据项目规模自动调整 token 限制
3. **更好的默认策略**: 优化默认的 chat_files 选择策略

## 结论

RepoMap 功能完全正常，tree-sitter 配置也正确。之前只显示文件名的问题是由于：
1. 测试项目（siada-agenthub）文件内容太少
2. Token 限制不够
3. 文件选择策略不当

通过使用复杂项目（siada）和优化配置，我们成功生成了包含详细函数名、类名、方法名的 repo map，验证了整个系统的正确性。
