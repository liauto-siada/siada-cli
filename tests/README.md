# Siada 自动化测试运行器

## 概述

`run_tests.py` 是 Siada 项目的自动化测试运行器，能够自动发现并运行所有 `test_*.py` 文件。

## 功能特性

- 🔍 **自动发现测试**：递归扫描 `tests/` 目录下所有 `test_*.py` 文件
- 🧪 **运行自动化测试**：使用 pytest 执行所有发现的测试
- 📊 **详细报告**：显示测试结果，包括失败测试的详细信息
- 🎯 **智能路径检测**：无论从项目根目录还是 tests 目录运行都能正确工作

## 使用方法

### 从 tests 目录运行（推荐）

```bash
cd tests
python run_tests.py           # 运行所有自动化测试
python run_tests.py --quiet   # 安静模式运行
python run_tests.py --list    # 只列出测试文件
```

### 从项目根目录运行

```bash
python tests/run_tests.py           # 运行所有自动化测试
python tests/run_tests.py --quiet   # 安静模式运行
python tests/run_tests.py --list    # 只列出测试文件
```

### 命令行参数

- `--quiet, -q`: 安静模式，减少输出信息
- `--list, -l`: 只列出发现的测试文件，不执行测试
- `--help, -h`: 显示帮助信息

## 测试文件约定

- ✅ **自动化测试**：文件名以 `test_` 开头的 `.py` 文件
- ❌ **演示文件**：其他 `.py` 文件（如 `demo_*.py`, `run_*.py` 等）

## 输出示例

### 成功运行
```
🔍 发现 29 个自动化测试文件
  - test_base.py
  - test_logging.py
  ...

🧪 开始运行自动化测试...
================================== test session starts ===================================
...
=================================== 29 passed in 5.23s ====================================

✅ 所有测试通过!
```

### 有失败的测试
```
🔍 发现 29 个自动化测试文件

🧪 开始运行自动化测试...
================================== test session starts ===================================
...
======================================== FAILURES ========================================
_____________________________________ test_example _____________________________________

    def test_example():
>       assert 1 + 1 == 3
        ^^^^^^^^^^^^^^^^^
E       assert (1 + 1) == 3

tests/test_example.py:5: AssertionError
============================== 1 failed, 28 passed in 5.23s ===============================

❌ 有测试失败!
```

## 配置

项目包含 `pytest.ini` 配置文件，设置了以下默认选项：

- `--tb=short`: 显示简短的错误信息
- `--color=yes`: 启用彩色输出
- `--strict-warnings`: 严格警告模式

## 集成到 CI/CD

```yaml
# GitHub Actions 示例
- name: Run automated tests
  run: python tests/run_tests.py

# 或者从 tests 目录运行
- name: Run automated tests
  run: |
    cd tests
    python run_tests.py
```

## 依赖删除影响测试

当删除项目依赖时，可以使用此测试运行器来验证删除的影响：

```bash
# 删除依赖后运行测试
poetry remove some-dependency
python tests/run_tests.py
```

如果测试通过，说明删除的依赖没有影响核心功能。

## 文件结构

```
tests/
├── run_tests.py          # 测试运行器脚本
├── pytest.ini           # pytest 配置文件
├── README.md            # 本说明文档
├── test_*.py            # 自动化测试文件
└── */                   # 测试子目录
    └── test_*.py        # 子目录中的测试文件
```

## 注意事项

1. 确保已安装 pytest：`poetry add --group dev pytest`
2. 测试文件必须遵循 `test_*.py` 命名约定
3. 测试函数必须以 `test_` 开头
4. 失败的测试不会阻止其他测试的执行
5. 脚本会自动检测运行位置，确保始终测试 tests 目录下的文件
