#!/usr/bin/env python3
"""
测试失败分析工具
分析 PASS_TO_PASS 中 success 变为 false 的测试用例，并对比 test_patch.txt 文件
"""

import json
import os
import re
from typing import Dict, List, Set, Tuple
from pathlib import Path
from dataclasses import dataclass


@dataclass
class FailureAnalysisResult:
    """失败分析结果"""
    project_name: str
    failed_tests: List[str]
    success_tests: List[str]
    patch_modified_tests: Set[str]
    patch_affected_failures: List[str]
    patch_unaffected_failures: List[str]
    patch_affected_successes: List[str]
    patch_unaffected_successes: List[str]


class TestFailureAnalyzer:
    """测试失败分析器"""
    
    def __init__(self, gold_path: str):
        self.gold_path = Path(gold_path)
        self.results: List[FailureAnalysisResult] = []
        
    def scan_projects(self) -> List[str]:
        """扫描所有项目文件夹"""
        projects = []
        if not self.gold_path.exists():
            print(f"错误：路径不存在 {self.gold_path}")
            return projects
            
        for item in self.gold_path.iterdir():
            if item.is_dir():
                report_file = item / "report.json"
                if report_file.exists():
                    projects.append(item.name)
        
        print(f"发现 {len(projects)} 个项目文件夹")
        return projects
    
    def parse_report_json(self, project_path: Path) -> Tuple[List[str], List[str]]:
        """解析 report.json 文件，提取 PASS_TO_PASS 中的失败和成功测试用例"""
        report_file = project_path / "report.json"
        failed_tests = []
        success_tests = []
        
        try:
            with open(report_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Get project data (report.json usually contains only one project)
            project_data = list(data.values())[0]
            
            if 'tests_status' in project_data:
                pass_to_pass = project_data['tests_status'].get('PASS_TO_PASS', {})
                failed_tests = pass_to_pass.get('failure', [])
                success_tests = pass_to_pass.get('success', [])
                
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"解析 {report_file} 时出错: {e}")
            
        return failed_tests, success_tests
    
    def parse_test_patch(self, project_path: Path) -> Set[str]:
        """解析 test_patch.txt 文件，提取被修改的测试函数名"""
        patch_file = project_path / "test_patch.txt"
        modified_tests = set()
        
        if not patch_file.exists():
            return modified_tests
            
        try:
            with open(patch_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Regular expression for extracting test function names
            # Match def test_function_name( or +def test_function_name(
            test_function_pattern = r'[+\-]?\s*def\s+(test_\w+)\s*\('
            matches = re.findall(test_function_pattern, content)
            
            for match in matches:
                modified_tests.add(match)
                
            # Also match possible test class methods
            # Match methods under class TestClass
            class_method_pattern = r'[+\-]?\s*def\s+(test_\w+)\s*\(self'
            class_matches = re.findall(class_method_pattern, content)
            
            for match in class_matches:
                modified_tests.add(match)
                
        except Exception as e:
            print(f"解析 {patch_file} 时出错: {e}")
            
        return modified_tests
    
    def extract_test_name(self, full_test_name: str) -> str:
        """从完整的测试名称中提取函数名"""
        # Handle format like "test_file.py::TestClass::test_method"
        if '::' in full_test_name:
            return full_test_name.split('::')[-1]
        
        # Handle format like "test_method"
        if full_test_name.startswith('test_'):
            return full_test_name
            
        # Handle other formats, try to extract parts starting with test_
        test_match = re.search(r'(test_\w+)', full_test_name)
        if test_match:
            return test_match.group(1)
            
        return full_test_name
    
    def analyze_project(self, project_name: str) -> FailureAnalysisResult:
        """分析单个项目"""
        project_path = self.gold_path / project_name
        
        # Get failed and successful test cases
        failed_tests, success_tests = self.parse_report_json(project_path)
        
        # Get tests modified by the patch
        patch_modified_tests = self.parse_test_patch(project_path)
        
        # Analyze which failed tests were affected by the patch
        patch_affected_failures = []
        patch_unaffected_failures = []
        
        for failed_test in failed_tests:
            test_name = self.extract_test_name(failed_test)
            if test_name in patch_modified_tests:
                patch_affected_failures.append(failed_test)
            else:
                patch_unaffected_failures.append(failed_test)
        
        # Analyze which successful tests were affected by the patch
        patch_affected_successes = []
        patch_unaffected_successes = []
        
        for success_test in success_tests:
            test_name = self.extract_test_name(success_test)
            if test_name in patch_modified_tests:
                patch_affected_successes.append(success_test)
            else:
                patch_unaffected_successes.append(success_test)
        
        return FailureAnalysisResult(
            project_name=project_name,
            failed_tests=failed_tests,
            success_tests=success_tests,
            patch_modified_tests=patch_modified_tests,
            patch_affected_failures=patch_affected_failures,
            patch_unaffected_failures=patch_unaffected_failures,
            patch_affected_successes=patch_affected_successes,
            patch_unaffected_successes=patch_unaffected_successes
        )
    
    def run_analysis(self) -> None:
        """运行完整分析"""
        print("开始分析 PASS_TO_PASS 测试用例...")
        print("=" * 60)
        
        projects = self.scan_projects()
        
        if not projects:
            print("未找到任何项目文件夹")
            return
        
        # Analyze each project
        total_failed_tests = 0
        total_success_tests = 0
        projects_with_failures = 0
        projects_with_tests = 0
        total_patch_affected_failures = 0
        total_patch_unaffected_failures = 0
        total_patch_affected_successes = 0
        total_patch_unaffected_successes = 0
        
        for i, project_name in enumerate(projects, 1):
            result = self.analyze_project(project_name)
            self.results.append(result)
            
            # Calculate number of projects with tests
            if result.failed_tests or result.success_tests:
                projects_with_tests += 1
            
            if result.failed_tests:
                projects_with_failures += 1
                
            total_failed_tests += len(result.failed_tests)
            total_success_tests += len(result.success_tests)
            total_patch_affected_failures += len(result.patch_affected_failures)
            total_patch_unaffected_failures += len(result.patch_unaffected_failures)
            total_patch_affected_successes += len(result.patch_affected_successes)
            total_patch_unaffected_successes += len(result.patch_unaffected_successes)
            
            # Show processing progress (every 50 projects)
            if i % 50 == 0:
                print(f"已处理 {i}/{len(projects)} 个项目...")
        
        print(f"处理完成，实际有测试数据的项目: {projects_with_tests}")
        print(f"累计测试总数: 失败 {total_failed_tests} + 成功 {total_success_tests} = {total_failed_tests + total_success_tests}")
        
        # Generate report
        self.generate_report(projects, total_failed_tests, total_success_tests, projects_with_failures, 
                           total_patch_affected_failures, total_patch_unaffected_failures,
                           total_patch_affected_successes, total_patch_unaffected_successes, projects_with_tests)
    
    def generate_report(self, projects: List[str], total_failed_tests: int, total_success_tests: int,
                       projects_with_failures: int, total_patch_affected_failures: int, 
                       total_patch_unaffected_failures: int, total_patch_affected_successes: int,
                       total_patch_unaffected_successes: int, projects_with_tests: int) -> None:
        """生成分析报告"""
        print("\n=== PASS_TO_PASS 测试用例分析报告 ===\n")
        
        # Overall statistics
        print("📊 总体统计：")
        print(f"   扫描项目总数: {len(projects)}")
        print(f"   有失败测试的项目数: {projects_with_failures}")
        print(f"   失败测试用例总数: {total_failed_tests}")
        print(f"   成功测试用例总数: {total_success_tests}")
        print(f"   总测试用例数: {total_failed_tests + total_success_tests}")
        print()
        print("   📋 失败测试补丁影响：")
        print(f"      • 被补丁修改的失败测试: {total_patch_affected_failures}")
        print(f"      • 未被补丁修改的失败测试: {total_patch_unaffected_failures}")
        if total_failed_tests > 0:
            failure_patch_rate = (total_patch_affected_failures / total_failed_tests) * 100
            print(f"      • 失败测试补丁影响率: {failure_patch_rate:.1f}%")
        
        print()
        print("   ✅ 成功测试补丁影响：")
        print(f"      • 被补丁修改的成功测试: {total_patch_affected_successes}")
        print(f"      • 未被补丁修改的成功测试: {total_patch_unaffected_successes}")
        if total_success_tests > 0:
            success_patch_rate = (total_patch_affected_successes / total_success_tests) * 100
            print(f"      • 成功测试补丁影响率: {success_patch_rate:.1f}%")
        
        print("\n" + "=" * 60)
        
        # Detailed analysis - failed tests
        print("\n❌ 失败测试详细分析：")
        
        failure_results = [r for r in self.results if r.failed_tests]
        
        if not failure_results:
            print("   🎉 所有项目的 PASS_TO_PASS 测试都通过了！")
        else:
            for i, result in enumerate(failure_results, 1):
                print(f"\n{i}. 项目: {result.project_name}")
                print(f"   ├── 失败测试数量: {len(result.failed_tests)}")
                
                if result.failed_tests:
                    print("   ├── 失败测试用例:")
                    for test in result.failed_tests:
                        status = "🔧 (被补丁修改)" if test in result.patch_affected_failures else "❌ (未被补丁修改)"
                        print(f"   │   • {test} {status}")
                
                if result.patch_modified_tests:
                    print(f"   ├── 补丁修改的测试函数: {', '.join(sorted(result.patch_modified_tests))}")
                
                patch_affected_count = len(result.patch_affected_failures)
                total_failures = len(result.failed_tests)
                if total_failures > 0:
                    impact_rate = (patch_affected_count / total_failures) * 100
                    print(f"   └── 补丁影响: {patch_affected_count}/{total_failures} ({impact_rate:.1f}%)")
        
        print("\n" + "=" * 60)
        
        # Detailed analysis - successful tests modified by patch
        print("\n✅ 成功测试中被补丁修改的分析：")
        
        success_patch_results = [r for r in self.results if r.patch_affected_successes]
        
        if not success_patch_results:
            print("   📝 没有成功测试被补丁修改")
        else:
            for i, result in enumerate(success_patch_results, 1):
                print(f"\n{i}. 项目: {result.project_name}")
                print(f"   ├── 被补丁修改的成功测试数量: {len(result.patch_affected_successes)}")
                print(f"   ├── 总成功测试数量: {len(result.success_tests)}")
                
                if result.patch_affected_successes:
                    print("   ├── 被补丁修改的成功测试用例:")
                    for test in result.patch_affected_successes[:10]:  # Limit display to first 10
                        print(f"   │   • {test}")
                    if len(result.patch_affected_successes) > 10:
                        print(f"   │   ... 还有 {len(result.patch_affected_successes) - 10} 个")
                
                success_count = len(result.success_tests)
                patch_success_count = len(result.patch_affected_successes)
                if success_count > 0:
                    success_rate = (patch_success_count / success_count) * 100
                    print(f"   └── 成功测试补丁影响: {patch_success_count}/{success_count} ({success_rate:.1f}%)")
        
        print("\n" + "=" * 60)
        print("\n📈 总体补丁影响统计：")
        print(f"   ❌ 失败测试:")
        print(f"      • 被补丁修改: {total_patch_affected_failures} 个")
        print(f"      • 未被补丁修改: {total_patch_unaffected_failures} 个")
        
        print(f"   ✅ 成功测试:")
        print(f"      • 被补丁修改: {total_patch_affected_successes} 个")
        print(f"      • 未被补丁修改: {total_patch_unaffected_successes} 个")
        
        total_tests = total_failed_tests + total_success_tests
        total_patch_affected = total_patch_affected_failures + total_patch_affected_successes
        
        if total_tests > 0:
            print(f"\n   📊 整体补丁影响率: {(total_patch_affected / total_tests) * 100:.1f}%")
            print(f"   🔧 补丁相关测试总数: {total_patch_affected} / {total_tests}")


def main():
    """主函数"""
    # Target path
    gold_path = "/Users/caoxin/Projects/latest_agent/logs/checker_link/gold"
    
    analyzer = TestFailureAnalyzer(gold_path)
    analyzer.run_analysis()


if __name__ == "__main__":
    main()
