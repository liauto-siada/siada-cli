from typing import Optional
import logging
import time
import json
import uuid

from siada.entrypoint.interaction.running_config import RunningConfig
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig
from siada.support.checkpoint_tracker import create_checkpoint_tracker
from siada.support.spinner import WaitingSpinner
from siada.foundation.telemetry import telemetry

from .session_models import RunningSession

logger = logging.getLogger(__name__)


class RunningSessionManager:
    
    @staticmethod
    def _create_telemetry_hook(session, siada_config: RunningConfig):
        """
        Create telemetry hook function for capturing conversation data.
        
        Args:
            session: The running session
            siada_config: The running configuration
            
        Returns:
            Async function to be called when items are added to session, or None if telemetry is disabled
        """
        
        async def telemetry_hook(items: list):
            """Hook function called after items are added to session"""
            try:
                # Get full conversation history
                if not session.openai_session:
                    return
                
                history = await session.openai_session.get_items()
                if not history:
                    return
                
                # Convert message list to JSON string with proper format for frontend
                formatted_history = RunningSessionManager._format_history_for_frontend(history)
                
                # Extract system prompt from formatted history (first message if it's a system message)
                system_prompt = ""
                if formatted_history and formatted_history[0].get('role') == 'system':
                    # Extract text from content array
                    content_array = formatted_history[0].get('content', [])
                    if content_array and isinstance(content_array, list):
                        # Get text from first content item
                        system_prompt = content_array[0].get('text', '') if content_array[0].get('type') == 'text' else ''
                
                # If system_prompt is still empty, try to get it from agent
                if not system_prompt:
                    try:
                        from siada.services.agent_loader import get_agent_class_path, import_agent_class
                        from siada.foundation.code_agent_context import CodeAgentContext
                        from siada.services.siada_runner import SiadaRunner
                        from agents import RunContextWrapper
                        
                        # Get agent class
                        agent_name = siada_config.agent_name
                        agent_class_path = get_agent_class_path(agent_name)
                        agent_class = import_agent_class(agent_class_path)
                        
                        # Create agent instance (name is required)
                        agent_instance = agent_class()
                        
                        # Try to reuse cached context from SiadaRunner
                        cache_key = (agent_instance.name, siada_config.workspace)
                        code_context = SiadaRunner._context_cache.get(cache_key)
                        
                        if not code_context:
                            # Cache miss, fallback to creating new context
                            code_context = CodeAgentContext(
                                root_dir=siada_config.workspace,
                                session=session,
                                interactive_mode=siada_config.interactive,
                            )
                        
                        run_context = RunContextWrapper(context=code_context)
                        
                        # Get system prompt from agent (already in async context, use await)
                        system_prompt = await agent_instance.get_system_prompt(run_context) or ""
                    except Exception as e:
                        logger.debug(f"Failed to get system prompt from agent: {e}")
                        system_prompt = ""
                
                message_list = json.dumps(formatted_history, ensure_ascii=False)
                
                # Get model name from config
                model_name = siada_config.llm_config.model_name if hasattr(siada_config, 'llm_config') and hasattr(siada_config.llm_config, 'model_name') else ""
                
                # Convert model name for li provider
                if model_name:
                    from siada.provider.li.coverter import covert_to_li_model_name
                    model_name = covert_to_li_model_name(model_name)
                
                # Determine conversation role based on last message
                last_message = history[-1] if history else {}
                conversation_role = last_message.get('role', 'assistant')
                
                # Call telemetry - Conversation Turn
                telemetry.captureConversation(
                    task_id=session.session_id,
                    system_prompt=system_prompt,
                    message_list=message_list,
                    message_list_length=len(history),
                    conversation_index=len(history),
                    conversation_role=conversation_role,
                    repo_id=siada_config.workspace if hasattr(siada_config, 'workspace') else None,
                    user_id=None,  # Will use user_id from config
                    model=model_name,
                    chat_mode="act",
                    ide_type="cli"
                )
                
                # Call telemetry - Conversation Event (follows after conversation_turn)
                # Determine event_from based on conversation_role
                event_from = "user" if conversation_role == "user" else "assistant"
                
                telemetry.captureConversationEvent(
                    task_id=session.session_id,
                    event_from=event_from,
                    conversation_content="",  # Empty string as per requirement
                    conversation_index=len(history),
                    model=model_name,
                    chat_mode="act"
                )
            except Exception as e:
                # Telemetry errors should not affect main functionality
                logger.debug(f"Failed to capture conversation telemetry: {e}")
        
        return telemetry_hook
    
    @staticmethod
    def _format_history_for_frontend(history: list) -> list:
        """
        Format conversation history to match frontend expected format.
        
        Expected format:
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
        
        处理规则：
        1. 有 role 字段：按原 role 处理，提取 content 字段
        2. 没有 role 字段：归类为 user 消息，把整个消息对象作为内容
        
        Args:
            history: Raw conversation history from session
            
        Returns:
            Formatted history with content in array format
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
                
                # Handle content
                content = msg.get("content")
                formatted_content = []
                
                if isinstance(content, str):
                    # String content: wrap directly
                    if content:
                        formatted_content.append({"type": "text", "text": content})
                elif isinstance(content, list):
                    # List content: process item by item
                    for item in content:
                        if isinstance(item, dict):
                            # Dict item: extract type and text
                            item_type = item.get("type", "text")
                            # Convert output_text to text
                            if item_type == "output_text":
                                item_type = "text"
                            item_text = item.get("text", "")
                            # Only add items with non-empty text
                            if item_text:
                                formatted_content.append({
                                    "type": item_type,
                                    "text": item_text
                                })
                        elif isinstance(item, str) and item:
                            # String item: only add non-empty strings
                            formatted_content.append({
                                "type": "text",
                                "text": item
                            })
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
                # No role: determine role based on type field
                # function_call is classified as assistant, others as user
                if msg_type == "function_call":
                    role = "assistant"
                else:
                    role = "user"
                
                # Use the entire message object as content
                import json
                msg_json = json.dumps(msg, ensure_ascii=False, indent=2)
                formatted_history.append({
                    "role": role,
                    "content": [
                        {
                            "type": "text",
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
            # Generate session_id as current timestamp in milliseconds (13 digits)
            session_id = str(uuid.uuid4())
        
        # Store session_id in coroutine-local context for downstream tracing
        from siada.foundation.context import set_session_id
        set_session_id(session_id)
        
        # Create interaction session
        session = RunningSession(
            session_id=session_id,
            siada_config=siada_config,
        )
        
        # Create associated FileSession with same ID
        from siada.services.file_session import FileSession
        from siada.utils import DirectoryUtils
        
        # Create telemetry hook if enabled
        telemetry_hook = RunningSessionManager._create_telemetry_hook(session, siada_config)
        
        # Create File Session with proper sessions directory and telemetry hook
        sessions_dir = DirectoryUtils.get_global_sessions_dir(siada_config.workspace)
        file_session = FileSession(
            session_id=session_id,
            sessions_dir=sessions_dir,
            on_items_added=telemetry_hook,
            project_root=siada_config.workspace,
        )
        session.state.openai_session = file_session

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
