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
        siada_config: RunningConfig,
        session_id: Optional[str] = None,
    ) -> RunningSession:
        """
        Create a new interaction session
        
        Args:
            siada_config: config of siada running
            session_id: Session ID, auto-generates UUID if not provided

        Returns:
            Session: Created session object
        """
        # Use provided session_id or generate new UUID
        if session_id is None:
            session_id = str(uuid4())
        
        # Create interaction session
        session = RunningSession(
            session_id=session_id,
            siada_config=siada_config,
        )
        
        # Create associated OpenAI SQLiteSession with same ID
        from agents import SQLiteSession
        
        # Create OpenAI Session
        openai_session = SQLiteSession(
            session_id=session_id,  # Use same ID
        )
        session.state.openai_session = openai_session
        return session

    @staticmethod
    def get_default_session():
        llm_config = ModelRunConfig.get_default_config()
        io = InputOutput()

        siada_config = RunningConfig(
            llm_config=llm_config,
            io=io,
            workspace='',
            agent_name='',
            console_output=True,
            interactive=False,
        )
        return RunningSessionManager.create_session(siada_config)
