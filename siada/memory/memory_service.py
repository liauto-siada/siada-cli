"""
Memory服务模块

提供统一的接口来访问Memory缓存
"""
from typing import Dict, Generic, Optional, Type, TypeVar
import logging

from siada.memory.Memory import Memory
from siada.memory.cache.base import BaseMemoryCache
from siada.memory.cache.memory_cache import InMemoryCache
from siada.core.logging import logger

T = TypeVar('T')

class MemoryCacheNotInitializedError(Exception):
    """当Memory缓存未初始化时抛出的异常"""
    pass


class MemoryService(Generic[T]):
    """
    Memory服务类
    
    提供统一的接口来访问Memory缓存
    """
    
    _instance = None
    _cache: BaseMemoryCache = None
    
    @classmethod
    def get_instance(cls) -> 'MemoryService':
        """
        获取MemoryService的单例实例
        
        Returns:
            MemoryService实例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def init(cls, cache_impl: BaseMemoryCache = None) -> None:
        """
        初始化MemoryService
        
        Args:
            cache_impl: 缓存实现，默认为InMemoryCache
        """
        if cache_impl is None:
            cache_impl = InMemoryCache()
        cls._cache = cache_impl
    
    @classmethod
    async def get_memory(cls, session_id: str, agent_name: Optional[str] = None) -> Optional[Memory[T]]:
        """
        获取指定session_id的Memory实例
        
        Args:
            session_id: 会话ID
            agent_name: 代理名称，可选
            
        Returns:
            Memory实例，如果不存在则返回None
            
        Raises:
            MemoryCacheNotInitializedError: 当缓存未初始化时抛出
        """
        if cls._cache is None:
            logger.error("Memory缓存未初始化，请先调用MemoryService.init()")
            raise MemoryCacheNotInitializedError("Memory缓存未初始化，请先调用MemoryService.init()")
        
        memory = await cls._cache.get(session_id)
        if memory is None:
            memory = Memory.create(session_id=session_id, current_agent=agent_name, model_context=None)
            await cls._cache.set(memory)
        
        return memory
    
    @classmethod
    async def set_memory(cls, memory: Memory[T]) -> None:
        """
        设置或更新Memory实例
        
        Args:
            memory: Memory实例
            
        Raises:
            MemoryCacheNotInitializedError: 当缓存未初始化时抛出
        """
        if cls._cache is None:
            logger.error("Memory缓存未初始化，请先调用MemoryService.init()")
            raise MemoryCacheNotInitializedError("Memory缓存未初始化，请先调用MemoryService.init()")
        await cls._cache.set(memory)
    
    @classmethod
    async def delete_memory(cls, session_id: str) -> bool:
        """
        删除指定session_id的Memory实例
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否成功删除
            
        Raises:
            MemoryCacheNotInitializedError: 当缓存未初始化时抛出
        """
        if cls._cache is None:
            logger.error("Memory缓存未初始化，请先调用MemoryService.init()")
            raise MemoryCacheNotInitializedError("Memory缓存未初始化，请先调用MemoryService.init()")
        return await cls._cache.delete(session_id)
    
    @classmethod
    async def exists_memory(cls, session_id: str) -> bool:
        """
        检查指定session_id的Memory实例是否存在
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否存在
            
        Raises:
            MemoryCacheNotInitializedError: 当缓存未初始化时抛出
        """
        if cls._cache is None:
            logger.error("Memory缓存未初始化，请先调用MemoryService.init()")
            raise MemoryCacheNotInitializedError("Memory缓存未初始化，请先调用MemoryService.init()")
        return await cls._cache.exists(session_id)
    
    @classmethod
    async def clear_all(cls) -> None:
        """
        清空所有Memory实例
        
        Raises:
            MemoryCacheNotInitializedError: 当缓存未初始化时抛出
        """
        if cls._cache is None:
            logger.error("Memory缓存未初始化，请先调用MemoryService.init()")
            raise MemoryCacheNotInitializedError("Memory缓存未初始化，请先调用MemoryService.init()")
        await cls._cache.clear()
