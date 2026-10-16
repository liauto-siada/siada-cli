"""Offline regression coverage for loop-local model provider ownership."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import pytest

from siada.provider import provider_factory


@pytest.fixture
def registered(monkeypatch):
    instances = []

    class Provider:
        def __init__(self):
            self.close_loop = None
            self.aclose = AsyncMock(side_effect=self.close)
            instances.append(self)

        async def close(self):
            self.close_loop = asyncio.get_running_loop()

    prototype = Provider()
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {"default": prototype, "other": prototype})
    return prototype, instances


def test_sequential_loops_share_with_children_but_not_each_other(registered):
    prototype, instances = registered

    async def run():
        async with provider_factory.provider_runtime():
            root = provider_factory.get_provider("default")

            async def child():
                await asyncio.sleep(0)
                return provider_factory.get_provider("default")

            assert all(p is root for p in await asyncio.gather(*(child() for _ in range(6))))
            other = provider_factory.get_provider("other")
            assert other is not root
            return root, other, asyncio.get_running_loop()

    first = asyncio.run(run())
    second = asyncio.run(run())
    assert first[0] is not second[0]
    assert first[1] is not second[1]
    for root, other, loop in (first, second):
        assert loop.is_closed()
        for provider in (root, other):
            provider.aclose.assert_awaited_once()
            assert provider.close_loop is loop
    assert len(instances) == 5
    prototype.aclose.assert_not_called()


def test_concurrent_controller_loops_are_isolated(registered):
    import threading

    barrier = threading.Barrier(2)

    async def run():
        async with provider_factory.provider_runtime():
            provider = provider_factory.get_provider("default")
            await asyncio.to_thread(barrier.wait, 3)
            assert provider_factory.get_provider("default") is provider
            return provider

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(asyncio.run, run()) for _ in range(2)]
        first, second = [future.result(timeout=5) for future in futures]
    assert first is not second
    first.aclose.assert_awaited_once()
    second.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_nested_runtime_does_not_close_siblings_or_providers(registered):
    async with provider_factory.provider_runtime():
        provider = provider_factory.get_provider("default")
        sibling = asyncio.create_task(asyncio.Event().wait())
        async with provider_factory.provider_runtime():
            assert provider_factory.get_provider("default") is provider
        assert not sibling.done()
        provider.aclose.assert_not_called()
    assert sibling.cancelled()
    provider.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_runtime_drains_children_before_close_and_stops_admission(registered, failure):
    events = []
    started = asyncio.Event()

    async def child():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            with pytest.raises(RuntimeError, match="shutting down"):
                provider_factory.get_provider("default")
            await asyncio.sleep(0)
            events.append("child drained")

    async def close():
        assert events == ["child drained"]
        events.append("provider closed")

    async def run():
        async with provider_factory.provider_runtime():
            provider = provider_factory.get_provider("default")
            provider.aclose.side_effect = close
            task = asyncio.create_task(child())
            await started.wait()
            if failure:
                raise ValueError("synthetic model failure")
        return task

    if failure:
        with pytest.raises(ValueError, match="synthetic model failure"):
            await run()
    else:
        assert (await run()).cancelled()
    assert events == ["child drained", "provider closed"]


@pytest.mark.asyncio
async def test_runtime_closes_all_providers_after_cleanup_failure(registered):
    with pytest.raises(OSError, match="synthetic close failure"):
        async with provider_factory.provider_runtime():
            first = provider_factory.get_provider("default")
            second = provider_factory.get_provider("other")
            first.aclose.side_effect = OSError("synthetic close failure")
    second.aclose.assert_awaited_once()
    with pytest.raises(RuntimeError, match="shutting down"):
        provider_factory.get_provider("default")
    await provider_factory.aclose_providers()


def test_dedicated_runtime_closes_abandoned_stream_before_provider(registered):
    events = []

    async def stream_cleanup_helper():
        try:
            await asyncio.Event().wait()
        finally:
            events.append("stream helper drained")

    async def stream():
        try:
            yield "synthetic chunk"
        finally:
            asyncio.create_task(stream_cleanup_helper())
            await asyncio.sleep(0)
            events.append("stream closed")

    async def start():
        provider = provider_factory.get_provider("default")

        async def close():
            assert events == ["stream closed", "stream helper drained"]
            events.append("provider closed")

        provider.aclose.side_effect = close
        generator = stream()
        assert await anext(generator) == "synthetic chunk"
        return generator

    with asyncio.Runner() as runner:
        generator = runner.run(start())
        runner.run(provider_factory.shutdown_provider_runtime())
    assert events == ["stream closed", "stream helper drained", "provider closed"]
    assert generator.ag_frame is None
