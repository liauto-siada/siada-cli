import os
from pathlib import Path


def get_username() -> str | None:
    """Get the username from ~/.siada-cli/conf.yaml.

    Reads the user_id field and returns the part before the '@' symbol.
    Returns None if the file doesn't exist or user_id is not configured.
    """
    conf_path = Path(os.path.expanduser("~")) / ".siada-cli" / "conf.yaml"
    if not conf_path.exists():
        return None

    try:
        import yaml
        with open(conf_path, "r", encoding="utf-8") as f:
            conf = yaml.safe_load(f)
        user_id = conf.get("user_id") if conf else None
        if not user_id:
            return None
        return user_id.split("@")[0]
    except Exception:
        return None
