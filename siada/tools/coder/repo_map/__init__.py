"""
Repo Map模块 - 代码仓库地图生成工具

该模块提供了生成代码仓库地图的完整功能，包括：
- 代码文件分析和标签提取
- 基于PageRank算法的文件重要性排序
- 智能的代码结构展示
- 高性能的token计算
- 灵活的IO处理

主要组件：
- RepoMap: 核心仓库地图生成器
- IO: 标准输入输出处理器
- TokenCounterModel: token计算模型
- Tag: 代码标签数据结构
"""

from .repo_map import RepoMap, Tag
from .io import IO, SilentIO, FileIO
from .token_counter import TokenCounterModel, OptimizedTokenCounterModel
from .dump import dump
from .special import filter_important_files, is_important
from .waiting import Spinner, WaitingSpinner

__all__ = [
    # 核心类
    'RepoMap',
    'Tag',
    
    # IO类
    'IO',
    'SilentIO', 
    'FileIO',
    
    # Token计算类
    'TokenCounterModel',
    'OptimizedTokenCounterModel',
    
    # 工具函数
    'dump',
    'filter_important_files',
    'is_important',
    
    # 等待/进度指示器
    'Spinner',
    'WaitingSpinner',
]

# 版本信息
__version__ = '1.0.0'

# 模块级别的便捷函数
def create_repo_map(
    root_path: str,
    model_name: str = "claude-3-5-sonnet-20241022",
    verbose: bool = False,
    map_tokens: int = 1024,
    **kwargs
) -> RepoMap:
    """
    创建RepoMap实例的便捷函数
    
    Args:
        root_path (str): 仓库根目录路径
        model_name (str): 语言模型名称，默认为Claude 3.5 Sonnet
        verbose (bool): 是否启用详细输出
        map_tokens (int): 地图最大token数量
        **kwargs: 其他RepoMap参数
        
    Returns:
        RepoMap: 配置好的RepoMap实例
        
    Example:
        >>> repo_map = create_repo_map("/path/to/repo", verbose=True)
        >>> result = repo_map.get_repo_map(chat_files=[], other_files=python_files)
    """
    io = IO(verbose=verbose)
    model = TokenCounterModel(model_name)
    
    return RepoMap(
        root=root_path,
        main_model=model,
        io=io,
        verbose=verbose,
        map_tokens=map_tokens,
        **kwargs
    )


def create_optimized_repo_map(
    root_path: str,
    model_name: str = "claude-3-5-sonnet-20241022",
    verbose: bool = False,
    map_tokens: int = 8192,
    sampling_threshold: int = 10000,
    **kwargs
) -> RepoMap:
    """
    创建优化版RepoMap实例的便捷函数
    
    适用于大型代码仓库，使用优化的token计算器
    
    Args:
        root_path (str): 仓库根目录路径
        model_name (str): 语言模型名称
        verbose (bool): 是否启用详细输出
        map_tokens (int): 地图最大token数量，默认8192
        sampling_threshold (int): 采样阈值
        **kwargs: 其他RepoMap参数
        
    Returns:
        RepoMap: 配置好的优化版RepoMap实例
    """
    io = IO(verbose=verbose)
    model = OptimizedTokenCounterModel(model_name, sampling_threshold)
    
    return RepoMap(
        root=root_path,
        main_model=model,
        io=io,
        verbose=verbose,
        map_tokens=map_tokens,
        **kwargs
    )


def create_silent_repo_map(
    root_path: str,
    model_name: str = "claude-3-5-sonnet-20241022",
    map_tokens: int = 1024,
    **kwargs
) -> RepoMap:
    """
    创建静默版RepoMap实例的便捷函数
    
    适用于测试或需要静默运行的场景
    
    Args:
        root_path (str): 仓库根目录路径
        model_name (str): 语言模型名称
        map_tokens (int): 地图最大token数量
        **kwargs: 其他RepoMap参数
        
    Returns:
        RepoMap: 配置好的静默版RepoMap实例
    """
    io = SilentIO()
    model = TokenCounterModel(model_name)
    
    return RepoMap(
        root=root_path,
        main_model=model,
        io=io,
        verbose=False,
        map_tokens=map_tokens,
        **kwargs
    )
