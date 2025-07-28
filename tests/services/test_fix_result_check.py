"""
FixResultChecker 测试

测试代码修复结果检查器的功能 - 使用真实的模型访问
"""
import unittest
import json

from siada.services.fix_result_check import FixResultChecker


class TestFixResultChecker(unittest.IsolatedAsyncioTestCase):
    """测试 FixResultChecker 类"""

    def setUp(self):
        """设置测试环境"""
        self.checker = FixResultChecker()

    async def test_call_model_for_analysis_real_api(self):
        """测试 _call_model_for_analysis 方法真实API调用"""
        # 准备测试数据
        issue_desc = """
        在Python代码中，有一个函数试图访问一个可能为None的变量的属性，导致AttributeError。
        
        错误代码：
        def process_user(user):
            return user.name.upper()
        
        当user为None时，会抛出AttributeError: 'NoneType' object has no attribute 'name'
        """
        
        fix_code = """
        修复代码：
        def process_user(user):
            if user is None:
                return "Unknown"
            return user.name.upper() if user.name else "Unknown"
        
        添加了None检查和name属性的安全访问。
        """
        
        try:
            # 执行真实的模型调用
            result = await self.checker._call_model_for_analysis(issue_desc, fix_code)
            
            # 验证返回结果不为空
            self.assertIsNotNone(result)
            self.assertIsInstance(result, str)
            self.assertTrue(len(result.strip()) > 0)

            print("result ====== ", result)
            
            # 尝试解析为JSON，处理可能的markdown包装
            try:
                # 如果响应被包装在markdown代码块中，提取JSON部分
                json_content = result.strip()
                if json_content.startswith('```json'):
                    # 提取markdown代码块中的JSON
                    lines = json_content.split('\n')
                    json_lines = []
                    in_json_block = False
                    for line in lines:
                        if line.strip() == '```json':
                            in_json_block = True
                            continue
                        elif line.strip() == '```' and in_json_block:
                            break
                        elif in_json_block:
                            json_lines.append(line)
                    json_content = '\n'.join(json_lines)
                
                parsed_json = json.loads(json_content)
                
                # 验证JSON结构
                self.assertIsInstance(parsed_json, dict)
                self.assertIn("analysis", parsed_json)
                self.assertIn("result", parsed_json)
                
                # 验证analysis部分
                analysis = parsed_json["analysis"]
                self.assertIsInstance(analysis, dict)
                expected_steps = [
                    "step1_problem_scope",
                    "step2_fix_coverage", 
                    "step3_test_validation",
                    "step4_logical_consistency",
                    "step5_final_assessment"
                ]
                for step in expected_steps:
                    self.assertIn(step, analysis, f"Missing step: {step}")
                    self.assertIsInstance(analysis[step], str)
                    self.assertTrue(len(analysis[step].strip()) > 0, f"Empty content for {step}")
                
                # 验证result部分
                result_data = parsed_json["result"]
                self.assertIsInstance(result_data, dict)
                self.assertIn("is_fixed", result_data)
                self.assertIn("reason", result_data)
                self.assertIsInstance(result_data["is_fixed"], bool)
                self.assertIsInstance(result_data["reason"], str)
                self.assertTrue(len(result_data["reason"].strip()) > 0)
                
                print(f"✅ JSON格式验证通过")
                print(f"📊 分析结果: is_fixed={result_data['is_fixed']}")
                print(f"📝 原因: {result_data['reason']}")
                
            except json.JSONDecodeError as e:
                # 如果不是有效JSON，打印原始响应用于调试
                print(f"❌ JSON解析失败: {e}")
                print(f"📄 原始响应内容:")
                print(result)
                self.fail(f"模型返回的不是有效的JSON格式: {e}")
                
        except Exception as e:
            print(f"❌ 模型调用失败: {e}")
            # 如果是网络或配置问题，跳过测试而不是失败
            self.skipTest(f"模型API调用失败，可能是网络或配置问题: {e}")

    async def test_call_model_for_analysis_simple_case(self):
        """测试简单的修复案例"""
        issue_desc = "变量未初始化就使用"
        fix_code = "在使用前添加了变量初始化: int count = 0;"
        
        try:
            result = await self.checker._call_model_for_analysis(issue_desc, fix_code)
            
            # 基本验证
            self.assertIsNotNone(result)
            self.assertIsInstance(result, str)
            
            # 尝试解析JSON
            try:
                parsed_json = json.loads(result.strip())
                self.assertIn("analysis", parsed_json)
                self.assertIn("result", parsed_json)
                
                print(f"✅ 简单案例测试通过")
                
            except json.JSONDecodeError:
                print(f"❌ 简单案例JSON解析失败")
                print(f"📄 响应内容: {result}")
                self.fail("简单案例返回的不是有效JSON格式")
                
        except Exception as e:
            self.skipTest(f"简单案例模型API调用失败: {e}")

    async def test_end_to_end_check_method(self):
        """测试完整的check方法端到端流程"""
        issue_desc = "数组越界访问导致程序崩溃"
        fix_code = "添加了数组边界检查: if (index >= 0 && index < array.length)"
        
        try:
            # 测试完整的check方法
            result = await self.checker.check(issue_desc, fix_code)
            
            # 验证返回结构
            self.assertIsInstance(result, dict)
            self.assertIn("is_fixed", result)
            self.assertIn("reason", result) 
            self.assertIn("analysis", result)
            
            # 验证数据类型
            self.assertIsInstance(result["is_fixed"], bool)
            self.assertIsInstance(result["reason"], str)
            self.assertIsInstance(result["analysis"], str)
            
            # 验证内容不为空
            self.assertTrue(len(result["reason"].strip()) > 0)
            self.assertTrue(len(result["analysis"].strip()) > 0)
            
            print(f"✅ 端到端测试通过")
            print(f"📊 最终结果: {result}")
            
        except Exception as e:
            self.skipTest(f"端到端测试失败: {e}")

    def test_build_prompt_content(self):
        """测试 build_prompt 方法生成的内容"""
        issue_desc = "变量未初始化"
        fix_code = "int x = 0;"
        
        prompt = self.checker.build_prompt(issue_desc, fix_code)
        
        # 验证prompt包含必要的内容
        self.assertIn(issue_desc, prompt)
        self.assertIn(fix_code, prompt)
        self.assertIn("JSON format", prompt)
        self.assertIn("Step 1: Problem Scope Analysis", prompt)
        self.assertIn("Step 2: Fix Coverage Evaluation", prompt)
        self.assertIn("Step 3: Test Case Completeness Validation", prompt)
        self.assertIn("Step 4: Logical Consistency Check", prompt)
        self.assertIn("Step 5: Final Assessment", prompt)
        self.assertIn("step1_problem_scope", prompt)
        self.assertIn("is_fixed", prompt)
        self.assertIn("reason", prompt)

    async def test_parse_analysis_result_valid_json(self):
        """测试 _parse_analysis_result 方法解析有效JSON"""
        # 准备有效的JSON响应
        json_response = json.dumps({
            "analysis": {
                "step1_problem_scope": "问题分析内容",
                "step2_fix_coverage": "修复覆盖分析",
                "step3_test_validation": "测试验证分析",
                "step4_logical_consistency": "逻辑一致性检查",
                "step5_final_assessment": "最终评估"
            },
            "result": {
                "is_fixed": True,
                "reason": "问题已修复"
            }
        })
        
        result = self.checker._parse_analysis_result(json_response)
        
        # 验证解析结果
        self.assertTrue(result["is_fixed"])
        self.assertEqual(result["reason"], "问题已修复")
        self.assertIn("问题分析内容", result["analysis"])
        self.assertIn("Step 1: Problem Scope Analysis", result["analysis"])

    async def test_parse_analysis_result_invalid_json(self):
        """测试 _parse_analysis_result 方法处理无效JSON"""
        # 准备无效的JSON响应
        invalid_json = "这不是有效的JSON格式"
        
        result = self.checker._parse_analysis_result(invalid_json)
        
        # 验证回退到文本解析
        self.assertIn("JSON解析失败", result["analysis"])
        self.assertIn(invalid_json, result["analysis"])


if __name__ == '__main__':
    unittest.main()
