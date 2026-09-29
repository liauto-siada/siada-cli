def covert_to_litellm_model_name(model_name: str) -> str:
    temp_model_name = model_name
    if model_name.startswith("claude-"):
        temp_model_name = model_name.replace("claude-", "anthropic/claude-")
    elif model_name.startswith("deepseek-"):
        if model_name == "deepseek-v3-0324":
            temp_model_name = "deepseek-chat-v3-0324"
        if model_name == "deepseek-v3.1":
            temp_model_name = "deepseek-chat-v3.1"
        temp_model_name = temp_model_name.replace("deepseek-", "deepseek/deepseek-")
    elif model_name == "o3" or model_name.startswith("o3-"):
        temp_model_name = "openai/" + model_name
    elif model_name.startswith("gpt-") and "codex" in model_name:
        # Codex models use OpenAI Responses API, not Chat Completions.
        # Using openai/responses/<name> forces litellm's responses_api_bridge regardless
        # of whether the model is in litellm's registry.
        temp_model_name = f"openai/responses/{model_name}"
    elif model_name == "codex-mini-latest":
        temp_model_name = "openai/responses/codex-mini-latest"
    elif model_name.startswith("gpt-"):
        temp_model_name = model_name.replace("gpt-", "openai/gpt-")
    elif model_name.startswith("gemini-"):
        # litellm's Google AI Studio prefix is "gemini/" (verified against
        # litellm 1.91: "google/gemini-*" is NOT a recognized provider prefix
        # and fails with "LLM Provider NOT provided"; "gemini/gemini-*"
        # routes to the native generateContent protocol, where a top-level
        # reasoning_effort is mapped to generationConfig.thinkingConfig.
        # thinkingLevel).
        temp_model_name = model_name.replace("gemini-", "gemini/gemini-", 1)
    elif model_name.startswith("kimi-"):
        temp_model_name = model_name.replace("kimi-", "moonshot/kimi-")
    elif model_name.startswith("glm-"):
        # ZhipuAI GLM — OpenAI-compatible API, base_url overrides endpoint
        temp_model_name = f"openai/{model_name}"
    elif (model_name.startswith("MiniMax-") or model_name.startswith("minimax-")
          or model_name.startswith("abab")):
        # MiniMax — OpenAI-compatible API, base_url overrides endpoint
        temp_model_name = f"openai/{model_name}"
    return temp_model_name