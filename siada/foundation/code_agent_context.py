from typing import Optional, Any
from pydantic import BaseModel, ConfigDict

from siada.session.session_models import RunningSession

from siada.foundation.logging import logger as logging

class CodeAgentContext(BaseModel):

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session: Optional[RunningSession] = None

    root_dir: str | None = None

    provider: str | None = None

    # Interactive mode flag, True for interactive mode, False for non-interactive mode
    interactive_mode: bool = True

    # Combined memory from all sources (rule_memory + user_memory + structured_memory)
    combined_memory: Optional[str] = None
    preferred_language: Optional[str] = None  # Preferred language for AI responses

    # MCP-related extensions
    mcp_service: Optional[Any] = None
    mcp_config: Optional[Any] = None
    mcp_enabled: bool = False

    # SiadaIgnore controller for file access control
    siadaignore_controller: Optional[Any] = None

    # Whether to enable human agreement mechanism for plan execution
    pre_plan: bool = False

    @property
    def task_message_state(self):
        return self.session.state.task_message_state

    @property
    def model_run_config(self):
        return self.session.siada_config.llm_config

    def save_checkpoints(self):
        if self.session and self.session.checkpoint_tracker:
            try:
                self.session.checkpoint_tracker.save_checkpoints(
                    session_id=self.session.session_id,
                    task_message_state=self.session.state.task_message_state,
                    usage=self.session.state.usage,
                )
            except Exception as e:
                logging.error(f"Error saving checkpoints: {e}")

    @property
    def session_id(self):
        if self.session:
            return self.session.session_id
        return None
    
    @property
    def auto_compact(self):
        if self.session:
            return self.session.siada_config.auto_compact
        return True

    @property
    def compaction_strategy_name(self):
        """User-configured compaction strategy override, or None for auto-detection."""
        if self.session:
            return self.session.siada_config.compaction_strategy
        return None

    @property
    def im_mode(self):
        """Whether running in IM (Lark) mode with chat-style compression.

        Uses SessionOwnershipManager.is_im_session() as the single source of truth,
        reading session_source from metadata.json on disk.
        """
        if self.session:
            from siada.session.ownership import SessionOwnershipManager
            return SessionOwnershipManager.is_im_session(self.session)
        return False
