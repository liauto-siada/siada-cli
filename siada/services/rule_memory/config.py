"""
Rule Memory Configuration Management

Handles configuration for the hierarchical context file system.
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

from siada.foundation.constants import SIADA_HOME

logger = logging.getLogger(__name__)


class RuleConfig:
    """Configuration for Rule memory system"""
    
    # Default configuration values
    DEFAULT_FILE_NAME = "siada_rule.md"
    DEFAULT_IMPORT_FORMAT = "tree"  # "tree" or "flat"
    DEFAULT_MAX_DIRS = 200
    DEFAULT_RESPECT_GITIGNORE = True
    DEFAULT_RESPECT_SIADAIGNORE = True
    DEFAULT_ENABLE_SUBDIRECTORIES = False  # Default: only load global and project root
    
    def __init__(self):
        self.config_dir = self._get_config_dir()
        self.config_file = os.path.join(self.config_dir, "settings.json")
        self._config_data = self._load_config()
    
    def _get_config_dir(self) -> str:
        """Get the configuration directory path"""
        config_dir = str(SIADA_HOME)
        
        # Create directory if it doesn't exist
        os.makedirs(config_dir, exist_ok=True)
        
        return config_dir
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from settings.json"""
        if not os.path.exists(self.config_file):
            return {}
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config from {self.config_file}: {e}")
            return {}
    
    def _save_config(self):
        """Save configuration to settings.json"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save config to {self.config_file}: {e}")
    
    def get_context_config(self) -> Dict[str, Any]:
        """Get context configuration section"""
        return self._config_data.get('context', {})
    
    def get_file_names(self) -> List[str]:
        """Get context file names to search for"""
        context = self.get_context_config()
        file_name = context.get('fileName', self.DEFAULT_FILE_NAME)
        
        if isinstance(file_name, str):
            return [file_name]
        elif isinstance(file_name, list):
            return file_name
        else:
            return [self.DEFAULT_FILE_NAME]
    
    def get_import_format(self) -> str:
        """Get import format: 'tree' or 'flat'"""
        context = self.get_context_config()
        format_type = context.get('importFormat', self.DEFAULT_IMPORT_FORMAT)
        
        if format_type not in ['tree', 'flat']:
            return self.DEFAULT_IMPORT_FORMAT
        
        return format_type
    
    def get_max_dirs(self) -> int:
        """Get maximum number of directories to search"""
        context = self.get_context_config()
        max_dirs = context.get('discoveryMaxDirs', self.DEFAULT_MAX_DIRS)
        
        try:
            return int(max_dirs)
        except (ValueError, TypeError):
            return self.DEFAULT_MAX_DIRS
    
    def get_include_directories(self) -> List[str]:
        """Get additional directories to include in search"""
        context = self.get_context_config()
        return context.get('includeDirectories', [])
    
    def get_respect_gitignore(self) -> bool:
        """Check if .gitignore should be respected"""
        context = self.get_context_config()
        filtering = context.get('fileFiltering', {})
        return filtering.get('respectGitIgnore', self.DEFAULT_RESPECT_GITIGNORE)
    
    def get_respect_siadaignore(self) -> bool:
        """Check if .siadaignore should be respected"""
        context = self.get_context_config()
        filtering = context.get('fileFiltering', {})
        return filtering.get('respectSiadaIgnore', self.DEFAULT_RESPECT_SIADAIGNORE)
    
    def get_enable_subdirectories(self) -> bool:
        """Check if subdirectory discovery is enabled"""
        context = self.get_context_config()
        return context.get('enableSubdirectories', self.DEFAULT_ENABLE_SUBDIRECTORIES)
    
    def get_global_file_path(self) -> str:
        """Get path to global context file"""
        return os.path.join(self.config_dir, self.get_file_names()[0])
    
    def set_context_config(self, key: str, value: Any):
        """Set a context configuration value"""
        if 'context' not in self._config_data:
            self._config_data['context'] = {}
        
        self._config_data['context'][key] = value
        self._save_config()


# Global config instance
_global_config: Optional[RuleConfig] = None


def get_rule_config() -> RuleConfig:
    """Get the global Rule configuration instance"""
    global _global_config
    if _global_config is None:
        _global_config = RuleConfig()
    return _global_config
