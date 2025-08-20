import re
import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
import threading
from datetime import datetime

from siada.services.fix_result_check import FixResultChecker


class FixResultCheckerValidator:
    """Fix Result Checker验证工具，用于验证分析fix_result_checker的结果。"""

    def __init__(self):
        self.fix_result_checker = FixResultChecker()
        self.output_lock = threading.Lock()
        self.output_file = None

    @staticmethod
    def filter_patch_exclude_tests(patch_content: str) -> str:
        """
        从patch内容中过滤掉测试文件相关的修改，类似于get_git_diff_exclude_test_files的逻辑。
        
        Args:
            patch_content: 原始patch内容
            
        Returns:
            str: 过滤后的patch内容
        """
        if not patch_content:
            return ""
        
        lines = patch_content.split('\n')
        filtered_lines = []
        current_file = None
        skip_current_file = False
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 检查是否是新文件的开始
            if line.startswith('diff --git'):
                # 提取文件路径
                match = re.search(r'diff --git a/(.*?) b/', line)
                if match:
                    current_file = match.group(1)
                    # 判断是否是测试文件
                    skip_current_file = (
                        'test' in current_file.lower() or
                        current_file.startswith('tests/') or
                        '/test' in current_file or
                        current_file.endswith('_test.py') or
                        current_file.endswith('test.py') or
                        current_file.endswith('_tests.py') or
                        'test_' in current_file
                    )
                else:
                    skip_current_file = False
                
                if not skip_current_file:
                    filtered_lines.append(line)
            elif not skip_current_file:
                filtered_lines.append(line)
            
            i += 1
        
        filtered_content = '\n'.join(filtered_lines)
        
        # 如果过滤后内容为空或只有很少内容，尝试保留src/目录的修改
        if not filtered_content.strip() or len(filtered_content.strip()) < 50:
            # 重新处理，只保留src/目录的修改
            lines = patch_content.split('\n')
            src_lines = []
            current_file = None
            include_current_file = False
            
            for line in lines:
                if line.startswith('diff --git'):
                    match = re.search(r'diff --git a/(.*?) b/', line)
                    if match:
                        current_file = match.group(1)
                        include_current_file = current_file.startswith('src/')
                    else:
                        include_current_file = False
                    
                    if include_current_file:
                        src_lines.append(line)
                elif include_current_file:
                    src_lines.append(line)
            
            if src_lines:
                filtered_content = '\n'.join(src_lines)
        
        return filtered_content

    def log_to_file(self, message: str):
        """线程安全地写入日志文件，确保每行不超过100个字符"""
        if self.output_file:
            with self.output_lock:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                prefix = f"[{timestamp}] "
                max_content_length = 100 - len(prefix)
                
                # 如果消息太长，分行处理
                if len(message) <= max_content_length:
                    self.output_file.write(f"{prefix}{message}\n")
                else:
                    # 分割长消息
                    words = message.split(' ')
                    current_line = ""
                    
                    for word in words:
                        if len(current_line + word + " ") <= max_content_length:
                            current_line += word + " "
                        else:
                            if current_line:
                                self.output_file.write(f"{prefix}{current_line.strip()}\n")
                                prefix = " " * len(f"[{timestamp}] ")  # 后续行使用空格对齐
                                current_line = word + " "
                            else:
                                # 单个词太长，强制截断
                                self.output_file.write(f"{prefix}{word[:max_content_length]}\n")
                                prefix = " " * len(f"[{timestamp}] ")
                                current_line = ""
                    
                    if current_line:
                        self.output_file.write(f"{prefix}{current_line.strip()}\n")
                
                self.output_file.flush()

    async def validate_single_instance(
        self, 
        instance_id: str, 
        base_dir: str = "/Users/caoxin/Projects/latest_agent/logs/checker_link/gold/"
    ) -> Dict[str, Any]:
        """
        验证单个实例的fix_result_checker结果。
        
        Args:
            instance_id: 实例ID
            base_dir: 基础目录路径
            
        Returns:
            Dict[str, Any]: 验证结果
        """
        self.log_to_file(f"开始验证实例: {instance_id}")
        
        instance_dir = Path(base_dir) / instance_id
        
        if not instance_dir.exists():
            error_msg = f"实例目录不存在: {instance_dir}"
            self.log_to_file(f"错误 - {instance_id}: {error_msg}")
            return {
                "instance_id": instance_id,
                "status": "error",
                "error": error_msg
            }
        
        # 读取problem_statement.txt
        problem_file = instance_dir / "problem_statement.txt"
        if not problem_file.exists():
            error_msg = f"problem_statement.txt文件不存在: {problem_file}"
            self.log_to_file(f"错误 - {instance_id}: {error_msg}")
            return {
                "instance_id": instance_id,
                "status": "error",
                "error": error_msg
            }
        
        try:
            with open(problem_file, 'r', encoding='utf-8') as f:
                problem_statement = f.read().strip()
        except Exception as e:
            error_msg = f"读取problem_statement.txt失败: {str(e)}"
            self.log_to_file(f"错误 - {instance_id}: {error_msg}")
            return {
                "instance_id": instance_id,
                "status": "error",
                "error": error_msg
            }
        
        # 读取patch.diff
        patch_file = instance_dir / "patch.diff"
        if not patch_file.exists():
            error_msg = f"patch.diff文件不存在: {patch_file}"
            self.log_to_file(f"错误 - {instance_id}: {error_msg}")
            return {
                "instance_id": instance_id,
                "status": "error",
                "error": error_msg
            }
        
        try:
            with open(patch_file, 'r', encoding='utf-8') as f:
                patch_content = f.read().strip()
        except Exception as e:
            error_msg = f"读取patch.diff失败: {str(e)}"
            self.log_to_file(f"错误 - {instance_id}: {error_msg}")
            return {
                "instance_id": instance_id,
                "status": "error",
                "error": error_msg
            }
        
        # 过滤掉测试文件
        filtered_patch = self.filter_patch_exclude_tests(patch_content)
        
        if not filtered_patch.strip():
            warning_msg = "过滤后的patch内容为空，可能只包含测试文件修改"
            self.log_to_file(f"警告 - {instance_id}: {warning_msg}")
            return {
                "instance_id": instance_id,
                "status": "warning",
                "warning": warning_msg,
                "original_patch_size": len(patch_content),
                "filtered_patch_size": 0
            }
        
        # 创建context，参考TestAnomalyCheckerRealMethod
        class SimpleContext:
            def __init__(self):
                self.provider = "li"
        
        context = SimpleContext()
        
        try:
            self.log_to_file(f"开始调用FixResultChecker分析 - {instance_id}")
            
            # 调用fix_result_checker进行分析，使用正确的方法
            result = await self.fix_result_checker.check(
                issue_desc=problem_statement,
                fix_code=filtered_patch,
                context=context
            )
            
            is_fixed = result.get("is_fixed", False)
            check_summary = result.get("check_summary", "")
            analysis = result.get("analysis", "")
            
            self.log_to_file(f"分析完成 - {instance_id}: 修复状态={is_fixed}")
            self.log_to_file(f"检查摘要 - {instance_id}: {check_summary}")
            self.log_to_file(f"详细分析 - {instance_id}: {analysis[:200]}...")
            
            return {
                "instance_id": instance_id,
                "status": "success",
                "problem_statement_length": len(problem_statement),
                "original_patch_size": len(patch_content),
                "filtered_patch_size": len(filtered_patch),
                "problem_statement": problem_statement,
                "filtered_patch": filtered_patch,
                "analysis_result": result
            }
            
        except Exception as e:
            error_msg = f"fix_result_checker分析失败: {str(e)}"
            self.log_to_file(f"错误 - {instance_id}: {error_msg}")
            return {
                "instance_id": instance_id,
                "status": "error",
                "error": error_msg,
                "problem_statement_length": len(problem_statement),
                "original_patch_size": len(patch_content),
                "filtered_patch_size": len(filtered_patch)
            }

    async def validate_instance_wrapper(self, instance_id: str, base_dir: str) -> Dict[str, Any]:
        """包装器函数，用于线程池执行"""
        return await self.validate_single_instance(instance_id, base_dir)

    async def validate_all_instances_concurrent(
        self, 
        base_dir: str = "/Users/caoxin/Projects/latest_agent/logs/checker_link/gold/",
        max_workers: int = 5
    ) -> Dict[str, Any]:
        """
        使用ThreadPoolExecutor并发验证所有30个实例的fix_result_checker结果。
        
        Args:
            base_dir: 基础目录路径
            max_workers: 最大并发线程数
            
        Returns:
            Dict[str, Any]: 所有实例的验证结果汇总
        """
        # 预定义的30个instance_id
        target_instances = [
            "django__django-12308",
            "django__django-12747", 
            "django__django-13321",
            "django__django-13448",
            "django__django-14016",
            "django__django-15061",
            "django__django-15202",
            "django__django-15320",
            "django__django-15388",
            "django__django-15781",
            "matplotlib__matplotlib-23476",
            "matplotlib__matplotlib-23987",
            "matplotlib__matplotlib-24265",
            "matplotlib__matplotlib-26011",
            "mwaskom__seaborn-2848",
            "pallets__flask-4045",
            "psf__requests-2317",
            "psf__requests-2674",
            "pylint-dev__pylint-6506",
            "scikit-learn__scikit-learn-13497",
            "scikit-learn__scikit-learn-25500",
            "sphinx-doc__sphinx-10451",
            "sympy__sympy-12454",
            "sympy__sympy-13437",
            "sympy__sympy-13971",
            "sympy__sympy-14774",
            "sympy__sympy-18835",
            "sympy__sympy-21379",
            "sympy__sympy-22840",
            "sympy__sympy-24909"
        ]
        
        print(f"开始并发验证 {len(target_instances)} 个实例的fix_result_checker结果...")
        print(f"基础目录: {base_dir}")
        print(f"并发线程数: {max_workers}")
        print("-" * 80)
        
        self.log_to_file(f"开始并发验证 {len(target_instances)} 个实例，使用 {max_workers} 个线程")
        
        results = {}
        success_count = 0
        error_count = 0
        warning_count = 0
        
        # 使用ThreadPoolExecutor进行并发处理
        loop = asyncio.get_event_loop()
        
        def run_validation_sync(instance_id: str) -> Dict[str, Any]:
            """同步包装器，在线程池中运行异步验证"""
            try:
                # 在新的事件循环中运行异步函数
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        self.validate_single_instance(instance_id, base_dir)
                    )
                finally:
                    new_loop.close()
            except Exception as e:
                return {
                    "instance_id": instance_id,
                    "status": "error",
                    "error": f"线程执行异常: {str(e)}"
                }
        
        # 使用ThreadPoolExecutor执行任务
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_instance = {
                executor.submit(run_validation_sync, instance_id): instance_id 
                for instance_id in target_instances
            }
            
            # 收集结果
            completed_count = 0
            for future in future_to_instance:
                instance_id = future_to_instance[future]
                completed_count += 1
                
                try:
                    result = future.result()
                    results[instance_id] = result
                    
                    if result["status"] == "success":
                        success_count += 1
                        analysis = result["analysis_result"]
                        is_fixed = analysis.get("is_fixed", False)
                        print(f"[{completed_count}/{len(target_instances)}] ✓ 成功 - {instance_id}: 修复状态={is_fixed}")
                    elif result["status"] == "warning":
                        warning_count += 1
                        print(f"[{completed_count}/{len(target_instances)}] ⚠ 警告 - {instance_id}: {result.get('warning', '未知警告')}")
                    else:
                        error_count += 1
                        print(f"[{completed_count}/{len(target_instances)}] ✗ 错误 - {instance_id}: {result.get('error', '未知错误')}")
                        
                except Exception as e:
                    error_count += 1
                    error_msg = f"线程执行异常: {str(e)}"
                    results[instance_id] = {
                        "instance_id": instance_id,
                        "status": "error",
                        "error": error_msg
                    }
                    print(f"[{completed_count}/{len(target_instances)}] ✗ 异常 - {instance_id}: {error_msg}")
                    self.log_to_file(f"异常 - {instance_id}: {error_msg}")
        
        # 生成汇总统计
        summary = {
            "total_instances": len(target_instances),
            "success_count": success_count,
            "warning_count": warning_count,
            "error_count": error_count,
            "success_rate": success_count / len(target_instances) * 100,
            "detailed_results": results
        }
        
        # 分析成功的实例
        if success_count > 0:
            successful_results = [r for r in results.values() if r["status"] == "success"]
            
            # 统计修复状态
            fixed_count = sum(1 for r in successful_results if r["analysis_result"].get("is_fixed", False))
            not_fixed_count = success_count - fixed_count
            
            summary.update({
                "analysis_statistics": {
                    "fixed_count": fixed_count,
                    "not_fixed_count": not_fixed_count,
                    "fix_rate": fixed_count / success_count * 100 if success_count > 0 else 0
                }
            })
        
        print("\n" + "=" * 80)
        print("验证结果汇总:")
        print(f"总实例数: {summary['total_instances']}")
        print(f"成功验证: {summary['success_count']} ({summary['success_rate']:.1f}%)")
        print(f"警告: {summary['warning_count']}")
        print(f"错误: {summary['error_count']}")
        
        if "analysis_statistics" in summary:
            stats = summary["analysis_statistics"]
            print(f"\n分析统计:")
            print(f"修复成功: {stats['fixed_count']}/{success_count} ({stats['fix_rate']:.1f}%)")
        
        self.log_to_file(f"验证完成 - 总数: {summary['total_instances']}, 成功: {summary['success_count']}, 警告: {summary['warning_count']}, 错误: {summary['error_count']}")
        
        return summary

    # 保持原有的串行方法作为备选
    async def validate_all_instances(
        self, 
        base_dir: str = "/Users/caoxin/Projects/latest_agent/logs/checker_link/gold/"
    ) -> Dict[str, Any]:
        """
        串行验证所有30个实例的fix_result_checker结果（备选方法）。
        """
        return await self.validate_all_instances_concurrent(base_dir, max_workers=1)

    def save_results_to_file(self, results: Dict[str, Any], output_file: str = "validation_results.json"):
        """
        将验证结果保存到文件。
        
        Args:
            results: 验证结果
            output_file: 输出文件路径
        """
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n验证结果已保存到: {output_file}")
        except Exception as e:
            print(f"保存结果失败: {str(e)}")

    async def run_validation_concurrent(
        self, 
        base_dir: str = "/Users/caoxin/Projects/latest_agent/logs/checker_link/gold/",
        save_to_file: bool = True,
        output_file: str = "validation_results.json",
        log_file: str = "validation_log.txt",
        max_workers: int = 5
    ):
        """
        运行完整的并发验证流程，txt日志输出。
        
        Args:
            base_dir: 基础目录路径
            save_to_file: 是否保存结果到文件
            output_file: 输出文件路径
            log_file: 日志文件路径
            max_workers: 最大并发线程数
        """
        try:
            self.output_file = open(log_file, 'w', encoding='utf-8')
            self.log_to_file("=" * 80)
            self.log_to_file("Fix Result Checker 验证开始")
            self.log_to_file(f"基础目录: {base_dir}")
            self.log_to_file(f"并发线程数: {max_workers}")
            self.log_to_file("=" * 80)
            
            results = await self.validate_all_instances_concurrent(base_dir, max_workers)
            
            # 记录汇总结果到日志文件
            self.log_to_file("=" * 80)
            self.log_to_file("验证结果汇总:")
            self.log_to_file(f"总实例数: {results['total_instances']}")
            self.log_to_file(f"成功验证: {results['success_count']} ({results['success_rate']:.1f}%)")
            self.log_to_file(f"警告: {results['warning_count']}")
            self.log_to_file(f"错误: {results['error_count']}")
            
            if "analysis_statistics" in results:
                stats = results["analysis_statistics"]
                self.log_to_file(f"修复成功: {stats['fixed_count']}/{results['success_count']} ({stats['fix_rate']:.1f}%)")
            
            self.log_to_file("=" * 80)
            self.log_to_file("Fix Result Checker 验证完成")
            
            if save_to_file:
                self.save_results_to_file(results, output_file)
            
            return results
            
        except Exception as e:
            error_msg = f"验证过程发生错误: {str(e)}"
            print(error_msg)
            if self.output_file:
                self.log_to_file(f"错误: {error_msg}")
            return None
        finally:
            # 关闭日志文件
            if self.output_file:
                self.output_file.close()
                self.output_file = None
                print(f"\n详细日志已保存到: {log_file}")

    async def run_validation(
        self, 
        base_dir: str = "/Users/caoxin/Projects/latest_agent/logs/checker_link/gold/",
        save_to_file: bool = True,
        output_file: str = "validation_results.json"
    ):
        """
        运行完整的验证流程（串行版本）。
        
        Args:
            base_dir: 基础目录路径
            save_to_file: 是否保存结果到文件
            output_file: 输出文件路径
        """
        return await self.run_validation_concurrent(
            base_dir=base_dir,
            save_to_file=save_to_file,
            output_file=output_file,
            max_workers=1
        )


# Example usage
if __name__ == "__main__":
    async def main():
        validator = FixResultCheckerValidator()
        await validator.run_validation_concurrent(max_workers=5)
    
    asyncio.run(main())
