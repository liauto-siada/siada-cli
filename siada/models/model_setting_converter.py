from agents import ModelSettings
from siada.models.model_base_config import (
    is_claude_4_6_or_newer,
    is_claude_model,
    is_gemini_model,
    is_glm_model,
    is_glm_5_3_or_newer,
    is_qwen_model,
)
from siada.models.model_run_config import ModelRunConfig
from siada.provider.responses.responses_model import is_responses_only_model
from openai.types.shared import Reasoning


class ModelSettingsConverter:
    """Converts a ``ModelRunConfig`` into provider-ready ``ModelSettings``.

    ALL reasoning-parameter translation lives here; providers forward the
    result verbatim (``LiModel._fetch_response`` / the SDK's
    ``LitellmModel._fetch_response``) without further post-processing:

    * ``extra_args``  -> top-level litellm kwargs (params the provider
      natively accepts: ``thinking`` / ``output_config`` for anthropic).
    * ``extra_body``  -> litellm's ``extra_body``, merged verbatim into the
      HTTP request body. Required for params litellm would silently drop
      under ``drop_params=True`` (``reasoning_effort``, GLM's ``thinking``
      dict).
    * ``ModelSettings.reasoning`` -> top-level ``reasoning_effort`` kwarg
      for providers that map it natively (Gemini -> thinkingLevel; Claude's
      default effort).

    Wire formats per family (verified against litellm 1.91.0 and the
    li-mate test gateway):

    - Effort is the ONLY strength control: token budgets are NEVER emitted.
    - Explicit disable (--no-thinking / ``enable_thinking: false``) is the
      ABSOLUTE off-switch — it wins over any effort/thinking_tokens config,
      including model defaults.
    - Claude 4.6+: always ``thinking: {type: "adaptive", display:
      "summarized"}`` + effort via ``output_config`` (4.6+-only capability);
      disable -> ``{type: "disabled"}`` with no output_config. Pre-4.6 sends
      no thinking/effort param. Effort defaults to ``high`` via
      ``ModelSettings.reasoning`` when thinking is on and no effort is set.
    - Gemini: top-level ``reasoning_effort`` (litellm -> thinkingLevel).
    - GPT-5.x: ``extra_body.reasoning`` (hoisted by ``ResponsesModel`` to
      the Responses-API ``reasoning`` param); disable -> ``effort: "none"``.
    - GLM (all versions): ``extra_body.thinking = {type: "enabled",
      clear_thinking: False}`` (preserved thinking for multi-turn replay) +
      ``reasoning_effort``, omitted when ``max`` (the gateway default — Zhipu
      rejects an explicit "max"). GLM 5.3 cannot disable thinking at all —
      the disable degrades to ``effort: "low"``; GLM 5.2 sends
      ``{type: "disabled"}`` (currently ignored by the gateway, kept for
      forward compatibility).
    - Others (deepseek/qwen/kimi/gpt-4.x): Qwen gets
      ``enable_thinking: true`` + ``preserve_thinking: true`` (DashScope
      switch, counterpart of GLM's clear_thinking=False); others raise
      ``enable_thinking: true`` only as the "thinking on" signal from
      thinking_tokens. Effort rides ``extra_body.reasoning_effort``. Disable:
      Qwen -> ``enable_thinking: false``; others -> the generic
      ``thinking: {type: "disabled"}`` (LiProvider translates this into
      ``enable_thinking: false`` for kivy-* models — an li-gateway-only
      concern). Temperature stays None whenever reasoning is on.
    """

    @staticmethod
    def convert_model_settings(model_running_config: ModelRunConfig) -> ModelSettings:
        model_name = model_running_config.model_name
        effort = model_running_config.get_reasoning_effort()
        thinking_tokens = model_running_config.get_raw_thinking_tokens()

        extra_body = {}
        extra_args = {}
        reasoning_item: Reasoning | None = None

        if is_claude_model(model_name):
            # Claude's thinking/output_config must ride ``extra_args`` (top-level
            # litellm kwargs): the "anthropic" provider — used by BOTH the li
            # gateway and the default provider — does NOT unwrap ``extra_body``,
            # so a literal "extra_body" key reaches the request body and the
            # gateway rejects it with "Extra inputs are not permitted". See
            # tests/provider/test_claude_param_channel.py.
            if is_claude_4_6_or_newer(model_name):
                # 4.6+ ALWAYS thinks adaptively; an explicit disable is the
                # absolute off-switch ({"type": "disabled"} — omission would
                # fall back to the model default, thinking ON).
                if model_running_config.enable_thinking is False:
                    extra_args["thinking"] = {"type": "disabled"}
                else:
                    extra_args["thinking"] = {"type": "adaptive", "display": "summarized"}
                    if effort is not None:
                        extra_args["output_config"] = {"effort": effort}
            # Pre-4.6: no adaptive, no budgets, effort is 4.6+-only — nothing sent.
            # Default effort=high (ModelSettings.reasoning) when thinking is on
            # and no effort is set — but NOT when an effort is configured:
            # providers surface ModelSettings.reasoning as a top-level
            # reasoning_effort kwarg, which litellm's Anthropic transformation
            # uses to OVERWRITE the thinking/output_config from extra_args.
            thinking_requested = (
                is_claude_4_6_or_newer(model_name)
                and model_running_config.enable_thinking is not False
            )
            if not is_claude_4_6_or_newer(model_name) and (
                model_running_config.enable_thinking is not False
            ):
                # Pre-4.6: thinking_tokens is the "thinking on" signal (and the
                # disable wins over a concurrently configured thinking_tokens).
                thinking_requested = thinking_tokens is not None
            if thinking_requested and effort is None:
                reasoning_item = Reasoning(effort="high")

        elif is_gemini_model(model_name):
            # For Gemini 3+, reasoning_effort is mapped to thinkingLevel by litellm
            # (e.g., "low"→"low", "medium"→"medium", "high"→"high")
            if effort is not None:
                reasoning_item = Reasoning(effort=effort)

        elif is_responses_only_model(model_name):
            # GPT-5.x: routed to the native Responses API — ``ResponsesModel``
            # hoists extra_body["reasoning"] to the top-level ``reasoning``
            # request param, which drives reasoning_summary_text events.
            responses_reasoning = {}
            if model_running_config.enable_thinking is False:
                # effort="none" fully turns reasoning OFF; without it the
                # SDK's low-effort default would silently re-enable it.
                responses_reasoning["effort"] = "none"
            elif effort is not None:
                responses_reasoning["effort"] = effort
            if responses_reasoning:
                extra_body["reasoning"] = responses_reasoning

        else:
            # OpenAI-protocol chat models (deepseek / qwen / glm / kimi /
            # gpt-4.x ...). An explicit disable is the absolute off-switch.
            if model_running_config.enable_thinking is False:
                if is_glm_model(model_name):
                    if is_glm_5_3_or_newer(model_name):
                        # GLM-5.3+ cannot disable thinking — the gateway rejects
                        # {"type": "disabled"} with "this model always thinks, so thinking cannot be
                        # disabled; use low, high or max". Degrade to the minimum effort.
                        extra_body["thinking"] = {"type": "enabled", "clear_thinking": False}
                        extra_body["reasoning_effort"] = "low"
                    else:
                        # GLM-5.2 currently ignores {"type": "disabled"} (keeps
                        # thinking) but accepts it — kept for when the gateway
                        # supports it.
                        extra_body["thinking"] = {"type": "disabled"}
                elif is_qwen_model(model_name):
                    # DashScope's native switch; the thinking dict is not.
                    extra_body["enable_thinking"] = False
                else:
                    # Generic disable form. (kivy-* models speak
                    # enable_thinking=false instead — LiProvider translates
                    # this for them; the default provider never serves kivy.)
                    extra_body["thinking"] = {"type": "disabled"}
            elif effort is not None or thinking_tokens is not None:
                if is_glm_model(model_name):
                    # Preserved thinking (clear_thinking=False) keeps reasoning
                    # content in responses for multi-turn replay. Must travel
                    # via extra_body: a top-level ``thinking`` kwarg is not in
                    # the openai provider's supported-params list and would be
                    # dropped under drop_params=True.
                    extra_body["thinking"] = {"type": "enabled", "clear_thinking": False}
                    # GLM (all versions) sets strength via reasoning_effort
                    # (low/high/max); Zhipu rejects an explicit "max" (also the
                    # gateway default), so omit it and let the gateway default.
                    if effort is not None and effort != "max":
                        extra_body["reasoning_effort"] = effort
                else:
                    # Qwen: DashScope expects enable_thinking alongside
                    # preserve_thinking (its counterpart of clear_thinking=False).
                    # Others: enable_thinking only as the "thinking on" signal
                    # from thinking_tokens. (kivy-* gateways default it on their
                    # own when reasoning params are present.)
                    if is_qwen_model(model_name):
                        extra_body["enable_thinking"] = True
                        extra_body["preserve_thinking"] = True
                    elif thinking_tokens is not None and thinking_tokens > 0:
                        extra_body["enable_thinking"] = True
                    # Effort rides extra_body: a top-level reasoning_effort kwarg
                    # is dropped by drop_params for these openai-protocol models.
                    # (Kimi K3+'s "max"-omission is an li-gateway concern and is
                    # applied in LiProvider, not here.)
                    if effort is not None:
                        extra_body["reasoning_effort"] = effort

        tool_choice = "auto"
        if model_running_config.extra_params and "tool_choice" in model_running_config.extra_params:
            tool_choice = model_running_config.extra_params["tool_choice"]

        return ModelSettings(
            max_tokens=model_running_config.max_tokens,
            extra_body=extra_body or None,
            extra_args=extra_args or None,
            tool_choice=tool_choice,
            parallel_tool_calls=model_running_config.parallel_tool_calls,
            include_usage=True,
            reasoning=reasoning_item,
        )

