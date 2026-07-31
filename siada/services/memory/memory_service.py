"""
Memory Service Module

Provides session memory storage functionality, converting FileSession data
into human-readable Markdown format for archival and future retrieval.
"""

import re
import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Set

from siada.services.file_session import FileSession
from siada.services.memory.memory_db import MemoryDatabase
from siada.foundation.logging import logger


class MemoryServiceConfig:
    """Configuration constants for MemoryService."""
    
    # Slug generation
    SLUG_TIMEOUT: float = 30.0
    CONTENT_PREVIEW_LENGTH: int = 2000
    MAX_SLUG_LENGTH: int = 30
    DEFAULT_SLUG: str = 'session'
    
    # File operations
    TEMP_FILE_SUFFIX: str = '.tmp'
    
    # Message validation
    VALID_ROLES: Set[str] = {'user', 'assistant'}
    VALID_CONTENT_TYPES: Set[str] = {'text', 'output_text'}
    COMMAND_PREFIX: str = '/'


@dataclass
class SessionMetadata:
    """Metadata for a memory session."""
    
    session_id: str
    timestamp: datetime
    date_str: str
    time_str: str
    datetime_str: str  # YYYY-MM-DD-HH-MM format for filename
    workspace: Optional[str] = None  # Absolute path to the working directory


class MemoryService:
    """
    Memory Service for storing conversation history in Markdown format.
    
    Converts FileSession data into organized Markdown files stored in
    ~/.siada-cli/workspace/memory/ directory.
    """
    
    # Approximate ratio for token-to-char conversion (4 chars ≈ 1 token)
    _CHARS_PER_TOKEN: float = 4.0

    def __init__(
        self, 
        memory_dir: Optional[Path] = None, 
        slug_message_limit: int = 4,
        max_session_tokens: Optional[int] = None,
    ):
        """
        Initialize the Memory Service.
        
        Args:
            memory_dir: Directory to store memory files. Defaults to ~/.siada-cli/workspace/memory/
            slug_message_limit: Number of recent messages to use for slug generation. Defaults to 4.
            max_session_tokens: Max tokens for session content. Reads from model_base_config
                (fast model's context_window) if None; defaults to 200_000 if not found.
        """
        if memory_dir is None:
            memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
        
        self.memory_dir = Path(memory_dir)
        self.session_dir = self.memory_dir / "session"
        self.slug_message_limit = slug_message_limit

        # Resolve max session char limit from config or default
        if max_session_tokens is None:
            max_session_tokens = self._resolve_max_session_tokens()
        self.max_session_chars = int(max_session_tokens * self._CHARS_PER_TOKEN)
        
        # Ensure memory directory and session subdirectory exist
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
    def _resolve_max_session_tokens(self) -> int:
        """Resolve max session tokens from fast model's context_window in model_base_config.
        
        Falls back to 200_000 if the config lookup fails.
        """
        try:
            from siada.models.model_base_config import get_model_config
            from siada.provider.fast_llm import _resolve_fast_model_name
            model_name = _resolve_fast_model_name()
            cfg = get_model_config(model_name)
            if cfg and cfg.context_window:
                logger.info(
                    f"[memory-service] max_session_tokens resolved from "
                    f"{model_name}.context_window={cfg.context_window}"
                )
                return cfg.context_window
        except Exception:
            pass
        default = 150_000
        logger.info(
            f"[memory-service] max_session_tokens fallback to default={default}"
        )
        return default
    
    async def save_session_memory(
        self, 
        file_session: FileSession,
        workspace: Optional[str] = None,
    ) -> Optional[str]:
        """
        Save session conversation history to a Markdown memory file.
        
        Supports two modes:
        - Append mode: If LAST_MEMORY_NAME exists in global cache, updates existing file
        - New mode: Creates new file and saves path to global cache
        
        Automatically triggers derived memory update using global LLM_CONFIG.
        
        Args:
            file_session: FileSession object containing conversation history
            workspace: Absolute path to the working directory for this session
        Returns:
            Path to the created/updated memory file, or None if failed
        """
        try:
            logger.info("[memory-service] Starting to save session memory")
            
            # Step 1: Prepare session data
            all_messages = await self._get_all_messages(file_session)
            if not all_messages:
                logger.info("[memory-service] No messages to save")
                return None
            
            # Step 1.a: Truncate to fit within LLM context window
            all_messages, was_truncated = self._truncate_messages(all_messages)
            if was_truncated:
                logger.info(
                    f"[memory-service] Messages truncated from original count "
                    f"to {len(all_messages)} (max_session_chars={self.max_session_chars})"
                )
            
            # Step 2: Create session metadata
            metadata = self._create_session_metadata(file_session, workspace=workspace)
            
            # Step 3: Determine mode and save file
            memory_file = await self._determine_and_save(
                all_messages, metadata, was_truncated=was_truncated
            )
            if not memory_file:
                return None
            
            # Step 4: Post-save operations (indexing and derived memory)
            self._post_save_operations(memory_file, all_messages)
            
            return str(memory_file)
            
        except Exception as e:
            logger.error(f"[memory-service] Failed to save session memory: {e}")
            return None
    
    def _create_session_metadata(
        self,
        file_session: FileSession,
        workspace: Optional[str] = None,
    ) -> SessionMetadata:
        """
        Create session metadata for memory file.
        
        Args:
            file_session: FileSession object
            workspace: Absolute path to the working directory
            
        Returns:
            SessionMetadata object with timestamp information
        """
        now = datetime.now()
        return SessionMetadata(
            session_id=file_session.session_id,
            timestamp=now,
            date_str=now.strftime("%Y-%m-%d"),
            time_str=now.strftime("%H:%M:%S"),
            datetime_str=now.strftime("%Y-%m-%d-%H-%M"),
            workspace=workspace,
        )
    
    async def _determine_and_save(
        self,
        all_messages: List[Dict[str, str]],
        metadata: SessionMetadata,
        *,
        was_truncated: bool = False,
    ) -> Optional[Path]:
        """
        Determine save mode (append or new) and save the memory file.
        
        Args:
            all_messages: All messages to save
            metadata: Session metadata
            was_truncated: Whether the messages were truncated
            
        Returns:
            Path to the saved file, or None if failed
        """
        from siada.foundation.global_cache import get_global_cache, LAST_MEMORY_NAME
        
        last_memory_file = get_global_cache(LAST_MEMORY_NAME)
        
        if last_memory_file and Path(last_memory_file).exists():
            return await self._save_in_append_mode(
                Path(last_memory_file), all_messages, metadata,
                was_truncated=was_truncated,
            )
        else:
            return await self._save_in_new_mode(
                all_messages, metadata, was_truncated=was_truncated
            )
    
    async def _save_in_append_mode(
        self,
        memory_file: Path,
        all_messages: List[Dict[str, str]],
        metadata: SessionMetadata,
        *,
        was_truncated: bool = False,
    ) -> Optional[Path]:
        """
        Save in append mode: update existing file with all messages.
        
        Args:
            memory_file: Existing memory file path
            all_messages: All messages to save
            metadata: Session metadata
            was_truncated: Whether the messages were truncated
            
        Returns:
            Path to the updated file
        """
        logger.info(f"[memory-service] Append mode: updating existing file {memory_file.name}")
        
        markdown_content = self._format_markdown_content(
            messages=all_messages,
            session_id=metadata.session_id,
            timestamp=metadata.timestamp,
            date_str=metadata.date_str,
            time_str=metadata.time_str,
            workspace=metadata.workspace,
            was_truncated=was_truncated,
        )
        
        self._write_file_atomically(memory_file, markdown_content)
        logger.info(f"[memory-service] Memory file updated: {memory_file}")
        
        return memory_file
    
    async def _save_in_new_mode(
        self,
        all_messages: List[Dict[str, str]],
        metadata: SessionMetadata,
        *,
        was_truncated: bool = False,
    ) -> Optional[Path]:
        """
        Save in new mode: create new file with generated slug.
        
        Args:
            all_messages: All messages to save
            metadata: Session metadata
            was_truncated: Whether the messages were truncated
            
        Returns:
            Path to the created file
        """
        from siada.foundation.global_cache import set_global_cache, LAST_MEMORY_NAME
        
        logger.info("[memory-service] New mode: creating new memory file")
        
        # Generate slug from recent messages
        slug = await self._generate_slug_for_session(all_messages, metadata)
        
        # Create unique filename
        memory_file = self._create_unique_filename(metadata.datetime_str, slug)
        
        # Format and write content
        markdown_content = self._format_markdown_content(
            messages=all_messages,
            session_id=metadata.session_id,
            timestamp=metadata.timestamp,
            date_str=metadata.date_str,
            time_str=metadata.time_str,
            workspace=metadata.workspace,
            was_truncated=was_truncated,
        )
        
        self._write_file_atomically(memory_file, markdown_content)
        logger.info(f"[memory-service] Memory file created: {memory_file}")
        
        # Save to global cache for future appends
        set_global_cache(LAST_MEMORY_NAME, str(memory_file))
        logger.info(f"[memory-service] Saved memory file path to global cache: {memory_file}")
        
        return memory_file
    
    async def _generate_slug_for_session(
        self,
        all_messages: List[Dict[str, str]],
        metadata: SessionMetadata
    ) -> str:
        """
        Generate slug for session using recent messages.
        
        Args:
            all_messages: All messages in session
            metadata: Session metadata (for fallback timestamp)
            
        Returns:
            Generated slug string
        """
        # Get recent N messages for slug generation
        recent_messages = (
            all_messages[-self.slug_message_limit:]
            if len(all_messages) > self.slug_message_limit
            else all_messages
        )
        
        # Try LLM generation
        session_content = self._format_messages_for_slug(recent_messages)
        slug = await self._generate_slug_via_llm(session_content)
        
        # Fallback to timestamp
        if not slug:
            slug = metadata.timestamp.strftime("%H%M")
            logger.info(f"[memory-service] No LLM slug generated, using time fallback: {slug}")
        else:
            logger.info(f"[memory-service] Generated LLM slug: {slug}")
        
        return slug
    
    def _create_unique_filename(self, datetime_str: str, slug: str) -> Path:
        """
        Create unique filename by appending counter if needed.
        
        Args:
            datetime_str: DateTime string (YYYY-MM-DD-HH-MM)
            slug: Slug string
            
        Returns:
            Unique file path in session subdirectory
        """
        filename = f"{datetime_str}-{slug}.md"
        memory_file = self.session_dir / filename
        
        counter = 1
        while memory_file.exists():
            filename = f"{datetime_str}-{slug}-{counter}.md"
            memory_file = self.session_dir / filename
            counter += 1
        
        return memory_file
    
    def _write_file_atomically(self, file_path: Path, content: str) -> None:
        """
        Write content to file atomically using a temporary file.
        
        Args:
            file_path: Target file path
            content: Content to write
        """
        temp_file = file_path.with_suffix(MemoryServiceConfig.TEMP_FILE_SUFFIX)
        try:
            temp_file.write_text(content, encoding='utf-8')
            temp_file.replace(file_path)
        finally:
            # Clean up temp file if it still exists
            if temp_file.exists():
                temp_file.unlink()
    
    def _post_save_operations(
        self,
        memory_file: Path,
        all_messages: List[Dict[str, str]]
    ) -> None:
        """
        Perform post-save operations: indexing.
        
        Derived memory update (session summary + experience extraction) is handled
        by the scheduler's periodic analyze_recent_sessions job rather than being
        triggered immediately after each save.
        
        Args:
            memory_file: Path to saved memory file
            all_messages: All messages that were saved
        """
        # Index the file into SQLite + FTS5
        self._index_memory_file(memory_file)
    
    async def _get_all_messages(
        self, 
        file_session: FileSession
    ) -> List[Dict[str, Any]]:
        """
        Get ALL user/assistant messages for memory persistence.

        Delegates the storage-layer policy (compressed snapshot + delta tail
        vs. raw api_history fallback) to ``FileSession.get_effective_messages``.
        This method is only responsible for filtering and shaping the final
        ``user``/``assistant`` text view used by memory files.

        For test mocks that don't implement ``get_effective_messages``, we
        gracefully fall back to ``get_items()`` (legacy behavior).

        Args:
            file_session: FileSession object to read from

        Returns:
            List of all message dictionaries with 'role' and 'content' keys
        """
        try:
            items = await self._fetch_effective_items(file_session)
            if not items:
                return []

            all_messages = []
            for item in items:
                # Items can be direct messages or wrapped in various formats
                message = self._extract_message_from_item(item)
                if message:
                    all_messages.append(message)

            logger.info(
                f"[memory-service] Extracted {len(all_messages)} user/assistant "
                f"messages (raw_items={len(items)})"
            )
            return all_messages

        except Exception as e:
            logger.error(f"[memory-service] Error reading messages: {e}")
            return []

    async def _fetch_effective_items(
        self, file_session: FileSession
    ) -> List[Any]:
        """Fetch the effective item list, with safe fallbacks for test mocks.

        Resolution:
          1. ``file_session.get_effective_messages()`` if available — this is
             the canonical view (compressed snapshot + delta tail, with raw
             history fallback baked in at the storage layer).
          2. Otherwise ``file_session.get_items()`` — covers MockFileSession
             objects in unit tests that only implement the bare ``get_items``
             interface.
        """
        getter = getattr(file_session, "get_effective_messages", None)
        if callable(getter):
            try:
                return list(await getter())
            except Exception as e:
                logger.warning(
                    f"[memory-service] get_effective_messages failed, "
                    f"falling back to api_history: {e}"
                )
        return list(await file_session.get_items() or [])
    
    def _truncate_messages(
        self, messages: List[Dict[str, str]]
    ) -> tuple[List[Dict[str, str]], bool]:
        """Truncate messages to fit within ``max_session_chars``.
        
        With the upstream switch to compressed snapshots
        (``FileSession.get_effective_messages``), the input is already
        bounded by the LLM context window, so a per-user-turn cap is no
        longer needed. We only enforce the character budget here as a
        defensive guardrail.
        
        Strategy: keep the most recent messages, drop the oldest ones
        whose inclusion would push total chars over the limit. At least
        one message is always retained — even if it alone exceeds the
        budget — so the resulting memory file is never empty.
        
        Returns:
            (truncated_messages, was_truncated) tuple
        """
        if not messages:
            return messages, False
        
        total = 0
        keep = []
        for msg in reversed(messages):
            msg_len = len(msg.get("content", ""))
            if total + msg_len > self.max_session_chars and keep:
                break
            total += msg_len
            keep.append(msg)
        keep.reverse()
        
        was_truncated = len(keep) < len(messages)
        return keep, was_truncated
    
    def _extract_message_from_item(self, item: Any) -> Optional[Dict[str, str]]:
        """
        Extract message content from a session item.
        
        Args:
            item: Session item (can be dict, object, etc.)
            
        Returns:
            Dictionary with 'role' and 'content', or None if not a valid message
        """
        try:
            # Extract role and content from item
            role = self._get_role_from_item(item)
            if not self._is_valid_role(role):
                return None
            
            # Extract text content
            text = self._extract_text_from_item(item)
            if not text or self._is_command(text):
                return None
            
            return {'role': role, 'content': text}
            
        except Exception as e:
            logger.debug(f"[memory-service] Error extracting message: {e}")
            return None
    
    def _get_role_from_item(self, item: Any) -> Optional[str]:
        """
        Get role from item (dict or object).
        
        Args:
            item: Session item
            
        Returns:
            Role string, or None if not found
        """
        if isinstance(item, dict):
            return item.get('role')
        elif hasattr(item, 'role'):
            return getattr(item, 'role', None)
        return None
    
    def _is_valid_role(self, role: Optional[str]) -> bool:
        """
        Check if role is valid (user or assistant).
        
        Args:
            role: Role string to validate
            
        Returns:
            True if valid, False otherwise
        """
        return role in MemoryServiceConfig.VALID_ROLES
    
    def _extract_text_from_item(self, item: Any) -> str:
        """
        Extract text content from item.
        
        Args:
            item: Session item
            
        Returns:
            Extracted text content, or empty string if not found
        """
        content = self._get_content_from_item(item)
        if not content:
            return ''
        
        # Handle string content (user messages)
        if isinstance(content, str):
            return self._strip_injection_blocks(content)

        # Handle list content (assistant messages with blocks)
        if isinstance(content, list):
            return self._strip_injection_blocks(
                self._extract_text_from_blocks(content)
            )

        return ''

    @staticmethod
    def _strip_injection_blocks(text: str) -> str:
        """Remove every known sentinel-wrapped injection block from ``text``.

        Two injection families are stripped:

        * Holographic-prefetch facts (``CodeGenAgent._inject_holographic_prefetch``).
        * Feishu/Lark IM context blocks — quoted reply, conversation info,
          mention hints (``LarkAgentExecutor._build_user_input``).

        Both are content *we* wrote into the user message for LLM priming;
        memory extraction must never treat them as user-authored, otherwise
        the review agent learns "user preferences" from our own output.
        """
        if not text:
            return text
        # Lazy import keeps the holographic package out of the cold-start
        # path of the broader memory service.
        from siada.services.memory.holographic.marker import (
            has_any_injection_block,
            strip_all_injection_blocks,
        )
        if not has_any_injection_block(text):
            return text
        return strip_all_injection_blocks(text)
    
    def _get_content_from_item(self, item: Any) -> Any:
        """
        Get content from item (dict or object).
        
        Args:
            item: Session item
            
        Returns:
            Content value, or None if not found
        """
        if isinstance(item, dict):
            return item.get('content')
        elif hasattr(item, 'content'):
            return getattr(item, 'content', None)
        return None
    
    def _extract_text_from_blocks(self, blocks: List[Any]) -> str:
        """
        Extract text from content blocks.
        
        Args:
            blocks: List of content blocks
            
        Returns:
            Combined text from all valid blocks
        """
        text_parts = []
        
        for block in blocks:
            block_text = self._extract_text_from_block(block)
            if block_text:
                text_parts.append(block_text)
        
        return '\n'.join(text_parts) if text_parts else ''
    
    def _extract_text_from_block(self, block: Any) -> str:
        """
        Extract text from a single content block.
        
        Args:
            block: Content block (dict or object)
            
        Returns:
            Text content, or empty string if not a text block
        """
        # Handle dict blocks
        if isinstance(block, dict):
            block_type = block.get('type')
            if block_type in MemoryServiceConfig.VALID_CONTENT_TYPES:
                return block.get('text', '')
        
        # Handle object blocks
        elif hasattr(block, 'type'):
            block_type = getattr(block, 'type', None)
            if block_type in MemoryServiceConfig.VALID_CONTENT_TYPES:
                return getattr(block, 'text', '')
        
        return ''
    
    def _is_command(self, text: str) -> bool:
        """
        Check if text is a command (starts with /).
        
        Args:
            text: Text to check
            
        Returns:
            True if command, False otherwise
        """
        return text.strip().startswith(MemoryServiceConfig.COMMAND_PREFIX)
    
    def _format_messages_for_slug(self, messages: List[Dict[str, str]]) -> str:
        """
        Format messages into a string for slug generation.
        
        Args:
            messages: List of message dictionaries
            
        Returns:
            Formatted string of conversation
        """
        parts = []
        for msg in messages:
            role = msg['role']
            content = msg['content']
            parts.append(f"{role}: {content}")
        
        return '\n'.join(parts)
    
    async def _generate_slug_via_llm(
        self, 
        session_content: str, 
    ) -> Optional[str]:
        """
        Generate a short filename slug using LLM.
        
        Args:
            session_content: Conversation content to analyze
            
        Returns:
            Generated slug (1-2 words, lowercase, hyphen-separated), or None if failed
        """
        try:
            # Use configured preview length
            content_preview = session_content[:MemoryServiceConfig.CONTENT_PREVIEW_LENGTH]
            
            prompt = f"""Based on this conversation, generate a short 1-2 word filename slug (lowercase, hyphen-separated, no file extension).

Conversation summary:
{content_preview}

Reply with ONLY the slug, nothing else. Examples: "vendor-pitch", "api-design", "bug-fix", "code-review"."""
            
            # Route slug generation through the fast model (DeepSeek via li)
            from siada.provider.fast_llm import fast_completion

            logger.debug("[memory-service] Calling fast LLM to generate slug...")

            response = await asyncio.wait_for(
                fast_completion(prompt, agent_name="memory_slug_generator"),
                timeout=MemoryServiceConfig.SLUG_TIMEOUT,
            )
            
            # Extract and clean the slug
            slug = self._extract_slug_from_response(response)
            if slug:
                logger.info(f"[memory-service] Generated slug via LLM: {slug}")
                return slug
            
            logger.debug("[memory-service] LLM response did not contain valid slug")
            return None
            
        except asyncio.TimeoutError:
            logger.debug("[memory-service] LLM slug generation timed out")
            return None
        except Exception as e:
            logger.debug(f"[memory-service] Failed to generate slug via LLM: {e}")
            return None
    
    def _extract_slug_from_response(self, response: Any) -> Optional[str]:
        """
        Extract and clean slug from LLM response.
        
        Args:
            response: LLM response object
            
        Returns:
            Cleaned slug, or None if extraction failed
        """
        if not response or not hasattr(response, 'choices') or len(response.choices) == 0:
            return None
        
        choice = response.choices[0]
        if not hasattr(choice, 'message') or not hasattr(choice.message, 'content'):
            return None
        
        raw_slug = choice.message.content.strip()
        cleaned_slug = self._clean_slug(raw_slug)
        
        # Validate slug is not just the default
        if cleaned_slug and cleaned_slug != MemoryServiceConfig.DEFAULT_SLUG:
            return cleaned_slug
        
        return None
    
    def _clean_slug(self, raw_slug: str) -> str:
        """
        Clean and validate a slug string.
        
        Args:
            raw_slug: Raw slug text from LLM
            
        Returns:
            Cleaned slug (lowercase, hyphenated, max length)
        """
        # Convert to lowercase
        slug = raw_slug.lower().strip()
        
        # Replace non-alphanumeric with hyphens
        slug = re.sub(r'[^a-z0-9-]+', '-', slug)
        
        # Remove multiple consecutive hyphens
        slug = re.sub(r'-+', '-', slug)
        
        # Remove leading/trailing hyphens
        slug = slug.strip('-')
        
        # Limit length using config
        slug = slug[:MemoryServiceConfig.MAX_SLUG_LENGTH]
        
        return slug or MemoryServiceConfig.DEFAULT_SLUG
    
    def _format_markdown_content(
        self,
        messages: List[Dict[str, str]],
        session_id: str,
        timestamp: datetime,
        date_str: str,
        time_str: str,
        workspace: Optional[str] = None,
        was_truncated: bool = False,
    ) -> str:
        """
        Format conversation into Markdown content.
        
        Args:
            messages: List of message dictionaries
            session_id: Session identifier
            timestamp: Local timestamp
            date_str: Formatted date string (YYYY-MM-DD)
            time_str: Formatted time string (HH:MM:SS)
            workspace: Absolute path to the working directory (optional)
            was_truncated: Whether earlier messages were truncated
            
        Returns:
            Formatted Markdown string
        """
        parts = [
            f"# Session: {date_str} {time_str}",
            "",
            f"- **Session ID**: {session_id}",
            f"- **Timestamp**: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        if workspace:
            parts.append(f"- **Workspace**: {workspace}")
        parts += [
            "",
            "## Conversation Summary",
            ""
        ]

        # Add truncation notice if earlier messages were dropped
        if was_truncated:
            parts.append(
                "> ⚠️ **Note**: Earlier messages in this session were truncated "
                "due to length limits. Only the most recent portion is shown below."
            )
            parts.append("")
        
        # Add each message
        for msg in messages:
            role = msg['role']
            content = msg['content']
            parts.append(f"{role}: {content}")
        
        parts.append("")  # Final newline
        
        return '\n'.join(parts)
    
    def _index_memory_file(self, memory_file: Path) -> None:
        """
        Index a memory file into SQLite + FTS5.
        
        Args:
            memory_file: Path to the memory markdown file
        """
        try:
            logger.debug(f"[memory-service] Indexing file: {memory_file}")
            
            # Create database instance with same directory as memory files
            db_path = self.memory_dir / "memory.db"
            db = MemoryDatabase(db_path)
            
            # Calculate relative path from memory_dir for storage in database
            try:
                relative_path = memory_file.relative_to(self.memory_dir)
            except ValueError:
                # If file is not under memory_dir, use absolute path as fallback
                relative_path = memory_file
                logger.warning(f"[memory-service] File {memory_file} is not under memory_dir, using absolute path")
            
            # Index the file with relative path
            success = db.index_file(
                file_path=relative_path,
                source='session',
                model='none'
            )
            
            if success:
                logger.info(f"[memory-service] Successfully indexed {relative_path}")
            else:
                logger.warning(f"[memory-service] Failed to index {relative_path}")
            
            # Close database connection
            db.close()
            
        except Exception as e:
            # Log error but don't fail the main operation
            logger.error(f"[memory-service] Error indexing file: {e}", exc_info=True)
    
    def _format_session_content(self, messages: List[Dict]) -> str:
        """
        Format message list into a readable string for memory extraction.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            
        Returns:
            Formatted conversation string
        """
        parts = []
        for msg in messages:
            role = msg['role']
            content = msg['content']
            # Format as simple conversation
            parts.append(f"{role}: {content}")
        
        return '\n\n'.join(parts)
    
    async def update_derived_memory(self, session_content: str) -> None:
        """
        Run the memory generation pipeline on the given session content.

        Delegates to MemoryAgent which executes four task instructions in sequence:
        structured_event → experience
        Each task reads existing files directly via edit_file as needed.

        Args:
            session_content: Formatted session conversation content
        """
        try:
            logger.info("[memory-service] Starting memory pipeline")

            from siada.services.memory.memory_agent import analyze_and_update_memory

            result = await analyze_and_update_memory(session_content=session_content)

            if result.get('success'):
                completed = result.get('completed_tasks', [])
                logger.info(f"[memory-service] Memory pipeline done: {completed}")
            else:
                logger.error(f"[memory-service] Memory pipeline failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"[memory-service] Error in memory pipeline: {e}", exc_info=True)
