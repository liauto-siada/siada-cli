from typing import Optional
import logging
from uuid import uuid4

from siada.entrypoint.interaction.interaction_controller import InteractionConfig
from siada.io.io import InputOutput
from siada.models.model_setting import ModelConfig
from siada.support.commands import SlashCommands

from .session_models import Session, SessionState
from siada.models.model_settings import ModelSettings

logger = logging.getLogger(__name__)


class InteractionSessionManager:
    
    @staticmethod
    def create_session(
        interaction_config: InteractionConfig,
        session_id: Optional[str] = None,
        db_path: Optional[str] = None,
    ) -> Session:
        """
        Create a new interaction session
        
        Args:
            config: Model configuration using ModelSettings structure
            session_id: Session ID, auto-generates UUID if not provided
            db_path: Database path for OpenAI SQLiteSession
            io: InputOutput instance
            
        Returns:
            Session: Created session object
        """
        # Use provided session_id or generate new UUID
        if session_id is None:
            session_id = str(uuid4())
        
        # Create interaction session
        session = Session(
            session_id=session_id,
            interaction_config= interaction_config,
        )
        
        # Create associated OpenAI SQLiteSession with same ID
        from agents import SQLiteSession
        
        # Create OpenAI Session
        openai_session = SQLiteSession(
            session_id=session_id,  # Use same ID
            db_path=db_path
        )
        session.state.openai_session = openai_session
        return session