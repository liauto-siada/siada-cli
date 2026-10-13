"""Per-run SDK bridge for authoritative FileSession effective context.

Keep the same admission ID when retrying an interrupted logical run.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import uuid
from dataclasses import replace
from typing import Any

from agents import Agent, Model, RunConfig
from agents.memory.session import SessionABC
from agents.models.fake_id import FAKE_RESPONSES_ID

from siada.foundation.logging import logger
from siada.services.file_session import FileSession
from siada.services.session_storage import ContextVersionConflict, SessionStorageError
from siada.services.model_wrapper import ModelProviderWrapper, ModelWrapper


_REMINDER_QUEUES = (
    "pending_reminder_items", "pending_hallucination_reminder_items",
    "pending_repeated_tool_reminder_items",
)


def _native_item(item: dict) -> dict:
    """Ignore SDK display-only metadata for admission identity checks."""
    result = copy.deepcopy(item)
    result.pop("_agents_tool_description", None)
    result.pop("_agents_tool_title", None)
    return result


async def configure_effective_run(storage, config: RunConfig, *, agent: Agent):
    """Install the default bridge without guessing an old history-only boundary."""
    if not isinstance(storage, FileSession):
        logger.info(
            "[effective-context][run] session=%s mode=passthrough bridge=disabled storage=%s",
            getattr(storage, "session_id", None), type(storage).__name__,
        )
        return storage, config
    if not storage.has_prepared_context:
        history = await storage.get_history_items()
        await storage.migrate_legacy_context(allow_history_only=not history)
    bridge = EffectiveContextSession(storage)
    return bridge, bridge.configure_run(config, agent=agent)


class EffectiveContextSession(SessionABC):
    """Own one SDK run's admission scope without modifying provider payloads."""

    session_settings: Any = None

    def __init__(self, storage: FileSession, *, admission_id: str | None = None):
        self.storage = storage
        self.session_id = storage.session_id
        self.admission_id = admission_id if admission_id is not None else uuid.uuid4().hex
        if not isinstance(self.admission_id, str) or not self.admission_id:
            raise ValueError("Admission ID must be a nonempty string")
        self._input: list[dict] | None = None
        self._input_save_pending = False
        self._batch_index = 0
        self._request_input: list[dict] | None = None
        self._request_version: int | None = None
        self._request_context: Any = None
        self._pending_contexts: list[str] = []
        self._pending_finalization: tuple[list[dict], list[str]] | None = None
        self._pending_checkpoints: list[str] = []
        self._restore_generation: int | None = None
        self._response_index = 0

    @property
    def request_identity(self) -> str:
        return f"{self.admission_id}:request:{self._response_index}"

    def response_received(self) -> None:
        self._response_index += 1

    def _check_restore_generation(self, snapshot: dict) -> None:
        """Fence in-flight runs after restore without blocking normal compaction."""
        generation = snapshot.get("restore_generation", 0)
        if self._restore_generation is None:
            self._restore_generation = generation
        elif generation != self._restore_generation:
            raise ContextVersionConflict("Effective context was restored during the SDK run")

    async def get_items(self, limit: int | None = None) -> list[dict]:
        snapshot = await self.storage.get_context_snapshot()
        self._check_restore_generation(snapshot)
        return self.storage._limit_items(snapshot["items"], limit)

    async def session_input_callback(self, history: list, new_items: list) -> list:
        """Commit new input before the first request, retaining its run identity."""
        native = [_native_item(item) for item in new_items]
        if self._input is not None and self._input != native:
            raise SessionStorageError("An effective-context bridge cannot be reused for different input")
        await self.get_items()
        await self.storage.append_context_items(
            native, message_ids=[f"{self.admission_id}:input:{index}" for index in range(len(native))],
            expected_restore_generation=self._restore_generation,
        )
        self._input = native
        self._input_save_pending = bool(native)
        # Do not merge stale callback history after admission or a concurrent
        # compaction. The SDK still identifies the new-input persistence subset.
        return await self.get_items()

    async def add_items(self, items: list) -> None:
        """Accept SDK saves, suppressing only this run's already admitted input."""
        await self.get_items()
        native = [_native_item(item) for item in items]
        consumed_input = False
        if self._input_save_pending and self._input:
            prefix = native[:len(self._input)]
            if prefix == self._input:
                native = native[len(self._input):]
                consumed_input = True
            elif prefix and prefix[0] == self._input[0]:
                raise SessionStorageError("SDK input persistence does not match admitted input")
        identities = []
        for index, item in enumerate(native):
            item_type = item.get("type", item.get("role", "item"))
            stable_id = item.get("call_id") or item.get("id")
            if stable_id == FAKE_RESPONSES_ID:
                stable_id = None
            if stable_id:
                identities.append(f"{self.admission_id}:output:{item_type}:{stable_id}")
            else:
                identities.append(f"{self.admission_id}:batch:{self._batch_index}:{index}")
        await self.storage.append_context_items(
            native, message_ids=identities, expected_restore_generation=self._restore_generation,
        )
        if consumed_input:
            self._input_save_pending = False
        self._batch_index += 1
        completed = {item.get("call_id") for item in native if item.get("type") == "function_call_output"}
        ready = [call_id for call_id in self._pending_checkpoints if call_id in completed]
        if ready:
            context = self._request_context
            tracker = context.session.checkpoint_tracker if context is not None and context.session else None
            if tracker is not None:
                from siada.services.session_runtime_state import save_context

                await asyncio.to_thread(save_context, context)
                snapshot = await asyncio.to_thread(self.storage.get_checkpoint_snapshot_sync)
                self._check_restore_generation(snapshot["context_snapshot"])
                for call_id in ready:
                    await asyncio.to_thread(
                        tracker.save_checkpoints, self.session_id, None, context.session.state.usage,
                        file_snapshot=snapshot, tool_call_id=call_id,
                        structured_state=snapshot["runtime_state"],
                    )
            self._pending_checkpoints = [call_id for call_id in self._pending_checkpoints if call_id not in ready]

    def queue_checkpoint(self, call_id: str) -> None:
        """Defer capture until the SDK has committed the matching tool result."""
        if call_id not in self._pending_checkpoints:
            self._pending_checkpoints.append(call_id)

    async def pop_item(self) -> dict | None:
        raise SessionStorageError("Effective-context SDK rewind requires an explicit restore transaction")

    async def clear_session(self) -> None:
        raise SessionStorageError("Effective-context reset requires an explicit restore transaction")

    def capture_pending_contexts(self, pending: list[str]) -> None:
        """Capture the exact background-notice prefix injected by RunHooks."""
        self._pending_contexts = list(pending)

    def _clear_committed_queues(self, items: list[dict]) -> None:
        """Clear only captured notices; background tasks may have added more."""
        context = self._request_context
        if context is None:
            return
        pending = context.hook_pending_contexts
        count = len(self._pending_contexts)
        captured = [{"role": "system", "content": text} for text in self._pending_contexts]
        if pending[:count] == self._pending_contexts and all(item in items for item in captured):
            del pending[:count]
        for field in _REMINDER_QUEUES:
            queued = getattr(context, field)
            if queued and all(item in items for item in queued):
                queued.clear()

    async def finalize_request_input(self, items: list[dict]) -> None:
        """Durably admit additions from both SDK hook chains before network I/O.

        Provider normalization remains downstream. Storage errors propagate;
        notices and processor queues are retained for an explicit retry.
        """
        if self._request_input is None or self._request_version is None:
            raise SessionStorageError("Model request did not pass the authoritative input filter")
        native = [_native_item(item) for item in items]
        size = len(self._request_input)
        if native[:size] != self._request_input:
            raise SessionStorageError("Post-filter hooks may append input but cannot rewrite admitted context")
        tail = native[size:]
        if self._pending_finalization is not None and self._pending_finalization[0] == tail:
            identities = self._pending_finalization[1]
        else:
            identities = [f"{self.admission_id}:hook:{uuid.uuid4().hex}" for _ in tail]
        self._pending_finalization = (tail, identities)
        from siada.services.session_runtime_state import commit_request_state

        def commit():
            with self.storage._mutation():
                added = self.storage.append_context_items_sync(
                    tail, message_ids=identities, expected_version=self._request_version,
                    expected_restore_generation=self._restore_generation,
                )
                if self._request_context is not None and self._request_context.session is not None:
                    commit_request_state(self._request_context, self._pending_contexts,
                                         request_identity=self.request_identity)
                return added

        added = await asyncio.to_thread(commit)
        if added and self.storage.on_items_added:
            await self.storage.on_items_added(copy.deepcopy(added))
        self._clear_committed_queues(tail)
        self._request_version += bool(added)
        self._request_input = native
        self._pending_finalization = None

    def configure_run(self, config: RunConfig, *, agent: Agent | None = None) -> RunConfig:
        """Copy a run config and enforce authoritative reads around its filter.

        Custom provider/model settings are retained. A custom input callback or
        limited session read would obscure the SDK admission boundary and is
        rejected rather than guessed. The filter must not persist via legacy
        snapshot methods; prepared storage rejects those obsolete writes.
        """
        if config.session_input_callback is not None or config.session_settings is not None:
            raise ValueError("Effective context owns the session input callback and read settings")
        original_filter = config.call_model_input_filter
        from siada.agent_hub.context_filter.context_capture_filter import context_capture_filter
        from siada.agent_hub.context_filter.effective_context_filter import effective_context_filter

        if original_filter is None or original_filter is context_capture_filter:
            original_filter = effective_context_filter

        async def authoritative_filter(data):
            self._check_restore_generation(await self.storage.get_context_snapshot())
            if self._pending_finalization is not None:
                pending, identities = self._pending_finalization
                await self.storage.append_context_items(
                    pending, message_ids=identities, expected_restore_generation=self._restore_generation,
                )
                self._clear_committed_queues(pending)
                self._pending_finalization = None
            self._request_context = data.context
            if data.context is not None:
                data.context.runtime_session = self
                self._pending_contexts = []
                from siada.agent_hub.context_filter.pending_user_input_filter import PendingUserInputInjector

                async def persist_queued(items, identities):
                    await self.storage.append_context_items(
                        items, message_ids=identities, expected_restore_generation=self._restore_generation,
                    )

                queued_data = copy.deepcopy(data.model_data)
                queued_data.input = []
                await PendingUserInputInjector().filter(
                    queued_data, data.agent, data.context, persist_items=persist_queued,
                )
            snapshot = await self.storage.get_context_snapshot()
            self._check_restore_generation(snapshot)
            input_items = len(snapshot["items"])
            model_data = copy.deepcopy(data.model_data)
            model_data.input = snapshot["items"]
            if original_filter is not None:
                filtered = original_filter(replace(data, model_data=model_data))
                model_data = await filtered if inspect.isawaitable(filtered) else filtered
            version = await self.storage.replace_context_items(
                model_data.input, expected_version=snapshot["context_version"],
            )
            self._request_input = [_native_item(item) for item in model_data.input]
            self._request_version = version
            logger.info(
                "[effective-context][request] session=%s mode=prepared source=api_message.json "
                "admission_id=%s request_index=%d version_before=%d version=%d input_items=%d items=%d "
                "stage=filter_committed",
                self.session_id, self.admission_id, self._response_index,
                snapshot["context_version"], version, input_items, len(self._request_input),
            )
            return model_data

        selected_model = config.model if config.model is not None else getattr(agent, "model", None)
        model_provider = config.model_provider
        if isinstance(selected_model, Model):
            selected_model = ModelWrapper(selected_model, before_request=self.finalize_request_input)
        else:
            model_provider = ModelProviderWrapper(model_provider, before_request=self.finalize_request_input)
        configured = replace(
            config,
            model=selected_model,
            model_provider=model_provider,
            session_input_callback=self.session_input_callback,
            call_model_input_filter=authoritative_filter,
        )
        logger.info(
            "[effective-context][run] session=%s mode=prepared bridge=enabled filter=%s admission_id=%s",
            self.session_id, "default" if original_filter is effective_context_filter else "custom",
            self.admission_id,
        )
        return configured
