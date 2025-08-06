# @ 命令位置识别优化

## 修改说明

优化了 `siada/support/completer.py` 中的 `@` 命令识别逻辑，使其能够在文本的任意位置工作，而不仅仅是在开头。

## 核心改动

### 之前的逻辑
```python
elif text[0] == "@":
    # 只能在文本开头使用
```

### 现在的逻辑
```python
# Check for @ symbol anywhere in the text before cursor
text_before_cursor = document.text_before_cursor
at_pos = text_before_cursor.rfind("@")

if at_pos != -1:
    # Extract query text from @ symbol to cursor
    query_text = text_before_cursor[at_pos:]
    # 基于光标位置精确处理
```

## 支持的使用场景

1. **传统用法**（兼容性保持）
   - `@file.py` ✅
   - `@src/` ✅

2. **新增用法**
   - `some command @file.py` ✅
   - `cmd1 @dir/ cmd2` ✅
   - `长文本 @path/to/file` ✅

## 技术实现

- 使用 `document.text_before_cursor` 获取光标前的文本
- 使用 `rfind("@")` 找到最近的 "@" 符号位置
- 提取从 "@" 到光标位置的查询文本
- 正确计算 `start_position` 确保替换位置准确

## 性能影响

- 时间复杂度：O(n)，n 为光标前文本长度
- 实际影响很小，因为用户输入通常较短
- 保持了原有的异常处理机制

## 测试验证

运行 `python tests/support/test_completer_at_command.py` 验证功能：
- 基本 @ 命令：✅
- 中间位置 @ 命令：✅
- 多个 @ 符号处理：✅
- 光标位置识别：✅

## 回车键行为修复

### 问题
修改 `completer.py` 后，中间位置的 "@" 命令在按回车键时会直接提交消息，而开头位置的 "@" 命令按回车键只是上屏补全内容。

### 根本原因
`siada/io/key_bindings.py` 中的 "@" 命令检测逻辑使用：
```python
is_at_command = text and text.lstrip().startswith("@")
```
这只能检测开头的 "@"，导致中间位置的 "@" 命令被误判为非 "@" 命令。

### 修复方案
将检测逻辑修改为与 `completer.py` 一致：
```python
# 使用光标位置检测@命令
text_before_cursor = buffer.document.text_before_cursor
at_pos = text_before_cursor.rfind("@")
is_at_command = at_pos != -1
```

### 修复后的行为
- **开头位置的 "@"**：回车键只上屏补全，不提交 ✅
- **中间位置的 "@"**：回车键只上屏补全，不提交 ✅  
- **"/" 命令**：回车键上屏补全并提交 ✅
- **普通文本**：回车键直接提交 ✅

## 向后兼容性

✅ 完全向后兼容，不影响现有的 "@" 命令使用方式
✅ 不影响 "/" 命令的原有逻辑
✅ 修复了中间位置 "@" 命令的回车键行为不一致问题
