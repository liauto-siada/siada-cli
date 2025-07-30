from typing import Optional
import logging
from uuid import uuid4

from siada.entrypoint.interaction.config import RunningConfig
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig
from siada.support.slash_commands import SlashCommands

from .session_models import RunningSession, SessionState
from siada.models.model_base_config import ModelBaseConfig

logger = logging.getLogger(__name__)


class RunningSessionManager:
    
    @staticmethod
    def create_session(
        running_config: RunningConfig,
        session_id: Optional[str] = None,
    ) -> RunningSession:
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
        session = RunningSession(
            session_id=session_id,
            running_config=running_config,
        )
        
        # Create associated OpenAI SQLiteSession with same ID
        from agents import SQLiteSession
        
        # Create OpenAI Session
        openai_session = SQLiteSession(
            session_id=session_id,  # Use same ID
        )
        session.state.openai_session = openai_session
        return session