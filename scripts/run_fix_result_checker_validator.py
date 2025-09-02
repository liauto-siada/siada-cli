#!/usr/bin/env python3
"""
Fix Result Checker Validator 一键执行脚本

用法:
    python scripts/run_fix_result_checker_validator.py

可选参数:
    --csv-path: CSV文件路径
    --output-dir: 输出目录
    --max-workers: 最大并发线程数 (默认: 5)
    --skip-extract: 跳过数据提取，直接使用已有数据
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from siada.foundation.tools.swebench_extractor import SWEBenchExtractor
from siada.foundation.tools.fix_result_checker_validator import FixResultCheckerValidator


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Fix Result Checker Validator 一键执行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 使用默认参数执行完整流程
  python scripts/run_fix_result_checker_validator.py
  
  # 指定自定义CSV文件和输出目录
  python scripts/run_fix_result_checker_validator.py \\
    --csv-path /path/to/your/swebench.csv \\
    --output-dir /path/to/output
  
  # 跳过数据提取，直接验证已有数据
  python scripts/run_fix_result_checker_validator.py \\
    --skip-extract \\
    --output-dir /path/to/existing/data
  
  # 调整并发线程数
  python scripts/run_fix_result_checker_validator.py \\
    --max-workers 10
        """
    )
    
    parser.add_argument(
        "--csv-path",
        default="/Users/caoxin/Projects/AgentHub/siada-agenthub/swebench_test.csv",
        help="SWEBench CSV文件路径 (默认: /Users/caoxin/Projects/AgentHub/siada-agenthub/swebench_test.csv)"
    )
    
    parser.add_argument(
        "--output-dir", 
        default="/Users/caoxin/Projects/latest_agent/logs/checker_validation_auto/",
        help="输出目录路径 (默认: /Users/caoxin/Projects/latest_agent/logs/checker_validation_auto/)"
    )
    
    parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        help="最大并发线程数 (默认: 5)"
    )
    
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="跳过数据提取步骤，直接使用已有数据进行验证"
    )
    
    parser.add_argument(
        "--log-file",
        help="日志文件路径 (默认: validation_YYYYMMDD_HHMMSS.log)"
    )
    
    parser.add_argument(
        "--result-file", 
        help="结果文件路径 (默认: validation_results_YYYYMMDD_HHMMSS.json)"
    )
    
    return parser.parse_args()


def generate_default_filenames():
    """生成默认的日志和结果文件名"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    log_file = f"validation_{timestamp}.log"
    result_file = f"validation_results_{timestamp}.json"
    
    return log_file, result_file


def print_banner():
    """打印欢迎横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                Fix Result Checker Validator                  ║
║                     一键执行工具                             ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def print_step(step_num, title, description=""):
    """打印步骤信息"""
    print(f"\n{'='*60}")
    print(f"步骤 {step_num}: {title}")
    if description:
        print(f"描述: {description}")
    print('='*60)


async def step1_extract_data(args):
    """步骤1: 数据提取"""
    if args.skip_extract:
        print("⏭️  跳过数据提取步骤")
        
        # 检查输出目录是否存在数据
        output_path = Path(args.output_dir)
        if not output_path.exists():
            raise FileNotFoundError(f"输出目录不存在: {output_path}")
        
        # 简单检查是否有数据
        subdirs = [d for d in output_path.iterdir() if d.is_dir()]
        if not subdirs:
            raise FileNotFoundError(f"输出目录中没有找到实例数据: {output_path}")
        
        print(f"✅ 发现 {len(subdirs)} 个实例目录")
        return len(subdirs)
    
    print_step(1, "数据提取", "从SWEBench CSV文件中提取问题描述和修复代码")
    
    print(f"📁 CSV文件路径: {args.csv_path}")
    print(f"📁 输出目录: {args.output_dir}")
    
    # 检查CSV文件是否存在
    if not Path(args.csv_path).exists():
        raise FileNotFoundError(f"CSV文件不存在: {args.csv_path}")
    
    try:
        # 执行数据提取
        print("🔄 开始提取数据...")
        result = SWEBenchExtractor.extract_specific_instances(
            csv_path=args.csv_path,
            output_dir=args.output_dir
        )
        
        print(f"✅ 数据提取完成!")
        print(f"   - 成功提取: {result['extracted_count']}/{result['total_requested']} 个实例")
        print(f"   - 输出目录: {result['output_directory']}")
        
        if result['failed_instances']:
            print(f"⚠️  失败的实例 ({len(result['failed_instances'])}):")
            for failed in result['failed_instances'][:5]:  # 只显示前5个
                print(f"     - {failed}")
            if len(result['failed_instances']) > 5:
                print(f"     ... 还有 {len(result['failed_instances']) - 5} 个失败实例")
        
        return result['extracted_count']
        
    except Exception as e:
        print(f"❌ 数据提取失败: {str(e)}")
        raise


async def step2_validate_results(args, log_file, result_file):
    """步骤2: 修复结果验证"""
    print_step(2, "修复结果验证", "使用AI模型批量分析修复代码的有效性")
    
    print(f"📁 数据目录: {args.output_dir}")
    print(f"🔧 并发线程数: {args.max_workers}")
    print(f"📝 日志文件: {log_file}")
    print(f"📊 结果文件: {result_file}")
    
    try:
        # 创建验证器并执行验证
        print("🔄 开始修复结果验证...")
        validator = FixResultCheckerValidator()
        
        results = await validator.run_validation_concurrent(
            base_dir=args.output_dir,
            max_workers=args.max_workers,
            log_file=log_file,
            output_file=result_file,
            save_to_file=True
        )
        
        return results
        
    except Exception as e:
        print(f"❌ 验证过程失败: {str(e)}")
        raise


def print_summary(results, log_file, result_file):
    """打印结果摘要"""
    print_step(3, "结果摘要")
    
    print(f"📊 验证统计:")
    print(f"   - 总实例数: {results['total_instances']}")
    print(f"   - 成功验证: {results['success_count']} ({results['success_rate']:.1f}%)")
    print(f"   - 警告: {results['warning_count']}")
    print(f"   - 错误: {results['error_count']}")
    
    if 'analysis_statistics' in results:
        stats = results['analysis_statistics']
        print(f"\n🔍 修复分析统计:")
        print(f"   - 修复成功: {stats['fixed_count']}")
        print(f"   - 修复失败: {stats['not_fixed_count']}")
        print(f"   - 修复率: {stats['fix_rate']:.1f}%")
    
    print(f"\n📁 输出文件:")
    print(f"   - 详细日志: {log_file}")
    print(f"   - 结果文件: {result_file}")
    
    # 显示一些成功修复的实例
    if results['success_count'] > 0:
        successful_instances = [
            instance_id for instance_id, result in results['detailed_results'].items()
            if result['status'] == 'success' and result['analysis_result'].get('is_fixed', False)
        ]
        
        if successful_instances:
            print(f"\n✅ 修复成功的实例示例 (前5个):")
            for instance_id in successful_instances[:5]:
                print(f"   - {instance_id}")


async def main():
    """主函数"""
    try:
        # 解析命令行参数
        args = parse_args()
        
        # 打印欢迎信息
        print_banner()
        print("🚀 开始执行 Fix Result Checker Validator 验证流程")
        print(f"⚙️  配置信息:")
        print(f"   - CSV文件: {args.csv_path}")
        print(f"   - 输出目录: {args.output_dir}")
        print(f"   - 并发线程数: {args.max_workers}")
        print(f"   - 跳过提取: {'是' if args.skip_extract else '否'}")
        
        # 生成默认文件名
        log_file, result_file = generate_default_filenames()
        if args.log_file:
            log_file = args.log_file
        if args.result_file:
            result_file = args.result_file
        
        # 步骤1: 数据提取
        extracted_count = await step1_extract_data(args)
        
        # 步骤2: 修复结果验证
        results = await step2_validate_results(args, log_file, result_file)
        
        if results:
            # 步骤3: 结果摘要
            print_summary(results, log_file, result_file)
            
            print(f"\n🎉 验证流程执行完成!")
            print(f"✅ 总体成功率: {results['success_rate']:.1f}%")
            
            if 'analysis_statistics' in results:
                stats = results['analysis_statistics']
                print(f"✅ 修复成功率: {stats['fix_rate']:.1f}%")
        else:
            print(f"\n❌ 验证流程执行失败!")
            return 1
            
    except KeyboardInterrupt:
        print(f"\n\n⚠️  用户中断执行")
        return 1
    except Exception as e:
        print(f"\n❌ 执行过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    # 设置事件循环策略 (避免Windows兼容性问题)
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # 运行主函数
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
