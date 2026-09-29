from __future__ import annotations
from typing import Any, List, Optional
import hashlib
import json

from agents.models.chatcmpl_converter import Converter
from agents.exceptions import UserError
from agents.tool import FunctionTool, Tool
from siada.foundation.logging import logger
from siada.support.chat_compat_items import to_chat_compatible_item

# Safety margin for char-based token estimation (20% buffer)
_ESTIMATION_SAFETY_MARGIN = 1.2

# Safety margin applied to all token counts to compensate for estimation
# inaccuracy between tiktoken (used locally) and provider-native counting
# (e.g. Anthropic).  10% means returned counts are inflated by 10%.
TOKEN_ESTIMATION_SAFETY_MARGIN = 0.10



def compute_message_signature(message: Any) -> str:
    """
    Compute MD5 signature for a message.
    
    Args:
        message: The message to compute signature for
        
    Returns:
        MD5 hash string of the message
    """
    # Convert message to string for MD5 calculation
    message_str = json.dumps(message, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(message_str.encode('utf-8')).hexdigest()


# Item ``type`` values that ``Converter.items_to_messages`` already understands
# (Responses-API items).  Anything carrying one of these types is left untouched
# by the normalizer below.
_RESPONSES_ITEM_TYPES = frozenset(
    {
        "message",
        "function_call",
        "function_call_output",
        "reasoning",
        "item_reference",
        "compaction",
        "file_search_call",
    }
)

_EASY_INPUT_ROLES = frozenset({"user", "assistant", "system", "developer"})

# Placeholder content for a synthesized tool response when an assistant
# tool_call has no matching tool message in the converted history.
# (Same string the agents SDK uses for omitted tool outputs.)
_OMITTED_TOOL_OUTPUT_PLACEHOLDER = "[tool output omitted]"


def fix_tool_message_ordering(messages: List) -> List:
    """
    Repair Chat Completions tool_call/tool message ordering.

    Background
    ----------
    Models like Kimi K3 may interleave an assistant text message between a
    ``function_call`` and its ``function_call_output`` in the Responses-API
    item stream, e.g.::

        fc_A, assistant_text, fc_B, fco_A, fco_B

    ``Converter.items_to_messages`` flushes the pending assistant message when
    it hits the interleaved text, producing::

        assistant(tool_calls=[A]), assistant(text, tool_calls=[B]), tool(A), tool(B)

    The first assistant message is then NOT immediately followed by the tool
    message responding to ``A`` — which strict Chat Completions providers
    (Moonshot/Kimi) reject with::

        an assistant message with 'tool_calls' must be followed by tool
        messages responding to each 'tool_call_id'

    The normal streaming path already applies this repair (see
    ``siada/internal/provider/li/li_provider.py`` →
    ``LitellmModel._fix_tool_message_ordering``); the compaction summarization
    call needs it too.

    Repairs performed
    -----------------
    1. Every assistant message carrying ``tool_calls`` is split into one
       assistant message per tool call (text/reasoning kept only on the
       first split to avoid duplication), and each is immediately followed
       by its matching tool message, wherever that tool message originally
       sat in the list.
    2. A tool_call without any matching tool message gets a synthesized
       ``[tool output omitted]`` placeholder, so strict providers never see
       a dangling tool_call.
    3. Orphan tool messages (``tool_call_id`` claimed by no assistant
       message) are dropped — strict providers reject them too.

    The input list is not mutated; a new list is returned.
    """
    if not messages:
        return messages

    # Pass 1: index tool result messages by tool_call_id (first occurrence
    # wins, later duplicates are dropped) and collect every tool_call id
    # claimed by an assistant message.
    tool_results: dict = {}
    claimed_ids: set = set()
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "tool":
            tcid = m.get("tool_call_id")
            if tcid and tcid not in tool_results:
                tool_results[tcid] = m
        elif role == "assistant":
            for tc in m.get("tool_calls") or []:
                if isinstance(tc, dict) and tc.get("id"):
                    claimed_ids.add(tc["id"])

    # Pass 2: rebuild the list so each assistant tool_call is immediately
    # followed by its tool response.
    fixed: List = []
    orphans_dropped = 0
    placeholders_added = 0
    for m in messages:
        if not isinstance(m, dict) or m.get("role") != "assistant" or not m.get("tool_calls"):
            if isinstance(m, dict) and m.get("role") == "tool":
                # Claimed tool messages are emitted alongside their assistant
                # message via ``tool_results``; anything left over is an
                # orphan and would be rejected by strict providers.
                if m.get("tool_call_id") not in claimed_ids:
                    orphans_dropped += 1
                continue
            fixed.append(m)
            continue

        tool_calls = [
            tc for tc in m["tool_calls"] if isinstance(tc, dict) and tc.get("id")
        ]
        if not tool_calls:
            # tool_calls present but unusable — strip it so the message is a
            # plain assistant message.
            stripped = dict(m)
            stripped.pop("tool_calls", None)
            fixed.append(stripped)
            continue

        for idx, tc in enumerate(tool_calls):
            single = dict(m)
            single["tool_calls"] = [tc]
            if idx > 0:
                # Keep shared fields only on the first split.
                for shared_field in ("content", "reasoning_content", "thinking_blocks"):
                    single.pop(shared_field, None)
            fixed.append(single)
            result_msg = tool_results.pop(tc["id"], None)
            if result_msg is not None:
                fixed.append(result_msg)
            else:
                placeholders_added += 1
                fixed.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": _OMITTED_TOOL_OUTPUT_PLACEHOLDER,
                    }
                )

    if orphans_dropped or placeholders_added or len(fixed) != len(messages):
        logger.info(
            "[fix_tool_message_ordering] messages %d -> %d "
            "(orphan_tool_msgs_dropped=%d, placeholder_tool_msgs_added=%d)",
            len(messages), len(fixed), orphans_dropped, placeholders_added,
        )
    return fixed


def _normalize_to_responses_items(items: List) -> List:
    """
    Normalize possibly-mixed message items into pure Responses-API items
    so that ``Converter.items_to_messages`` can handle them.

    Background
    ----------
    ``Converter.items_to_messages`` only understands Responses-API items:
      - EasyInputMessage:        ``{role, content}``  (exactly 2 keys)
      - InputMessage:            ``{type:"message", role, content}``
      - ResponseOutputMessage:   ``{type:"message", role:"assistant", content:[...]}``
      - function call:           ``{type:"function_call", call_id, name, arguments}``
      - function call output:    ``{type:"function_call_output", call_id, output}``
      - reasoning / item_reference / file_search_call / compaction

    Some siada provider paths (e.g. li/Bedrock/ADK) write ChatCompletion-style
    dicts into ``task_message_state``::

        {role:"assistant", content:"", tool_calls:[{id, function:{name, arguments}}]}
        {role:"tool", tool_call_id, content}

    These cannot be matched by any ``maybe_*`` branch and trigger
    ``UserError: Unhandled item type or structure``.  We rewrite them so that
    token counting can succeed without falling back to a coarse char-based
    estimate.

    Conversions performed
    ---------------------
    1. ``{role:"assistant", content, tool_calls:[...]}`` is expanded into:
       - an optional Responses message preserving any textual content, and
       - one ``{type:"function_call", call_id, name, arguments}`` per tool call.
    2. ``{role:"tool", tool_call_id, content}`` becomes
       ``{type:"function_call_output", call_id, output}`` with content
       stringified for token counting.
    3. Anything already in Responses form (recognized ``type``) or in strict
       EasyInputMessage shape is passed through unchanged.
    4. Unknown shapes are passed through unchanged so the underlying converter
       still has a chance to fail loudly when truly unrecoverable.

    The original list is not mutated; a new list is returned.
    """
    if not isinstance(items, list):
        return items

    out: List = []
    for item in items:
        if not isinstance(item, dict):
            out.append(item)
            continue

        # Responses-only item shapes that the ChatCompletions converter cannot
        # parse (native apply_patch items, id-less assistant output messages)
        # are rewritten into chat-safe proxies.  The rewrite rules live in
        # ``siada.support.chat_compat_items`` so the wire-level replay paths
        # apply exactly the same normalization; anything else falls through to
        # the existing pass-through rules below.
        rewritten = to_chat_compatible_item(item)
        if rewritten is not item:
            out.append(rewritten)
            continue

        # Already a Responses-API item — pass through.
        if item.get("type") in _RESPONSES_ITEM_TYPES:
            out.append(item)
            continue

        # Strict EasyInputMessage ({role, content} only) — pass through.
        if (
            set(item.keys()) == {"role", "content"}
            and item.get("role") in _EASY_INPUT_ROLES
        ):
            out.append(item)
            continue

        role = item.get("role")

        # Case A: ChatCompletion assistant message with tool_calls.
        if role == "assistant" and item.get("tool_calls"):
            content = item.get("content")
            # Preserve any textual content as a Responses message.
            if isinstance(content, str) and content:
                # Strict EasyInputMessage shape; converter accepts this.
                out.append({"role": "assistant", "content": content})
            elif isinstance(content, list) and content:
                # Already structured content parts — wrap as Responses message.
                out.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": content,
                    }
                )
            # Expand each tool call into its own function_call item.
            for tc in item["tool_calls"]:
                if not isinstance(tc, dict):
                    continue
                func = tc.get("function") or {}
                args = func.get("arguments")
                if isinstance(args, dict):
                    args = json.dumps(args, ensure_ascii=False)
                elif args is None:
                    args = "{}"
                elif not isinstance(args, str):
                    args = str(args)
                out.append(
                    {
                        "type": "function_call",
                        "call_id": tc.get("id") or "",
                        "name": func.get("name") or "",
                        "arguments": args,
                    }
                )
            continue

        # Case B: ChatCompletion tool result message.
        if role == "tool" and "tool_call_id" in item:
            content = item.get("content")
            if isinstance(content, list):
                # Flatten multipart content for token counting.
                output_text = json.dumps(content, ensure_ascii=False)
            elif content is None:
                output_text = ""
            else:
                output_text = str(content)
            out.append(
                {
                    "type": "function_call_output",
                    "call_id": item.get("tool_call_id") or "",
                    "output": output_text,
                }
            )
            continue

        # Default: pass through; let the converter raise if it really cannot
        # handle the item, surfacing genuine new shapes for investigation.
        out.append(item)

    return out


def _summarize_items_for_log(messages_or_text: Any) -> str:
    """Build a compact summary of items for log output (no full dump)."""
    if isinstance(messages_or_text, str):
        return f"text_len={len(messages_or_text)}"
    if isinstance(messages_or_text, list):
        roles = []
        for m in messages_or_text[-3:]:
            if isinstance(m, dict):
                roles.append(m.get("type") or m.get("role") or "?")
            else:
                roles.append(type(m).__name__)
        return f"items={len(messages_or_text)} tail={roles}"
    return type(messages_or_text).__name__


def _convert_tools_to_openai_params(tools: List[Tool]) -> list:
    """
    Convert agent Tool objects to ChatCompletionToolParam dicts for litellm.

    Only FunctionTool instances are converted; other tool types are skipped
    since they are not representable in the ChatCompletions API.

    Args:
        tools: list of agent Tool objects

    Returns:
        list of ChatCompletionToolParam dicts
    """
    result = []
    for tool in tools:
        try:
            result.append(Converter.tool_to_openai(tool))
        except Exception:
            # Skip non-FunctionTool types (e.g. hosted tools)
            continue
    return result


def _calculate_tokens(
    model_name: str,
    messages_or_text: List | str,
    *,
    tools: Optional[List[Tool]] = None,
) -> int:
    """
    Calculate token count using litellm's model-aware tokenizer (internal).

    When ``tools`` is provided, the actual tool definitions are tokenized
    by litellm for precise counting.  Tool overhead is handled separately
    via CompactionStrategy.calculate_fixed_overhead, so this function
    does NOT add any fixed buffer when tools are absent.

    Args:
        model_name: LLM model name (e.g. "claude-4-sonnet")
        messages_or_text: list of API message items, or a plain string
        tools: optional list of agent Tool objects for accurate tool-token counting

    Returns:
        Token count
    """
    import time as _time
    import litellm

    _t0 = _time.perf_counter()

    if isinstance(messages_or_text, str):
        result = litellm.token_counter(model=model_name, text=messages_or_text)
        logger.debug(
            "[PERF][_calculate_tokens] mode=text chars=%d | %.1fms",
            len(messages_or_text), (_time.perf_counter() - _t0) * 1000,
        )
        return result

    # Some upstream provider paths inject ChatCompletion-style dicts (e.g.
    # ``{role:"assistant", tool_calls:[...]}``) into the message list, which
    # ``Converter.items_to_messages`` cannot recognize.  Normalize defensively
    # so token counting stays accurate instead of silently falling back to a
    # char-based estimate.
    _t_normalize0 = _time.perf_counter()
    normalized_items = _normalize_to_responses_items(messages_or_text)
    _t_normalize = _time.perf_counter() - _t_normalize0

    _t_convert0 = _time.perf_counter()
    converted_messages = Converter.items_to_messages(
        items=normalized_items,
        model=model_name,
        preserve_thinking_blocks=True,
        preserve_tool_output_all_content=True,
    )
    _t_convert = _time.perf_counter() - _t_convert0

    # Convert tools for accurate token counting if provided
    openai_tools = _convert_tools_to_openai_params(tools) if tools else None

    _t_count0 = _time.perf_counter()
    if openai_tools:
        result = litellm.token_counter(
            model=model_name,
            messages=converted_messages,
            tools=openai_tools,
        )
    else:
        result = litellm.token_counter(
            model=model_name,
            messages=converted_messages,
        )
    _t_count = _time.perf_counter() - _t_count0

    logger.debug(
        "[PERF][_calculate_tokens] mode=messages items=%d | normalize=%.1fms "
        "convert=%.1fms token_count=%.1fms total=%.1fms",
        len(messages_or_text), _t_normalize * 1000, _t_convert * 1000,
        _t_count * 1000, (_time.perf_counter() - _t0) * 1000,
    )
    return result


def estimate_tokens(messages: List, *, safety_margin: float = _ESTIMATION_SAFETY_MARGIN) -> int:
    """
    Rough token estimate: ~4 chars per token with safety margin.

    Fast fallback when litellm is unavailable (e.g. in tests).
    Can be used standalone without a CodeAgentContext.

    Args:
        messages: list of message items to estimate
        safety_margin: multiplier for estimation buffer (default 1.2)

    Returns:
        Estimated token count
    """
    total_chars = sum(
        len(json.dumps(m, sort_keys=True, ensure_ascii=False, default=str))
        for m in messages
    )
    return int(total_chars / 4 * safety_margin)


def calculate_tokens(
    model_name: str | None,
    messages_or_text: List | str,
    *,
    tools: Optional[List[Tool]] = None,
) -> int:
    """
    Count tokens using litellm when model_name is available,
    falling back to char-based estimate otherwise.

    Unified public API for token counting. Accepts both message lists
    and plain strings (e.g. system instructions).

    Applies TOKEN_ESTIMATION_SAFETY_MARGIN to inflate the result,
    compensating for inaccuracy between tiktoken (used locally) and
    provider-native counting (e.g. Anthropic). This ensures all
    budget comparisons across the codebase automatically include
    safety headroom.

    Args:
        model_name: if provided, uses litellm model-aware tokenizer
        messages_or_text: list of API message items, or a plain string
        tools: optional list of agent Tool objects for accurate tool-token counting

    Returns:
        Token count (inflated by safety margin)
    """
    if model_name is not None:
        try:
            raw = _calculate_tokens(model_name, messages_or_text, tools=tools)
            return int(raw * (1 + TOKEN_ESTIMATION_SAFETY_MARGIN))
        except UserError as e:
            # Converter could not interpret the items (often a previously-unseen
            # ChatCompletion-style shape).  Demote to warning + compact summary
            # so the log is actionable but not noisy.
            logger.warning(
                "token_counter fell back to estimate "
                f"(converter rejected items: {e}); "
                f"{_summarize_items_for_log(messages_or_text)}"
            )
        except Exception as e:
            logger.error(
                f"litellm token_counter failed, falling back to estimate: {e}"
            )
    if isinstance(messages_or_text, str):
        raw = len(messages_or_text) // 4
        return int(raw * (1 + TOKEN_ESTIMATION_SAFETY_MARGIN))
    return estimate_tokens(messages_or_text)
