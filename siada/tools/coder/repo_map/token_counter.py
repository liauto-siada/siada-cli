"""
TokenCounterModel类 - 超级极简版本

该模块提供基于不同语言模型的token计算功能，采用超级极简设计：
- 优先使用litellm进行精确token计算
- 提供简单的fallback估算机制
- 支持任何模型，零配置
- 内置基础缓存，提高性能
"""

import logging
from typing import Optional


class TokenCounterModel:
    """
    Token计数模型类 - 超级极简版本
    
    专注于核心功能：
    - 优先使用litellm进行精确计算
    - litellm不可用时使用简单估算（4字符≈1token）
    - 支持任何模型名称，零配置
    - 基础缓存机制
    """
    
    def __init__(self, model_name: str):
        """
        初始化TokenCounterModel实例
        
        Args:
            model_name (str): 语言模型名称（任何名称都支持）
        """
        self.model_name = model_name
        self._litellm_available = self._check_litellm_availability()
        self._cache = {}  # 简单的缓存
        
        # 只在debug模式下记录日志
        logger = logging.getLogger(__name__)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"初始化TokenCounterModel: {self.model_name}")
    
    def token_count(self, text: str) -> int:
        """
        计算文本的token数量
        
        Args:
            text (str): 要计算token数量的文本
            
        Returns:
            int: token数量
        """
        if not text:
            return 0
        
        # 简单缓存检查
        text_hash = hash(text)
        if text_hash in self._cache:
            return self._cache[text_hash]
        
        try:
            if self._litellm_available:
                token_count = self._count_with_litellm(text)
            else:
                token_count = self._count_with_estimation(text)
            
            # 简单缓存管理
            if len(self._cache) >= 1000:  # 防止内存无限增长
                self._cache.clear()
            self._cache[text_hash] = token_count
            
            return token_count
            
        except Exception as e:
            # 任何错误都fallback到估算
            logging.getLogger(__name__).warning(f"Token计算失败，使用估算: {e}")
            return self._count_with_estimation(text)
    
    def _check_litellm_availability(self) -> bool:
        """检查litellm是否可用"""
        try:
            import litellm
            return True
        except ImportError:
            return False
    
    def _count_with_litellm(self, text: str) -> int:
        """使用litellm计算token数量"""
        import litellm
        response = litellm.token_counter(model=self.model_name, text=text)
        return int(response)
    
    def _count_with_estimation(self, text: str) -> int:
        """使用简单估算方法计算token数量"""
        return max(1, len(text) // 4)  # 4字符≈1token
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"TokenCounterModel(model={self.model_name}, litellm={self._litellm_available})"
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return f"TokenCounterModel(model_name='{self.model_name}', litellm_available={self._litellm_available})"


class OptimizedTokenCounterModel(TokenCounterModel):
    """
    优化版本的Token计数模型
    
    针对长文本进行了优化，适用于处理大型代码库
    """
    
    def __init__(self, model_name: str, sampling_threshold: int = 10000):
        """
        初始化优化版TokenCounterModel
        
        Args:
            model_name (str): 模型名称
            sampling_threshold (int): 采样阈值，超过此长度的文本将使用采样计算
        """
        super().__init__(model_name)
        self.sampling_threshold = sampling_threshold
    
    def token_count(self, text: str) -> int:
        """
        优化的token计算方法，对长文本使用采样
        
        Args:
            text (str): 要计算的文本
            
        Returns:
            int: token数量
        """
        if not text:
            return 0
        
        # 对于短文本，使用标准方法
        if len(text) <= self.sampling_threshold:
            return super().token_count(text)
        
        # 对于长文本，使用采样方法
        return self._count_with_sampling(text)
    
    def _count_with_sampling(self, text: str) -> int:
        """使用采样方法计算长文本的token数量"""
        lines = text.splitlines(keepends=True)
        num_lines = len(lines)
        
        if num_lines <= 100:
            return super().token_count(text)
        
        # 采样计算
        step = max(1, num_lines // 100)
        sampled_lines = lines[::step]
        sample_text = "".join(sampled_lines)
        
        # 计算采样文本的token数
        sample_tokens = super().token_count(sample_text)
        
        # 按比例估算总token数
        sample_length = len(sample_text)
        total_length = len(text)
        
        if sample_length > 0:
            estimated_tokens = int(sample_tokens * total_length / sample_length)
        else:
            estimated_tokens = self._count_with_estimation(text)
        
        return estimated_tokens
