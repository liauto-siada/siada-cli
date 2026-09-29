from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from siada.session.session_models import RunningSession

from siada.foundation.logging import logger as logging


class RuntimeSource:
    CLI = "cli"
    DAEMON = "daemon"
    LARK_CONTROLLER = "lark_controller"

class CodeAgentContext(BaseModel):

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session: Optional[RunningSession] = None

    # Runtime source of the current agent execution.
    runtime_source: str = RuntimeSource.CLI

    root_dir: str | None = None

    provider: str | None = None

    # Interactive mode flag, True for interactive mode, False for non-interactive mode
    interactive_mode: bool = True

    # Combined memory from all sources (rule_memory + user_memory + structured_memory)
    combined_memory: Optional[str] = None
    preferred_language: Optional[str] = None  # Preferred language for AI responses

    # Skill names explicitly activated by a slash command for this run only.
    activated_skill_names: set[str] = Field(default_factory=set)

    # MCP-related extensions
    mcp_service: Optional[Any] = None
    mcp_config: Optional[Any] = None
    mcp_enabled: bool = False

    # SiadaIgnore controller for file access control
    siadaignore_controller: Optional[Any] = None

    # Whether to enable human agreement mechanism for plan execution
    pre_plan: bool = False

    # Master switch: False disables all memory tools and memory-related system prompt.
    # Set by SiadaRunner based on memory_config.enabled; defaults to True.
    memory_tools_enabled: bool = True

    # Web tools (web_search / web_fetch) tri-state switch:
    #   - None  ("auto", default): web tools are ON.
    #   - True:  always enable web tools.
    #   - False: always disable web tools.
    # Set by SiadaRunner based on web_config.enabled; may be toggled live by /web.
    web_tools_enabled: Optional[bool] = None

    # Master switch for the sub-agent feature (`run_subtask`), from conf.yaml
    # `sub_agent.enabled` (default True). When False, `run_subtask` is left out
    # of the tool list and the sub-agent guidance is dropped from the system
    # prompt, so every task is worked inline in the main agent's own context.
    subagent_enabled: bool = True

    # Inline memory store (MEMORY.md / USER.md); None when memory disabled
    memory_store: Optional[Any] = None

    # Holographic structured fact memory provider; None when holographic disabled.
    # See siada/services/memory/holographic/provider.py and
    # design_docs/siada-holographic-memory-introduction.md.
    holographic_provider: Optional[Any] = None

    # Maximum number of turns for the code agent (None means use default from settings)
    max_turns: Optional[int] = None

    # True when this context belongs to a sub-agent run launched via
    # run_subtask (fork or non-fork). Used by the recursion guard: tools on
    # the "sub-agent unavailable" list check this flag at execution time and
    # refuse to run instead of being structurally absent from the tool list
    # (needed for fork=true, where the sub-agent's tool list is byte-for-byte
    # identical to the parent's — including run_subtask itself — to preserve
    # the parent's prompt cache prefix).
    is_subagent: bool = False

    # Nesting depth in the sub-agent tree: 0 = main agent, 1 = sub-agent,
    # 2 = sub-sub-agent. Only meaningful when sub_agent.allow_recursive_subagents
    # is enabled (see siada/tools/agent/subagent_recursion.py); when the
    # feature is off, every sub-agent context still gets depth=1 for
    # informational purposes but the depth is never consulted by any guard.
    subagent_depth: int = 0

    # The root (main-agent) session id this context's agent tree belongs to.
    # Sub-agent contexts don't carry a live `session` (kept minimal to match
    # pre-existing non-fork behaviour), so this is threaded through
    # explicitly at spawn time — it is the tracking key used by the
    # per-tree concurrency counter and by the on-disk persistence layout
    # (<sessions_dir>/<root_session_id>/subagents/...).
    root_session_id: Optional[str] = None

    # Mirrors conf.yaml's sub_agent.allow_recursive_subagents (SiadaRunner
    # copies it here for the main agent's context; run_subtask propagates it
    # unchanged to every sub-agent/sub-sub-agent context it spawns). Default
    # False preserves the exact pre-existing "sub-agents can never nest"
    # behaviour. See siada/tools/agent/subagent_recursion.py.
    allow_recursive_subagents: bool = False

    # This context's OWN sub-agent id (as pushed via sub_agent_notifier /
    # subagent_persistence), or None for the main agent. Used as the
    # "parent_id" when THIS agent itself spawns a nested child, so the
    # on-disk persistence index can reconstruct the sub-agent tree shape.
    subagent_self_id: Optional[str] = None

    # Hook control state — populated by PluginHookGuardrails during tool execution.
    # hook_pending_contexts: texts to inject as system messages on next LLM call.
    # hook_pending_input_updates: tool_call_id -> updated JSON arguments string.
    hook_pending_contexts: list[str] = Field(default_factory=list)
    hook_pending_input_updates: dict[str, str] = Field(default_factory=dict)

    # Git workspace info (repo URL, branch, HEAD commit) resolved once at session
    # start by SiadaRunner and cached here for telemetry use.
    # Actual type is siada.support.git_info.GitInfo; typed as Any to avoid the import.
    git_context: Optional[Any] = None

    # Todo list state (V1: in-memory, not persisted to disk).
    # Actual item type is List[TodoItem]; typed as Any to avoid circular imports.
    todos: List[Any] = Field(default_factory=list)
    # Sub-agent display state (in-memory; item type is
    # siada.tools.agent.sub_agent_notifier.SubAgentItem; typed as Any to avoid
    # circular imports). Consumed by sub_agent_notifier ACP push.
    sub_agent_items: List[Any] = Field(default_factory=list)
    # Assistant turns elapsed since the last todo_write call (maintained by TodoReminderProcessor).
    todo_turns_since_write: int = 0
    # Assistant turns elapsed since the last reminder was injected (maintained by TodoReminderProcessor).
    todo_turns_since_reminder: int = 0

    # Reminder items (TodoReminderProcessor's todo nudge) that were injected
    # directly into THIS call's real model input (input_items, in
    # TodoReminderProcessor.on_llm_start) but still need to be durably
    # persisted to api_history.json. on_llm_start only affects the input the
    # model sees for the current call -- it cannot write to the SDK's
    # Session itself -- so on_llm_start stages a copy here instead, and
    # TodoReminderProcessor.on_llm_end (registered on SiadaAgentHooks)
    # drains this list right after the LLM call succeeds, calling
    # session.add_items() the same way the SDK persists real conversation
    # turns. Cleared once drained.
    #
    # CONTRACT: OVERWRITE this list (e.g.
    # ``context.pending_reminder_items = [dict(item)]``), never append --
    # on_llm_start may run more than once before on_llm_end fires (e.g. a
    # retried call), and each invocation already recomputes a fresh,
    # complete reminder from current state, so appending would let retries
    # accumulate duplicate items. This queue is owned solely by
    # TodoReminderProcessor -- other producers needing the same
    # durable-persistence pattern (e.g.
    # ModelHallucinationSuppressionProcessor) should use their own
    # dedicated field instead of sharing this one, so persistence never
    # depends on hook registration order between unrelated processors.
    pending_reminder_items: List[Any] = Field(default_factory=list)

    # Same durable-persistence pattern as pending_reminder_items above, but
    # owned solely by ModelHallucinationSuppressionProcessor so it can drain
    # its own queue in its own on_llm_end, independent of
    # TodoReminderProcessor / hook registration order.
    pending_hallucination_reminder_items: List[Any] = Field(default_factory=list)



    # Goal state (persisted to <session_dir>/goal.json via goal_storage).
    # Actual type is Optional[Goal]; typed as Any to avoid circular imports.
    goal: Optional[Any] = None
    # Maximum consecutive failed verifier turns before automatic continuation
    # is blocked; populated from conf.yaml's goal.max_turns.
    goal_max_turns: int = 6

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
