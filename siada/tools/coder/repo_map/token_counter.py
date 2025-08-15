"""
Token counting functionality for language models.

Provides token calculation with litellm integration and fallback estimation.
Supports any model with zero configuration and basic caching for performance.
"""

import logging
from typing import Optional


class TokenCounterModel:
    """
    Token counting model with litellm integration and fallback estimation.
    
    Uses litellm for accurate counting when available, otherwise falls back
    to simple estimation (4 characters ≈ 1 token). Supports any model name
    with basic caching mechanism.
    """
    
    def __init__(self, model_name: str):
        """
        Initialize TokenCounterModel instance.
        
        Args:
            model_name (str): Language model name (any name supported)
        """
        self.model_name = model_name
        self._litellm_available = self._check_litellm_availability()
        self._cache = {}
        
        logger = logging.getLogger(__name__)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Initialized TokenCounterModel: {self.model_name}")
    
    def token_count(self, text: str) -> int:
        """
        Calculate token count for given text.
        
        Args:
            text (str): Text to count tokens for
            
        Returns:
            int: Number of tokens
        """
        if not text:
            return 0
        
        text_hash = hash(text)
        if text_hash in self._cache:
            return self._cache[text_hash]
        
        try:
            if self._litellm_available:
                token_count = self._count_with_litellm(text)
            else:
                token_count = self._count_with_estimation(text)
            
            if len(self._cache) >= 1000:
                self._cache.clear()
            self._cache[text_hash] = token_count
            
            return token_count
            
        except Exception as e:
            logging.getLogger(__name__).warning(f"Token calculation failed, using estimation: {e}")
            return self._count_with_estimation(text)
    
    def _check_litellm_availability(self) -> bool:
        """Check if litellm is available."""
        try:
            from siada.provider.lazy_lite_llm import litellm
            return True
        except ImportError:
            return False
    
    def _count_with_litellm(self, text: str) -> int:
        """Count tokens using litellm."""
        from siada.provider.lazy_lite_llm import litellm
        response = litellm.token_counter(model=self.model_name, text=text)
        return int(response)
    
    def _count_with_estimation(self, text: str) -> int:
        """Count tokens using simple estimation (4 chars ≈ 1 token)."""
        return max(1, len(text) // 4)
    
    def __str__(self) -> str:
        """String representation."""
        return f"TokenCounterModel(model={self.model_name}, litellm={self._litellm_available})"
    
    def __repr__(self) -> str:
        """Detailed string representation."""
        return f"TokenCounterModel(model_name='{self.model_name}', litellm_available={self._litellm_available})"


class OptimizedTokenCounterModel(TokenCounterModel):
    """
    Optimized token counter for long texts and large codebases.
    
    Uses sampling for texts exceeding the threshold to improve performance.
    """
    
    def __init__(self, model_name: str, sampling_threshold: int = 10000):
        """
        Initialize optimized TokenCounterModel.
        
        Args:
            model_name (str): Model name
            sampling_threshold (int): Threshold for sampling, texts longer than this will use sampling
        """
        super().__init__(model_name)
        self.sampling_threshold = sampling_threshold
    
    def token_count(self, text: str) -> int:
        """
        Optimized token counting with sampling for long texts.
        
        Args:
            text (str): Text to count tokens for
            
        Returns:
            int: Number of tokens
        """
        if not text:
            return 0
        
        if len(text) <= self.sampling_threshold:
            return super().token_count(text)
        
        return self._count_with_sampling(text)
    
    def _count_with_sampling(self, text: str) -> int:
        """Count tokens for long text using sampling method."""
        lines = text.splitlines(keepends=True)
        num_lines = len(lines)
        
        if num_lines <= 100:
            return super().token_count(text)
        
        step = max(1, num_lines // 100)
        sampled_lines = lines[::step]
        sample_text = "".join(sampled_lines)
        
        sample_tokens = super().token_count(sample_text)
        
        sample_length = len(sample_text)
        total_length = len(text)
        
        if sample_length > 0:
            estimated_tokens = int(sample_tokens * total_length / sample_length)
        else:
            estimated_tokens = self._count_with_estimation(text)
        
        return estimated_tokens
