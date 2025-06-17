"""
内存缓存实现模块

提供基于内存的Memory缓存实现
"""
from typing import Dict, Generic, Optional, TypeVar

from siada.memory.Memory import Memory
from siada.memory.cache.base import BaseMemoryCache

T = TypeVar('T')


class InMemoryCache(BaseMemoryCache[T], Generic[T]):
    """
    基于内存的Memory缓存实现
    
    使用字典存储session_id到Memory实例的映射
    """
    
    def __init__(self):
        """
        初始化内存缓存
        """
        self._cache: Dict[str, Memory[T]] = {}
    
    async def get(self, session_id: str) -> Optional[Memory[T]]:
        """
        获取指定session_id的Memory实例
        
        Args:
            session_id: 会话ID
            
        Returns:
            Memory实例，如果不存在则返回None
        """
        return self._cache.get(session_id)
    
    async def set(self, memory: Memory[T]) -> None:
        """
        设置或更新Memory实例
        
        Args:
            memory: Memory实例
        """
        self._cache[memory.session_id] = memory
    
    async def delete(self, session_id: str) -> bool:
        """
        删除指定session_id的Memory实例
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否成功删除
        """
        if session_id in self._cache:
            del self._cache[session_id]
            return True
        return False
    
    async def exists(self, session_id: str) -> bool:
        """
        检查指定session_id的Memory实例是否存在
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否存在
        """
        return session_id in self._cache
    
    async def clear(self) -> None:
        """
        清空所有Memory实例
        """
        self._cache.clear()
