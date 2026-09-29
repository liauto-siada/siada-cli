def get_username() -> str | None:
    """Get the username from ~/.siada-cli/conf.yaml.

    Reads the user_id field and returns the part before the '@' symbol.
    Returns None if the file doesn't exist or user_id is not configured.
    """
    from siada.config.conf_store import get_conf_value

    user_id = get_conf_value("user_id")
    if not user_id or not isinstance(user_id, str):
        return None
    return user_id.split("@")[0]
