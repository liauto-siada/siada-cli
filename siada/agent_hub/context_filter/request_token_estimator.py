"""Response-calibrated request budgets with compact, resumable anchors."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from agents import Agent
from agents.agent_output import AgentOutputSchema, AgentOutputSchemaBase
from agents.exceptions import UserError
from agents.handoffs import handoff
from agents.models.chatcmpl_converter import Converter
from agents.models.openai_responses import Converter as ResponsesConverter
from agents.tool import ComputerTool
from openai import omit

from siada.foundation.logging import logger
from siada.provider.responses.sanitize import sanitize_responses_tools_for_openai
from siada.provider.token_counting import TokenCountingInfo, token_counting_info_from_model

from .utils import calculate_tokens, compute_message_signature


# Bump when local input projection or reasoning replay semantics change.
_REQUEST_TOKEN_DOMAIN_VERSION = 1
_SIGNATURE_COMPONENTS = frozenset({
    "domain", "instructions", "tools", "output", "instructions_core",
    "instructions_skills", "instructions_agents", "instructions_memory",
})
_REQUEST_INPUT_OVERRIDE_KEYS = frozenset({
    "model", "messages", "input", "instructions", "system", "tools", "functions",
    "response_format", "text", "prompt", "conversation", "conversation_id", "previous_response_id",
    "context_management", "truncation",
})


def _validated_components(value: Any) -> dict[str, str] | None:
    """Optional diagnostics never grant permission to reuse an anchor."""
    if not isinstance(value, dict) or set(value) != _SIGNATURE_COMPONENTS:
        return None
    if not all(isinstance(digest, str) and len(digest) == 32
               and all(char in "0123456789abcdef" for char in digest) for digest in value.values()):
        return None
    return dict(value)


def _instruction_components(instructions: str) -> dict[str, str]:
    """Hash rendered catalog/memory blocks; do not persist their contents."""
    sections: dict[str, list[str]] = {"core": [], "skills": [], "agents": [], "memory": []}
    section = "core"
    for line in instructions.splitlines(keepends=True):
        heading = line.strip()
        if section != "memory":
            if heading in {"# Skills", "## Skills"}:
                section = "skills"
            elif heading == "# AGENT TYPES":
                section = "agents"
            elif heading == "# Combined Memory":
                section = "memory"
        sections[section].append(line)
    return {
        f"instructions_{name}": compute_message_signature("".join(lines))
        for name, lines in sections.items()
    }


def _has_request_overrides(settings: Any) -> bool:
    """Reject untracked input/schema overrides without hashing output settings."""
    if getattr(settings, "context_management", None) or getattr(settings, "truncation", None) == "auto":
        return True

    def overrides(value: Any) -> bool:
        if value is None:
            return False
        if not isinstance(value, dict) or _REQUEST_INPUT_OVERRIDE_KEYS.intersection(value):
            return True
        return overrides(value.get("extra_body")) or overrides(value.get("extra_args"))

    return overrides(getattr(settings, "extra_body", None)) or overrides(getattr(settings, "extra_args", None))


def _request_counting_info(context: Any, agent: Any) -> TokenCountingInfo:
    runtime = getattr(context, "runtime_session", None)
    info = getattr(runtime, "token_counting_info", None)
    return info if info is not None else token_counting_info_from_model(getattr(agent, "model", None))


def request_token_model_name(context: Any, agent: Any) -> str:
    """Use immutable route information rather than retained model instances."""
    return _request_counting_info(context, agent).model_name or context.model_run_config.model_name


def request_token_signature(
    context: Any, agent: Any, instructions: str | None, *, components: dict[str, str] | None = None,
) -> str | None:
    """Sign counting semantics, instructions, and wire schemas, not run settings."""
    runtime = getattr(context, "runtime_session", None)
    if components is not None:
        components.clear()

    def unavailable(reason: str) -> None:
        logger.debug(
            "[CTX-BUILD][signature] session=%s request=%s status=unavailable reason=%s",
            getattr(context, "session_id", None), getattr(runtime, "request_identity", None), reason,
        )

    if any(_has_request_overrides(settings) for settings in (
        getattr(agent, "model_settings", None), getattr(runtime, "token_budget_model_settings", None),
    )):
        return unavailable("request_override")
    info = _request_counting_info(context, agent)
    native = info.protocol == "responses"
    logger.debug(
        "[CTX-BUILD][signature] session=%s request=%s status=route_selected "
        "provider=%s source=%s protocol=%s native=%s info=%s",
        getattr(context, "session_id", None), getattr(runtime, "request_identity", None),
        getattr(context, "provider", None),
        "runtime_session" if getattr(runtime, "token_counting_info", None) is not None else "agent_model",
        info.protocol, native, info,
    )
    if info.unavailable_reason is not None:
        return unavailable(info.unavailable_reason)
    model_name = request_token_model_name(context, agent)
    if getattr(agent, "mcp_servers", None) or getattr(agent, "prompt", None):
        return unavailable("mcp_tools" if getattr(agent, "mcp_servers", None) else "remote_prompt")
    tools = []
    for tool in getattr(agent, "tools", None) or []:
        enabled = getattr(tool, "is_enabled", True)
        if not isinstance(enabled, bool):
            return unavailable("dynamic_tool")
        if enabled:
            # Computer schemas also depend on resolved factories/tool choice,
            # neither of which is exposed by the SDK input-filter payload.
            if isinstance(tool, ComputerTool):
                return unavailable("unresolved_computer_schema")
            tools.append(tool)
    handoffs = []
    for value in getattr(agent, "handoffs", None) or []:
        value = handoff(value) if isinstance(value, Agent) else value
        if not isinstance(value.is_enabled, bool):
            return unavailable("dynamic_handoff")
        if value.is_enabled:
            handoffs.append(value)
    names = [tool.name for tool in tools] + [value.tool_name for value in handoffs]
    if len(names) != len(set(names)):
        return unavailable("duplicate_tool_name")
    output = getattr(agent, "output_type", None)
    try:
        output_schema = (
            None if output is None or output is str
            else output if isinstance(output, AgentOutputSchemaBase) else AgentOutputSchema(output)
        )
        if native:
            wire_tools = ResponsesConverter.convert_tools(tools, handoffs, model=model_name).tools
            if info.input_projection == "siada_responses":
                wire_tools = sanitize_responses_tools_for_openai(wire_tools)
            wire_output = ResponsesConverter.get_response_format(output_schema)
        else:
            wire_tools = [Converter.tool_to_openai(tool) for tool in tools]
            wire_tools.extend(Converter.convert_handoff_tool(value) for value in handoffs)
            wire_output = Converter.convert_response_format(output_schema)
        payload = {
            "domain": {"model": model_name, "provider": context.provider,
                       "protocol": "responses" if native else "chat",
                       "input_projection": info.input_projection,
                       "replay_version": _REQUEST_TOKEN_DOMAIN_VERSION},
            "instructions": instructions or "",
            "schemas": {"tools": wire_tools, "output": None if wire_output is omit else wire_output},
        }
        signature = compute_message_signature(payload)
        fingerprints = {
            "domain": compute_message_signature(payload["domain"]),
            "instructions": compute_message_signature(payload["instructions"]),
            "tools": compute_message_signature(payload["schemas"]["tools"]),
            "output": compute_message_signature(payload["schemas"]["output"]),
            **_instruction_components(instructions or ""),
        }
        if components is not None:
            components.update(fingerprints)
        logger.debug(
            "[CTX-BUILD][signature] session=%s request=%s status=computed signature=%s "
            "instructions_chars=%d components=%s",
            getattr(context, "session_id", None), getattr(runtime, "request_identity", None),
            signature, len(instructions or ""), fingerprints,
        )
        return signature
    except (TypeError, ValueError, UserError):
        return unavailable("unsupported_schema")


@dataclass(frozen=True)
class RequestTokenBaseline:
    """Anchor reported total usage to durable input and fully replayed output."""

    signature: str
    items: list[dict]
    input_tokens: int
    session_id: str
    restore_generation: int = 0
    response_tokens: int = 0
    signature_components: dict[str, str] | None = None

    @property
    def context_tokens(self) -> int:
        return self.input_tokens + self.response_tokens

    @classmethod
    def from_response(
        cls, signature: str, items: list[dict], usage: Any, *, session_id: str,
        restore_generation: int = 0,
        signature_components: dict[str, str] | None = None,
    ) -> RequestTokenBaseline | None:
        """Use server total usage, including reasoning, for full response replay.

        Some providers report uncached input but retain cache-inclusive total
        usage. Recover input from total minus output without adding cache twice.
        Output usage already includes reasoning; never tokenize its encrypted
        carrier or visible summary to reconstruct the response budget.
        """
        if usage is None or usage.requests != 1:
            return None
        counts = (usage.input_tokens, usage.output_tokens, usage.total_tokens)
        if any(type(value) is not int or value < 0 for value in counts):
            return None
        tokens = usage.total_tokens - usage.output_tokens
        if tokens <= 0 or tokens < usage.input_tokens:
            return None
        if not isinstance(session_id, str) or not session_id:
            return None
        return cls(signature, copy.deepcopy(items), tokens, session_id, restore_generation,
                   usage.output_tokens, _validated_components(signature_components))

    def to_dict(self) -> dict:
        """Persist a prefix digest, not a second copy of authoritative history."""
        data = {
            "format_version": 4, "signature": self.signature, "input_tokens": self.input_tokens,
            "response_tokens": self.response_tokens,
            "item_count": len(self.items), "prefix_signature": compute_message_signature(self.items),
            "restore_generation": self.restore_generation, "session_id": self.session_id,
        }
        if self.signature_components is not None:
            data["signature_components"] = dict(self.signature_components)
        return data

    @classmethod
    def from_dict(
        cls, data: Any, snapshot: dict, usage: Any, *, session_id: str,
    ) -> RequestTokenBaseline | None:
        """Reject stale or damaged optional anchors without losing actual usage."""
        if not isinstance(data, dict) or type(data.get("format_version")) is not int or data["format_version"] != 4:
            return None
        if not isinstance(session_id, str) or not session_id or data.get("session_id") != session_id:
            return None
        if snapshot.get("session_id", session_id) != session_id:
            return None
        count = data.get("item_count")
        tokens = data.get("input_tokens")
        response_tokens = data.get("response_tokens")
        generation = data.get("restore_generation")
        if (type(count) is not int or count < 0 or count > len(snapshot["items"])
                or type(tokens) is not int or tokens <= 0
                or type(response_tokens) is not int or response_tokens < 0
                or type(generation) is not int or generation != snapshot.get("restore_generation", 0)):
            return None
        for name in ("signature", "prefix_signature"):
            value = data.get(name)
            if not isinstance(value, str) or len(value) != 32 or any(char not in "0123456789abcdef" for char in value):
                return None
        items = snapshot["items"][:count]
        if compute_message_signature(items) != data["prefix_signature"]:
            return None
        baseline = cls.from_response(
            data["signature"], items, usage, restore_generation=generation, session_id=session_id,
            signature_components=_validated_components(data.get("signature_components")),
        )
        return baseline if (baseline is not None and baseline.input_tokens == tokens
                            and baseline.response_tokens == response_tokens) else None


def estimate_request_tokens(context: Any, agent: Any, items: list[dict], instructions: str | None) -> int:
    """Tokenize only additions after the last durably anchored response."""
    state = context.session.state
    baseline = getattr(state, "context_token_baseline", None)
    components: dict[str, str] = {}
    signature = request_token_signature(context, agent, instructions, components=components)
    model_name = request_token_model_name(context, agent)
    runtime = getattr(context, "runtime_session", None)
    session_id = context.session_id
    storage_id = getattr(state.openai_session, "session_id", session_id)
    generation = getattr(runtime, "_restore_generation", None) or 0
    request = getattr(runtime, "request_identity", None)
    if signature is None:
        reason = "signature_unavailable"
    elif baseline is None:
        reason = "no_baseline"
    elif not (
        baseline.session_id == session_id == storage_id
        and getattr(context.session, "session_id", session_id) == session_id
        and getattr(context, "bound_session_id", session_id) == session_id
    ):
        reason = "session_owner_mismatch"
    elif baseline.restore_generation != generation:
        reason = "restore_generation_mismatch"
    elif baseline.signature != signature:
        reason = "signature_mismatch"
        changed = (
            ",".join(sorted(name for name in _SIGNATURE_COMPONENTS
                            if baseline.signature_components[name] != components.get(name)))
            if _validated_components(baseline.signature_components) is not None else "unavailable"
        )
        logger.info(
            "[CTX-BUILD][signature] session=%s request=%s status=mismatch "
            "baseline_signature=%s request_signature=%s changed_components=%s",
            session_id, request, baseline.signature, signature, changed or "none",
        )
        logger.debug(
            "[CTX-BUILD][signature] session=%s request=%s status=mismatch_details "
            "baseline_components=%s request_components=%s",
            session_id, request, _validated_components(baseline.signature_components), components,
        )
    else:
        size = len(baseline.items)
        # Check every item, not just the final item: repairs/offloads may rewrite
        # an earlier tool result while leaving the last message unchanged.
        if len(items) >= size and items[:size] == baseline.items:
            delta = items[size:]
            diagnostics: dict[str, Any] = {}
            delta_tokens = calculate_tokens(model_name, delta, diagnostics=diagnostics) if delta else 0
            tokens = baseline.context_tokens + delta_tokens
            raw_tokens = (
                baseline.context_tokens + diagnostics["raw_tokens"] if diagnostics
                else tokens if not delta else "unavailable"
            )
            logger.info(
                "[CTX-BUILD][effective] session=%s request=%s model=%s token_mode=delta_only "
                "baseline_source=server_usage restore_generation=%d baseline_count=%d "
                "input_tokens=%d response_tokens=%d "
                "baseline_tokens=%d delta_count=%d delta_tokens=%d total=%d "
                "raw_tokens=%s safety_tokens=%s budget_tokens=%d tokenizer_source=%s",
                session_id, request, model_name, generation, size, baseline.input_tokens,
                baseline.response_tokens, baseline.context_tokens, len(delta), delta_tokens, tokens,
                raw_tokens,
                diagnostics.get("safety_tokens", 0 if not delta else "unavailable"), tokens,
                "server_usage+" + diagnostics.get("tokenizer_source", "none" if not delta else "unavailable"),
            )
            return tokens
        reason = "prefix_shortened" if len(items) < size else "prefix_rewritten"
    state.context_token_baseline = None
    message_count: dict[str, Any] = {}
    instruction_count: dict[str, Any] = {}
    tokens = calculate_tokens(model_name, items, tools=getattr(agent, "tools", None), diagnostics=message_count)
    tokens += calculate_tokens(model_name, instructions or "", diagnostics=instruction_count)
    counts = (message_count, instruction_count)
    logger.info(
        "[CTX-BUILD][effective] session=%s request=%s model=%s token_mode=recount_all "
        "reason=%s restore_generation=%d items=%d total=%d "
        "raw_tokens=%s safety_tokens=%s budget_tokens=%d tokenizer_source=%s",
        session_id, request, model_name, reason, generation, len(items), tokens,
        sum(count["raw_tokens"] for count in counts) if all(counts) else "unavailable",
        sum(count["safety_tokens"] for count in counts) if all(counts) else "unavailable", tokens,
        "+".join(count.get("tokenizer_source", "unavailable") for count in counts),
    )
    return tokens