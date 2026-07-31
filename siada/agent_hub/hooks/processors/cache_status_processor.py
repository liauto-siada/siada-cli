"""
Cache Status Processor

Computes per-LLM-call cache hit-rate and miss-reason classification, then
emits the result both to the structured log and (when running in ACP mode)
to the frontend via a `session/update` notification with reason
`cache_status`.

Miss-reason decision tree (first match wins):
  * cold_start          - first request of the session, no prior state
  * model_switched      - last_model != current_model
  * compaction          - compaction strategy just produced a new prefix
  * ttl_expired_5min    - cr=0 and idle > 5 min (Anthropic default cache TTL)
  * prefix_rewrite      - cr=0, cw>0, input<=10 (server is rebuilding cache)
  * prefix_mismatch     - cr=0, large fresh input (entirely new prefix)
  * unknown_miss        - cr=0 but none of the above
  * hit                 - cr>0
"""

import json
import logging
import time
from typing import Any, Optional

from agents import (
    Agent,
    AgentHooks,
    ModelResponse,
    RunContextWrapper,
    TContext,
    TResponseInputItem,
    Tool,
)

from siada.foundation.code_agent_context import CodeAgentContext
from siada.models.model_pricing import calculate_token_cost_breakdown

logger = logging.getLogger(__name__)

# Anthropic prompt-cache default TTL is 5 minutes; OpenAI/DeepSeek implicit
# caches also typically expire on the order of minutes. We use 5min as the
# universal heuristic threshold for "ttl_expired" classification.
TTL_SECONDS = 4 * 60 + 30


class CacheStatusProcessor(AgentHooks):
    """Emit cache hit-rate + miss-reason after every LLM call."""

    @staticmethod
    def _extract_token_data(usage) -> dict:
        """Pull input/output/cache_read/cache_write out of ModelResponse.usage.

        Mirrors TokenUsageReporterProcessor._extract_token_data so that the
        two stay aligned. cache_write is derived from total_tokens because
        the openai-agents SDK normalizes the usage shape and only exposes
        cache_read directly via input_tokens_details.cached_tokens.
        """
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        cache_read = 0
        details = getattr(usage, "input_tokens_details", None)
        if details and getattr(details, "cached_tokens", 0):
            cache_read = details.cached_tokens or 0
        cache_write = 0
        total = getattr(usage, "total_tokens", 0) or 0
        if total > inp + out + cache_read:
            cache_write = total - inp - out - cache_read
        return {
            "input": inp,
            "output": out,
            "cache_read": cache_read,
            "cache_write": cache_write,
        }

    @staticmethod
    def _classify(state: dict, model: str, cr: int, cw: int, inp: int, now: float) -> str:
        last_t = state.get("last_request_at")
        last_m = state.get("last_model")

        if last_t is None:
            return "cold_start"
        if last_m and last_m != model:
            return "model_switched"
        # compaction flag is one-shot; consume it so we don't classify the
        # next normal request as compaction-induced.
        if state.pop("compaction_just_happened", False):
            return "compaction"
        if cr == 0:
            idle = now - last_t
            if idle > TTL_SECONDS:
                return "ttl_expired_5min"
            if cw > 0 and inp <= 10:
                return "prefix_rewrite"
            if inp > 100:
                return "prefix_mismatch"
            return "unknown_miss"
        return "hit"

    async def on_llm_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        try:
            session = getattr(context.context, "session", None)
            if not session or not response.usage:
                return
            cfg = getattr(session, "siada_config", None)
            if not cfg:
                return

            model_name = "unknown"
            try:
                model_name = cfg.llm_config.model_name or "unknown"
            except Exception:
                pass

            # Convert model name to li provider format for pricing lookup.
            li_model_name = model_name
            try:
                from siada.provider.li.coverter import covert_to_li_model_name
                converted = covert_to_li_model_name(model_name)
                if converted:
                    li_model_name = converted
            except Exception:
                pass  # Keep using original model_name; cost calculation will return 0.0

            data = self._extract_token_data(response.usage)
            now = time.time()

            # Persist per-session state on session.state via a plain attribute.
            # SessionState is a dataclass without __slots__, so dynamic
            # attributes are fine and they live for the session's lifetime.
            state = getattr(session.state, "cache_status_state", None) or {}

            request_start = state.get("pending_request_start_at", now)

            reason = self._classify(
                state, model_name, data["cache_read"], data["cache_write"], data["input"], request_start,
            )

            prompt_total = data["input"] + data["cache_read"]
            hit_rate = (data["cache_read"] / prompt_total * 100) if prompt_total else 0.0
            idle_seconds = round(request_start - state["last_request_at"], 1) if state.get("last_request_at") else 0.0

            # Accumulate cache_read/prompt_total across the turn (agent_start ->
            # agent_end) so the displayed hit-rate reflects the average of all
            # LLM calls in this turn, not just the last one.
            state["turn_accumulated_cache_read"] = state.get("turn_accumulated_cache_read", 0) + data["cache_read"]
            state["turn_accumulated_prompt_total"] = state.get("turn_accumulated_prompt_total", 0) + prompt_total
            accumulated_hit_rate = (
                state["turn_accumulated_cache_read"] / state["turn_accumulated_prompt_total"] * 100
            ) if state["turn_accumulated_prompt_total"] else 0.0

            # Accumulate raw token counts across the turn as well, so the
            # displayed token counts stay consistent with the accumulated
            # costs shown alongside them (previously only cost was
            # accumulated while the token counts reflected only the last
            # LLM call, causing cost and token count to disagree).
            state["turn_accumulated_input"] = state.get("turn_accumulated_input", 0) + data["input"]
            state["turn_accumulated_output"] = state.get("turn_accumulated_output", 0) + data["output"]
            state["turn_accumulated_cache_write"] = state.get("turn_accumulated_cache_write", 0) + data["cache_write"]
            # turn_accumulated_cache_read is already tracked above.

            # Calculate cost breakdown for this LLM call. Try the raw model_name
            # first (matches user-defined pricing in ~/.siada-cli/models.json),
            # falling back to the li-provider-converted name for the built-in table.
            costs = calculate_token_cost_breakdown(
                model_name=model_name,
                input_tokens=data["input"],
                output_tokens=data["output"],
                cache_write_tokens=data["cache_write"],
                cache_read_tokens=data["cache_read"],
                fallback_model_name=li_model_name,
            )

            # DEBUG: temporarily trace which model_name/pricing entry was used,
            # to diagnose reports of cost mismatching the expected model's price.
            try:
                from siada.models.model_pricing import get_model_pricing
                _pricing = get_model_pricing(model_name, li_model_name)
                logger.info(
                    "[CacheStatus][DEBUG] cfg_model_name=%r li_model_name=%r "
                    "pricing_matched_model=%r input_price=%s output_price=%s "
                    "cache_write_price=%s cache_read_price=%s "
                    "in=%d out=%d cw=%d cr=%d total_cost=%s",
                    model_name, li_model_name,
                    getattr(_pricing, "model_name", None),
                    getattr(_pricing, "input_price", None),
                    getattr(_pricing, "output_price", None),
                    getattr(_pricing, "cache_write_price", None),
                    getattr(_pricing, "cache_read_price", None),
                    data["input"], data["output"], data["cache_write"], data["cache_read"],
                    costs["total_cost"],
                )
            except Exception:
                logger.exception("[CacheStatus][DEBUG] failed to trace pricing lookup")

            # Accumulate turn costs.
            state["turn_accumulated_input_cost"] = round(
                state.get("turn_accumulated_input_cost", 0.0) + costs["input_cost"], 4)
            state["turn_accumulated_output_cost"] = round(
                state.get("turn_accumulated_output_cost", 0.0) + costs["output_cost"], 4)
            state["turn_accumulated_cache_write_cost"] = round(
                state.get("turn_accumulated_cache_write_cost", 0.0) + costs["cache_write_cost"], 4)
            state["turn_accumulated_cache_read_cost"] = round(
                state.get("turn_accumulated_cache_read_cost", 0.0) + costs["cache_read_cost"], 4)
            state["turn_accumulated_total_cost"] = round(
                state.get("turn_accumulated_total_cost", 0.0) + costs["total_cost"], 4)

            # Calculate turn elapsed time.
            turn_start = state.get("turn_start_time", now)
            cost_time_seconds = round(now - turn_start, 1)

            payload = {
                "model": model_name,
                "input": data["input"],
                "output": data["output"],
                "cache_read": data["cache_read"],
                "cache_write": data["cache_write"],
                "prompt_total": prompt_total,
                "hit_rate": round(hit_rate, 2),
                "accumulated_hit_rate": round(accumulated_hit_rate, 2),
                "reason": reason,
                "idle_seconds": idle_seconds,

                # 本次调用成本
                "input_cost": costs["input_cost"],
                "output_cost": costs["output_cost"],
                "cache_write_cost": costs["cache_write_cost"],
                "cache_read_cost": costs["cache_read_cost"],
                "total_cost": costs["total_cost"],

                # 累计成本
                "accumulated_input_cost": state["turn_accumulated_input_cost"],
                "accumulated_output_cost": state["turn_accumulated_output_cost"],
                "accumulated_cache_write_cost": state["turn_accumulated_cache_write_cost"],
                "accumulated_cache_read_cost": state["turn_accumulated_cache_read_cost"],
                "accumulated_total_cost": state["turn_accumulated_total_cost"],
                "cost_time_seconds": cost_time_seconds,

                # 累计 token 数（与上面的累计成本保持同一口径）
                "accumulated_input": state["turn_accumulated_input"],
                "accumulated_output": state["turn_accumulated_output"],
                "accumulated_cache_write": state["turn_accumulated_cache_write"],
                "accumulated_cache_read": state["turn_accumulated_cache_read"],
            }

            # Update per-session state for the next round.
            state["last_request_at"] = now
            state["last_model"] = model_name
            session.state.cache_status_state = state

            # Push to ACP frontend (best-effort; never break the LLM round).
            try:
                io = getattr(cfg, "io", None)
                if io and getattr(io, "acp_enabled", False) and getattr(io, "acp_adapter", None):
                    from siada.io.acp.message_builder import ACPMessageBuilder
                    builder = ACPMessageBuilder()
                    msg = builder.build_session_update(
                        reason="cache_status",
                        content=json.dumps(payload),
                        metadata={},
                    )
                    io.acp_adapter._send_if_acp(lambda m=msg: m)
            except Exception as e:
                logger.debug(f"[CacheStatus] ACP push failed: {e}")

            # INFO log fallback so terminal/non-ACP runs and post-mortem
            # log analysis can still see the cache classification.
            logger.info(
                "[CacheStatus] hit=%s%% reason=%s input=%d cr=%d cw=%d "
                "out=%d idle=%ss model=%s cost=¥%.4f acc_cost=¥%.4f",
                payload["hit_rate"], reason, data["input"], data["cache_read"],
                data["cache_write"], data["output"], idle_seconds, model_name,
                costs["total_cost"], payload["accumulated_total_cost"],
            )
        except Exception as e:
            logger.debug(f"[CacheStatus] processor failed: {e}")

    # No-op implementations for the rest of the AgentHooks contract.
    async def on_llm_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        system_prompt: Optional[str],
        input_items: list[TResponseInputItem],
    ) -> None:
        try:
            session = getattr(context.context, "session", None)
            if not session:
                return

            state = getattr(session.state, "cache_status_state", None) or {}
            state["pending_request_start_at"] = time.time()
            session.state.cache_status_state = state
        except Exception as e:
            logger.debug(f"[CacheStatus] on_llm_start failed: {e}")

    async def on_agent_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
    ) -> None:
        try:
            session = getattr(context.context, "session", None)
            if not session:
                return
            cfg = getattr(session, "siada_config", None)
            if not cfg:
                return

            state = getattr(session.state, "cache_status_state", None) or {}

            # 检测 turn 边界：turn_active 为 False 时表示新一轮 turn 开始
            if not state.get("turn_active"):
                now = time.time()
                state["turn_active"] = True
                state["turn_start_time"] = now
                state["turn_id"] = state.get("turn_id", 0) + 1

                # 重置累计值
                state["turn_accumulated_input_cost"] = 0.0
                state["turn_accumulated_output_cost"] = 0.0
                state["turn_accumulated_cache_write_cost"] = 0.0
                state["turn_accumulated_cache_read_cost"] = 0.0
                state["turn_accumulated_total_cost"] = 0.0
                state["turn_accumulated_cache_read"] = 0
                state["turn_accumulated_prompt_total"] = 0
                state["turn_accumulated_input"] = 0
                state["turn_accumulated_output"] = 0
                state["turn_accumulated_cache_write"] = 0

                session.state.cache_status_state = state
                logger.debug(
                    "[CacheStatus] new turn #%d started, reset accumulators",
                    state["turn_id"],
                )
        except Exception as e:
            logger.debug(f"[CacheStatus] on_agent_start failed: {e}")

    async def on_agent_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        output: Any,
    ) -> None:
        try:
            session = getattr(context.context, "session", None)
            if not session:
                return
            cfg = getattr(session, "siada_config", None)
            if not cfg:
                return

            state = getattr(session.state, "cache_status_state", None) or {}
            # 关闭 turn 边界：下一次 on_agent_start 会据此判定新一轮 turn 开始
            state["turn_active"] = False
            session.state.cache_status_state = state
        except Exception as e:
            logger.debug(f"[CacheStatus] on_agent_end failed: {e}")

    async def on_tool_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
    ) -> None:
        pass

    async def on_tool_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
        result: str,
    ) -> None:
        pass
