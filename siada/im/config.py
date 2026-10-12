"""IM configuration loader.

Thin wrapper that delegates to the unified config_loader.
All lark IM config is loaded from ~/.siada-cli/conf.yaml via load_conf().
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("siada.im.config")


def load_im_config(config_path: Optional[Path] = None) -> Optional[dict]:
    """Load lark IM configuration from conf.yaml.

    Delegates to config_loader.load_conf() for unified config loading.
    Environment references are resolved by the shared loader. Missing mode
    defaults to direct mode in the controller; legacy relay values remain
    readable so the controller can report an actionable unsupported-mode error.

    Args:
        config_path: Path to conf.yaml. Defaults to ~/.siada-cli/conf.yaml.

    Returns:
        Parsed config dict with structure ``{"lark": {...}}``,
        or None if no valid lark config is found.
    """
    from siada.config.config_loader import load_conf

    conf = load_conf(config_path=config_path)
    return conf.lark_config
