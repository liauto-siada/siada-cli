from typing import Optional
import logging
import time
import json
import uuid

from siada.entrypoint.interaction.running_config import RunningConfig
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig
from siada.support.checkpoint_tracker import create_checkpoint_tracker
from siada.support.message_classifier import get_role_and_type_from_item
from siada.support.spinner import WaitingSpinner

from .session_models import RunningSession

logger = logging.getLogger(__name__)


class RunningSessionManager:
    
    @staticmethod
    def _create_telemetry_hook(session, siada_config: RunningConfig):
        """Disable conversation collection in the public distribution.

        FileSession accepts a missing callback. Returning None also avoids
        reading conversation history or rebuilding prompts for an inert client.
        """
        return None
    
    @staticmethod
    def _format_history_for_telemetry(history: list) -> list:
        """Retain the legacy history formatter for API compatibility.

        This helper does not collect or transmit data. Frontend rendering uses
        ``siada.support.message_classifier.format_native_items_for_display``,
        which strips injected context blocks before showing chat messages.
        Callers of this formatter receive the original message content.

        Output format:

        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "..."},
                    {"type": "text", "text": "..."}
                ]
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "..."}
                ]
            }
        ]

        Rules:
          1. ``role`` present  → classify by role, expand ``content``.
          2. ``role`` missing  → fall back to user/assistant by item type
             (function_call / reasoning → assistant; others → user); embed
             the whole raw message JSON to preserve tool-call content.
        """
        formatted_history = []

        for msg in history:
            msg_type = msg.get("type", "")

            # Check if role field exists
            if "role" in msg:
                # Has role: process according to original role
                role = msg.get("role")
                if not role:
                    continue

                # Handle content. Note: we forward text verbatim — no
                # injection-block stripping here, that is the frontend
                # display layer's job.
                content = msg.get("content")
                formatted_content = []

                if isinstance(content, str):
                    if content:
                        formatted_content.append({"type": "text", "text": content})
                elif isinstance(content, list):
                    # List content: process item by item
                    for item in content:
                        if isinstance(item, dict):
                            # Dict item: keep the real type from the message item
                            # (e.g. "output_text", "reasoning_text", "text"), do not
                            # rewrite it to "text".
                            item_type = item.get("type", "text")
                            item_text = item.get("text", "")
                            # Only add items with non-empty text
                            if item_text:
                                formatted_content.append({
                                    "type": item_type,
                                    "text": item_text
                                })
                        elif isinstance(item, str) and item:
                            # String item: only add non-empty strings
                            formatted_content.append({"type": "text", "text": item})
                elif content:
                    # Other types: convert to string
                    formatted_content.append({
                        "type": "text",
                        "text": str(content)
                    })

                # Only add messages with non-empty content
                if formatted_content:
                    formatted_history.append({
                        "role": role,
                        "content": formatted_content
                    })
            else:
                # No role: determine role based on type field.  Native
                # Responses items (``apply_patch_call``, ``shell_call``,
                # ``local_shell_call``, ``custom_tool_call``, ``reasoning`` ...)
                # carry no ``role`` at all, so classify them with the shared
                # classifier instead of defaulting every unknown type to a user
                # message — that used to file model-generated patch calls under
                # ``role: "user"`` in the telemetry payload.
                #
                # Only the assistant verdict is adopted here: this telemetry
                # schema distinguishes just user/assistant, so tool outputs
                # (``*_call_output``) deliberately stay ``user``.
                classified_role, _ = get_role_and_type_from_item(msg)
                role = "assistant" if classified_role == "assistant" else "user"

                # Use the entire message object as content, keep the real
                # message type (e.g. "reasoning", "function_call",
                # "function_call_output") instead of hardcoding "text".
                import json
                msg_json = json.dumps(msg, ensure_ascii=False, indent=2)
                item_type = msg_type if msg_type else "text"
                formatted_history.append({
                    "role": role,
                    "content": [
                        {
                            "type": item_type,
                            "text": msg_json
                        }
                    ]
                })

        return formatted_history

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
            from siada.foundation.id_generator import generate_session_id
            session_id = generate_session_id()
        
        # Store session_id in coroutine-local context for downstream tracing
        from siada.foundation.context import set_session_id
        set_session_id(session_id)
        
        # Create interaction session
        session = RunningSession(
            session_id=session_id,
            siada_config=siada_config,
        )
        
        # Register a lazy factory for FileSession so that the agents SDK
        # (imported by file_session.py at module level) is not pulled in on the
        # startup critical path.  The factory is called on first access to
        # session.state.openai_session (inside the agent run loop).
        from siada.utils import DirectoryUtils
        telemetry_hook = RunningSessionManager._create_telemetry_hook(session, siada_config)
        sessions_dir = DirectoryUtils.get_global_sessions_dir(siada_config.workspace)
        _sid, _sdir, _hook, _root = session_id, sessions_dir, telemetry_hook, siada_config.workspace

        def _file_session_factory():
            from siada.services.file_session import FileSession
            return FileSession(
                session_id=_sid,
                sessions_dir=_sdir,
                on_items_added=_hook,
                project_root=_root,
            )

        session.state._openai_session_factory = _file_session_factory

        if siada_config.checkpointing_config and siada_config.checkpointing_config.enable:
            # Get max_checkpoint_files from config, default to 50 if not set
            max_files = siada_config.checkpointing_config.max_checkpoint_files or 50
            session.checkpoint_tracker = create_checkpoint_tracker(
                cwd=siada_config.workspace, 
                session_id=session_id,
                max_checkpoint_files=max_files
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
