"""Public API compatibility for modules that no longer delegate to private code.

These modules used to forward to a private package whenever it was importable.
These tests pin the public contract instead: the modules stay importable and
usable on their own, unsupported features fail with an explicit message, and
nothing here references the private package.
"""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from siada.config.config_loader import AutoUpdateConfig
from siada.foundation.telemetry import Telemetry, telemetry
from siada.services import auto_update
from siada.tools import web as web_tools

REPO_ROOT = Path(__file__).resolve().parents[2]

PRIVATE_PACKAGE = "siada.internal"

# Module -> source file of every public path covered by this contract.
PUBLIC_MODULES = {
    "siada.foundation.telemetry": "siada/foundation/telemetry.py",
    "siada.session.session_manager": "siada/session/session_manager.py",
    "siada.im.transport.relay": "siada/im/transport/relay.py",
    "siada.entrypoint.interaction.lark_controller": (
        "siada/entrypoint/interaction/lark_controller.py"
    ),
    "siada.services.auto_update": "siada/services/auto_update.py",
    "siada.services.version_checker": "siada/services/version_checker/__init__.py",
    "siada.services.version_checker.base": "siada/services/version_checker/base.py",
    "siada.services.version_checker.version_checker": (
        "siada/services/version_checker/version_checker.py"
    ),
    "siada.services.version_checker.handlers.external_handler": (
        "siada/services/version_checker/handlers/external_handler.py"
    ),
    "siada.tools.web": "siada/tools/web/__init__.py",
    "siada.provider.default.kimi_tool_ordering": (
        "siada/provider/default/kimi_tool_ordering.py"
    ),
    "siada.agent_hub.context_filter.compaction_strategy": (
        "siada/agent_hub/context_filter/compaction_strategy.py"
    ),
    "siada.agent_hub.context_filter.utils": "siada/agent_hub/context_filter/utils.py",
}


def _private_modules_loaded() -> set[str]:
    return {
        name
        for name in sys.modules
        if name == PRIVATE_PACKAGE or name.startswith(f"{PRIVATE_PACKAGE}.")
    }


def test_public_sources_do_not_reference_private_package() -> None:
    offenders = []
    for relative_path in PUBLIC_MODULES.values():
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        if PRIVATE_PACKAGE in text or PRIVATE_PACKAGE.replace(".", "/") in text:
            offenders.append(relative_path)
    assert offenders == []


def test_public_modules_import_without_loading_private_package() -> None:
    before = _private_modules_loaded()

    for module_name in PUBLIC_MODULES:
        importlib.import_module(module_name)

    assert _private_modules_loaded() - before == set()


# ---------------------------------------------------------------------------
# Telemetry: pure no-op that preserves the used surface
# ---------------------------------------------------------------------------


def test_telemetry_singleton_exposes_inert_configuration() -> None:
    assert telemetry.config.url == ""
    assert telemetry.config.conversation_url == ""
    assert telemetry.config.user_id is None
    assert telemetry.device_id == ""
    assert telemetry.mac_id == ""


@pytest.mark.parametrize(
    "method_name",
    [
        "captureConversation",
        "captureConversationEvent",
        "captureApiTokenUsage",
        "captureToolEditFileUsage",
    ],
)
def test_telemetry_capture_methods_are_no_ops(method_name: str) -> None:
    method = getattr(telemetry, method_name)

    assert method(task_id="session-1", model="test-model", chat_mode="act") is None


def test_telemetry_instances_are_independent_no_ops() -> None:
    fresh = Telemetry()

    fresh.config.user_id = "user-1"

    assert fresh.config.user_id == "user-1"
    assert telemetry.config.user_id is None
    assert fresh.captureConversation(task_id="session-2") is None


def test_public_sessions_do_not_register_conversation_collection() -> None:
    from siada.session.session_manager import RunningSessionManager

    class UnreadableSession:
        def __getattribute__(self, name):
            raise AssertionError(f"conversation collection accessed {name}")

    assert RunningSessionManager._create_telemetry_hook(
        UnreadableSession(), SimpleNamespace()
    ) is None


# ---------------------------------------------------------------------------
# Relay transport: unavailable, but with an actionable error
# ---------------------------------------------------------------------------


def test_relay_transport_reports_unavailable() -> None:
    relay = importlib.import_module("siada.im.transport.relay")

    assert relay.RELAY_AVAILABLE is False


@pytest.mark.parametrize("name", ["RelayTransport", "LarkCredentials"])
def test_relay_legacy_names_raise_useful_import_error(name: str) -> None:
    relay = importlib.import_module("siada.im.transport.relay")

    with pytest.raises(ImportError) as excinfo:
        getattr(relay, name)

    message = str(excinfo.value)
    assert "unavailable" in message
    assert "direct" in message


def test_relay_legacy_import_statement_raises_useful_import_error() -> None:
    with pytest.raises(ImportError, match="direct mode"):
        from siada.im.transport.relay import RelayTransport  # noqa: F401


def test_relay_module_still_rejects_unknown_attributes() -> None:
    relay = importlib.import_module("siada.im.transport.relay")

    with pytest.raises(AttributeError):
        relay.NotARelayName


# ---------------------------------------------------------------------------
# Lark controller: direct mode works, relay mode fails explicitly
# ---------------------------------------------------------------------------


def _patch_lark_config(monkeypatch, lark_config) -> None:
    monkeypatch.setattr("siada.im.config.load_im_config", lambda config_path=None: lark_config)


def test_lark_relay_mode_reports_unsupported(monkeypatch) -> None:
    import siada.entrypoint.interaction.lark_controller as lark_controller

    _patch_lark_config(monkeypatch, {"lark": {"enabled": True, "mode": "relay"}})

    with pytest.raises(RuntimeError) as excinfo:
        lark_controller.create_if_configured()

    message = str(excinfo.value)
    assert "relay mode is not supported" in message
    assert "'direct'" in message


@pytest.mark.parametrize("mode", ["direct", None])
def test_lark_direct_mode_returns_direct_controller(monkeypatch, mode) -> None:
    import siada.entrypoint.interaction.lark_controller as lark_controller

    lark_config = {
        "lark": {
            "enabled": True,
            "direct": {"app_id": "cli_test_app", "app_secret": "test-secret"},
        }
    }
    if mode is not None:
        lark_config["lark"]["mode"] = mode
    _patch_lark_config(monkeypatch, lark_config)
    recorded = {}

    def _recording_init(self, config):
        recorded["config"] = config

    monkeypatch.setattr(lark_controller.LarkController, "__init__", _recording_init)

    controller = lark_controller.create_if_configured()

    assert isinstance(controller, lark_controller.LarkController)
    assert recorded["config"] == lark_config


def test_lark_without_config_returns_no_controller(monkeypatch) -> None:
    import siada.entrypoint.interaction.lark_controller as lark_controller

    _patch_lark_config(monkeypatch, None)

    assert lark_controller.create_if_configured() is None


def test_lark_direct_mode_requires_credentials(monkeypatch) -> None:
    import siada.entrypoint.interaction.lark_controller as lark_controller

    _patch_lark_config(monkeypatch, {"lark": {"enabled": True, "mode": "direct"}})

    with pytest.raises(RuntimeError, match="app_id"):
        lark_controller.create_if_configured()


def test_lark_disabled_returns_no_controller(monkeypatch) -> None:
    import siada.entrypoint.interaction.lark_controller as lark_controller

    _patch_lark_config(monkeypatch, {"lark": {"enabled": False, "mode": "direct"}})

    assert lark_controller.create_if_configured() is None


def test_lark_unknown_mode_is_rejected(monkeypatch) -> None:
    import siada.entrypoint.interaction.lark_controller as lark_controller

    _patch_lark_config(monkeypatch, {"lark": {"enabled": True, "mode": "carrier-pigeon"}})

    with pytest.raises(RuntimeError, match="Invalid lark mode"):
        lark_controller.create_if_configured()


# ---------------------------------------------------------------------------
# Auto update: public install-mode classification and PyPI strategy only
# ---------------------------------------------------------------------------


def test_detect_install_mode_defaults_to_external(monkeypatch) -> None:
    monkeypatch.delenv("SIADA_AUTO_UPDATE_MODE", raising=False)
    monkeypatch.delenv("SIADA_UPDATE_SOURCE", raising=False)
    monkeypatch.setattr(auto_update.sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(auto_update.sys, "prefix", "/usr")
    monkeypatch.setattr(auto_update.siada, "__file__", "/usr/lib/python3/siada/__init__.py")

    assert auto_update.detect_install_mode() == "external"


@pytest.mark.parametrize("env_var", ["SIADA_AUTO_UPDATE_MODE", "SIADA_UPDATE_SOURCE"])
def test_detect_install_mode_honours_forced_mode(monkeypatch, env_var: str) -> None:
    monkeypatch.delenv("SIADA_AUTO_UPDATE_MODE", raising=False)
    monkeypatch.delenv("SIADA_UPDATE_SOURCE", raising=False)
    monkeypatch.setenv(env_var, "internal")

    assert auto_update.detect_install_mode() == "internal"


def test_build_update_strategy_stays_on_public_pypi_strategy(monkeypatch) -> None:
    monkeypatch.setenv("SIADA_AUTO_UPDATE_MODE", "internal")

    assert auto_update.detect_install_mode() == "internal"

    strategy = auto_update.build_update_strategy("beta")

    assert isinstance(strategy, auto_update.ExternalUpdateStrategy)
    assert strategy.channel == "beta"


def test_external_strategy_reads_public_release_metadata(monkeypatch) -> None:
    requested = []
    response = SimpleNamespace(
        json=lambda: {"info": {"version": "9.9.9"}},
        raise_for_status=lambda: None,
    )

    def _fake_get(url, timeout=None):
        requested.append((url, timeout))
        return response

    monkeypatch.setattr(auto_update.requests, "get", _fake_get)

    release = auto_update.get_latest_release_info(AutoUpdateConfig(channel="prod"))

    assert [url for url, _ in requested] == ["https://pypi.org/pypi/siada-cli/json"]
    assert release.version == "9.9.9"
    assert release.version_source == "https://pypi.org/pypi/siada-cli/json"
    assert release.install_mode == "external"
    assert release.channel == "prod"


def test_external_strategy_upgrade_hint_uses_pip() -> None:
    hint = auto_update.ExternalUpdateStrategy().get_manual_upgrade_hint()

    assert "pip" in hint
    assert "siada-cli" in hint


# ---------------------------------------------------------------------------
# Version checking: shared VersionHandler contract plus PyPI releases
# ---------------------------------------------------------------------------


def _release(version: str, source: str = "pypi"):
    return SimpleNamespace(
        version=version,
        version_source=source,
        install_mode="external",
        channel="prod",
    )


def test_module_level_version_checker_exposes_public_api() -> None:
    version_checker_module = importlib.import_module("siada.services.version_checker")
    handler_module = importlib.import_module("siada.services.version_checker.base")

    for name in (
        "VersionChecker",
        "version_checker",
        "get_latest_version",
        "install_upgrade",
        "check_version",
    ):
        assert hasattr(version_checker_module, name)

    handler = version_checker_module.version_checker.handler
    assert handler is None or isinstance(handler, handler_module.VersionHandler)


def test_version_handler_contract_is_inert_but_usable() -> None:
    handler_module = importlib.import_module("siada.services.version_checker.base")
    handler = handler_module.VersionHandler()

    assert handler.get_version() is None
    assert handler.install(io=None) is None
    assert handler.get_manual_upgrade_hint() == "siada-cli --upgrade"
    assert "1.2.3" in handler.get_install_message("1.2.3")


def test_external_handler_reads_pypi_without_private_support(monkeypatch) -> None:
    handler_module = importlib.import_module(
        "siada.services.version_checker.handlers.external_handler"
    )
    handler = handler_module.VersionHandler()
    monkeypatch.setattr(
        requests, "get", lambda url, timeout=None: SimpleNamespace(json=lambda: {"info": {"version": "9.9.9"}})
    )

    assert handler.get_version() == ("9.9.9", "success")
    assert handler.pypi_url == "https://pypi.org/pypi/siada-cli/json"
    assert "siada-cli" in handler.get_manual_upgrade_hint()


def test_external_handler_reports_errors_instead_of_raising(monkeypatch) -> None:
    handler_module = importlib.import_module(
        "siada.services.version_checker.handlers.external_handler"
    )
    handler = handler_module.VersionHandler()

    def _boom(url, timeout=None):
        raise RuntimeError("offline")

    monkeypatch.setattr(requests, "get", _boom)

    version, status = handler.get_version()

    assert version is None
    assert status.startswith("error:")


def test_version_checker_uses_public_release_info(monkeypatch) -> None:
    checker_module = importlib.import_module(
        "siada.services.version_checker.version_checker"
    )
    monkeypatch.setattr(
        checker_module, "get_latest_release_info", lambda config: _release("9.9.9")
    )
    monkeypatch.setattr(
        checker_module, "get_runtime_auto_update_config", lambda: AutoUpdateConfig()
    )

    checker = checker_module.VersionChecker(handler=None)

    assert checker.get_latest_version() == ("9.9.9", "pypi")


def test_version_checker_falls_back_to_handler_without_release_info(monkeypatch) -> None:
    checker_module = importlib.import_module(
        "siada.services.version_checker.version_checker"
    )

    def _boom(config):
        raise RuntimeError("offline")

    handler = MagicMock()
    handler.get_version.return_value = ("1.2.3", "handler")
    monkeypatch.setattr(checker_module, "get_latest_release_info", _boom)
    monkeypatch.setattr(
        checker_module, "get_runtime_auto_update_config", lambda: AutoUpdateConfig()
    )

    checker = checker_module.VersionChecker(handler=handler)

    assert checker.get_latest_version() == ("1.2.3", "available")


def test_version_checker_reports_no_handler_without_release_info(monkeypatch) -> None:
    checker_module = importlib.import_module(
        "siada.services.version_checker.version_checker"
    )

    def _boom(config):
        raise RuntimeError("offline")

    monkeypatch.setattr(checker_module, "get_latest_release_info", _boom)
    monkeypatch.setattr(
        checker_module, "get_runtime_auto_update_config", lambda: AutoUpdateConfig()
    )

    checker = checker_module.VersionChecker(handler=None)

    assert checker.get_latest_version() == (None, "no_handler_available")


def test_check_version_writes_cache_under_tmp_path(tmp_path, monkeypatch) -> None:
    checker_module = importlib.import_module(
        "siada.services.version_checker.version_checker"
    )
    cache_file = tmp_path / "caches" / "versioncheck"
    monkeypatch.setattr(checker_module, "VERSION_CHECK_FNAME", cache_file)
    monkeypatch.setattr(
        checker_module, "get_latest_release_info", lambda config: _release("9.9.9")
    )
    monkeypatch.setattr(
        checker_module, "get_runtime_auto_update_config", lambda: AutoUpdateConfig()
    )
    io = MagicMock()

    result = checker_module.VersionChecker(handler=None).check_version(
        io, just_check=True, verbose=True
    )

    assert result is True
    assert cache_file.exists()
    io.print_info.assert_called_once()
    assert "9.9.9" in io.print_info.call_args.args[0]


def test_install_upgrade_uses_public_installer(tmp_path, monkeypatch) -> None:
    checker_module = importlib.import_module(
        "siada.services.version_checker.version_checker"
    )
    monkeypatch.setattr(
        checker_module, "get_runtime_auto_update_config", lambda: AutoUpdateConfig()
    )
    monkeypatch.setattr(
        checker_module,
        "install_latest_update",
        lambda config=None, force=False: (True, _release("9.9.9"), "Update installed"),
    )
    io = MagicMock()

    assert checker_module.VersionChecker(handler=None).install_upgrade(io, "9.9.9") is True

    io.print_info.assert_called_once()
    assert "9.9.9" in io.print_info.call_args.args[0]


# ---------------------------------------------------------------------------
# Web tools: only public implementations are published
# ---------------------------------------------------------------------------


def test_web_search_has_no_public_implementation() -> None:
    assert web_tools.web_search is None


def test_get_web_tools_publishes_only_public_implementations() -> None:
    tools = web_tools.get_web_tools()

    assert isinstance(tools, list)
    assert "web_search" not in {getattr(tool, "name", None) for tool in tools}
    if web_tools.web_fetch is None:
        assert tools == []
    else:
        assert tools == [web_tools.web_fetch]


def test_get_web_tools_stays_empty_without_public_implementation(monkeypatch) -> None:
    monkeypatch.setattr(web_tools, "web_fetch", None)

    assert web_tools.get_web_tools() == []


def test_resolve_web_tools_enabled_is_generic() -> None:
    assert web_tools.resolve_web_tools_enabled("any-provider", None) is True
    assert web_tools.resolve_web_tools_enabled("any-provider", True) is True
    assert web_tools.resolve_web_tools_enabled("any-provider", False) is False


def test_resolve_provider_from_context_prefers_context_provider() -> None:
    context = SimpleNamespace(provider="custom-provider")

    assert web_tools.resolve_provider_from_context(context) == "custom-provider"
    assert web_tools.resolve_provider_from_context(None) is None


def test_resolve_provider_from_context_falls_back_to_model_routing(monkeypatch) -> None:
    provider_factory = importlib.import_module("siada.provider.provider_factory")
    monkeypatch.setattr(
        provider_factory, "resolve_provider_by_model", lambda model, provider: "routed"
    )
    context = SimpleNamespace(
        provider=None,
        model_run_config=SimpleNamespace(provider="raw", model_name="some-model"),
    )

    assert web_tools.resolve_provider_from_context(context) == "routed"