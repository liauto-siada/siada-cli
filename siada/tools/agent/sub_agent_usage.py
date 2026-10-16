"""Run-scoped request accounting for a sub-agent's transcript."""

import json
import time
from dataclasses import asdict, is_dataclass
from typing import Callable

from agents import Agent, ModelResponse, RunContextWrapper, RunHooks, TResponseInputItem

from siada.agent_hub.hooks.processors.cache_status_processor import CacheStatusProcessor
from siada.foundation.logging import logger
from siada.foundation.code_agent_context import CodeAgentContext
from siada.models.model_pricing import calculate_token_cost_breakdown, get_model_pricing


class SubAgentUsageHooks(RunHooks):
    """Keep accounting independent of tracing and the parent session's usage."""

    def __init__(self, model_name: str, append: Callable[[str, str], None]) -> None:
        self.model_name = model_name
        self.append = append
        self.started_at = time.perf_counter()
        self.pending_start: float | None = None
        self.request_count = 0
        self.sdk_request_count = 0
        self.tokens = dict(input=0, output=0, cache_read=0, cache_write=0, total=0)
        self.reasoning_tokens = 0
        self.total_cost = 0.0
        self.unknown_cost_requests = 0
        self.model_duration = 0.0

    async def on_llm_start(
        self, context: RunContextWrapper[CodeAgentContext], agent: Agent,
        system_prompt: str | None, input_items: list[TResponseInputItem],
    ) -> None:
        self.request_count += 1
        self.pending_start = time.perf_counter()

    async def on_llm_end(
        self, context: RunContextWrapper[CodeAgentContext], agent: Agent,
        response: ModelResponse,
    ) -> None:
        duration = self._end_request()
        try:
            usage = response.usage
            if usage is None or (
                getattr(usage, "requests", None) == 0
                and not getattr(usage, "request_usage_entries", [])
                and not any(getattr(usage, key, 0) for key in ("input_tokens", "output_tokens", "total_tokens"))
            ):
                # The SDK substitutes an empty Usage when no usage was returned.
                self.unknown_cost_requests += 1
                self._append("request_usage", self._request_header(duration) + "\nTokens: unavailable\nCost: unavailable (no usage)")
                return
            data = CacheStatusProcessor._extract_token_data(usage)
            # Responses usage can report cache writes explicitly without
            # including them in total_tokens. Zero is also the SDK default
            # for providers that omit the field, so retain inference there.
            details = getattr(usage, "input_tokens_details", None)
            explicit_cache_write = getattr(details, "cache_write_tokens", 0) or 0
            if explicit_cache_write > 0:
                data["cache_write"] = explicit_cache_write
            data["total"] = getattr(usage, "total_tokens", 0) or 0
            sdk_requests = getattr(usage, "requests", 0) or 0
            self.sdk_request_count += sdk_requests
            for key, value in data.items():
                self.tokens[key] += value
            output_details = getattr(usage, "output_tokens_details", None)
            reasoning_tokens = getattr(output_details, "reasoning_tokens", None)
            if reasoning_tokens is not None:
                self.reasoning_tokens += reasoning_tokens

            # Raw configured names preserve user-defined pricing; the public
            # provider set has no gateway alias, so the name is used as-is.
            if get_model_pricing(self.model_name) is None:
                self.unknown_cost_requests += 1
                cost_text = "Cost: unavailable (model pricing not configured)"
            else:
                costs = calculate_token_cost_breakdown(
                    self.model_name, data["input"], data["output"],
                    cache_write_tokens=data["cache_write"],
                    cache_read_tokens=data["cache_read"],
                )
                self.total_cost = round(self.total_cost + costs["total_cost"], 4)
                cost_text = (
                    f"Cost: CNY {costs['total_cost']:.4f} "
                    f"(Input={costs['input_cost']:.4f}, Output={costs['output_cost']:.4f}, "
                    f"CacheRead={costs['cache_read_cost']:.4f}, CacheWrite={costs['cache_write_cost']:.4f})"
                )
            self._append(
                "request_usage",
                self._request_header(duration)
                + f"\nSDK Reported Requests: {sdk_requests}\n"
                + self._token_text(data)
                + f"\nReasoning Tokens: {reasoning_tokens if reasoning_tokens is not None else 'unavailable'}"
                + "\nUsage Details:\n" + self._usage_details(usage)
                + "\n" + cost_text,
            )
        except Exception:
            self.unknown_cost_requests += 1
            logger.warning("[sub_agent_usage] failed to record request usage", exc_info=True)

    def _append(self, kind: str, text: str) -> None:
        try:
            self.append(kind, text)
        except Exception:
            logger.warning("[sub_agent_usage] failed to append accounting", exc_info=True)

    def _end_request(self) -> float:
        duration = (
            time.perf_counter() - self.pending_start
            if self.pending_start is not None else 0.0
        )
        self.pending_start = None
        self.model_duration += duration
        return duration

    def _request_header(self, duration: float) -> str:
        return f"Request: {self.request_count}\nModel: {self.model_name}\nDuration: {duration:.3f}s"

    @staticmethod
    def _usage_details(usage: object) -> str:
        """Preserve SDK token details without copying response content."""
        def details_dict(details: object) -> dict:
            model_dump = getattr(details, "model_dump", None)
            if callable(model_dump):
                return model_dump()
            if is_dataclass(details) and not isinstance(details, type):
                return asdict(details)
            return vars(details)

        try:
            return json.dumps(
                {
                    "requests": getattr(usage, "requests", None),
                    "input_tokens": getattr(usage, "input_tokens", None),
                    "input_tokens_details": getattr(usage, "input_tokens_details", None),
                    "output_tokens": getattr(usage, "output_tokens", None),
                    "output_tokens_details": getattr(usage, "output_tokens_details", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                    "request_usage_entries": getattr(usage, "request_usage_entries", []),
                },
                indent=2, default=details_dict, allow_nan=False,
            )
        except Exception:
            logger.warning("[sub_agent_usage] failed to serialize usage details", exc_info=True)
            return "unavailable (SDK usage details could not be serialized)"

    @staticmethod
    def _token_text(data: dict[str, int]) -> str:
        return (
            f"Tokens: Input={data['input']}, Output={data['output']}, "
            f"CacheRead={data['cache_read']}, CacheWrite={data['cache_write']}, Total={data['total']}"
        )

    def record_incomplete_request(self, status: str) -> None:
        """Close a failed request before another attempt replaces its timer."""
        if self.pending_start is not None:
            duration = self._end_request()
            self.unknown_cost_requests += 1
            self._append(
                "request_usage",
                self._request_header(duration)
                + f"\nStatus: {status}\nTokens: unavailable\nCost: unavailable (request did not complete)",
            )

    def finish(self, status: str) -> None:
        """Record unfinished requests without inventing usage or charges."""
        self.record_incomplete_request(status)
        self._append(
            "usage_summary",
            f"Status: {status}\nRequests: {self.request_count}\n"
            f"SDK Reported Requests: {self.sdk_request_count}\n"
            f"Duration: {time.perf_counter() - self.started_at:.3f}s\n"
            f"Model Request Duration: {self.model_duration:.3f}s\n"
            + self._token_text(self.tokens)
            + f"\nReasoning Tokens (SDK): {self.reasoning_tokens}"
            + f"\nKnown Cost: CNY {self.total_cost:.4f}\n"
            f"Requests with unknown cost: {self.unknown_cost_requests}",
        )