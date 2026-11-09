from __future__ import annotations

import base64
import copy
import json
import mimetypes
from typing import Any
from urllib.parse import urlparse

from agents import AgentOutputSchemaBase, Handoff, ModelSettings
from agents.exceptions import UserError
from agents.tool import FunctionTool, Tool
from google.genai import types
from siada.provider.gemini.replay import MISSING_SIGNATURE_BYPASS, decode_replay, imported_tool_item, legacy_item_parts, replay_data
from siada.provider.gemini.routing import wire_model_name


def _item_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    return item.model_dump(mode="json", exclude_unset=True)


def _parts(content: Any) -> list[types.Part]:
    if isinstance(content, str):
        return [types.Part(text=content)]
    result = []
    for part in content or []:
        kind = part.get("type")
        if kind in {"input_text", "output_text", "text"}:
            result.append(types.Part(text=part["text"]))
        elif kind in {"input_image", "image_url"}:
            url = part.get("image_url")
            url = url.get("url") if isinstance(url, dict) else url
            if not isinstance(url, str):
                raise UserError("Gemini image input requires an image URL or data URL.")
            if url.startswith("data:"):
                header, encoded = url.split(",", 1)
                if not header.endswith(";base64"):
                    raise UserError("Gemini inline images require Base64 encoding.")
                result.append(types.Part.from_bytes(data=base64.b64decode(encoded, validate=True), mime_type=header[5:-7]))
            else:
                mime_type = mimetypes.guess_type(urlparse(url).path)[0]
                if not mime_type or not mime_type.startswith("image/"):
                    raise UserError("Gemini image URI needs a recognizable image extension; otherwise use a typed data URL.")
                result.append(types.Part.from_uri(file_uri=url, mime_type=mime_type))
        elif kind == "refusal":
            result.append(types.Part(text=part["refusal"]))
        else:
            raise UserError("This input content type is not supported by the native Gemini model.")
    return result


def _function_response(output: Any, call: types.FunctionCall) -> types.Part:
    media_parts: list[types.FunctionResponsePart] = []
    if isinstance(output, str):
        text = output
    elif isinstance(output, list) and all(isinstance(part, dict) for part in output):
        text_parts: list[str] = []
        for part in _parts(output):
            if part.text is not None:
                text_parts.append(part.text)
            elif part.inline_data is not None:
                data = part.inline_data.data
                mime_type = part.inline_data.mime_type
                if not data or not mime_type or not mime_type.startswith("image/"):
                    raise UserError("Gemini tool images require nonempty image data and an image MIME type.")
                media_parts.append(types.FunctionResponsePart.from_bytes(data=data, mime_type=mime_type))
            else:
                raise UserError("Gemini tool images require Base64 data URLs; external image URIs are not supported.")
        text = "".join(text_parts)
    else:
        raise UserError("Gemini function results require text or a list of text and image content.")
    return types.Part(function_response=types.FunctionResponse(
        id=call.id, name=call.name, response={"output": text}, parts=media_parts or None,
    ))


def _imported_function_call(item: dict[str, Any]) -> tuple[types.FunctionCall, types.Part]:
    """Adapt a foreign call with the documented signature validation bypass."""
    name = item.get("name")
    if not isinstance(name, str) or not name:
        raise UserError("Imported tool calls require a nonempty function name.")
    arguments = None
    if isinstance(item.get("arguments"), str):
        try:
            arguments = json.loads(item["arguments"])
        except json.JSONDecodeError:
            pass
    if not isinstance(arguments, dict):
        raise UserError("Imported tool arguments must be a JSON object.")
    call = types.FunctionCall(name=name, args=arguments)
    # The marker is already the API's JSON bytes representation. Passing its
    # UTF-8 bytes instead would Base64-encode it again on the wire.
    part = types.Part.model_validate({
        "function_call": call, "thought_signature": MISSING_SIGNATURE_BYPASS,
    })
    return call, part


def _validate_replay_item(item: dict[str, Any], parts: list[types.Part]) -> types.FunctionCall | None:
    calls = [part.function_call for part in parts if part.function_call is not None]
    kind = item.get("type")
    if kind == "function_call":
        if len(calls) != 1 or calls[0].name != item["name"] or (calls[0].args or {}) != json.loads(item["arguments"]):
            raise UserError("Gemini tool view no longer matches its native signed Part.")
        return calls[0]
    if calls:
        raise UserError("Gemini message replay contains an unexpected function call.")
    text = "".join(part.text or "" for part in parts)
    if kind == "reasoning":
        visible = "".join(part.get("text", "") for part in item.get("summary", []))
    elif kind == "message" and item.get("role") == "assistant":
        visible = "".join(part.text or "" for part in _parts(item.get("content")))
    else:
        raise UserError("Gemini replay metadata belongs to a model output item.")
    if visible != text:
        raise UserError("Gemini text view no longer matches its native signed Parts.")
    return None


def _native_replay_groups(
    inputs: list[dict[str, Any]], payloads: list[dict[str, Any] | None], origin: dict[str, str],
) -> dict[str, tuple[list[types.Content], list[tuple[str, types.FunctionCall]]]]:
    groups: dict[str, list[tuple[int, dict[str, Any], dict[str, Any]]]] = {}
    for index, (item, payload) in enumerate(zip(inputs, payloads)):
        if payload is not None:
            if payload.get("origin") != origin:
                raise UserError("Gemini signature origin changed; start a new session instead of replaying across backends.")
            group_id = payload["response_group_id"]
            if not isinstance(group_id, str) or not group_id:
                raise UserError("Invalid Gemini response group identity.")
            groups.setdefault(group_id, []).append((index, item, payload))
    native_groups = {}
    for group_id, members in groups.items():
        positions = [index for index, _item, _payload in members]
        if positions != list(range(positions[0], positions[0] + len(members))):
            raise UserError("Gemini response group was split by another history item.")
        legacy = [payload for _index, item, payload in members if replay_data(item)["version"] == 1]
        if legacy:
            owners = [payload for payload in legacy if "contents" in payload]
            if len(legacy) != len(members) or len(owners) != 1:
                raise UserError("Legacy Gemini response group has no unique native owner.")
            owner = owners[0]
            member_ids = [item["id"] for _index, item, _payload in members]
            if [item_id for item_id in owner["item_ids"] if item_id in member_ids] != member_ids:
                raise UserError("Legacy Gemini response group was split or reordered.")
            retained_calls = sum(item.get("type") == "function_call" for _index, item, _payload in members)
            original_calls = sum(bool(part.get("function_call")) for content in owner["contents"] for part in content.get("parts", []))
            if retained_calls and retained_calls != original_calls:
                raise UserError("Legacy Gemini parallel tool group was split.")
            records_by_item = [legacy_item_parts(item, owner["contents"]) for _index, item, _payload in members]
            assigned = {(record["content_index"], record["part_index"]) for records in records_by_item for record in records}
            for content_index, content in enumerate(owner["contents"]):
                for part_index, part in enumerate(content.get("parts", [])):
                    if (content_index, part_index) not in assigned and set(part) <= {"thought_signature", "thought"}:
                        records_by_item[-1].append({"content_index": content_index, "part_index": part_index, "part": part})
        else:
            tool_ids = [item["id"] for _index, item, _payload in members if item.get("type") == "function_call"]
            if tool_ids and any(payload.get("tool_item_ids") != tool_ids for _index, _item, payload in members):
                raise UserError("Gemini parallel tool group was split or reordered.")
            records_by_item = [payload["parts"] for _index, _item, payload in members]
        native_parts: dict[int, dict[int, types.Part]] = {}
        calls = []
        for (_index, item, _payload), records in zip(members, records_by_item):
            records = sorted(records, key=lambda record: (record["content_index"], record["part_index"]))
            parts = [types.Part.model_validate(record["part"]) for record in records]
            call = _validate_replay_item(item, parts)
            if call is not None:
                calls.append((item["call_id"], call))
            for record, part in zip(records, parts):
                content_index, part_index = record["content_index"], record["part_index"]
                if type(content_index) is not int or type(part_index) is not int or min(content_index, part_index) < 0:
                    raise UserError("Invalid Gemini replay Part position.")
                content_parts = native_parts.setdefault(content_index, {})
                if part_index in content_parts:
                    raise UserError("Gemini replay Part is owned by more than one item.")
                content_parts[part_index] = part
        group_parts = [parts[index] for _content_index, parts in sorted(native_parts.items()) for index in sorted(parts)]
        native_groups[group_id] = ([types.Content(role="model", parts=group_parts)] if group_parts else [], calls)
    return native_groups


def items_to_contents(items: str | list[Any], origin: dict[str, str]) -> tuple[list[types.Content], list[types.Part]]:
    if isinstance(items, str):
        return [types.Content(role="user", parts=[types.Part(text=items)])], []
    inputs = [imported_tool_item(_item_dict(item)) for item in items]
    payloads = [decode_replay(item) for item in inputs]
    native_groups = _native_replay_groups(inputs, payloads, origin)

    contents: list[types.Content] = []
    instructions: list[types.Part] = []
    pending: dict[str, types.FunctionCall] = {}
    results: dict[str, types.Part] = {}
    imported_parts: list[types.Part] = []
    seen_call_ids: set[str] = set()

    def register_call(call_id: Any, call: types.FunctionCall) -> None:
        if not isinstance(call_id, str) or not call_id or call_id in seen_call_ids:
            raise UserError("Gemini tool history requires unique nonempty call IDs.")
        seen_call_ids.add(call_id)
        pending[call_id] = call

    def flush_results() -> None:
        if not pending:
            return
        if set(pending) != set(results):
            raise UserError("Gemini tool history is missing a function result; complete or restore the tool round first.")
        if imported_parts:
            contents.append(types.Content(role="model", parts=list(imported_parts)))
            imported_parts.clear()
        contents.append(types.Content(role="user", parts=[results[call_id] for call_id in pending]))
        pending.clear()
        results.clear()

    for item, metadata in zip(inputs, payloads):
        if metadata is not None:
            native_group = native_groups.pop(metadata["response_group_id"], None)
            if native_group is None:
                continue
            flush_results()
            native, calls = native_group
            contents.extend(native)
            for call_id, call in calls:
                register_call(call_id, call)
            continue
        kind = item.get("type")
        if kind == "function_call_output":
            call_id = item["call_id"]
            call = pending.get(call_id)
            if call is None or call_id in results:
                raise UserError("Gemini tool result has no unique call in this response group.")
            results[call_id] = _function_response(item.get("output", ""), call)
        elif kind == "function_call":
            if not imported_parts:
                flush_results()
            call, part = _imported_function_call(item)
            register_call(item.get("call_id"), call)
            # Foreign items lack response groups. Keep a contiguous tool block
            # together, including call/result pairs interleaved by Chat adapters.
            imported_parts.append(part)
        elif kind == "reasoning":
            if imported_parts and len(results) == len(pending):
                flush_results()
            continue
        elif kind in {None, "message"} and item.get("role") in {"system", "developer", "user", "assistant"}:
            parts = _parts(item.get("content"))
            if imported_parts and len(results) < len(pending) and item["role"] == "assistant":
                imported_parts.extend(parts)
                continue
            flush_results()
            if item["role"] in {"system", "developer"}:
                instructions.extend(parts)
            else:
                contents.append(types.Content(role="model" if item["role"] == "assistant" else "user", parts=parts))
        else:
            raise UserError("This history item is not supported by the native Gemini model.")
    flush_results()
    return contents, instructions


def function_declarations(tools: list[Tool], handoffs: list[Handoff]) -> list[types.FunctionDeclaration]:
    declarations = []
    for tool in tools:
        if not isinstance(tool, FunctionTool) or getattr(tool, "namespace", None):
            raise UserError("Native Gemini supports unnamespaced function tools; hosted tools require their native provider.")
        declarations.append(types.FunctionDeclaration(name=tool.name, description=tool.description, parameters_json_schema=tool.params_json_schema))
    for handoff in handoffs:
        declarations.append(types.FunctionDeclaration(name=handoff.tool_name, description=handoff.tool_description, parameters_json_schema=handoff.input_json_schema))
    return declarations


def build_config(settings: ModelSettings, tools: list[Tool], handoffs: list[Handoff], output_schema: AgentOutputSchemaBase | None,
                 instructions: str | None, extra_instructions: list[types.Part], model: str) -> types.GenerateContentConfig:
    extra = copy.deepcopy(settings.extra_body or {})
    extra.update(copy.deepcopy(settings.extra_args or {}))
    timeout = extra.pop("timeout", settings.timeout)
    protected = {"contents", "model", "tools", "system_instruction", "systemInstruction", "http_options", "httpOptions", "automatic_function_calling", "automaticFunctionCalling"}
    if protected.intersection(extra) or settings.extra_query or settings.context_management or settings.truncation == "auto":
        raise UserError("Gemini request ownership fields cannot be overridden through ModelSettings.")
    if any(getattr(settings, name) is not None for name in ("verbosity", "metadata", "prompt_cache_retention", "prompt_cache_options", "response_include", "top_logprobs")) or settings.store is True:
        raise UserError("This OpenAI-specific ModelSettings option is not supported by native Gemini.")
    unknown = set(extra) - set(types.GenerateContentConfig.model_fields) - {field.alias for field in types.GenerateContentConfig.model_fields.values() if field.alias}
    if unknown:
        raise UserError("Use official GenerateContentConfig field names in Gemini extra_body/extra_args.")
    config = types.GenerateContentConfig.model_validate(extra)
    config.automatic_function_calling = types.AutomaticFunctionCallingConfig(disable=True)
    config.candidate_count = 1
    config.http_options = types.HttpOptions(headers=dict(settings.extra_headers or {}), timeout=int(timeout * 1000) if timeout else None,
                                           retry_options=types.HttpRetryOptions(attempts=1))
    system_parts = ([types.Part(text=instructions)] if instructions else []) + extra_instructions
    if system_parts:
        config.system_instruction = types.Content(parts=system_parts)
    for source, target in (("temperature", "temperature"), ("top_p", "top_p"), ("max_tokens", "max_output_tokens"),
                           ("frequency_penalty", "frequency_penalty"), ("presence_penalty", "presence_penalty")):
        value = getattr(settings, source)
        if value is not None:
            setattr(config, target, value)
    declarations = function_declarations(tools, handoffs)
    if declarations:
        config.tools = [types.Tool(function_declarations=declarations)]
    if settings.tool_choice is not None:
        choice = settings.tool_choice
        if not isinstance(choice, str):
            raise UserError("Gemini tool_choice must be auto, none, required or a function name.")
        if choice not in {"auto", "none", "required"}:
            mode, allowed = "ANY", [choice]
        else:
            mode, allowed = {"auto": "AUTO", "none": "NONE", "required": "ANY"}[choice], None
        config.tool_config = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode=mode, allowed_function_names=allowed))
    if output_schema is not None and not output_schema.is_plain_text():
        config.response_mime_type = "application/json"
        config.response_json_schema = output_schema.json_schema()
    if settings.reasoning is not None:
        effort = settings.reasoning.effort
        thinking = config.thinking_config or types.ThinkingConfig()
        if effort == "none":
            thinking.thinking_budget = 0
            thinking.thinking_level = None
        elif effort:
            if not wire_model_name(model).lower().startswith(("gemini-3", "gemini-4")):
                raise UserError("Use native thinking_config for Gemini models without thinkingLevel support.")
            thinking.thinking_budget = None
            thinking.thinking_level = types.ThinkingLevel({"minimal": "MINIMAL", "low": "LOW", "medium": "MEDIUM", "high": "HIGH", "xhigh": "HIGH", "max": "HIGH"}[effort])
        if settings.reasoning.summary:
            thinking.include_thoughts = True
        config.thinking_config = thinking
    return config
