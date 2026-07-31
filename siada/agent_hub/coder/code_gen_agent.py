"""
Code Generation Agent Module

Provides specialized Agent implementation for code generation tasks.
"""
import os
from typing import List

from agents import RunContextWrapper, RunResult, RunResultStreaming, TResponseInputItem
from siada.foundation.code_agent_context import CodeAgentContext, RuntimeSource
from siada.agent_hub.siada_agent import SiadaAgent
from siada.tools.ast.ast_tool import list_code_definition_names
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.run_powershell import get_run_powershell_tool_if_available
from siada.foundation.setting import settings
from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.agent_hub.coder.prompt.base.tool_use import should_enable_parallel_tool_calls_in_prompt
from siada.services.handle_at_command import handle_at_command
import logging
from siada.foundation.logging import logger as siada_logger
from siada.services.memory.holographic.marker import (
    strip_benchmark_hint_block,
    wrap_prefetch_block,
)
from siada.tools.memory import search_memory, memory, fact_store, fact_feedback
from siada.tools.memory import search_memory, memory
from siada.tools.todo import todo_write
from siada.tools.web import (
    web_search,
    web_fetch,
    resolve_web_tools_enabled,
    resolve_provider_from_context,
)

from siada.tools.agent.run_subtask import run_subtask
from siada.tools.lark import get_available_lark_tools

# Note: previously this file called ``logging.getLogger().setLevel(logging.INFO)``
# and then used ``logging.info(...)`` (the root logger). The siada framework
# wires its file handlers (``siada_cli.log`` etc.) only onto the ``siada`` /
# ``siada.app`` named loggers and sets ``propagate=False`` on them, so root
# logger output never reached the on-disk log files. We now route this
# module's logs through ``siada.foundation.logging.logger`` (a TimingLogger
# wrapping ``siada.app``), which makes them visible in ``siada_cli.log``
# alongside every other siada-namespace log.


class CodeGenAgent(SiadaAgent[CodeAgentContext]):
    """
    Code Generation Agent
    
    Specialized Agent implementation for code generation tasks.
    Includes memory search capability for recalling past conversations and decisions.
    """

    def __init__(self, *args, **kwargs):

        if 'name' not in kwargs:
            kwargs['name'] = "CodeGenAgent"

        if 'tools' not in kwargs:
            kwargs['tools'] = self._get_base_tools()

        super().__init__(
            *args,
            **kwargs
        )

    def _get_base_tools(self) -> list:
        base_tools = [edit, regex_search_files, run_cmd, list_code_definition_names, run_subtask, todo_write]

        pwsh = get_run_powershell_tool_if_available()
        if pwsh is not None:
            base_tools.append(pwsh)

        return base_tools

    def configure_tools_for_context(self, context: CodeAgentContext) -> None:
        tools = self._get_base_tools()

        # Web tools (web_search / web_fetch) are gated by a tri-state switch:
        # explicit conf.yaml setting (or live /web toggle) wins; otherwise the
        # provider-based default applies (ON for "li", OFF for others). Only
        # add tools that the optional internal package actually exposes.
        # Prefer the resolved provider name written by _build_run_config
        # (context.provider) — the actual provider used for model calls — and
        # fall back to the raw llm_config value with model-based routing applied.
        provider = resolve_provider_from_context(context)
        if resolve_web_tools_enabled(
            provider,
            getattr(context, "web_tools_enabled", None),
        ):


            if web_search is not None:
                tools.append(web_search)
            if web_fetch is not None:
                tools.append(web_fetch)

        # Always register lark tools regardless of runtime source.
        # When running from LARK_CONTROLLER, the tool itself will
        # gracefully degrade instead of being absent (which would cause
        # a fatal ModelBehaviorError "Tool not found" from the SDK).
        tools.extend(get_available_lark_tools())

        # Add memory tools only when the master switch is ON.
        if getattr(context, "memory_tools_enabled", True):
            tools.extend([search_memory, memory])
            # Add holographic tools only when the provider is actually
            # initialized; adding them when disabled would pollute the
            # LLM's tool list with always-failing entries.
            if getattr(context, "holographic_provider", None) is not None:
                tools.extend([fact_store, fact_feedback])

        self.tools = tools

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir        

        # Get combined memory from context (prepared by SiadaRunner)
        combined_memory = run_context.context.combined_memory

        # Get preferred language and agent name from session config
        preferred_language = run_context.context.preferred_language
        agent_name = run_context.context.session.siada_config.agent_name
        # Get pre_plan setting from context
        pre_plan = run_context.context.pre_plan
        
        enable_parallel = should_enable_parallel_tool_calls_in_prompt(run_context)

        # Get model name for GPT-5 specific prompt optimizations
        model_name = None
        try:
            model_name = run_context.context.session.siada_config.llm_config.model_name
        except (AttributeError, TypeError):
            pass

        system_prompt = code_gen_prompt.get_system_prompt(
            root_dir, run_context.context.interactive_mode,
            combined_memory, preferred_language, agent_name,
            pre_plan,
            enable_parallel_tool_calls=enable_parallel,
            model_name=model_name,
        )
        return system_prompt

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        interactive_mode = self.get_interactive_mode()

        context = CodeAgentContext(
            root_dir=current_working_dir,
            interactive_mode=interactive_mode
        )
        return context

    async def process_at_commands(self, user_input: str| List[TResponseInputItem], context: CodeAgentContext) -> str:
        """
        Process @ commands in user input and return processed input
        
        Args:
            user_input: Original user input that may contain @ commands
            context: Code agent context
            
        Returns:
            Processed user input with @ command content injected
        """
        try:
            # Check if input contains @ commands
            if '@' not in user_input:
                return user_input
            
            logging.info(f"[process_at_commands] Input contains '@', processing at-commands (input_len={len(user_input)})")

            # Create configuration object for at command processing
            class AtCommandConfig:
                def __init__(self, root_dir: str, interactive: bool = False, io=None):
                    # Root directory used for resolving @ paths
                    self.root_dir = root_dir
                    # Whether we are in interactive mode (controls spinner behavior)
                    self.interactive = interactive
                    # Optional IO instance, if available (for rich panel-aware spinner)
                    self.io = io

            # Determine interactive flag and IO from context if available
            interactive = getattr(context, "interactive_mode", False)
            io_instance = None
            if getattr(context, "session", None) and getattr(context.session, "siada_config", None):
                io_instance = context.session.siada_config.io

            config = AtCommandConfig(context.root_dir, interactive=interactive, io=io_instance)

            # Create callback functions
            def add_item(item, message_id):
                # Log the item for debugging
                logging.debug(f"AtCommand item added: {item}")

            def on_debug_message(message):
                # Log debug messages
                logging.debug(f"AtCommand debug: {message}")

            # Process at commands
            result = await handle_at_command(
                query=user_input,
                config=config,
                add_item=add_item,
                on_debug_message=on_debug_message,
                message_id=1
            )

            if result.should_proceed and result.processed_query:
                # Combine all text parts from processed query
                processed_text = ""
                for part in result.processed_query:
                    if isinstance(part, dict) and 'text' in part:
                        processed_text += part['text']

                return processed_text.strip() if processed_text else user_input
            else:
                # If processing failed, return original input
                return user_input

        except Exception as e:
            # If any error occurs, log it and return original input
            logging.warning(f"Failed to process @ commands: {e}")
            return user_input

    async def run(self, user_input: str| List[TResponseInputItem], context: CodeAgentContext, run_config=None, openai_session=None) -> RunResult:
        """
        Execute code generation task.

        Args:
            user_input: User's code generation request with requirements and specifications
            context: Context object providing project information
            run_config: Run configuration (provided by SiadaRunner)
            openai_session: OpenAI session (provided by SiadaRunner)
        Returns:
            Generation result containing final output and execution details
        """

        self.configure_tools_for_context(context)

        # Process @ commands first
        processed_input = await self.process_at_commands(user_input, context)

        input_with_env = self.assemble_user_input(processed_input, context)
        result = await self.run_impl(
            starting_agent=self,
            input=input_with_env,
            max_turns=context.max_turns if context.max_turns is not None else settings.MAX_TURNS,
            context=context,
            run_config=run_config,
            openai_session=openai_session,
        )

        return result

    async def run_streamed(
        self, user_input: str| List[TResponseInputItem], context: CodeAgentContext, run_config=None, openai_session=None
    ) -> RunResultStreaming:
        """
        Execute code generation task with streaming output.

        Args:
            user_input: User's code generation request with requirements and specifications
            context: Context object providing project information
            run_config: Run configuration (provided by SiadaRunner)
            openai_session: OpenAI session (provided by SiadaRunner)
        Returns:
            A streaming result of the generation, containing final output and execution details.
        """

        self.configure_tools_for_context(context)

        # Process @ commands first
        processed_input = await self.process_at_commands(user_input, context)

        input_with_env = self.assemble_user_input(processed_input, context)
        result = await self.run_streamed_impl(
            starting_agent=self,
            input=input_with_env,
            context=context,
            max_turns=context.max_turns if context.max_turns is not None else settings.MAX_TURNS,
            run_config=run_config,
            openai_session=openai_session,
        )

        return result

    def assemble_user_input(
        self, user_input: str | List[TResponseInputItem], context: CodeAgentContext
    ) -> any:
        # Holographic prefetch injection — runs once per agent ``run()`` (vs.
        # per-LLM-call), so the prefix gets persisted into the conversation
        # alongside the user message and we never accumulate duplicate blocks
        # on subsequent turns. See
        # design_docs/siada-holographic-memory-introduction.md §11.
        #
        # Temporarily disabled: the prefetch facts block is no longer appended
        # to the user input. ``assemble_user_input`` now returns the input
        # unchanged. The ``_inject_holographic_prefetch`` method is kept intact
        # below so it can be re-enabled easily by restoring the call. All other
        # memory paths (search_memory / memory / fact_store tools and the
        # combined_memory system-prompt block) are independent of this injection
        # and remain unaffected.
        # user_input = self._inject_holographic_prefetch(user_input, context)
        return user_input

        # repo_map_content = self.generate_repo_map(context)

        # if repo_map_content:
        #     project_structure = f"Repository Map:\n{repo_map_content}"
        # else:
        #     project_structure = "Repository Map: Unable to generate repository map"

        # environment_details = f'<environment_details>\n{project_structure}\n</environment_details>'
        # return task + '\n' + environment_details

    def _inject_holographic_prefetch(
        self,
        user_input: str | List[TResponseInputItem],
        context: CodeAgentContext,
    ) -> str | List[TResponseInputItem]:
        """Append the ``provider.prefetch(query)`` block AFTER the user input.

        The facts block is suffixed (not prefixed) so the LLM reads the
        user's actual question first and only then sees the recalled
        facts. Putting recall above the question used to make the model
        treat stored facts as the primary instruction and answer them
        instead of the user's request.

        Always best-effort: any failure in the holographic stack is logged at
        debug level and we hand the original input back unmodified — prefetch
        must never break the main agent run.
        """
        provider = getattr(context, "holographic_provider", None)
        if provider is None:
            siada_logger.info("[holographic-prefetch] Skipped: provider not initialized.")
            return user_input
        try:
            # Flatten the input down to a query string. Most often it's already
            # a string (post `process_at_commands`); the list branch covers
            # multimodal payloads coming from IM / future call sites.
            if isinstance(user_input, str):
                query = user_input
            elif isinstance(user_input, list):
                parts = []
                for item in user_input:
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("content")
                        if isinstance(text, str):
                            parts.append(text)
                query = "\n".join(parts)
            else:
                query = ""
            if not query.strip():
                siada_logger.info(
                    f"[holographic-prefetch] Skipped: empty query "
                    f"(input type={type(user_input).__name__})."
                )
                return user_input

            # Strip ``BENCHMARK_HINT`` blocks from the query so that
            # caller-supplied "tool hints" / harness instructions
            # (e.g. "use search_memory", "write the answer to <tmp_path>")
            # don't pollute the embedding search. The wrapped block stays
            # in ``user_input`` (the LLM still reads it); only the
            # in-flight ``query`` here is cleaned. Currently used by the
            # memory benchmark — see benchmark/memory/run_benchmark.py.
            query_for_prefetch = strip_benchmark_hint_block(query)
            if query_for_prefetch != query:
                siada_logger.info(
                    f"[holographic-prefetch] Stripped BENCHMARK_HINT block "
                    f"({len(query)}→{len(query_for_prefetch)} chars) before search."
                )
            if not query_for_prefetch.strip():
                # Whole query was inside a hint block — nothing left to
                # search on. Skip prefetch instead of running an empty query.
                siada_logger.info("[holographic-prefetch] Skipped: query empty after benchmark-hint strip.")
                return user_input

            siada_logger.info(
                f"[holographic-prefetch] Querying facts (input type={type(user_input).__name__}, "
                f"query_len={len(query_for_prefetch)}): {query_for_prefetch[:80]}..."
            )
            facts_block = provider.prefetch(query_for_prefetch)
            if not facts_block:
                siada_logger.info("[holographic-prefetch] No matching facts found this turn.")
                return user_input

            # Wrap the synthesized facts block with sentinel markers so
            # downstream consumers (frontend renderer, MemoryReviewAgent,
            # ResumeService) can distinguish — and optionally strip — the
            # injected segment from the user's actual message.
            wrapped_block = wrap_prefetch_block(facts_block)
            if not wrapped_block:
                # Edge case: provider returned non-empty but whitespace-only.
                siada_logger.info("[holographic-prefetch] Skipped: facts block is whitespace-only.")
                return user_input

            siada_logger.info(
                f"[holographic-prefetch] Injected facts block "
                f"(facts_len={len(facts_block)}, wrapped_len={len(wrapped_block)})."
            )
            # Append the wrapped facts block AFTER the user's content. We
            # add a ``\n\n`` separator because ``wrap_prefetch_block`` only
            # adds trailing newlines (designed historically for prepend);
            # without the leading separator the user's last line would
            # collide with the BEGIN marker on the same visual line.
            if isinstance(user_input, str):
                return user_input.rstrip() + "\n\n" + wrapped_block
            if isinstance(user_input, list):
                return list(user_input) + [
                    {"type": "input_text", "text": "\n\n" + wrapped_block}
                ]
            return user_input
        except Exception as e:  # pragma: no cover — defensive
            siada_logger.warning(
                f"[holographic-prefetch] Injection failed: {e}", exc_info=True
            )
            return user_input

    def generate_repo_map(self, context: CodeAgentContext) -> str:
        """
        Generate repository map for project structure analysis.
        
        Args:
            context: Code agent context containing project information
            
        Returns:
            Repository map content as string
        """
        try:
            if not context.root_dir:
                return ""

            repo_map = self.get_repo_map_instance(context.root_dir)
            if not repo_map:
                return ""

            python_files = []
            for root, dirs, files in os.walk(context.root_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [
                    '__pycache__', 'node_modules', '.git', '.venv', 'venv', 'env'
                ]]

                for file in files:
                    if file.endswith('.py') and not file.startswith('.'):
                        filepath = os.path.join(root, file)
                        python_files.append(filepath)

            substantial_files = []
            for filepath in python_files:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if len(content) > 100:
                            lines = [line.strip() for line in content.split('\n') if line.strip()]
                            non_comment_lines = [line for line in lines if not line.startswith('#')]
                            if len(non_comment_lines) > 5:
                                substantial_files.append(filepath)
                except Exception:
                    continue

            if len(substantial_files) > 50:
                substantial_files = substantial_files[:50]

            result = repo_map.get_repo_map(
                chat_files=[],
                other_files=substantial_files,
                mentioned_fnames=set(),
                mentioned_idents=set(['class', 'def', 'function'])
            )

            return result or ""

        except Exception as e:
            return f"Generate repo map failed: {str(e)}"
