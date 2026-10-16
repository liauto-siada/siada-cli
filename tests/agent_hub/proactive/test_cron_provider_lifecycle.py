"""Cron runs must release their own model clients before closing the event loop."""

import asyncio
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from agents import ModelSettings
from openai import AsyncOpenAI

from siada.agent_hub.proactive.cron_task_storage import CronTaskStorage
from siada.agent_hub.proactive.models import CronTask
from siada.agent_hub.proactive.scheduler import ProactiveScheduler
from siada.config.config_loader import ProactiveConfig
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.provider import provider_factory


@pytest.fixture
def cron_log(caplog):
    logger = logging.getLogger("siada.agent_hub.proactive.scheduler")
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


@pytest.fixture
def cron_run(tmp_path, monkeypatch: pytest.MonkeyPatch):
    storage = CronTaskStorage(str(tmp_path / "cron_tasks.json"))
    task = CronTask.create(
        name="Synthetic daily report", cron_expr="0 9 * * *", instruction="Run report"
    )
    storage.add(task)
    scheduler = ProactiveScheduler(
        config=ProactiveConfig(enabled=False),
        cron_storage=storage,
        signal_file=tmp_path / "cron_tasks.reload",
        workspace=str(tmp_path),
    )
    monkeypatch.setattr(
        scheduler,
        "_resolve_cron_model",
        lambda: SimpleNamespace(provider="synthetic", model_name="test-model"),
    )
    monkeypatch.setattr(
        ModelSettingsConverter, "convert_model_settings", lambda config: ModelSettings()
    )
    return scheduler, task, storage


@pytest.fixture
def tracked_providers(monkeypatch: pytest.MonkeyPatch):
    instances = []

    class Provider:
        def __init__(self) -> None:
            self.close_loops = []
            self.aclose = AsyncMock(side_effect=self._close)
            instances.append(self)

        async def _close(self) -> None:
            self.close_loops.append(asyncio.get_running_loop())

    shared = Provider()
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {"synthetic": shared})
    return shared, instances


@pytest.mark.parametrize("failure", [None, RuntimeError("model failed")])
def test_cron_closes_only_owned_provider_on_the_request_loop(
    cron_run, tracked_providers, monkeypatch: pytest.MonkeyPatch, failure
) -> None:
    scheduler, task, storage = cron_run
    shared, instances = tracked_providers
    request_loops = []
    used_providers = []

    async def run_agent(agent_name, instruction, run_config):
        request_loops.append(asyncio.get_running_loop())
        used_providers.append(run_config.model_provider.base_provider)
        assert agent_name == "coder"
        assert instruction == task.instruction
        assert run_config.model == "test-model"
        if failure is not None:
            raise failure

    monkeypatch.setattr(scheduler, "_run_agent", run_agent)
    scheduler._run_async(scheduler._run_cron_task(task.id, task.instruction))

    assert len(instances) == 2
    owned = instances[1]
    assert used_providers == [owned]
    owned.aclose.assert_awaited_once()
    assert owned.close_loops == request_loops
    assert request_loops[0].is_closed()
    shared.aclose.assert_not_called()
    assert storage.get(task.id).last_run is not None


def test_cron_cancellation_still_closes_owned_provider(
    cron_run, tracked_providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduler, task, storage = cron_run
    shared, instances = tracked_providers
    request_loops = []
    started = asyncio.Event()

    async def run_agent(*args):
        request_loops.append(asyncio.get_running_loop())
        started.set()
        await asyncio.Event().wait()

    async def cancel_run():
        run = asyncio.create_task(scheduler._run_cron_task(task.id, task.instruction))
        await started.wait()
        run.cancel()
        await run

    monkeypatch.setattr(scheduler, "_run_agent", run_agent)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancel_run())

    assert len(instances) == 2
    owned = instances[1]
    owned.aclose.assert_awaited_once()
    assert owned.close_loops == request_loops
    shared.aclose.assert_not_called()
    assert storage.get(task.id).last_run is not None


def test_cron_cleanup_failure_is_logged_and_timestamps_are_updated(
    cron_run, tracked_providers, monkeypatch: pytest.MonkeyPatch, cron_log
) -> None:
    scheduler, task, storage = cron_run
    shared, instances = tracked_providers

    async def run_agent(agent_name, instruction, run_config):
        run_config.model_provider.base_provider.aclose.side_effect = RuntimeError(
            "client cleanup failed"
        )

    monkeypatch.setattr(scheduler, "_run_agent", run_agent)
    with cron_log.at_level(logging.ERROR, logger="siada.agent_hub.proactive.scheduler"):
        asyncio.run(scheduler._run_cron_task(task.id, task.instruction))

    assert len(instances) == 2
    instances[1].aclose.assert_awaited_once()
    assert "client cleanup failed" in cron_log.text
    shared.aclose.assert_not_called()
    assert storage.get(task.id).last_run is not None


def test_cron_closes_provider_if_run_config_setup_fails(
    cron_run, tracked_providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from siada.services import model_wrapper

    scheduler, task, storage = cron_run
    shared, instances = tracked_providers

    def fail_setup(**kwargs):
        raise RuntimeError("wrapper setup failed")

    monkeypatch.setattr(model_wrapper, "ModelProviderWrapper", fail_setup)
    scheduler._run_agent = AsyncMock()
    asyncio.run(scheduler._run_cron_task(task.id, task.instruction))

    assert len(instances) == 2
    instances[1].aclose.assert_awaited_once()
    scheduler._run_agent.assert_not_called()
    shared.aclose.assert_not_called()
    assert storage.get(task.id).last_run is not None


def test_cron_supports_providers_without_async_cleanup(
    cron_run, monkeypatch: pytest.MonkeyPatch, cron_log
) -> None:
    scheduler, task, storage = cron_run

    class Provider:
        pass

    shared = Provider()
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {"synthetic": shared})
    scheduler._run_agent = AsyncMock()
    with cron_log.at_level(logging.ERROR, logger="siada.agent_hub.proactive.scheduler"):
        asyncio.run(scheduler._run_cron_task(task.id, task.instruction))

    scheduler._run_agent.assert_awaited_once()
    owned = scheduler._run_agent.call_args.args[2].model_provider.base_provider
    assert owned is not shared
    assert not [record for record in cron_log.records if record.levelno >= logging.ERROR]
    assert storage.get(task.id).last_run is not None


@pytest.fixture
def completion_server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.dumps(
                {
                    "id": "chatcmpl-synthetic",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "test-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("child_provider", ["synthetic", "override"])
def test_cron_descendants_and_helpers_use_the_owning_pool(
    cron_run, tracked_providers, monkeypatch, child_provider
):
    from siada.services import sub_agent_run_config
    from siada.tools.agent.subagent_async import register_background_subtask

    scheduler, task, storage = cron_run
    shared, instances = tracked_providers
    monkeypatch.setattr(
        provider_factory, "provider_map", {"synthetic": shared, "override": shared}
    )
    child_llm = SimpleNamespace(provider=child_provider, model_name="child-model")
    monkeypatch.setattr(
        sub_agent_run_config, "resolve_sub_agent_llm_config", lambda context: child_llm
    )
    events = []
    used = []

    async def run_agent(agent_name, instruction, run_config):
        root = run_config.model_provider.base_provider
        assert provider_factory.get_provider("synthetic") is root
        context = SimpleNamespace(
            session_id="synthetic-cron-descendant", provider=None, session=SimpleNamespace(
                siada_config=SimpleNamespace(tracing_disabled=True, llm_config=SimpleNamespace(provider=None))
            ),
        )
        child_config = sub_agent_run_config.build_sub_agent_run_config(context)
        child = child_config.model_provider.base_provider
        assert child is provider_factory.get_provider(child_provider)
        assert (child is root) == (child_provider == "synthetic")
        used.extend({root, child})
        started = asyncio.Event()

        async def descendant():
            assert provider_factory.get_provider(child_provider) is child
            recursive = sub_agent_run_config.build_sub_agent_run_config(context)
            assert recursive.model_provider.base_provider is child
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                assert all(provider.aclose.await_count == 0 for provider in used)
                events.append("descendant drained")

        register_background_subtask(context, descendant)
        await started.wait()

    monkeypatch.setattr(scheduler, "_run_agent", run_agent)
    scheduler._run_async(scheduler._run_cron_task(task.id, task.instruction))
    assert events == ["descendant drained"]
    for provider in used:
        provider.aclose.assert_awaited_once()
        assert provider.close_loops[0].is_closed()
    shared.aclose.assert_not_called()
    assert storage.get(task.id).last_run is not None


def test_consecutive_cron_runs_use_fresh_native_chat_clients(
    cron_run, completion_server, monkeypatch: pytest.MonkeyPatch, cron_log
) -> None:
    from siada.provider.default import chat_completions as default_chat
    from siada.provider.default.default_provider import DefaultProvider

    scheduler, task, storage = cron_run
    clients = []
    instances = []
    responses = []
    request_loops = []

    def create_client(**kwargs):
        client = AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(
                trust_env=False, limits=httpx.Limits(keepalive_expiry=0.01)
            ),
        )
        clients.append(client)
        return client

    monkeypatch.setattr(default_chat, "AsyncOpenAI", create_client)
    monkeypatch.setenv("BASE_URL", completion_server)
    monkeypatch.setenv("API_KEY", "synthetic-key")

    shared = DefaultProvider()
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {"synthetic": shared})
    create_provider = provider_factory.create_provider

    def create_owned_provider(provider_key):
        provider = create_provider(provider_key)
        instances.append(provider)
        return provider

    monkeypatch.setattr(provider_factory, "create_provider", create_owned_provider)

    async def run_agent(agent_name, instruction, run_config):
        request_loops.append(asyncio.get_running_loop())
        model = run_config.model_provider.base_provider.get_model("gpt-4o")
        assert isinstance(model, default_chat.DefaultOpenAIChatCompletionsModel)
        factory = model._client_factory
        client = factory.get_client()
        assert factory.get_client() is client
        response = await client.chat.completions.create(
            model="test-model", messages=[{"role": "user", "content": "synthetic"}]
        )
        responses.append(response.choices[0].message.content)

    async def use_shared_client():
        model = shared.get_model("gpt-4o")
        client = model._client_factory.get_client()
        response = await client.chat.completions.create(
            model="test-model", messages=[{"role": "user", "content": "synthetic"}]
        )
        assert response.choices[0].message.content == "ok"
        return client

    monkeypatch.setattr(scheduler, "_run_agent", run_agent)
    with asyncio.Runner() as shared_runner:
        try:
            shared_client = shared_runner.run(use_shared_client())
            scheduler._run_async(scheduler._run_cron_task(task.id, task.instruction))
            # Expire old connections to exercise the original cross-loop cleanup failure.
            time.sleep(0.05)
            scheduler._run_async(scheduler._run_cron_task(task.id, task.instruction))

            assert responses == ["ok", "ok"]
            assert len(instances) == 2
            assert len(clients) == 3
            assert clients[1] is not clients[2]
            assert all(client.is_closed() for client in clients[1:])
            assert request_loops[0] is not request_loops[1]
            assert all(loop.is_closed() for loop in request_loops)
            assert not shared_client.is_closed()
            assert shared_runner.run(use_shared_client()) is shared_client
            assert not [
                record for record in cron_log.records if record.levelno >= logging.ERROR
            ]
            assert storage.get(task.id).last_run is not None
        finally:
            shared_runner.run(shared.aclose())
            for provider in instances:
                asyncio.run(provider.aclose())
