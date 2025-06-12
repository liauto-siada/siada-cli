"""
Memory缓存抽象接口模块

定义Memory缓存的抽象接口
"""
from abc import ABC, abstractmethod
from typing import Dict, Generic, Optional, TypeVar

from src.memory.Memory import Memory

T = TypeVar('T')


class BaseMemoryCache(Generic[T], ABC):
    """
    Memory缓存的抽象基类
    
    定义了Memory缓存的基本操作接口
    """
    
    @abstractmethod
    async def get(self, session_id: str) -> Optional[Memory[T]]:
        """
        获取指定session_id的Memory实例
        
        Args:
            session_id: 会话ID
            
        Returns:
            Memory实例，如果不存在则返回None
        """
        pass
    
    @abstractmethod
    async def set(self, memory: Memory[T]) -> None:
        """
        设置或更新Memory实例
        
        Args:
            memory: Memory实例
        """
        pass
    
    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """
        删除指定session_id的Memory实例
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否成功删除
        """
        pass
    
    @abstractmethod
    async def exists(self, session_id: str) -> bool:
        """
        检查指定session_id的Memory实例是否存在
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否存在
        """
        pass
    
    @abstractmethod
    async def clear(self) -> None:
        """
        清空所有Memory实例
        """
        pass
