from typing import Optional
import logging
import time

from siada.entrypoint.interaction.running_config import RunningConfig
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig
from siada.support.checkpoint_tracker import create_checkpoint_tracker

from .session_models import RunningSession

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
        # Use provided session_id or generate timestamp-based ID
        if session_id is None:
            # Generate session_id as current timestamp in milliseconds (13 digits)
            session_id = str(int(time.time() * 1000))
        
        # Create interaction session
        session = RunningSession(
            session_id=session_id,
            siada_config=siada_config,
        )
        
        # Create associated FileSession with same ID
        from siada.services.file_session import FileSession
        from siada.utils import DirectoryUtils
        
        # Create File Session with proper sessions directory
        sessions_dir = DirectoryUtils.get_global_sessions_dir(siada_config.workspace)
        file_session = FileSession(
            session_id=session_id,  # Use same ID
            sessions_dir=sessions_dir,
        )
        session.state.openai_session = file_session

        if siada_config.enable_checkpointing:
            session.checkpoint_tracker = create_checkpoint_tracker(
                cwd=siada_config.workspace, session_id=session_id
            )
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
