from __future__ import annotations

import json
import uuid
from typing import Any

from agents.exceptions import ModelBehaviorError
from google.genai import types
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText, ResponseReasoningItem
from openai.types.responses.response_reasoning_item import Summary

from siada.provider.gemini.replay import encode_replay


class GeminiResponseAssembly:
    def __init__(self, origin: dict[str, str]):
        self.origin = origin
        self.response_id = f"gemini_{uuid.uuid4().hex}"
        self.output: list[Any] = []
        self.usage: types.GenerateContentResponseUsageMetadata | None = None
        self.finish_reason: str | None = None
        self._text_index: int | None = None
        self._reasoning_index: int | None = None
        self._item_parts: dict[int, list[dict[str, Any]]] = {}
        self._content_count = 0

    def add(self, response: types.GenerateContentResponse) -> list[tuple[int, str, str]]:
        if response.usage_metadata:
            self.usage = response.usage_metadata
        candidates = response.candidates or []
        if len(candidates) > 1:
            raise ModelBehaviorError("Gemini model supports one response candidate.")
        if not candidates:
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                raise ModelBehaviorError("Gemini blocked the request.")
            return []
        candidate = candidates[0]
        if candidate.finish_reason:
            self.finish_reason = str(candidate.finish_reason.value)
        if candidate.content is None:
            return []
        content_index = self._content_count
        self._content_count += 1
        deltas = []
        for part_index, part in enumerate(candidate.content.parts or []):
            if part.function_call:
                call = part.function_call
                if not call.name or call.partial_args or call.will_continue:
                    raise ModelBehaviorError("Gemini returned an incomplete function call; streaming function arguments are not supported.")
                item = ResponseFunctionToolCall(id=f"fc_{uuid.uuid4().hex}", type="function_call", status="completed",
                                               call_id=f"call_{uuid.uuid4().hex}", name=call.name, arguments=json.dumps(call.args or {}, ensure_ascii=False))
                index = len(self.output)
                self.output.append(item)
            elif part.text is not None:
                if part.thought:
                    if self._reasoning_index is None:
                        self._reasoning_index = len(self.output)
                        self.output.append(ResponseReasoningItem(id=f"rs_{uuid.uuid4().hex}", type="reasoning", summary=[Summary(type="summary_text", text="")], status="in_progress"))
                    index = self._reasoning_index
                    self.output[index].summary[0].text += part.text
                    deltas.append((index, "reasoning", part.text))
                else:
                    if self._text_index is None:
                        self._text_index = len(self.output)
                        self.output.append(ResponseOutputMessage(id=f"msg_{uuid.uuid4().hex}", type="message", role="assistant", status="in_progress",
                                                                 content=[ResponseOutputText(type="output_text", text="", annotations=[], logprobs=[])]))
                    index = self._text_index
                    self.output[index].content[0].text += part.text
                    deltas.append((index, "message", part.text))
            elif (
                not part.thought_signature
                or set(part.model_dump(exclude_none=True)) - {"thought_signature", "thought"}
            ):
                raise ModelBehaviorError("Gemini returned an unsupported output Part.")
            else:
                if not self.output:
                    self.output.append(ResponseOutputMessage(id=f"msg_{uuid.uuid4().hex}", type="message", role="assistant", status="in_progress", content=[]))
                index = len(self.output) - 1
            self._item_parts.setdefault(index, []).append({
                "content_index": content_index, "part_index": part_index,
                "part": part.model_dump(mode="json", exclude_none=True),
            })
        return deltas

    def finalize(self, *, parallel_tool_calls: bool | None = None) -> list[Any]:
        if self.finish_reason is None:
            raise ModelBehaviorError("Gemini response ended without a finish reason.")
        if self.finish_reason not in {"STOP", "MAX_TOKENS"}:
            raise ModelBehaviorError(f"Gemini response did not complete ({self.finish_reason}).")
        if self.finish_reason == "MAX_TOKENS" and any(item.type == "function_call" for item in self.output):
            raise ModelBehaviorError("Gemini output limit interrupted a tool response; no tools will be executed.")
        if not self.output and self._content_count:
            self.output.append(ResponseOutputMessage(id=f"msg_{uuid.uuid4().hex}", type="message", role="assistant", status="completed", content=[]))
        if not self.output:
            raise ModelBehaviorError("Gemini returned no replayable output.")
        if parallel_tool_calls is False and sum(item.type == "function_call" for item in self.output) > 1:
            raise ModelBehaviorError("Gemini returned parallel calls while parallel_tool_calls is disabled.")
        group_id = f"group_{uuid.uuid4().hex}"
        tool_item_ids = [item.id for item in self.output if item.type == "function_call"]
        for index, item in enumerate(self.output):
            item.status = "completed"
            item.provider_data = {"gemini": encode_replay({
                "origin": self.origin, "response_group_id": group_id,
                "tool_item_ids": tool_item_ids, "parts": self._item_parts.get(index, []),
            })}
        return self.output
