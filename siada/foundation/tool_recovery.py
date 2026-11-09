"""Recover missing native/custom tools without exposing them to the model.

openai-agents 0.22.3 only honors ``tool_not_found_behavior`` for function
calls. Keep this compatibility adapter scoped to that recovery setting and
leave registered tools, approvals, and invocation validation with the SDK.
"""

from __future__ import annotations

import inspect
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, Literal

from agents import ApplyPatchTool, RunConfig, RunContextWrapper
from agents.editor import ApplyPatchOperation, ApplyPatchResult
from agents.items import ItemHelpers, ToolCallOutputItem
from agents.run_config import ToolErrorFormatterArgs
from agents.tool import CustomTool

_INSTALL_LOCK = threading.Lock()
_INSTALLED = False
_CURRENT_INVENTORY: ContextVar[tuple[str, ...]] = ContextVar("missing_tool_inventory", default=())
logger = logging.getLogger(__name__)


@contextmanager
def tool_recovery_scope() -> Iterator[None]:
    """Keep inventory local to this run, including SDK streaming producer tasks."""
    token = _CURRENT_INVENTORY.set(())
    try:
        yield
    finally:
        _CURRENT_INVENTORY.reset(token)


def _tool_inventory() -> str:
    names = _CURRENT_INVENTORY.get()
    if not names:
        return "No tools are currently available. Continue without calling tools."
    return f"Available tools: {', '.join(names)}. Choose one of these tools to continue."


def missing_tool_formatter(args: ToolErrorFormatterArgs[Any]) -> str:
    """Use the SDK's resolved per-turn inventory, without reevaluating tools."""
    if args.kind != "tool_not_found":
        return args.default_message
    return f"{args.default_message} {_tool_inventory()}"


async def _missing_tool_message(
    config: RunConfig, context: RunContextWrapper[Any], tool_name: str,
    tool_type: Literal["apply_patch", "custom"], call_id: str,
) -> str:
    args = ToolErrorFormatterArgs(
        kind="tool_not_found", tool_type=tool_type, tool_name=tool_name,
        call_id=call_id, default_message=f"Tool '{tool_name}' not found.", run_context=context,
    )
    fallback = missing_tool_formatter(args)
    if config.tool_error_formatter is None:
        return fallback
    try:
        message = config.tool_error_formatter(args)
        if inspect.isawaitable(message):
            message = await message
    except Exception:
        logger.warning("Missing-tool error formatter failed; using default feedback.", exc_info=True)
        return fallback
    return message if isinstance(message, str) else fallback


class _UnavailablePatchEditor:
    """Fail closed even if a future SDK bypasses the recovery action."""

    def create_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        return ApplyPatchResult(status="failed", output="Tool 'apply_patch' not found.")

    update_file = create_file
    delete_file = create_file


class _MissingApplyPatchTool(ApplyPatchTool):
    """Dispatch-only marker; never included in the model's tool definitions."""


def install_missing_tool_recovery() -> None:
    """Install the narrow adapter once after the SDK import has completed."""
    global _INSTALLED
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        from agents.run_internal import turn_resolution
        from agents.run_internal.tool_actions import ApplyPatchAction
        from agents.run_internal.tool_execution import is_apply_patch_name

        process_response = turn_resolution.process_model_response
        execute_patch = ApplyPatchAction.execute

        @wraps(process_response)
        def process_with_recovery(**kwargs: Any) -> Any:
            config = kwargs.get("run_config")
            if config is None or config.tool_not_found_behavior != "return_error_to_model":
                return process_response(**kwargs)
            tools = kwargs["all_tools"]
            names = {getattr(tool, "qualified_name", None) or tool.name for tool in tools}
            names.update(handoff.tool_name for handoff in kwargs["handoffs"])
            _CURRENT_INVENTORY.set(tuple(sorted(names)))
            patch_tool = next((tool for tool in tools if isinstance(tool, ApplyPatchTool)), None)
            registered_patch = patch_tool is not None
            has_patch = registered_patch
            custom_names = {tool.name for tool in tools if isinstance(tool, CustomTool)}
            recovery_tools = []
            for item in kwargs["response"].output:
                item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
                if item_type == "apply_patch_call" and not has_patch:
                    recovery_tools.append(_MissingApplyPatchTool(editor=_UnavailablePatchEditor()))
                    has_patch = True
                elif item_type == "custom_tool_call":
                    name = item.get("name") if isinstance(item, dict) else item.name
                    if name in custom_names:
                        continue
                    # A registered native patch tool owns its custom-call fallback.
                    if registered_patch and is_apply_patch_name(name, patch_tool):
                        continue

                    async def return_error(
                        context: RunContextWrapper[Any], input: str, *, tool_name: str = name,
                    ) -> str:
                        return await _missing_tool_message(
                            config, context, tool_name, "custom", context.tool_call_id,
                        )

                    recovery_tools.append(CustomTool(
                        name=name, description="Unavailable tool", on_invoke_tool=return_error,
                    ))
                    custom_names.add(name)
            if recovery_tools:
                kwargs = {**kwargs, "all_tools": [*tools, *recovery_tools]}
            if not registered_patch:
                # An unavailable function named apply_patch must reach the public
                # missing-function path before the SDK attempts to parse its JSON.
                kwargs = {**kwargs, "allow_apply_patch_function_fallback": False}
            return process_response(**kwargs)

        @wraps(execute_patch)
        async def execute_with_recovery(cls: type, **kwargs: Any) -> Any:
            call = kwargs["call"]
            if not isinstance(call.apply_patch_tool, _MissingApplyPatchTool):
                return await execute_patch(**kwargs)
            raw_call = call.tool_call
            call_id = raw_call.get("call_id") if isinstance(raw_call, dict) else raw_call.call_id
            context = kwargs["context_wrapper"]
            message = await _missing_tool_message(
                kwargs["config"], context, "apply_patch", "apply_patch", call_id,
            )
            raw_output: dict[str, Any] = {
                "type": "apply_patch_call_output", "call_id": call_id,
                "status": "failed", "output": message,
            }
            ItemHelpers.copy_tool_call_caller(raw_call, raw_output)
            context._mark_tool_invocation_executed(raw_call, tool_name="apply_patch")
            result = ToolCallOutputItem(agent=kwargs["agent"], output=message, raw_item=raw_output)
            if committer := kwargs.get("tool_output_committer"):
                committer(result)
            return result

        turn_resolution.process_model_response = process_with_recovery
        ApplyPatchAction.execute = classmethod(execute_with_recovery)
        _INSTALLED = True