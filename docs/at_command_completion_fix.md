# @ 命令自动补全修复

## 问题描述

当用户输入 `@` 命令触发文件建议时，选中文件并按 Enter 键会直接将文件发送给后端处理，而不是将文件名插入到输入框中供用户继续编辑。

## 解决方案

### 1. 修改按键绑定逻辑 (`siada/io/key_bindings.py`)

**修改内容:**
- 导入了 `has_completions` 过滤器
- 将 Enter 键绑定分为两种情况：
  - 当没有自动补全菜单时：按原逻辑处理（提交输入或插入换行）
  - 当有自动补全菜单时：区分 @ 命令和 / 命令的不同行为

**代码修改:**
```python
# 原来的单一 Enter 绑定
@kb.add("enter", eager=True, filter=~is_searching)

# 修改为两个独立的绑定
@kb.add("enter", eager=True, filter=~is_searching & ~has_completions)  # 无补全时
@kb.add("enter", eager=True, filter=~is_searching & has_completions)   # 有补全时
```

**关键逻辑:**
```python
# 检查是否为 @ 命令
is_at_command = text and text.lstrip().startswith("@")

if not is_at_command:
    # 对于 / 命令等，接受补全后立即提交（保持原有行为）
    buffer.validate_and_handle()
# 对于 @ 命令，只接受补全，不提交
```

### 2. 修正自动补全器逻辑 (`siada/support/completer.py`)

**修改内容:**
- 修正了 `start_position` 的计算，确保正确替换整个 @ 命令
- 在补全文本中包含 @ 符号，避免文本插入错误

**代码修改:**
```python
# 修正前
start_position = -len(at_text)  # 只替换 @ 后面的部分
Completion(suggestion['value'], ...)  # 补全文本不包含 @

# 修正后  
start_position = -len(text)  # 替换整个 @ 命令
Completion("@" + suggestion['value'], ...)  # 补全文本包含 @
```

## 修改后的用户体验

### 修改前
1. 用户输入 `@`
2. 显示文件建议菜单
3. 用户选择文件并按 Enter
4. **文件直接发送给后端处理** ❌

### 修改后  
1. 用户输入 `@`
2. 显示文件建议菜单
3. 用户选择文件并按 Enter
4. **文件名插入到输入框，用户可以继续编辑** ✅
5. 用户可以添加更多内容或再次按 Enter 提交

## 测试验证

创建了测试脚本 `tests/support/test_completer_at_command.py` 来验证修改：

```bash
$ python tests/support/test_completer_at_command.py

Testing @ command completion...
Completions for '@': 4 found
  1. @config.json (start_pos: -1, display: config.json)
  2. @README.md (start_pos: -1, display: README.md)
  3. @test_file.py (start_pos: -1, display: test_file.py)
  4. @src/ (start_pos: -1, display: src/)

✅ @ command completion test completed!
```

## 技术细节

### 按键绑定机制
- 使用 `has_completions` 过滤器检测是否有自动补全菜单
- 当有补全菜单时，Enter 键调用 `buffer.apply_completion()` 而不是 `buffer.validate_and_handle()`

### 补全位置计算
- `start_position = -len(text)` 确保替换整个 @ 命令
- 补全文本包含 @ 符号，保持命令的完整性

## 影响范围

- **主要影响**: @ 命令的交互体验
- **兼容性**: 不影响其他功能，向后兼容
- **性能**: 无明显性能影响

## 相关文件

1. `siada/io/key_bindings.py` - 按键绑定逻辑
2. `siada/support/completer.py` - 自动补全器
3. `tests/support/test_completer_at_command.py` - 测试脚本
4. `docs/at_command_completion_fix.md` - 本文档
