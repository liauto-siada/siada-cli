# Fix Result Checker Validator 使用说明

## 概述

`fix_result_checker_validator` 是一个用于验证修复结果检查器性能的工具系统。该系统包含两个主要步骤：

1. **swebench_extractor** 从CSV中提取problem描述和patch代码
2. **并发执行** 让fix_result_checker对problem描述和patch.diff进行修复有效性判断

## 一键执行

### 基本用法

```bash
# 使用默认参数执行完整流程
python scripts/run_fix_result_checker_validator.py
```

### 常用参数

```bash
# 指定自定义CSV文件和输出目录
python scripts/run_fix_result_checker_validator.py \
    --csv-path /home/ops/agenthub_for_swebench/swe-bench/swebench_test.csv \
    --output-dir /home/ops/agenthub_for_swebench/swe-bench/logs/run_evaluation/django_10_checker_agent_0801_logs/gold/ > test1.log



# 跳过数据提取，直接验证已有数据
python scripts/run_fix_result_checker_validator.py \
    --skip-extract \
    --output-dir /path/to/existing/data

python scripts/run_fix_result_checker_validator.py \
   --skip-extract \
    --output-dir /Users/caoxin/Projects/latest_agent/logs/9_django_checker_819_choose_05/gold/ > test2.log

# 调整并发线程数
python scripts/run_fix_result_checker_validator.py \
    --max-workers 10
```

### 完整参数列表

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--csv-path` | SWEBench CSV文件路径 | `/Users/caoxin/Projects/AgentHub/siada-agenthub/swebench_test.csv` |
| `--output-dir` | 输出目录路径 | `/Users/caoxin/Projects/latest_agent/logs/checker_validation_auto/` |
| `--max-workers` | 最大并发线程数 | `5` |
| `--skip-extract` | 跳过数据提取步骤 | `False` |
| `--log-file` | 日志文件路径 | `validation_YYYYMMDD_HHMMSS.log` |
| `--result-file` | 结果文件路径 | `validation_results_YYYYMMDD_HHMMSS.json` |

## 工作流程

### 步骤1: 数据提取
- **智能扫描**: 自动扫描`output_dir`目录中已有的文件夹名称作为instance_id列表
- **动态提取**: 从SWEBench CSV文件中提取对应实例的数据
- **文件生成**: 生成目录结构：`output_dir/instance_id/problem_statement.txt`
- **完整数据**: 同时提取patch.txt和test_patch.txt

### 步骤2: 并发验证
- 并发调用fix_result_checker分析每个实例
- 使用AI模型进行七步系统性分析
- 生成修复有效性判断结果

### 步骤3: 结果汇总
- 统计成功率、修复率等指标
- 生成详细日志和JSON结果文件

## 数据提取机制

系统支持两种数据提取模式：

### 1. 基于目录扫描（推荐）
```bash
# 创建目录结构，系统会自动扫描文件夹名称
mkdir -p /path/to/output/django__django-12308
mkdir -p /path/to/output/matplotlib__matplotlib-23476

# 执行提取，系统会根据文件夹名称提取对应数据
python scripts/run_fix_result_checker_validator.py \
    --output-dir /path/to/output
```

### 2. 跳过提取，直接验证
```bash
# 如果数据已经存在，直接验证
python scripts/run_fix_result_checker_validator.py \
    --skip-extract \
    --output-dir /path/to/existing/data
```

## 输出文件

### 日志文件示例
```
[2025-09-03 09:40:39] 开始验证实例: django__django-12308
[2025-09-03 09:40:45] 分析完成 - django__django-12308: 修复状态=True
[2025-09-03 09:40:45] 检查摘要 - django__django-12308: 修复已完全解决核心问题
```

### JSON结果文件结构
```json
{
  "total_instances": 80,
  "success_count": 75,
  "success_rate": 93.75,
  "analysis_statistics": {
    "fixed_count": 45,
    "not_fixed_count": 30,
    "fix_rate": 60.0
  },
  "detailed_results": {
    "instance_id": {
      "status": "success",
      "analysis_result": {
        "is_fixed": true,
        "check_summary": "修复摘要",
        "analysis": "详细分析"
      }
    }
  }
}
```

## 快速开始

1. **准备环境**
   ```bash
   # 确保已安装依赖
   pip install -r requirements.txt
   ```

2. **执行验证**
   ```bash
   # 使用默认配置执行
   python scripts/run_fix_result_checker_validator.py
   ```

3. **查看结果**
   ```bash
   # 检查生成的日志和结果文件
   ls validation_*.log validation_results_*.json
   ```

## 性能建议

- **并发线程数**: 建议设置为CPU核数的1-2倍
- **内存使用**: 每个线程约需要200-500MB内存
- **处理时间**: 每个实例平均需要30-60秒

## 故障排除

1. **CSV文件不存在**
   ```
   确保CSV文件路径正确且文件存在
   ```

2. **内存不足**
   ```
   减少--max-workers参数值
   ```

3. **API访问错误**
   ```
   检查AI模型配置和访问权限
   ```

## 示例执行输出

```
╔══════════════════════════════════════════════════════════════╗
║                Fix Result Checker Validator                  ║
║                     一键执行工具                             ║
╚══════════════════════════════════════════════════════════════╝

🚀 开始执行 Fix Result Checker Validator 验证流程
⚙️  配置信息:
   - CSV文件: /path/to/swebench_test.csv
   - 输出目录: /path/to/output/
   - 并发线程数: 5
   - 跳过提取: 否

============================================================
步骤 1: 数据提取
描述: 从SWEBench CSV文件中提取问题描述和修复代码
============================================================
✅ 数据提取完成!
   - 成功提取: 80/80 个实例

============================================================
步骤 2: 修复结果验证  
描述: 使用AI模型批量分析修复代码的有效性
============================================================
✅ 验证完成!

============================================================
步骤 3: 结果摘要
============================================================
📊 验证统计:
   - 总实例数: 80
   - 成功验证: 75 (93.8%)
   - 警告: 3
   - 错误: 2

🔍 修复分析统计:
   - 修复成功: 45
   - 修复失败: 30
   - 修复率: 60.0%

🎉 验证流程执行完成!
✅ 总体成功率: 93.8%
✅ 修复成功率: 60.0%
