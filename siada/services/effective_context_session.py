"""Per-run SDK bridge for authoritative FileSession effective context.

Keep the same admission ID when retrying an interrupted logical run.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import uuid
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from agents import Agent, Model, RunConfig
from agents.memory.session import SessionABC
from agents.models.fake_id import FAKE_RESPONSES_ID

from siada.foundation.logging import logger
from siada.provider.token_counting import TokenCountingInfo, provider_token_counting_info, token_counting_info_from_model
from siada.services.file_session import FileSession
from siada.services.model_wrapper import ModelProviderWrapper, ModelWrapper
from siada.services.session_storage import ContextVersionConflict, SessionStorageError

if TYPE_CHECKING:
    from siada.agent_hub.context_filter.request_token_estimator import RequestTokenBaseline


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
        self._request_token_signature: str | None = None
        self._request_signature_components: dict[str, str] = {}
        self._request_agent: Any = None
        self._request_instructions: str | None = None
        self.token_counting_info: TokenCountingInfo | None = None
        self.token_budget_model_settings: Any = None
        self._pending_contexts: list[str] = []
        self._pending_finalization: tuple[list[dict], list[str]] | None = None
        self._request_commit_done: asyncio.Event | None = None
        self._pending_checkpoints: list[str] = []
        self._restore_generation: int | None = None
        self._response_index = 0
        self._pending_response: tuple[Any, RequestTokenBaseline | None, list[dict]] | None = None

    @property
    def request_identity(self) -> str:
        return f"{self.admission_id}:request:{self._response_index}"

    def token_baseline_from_response(self, response: Any) -> RequestTokenBaseline | None:
        """Stage server total usage; this is not yet a durable response anchor."""
        from siada.agent_hub.context_filter.request_token_estimator import RequestTokenBaseline

        if self._request_token_signature is None or self._request_input is None:
            return None
        return RequestTokenBaseline.from_response(
            self._request_token_signature, self._request_input, getattr(response, "usage", None),
            restore_generation=self._restore_generation or 0,
            session_id=self.session_id,
            signature_components=self._request_signature_components,
        )

    async def response_received(self, response: Any) -> None:
        """Stage response metadata after usage commits, before SDK message saves."""
        self._pending_response = (
            response, self.token_baseline_from_response(response),
            [_native_item(item) for item in response.to_input_items()],
        )
        logger.debug(
            "[CTX-BUILD][anchor] session=%s request=%s stage=response_staged "
            "candidate=%s response_items=%d",
            self.session_id, self.request_identity, self._pending_response[1] is not None,
            len(self._pending_response[2]),
        )
        self._response_index += 1
        # An empty response gives the SDK nothing to save. Its input is already
        # durable, so confirm that boundary while retaining reported total usage.
        if not self._pending_response[2]:
            await self.add_items([])

    def _durable_response_baseline(self, snapshot: dict) -> RequestTokenBaseline | None:
        """Use the actual persisted prefix, excluding tool results and later input."""
        _, baseline, expected_response = self._pending_response
        if baseline is None:
            return None
        size = len(baseline.items)
        items = snapshot["items"]
        if items[:size] != baseline.items:
            logger.info(
                "[CTX-BUILD][anchor] session=%s stage=discarded reason=request_prefix_changed",
                self.session_id,
            )
            return None
        response_items = items[size:size + len(expected_response)]

        def matching_item(item: dict) -> dict:
            item = _native_item(item)
            # The SDK may omit reasoning IDs on save. Keep every other field
            # intact, and anchor the stored IDs rather than the hook's copy.
            if item.get("type") == "reasoning":
                item.pop("id", None)
            return item

        if [matching_item(item) for item in response_items] != [matching_item(item) for item in expected_response]:
            logger.info(
                "[CTX-BUILD][anchor] session=%s stage=discarded reason=response_items_mismatch",
                self.session_id,
            )
            return None
        return replace(
            baseline, items=copy.deepcopy(items[:size + len(response_items)]),
        )

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
        pending_response = self._pending_response
        if pending_response is None:
            await self.storage.append_context_items(
                native, message_ids=identities, expected_restore_generation=self._restore_generation,
            )
        else:
            from siada.services.session_runtime_state import record_response

            # response_received advances the index before the SDK saves output.
            request = f"{self.admission_id}:request:{self._response_index - 1}"

            def commit():
                with self.storage._mutation():
                    added = self.storage.append_context_items_sync(
                        native, message_ids=identities, expected_restore_generation=self._restore_generation,
                    )
                    snapshot = self.storage.get_context_snapshot_sync()
                    self._check_restore_generation(snapshot)
                    baseline = self._durable_response_baseline(snapshot)
                    record_response(self._request_context, pending_response[0], baseline=baseline, publish=False)
                return added, baseline

            try:
                added, baseline = await asyncio.to_thread(commit)
            except Exception as error:
                logger.info(
                    "[CTX-BUILD][anchor] session=%s request=%s admission_id=%s "
                    "stage=response_commit_failed error_type=%s",
                    self.session_id, request, self.admission_id, type(error).__name__,
                )
                raise
            # Publish only after the outer message/usage/anchor transaction succeeds.
            state = self._request_context.session.state
            state.usage = pending_response[0].usage
            state.context_token_baseline = baseline
            self._pending_response = None
            logger.info(
                "[CTX-BUILD][anchor] session=%s request=%s admission_id=%s stage=response_committed "
                "anchored=%s baseline_source=%s restore_generation=%d prefix_items=%d "
                "input_tokens=%d response_tokens=%d baseline_tokens=%d",
                self.session_id, request, self.admission_id, baseline is not None,
                "server_usage" if baseline is not None else "unavailable", self._restore_generation or 0,
                len(baseline.items) if baseline is not None else 0,
                baseline.input_tokens if baseline is not None else 0,
                baseline.response_tokens if baseline is not None else 0,
                baseline.context_tokens if baseline is not None else 0,
            )
            if added and self.storage.on_items_added:
                try:
                    await self.storage.on_items_added(copy.deepcopy(added))
                except Exception as error:
                    logger.debug("Error in on_items_added hook: %s", error)
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

        Provider normalization remains downstream. Cancellation waits for the
        storage outcome; failed commits retain queues for an explicit retry.
        """
        if self._request_commit_done is not None:
            await self._request_commit_done.wait()
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

        logger.debug(
            "[CTX-BUILD][admission] session=%s request=%s stage=hooks_pending "
            "version=%d input_items=%d hook_items=%d",
            self.session_id, self.request_identity, self._request_version, size, len(tail),
        )
        commit_done = asyncio.Event()
        self._request_commit_done = commit_done
        cancellation: asyncio.CancelledError | None = None
        try:
            commit_task = asyncio.create_task(asyncio.to_thread(commit))
            try:
                while not commit_task.done():
                    try:
                        await asyncio.shield(commit_task)
                    except asyncio.CancelledError as error:
                        cancellation = cancellation or error
                added = commit_task.result()
            except Exception as error:
                logger.debug(
                    "[CTX-BUILD][admission] session=%s request=%s stage=hooks_commit_failed error_type=%s",
                    self.session_id, self.request_identity, type(error).__name__,
                )
                if cancellation is not None:
                    raise cancellation from error
                raise
            self._clear_committed_queues(tail)
            self._request_version += bool(added)
            self._request_input = native
            self._pending_finalization = None
            self._request_token_signature = None
            if self._request_context is not None and self._request_context.session is not None:
                from siada.agent_hub.context_filter.request_token_estimator import request_token_signature

                self._request_token_signature = request_token_signature(
                    self._request_context, self._request_agent, self._request_instructions,
                    components=self._request_signature_components,
                )
            logger.debug(
                "[CTX-BUILD][admission] session=%s request=%s stage=hooks_committed "
                "version=%d items=%d hook_items=%d anchor_eligible=%s",
                self.session_id, self.request_identity, self._request_version, len(native), len(tail),
                self._request_token_signature is not None,
            )
        finally:
            self._request_commit_done = None
            commit_done.set()
        if cancellation is not None:
            raise cancellation
        if added and self.storage.on_items_added:
            await self.storage.on_items_added(copy.deepcopy(added))

    def verify_request_model(self, model: Model) -> None:
        """Reject changed counting semantics before committing hooks or sending.

        Replacing metadata cannot recover a filter's previous budget decision.
        Restart with a newly configured run so its route is counted from scratch
        when incompatible with the durable baseline. Never retry this mismatch
        as a transport failure or discard uncommitted reminder queues.
        """
        actual_info = token_counting_info_from_model(model)
        matches = actual_info == self.token_counting_info
        logger.debug(
            "[CTX-BUILD][model] session=%s request=%s status=%s model_type=%s "
            "expected_info=%s actual_info=%s",
            self.session_id, self.request_identity, "matched" if matches else "counting_mismatch",
            type(model).__name__, self.token_counting_info, actual_info,
        )
        if not matches:
            self._request_token_signature = None
            context = self._request_context
            if context is not None and getattr(context, "session", None) is not None:
                context.session.state.context_token_baseline = None
            raise SessionStorageError(
                "Request model counting semantics changed; restart with a newly configured run before sending"
            )

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
        selected_model = config.model if config.model is not None else getattr(agent, "model", None)
        self.token_counting_info = (
            token_counting_info_from_model(selected_model) if isinstance(selected_model, Model)
            else provider_token_counting_info(config.model_provider, selected_model)
        )
        logger.debug(
            "[CTX-BUILD][route] session=%s request=%s source=%s configured_model=%s "
            "provider_type=%s info=%s",
            self.session_id, self.request_identity,
            "explicit_model" if isinstance(selected_model, Model) else "provider_route",
            getattr(selected_model, "model", None) if isinstance(selected_model, Model) else selected_model,
            type(config.model_provider).__name__, self.token_counting_info,
        )
        self.token_budget_model_settings = config.model_settings
        # This run uses a fixed model route and does not support handoff. Before
        # adding handoff, reevaluate per-agent model binding, counting metadata,
        # and whether model-instance caching is needed across SDK resolutions.

        async def authoritative_filter(data):
            if self._request_commit_done is not None:
                await self._request_commit_done.wait()
            self._check_restore_generation(await self.storage.get_context_snapshot())
            if self._pending_finalization is not None:
                # Recover under the previous request's context and identities,
                # using the same message/runtime-state transaction as admission.
                pending, _ = self._pending_finalization
                await self.finalize_request_input([*(self._request_input or []), *pending])
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
            self._request_agent = data.agent
            self._request_instructions = model_data.instructions
            self._request_version = version
            logger.info(
                "[effective-context][request] session=%s mode=prepared source=api_message.json "
                "admission_id=%s request_index=%d version_before=%d version=%d input_items=%d items=%d "
                "stage=filter_committed",
                self.session_id, self.admission_id, self._response_index,
                snapshot["context_version"], version, input_items, len(self._request_input),
            )
            return model_data

        model_provider = config.model_provider
        if isinstance(selected_model, Model):
            selected_model = ModelWrapper(
                selected_model, before_request=self.finalize_request_input, verify_model=self.verify_request_model,
            )
        else:
            model_provider = ModelProviderWrapper(
                model_provider, before_request=self.finalize_request_input, verify_model=self.verify_request_model,
            )
            # Count from pure route metadata: no preliminary model construction.
            # Retain the configured name to preserve SDK implicit setting precedence.
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
