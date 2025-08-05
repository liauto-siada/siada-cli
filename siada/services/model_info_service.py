"""
Model Information Service

Provides comprehensive model information, validation, and management capabilities.
This service acts as a centralized interface for model-related operations.
"""

from typing import List, Optional, Dict, Any
from dataclasses import asdict

from siada.models.model_base_config import ModelBaseConfig, MODEL_SETTING, get_model_config
from siada.models.model_run_config import ModelRunConfig


class ModelInfoService:
    """
    Service for managing and querying model information.
    
    This service provides methods to:
    - List available models
    - Get detailed model information
    - Validate model configurations
    - Search and filter models by capabilities
    """

    @staticmethod
    def get_all_models() -> List[ModelBaseConfig]:
        """
        Get all available model configurations.
        
        Returns:
            List[ModelBaseConfig]: List of all model configurations
        """
        return MODEL_SETTING.copy()

    @staticmethod
    def get_model_names() -> List[str]:
        """
        Get a list of all available model names.
        
        Returns:
            List[str]: List of model names
        """
        return [model.model_name for model in MODEL_SETTING]

    @staticmethod
    def get_model_info(model_name: str) -> Optional[ModelBaseConfig]:
        """
        Get detailed information for a specific model.
        
        Args:
            model_name: Name of the model to query
            
        Returns:
            Optional[ModelBaseConfig]: Model configuration if found, None otherwise
        """
        return get_model_config(model_name)

    @staticmethod
    def is_model_supported(model_name: str) -> bool:
        """
        Check if a model is supported.
        
        Args:
            model_name: Name of the model to check
            
        Returns:
            bool: True if model is supported, False otherwise
        """
        return get_model_config(model_name) is not None

    @staticmethod
    def get_models_with_images() -> List[ModelBaseConfig]:
        """
        Get all models that support image processing.
        
        Returns:
            List[ModelBaseConfig]: List of models with image support
        """
        return [model for model in MODEL_SETTING if model.supports_images]

    @staticmethod
    def search_models(query: str, case_sensitive: bool = False) -> List[ModelBaseConfig]:
        """
        Search for models by name.
        
        Args:
            query: Search query string
            case_sensitive: Whether to perform case-sensitive search (default: False)
            
        Returns:
            List[ModelBaseConfig]: List of models matching the search query
        """
        if not case_sensitive:
            query = query.lower()
        
        results = []
        for model in MODEL_SETTING:
            model_name = model.model_name if case_sensitive else model.model_name.lower()
            if query in model_name:
                results.append(model)
        
        return results
