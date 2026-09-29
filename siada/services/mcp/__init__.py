"""MCP OAuth lazy import requests/lark_oauth）"""

_OAUTH_EXPORTS = {
    'LarkOAuthManager': '.oauth',
    'LarkOAuthService': '.oauth',
    'LARK_AUTH_EXPIRED_ERROR_MESSAGE': '.oauth',
    'LARK_AUTH_EXPIRED_SUGGESTION': '.oauth',
}


def __getattr__(name):
    if name in _OAUTH_EXPORTS:
        from . import oauth
        return getattr(oauth, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_OAUTH_EXPORTS)
