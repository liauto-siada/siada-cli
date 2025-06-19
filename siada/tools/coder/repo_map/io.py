"""
IO类 - 提供标准的输入输出接口

该模块提供了RepoMap使用的标准IO接口，包括：
- 不同级别的日志输出（info, warning, error）
- 文件读取功能
- 可配置的输出选项
"""

import os
import sys
from typing import Optional, TextIO
from pathlib import Path


class IO:
    """
    标准IO类，提供文件读取和日志输出功能
    
    该类为RepoMap提供统一的IO接口，支持：
    - 多级别日志输出
    - 文件内容读取
    - 可配置的输出目标
    - 详细模式控制
    """
    
    def __init__(
        self, 
        verbose: bool = False,
        output_stream: Optional[TextIO] = None,
        error_stream: Optional[TextIO] = None
    ):
        """
        初始化IO实例
        
        Args:
            verbose (bool): 是否启用详细输出模式
            output_stream (TextIO, optional): 标准输出流，默认为sys.stdout
            error_stream (TextIO, optional): 错误输出流，默认为sys.stderr
        """
        self.verbose = verbose
        self.output_stream = output_stream or sys.stdout
        self.error_stream = error_stream or sys.stderr
        
        # 统计信息
        self.outputs = []
        self.warnings = []
        self.errors = []
    
    def tool_output(self, message: str) -> None:
        """
        输出信息消息
        
        Args:
            message (str): 要输出的消息
        """
        self.outputs.append(message)
        if self.verbose:
            print(f"[INFO] {message}", file=self.output_stream)
    
    def tool_warning(self, message: str) -> None:
        """
        输出警告消息
        
        Args:
            message (str): 要输出的警告消息
        """
        self.warnings.append(message)
        print(f"[WARNING] {message}", file=self.error_stream)
    
    def tool_error(self, message: str) -> None:
        """
        输出错误消息
        
        Args:
            message (str): 要输出的错误消息
        """
        self.errors.append(message)
        print(f"[ERROR] {message}", file=self.error_stream)
    
    def read_text(self, filepath: str) -> str:
        """
        读取文件内容
        
        Args:
            filepath (str): 文件路径
            
        Returns:
            str: 文件内容，如果读取失败则返回空字符串
        """
        try:
            # 确保路径是绝对路径或相对于当前工作目录的路径
            path = Path(filepath)
            
            # 尝试不同的编码方式
            encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin1']
            
            for encoding in encodings:
                try:
                    with open(path, 'r', encoding=encoding) as f:
                        content = f.read()
                    return content
                except UnicodeDecodeError:
                    continue
            
            # 如果所有编码都失败，尝试二进制模式读取并忽略错误
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if self.verbose:
                self.tool_warning(f"文件 {filepath} 使用fallback编码读取")
            
            return content
            
        except FileNotFoundError:
            self.tool_error(f"文件不存在: {filepath}")
            return ""
        except PermissionError:
            self.tool_error(f"没有权限读取文件: {filepath}")
            return ""
        except IsADirectoryError:
            self.tool_error(f"路径是目录而不是文件: {filepath}")
            return ""
        except Exception as e:
            self.tool_error(f"读取文件失败 {filepath}: {str(e)}")
            return ""
    
    def clear_stats(self) -> None:
        """清除统计信息"""
        self.outputs.clear()
        self.warnings.clear()
        self.errors.clear()
    
    def get_stats(self) -> dict:
        """
        获取统计信息
        
        Returns:
            dict: 包含输出、警告、错误数量的字典
        """
        return {
            'outputs': len(self.outputs),
            'warnings': len(self.warnings),
            'errors': len(self.errors)
        }
    
    def set_verbose(self, verbose: bool) -> None:
        """
        设置详细模式
        
        Args:
            verbose (bool): 是否启用详细输出
        """
        self.verbose = verbose


class SilentIO(IO):
    """
    静默IO类，不输出任何信息到控制台
    
    适用于测试或需要静默运行的场景
    """
    
    def __init__(self):
        """初始化静默IO实例"""
        super().__init__(verbose=False)
    
    def tool_output(self, message: str) -> None:
        """静默记录输出消息"""
        self.outputs.append(message)
    
    def tool_warning(self, message: str) -> None:
        """静默记录警告消息"""
        self.warnings.append(message)
    
    def tool_error(self, message: str) -> None:
        """静默记录错误消息"""
        self.errors.append(message)


class FileIO(IO):
    """
    文件IO类，将输出重定向到文件
    
    适用于需要将日志保存到文件的场景
    """
    
    def __init__(
        self, 
        log_file: str,
        verbose: bool = True,
        append: bool = True
    ):
        """
        初始化文件IO实例
        
        Args:
            log_file (str): 日志文件路径
            verbose (bool): 是否启用详细输出
            append (bool): 是否追加到现有文件
        """
        self.log_file = Path(log_file)
        self.append = append
        
        # 确保日志目录存在
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 打开日志文件
        mode = 'a' if append else 'w'
        self.log_stream = open(self.log_file, mode, encoding='utf-8')
        
        super().__init__(
            verbose=verbose,
            output_stream=self.log_stream,
            error_stream=self.log_stream
        )
    
    def __del__(self):
        """析构函数，确保文件被正确关闭"""
        if hasattr(self, 'log_stream') and not self.log_stream.closed:
            self.log_stream.close()
    
    def close(self):
        """手动关闭日志文件"""
        if hasattr(self, 'log_stream') and not self.log_stream.closed:
            self.log_stream.close()
