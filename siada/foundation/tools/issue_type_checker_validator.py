import re
import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
import threading
from datetime import datetime

from siada.services.issue_type_checker import IssueTypeChecker


class IssueTypeCheckerValidator:
    """Issue Type Checker验证工具，用于验证分析issue_type_checker的结果。"""

    def __init__(self):
        self.issue_type_checker = IssueTypeChecker()
        self.output_lock = threading.Lock()
        self.output_file = None

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
        验证单个实例的issue_type_checker结果。
        
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
        
        # 创建context，参考TestAnomalyCheckerRealMethod
        class SimpleContext:
            def __init__(self):
                self.provider = "li"
        
        context = SimpleContext()
        
        try:
            self.log_to_file(f"开始调用IssueTypeChecker分析 - {instance_id}")
            
            # 调用issue_type_checker进行分析
            result = await self.issue_type_checker.analyze_issue_type(
                issue_desc=problem_statement,
                context=context
            )
            
            # 调用项目类型分析
            project_result = await self.issue_type_checker.analyze_project_type(
                issue_desc=problem_statement,
                context=context
            )
            
            issue_type = result.get("issue_type", "unknown")
            complexity = result.get("complexity", "unknown")
            confidence = result.get("confidence", 0.0)
            analysis = result.get("analysis", "")
            key_indicators = result.get("key_indicators", [])
            
            project_type = project_result.get("project_type", "unknown")
            project_confidence = project_result.get("confidence", 0.0)
            
            self.log_to_file(f"分析完成 - {instance_id}: 类型={issue_type}, 复杂度={complexity}, 置信度={confidence:.2f}")
            self.log_to_file(f"项目类型 - {instance_id}: {project_type}, 置信度={project_confidence:.2f}")
            self.log_to_file(f"关键指标 - {instance_id}: {len(key_indicators)}个指标")
            self.log_to_file(f"分析摘要 - {instance_id}: {analysis[:150]}...")
            
            return {
                "instance_id": instance_id,
                "status": "success",
                "problem_statement_length": len(problem_statement),
                "problem_statement": problem_statement,
                "analysis_result": result,
                "project_analysis_result": project_result
            }
            
        except Exception as e:
            error_msg = f"issue_type_checker分析失败: {str(e)}"
            self.log_to_file(f"错误 - {instance_id}: {error_msg}")
            return {
                "instance_id": instance_id,
                "status": "error",
                "error": error_msg,
                "problem_statement_length": len(problem_statement)
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
        使用ThreadPoolExecutor并发验证所有实例的issue_type_checker结果。
        
        Args:
            base_dir: 基础目录路径
            max_workers: 最大并发线程数
            
        Returns:
            Dict[str, Any]: 所有实例的验证结果汇总
        """
        # 动态读取目录中的所有实例
        base_path = Path(base_dir)
        if not base_path.exists():
            raise FileNotFoundError(f"基础目录不存在: {base_dir}")
        
        target_instances = []
        for item in base_path.iterdir():
            if item.is_dir() and (item / "problem_statement.txt").exists():
                target_instances.append(item.name)
        
        target_instances.sort()  # 排序以便一致的处理顺序
        
        print(f"开始并发验证 {len(target_instances)} 个实例的issue_type_checker结果...")
        print(f"基础目录: {base_dir}")
        print(f"并发线程数: {max_workers}")
        print("-" * 80)
        
        self.log_to_file(f"开始并发验证 {len(target_instances)} 个实例，使用 {max_workers} 个线程")
        
        results = {}
        success_count = 0
        error_count = 0
        
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
                        issue_type = analysis.get("issue_type", "unknown")
                        complexity = analysis.get("complexity", "unknown")
                        confidence = analysis.get("confidence", 0.0)
                        print(f"[{completed_count}/{len(target_instances)}] ✓ 成功 - {instance_id}: {issue_type}, {complexity}, {confidence:.2f}")
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
        
        # 分析成功的实例
        successful_results = [r for r in results.values() if r["status"] == "success"]
        
        # 统计问题类型
        bug_fix_count = sum(1 for r in successful_results if r["analysis_result"].get("issue_type") == "bug_fix")
        feature_request_count = sum(1 for r in successful_results if r["analysis_result"].get("issue_type") == "feature_request")
        unknown_count = sum(1 for r in successful_results if r["analysis_result"].get("issue_type") == "unknown")
        
        # 统计复杂度
        simple_count = sum(1 for r in successful_results if r["analysis_result"].get("complexity") == "simple")
        medium_count = sum(1 for r in successful_results if r["analysis_result"].get("complexity") == "medium")
        complex_count = sum(1 for r in successful_results if r["analysis_result"].get("complexity") == "complex")
        
        # 统计置信度
        confidences = [r["analysis_result"].get("confidence", 0.0) for r in successful_results]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        # 统计项目类型
        project_types = {}
        project_confidences = []
        for r in successful_results:
            if "project_analysis_result" in r:
                project_type = r["project_analysis_result"].get("project_type", "unknown")
                project_confidence = r["project_analysis_result"].get("confidence", 0.0)
                project_types[project_type] = project_types.get(project_type, 0) + 1
                project_confidences.append(project_confidence)
        
        avg_project_confidence = sum(project_confidences) / len(project_confidences) if project_confidences else 0.0
        
        # 生成汇总统计
        summary = {
            "total_instances": len(target_instances),
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": success_count / len(target_instances) * 100,
            "detailed_results": results
        }
        
        if success_count > 0:
            summary.update({
                "analysis_statistics": {
                    "issue_type_distribution": {
                        "bug_fix": bug_fix_count,
                        "feature_request": feature_request_count,
                        "unknown": unknown_count
                    },
                    "complexity_distribution": {
                        "simple": simple_count,
                        "medium": medium_count,
                        "complex": complex_count
                    },
                    "project_type_distribution": project_types,
                    "confidence_stats": {
                        "average_confidence": avg_confidence,
                        "min_confidence": min(confidences) if confidences else 0.0,
                        "max_confidence": max(confidences) if confidences else 0.0,
                        "average_project_confidence": avg_project_confidence,
                        "min_project_confidence": min(project_confidences) if project_confidences else 0.0,
                        "max_project_confidence": max(project_confidences) if project_confidences else 0.0
                    }
                }
            })
        
        print("\n" + "=" * 80)
        print("验证结果汇总:")
        print(f"总实例数: {summary['total_instances']}")
        print(f"成功验证: {summary['success_count']} ({summary['success_rate']:.1f}%)")
        print(f"错误: {summary['error_count']}")
        
        if "analysis_statistics" in summary:
            stats = summary["analysis_statistics"]
            print(f"\n问题类型分析:")
            print(f"Bug修复: {stats['issue_type_distribution']['bug_fix']}")
            print(f"功能需求: {stats['issue_type_distribution']['feature_request']}")
            print(f"未知类型: {stats['issue_type_distribution']['unknown']}")
            
            print(f"\n复杂度分析:")
            print(f"简单: {stats['complexity_distribution']['simple']}")
            print(f"中等: {stats['complexity_distribution']['medium']}")
            print(f"复杂: {stats['complexity_distribution']['complex']}")
            
            print(f"\n项目类型分析:")
            for project_type, count in stats['project_type_distribution'].items():
                print(f"{project_type}: {count}")
            
            print(f"\n置信度统计:")
            print(f"问题类型平均置信度: {stats['confidence_stats']['average_confidence']:.3f}")
            print(f"问题类型置信度范围: {stats['confidence_stats']['min_confidence']:.3f} - {stats['confidence_stats']['max_confidence']:.3f}")
            print(f"项目类型平均置信度: {stats['confidence_stats']['average_project_confidence']:.3f}")
            print(f"项目类型置信度范围: {stats['confidence_stats']['min_project_confidence']:.3f} - {stats['confidence_stats']['max_project_confidence']:.3f}")
        
        self.log_to_file(f"验证完成 - 总数: {summary['total_instances']}, 成功: {summary['success_count']}, 错误: {summary['error_count']}")
        
        return summary

    # 保持原有的串行方法作为备选
    async def validate_all_instances(
        self, 
        base_dir: str = "/Users/caoxin/Projects/latest_agent/logs/checker_link/gold/"
    ) -> Dict[str, Any]:
        """
        串行验证所有30个实例的issue_type_checker结果（备选方法）。
        """
        return await self.validate_all_instances_concurrent(base_dir, max_workers=1)

    def save_results_to_file(self, results: Dict[str, Any], output_file: str = "issue_type_validation_results.json"):
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
        output_file: str = "issue_type_validation_results.json",
        log_file: str = "issue_type_validation_log.txt",
        max_workers: int = 5
    ):
        """
        运行完整的并发验证流程，支持txt日志输出。
        
        Args:
            base_dir: 基础目录路径
            save_to_file: 是否保存结果到文件
            output_file: 输出文件路径
            log_file: 日志文件路径
            max_workers: 最大并发线程数
        """
        # 打开日志文件
        try:
            self.output_file = open(log_file, 'w', encoding='utf-8')
            self.log_to_file("=" * 80)
            self.log_to_file("Issue Type Checker 验证开始")
            self.log_to_file(f"基础目录: {base_dir}")
            self.log_to_file(f"并发线程数: {max_workers}")
            self.log_to_file("=" * 80)
            
            results = await self.validate_all_instances_concurrent(base_dir, max_workers)
            
            # 记录汇总结果到日志文件
            self.log_to_file("=" * 80)
            self.log_to_file("验证结果汇总:")
            self.log_to_file(f"总实例数: {results['total_instances']}")
            self.log_to_file(f"成功验证: {results['success_count']} ({results['success_rate']:.1f}%)")
            self.log_to_file(f"错误: {results['error_count']}")
            
            if "analysis_statistics" in results:
                stats = results["analysis_statistics"]
                self.log_to_file(f"Bug修复: {stats['issue_type_distribution']['bug_fix']}")
                self.log_to_file(f"功能需求: {stats['issue_type_distribution']['feature_request']}")
                self.log_to_file(f"平均置信度: {stats['confidence_stats']['average_confidence']:.3f}")
            
            self.log_to_file("=" * 80)
            self.log_to_file("Issue Type Checker 验证完成")
            
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
        output_file: str = "issue_type_validation_results.json"
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
        validator = IssueTypeCheckerValidator()
        # 使用并发验证，5个线程
        await validator.run_validation_concurrent(max_workers=5)
    
    # 运行验证
    asyncio.run(main())
