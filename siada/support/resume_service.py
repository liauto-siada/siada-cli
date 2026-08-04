"""Session resume service."""

from typing import Optional, Tuple
from siada.services.session_management import SessionManager, SessionData
from siada.session.task_message_state import RealApiMessage
from siada.agent_hub.context_filter.utils import compute_message_signature
from siada.foundation.logging import logger


class ResumeService:
    """Handles session lookup, loading, and restoration."""

    def __init__(self, project_root: str):
        self.session_manager = SessionManager(project_root)

    def list_sessions(self, scope: str = 'current') -> str:
        """Return a formatted string listing available sessions.

        scope: 'current' lists sessions for the current project only,
               'all' lists sessions across all projects.
        """
        sessions = self.session_manager.list_sessions(scope=scope)

        if not sessions:
            return "No saved sessions found."

        if scope == 'all':
            lines = ["Available sessions (All Projects):"]
        else:
            lines = [f"Available sessions (Current Project: {self.session_manager.project_name}):"]

        for session in sessions:
            from datetime import datetime
            try:
                last_updated = datetime.fromisoformat(session.last_updated)
                time_str = last_updated.strftime("%Y-%m-%d %H:%M")
            except Exception:
                time_str = session.last_updated

            if scope == 'all':
                lines.append(
                    f"  [{session.index}] [{session.project_name}] {session.first_user_message[:50]} "
                    f"({session.message_count} messages, {time_str})"
                )
            else:
                lines.append(
                    f"  [{session.index}] {session.first_user_message[:50]} "
                    f"({session.message_count} messages, {time_str})"
                )

        if scope == 'all':
            lines.append("\nUsage: /resume <latest|index|session_id>")
            lines.append("       /resume  (show current project only)")
        else:
            lines.append("\nUsage: /resume <latest|index|session_id>")
            lines.append("       /resume --all  (show all projects)")

        return "\n".join(lines)

    def get_session_info(self, identifier: str):
        """Return SessionInfo (metadata only, no full data load) for the given identifier.

        Returns SessionInfo on success, or None if not found.
        """
        try:
            return self.session_manager.find_session(identifier, scope='all')
        except Exception as e:
            logger.error(f"Failed to find session info: {e}")
            return None

    def execute(self, identifier: str = 'latest') -> Optional[Tuple[SessionData, str]]:
        """Load a session by identifier ('latest', numeric index, or session_id).

        Returns (SessionData, message) on success, or (None, error_message) on failure.
        """
        try:
            session_info = self.session_manager.find_session(identifier, scope='all')

            if not session_info:
                return None, f"Session not found: {identifier}"

            # session_path allows loading sessions from other projects
            session_data = self.session_manager.load_session(
                session_info.session_id,
                session_path=session_info.session_path
            )
            session_data.project_root = session_info.project_root

            message = (
                f"Loaded session [{session_info.index}]: {session_info.first_user_message}\n"
                f"Project: {session_info.project_name}\n"
                f"Messages: {session_data.metadata.get('message_count', 0)}\n"
                f"Last updated: {session_info.last_updated}"
            )

            return session_data, message

        except Exception as e:
            logger.error(f"Failed to resume session: {e}")
            return None, f"Error: {str(e)}"

    def restore_to_running_session(self, session_data: SessionData, running_session) -> None:
        """Restore session_data into a live session, reusing the original session_id and storage path."""
        try:
            # Step 1: adopt the restored session's ID
            running_session.session_id = session_data.session_id

            # Step 2: redirect FileSession to the original session directory
            if session_data.session_path and running_session.state.openai_session:
                from siada.services.file_session import FileSession
                old_session = running_session.state.openai_session
                new_file_session = FileSession(
                    session_id=session_data.session_id,
                    sessions_dir=session_data.session_path.parent,
                    on_items_added=old_session.on_items_added,
                    project_root=str(session_data.session_path.parent.parent),
                )
                running_session.state.openai_session = new_file_session

            # Step 3: restore message history, dropping any function_call items with
            # invalid arguments JSON (and all items that follow them)
            import json as _json

            filtered_items = []
            for item in session_data.items:
                if (
                    isinstance(item, dict)
                    and item.get("type") == "function_call"
                    and isinstance(item.get("arguments"), str)
                ):
                    try:
                        _json.loads(item["arguments"])
                    except (_json.JSONDecodeError, ValueError):
                        logger.warning(
                            f"Dropping function_call item and all subsequent items due to invalid arguments JSON, "
                            f"call_id={item.get('call_id')}, name={item.get('name')}"
                        )
                        break
                filtered_items.append(item)
            running_session.state.task_message_state.reset_message_history(
                message_history=filtered_items
            )

            # Recover todo list from the restored message history.
            # Stored as pending_todos on session state; SiadaRunner will transfer it
            # to context.todos once the context is available.
            try:
                from siada.tools.todo.recovery import extract_todos_from_messages
                recovered = extract_todos_from_messages(filtered_items)
                if recovered:
                    running_session.state.pending_todos = recovered
                    logger.debug(f"[todo] Staged {len(recovered)} recovered todos in pending_todos")
            except Exception as e:
                logger.debug(f"[todo] Failed to recover todos on resume: {e}")

            # Recover goal state from goal.json, same stage-then-consume pattern
            # as pending_todos above — SiadaRunner transfers it to context.goal
            # once the context is available. cmd_resume also reads
            # running_session.state.pending_goal right after this call
            # returns to immediately push the recovered goal's state to the
            # frontend (see SlashCommands.cmd_resume) — the GoalStatusBar
            # would otherwise stay blank until the next conversation turn
            # happens to run SiadaRunner._prepare_context_for_run's lazy
            # pending_goal -> context.goal consumption.
            #
            # Explicitly reset to None first (rather than only overwriting
            # on a hit) so a stale pending_goal from a PREVIOUS resume/goal
            # activity on this same long-lived RunningSession object never
            # leaks into a session that has no goal.json (e.g. the user ran
            # ``/goal clear`` before disconnecting, or resumes a different,
            # goal-less session next).
            running_session.state.pending_goal = None
            try:
                if session_data.session_path:
                    from siada.services.goal import goal_storage
                    recovered_goal = goal_storage.load_goal(session_data.session_path)
                    if recovered_goal is not None:
                        running_session.state.pending_goal = recovered_goal
                        logger.debug(
                            f"[goal] Staged recovered goal ({recovered_goal.status}) in pending_goal"
                        )
            except Exception as e:
                logger.debug(f"[goal] Failed to recover goal on resume: {e}")


            # Step 4: restore RealApiMessage from api_messages.json.
            # (see _align_last_index for how the tracking anchor is derived)
            # Filtered-out items are never compacted, so they appear verbatim at the
            # tail of api_messages. Strip them from the tail before restoring.
            if session_data.api_messages and filtered_items:
                api_messages_to_use = list(session_data.api_messages)
                filtered_out_items = session_data.items[len(filtered_items):]
                for item in reversed(filtered_out_items):
                    if api_messages_to_use and str(api_messages_to_use[-1]) == str(item):
                        api_messages_to_use.pop()
                    else:
                        break
                # The tracking anchor must point at the history position of the
                # LAST message that api_messages already covers — NOT at the end
                # of the history. api_messages is the model-visible snapshot taken
                # *before* the last LLM call, so everything produced after that
                # call (assistant reply, tool calls/outputs, the next user turn)
                # is still missing from it. Anchoring at len(history) - 1 makes the
                # next incremental update start its delta after those items and
                # silently drop them from the model's context.
                #
                # The anchor is resolved by aligning api_messages against the
                # history as a subsequence (history may contain extra items that
                # never reach api_messages, e.g. post-filter goal/todo reminders),
                # and it is computed over native items only because
                # FileSession.get_items() hides cross-session ``_injected`` items
                # from the next LLM input.
                native_items = [
                    item for item in filtered_items
                    if not (isinstance(item, dict) and item.get("_injected"))
                ]
                persisted_last_index = self._align_last_index(native_items, api_messages_to_use)
                if persisted_last_index is None:
                    # Cannot align (e.g. api_messages starts with a compaction
                    # summary that has no counterpart in history): fall back to a
                    # full refresh instead of corrupting the context. The persisted
                    # tracking must be reset too, otherwise the stale values in
                    # api_messages.json win in _read_tracking_info_from_file.
                    logger.info(
                        "Could not align api_messages with history on resume; "
                        "next LLM call will do a full refresh"
                    )
                    running_session.state.task_message_state.reset_real_messages()
                    if session_data.session_path:
                        SessionManager.update_api_messages_tracking(
                            session_data.session_path, -1, ""
                        )
                    return
                persisted_last_signature = compute_message_signature(
                    native_items[persisted_last_index]
                )
                # Persist computed values back to api_messages.json
                if session_data.session_path:
                    SessionManager.update_api_messages_tracking(
                        session_data.session_path, persisted_last_index, persisted_last_signature
                    )
                running_session.state.task_message_state.set_real_messages(
                    RealApiMessage(
                        real_api_history=api_messages_to_use,
                        last_index=persisted_last_index,
                        last_signature=persisted_last_signature,
                    )
                )
                # Restore the saved token count so _try_incremental_update only
                # accounts for the delta on the next turn.
                if session_data.api_messages_tokens:
                    from agents.usage import Usage
                    running_session.state.usage = Usage(
                        input_tokens=session_data.api_messages_tokens,
                        output_tokens=0,
                        total_tokens=session_data.api_messages_tokens,
                    )
            else:
                running_session.state.task_message_state.reset_real_messages()
                if session_data.session_path:
                    SessionManager.update_api_messages_tracking(
                        session_data.session_path, -1, ""
                    )

            logger.info(f"Session restored (reusing session_id): {session_data.session_id}")

        except Exception as e:
            logger.error(f"Failed to restore session: {e}")
            raise

    @staticmethod
    def _align_last_index(items: list, api_messages: list) -> Optional[int]:
        """Locate the history index of the last message covered by api_messages.

        api_messages is a subsequence of the history: the history can contain
        items that never make it into the model-visible snapshot (post-filter
        goal/todo reminders), and api_messages can contain items with no history
        counterpart (compaction summaries). The pair is aligned from the tail so
        that trailing compaction summaries do not break the match, and the index
        of the last matched history item is returned.

        Returns None when no api_message could be matched at all, which means the
        caller must fall back to a full refresh.
        """
        i = len(items) - 1
        j = len(api_messages) - 1
        anchor: Optional[int] = None
        while i >= 0 and j >= 0:
            if compute_message_signature(items[i]) == compute_message_signature(api_messages[j]):
                if anchor is None:
                    anchor = i
                j -= 1
            i -= 1
        return anchor
