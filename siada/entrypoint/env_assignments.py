"""Parse CLI environment assignments without initializing application runtimes."""


def parse_env_assignments(args: object | None) -> dict[str, str]:
    """Validate all assignments without exposing their values or changing the environment."""
    overrides: dict[str, str] = {}
    for setting in getattr(args, "set_env", None) or []:
        if not isinstance(setting, str):
            raise ValueError("Invalid --set-env format. Use ENV_VAR_NAME=value.")
        name, separator, value = setting.partition("=")
        if not separator or not name.strip() or "\0" in setting:
            raise ValueError("Invalid --set-env format. Use ENV_VAR_NAME=value.")
        overrides[name.strip()] = value.strip()
    return overrides