"""
BugDescOptimizer 测试

测试bug描述优化器的功能 - 使用真实的模型访问
"""
import unittest
import yaml
from pathlib import Path

from siada.services.bug_desc_optimizer import BugDescOptimizer
from siada.config.config_loader import load_conf


class TestBugDescOptimizer(unittest.IsolatedAsyncioTestCase):
    """测试 BugDescOptimizer 类"""

    def setUp(self):
        """设置测试环境"""
        # 创建BugDescOptimizer实例，model参数暂时传None
        self.optimizer = BugDescOptimizer()

        # 从配置文件中读取provider信息
        provider = self._get_provider_from_config()

        # 创建简单的context对象
        class SimpleContext:
            def __init__(self, provider):
                self.provider = provider

        self.context = SimpleContext(provider)

    def _get_provider_from_config(self) -> str:
        """从配置文件中获取provider信息"""
        try:
            # 首先尝试从agent_config.yaml读取
            agent_config_path = Path.cwd() / "agent_config.yaml"
            if agent_config_path.exists():
                with open(agent_config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    llm_config = config.get('llm_config', {})
                    provider = llm_config.get('provider')
                    if provider:
                        return provider

            # 然后尝试从用户配置文件读取
            user_config = load_conf()
            if user_config.llm_config.provider:
                return user_config.llm_config.provider

            # 如果都没有配置，返回默认值
            return "li"

        except Exception as e:
            print(f"Warning: Failed to load provider from config: {e}")
            return "li"  # 默认fallback

    async def test_optimize_real_api(self):
        """测试 optimize 方法真实API调用"""
        # 准备测试数据 - 一个典型的bug描述
        bug_description = """
        在处理numpy数组时出现IndexError。

        错误代码：
        import numpy as np
        
        def process_array(arr):
            return arr[0][1]  # 直接访问二维数组元素
        
        data = np.array([1, 2, 3])  # 一维数组
        result = process_array(data)  # 这里会出错
        
        错误信息：
        IndexError: too many indices for array: array is 1-d, but 2 were used
        
        期望能够处理不同维度的numpy数组输入。
        """

        try:
            # 执行真实的模型调用
            result = await self.optimizer.optimize(bug_description, self.context)

            # 验证返回结果不为空
            self.assertIsNotNone(result)
            self.assertIsInstance(result, str)
            self.assertTrue(len(result.strip()) > 0)

            print("=" * 80)
            print("🔧 BugDescOptimizer.optimize() 测试结果")
            print("=" * 80)
            print()
            print("📝 原始Bug描述:")
            print("-" * 40)
            print(bug_description.strip())
            print()
            print("✨ 优化后的Bug描述:")
            print("-" * 40)
            print(result)
            print()
            print("=" * 80)

            # 验证优化后的描述包含结构化内容
            # 根据get_prompt方法，应该包含这些结构化部分
            expected_sections = [
                "Issue Overview",
                "Problem Description", 
                "Reproduction Steps",
                "Expected Behavior",
                "Acceptance Criteria"
            ]

            found_sections = []
            for section in expected_sections:
                if section.lower() in result.lower():
                    found_sections.append(section)

            print(f"📊 结构化内容检查:")
            print(f"   期望的章节: {expected_sections}")
            print(f"   找到的章节: {found_sections}")
            print(f"   覆盖率: {len(found_sections)}/{len(expected_sections)}")

            # 验证至少包含一些结构化内容
            self.assertTrue(len(found_sections) > 0, 
                          f"优化后的描述应该包含结构化内容，但没有找到预期的章节")

            # 验证优化后的内容比原始内容更详细
            self.assertTrue(len(result) > len(bug_description), 
                          "优化后的描述应该比原始描述更详细")

            print(f"✅ 所有验证通过!")

        except Exception as e:
            print(f"❌ 模型调用失败: {e}")
            print(f"📄 错误详情: {type(e).__name__}: {str(e)}")
            
            # 如果是网络或配置问题，提供一些调试信息
            print("🔍 调试信息:")
            print(f"   Provider: {self.context.provider}")
            print(f"   Context类型: {type(self.context)}")
            
            # 测试prompt生成功能是否正常
            try:
                prompt = self.optimizer.get_prompt(bug_description)
                print(f"   Prompt生成: ✅ 正常 (长度: {len(prompt)})")
                
                # 验证prompt包含必要内容
                self.assertIn(bug_description.strip(), prompt)
                self.assertIn("Issue Overview", prompt)
                self.assertIn("Reproduction Steps", prompt)
                
            except Exception as prompt_error:
                print(f"   Prompt生成: ❌ 失败 - {prompt_error}")
                self.fail(f"Prompt生成失败: {prompt_error}")
            
            # 重新抛出原始异常以便测试失败
            self.fail(f"模型调用失败: {e}")

    def test_get_prompt_content(self):
        """测试 get_prompt 方法生成的内容"""
        test_description = "测试bug描述"
        
        prompt = self.optimizer.get_prompt(test_description)
        
        # 验证prompt包含必要的内容
        self.assertIn(test_description, prompt)
        self.assertIn("Issue Overview", prompt)
        self.assertIn("Problem Description", prompt)
        self.assertIn("Reproduction Steps", prompt)
        self.assertIn("Expected Behavior", prompt)
        self.assertIn("Acceptance Criteria", prompt)
        self.assertIn("numpy array", prompt)
        
        print("✅ get_prompt方法测试通过")
        print(f"📊 生成的prompt长度: {len(prompt)}")

    def test_provider_config_loading(self):
        """测试provider配置加载功能"""
        provider = self._get_provider_from_config()

        # 验证provider不为空
        self.assertIsNotNone(provider)
        self.assertIsInstance(provider, str)
        self.assertTrue(len(provider.strip()) > 0)

        # 验证context对象正确设置了provider
        self.assertIsNotNone(self.context.provider)
        self.assertEqual(self.context.provider, provider)

        print(f"✅ Provider配置加载测试通过")
        print(f"📊 当前使用的provider: {provider}")


if __name__ == '__main__':
    unittest.main()
