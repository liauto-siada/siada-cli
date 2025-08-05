
def covert_to_li_model_name(model_name: str) -> str:
    # Temporary handling, currently only processes claude-3.7-sonnet
    if model_name == "claude-3.7-sonnet":
        return "claude-3-7-sonnet"
    if model_name == "gemini-2.5-pro":
        return "Gemini-2.5-pro"
    return model_name