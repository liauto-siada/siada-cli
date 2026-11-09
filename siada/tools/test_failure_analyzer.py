#!/usr/bin/env python3
"""
Analyze failed PASS_TO_PASS tests and compare them with test_patch.txt.
"""

import json
import argparse
import os
import re
from typing import Dict, List, Set, Tuple
from pathlib import Path
from dataclasses import dataclass


@dataclass
class FailureAnalysisResult:
    """Failure analysis result."""
    project_name: str
    failed_tests: List[str]
    success_tests: List[str]
    patch_modified_tests: Set[str]
    patch_affected_failures: List[str]
    patch_unaffected_failures: List[str]
    patch_affected_successes: List[str]
    patch_unaffected_successes: List[str]


class TestFailureAnalyzer:
    """Analyze test failures."""
    
    def __init__(self, gold_path: str):
        self.gold_path = Path(gold_path)
        self.results: List[FailureAnalysisResult] = []
        
    def scan_projects(self) -> List[str]:
        """Scan project directories."""
        projects = []
        if not self.gold_path.exists():
            print(f"Error: path does not exist: {self.gold_path}")
            return projects
            
        for item in self.gold_path.iterdir():
            if item.is_dir():
                report_file = item / "report.json"
                if report_file.exists():
                    projects.append(item.name)
        
        print(f"Found {len(projects)} project directories")
        return projects
    
    def parse_report_json(self, project_path: Path) -> Tuple[List[str], List[str]]:
        """Read failed and successful PASS_TO_PASS tests from report.json."""
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
            print(f"Error parsing {report_file}: {e}")
            
        return failed_tests, success_tests
    
    def parse_test_patch(self, project_path: Path) -> Set[str]:
        """Extract modified test function names from test_patch.txt."""
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
            print(f"Error parsing {patch_file}: {e}")
            
        return modified_tests
    
    def extract_test_name(self, full_test_name: str) -> str:
        """Extract the function name from a complete test name."""
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
        """Analyze one project."""
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
        """Run the complete analysis."""
        print("Analyzing PASS_TO_PASS tests...")
        print("=" * 60)
        
        projects = self.scan_projects()
        
        if not projects:
            print("No project directories found")
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
                print(f"Processed {i}/{len(projects)} projects...")
        
        print(f"Completed; projects with test data: {projects_with_tests}")
        print(f"Total tests: {total_failed_tests} failed + {total_success_tests} passed = {total_failed_tests + total_success_tests}")
        
        # Generate report
        self.generate_report(projects, total_failed_tests, total_success_tests, projects_with_failures, 
                           total_patch_affected_failures, total_patch_unaffected_failures,
                           total_patch_affected_successes, total_patch_unaffected_successes, projects_with_tests)
    
    def generate_report(self, projects: List[str], total_failed_tests: int, total_success_tests: int,
                       projects_with_failures: int, total_patch_affected_failures: int, 
                       total_patch_unaffected_failures: int, total_patch_affected_successes: int,
                       total_patch_unaffected_successes: int, projects_with_tests: int) -> None:
        """Generate an analysis report."""
        print("\n=== PASS_TO_PASS test analysis ===\n")
        
        # Overall statistics
        print("Overall statistics:")
        print(f"   Projects scanned: {len(projects)}")
        print(f"   Projects with failures: {projects_with_failures}")
        print(f"   Failed tests: {total_failed_tests}")
        print(f"   Passed tests: {total_success_tests}")
        print(f"   Total tests: {total_failed_tests + total_success_tests}")
        print()
        print("   Patch impact on failed tests:")
        print(f"      Modified failures: {total_patch_affected_failures}")
        print(f"      Unmodified failures: {total_patch_unaffected_failures}")
        if total_failed_tests > 0:
            failure_patch_rate = (total_patch_affected_failures / total_failed_tests) * 100
            print(f"      Failure patch impact: {failure_patch_rate:.1f}%")
        
        print()
        print("   Patch impact on passed tests:")
        print(f"      Modified successes: {total_patch_affected_successes}")
        print(f"      Unmodified successes: {total_patch_unaffected_successes}")
        if total_success_tests > 0:
            success_patch_rate = (total_patch_affected_successes / total_success_tests) * 100
            print(f"      Success patch impact: {success_patch_rate:.1f}%")
        
        print("\n" + "=" * 60)
        
        # Detailed analysis - failed tests
        print("\nFailed test details:")
        
        failure_results = [r for r in self.results if r.failed_tests]
        
        if not failure_results:
            print("   All projects passed their PASS_TO_PASS tests.")
        else:
            for i, result in enumerate(failure_results, 1):
                print(f"\n{i}. Project: {result.project_name}")
                print(f"   Failed test count: {len(result.failed_tests)}")
                
                if result.failed_tests:
                    print("   Failed tests:")
                    for test in result.failed_tests:
                        status = "(modified by patch)" if test in result.patch_affected_failures else "(unmodified)"
                        print(f"   │   • {test} {status}")
                
                if result.patch_modified_tests:
                    print(f"   Modified test functions: {', '.join(sorted(result.patch_modified_tests))}")
                
                patch_affected_count = len(result.patch_affected_failures)
                total_failures = len(result.failed_tests)
                if total_failures > 0:
                    impact_rate = (patch_affected_count / total_failures) * 100
                    print(f"   Patch impact: {patch_affected_count}/{total_failures} ({impact_rate:.1f}%)")
        
        print("\n" + "=" * 60)
        
        # Detailed analysis - successful tests modified by patch
        print("\nPassed tests modified by the patch:")
        
        success_patch_results = [r for r in self.results if r.patch_affected_successes]
        
        if not success_patch_results:
            print("   No passed tests were modified")
        else:
            for i, result in enumerate(success_patch_results, 1):
                print(f"\n{i}. Project: {result.project_name}")
                print(f"   Modified successes: {len(result.patch_affected_successes)}")
                print(f"   Total successes: {len(result.success_tests)}")
                
                if result.patch_affected_successes:
                    print("   Modified passed tests:")
                    for test in result.patch_affected_successes[:10]:  # Limit display to first 10
                        print(f"   │   • {test}")
                    if len(result.patch_affected_successes) > 10:
                        print(f"   ... {len(result.patch_affected_successes) - 10} more")
                
                success_count = len(result.success_tests)
                patch_success_count = len(result.patch_affected_successes)
                if success_count > 0:
                    success_rate = (patch_success_count / success_count) * 100
                    print(f"   Success patch impact: {patch_success_count}/{success_count} ({success_rate:.1f}%)")
        
        print("\n" + "=" * 60)
        print("\nOverall patch impact:")
        print("   Failed tests:")
        print(f"      Modified: {total_patch_affected_failures}")
        print(f"      Unmodified: {total_patch_unaffected_failures}")
        
        print("   Passed tests:")
        print(f"      Modified: {total_patch_affected_successes}")
        print(f"      Unmodified: {total_patch_unaffected_successes}")
        
        total_tests = total_failed_tests + total_success_tests
        total_patch_affected = total_patch_affected_failures + total_patch_affected_successes
        
        if total_tests > 0:
            print(f"\n   Overall patch impact: {(total_patch_affected / total_tests) * 100:.1f}%")
            print(f"   Patch-related tests: {total_patch_affected} / {total_tests}")


def main():
    """Run analysis for an explicitly provided report directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gold_path", help="Directory containing project reports")
    args = parser.parse_args()
    analyzer = TestFailureAnalyzer(args.gold_path)
    analyzer.run_analysis()


if __name__ == "__main__":
    main()
