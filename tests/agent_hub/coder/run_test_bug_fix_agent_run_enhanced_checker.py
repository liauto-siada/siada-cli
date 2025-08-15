"""
BugFixAgent.run_enhanced_checker method tests

Tests the enhanced fix result checker functionality, including execution trace analysis and expert-level evaluation
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import json
from datetime import datetime
from typing import Dict, Any

from siada.agent_hub.coder.bug_fix_agent import BugFixAgent
from siada.foundation.code_agent_context import CodeAgentContext
from siada.services.execution_trace_collector import ExecutionTrace, ModelCall, ToolCall
from agents import RunResult


class TestBugFixAgentRunEnhancedChecker(unittest.IsolatedAsyncioTestCase):
    """Test BugFixAgent.run_enhanced_checker method"""

    def setUp(self):
        """Set up test environment"""
        self.agent = BugFixAgent()
        self.context = CodeAgentContext(root_dir="/test/project")
        self.user_input = "Fix array bounds access issue"
        
        # Create mock RunResult
        self.mock_run_result = MagicMock(spec=RunResult)
        self.mock_run_result.new_items = self._create_mock_new_items()
        self.mock_run_result._extract_execution_trace_from_run_result = MagicMock()

    def _create_mock_new_items(self):
        """Create mock new_items list containing message_output_item and tool_call_output_item"""
        # Create message_output_item
        message_item = MagicMock()
        message_item.type = "message_output_item"
        message_item.raw_item = MagicMock()
        message_item.raw_item.content = "I analyzed the code issue and found need to add boundary check"
        
        # Create tool_call_item (tool call)
        tool_call_item = MagicMock()
        tool_call_item.type = "tool_call_item"
        tool_call_item.arguments = '{"file_path": "src/array_utils.py", "content": "Add boundary check code"}'
        
        # Create tool_call_output_item (tool call result)
        tool_call_output_item = MagicMock()
        tool_call_output_item.type = "tool_call_output_item"
        tool_call_output_item.raw_item = {
            "output": "File successfully modified, added array boundary check",
            "success": True
        }
        
        # Return list containing message_output_item, tool_call_item, tool_call_output_item
        return [message_item, tool_call_item, tool_call_output_item]

    def _create_mock_execution_trace(self) -> ExecutionTrace:
        """Create mock execution trace"""
        # Create mock model call
        model_call = ModelCall(
            call_id=1,
            model="claude-3-sonnet",
            input_messages=[{"role": "user", "content": "Analyze code issue"}],
            output_messages=[{"role": "assistant", "content": "Found array bounds issue"}]
        )
        
        # Create mock tool call
        tool_call = ToolCall(
            call_id=1,
            tool_name="",
            input_args=MagicMock(),
            output_result="File content read",
            duration_ms=150.0,
            error_message=None
        )
        
        # Create execution trace
        trace = ExecutionTrace(
            trace_id="test_trace_001",
            workflow_name="bug_fix",
            start_time= datetime.now(),
            model_calls=[model_call],
            tool_calls=[tool_call],
            total_tokens=1500,
            total_input_tokens=800,
            total_output_tokens=700
        )
        
        return trace

    def _create_mock_enhanced_check_result(self) -> Dict[str, Any]:
        """Create mock enhanced check result"""
        return {
            "is_fixed": True,
            "check_summary": "🔍 **专家分析**: 数组边界检查已正确实现。🧠 **认知模式**: 系统性问题分析方法。⚠️ **关键差距**: 无重大遗漏。🎯 **影响评估**: 修复完整且安全。💡 **策略建议**: 建议添加单元测试验证边界条件。",
            "fix_analysis": "架构影响分析：修复不影响整体系统架构",
            "trace_analysis": "执行策略有效性：问题解决方法系统且全面",
            "efficiency_suggestions": [
                "**关键**: 添加边界条件的单元测试",
                "**重要**: 考虑使用更安全的数组访问模式",
                "**建议**: 添加代码注释说明边界检查逻辑"
            ],
            "strategy_suggestions": [
                "**架构**: 考虑引入统一的数组访问工具类",
                "**流程**: 建立代码审查检查清单",
                "**工具**: 使用静态分析工具检测类似问题"
            ],
            "overall_score": 8.5,
            "expert_assessment": {
                "confidence_level": "High",
                "technical_depth_analysis": {
                    "architecture_impact": "修复不影响整体系统架构，局部改进",
                    "integration_concerns": "无集成风险，向后兼容",
                    "performance_implications": "性能影响微乎其微，边界检查开销很小",
                    "security_considerations": "显著提升安全性，防止缓冲区溢出",
                    "maintainability_assessment": "代码可维护性良好，逻辑清晰"
                },
                "cognitive_analysis": {
                    "problem_framing_quality": "问题识别准确，根因分析到位",
                    "solution_strategy_assessment": "解决方案策略合理，实施得当",
                    "decision_making_patterns": "决策过程逻辑清晰，考虑全面",
                    "blind_spots_identified": "测试覆盖可以进一步加强"
                }
            },
            "execution_intelligence": {
                "strategy_effectiveness": {
                    "overall_approach": "系统性问题解决方法，效果良好",
                    "information_gathering": "信息收集充分，上下文理解准确",
                    "solution_development": "解决方案开发过程合理",
                    "validation_strategy": "验证策略基本完善"
                },
                "efficiency_analysis": {
                    "resource_utilization": "计算资源使用合理",
                    "workflow_optimization": "工作流程基本优化",
                    "bottleneck_identification": "未发现明显性能瓶颈",
                    "improvement_opportunities": "可优化测试验证环节"
                },
                "learning_patterns": {
                    "adaptation_quality": "对新信息适应良好",
                    "insight_generation": "生成了有价值的洞察",
                    "error_recovery": "错误恢复机制有效",
                    "knowledge_integration": "知识整合能力强"
                }
            },
            "professional_recommendations": {
                "immediate_actions": [
                    "**关键**: 添加边界条件的单元测试",
                    "**重要**: 验证所有数组访问点",
                    "**建议**: 更新相关文档"
                ],
                "strategic_improvements": [
                    "**架构**: 建立统一的安全编码标准",
                    "**流程**: 完善代码审查流程",
                    "**工具**: 集成静态分析工具"
                ],
                "learning_opportunities": [
                    "**模式识别**: 学习识别类似的边界检查问题",
                    "**技能发展**: 提升安全编码技能",
                    "**知识差距**: 深入理解内存安全最佳实践"
                ]
            },
            "risk_assessment": {
                "production_risks": [
                    {
                        "risk_type": "Security",
                        "severity": "Low",
                        "probability": "Low",
                        "description": "修复后安全风险显著降低",
                        "mitigation": "继续监控和测试"
                    }
                ],
                "technical_debt_impact": "技术债务略有减少，代码质量提升",
                "regression_potential": "回归风险很低，修复向后兼容"
            },
            "quality_metrics": {
                "detailed_scores": {
                    "problem_understanding": 9.0,
                    "solution_completeness": 8.5,
                    "implementation_quality": 8.0,
                    "testing_coverage": 7.0,
                    "documentation_quality": 7.5,
                    "execution_efficiency": 8.5,
                    "strategic_thinking": 8.0
                },
                "score_justification": "整体质量良好，主要改进空间在测试覆盖和文档完善"
            },
            "executive_summary": {
                "verdict": "**专业判断**: 修复质量高，有效解决了核心问题",
                "key_concerns": "**主要关注点**: 测试覆盖需要加强，文档需要更新",
                "success_criteria": "**成功标准**: 边界检查正确实现，无安全漏洞，性能影响可接受",
                "next_steps": "**建议后续步骤**: 1. 添加单元测试 2. 更新文档 3. 代码审查"
            },
            "code_diff": "diff --git a/array_utils.py b/array_utils.py\n+if index >= 0 and index < len(array):"
        }

    async def test_run_enhanced_checker_with_run_result(self):
        """测试带有 RunResult 的 run_enhanced_checker 方法"""
        # 准备测试数据
        mock_diff = "diff --git a/test.py b/test.py\n+if index < len(array):"
        mock_trace = self._create_mock_execution_trace()
        mock_enhanced_result = self._create_mock_enhanced_check_result()
        
        # Mock GitDiffUtil
        with patch('siada.foundation.tools.get_git_diff.GitDiffUtil.get_git_diff_exclude_test_files') as mock_git_diff:
            mock_git_diff.return_value = mock_diff
            
            # Mock _extract_execution_trace_from_run_result 方法
            with patch.object(self.agent, '_extract_execution_trace_from_run_result', return_value=mock_trace):
                
                # Mock enhanced_fix_result_checker.check_with_trace
                self.agent.enhanced_fix_result_checker.check_with_trace = AsyncMock(return_value=mock_enhanced_result)
                
                # 执行测试
                result = await self.agent.run_enhanced_checker(
                    self.user_input, 
                    self.context, 
                    self.mock_run_result
                )
            
            # 验证基本结果结构
            self.assertIsInstance(result, dict)
            self.assertTrue(result["is_fixed"])
            self.assertIn("专家分析", result["check_summary"])
            self.assertEqual(result["overall_score"], 8.5)
            self.assertEqual(result["code_diff"], mock_diff)
            
            # 验证所有必需的字段都存在
            required_fields = [
                "is_fixed", "check_summary", "fix_analysis", "trace_analysis",
                "efficiency_suggestions", "strategy_suggestions", "overall_score",
                "expert_assessment", "execution_intelligence", "professional_recommendations",
                "risk_assessment", "quality_metrics", "executive_summary", "code_diff"
            ]
            
            for field in required_fields:
                self.assertIn(field, result, f"Missing required field: {field}")
            
            # 验证专家评估结构
            expert_assessment = result["expert_assessment"]
            self.assertIn("confidence_level", expert_assessment)
            self.assertEqual(expert_assessment["confidence_level"], "High")
            self.assertIn("technical_depth_analysis", expert_assessment)
            self.assertIn("cognitive_analysis", expert_assessment)
            
            # 验证技术深度分析
            tech_analysis = expert_assessment["technical_depth_analysis"]
            expected_tech_fields = [
                "architecture_impact", "integration_concerns", "performance_implications",
                "security_considerations", "maintainability_assessment"
            ]
            for field in expected_tech_fields:
                self.assertIn(field, tech_analysis)
            
            # 验证认知分析
            cognitive_analysis = expert_assessment["cognitive_analysis"]
            expected_cognitive_fields = [
                "problem_framing_quality", "solution_strategy_assessment",
                "decision_making_patterns", "blind_spots_identified"
            ]
            for field in expected_cognitive_fields:
                self.assertIn(field, cognitive_analysis)
            
            # 验证执行智能分析结构
            execution_intelligence = result["execution_intelligence"]
            self.assertIn("strategy_effectiveness", execution_intelligence)
            self.assertIn("efficiency_analysis", execution_intelligence)
            self.assertIn("learning_patterns", execution_intelligence)
            
            # 验证专业建议结构
            professional_recommendations = result["professional_recommendations"]
            self.assertIn("immediate_actions", professional_recommendations)
            self.assertIn("strategic_improvements", professional_recommendations)
            self.assertIn("learning_opportunities", professional_recommendations)
            
            # 验证建议内容不为空
            self.assertTrue(len(professional_recommendations["immediate_actions"]) > 0)
            self.assertTrue(len(professional_recommendations["strategic_improvements"]) > 0)
            self.assertTrue(len(professional_recommendations["learning_opportunities"]) > 0)
            
            # 验证风险评估结构
            risk_assessment = result["risk_assessment"]
            self.assertIn("production_risks", risk_assessment)
            self.assertIn("technical_debt_impact", risk_assessment)
            self.assertIn("regression_potential", risk_assessment)
            
            # 验证生产风险结构
            production_risks = risk_assessment["production_risks"]
            self.assertIsInstance(production_risks, list)
            if production_risks:
                risk = production_risks[0]
                self.assertIn("risk_type", risk)
                self.assertIn("severity", risk)
                self.assertIn("probability", risk)
                self.assertIn("description", risk)
                self.assertIn("mitigation", risk)
            
            # 验证质量指标结构
            quality_metrics = result["quality_metrics"]
            self.assertIn("detailed_scores", quality_metrics)
            self.assertIn("score_justification", quality_metrics)
            
            # 验证详细评分
            detailed_scores = quality_metrics["detailed_scores"]
            expected_score_fields = [
                "problem_understanding", "solution_completeness", "implementation_quality",
                "testing_coverage", "documentation_quality", "execution_efficiency", "strategic_thinking"
            ]
            for field in expected_score_fields:
                self.assertIn(field, detailed_scores)
                self.assertIsInstance(detailed_scores[field], (int, float))
                self.assertGreaterEqual(detailed_scores[field], 0)
                self.assertLessEqual(detailed_scores[field], 10)
            
            # 验证执行摘要结构
            executive_summary = result["executive_summary"]
            self.assertIn("verdict", executive_summary)
            self.assertIn("key_concerns", executive_summary)
            self.assertIn("success_criteria", executive_summary)
            self.assertIn("next_steps", executive_summary)
            
            # 验证摘要内容不为空
            for key, value in executive_summary.items():
                self.assertIsInstance(value, str)
                self.assertTrue(len(value.strip()) > 0, f"Empty {key} in executive_summary")
            
            # 验证效率建议和策略建议
            self.assertIsInstance(result["efficiency_suggestions"], list)
            self.assertIsInstance(result["strategy_suggestions"], list)
            self.assertTrue(len(result["efficiency_suggestions"]) > 0)
            self.assertTrue(len(result["strategy_suggestions"]) > 0)
            
            # 验证 GitDiffUtil 被正确调用
            mock_git_diff.assert_called_once_with(self.context.root_dir)
            
            # 注意：由于使用了 patch.object，这里不需要验证 mock_run_result 的调用
            # 实际的 _extract_execution_trace_from_run_result 方法被 patch 替换了
            
            # 验证 enhanced_fix_result_checker.check_with_trace 被正确调用
            self.agent.enhanced_fix_result_checker.check_with_trace.assert_called_once_with(
                issue_desc=self.user_input,
                fix_code=mock_diff,
                execution_trace=mock_trace
            )
            
            # 验证轨迹数据的完整性
            self.assertIsNotNone(mock_trace)
            self.assertEqual(mock_trace.trace_id, "test_trace_001")
            self.assertEqual(mock_trace.workflow_name, "bug_fix")
            self.assertEqual(len(mock_trace.model_calls), 1)
            self.assertEqual(len(mock_trace.tool_calls), 1)
            self.assertEqual(mock_trace.total_tokens, 1500)

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


    def test_build_enhanced_feedback_with_execution_stats(self):
        """测试包含执行统计信息的反馈"""
        current_turn = 0
        result = self._create_mock_result("修复逻辑")
        check_result = self._create_mock_check_result()
        check_summary = "检查摘要"
        enhanced_check_result = self._create_mock_enhanced_check_result()
        enhanced_check_result["execution_stats"] = {
            "model_calls": 5,
            "tool_calls": 8
        }

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

    async def test_run_enhanced_checker_without_run_result(self):
        """测试不带 RunResult 的 run_enhanced_checker 方法"""
        # 准备测试数据
        mock_diff = "diff --git a/test.py b/test.py\n+if index < len(array):"
        mock_enhanced_result = self._create_mock_enhanced_check_result()
        
        # Mock GitDiffUtil
        with patch('siada.foundation.tools.get_git_diff.GitDiffUtil.get_git_diff_exclude_test_files') as mock_git_diff:
            mock_git_diff.return_value = mock_diff
            
            # Mock enhanced_fix_result_checker.check_with_trace
            self.agent.enhanced_fix_result_checker.check_with_trace = AsyncMock(return_value=mock_enhanced_result)
            
            # 执行测试（不传入 run_result）
            result = await self.agent.run_enhanced_checker(
                self.user_input, 
                self.context
            )
            
            # 验证结果
            self.assertIsInstance(result, dict)
            self.assertTrue(result["is_fixed"])
            self.assertEqual(result["code_diff"], mock_diff)
            
            # 验证基本字段存在
            self.assertIn("check_summary", result)
            self.assertIn("overall_score", result)
            self.assertIn("expert_assessment", result)
            
            # 验证 enhanced_fix_result_checker.check_with_trace 被调用时 execution_trace 为 None
            self.agent.enhanced_fix_result_checker.check_with_trace.assert_called_once_with(
                issue_desc=self.user_input,
                fix_code=mock_diff,
                execution_trace=None
            )

    async def test_run_enhanced_checker_trace_extraction_failure(self):
        """测试执行轨迹提取失败的情况"""
        mock_diff = "diff content"
        mock_enhanced_result = self._create_mock_enhanced_check_result()
        
        # Mock GitDiffUtil
        with patch('siada.foundation.tools.get_git_diff.GitDiffUtil.get_git_diff_exclude_test_files') as mock_git_diff:
            mock_git_diff.return_value = mock_diff
            
            # Mock _extract_execution_trace_from_run_result 抛出异常
            with patch.object(self.agent, '_extract_execution_trace_from_run_result', side_effect=Exception("Trace extraction failed")):
                
                # Mock enhanced_fix_result_checker.check_with_trace
                self.agent.enhanced_fix_result_checker.check_with_trace = AsyncMock(return_value=mock_enhanced_result)
                
                # 执行测试
                result = await self.agent.run_enhanced_checker(
                    self.user_input, 
                    self.context, 
                    self.mock_run_result
                )
                
                # 验证即使轨迹提取失败，方法仍能正常工作（传入 None）
                self.assertIsInstance(result, dict)
                self.agent.enhanced_fix_result_checker.check_with_trace.assert_called_once_with(
                    issue_desc=self.user_input,
                    fix_code=mock_diff,
                    execution_trace=None
                )

    def test_extract_execution_trace_from_run_result(self):
        """测试 _extract_execution_trace_from_run_result 方法"""
        # 使用已经设置好的 mock_run_result，它包含了 _create_mock_new_items() 的数据
        
        # 执行轨迹提取
        trace = self.agent._extract_execution_trace_from_run_result(self.mock_run_result)
        
        # 验证返回的轨迹对象
        self.assertIsInstance(trace, ExecutionTrace)
        self.assertIsNotNone(trace.trace_id)
        self.assertTrue(trace.trace_id.startswith("trace_"))
        self.assertEqual(trace.workflow_name, "bug_fix")
        self.assertIsNotNone(trace.start_time)
        
        # 验证模型调用数量（应该有1个 message_output_item）
        self.assertEqual(len(trace.model_calls), 1)
        
        # 验证工具调用数量（应该有1个 tool_call_output_item）
        self.assertEqual(len(trace.tool_calls), 1)
        
        # 验证模型调用内容
        model_call = trace.model_calls[0]
        self.assertEqual(model_call.call_id, 1)
        self.assertIn("我分析了代码问题，发现需要添加边界检查", str(model_call.output_messages))
        
        # 验证工具调用内容
        tool_call = trace.tool_calls[0]
        self.assertEqual(tool_call.call_id, 1)
        self.assertIn("文件已成功修改", tool_call.output_result)

    # async def test_run_enhanced_checker_without_run_result(self):
    #     """测试不带 RunResult 的 run_enhanced_checker 方法"""
    #     # 准备测试数据
    #     mock_diff = "diff --git a/test.py b/test.py\n+if index < len(array):"
    #     mock_enhanced_result = self._create_mock_enhanced_check_result()
        
    #     # Mock GitDiffUtil
    #     with patch('siada.foundation.tools.get_git_diff.GitDiffUtil.get_git_diff_exclude_test_files') as mock_git_diff:
    #         mock_git_diff.return_value = mock_diff
            
    #         # Mock enhanced_fix_result_checker.check
    #         self.agent.enhanced_fix_result_checker.check = AsyncMock(return_value=mock_enhanced_result)
            
    #         # 执行测试（不传入 run_result）
    #         result = await self.agent.run_enhanced_checker(
    #             self.user_input, 
    #             self.context
    #         )
            
    #         # 验证结果
    #         self.assertIsInstance(result, dict)
    #         self.assertTrue(result["is_fixed"])
    #         self.assertEqual(result["code_diff"], mock_diff)
            
    #         # 验证 enhanced_fix_result_checker.check 被调用时 execution_trace 为 None
    #         self.agent.enhanced_fix_result_checker.check.assert_called_once_with(
    #             issue_desc=self.user_input,
    #             fix_code=mock_diff,
    #             execution_trace=None
    #         )

    # async def test_run_enhanced_checker_with_execution_stats(self):
    #     """测试包含执行统计信息的增强检查"""
    #     # 准备包含执行统计的测试数据
    #     mock_enhanced_result = self._create_mock_enhanced_check_result()
    #     mock_enhanced_result["execution_stats"] = {
    #         "model_calls": 3,
    #         "tool_calls": 5,
    #         "total_duration_ms": 2500.0
    #     }
        
    #     mock_diff = "diff --git a/test.py b/test.py\n+boundary check added"
        
    #     # Mock dependencies
    #     with patch('siada.foundation.tools.get_git_diff.GitDiffUtil.get_git_diff_exclude_test_files') as mock_git_diff:
    #         mock_git_diff.return_value = mock_diff
            
    #         self.agent.enhanced_fix_result_checker.check = AsyncMock(return_value=mock_enhanced_result)
            
    #         # 执行测试
    #         result = await self.agent.run_enhanced_checker(
    #             self.user_input, 
    #             self.context
    #         )
            
    #         # 验证执行统计信息
    #         self.assertIn("execution_stats", result)
    #         self.assertEqual(result["execution_stats"]["model_calls"], 3)
    #         self.assertEqual(result["execution_stats"]["tool_calls"], 5)

    # async def test_run_enhanced_checker_error_handling(self):
    #     """测试 run_enhanced_checker 的错误处理"""
    #     # Mock GitDiffUtil 抛出异常
    #     with patch('siada.foundation.tools.get_git_diff.GitDiffUtil.get_git_diff_exclude_test_files') as mock_git_diff:
    #         mock_git_diff.side_effect = Exception("Git diff failed")
            
    #         # 执行测试
    #         with self.assertRaises(Exception) as context:
    #             await self.agent.run_enhanced_checker(
    #                 self.user_input, 
    #                 self.context
    #             )
            
    #         self.assertIn("Git diff failed", str(context.exception))

    # async def test_run_enhanced_checker_enhanced_checker_failure(self):
    #     """测试增强检查器失败的情况"""
    #     mock_diff = "diff content"
        
    #     # Mock GitDiffUtil 正常工作
    #     with patch('siada.foundation.tools.get_git_diff.GitDiffUtil.get_git_diff_exclude_test_files') as mock_git_diff:
    #         mock_git_diff.return_value = mock_diff
            
    #         # Mock enhanced_fix_result_checker.check 抛出异常
    #         self.agent.enhanced_fix_result_checker.check = AsyncMock(
    #             side_effect=Exception("Enhanced checker failed")
    #         )
            
    #         # 执行测试
    #         with self.assertRaises(Exception) as context:
    #             await self.agent.run_enhanced_checker(
    #                 self.user_input, 
    #                 self.context
    #             )
            
    #         self.assertIn("Enhanced checker failed", str(context.exception))

    # async def test_run_enhanced_checker_trace_extraction_failure(self):
    #     """测试执行轨迹提取失败的情况"""
    #     mock_diff = "diff content"
    #     mock_enhanced_result = self._create_mock_enhanced_check_result()
        
    #     # Mock GitDiffUtil
    #     with patch('siada.foundation.tools.get_git_diff.GitDiffUtil.get_git_diff_exclude_test_files') as mock_git_diff:
    #         mock_git_diff.return_value = mock_diff
            
    #         # Mock _extract_execution_trace_from_run_result 抛出异常
    #         self.mock_run_result._extract_execution_trace_from_run_result.side_effect = Exception("Trace extraction failed")
            
    #         # Mock enhanced_fix_result_checker.check
    #         self.agent.enhanced_fix_result_checker.check = AsyncMock(return_value=mock_enhanced_result)
            
    #         # 执行测试
    #         result = await self.agent.run_enhanced_checker(
    #             self.user_input, 
    #             self.context, 
    #             self.mock_run_result
    #         )
            
    #         # 验证即使轨迹提取失败，方法仍能正常工作（传入 None）
    #         self.assertIsInstance(result, dict)
    #         self.agent.enhanced_fix_result_checker.check.assert_called_once_with(
    #             issue_desc=self.user_input,
    #             fix_code=mock_diff,
    #             execution_trace=None
    #         )

    # async def test_run_enhanced_checker_comprehensive_result_structure(self):
    #     """测试 run_enhanced_checker 返回的完整结果结构"""
    #     mock_diff = "comprehensive diff content"
    #     mock_enhanced_result = self._create_mock_enhanced_check_result()
        
    #     with patch('siada.foundation.tools.get_git_diff.GitDiffUtil.get_git_diff_exclude_test_files') as mock_git_diff:
    #         mock_git_diff.return_value = mock_diff
            
    #         self.agent.enhanced_fix_result_checker.check = AsyncMock(return_value=mock_enhanced_result)
            
    #         result = await self.agent.run_enhanced_checker(
    #             self.user_input, 
    #             self.context
    #         )
            
    #         # 验证所有必需的字段都存在
    #         required_fields = [
    #             "is_fixed", "check_summary", "fix_analysis", "trace_analysis",
    #             "efficiency_suggestions", "strategy_suggestions", "overall_score",
    #             "expert_assessment", "execution_intelligence", "professional_recommendations",
    #             "risk_assessment", "quality_metrics", "executive_summary", "code_diff"
    #         ]
            
    #         for field in required_fields:
    #             self.assertIn(field, result, f"Missing required field: {field}")
            
    #         # 验证专家评估结构
    #         expert_assessment = result["expert_assessment"]
    #         self.assertIn("confidence_level", expert_assessment)
    #         self.assertIn("technical_depth_analysis", expert_assessment)
    #         self.assertIn("cognitive_analysis", expert_assessment)
            
    #         # 验证执行智能分析结构
    #         execution_intelligence = result["execution_intelligence"]
    #         self.assertIn("strategy_effectiveness", execution_intelligence)
    #         self.assertIn("efficiency_analysis", execution_intelligence)
    #         self.assertIn("learning_patterns", execution_intelligence)
            
    #         # 验证专业建议结构
    #         professional_recommendations = result["professional_recommendations"]
    #         self.assertIn("immediate_actions", professional_recommendations)
    #         self.assertIn("strategic_improvements", professional_recommendations)
    #         self.assertIn("learning_opportunities", professional_recommendations)
            
    #         # 验证风险评估结构
    #         risk_assessment = result["risk_assessment"]
    #         self.assertIn("production_risks", risk_assessment)
    #         self.assertIn("technical_debt_impact", risk_assessment)
    #         self.assertIn("regression_potential", risk_assessment)
            
    #         # 验证质量指标结构
    #         quality_metrics = result["quality_metrics"]
    #         self.assertIn("detailed_scores", quality_metrics)
    #         self.assertIn("score_justification", quality_metrics)
            
    #         # 验证执行摘要结构
    #         executive_summary = result["executive_summary"]
    #         self.assertIn("verdict", executive_summary)
    #         self.assertIn("key_concerns", executive_summary)
    #         self.assertIn("success_criteria", executive_summary)
    #         self.assertIn("next_steps", executive_summary)

    # async def test_run_enhanced_checker_different_user_inputs(self):
    #     """测试不同类型的用户输入"""
    #     test_cases = [
    #         "修复内存泄漏问题",
    #         "解决并发访问冲突",
    #         "优化数据库查询性能",
    #         "修复安全漏洞",
    #         "重构代码结构"
    #     ]
        
    #     mock_diff = "test diff"
    #     mock_enhanced_result = self._create_mock_enhanced_check_result()
        
    #     with patch('siada.foundation.tools.get_git_diff.GitDiffUtil.get_git_diff_exclude_test_files') as mock_git_diff:
    #         mock_git_diff.return_value = mock_diff
            
    #         self.agent.enhanced_fix_result_checker.check = AsyncMock(return_value=mock_enhanced_result)
            
    #         for user_input in test_cases:
    #             with self.subTest(user_input=user_input):
    #                 result = await self.agent.run_enhanced_checker(
    #                     user_input, 
    #                     self.context
    #                 )
                    
    #                 # 验证基本结构
    #                 self.assertIsInstance(result, dict)
    #                 self.assertIn("is_fixed", result)
    #                 self.assertIn("check_summary", result)
    #                 self.assertEqual(result["code_diff"], mock_diff)

    # def test_run_enhanced_checker_docstring_accuracy(self):
    #     """测试方法文档字符串的准确性"""
    #     # 获取方法的文档字符串
    #     docstring = self.agent.run_enhanced_checker.__doc__
        
    #     # 验证文档字符串包含关键信息
    #     self.assertIsNotNone(docstring)
    #     self.assertIn("运行增强版检查器", docstring)
    #     self.assertIn("user_input", docstring)
    #     self.assertIn("context", docstring)
    #     self.assertIn("run_result", docstring)
    #     self.assertIn("Returns", docstring)
    #     self.assertIn("增强的检查结果", docstring)


if __name__ == '__main__':
    unittest.main()
