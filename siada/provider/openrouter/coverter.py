def covert_to_openrouter_model_name(model_name: str) -> str:
    temp_model_name = model_name
    if model_name.startswith("claude-"):
        temp_model_name = model_name.replace("claude-", "anthropic/claude-")
    elif model_name.startswith("deepseek-"):
        if model_name == "deepseek-v3-0324":
            temp_model_name = "deepseek-chat-v3-0324"
        temp_model_name = temp_model_name.replace("deepseek-", "deepseek/deepseek-")
    elif model_name.startswith("o3-"):
        temp_model_name = model_name.replace("o3-", "openai/o3-")
    elif model_name.startswith("gpt-"):
        temp_model_name = model_name.replace("gpt-", "openai/gpt-")
    elif model_name.startswith("gemini-"):
        temp_model_name = model_name.replace("gemini-", "google/gemini-")
    elif model_name.startswith("kimi-"):
        temp_model_name = model_name.replace("kimi-", "moonshotai/kimi-")
    return f"openrouter/{temp_model_name}"