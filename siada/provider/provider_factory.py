import os
import importlib
import inspect
import asyncio
import logging
import threading
import weakref
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator, Awaitable, Dict, Iterable, Optional, TypeVar

if TYPE_CHECKING:
    from agents import ModelProvider

PROVIDER_DIR = os.path.dirname(__file__)
provider_map: Dict = {}
_providers_discovered = False
_provider_lock = threading.RLock()
_loop_pools: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, "ProviderPool"] = weakref.WeakKeyDictionary()
_Result = TypeVar("_Result")
logger = logging.getLogger(__name__)


def resolve_provider_by_model(model_name: Optional[str], default_provider: Optional[str] = None) -> Optional[str]:
    """
    Resolve the provider name for a given model.

    Protocol routing (e.g. GPT-5.x models going through the native OpenAI
    Responses API) is handled inside each provider itself. This hook remains
    for provider-level overrides; currently no special rules apply and
    ``default_provider`` is always returned.

    Args:
        model_name: The name of the model (e.g. ``"gpt-5.4"``, ``"claude-sonnet-4.6"``).
        default_provider: The provider the caller would otherwise use.

    Returns:
        ``default_provider`` unchanged.
    """
    return default_provider

def _discover_providers():
    with _provider_lock:
        _discover_providers_locked()


def _discover_providers_locked():
    """
    Dynamically discovers and registers all ModelProvider implementations.
    Lazy: called on first get_provider() invocation so that importing this module
    does NOT trigger the heavy `from agents import ModelProvider` cold import.
    """
    global _providers_discovered
    if _providers_discovered:
        return
    _providers_discovered = True
    from agents import ModelProvider  # heavy import — deferred until first get_provider() call
    for item in os.listdir(PROVIDER_DIR):
        item_path = os.path.join(PROVIDER_DIR, item)
        if os.path.isdir(item_path):
            provider_key = item
            for file_name in os.listdir(item_path):
                if file_name.endswith("_provider.py"):
                    module_name = f"siada.provider.{provider_key}.{file_name[:-3]}"
                    try:
                        module = importlib.import_module(module_name)
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if inspect.isclass(attr) and issubclass(attr, ModelProvider) and attr is not ModelProvider:
                                provider_map[provider_key] = attr()
                    except ImportError as e:
                        logger.warning("Error importing provider module %s: %s", module_name, e)

# The provider keys are determined dynamically, so we use `str` for type hinting.
provider_type = str


def get_provider(p_type: provider_type | None = None):
    """
    Retrieves the model provider instance based on the provider name.

    Async callers resolve through their running loop's pool. Root runtimes
    own its shutdown; agents and tools only borrow providers from that pool.

    Args:
        p_type (provider_type | None): The name of the provider, e.g., 'default'.
                                           If None, defaults to the first available provider.

    Returns:
        ModelProvider: The corresponding model provider instance.

    Raises:
        ValueError: If the provider name is not supported.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # Synchronous configuration retains the legacy registry interface.
        return _registered_provider(p_type)[1]
    return _get_loop_pool().get_provider(p_type)


def _registered_provider(p_type: provider_type | None) -> tuple[str, "ModelProvider"]:
    _discover_providers()
    if not provider_map:
        raise ValueError("No model providers found or registered.")
    if p_type is None:
        p_type = next(iter(provider_map))
    if p_type not in provider_map:
        available = ", ".join(sorted(provider_map))
        raise ValueError(
            f"Unsupported model provider '{p_type}'. Available providers: {available}."
        )
    return p_type, provider_map[p_type]


def create_provider(p_type: provider_type) -> "ModelProvider":
    """Create a provider owned by a caller with its own event-loop lifetime.

    Discovery requires no-argument construction. This bypasses the loop pool;
    ordinary agents and helpers should use get_provider instead. The caller
    must close the returned provider on its owning loop.
    """
    return type(_registered_provider(p_type)[1])()


class ProviderPool:
    """Share providers on one event loop, never across runtime loops."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = weakref.ref(loop)
        self._providers: dict[str, "ModelProvider"] = {}
        self._closing = False
        self._closed = False
        self._runtime_active = False

    def _check_loop(self) -> None:
        if asyncio.get_running_loop() is not self._loop():
            raise RuntimeError("Provider pool belongs to a different event loop")

    def get_provider(self, p_type: provider_type | None = None) -> "ModelProvider":
        self._check_loop()
        if self._closing:
            raise RuntimeError("Provider runtime is shutting down")
        key, _ = _registered_provider(p_type)
        if key not in self._providers:
            self._providers[key] = create_provider(key)
        return self._providers[key]

    def stop_admission(self) -> None:
        self._check_loop()
        self._closing = True

    async def aclose(self) -> None:
        self._check_loop()
        if self._closed:
            return
        self.stop_admission()
        try:
            await _close_provider_instances(tuple(self._providers.values()))
        finally:
            self._providers.clear()
            self._closed = True


def _get_loop_pool() -> ProviderPool:
    loop = asyncio.get_running_loop()
    with _provider_lock:
        pool = _loop_pools.get(loop)
        if pool is None:
            pool = ProviderPool(loop)
            _loop_pools[loop] = pool
        return pool


async def aclose_providers() -> None:
    """Close this loop's providers after the caller has drained its tasks.

    Legacy synchronous registry users retain explicit cleanup support. Runtime
    entry points use shutdown_provider_runtime or provider_runtime instead.
    """
    with _provider_lock:
        pool = _loop_pools.get(asyncio.get_running_loop())
    if pool is not None:
        await pool.aclose()
        return
    if not _providers_discovered:
        return
    await _close_provider_instances(tuple(provider_map.values()))


async def _close_provider_instances(providers: Iterable["ModelProvider"]) -> None:
    errors: list[Exception] = []
    for provider in providers:
        close = getattr(provider, "aclose", None)
        if callable(close):
            try:
                await close()
            except Exception as exc:
                errors.append(exc)

    if len(errors) == 1:
        raise errors[0]
    if errors:
        raise ExceptionGroup("Failed to close one or more model providers", errors)


async def _cancel_runtime_tasks(excluded: set[asyncio.Task]) -> None:
    """Drain tasks, including tasks spawned by cancellation finalizers."""
    current = asyncio.current_task()
    while pending := asyncio.all_tasks() - excluded - {current}:
        for task in pending:
            task.cancel()
        results = await asyncio.gather(*pending, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.error(
                    "Runtime task failed during shutdown",
                    exc_info=(type(result), result, result.__traceback__),
                )


@asynccontextmanager
async def provider_runtime() -> AsyncIterator[ProviderPool]:
    """Own a runtime on this loop; nested helpers borrow the outer owner.

    This is an entry-point boundary, not a per-agent or per-request context.
    Tasks already present at entry belong to the embedding caller and are not
    cancelled. Explicit loop finalizers use shutdown_provider_runtime instead.
    """
    pool = _get_loop_pool()
    if pool._closing:
        raise RuntimeError("Provider runtime is shutting down")
    if pool._runtime_active:
        yield pool
        return
    pool._runtime_active = True
    existing_tasks = asyncio.all_tasks()
    try:
        yield pool
    finally:
        pool.stop_admission()
        try:
            await _cancel_runtime_tasks(existing_tasks)
        finally:
            await pool.aclose()


async def run_in_provider_runtime(coro: Awaitable[_Result]) -> _Result:
    """Own an ephemeral loop; pass this wrapper directly to asyncio.run.

    Unlike the embedding context manager, this owns every task and async
    generator on the loop. Do not use it around individual model requests.
    """
    pool = _get_loop_pool()
    pool._runtime_active = True
    try:
        return await coro
    finally:
        await shutdown_provider_runtime()


async def shutdown_provider_runtime() -> None:
    """Finalize a dedicated loop: stop admission, drain tasks, close providers."""
    pool = _get_loop_pool()
    pool.stop_admission()
    try:
        await _cancel_runtime_tasks(set())
        # Abandoned stream generators may outlive their consumer tasks.
        await asyncio.get_running_loop().shutdown_asyncgens()
        await _cancel_runtime_tasks(set())
    finally:
        await pool.aclose()


def stop_provider_admission() -> None:
    """Prevent model helpers from admitting work during entry-point teardown."""
    _get_loop_pool().stop_admission()
