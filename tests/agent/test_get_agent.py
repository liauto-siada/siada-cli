"""
SiadaRunner.get_agent 方法测试

测试基于配置文件的Agent获取功能
"""
import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, mock_open

from siada.services.siada_runner import SiadaRunner
from siada.agent_hub.coder.bug_fix_agent import BugFixAgent


class TestGetAgent(unittest.IsolatedAsyncioTestCase):
    """测试 SiadaRunner.get_agent 方法"""

    def setUp(self):
        """测试前准备"""
        # 创建测试用的配置内容
        self.valid_config = {
            'agents': {
                'bugfix': {
                    'class': 'siada.agent_hub.coder.bug_fix_agent.BugFixAgent',
                    'description': '专门用于代码bug修复的Agent',
                    'enabled': True
                },
                'coder': {
                    'class': None,
                    'description': '通用代码开发Agent',
                    'enabled': False
                },
                'testdisabled': {
                    'class': 'siada.agent_hub.coder.bug_fix_agent.BugFixAgent',
                    'description': '测试禁用的Agent',
                    'enabled': False
                }
            }
        }

    async def test_get_agent_bugfix_success(self):
        """测试成功获取 bugfix agent"""
        with patch('siada.services.siada_runner.SiadaRunner._load_agent_config') as mock_load:
            mock_load.return_value = self.valid_config['agents']
            
            agent = await SiadaRunner.get_agent("bugfix")
            
            self.assertIsInstance(agent, BugFixAgent)
            self.assertEqual(agent.name, "BugFixAgent")

    async def test_get_agent_case_insensitive(self):
        """测试大小写不敏感的名称匹配"""
        with patch('siada.services.siada_runner.SiadaRunner._load_agent_config') as mock_load:
            mock_load.return_value = self.valid_config['agents']
            
            # 测试大写
            agent1 = await SiadaRunner.get_agent("BUGFIX")
            self.assertIsInstance(agent1, BugFixAgent)
            
            # 测试混合大小写
            agent2 = await SiadaRunner.get_agent("BugFix")
            self.assertIsInstance(agent2, BugFixAgent)

    async def test_get_agent_name_variations(self):
        """测试名称变体支持（下划线、连字符）"""
        with patch('siada.services.siada_runner.SiadaRunner._load_agent_config') as mock_load:
            mock_load.return_value = self.valid_config['agents']
            
            # 测试下划线
            agent1 = await SiadaRunner.get_agent("bug_fix")
            self.assertIsInstance(agent1, BugFixAgent)
            
            # 测试连字符
            agent2 = await SiadaRunner.get_agent("bug-fix")
            self.assertIsInstance(agent2, BugFixAgent)

    async def test_get_agent_disabled_agent(self):
        """测试获取禁用的Agent时抛出异常"""
        with patch('siada.services.siada_runner.SiadaRunner._load_agent_config') as mock_load:
            mock_load.return_value = self.valid_config['agents']
            
            with self.assertRaises(ValueError) as context:
                await SiadaRunner.get_agent("coder")
            
            self.assertIn("is disabled", str(context.exception))

    async def test_get_agent_disabled_agent_custom(self):
        """测试获取自定义禁用的Agent时抛出异常"""
        with patch('siada.services.siada_runner.SiadaRunner._load_agent_config') as mock_load:
            mock_load.return_value = self.valid_config['agents']
            
            with self.assertRaises(ValueError) as context:
                await SiadaRunner.get_agent("testdisabled")
            
            self.assertIn("is disabled", str(context.exception))

    async def test_get_agent_unknown_agent(self):
        """测试获取不存在的Agent时抛出异常"""
        with patch('siada.services.siada_runner.SiadaRunner._load_agent_config') as mock_load:
            mock_load.return_value = self.valid_config['agents']
            
            with self.assertRaises(ValueError) as context:
                await SiadaRunner.get_agent("unknown")
            
            self.assertIn("Unsupported agent type", str(context.exception))
            self.assertIn("Supported agent types: ['bugfix']", str(context.exception))

    async def test_get_agent_empty_name(self):
        """测试空字符串Agent名称时抛出异常"""
        with patch('siada.services.siada_runner.SiadaRunner._load_agent_config') as mock_load:
            mock_load.return_value = self.valid_config['agents']
            
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
        
        with patch('siada.services.siada_runner.SiadaRunner._load_agent_config') as mock_load:
            mock_load.return_value = config
            
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
        
        with patch('siada.services.siada_runner.SiadaRunner._load_agent_config') as mock_load:
            mock_load.return_value = config
            
            with self.assertRaises(ImportError) as context:
                await SiadaRunner.get_agent("invalid")
            
            self.assertIn("Failed to import agent class", str(context.exception))

    def test_load_agent_config_file_not_found(self):
        """测试配置文件不存在时抛出异常"""
        with patch('pathlib.Path.exists', return_value=False):
            with self.assertRaises(FileNotFoundError) as context:
                SiadaRunner._load_agent_config()
            
            self.assertIn("Agent configuration file not found", str(context.exception))

    def test_load_agent_config_success(self):
        """测试成功加载配置文件"""
        import yaml
        
        config_content = yaml.dump(self.valid_config)
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=config_content)):
                result = SiadaRunner._load_agent_config()
                
                self.assertEqual(result, self.valid_config['agents'])

    def test_import_agent_class_success(self):
        """测试成功导入Agent类"""
        class_path = "siada.agent_hub.coder.bug_fix_agent.BugFixAgent"
        
        agent_class = SiadaRunner._import_agent_class(class_path)
        
        self.assertEqual(agent_class, BugFixAgent)

    def test_import_agent_class_invalid_path(self):
        """测试导入无效类路径时抛出异常"""
        class_path = "invalid.path"
        
        with self.assertRaises(ModuleNotFoundError):
            SiadaRunner._import_agent_class(class_path)

    async def test_get_agent_multiple_instances(self):
        """测试多次获取Agent实例是否正常"""
        with patch('siada.services.siada_runner.SiadaRunner._load_agent_config') as mock_load:
            mock_load.return_value = self.valid_config['agents']
            
            # 获取多个实例
            agent1 = await SiadaRunner.get_agent("bugfix")
            agent2 = await SiadaRunner.get_agent("bugfix")
            
            # 验证都是BugFixAgent实例
            self.assertIsInstance(agent1, BugFixAgent)
            self.assertIsInstance(agent2, BugFixAgent)
            
            # 验证是不同的实例（每次调用都创建新实例）
            self.assertIsNot(agent1, agent2)

    async def test_get_agent_config_reload(self):
        """测试配置文件重新加载功能"""
        # 第一次调用
        with patch('siada.services.siada_runner.SiadaRunner._load_agent_config') as mock_load:
            mock_load.return_value = self.valid_config['agents']
            
            agent1 = await SiadaRunner.get_agent("bugfix")
            self.assertIsInstance(agent1, BugFixAgent)
            
            # 验证配置加载被调用
            mock_load.assert_called()

        # 第二次调用（模拟配置文件变更）
        modified_config = {
            'bugfix': {
                'class': 'siada.agent_hub.coder.bug_fix_agent.BugFixAgent',
                'description': '修改后的描述',
                'enabled': True
            }
        }
        
        with patch('siada.services.siada_runner.SiadaRunner._load_agent_config') as mock_load:
            mock_load.return_value = modified_config
            
            agent2 = await SiadaRunner.get_agent("bugfix")
            self.assertIsInstance(agent2, BugFixAgent)
            
            # 验证配置重新加载
            mock_load.assert_called()


if __name__ == '__main__':
    unittest.main()
