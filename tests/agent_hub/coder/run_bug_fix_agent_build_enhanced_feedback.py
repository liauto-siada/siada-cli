"""
BugFixAgent._build_enhanced_feedback 方法测试

测试增强反馈构建功能，包括多轮修复的反馈消息生成
"""
import unittest
from unittest.mock import MagicMock
from typing import Dict, Any, List

from siada.agent_hub.coder.bug_fix_agent import BugFixAgent
from agents import RunResult


class TestBugFixAgentBuildEnhancedFeedback(unittest.TestCase):
    """测试 BugFixAgent._build_enhanced_feedback 方法"""

    def setUp(self):
        """设置测试环境"""
        self.agent = BugFixAgent()

    def _create_mock_result(self, final_output: str = "默认修复逻辑") -> MagicMock:
        """创建模拟的 RunResult"""
        mock_result = MagicMock(spec=RunResult)
        mock_result.final_output = final_output
        return mock_result

    def _create_mock_check_result(
        self, 
        is_fixed: bool = False, 
        code_diff: str = "默认代码差异",
        additional_fields: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """创建模拟的检查结果"""
        result = {
            "is_fixed": is_fixed,
            "code_diff": code_diff,
            "analysis": "基础分析结果"
        }
        if additional_fields:
            result.update(additional_fields)
        return result

    def _create_mock_enhanced_check_result(
        self,
        overall_score: float = 7.5,
        check_summary: str = "增强检查摘要",
        execution_stats: Dict[str, Any] = None,
        trace_analysis: str = "轨迹分析结果",
        fix_analysis: str = "修复分析结果"
    ) -> Dict[str, Any]:
        """创建模拟的增强检查结果"""
        result = {
            "overall_score": overall_score,
            "check_summary": check_summary,
            "trace_analysis": trace_analysis,
            "fix_analysis": fix_analysis,
            "professional_recommendations": {
                "strategic_improvements": [
                    "架构改进建议1",
                    "架构改进建议2",
                    "架构改进建议3"
                ]
            }
        }
        
        if execution_stats:
            result["execution_stats"] = execution_stats
            
        return result

    def test_build_enhanced_feedback_basic_structure(self):
        """测试基本的增强反馈结构"""
        # 准备测试数据
        current_turn = 0
        result = self._create_mock_result("第一轮修复逻辑：添加了边界检查")
        check_result = self._create_mock_check_result(
            is_fixed=False,
            code_diff="diff --git a/test.py b/test.py\n+if index < len(array):"
        )
        check_summary = "边界检查不完整"
        enhanced_check_result = self._create_mock_enhanced_check_result()

        # 执行测试
        feedback = self.agent._build_enhanced_feedback(
            current_turn,
            result,
            check_result,
            check_summary,
            enhanced_check_result
        )

        # 验证基本结构
        self.assertIsInstance(feedback, str)
        self.assertIn("## Previous Fix Attempt (Round 1)", feedback)
        self.assertIn("**Fix Logic:**", feedback)
        self.assertIn("第一轮修复逻辑：添加了边界检查", feedback)
        self.assertIn("**Current Code Diff:**", feedback)
        self.assertIn("diff --git a/test.py b/test.py", feedback)
        self.assertIn("## Primary Check Result", feedback)
        self.assertIn("**Fix Status:** ❌ Not Fixed", feedback)
        self.assertIn("**Primary Analysis:** 边界检查不完整", feedback)
        self.assertIn("## Enhanced Analysis", feedback)
        self.assertIn("## Next Steps", feedback)

    def test_build_enhanced_feedback_with_overall_score(self):
        """测试包含总体评分的反馈"""
        current_turn = 1
        result = self._create_mock_result("第二轮修复逻辑")
        check_result = self._create_mock_check_result()
        check_summary = "仍有问题"
        enhanced_check_result = self._create_mock_enhanced_check_result(overall_score=6.8)

        feedback = self.agent._build_enhanced_feedback(
            current_turn,
            result,
            check_result,
            check_summary,
            enhanced_check_result
        )

        # 验证评分信息
        self.assertIn("**Quality Score:** 6.8/10", feedback)
        self.assertIn("## Previous Fix Attempt (Round 2)", feedback)

    def test_build_enhanced_feedback_with_enhanced_summary(self):
        """测试包含增强摘要的反馈"""
        current_turn = 2
        result = self._create_mock_result("第三轮修复逻辑")
        check_result = self._create_mock_check_result()
        check_summary = "基础检查摘要"
        enhanced_check_result = self._create_mock_enhanced_check_result(
            check_summary="详细的增强检查摘要，包含专家分析"
        )

        feedback = self.agent._build_enhanced_feedback(
            current_turn,
            result,
            check_result,
            check_summary,
            enhanced_check_result
        )

        # 验证增强摘要
        self.assertIn("**Enhanced Summary:** 详细的增强检查摘要，包含专家分析", feedback)
        self.assertIn("## Previous Fix Attempt (Round 3)", feedback)

    def test_build_enhanced_feedback_with_execution_stats(self):
        """测试包含执行统计信息的反馈"""
        current_turn = 0
        result = self._create_mock_result("修复逻辑")
        check_result = self._create_mock_check_result()
        check_summary = "检查摘要"
        enhanced_check_result = self._create_mock_enhanced_check_result(
            execution_stats={
                "model_calls": 5,
                "tool_calls": 8
            }
        )

        feedback = self.agent._build_enhanced_feedback(
            current_turn,
            result,
            check_result,
            check_summary,
            enhanced_check_result
        )

        # 验证执行统计信息
        self.assertIn("**Execution Statistics:**", feedback)
        self.assertIn("- Model calls: 5", feedback)
        self.assertIn("- Tool calls: 8", feedback)

    def test_build_enhanced_feedback_with_strategy_suggestions(self):
        """测试包含策略建议的反馈"""
        current_turn = 0
        result = self._create_mock_result("修复逻辑")
        check_result = self._create_mock_check_result()
        check_summary = "检查摘要"
        enhanced_check_result = self._create_mock_enhanced_check_result()

        feedback = self.agent._build_enhanced_feedback(
            current_turn,
            result,
            check_result,
            check_summary,
            enhanced_check_result
        )

        # 验证策略建议
        self.assertIn("**Strategy Improvement Suggestions:", feedback)
        self.assertIn("1. 架构改进建议1", feedback)
        self.assertIn("2. 架构改进建议2", feedback)
        self.assertIn("3. 架构改进建议3", feedback)

    def test_build_enhanced_feedback_with_trace_analysis(self):
        """测试包含轨迹分析的反馈"""
        current_turn = 0
        result = self._create_mock_result("修复逻辑")
        check_result = self._create_mock_check_result()
        check_summary = "检查摘要"
        enhanced_check_result = self._create_mock_enhanced_check_result(
            trace_analysis="详细的执行轨迹分析，包含性能和效率评估"
        )

        feedback = self.agent._build_enhanced_feedback(
            current_turn,
            result,
            check_result,
            check_summary,
            enhanced_check_result
        )

        # 验证轨迹分析
        self.assertIn("**Execution Trace Analysis:**", feedback)
        self.assertIn("详细的执行轨迹分析，包含性能和效率评估", feedback)

    def test_build_enhanced_feedback_with_fix_analysis(self):
        """测试包含修复分析的反馈"""
        current_turn = 0
        result = self._create_mock_result("修复逻辑")
        check_result = self._create_mock_check_result()
        check_summary = "主要检查摘要"
        enhanced_check_result = self._create_mock_enhanced_check_result(
            fix_analysis="深度修复分析，包含架构影响评估"
        )

        feedback = self.agent._build_enhanced_feedback(
            current_turn,
            result,
            check_result,
            check_summary,
            enhanced_check_result
        )

        # 验证修复分析
        self.assertIn("**Primary Focus:** 主要检查摘要", feedback)
        self.assertIn("**Additional Focus:** 深度修复分析，包含架构影响评估", feedback)

    def test_build_enhanced_feedback_no_code_diff(self):
        """测试没有代码差异的情况"""
        current_turn = 0
        result = self._create_mock_result("修复逻辑")
        check_result = self._create_mock_check_result(code_diff="")
        check_summary = "检查摘要"
        enhanced_check_result = self._create_mock_enhanced_check_result()

        feedback = self.agent._build_enhanced_feedback(
            current_turn,
            result,
            check_result,
            check_summary,
            enhanced_check_result
        )

        # 验证无代码差异的处理
        self.assertIn("No changes detected", feedback)

    def test_build_enhanced_feedback_missing_code_diff_key(self):
        """测试缺少 code_diff 键的情况"""
        current_turn = 0
        result = self._create_mock_result("修复逻辑")
        check_result = {"is_fixed": False}  # 没有 code_diff 键
        check_summary = "检查摘要"
        enhanced_check_result = self._create_mock_enhanced_check_result()

        feedback = self.agent._build_enhanced_feedback(
            current_turn,
            result,
            check_result,
            check_summary,
            enhanced_check_result
        )

        # 验证缺少 code_diff 键的处理
        self.assertIn("No changes detected", feedback)

    def test_build_enhanced_feedback_empty_enhanced_result(self):
        """测试空的增强检查结果"""
        current_turn = 0
        result = self._create_mock_result("修复逻辑")
        check_result = self._create_mock_check_result()
        check_summary = "检查摘要"
        enhanced_check_result = {}  # 空的增强检查结果

        feedback = self.agent._build_enhanced_feedback(
            current_turn,
            result,
            check_result,
            check_summary,
            enhanced_check_result
        )

        # 验证基本结构仍然存在
        self.assertIn("## Previous Fix Attempt", feedback)
        self.assertIn("## Primary Check Result", feedback)
        self.assertIn("## Enhanced Analysis", feedback)
        self.assertIn("## Next Steps", feedback)

    def test_build_enhanced_feedback_multiple_turns(self):
        """测试多轮修复的反馈"""
        test_cases = [
            (0, "Round 1"),
            (1, "Round 2"),
            (2, "Round 3"),
            (5, "Round 6")
        ]

        for current_turn, expected_round in test_cases:
            with self.subTest(current_turn=current_turn):
                result = self._create_mock_result(f"第{current_turn + 1}轮修复逻辑")
                check_result = self._create_mock_check_result()
                check_summary = f"第{current_turn + 1}轮检查摘要"
                enhanced_check_result = self._create_mock_enhanced_check_result()

                feedback = self.agent._build_enhanced_feedback(
                    current_turn,
                    result,
                    check_result,
                    check_summary,
                    enhanced_check_result
                )

                # 验证轮次信息
                self.assertIn(f"## Previous Fix Attempt ({expected_round})", feedback)
                self.assertIn(f"第{current_turn + 1}轮修复逻辑", feedback)

    def test_extract_strategy_suggestions_from_professional_recommendations(self):
        """测试从专业建议中提取策略建议"""
        # 测试新结构（professional_recommendations.strategic_improvements）
        enhanced_check_result = {
            "professional_recommendations": {
                "strategic_improvements": [
                    "新结构建议1",
                    "新结构建议2",
                    "新结构建议3",
                    "新结构建议4",  # 测试只取前3个
                    "新结构建议5"
                ]
            }
        }

        suggestions = self.agent._extract_strategy_suggestions(enhanced_check_result)

        # 验证提取结果
        self.assertEqual(len(suggestions), 5)  # 应该返回所有建议
        self.assertEqual(suggestions[0], "新结构建议1")
        self.assertEqual(suggestions[1], "新结构建议2")
        self.assertEqual(suggestions[2], "新结构建议3")

    def test_extract_strategy_suggestions_fallback_to_old_structure(self):
        """测试回退到旧结构的策略建议提取"""
        # 测试旧结构（strategy_suggestions）
        enhanced_check_result = {
            "strategy_suggestions": [
                "旧结构建议1",
                "旧结构建议2"
            ]
        }

        suggestions = self.agent._extract_strategy_suggestions(enhanced_check_result)

        # 验证回退到旧结构
        self.assertEqual(len(suggestions), 2)
        self.assertEqual(suggestions[0], "旧结构建议1")
        self.assertEqual(suggestions[1], "旧结构建议2")

    def test_extract_strategy_suggestions_empty_results(self):
        """测试空的策略建议提取"""
        test_cases = [
            {},  # 完全空的结果
            {"professional_recommendations": {}},  # 空的专业建议
            {"professional_recommendations": {"strategic_improvements": []}},  # 空的策略改进
            {"strategy_suggestions": []},  # 空的旧结构
        ]

        for enhanced_check_result in test_cases:
            with self.subTest(enhanced_check_result=enhanced_check_result):
                suggestions = self.agent._extract_strategy_suggestions(enhanced_check_result)
                self.assertEqual(suggestions, [])

    def test_build_enhanced_feedback_comprehensive_scenario(self):
        """测试包含所有元素的综合场景"""
        current_turn = 1
        result = self._create_mock_result("综合修复逻辑：添加了完整的错误处理和边界检查")
        check_result = self._create_mock_check_result(
            is_fixed=False,
            code_diff="diff --git a/comprehensive.py b/comprehensive.py\n+try:\n+    # 完整的错误处理\n+    pass\n+except Exception as e:\n+    # 异常处理逻辑\n+    pass"
        )
        check_summary = "错误处理逻辑需要进一步完善"
        enhanced_check_result = self._create_mock_enhanced_check_result(
            overall_score=7.8,
            check_summary="综合增强检查：错误处理基本完善，但需要更具体的异常类型处理",
            execution_stats={
                "model_calls": 4,
                "tool_calls": 7
            },
            trace_analysis="执行轨迹显示问题解决策略系统且全面，但在异常处理细节上需要改进",
            fix_analysis="修复分析：架构设计合理，但异常处理粒度需要细化"
        )

        feedback = self.agent._build_enhanced_feedback(
            current_turn,
            result,
            check_result,
            check_summary,
            enhanced_check_result
        )

        # 验证所有元素都存在
        expected_elements = [
            "## Previous Fix Attempt (Round 2)",
            "综合修复逻辑：添加了完整的错误处理和边界检查",
            "diff --git a/comprehensive.py",
            "**Quality Score:** 7.8/10",
            "**Enhanced Summary:** 综合增强检查",
            "**Execution Statistics:**",
            "- Model calls: 4",
            "- Tool calls: 7",
            "**Strategy Improvement Suggestions:",
            "1. 架构改进建议1",
            "2. 架构改进建议2",
            "3. 架构改进建议3",
            "**Execution Trace Analysis:**",
            "执行轨迹显示问题解决策略系统且全面",
            "**Primary Focus:** 错误处理逻辑需要进一步完善",
            "**Additional Focus:** 修复分析：架构设计合理，但异常处理粒度需要细化"
        ]

        for element in expected_elements:
            self.assertIn(element, feedback, f"Missing element: {element}")

    def test_build_enhanced_feedback_edge_cases(self):
        """测试边界情况"""
        # 测试 None 值
        current_turn = 0
        result = self._create_mock_result("")  # 空的修复逻辑
        check_result = self._create_mock_check_result(code_diff=None)  # None 代码差异
        check_summary = ""  # 空的检查摘要
        enhanced_check_result = {
            "overall_score": None,  # None 评分
            "check_summary": None,  # None 增强摘要
            "trace_analysis": None,  # None 轨迹分析
            "fix_analysis": None,  # None 修复分析
        }

        # 应该不抛出异常
        feedback = self.agent._build_enhanced_feedback(
            current_turn,
            result,
            check_result,
            check_summary,
            enhanced_check_result
        )

        # 验证基本结构仍然存在
        self.assertIsInstance(feedback, str)
        self.assertIn("## Previous Fix Attempt", feedback)
        self.assertIn("## Next Steps", feedback)


if __name__ == '__main__':
    unittest.main()
