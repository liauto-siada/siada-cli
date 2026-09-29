"""
SiadaRunner.get_agent 方法测试

测试基于配置文件的Agent获取功能
"""
import unittest
from unittest.mock import patch, mock_open

from siada.services.siada_runner import SiadaRunner
from siada.services import agent_loader
from siada.agent_hub.coder.code_gen_agent import CodeGenAgent

CODE_GEN_CLASS_PATH = 'siada.agent_hub.coder.code_gen_agent.CodeGenAgent'


class TestGetAgent(unittest.IsolatedAsyncioTestCase):
    """测试 SiadaRunner.get_agent 方法"""

    def setUp(self):
        """测试前准备"""
        # Clear the agent cache so tests never observe each other's instances
        # (get_agent uses a stale-while-revalidate class-level cache).
        SiadaRunner._agent_cache.clear()

        # 创建测试用的配置内容
        self.valid_config = {
            'coder': {
                'class': CODE_GEN_CLASS_PATH,
                'description': '通用代码开发Agent',
                'enabled': True
            },
            'testdisabled': {
                'class': CODE_GEN_CLASS_PATH,
                'description': '测试禁用的Agent',
                'enabled': False
            }
        }

    def _patch_config(self, agents):
        """Patch agent_loader.load_agent_config so get_agent_class_path runs
        its real normalization / enabled / implemented checks against the
        given agents dict."""
        return patch.object(agent_loader, 'load_agent_config', return_value=agents)

    async def test_get_agent_coder_success(self):
        """测试成功获取 coder agent"""
        with self._patch_config(self.valid_config):
            agent = await SiadaRunner.get_agent("coder")

            self.assertIsInstance(agent, CodeGenAgent)
            self.assertEqual(agent.name, "CodeGenAgent")

    async def test_get_agent_case_insensitive(self):
        """测试大小写不敏感的名称匹配"""
        with self._patch_config(self.valid_config):
            # 测试大写
            agent1 = await SiadaRunner.get_agent("CODER")
            self.assertIsInstance(agent1, CodeGenAgent)

            # 测试混合大小写
            agent2 = await SiadaRunner.get_agent("Coder")
            self.assertIsInstance(agent2, CodeGenAgent)

    async def test_get_agent_name_variations(self):
        """测试名称变体支持（下划线、连字符）"""
        with self._patch_config(self.valid_config):
            # 测试下划线
            agent1 = await SiadaRunner.get_agent("co_der")
            self.assertIsInstance(agent1, CodeGenAgent)

            # 测试连字符
            agent2 = await SiadaRunner.get_agent("co-der")
            self.assertIsInstance(agent2, CodeGenAgent)

    async def test_get_agent_disabled_agent(self):
        """测试获取禁用的Agent时抛出异常"""
        with self._patch_config(self.valid_config):
            with self.assertRaises(ValueError) as context:
                await SiadaRunner.get_agent("testdisabled")

            self.assertIn("is disabled", str(context.exception))

    async def test_get_agent_disabled_agent_custom(self):
        """测试获取自定义禁用的Agent时抛出异常"""
        config = {
            'customdisabled': {
                'class': CODE_GEN_CLASS_PATH,
                'description': '自定义禁用的Agent',
                'enabled': False
            }
        }

        with self._patch_config(config):
            with self.assertRaises(ValueError) as context:
                await SiadaRunner.get_agent("customdisabled")

            self.assertIn("is disabled", str(context.exception))

    async def test_get_agent_unknown_agent(self):
        """测试获取不存在的Agent时抛出异常"""
        with self._patch_config(self.valid_config):
            with self.assertRaises(ValueError) as context:
                await SiadaRunner.get_agent("unknown")

            self.assertIn("Unsupported agent type", str(context.exception))
            self.assertIn("Supported agent types: ['coder']", str(context.exception))

    async def test_get_agent_empty_name(self):
        """测试空字符串Agent名称时抛出异常"""
        with self._patch_config(self.valid_config):
            with self.assertRaises(ValueError) as context:
                await SiadaRunner.get_agent("")

            self.assertIn("Unsupported agent type", str(context.exception))

    async def test_get_agent_unimplemented_agent(self):
        """测试获取未实现的Agent时抛出异常"""
        config = {
            'unimplemented': {
                'class': None,
                'description': '未实现的Agent',
                'enabled': True
            }
        }

        with self._patch_config(config):
            with self.assertRaises(ValueError) as context:
                await SiadaRunner.get_agent("unimplemented")

            self.assertIn("is not implemented yet", str(context.exception))

    async def test_get_agent_import_error(self):
        """测试导入错误时抛出异常"""
        config = {
            'invalid': {
                'class': 'non.existent.module.InvalidAgent',
                'description': '无效的Agent',
                'enabled': True
            }
        }

        with self._patch_config(config):
            with self.assertRaises(ImportError) as context:
                await SiadaRunner.get_agent("invalid")

            self.assertIn("Failed to import agent class", str(context.exception))

    def test_load_agent_config_file_not_found(self):
        """测试配置文件不存在时抛出异常"""
        with patch('pathlib.Path.exists', return_value=False):
            with self.assertRaises(FileNotFoundError) as context:
                agent_loader.load_agent_config()

            self.assertIn("Agent configuration file not found", str(context.exception))

    def test_load_agent_config_success(self):
        """测试成功加载配置文件"""
        import yaml

        config_content = yaml.dump({'agents': self.valid_config})

        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=config_content)):
                result = agent_loader.load_agent_config()

                self.assertEqual(result, self.valid_config)

    def test_import_agent_class_success(self):
        """测试成功导入Agent类"""
        agent_class = agent_loader.import_agent_class(CODE_GEN_CLASS_PATH)

        self.assertEqual(agent_class, CodeGenAgent)

    def test_import_agent_class_invalid_path(self):
        """测试导入无效类路径时抛出异常"""
        class_path = "invalid.path"

        with self.assertRaises(ModuleNotFoundError):
            agent_loader.import_agent_class(class_path)

    async def test_get_agent_config_reload(self):
        """测试配置文件重新加载功能"""
        # 第一次调用
        with self._patch_config(self.valid_config) as mock_load:
            agent1 = await SiadaRunner.get_agent("coder")
            self.assertIsInstance(agent1, CodeGenAgent)

            # 验证配置加载被调用
            mock_load.assert_called()

        # 第二次调用（模拟配置文件变更）
        modified_config = {
            'coder': {
                'class': CODE_GEN_CLASS_PATH,
                'description': '修改后的描述',
                'enabled': True
            }
        }

        SiadaRunner._agent_cache.clear()
        with self._patch_config(modified_config) as mock_load:
            agent2 = await SiadaRunner.get_agent("coder")
            self.assertIsInstance(agent2, CodeGenAgent)

            # 验证配置重新加载
            mock_load.assert_called()


if __name__ == '__main__':
    unittest.main()
