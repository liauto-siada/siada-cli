"""
Tests for ProactiveConfig in config_loader.py
"""
import tempfile
from pathlib import Path
import yaml
import pytest

from siada.config.config_loader import ProactiveConfig, load_conf


class TestProactiveConfig:
    """Test ProactiveConfig data class"""
    
    def test_default_values(self):
        """Test ProactiveConfig default values"""
        config = ProactiveConfig()
        
        assert config.enabled is True
        assert config.work_hours == "09:00-18:00"
        assert config.trigger_interval == 60
        assert config.daily_task_execution_time == "08:30"
    
    def test_from_dict_full(self):
        """Test creating ProactiveConfig from full dictionary"""
        data = {
            'enabled': False,
            'work_hours': '08:00-17:00',
            'trigger_interval': 30,
            'daily_task_execution_time': '07:30'
        }
        
        config = ProactiveConfig.from_dict(data)
        
        assert config.enabled is False
        assert config.work_hours == "08:00-17:00"
        assert config.trigger_interval == 30
        assert config.daily_task_execution_time == "07:30"
    
    def test_from_dict_partial(self):
        """Test creating ProactiveConfig from partial dictionary (uses defaults)"""
        data = {
            'enabled': False,
            'trigger_interval': 120
        }
        
        config = ProactiveConfig.from_dict(data)
        
        assert config.enabled is False
        assert config.work_hours == "09:00-18:00"  # default
        assert config.trigger_interval == 120
        assert config.daily_task_execution_time == "08:30"  # default
    
    def test_from_dict_empty(self):
        """Test creating ProactiveConfig from empty dictionary (all defaults)"""
        data = {}
        
        config = ProactiveConfig.from_dict(data)
        
        assert config.enabled is True
        assert config.work_hours == "09:00-18:00"
        assert config.trigger_interval == 60
        assert config.daily_task_execution_time == "08:30"
    
    def test_to_dict(self):
        """Test converting ProactiveConfig to dictionary"""
        config = ProactiveConfig(
            enabled=False,
            work_hours="10:00-19:00",
            trigger_interval=45,
            daily_task_execution_time="09:00"
        )
        
        result = config.to_dict()
        
        assert result == {
            'enabled': False,
            'work_hours': '10:00-19:00',
            'trigger_interval': 45,
            'daily_task_execution_time': '09:00'
        }
    
    def test_immutability(self):
        """Test that ProactiveConfig is immutable (frozen=True)"""
        config = ProactiveConfig()
        
        with pytest.raises(AttributeError):
            config.enabled = False


class TestLoadConfProactive:
    """Test load_conf function with proactive configuration"""
    
    def test_load_proactive_config_from_yaml(self):
        """Test loading proactive config from YAML file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'conf.yaml'
            
            yaml_content = {
                'proactive': {
                    'enabled': False,
                    'work_hours': '08:30-17:30',
                    'trigger_interval': 90,
                    'daily_task_execution_time': '08:00'
                }
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(yaml_content, f)
            
            config = load_conf(config_path)
            
            assert config.proactive_config.enabled is False
            assert config.proactive_config.work_hours == "08:30-17:30"
            assert config.proactive_config.trigger_interval == 90
            assert config.proactive_config.daily_task_execution_time == "08:00"
    
    def test_load_proactive_config_partial(self):
        """Test loading partial proactive config (with defaults)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'conf.yaml'
            
            yaml_content = {
                'proactive': {
                    'enabled': False
                }
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(yaml_content, f)
            
            config = load_conf(config_path)
            
            assert config.proactive_config.enabled is False
            assert config.proactive_config.work_hours == "09:00-18:00"  # default
            assert config.proactive_config.trigger_interval == 60  # default
    
    def test_load_proactive_config_missing(self):
        """Test loading config without proactive section (uses all defaults)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'conf.yaml'
            
            yaml_content = {
                'llm_config': {
                    'model': 'gpt-4'
                }
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(yaml_content, f)
            
            config = load_conf(config_path)
            
            # Should use default ProactiveConfig
            assert config.proactive_config.enabled is True
            assert config.proactive_config.work_hours == "09:00-18:00"
            assert config.proactive_config.trigger_interval == 60
            assert config.proactive_config.daily_task_execution_time == "08:30"
    
    def test_load_config_file_not_exists(self):
        """Test loading config when file doesn't exist (uses defaults)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'non_existent.yaml'
            
            config = load_conf(config_path)
            
            # Should use default ProactiveConfig
            assert config.proactive_config.enabled is True
            assert config.proactive_config.work_hours == "09:00-18:00"
            assert config.proactive_config.trigger_interval == 60
    
    def test_proactive_config_type_conversion(self):
        """Test type conversions in proactive config"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'conf.yaml'
            
            yaml_content = {
                'proactive': {
                    'enabled': 'true',  # string that should be treated as True
                    'trigger_interval': '120'  # string that should be converted to int
                }
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(yaml_content, f)
            
            config = load_conf(config_path)
            
            # YAML should handle the conversion
            assert isinstance(config.proactive_config.enabled, bool)
            assert isinstance(config.proactive_config.trigger_interval, int)


class TestProactiveConfigIntegration:
    """Integration tests for proactive config with other configs"""
    
    def test_proactive_with_other_configs(self):
        """Test that proactive config works alongside other configurations"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'conf.yaml'
            
            yaml_content = {
                'llm_config': {
                    'model': 'gpt-4',
                    'provider': 'openai'
                },
                'checkpoint_config': {
                    'enable': True,
                    'max_checkpoint_files': 5
                },
                'proactive': {
                    'enabled': True,
                    'work_hours': '09:00-18:00'
                },
                'command_timeout': 300
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(yaml_content, f)
            
            config = load_conf(config_path)
            
            # Check all configs are loaded correctly
            assert config.llm_config.model == 'gpt-4'
            assert config.checkpoint_config.enable is True
            assert config.proactive_config.enabled is True
            assert config.proactive_config.work_hours == "09:00-18:00"
            assert config.command_timeout == 300
