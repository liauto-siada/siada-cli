"""
Checkpointer Recommendation Service - 检查点推荐功能

This package provides intelligent checkpoint file discovery and recommendation for /restore commands.
When users type /restore followed by text, the system provides real-time checkpoint file suggestions.

Main Components:
- CheckPointService: Main service for checkpoint file discovery and search
- CheckpointFile: Data structure representing a checkpoint file
- create_checkpoint_service: Factory function for creating service instances

Usage:
    from siada.services.checkpointer_recommendation import CheckPointService, create_checkpoint_service
    
    service = create_checkpoint_service(
        cwd=os.getcwd(),
        session_id="current_session_id"
    )
    
    # List all checkpoint files
    all_checkpoints = service.list_checkpoint_files()
    
    # Search checkpoints by query
    matching_checkpoints = service.search_checkpoints("edit")
"""

from .checkpoint_recommend import CheckPointRecommendEngine, CheckpointFile, create_checkpoint_recommend_engine

__all__ = [
    'CheckPointRecommendEngine',
    'CheckpointFile', 
    'create_checkpoint_recommend_engine'
]

# Version information
__version__ = '1.0.0'
__author__ = 'Siada Team'
__description__ = 'Intelligent checkpoint file discovery and recommendation for /restore commands'
