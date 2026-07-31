"""Abstract base class for IM (Instant Messaging) controllers.

Defines the interface that all IM controllers (Lark, WeCom, DingTalk, etc.)
must implement to integrate with the SiadaDaemon.

Includes session routing infrastructure: a persistent routing table that maps
chat_id -> session_id, enabling switchable sessions per chat conversation.
"""

import abc
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional, TypedDict

from siada.session.ownership import SessionOwner, SessionOwnershipManager

if TYPE_CHECKING:
    from siada.entrypoint.interaction.running_config import RunningConfig
    from siada.session.session_models import RunningSession

logger = logging.getLogger("siada.im.controller")


class RoutingEntry(TypedDict):
    """Persisted routing metadata for a chat."""

    session_id: str
    is_single_chat: bool


class RoutingTable:
    """In-memory routing table matching the routing.json on-disk structure.

    Encapsulates two indices and provides unified query methods::

        {
            "chats":    { chat_id: RoutingEntry, ... },
            "open_ids": { open_id: session_id,   ... }
        }
    """

    _CHATS_KEY = "chats"
    _OPEN_IDS_KEY = "open_ids"

    def __init__(self) -> None:
        self.chats: dict[str, RoutingEntry] = {}
        self.open_ids: dict[str, str] = {}

    # ── Chat-based queries ────────────────────────────────────────────

    def get_entry(self, chat_id: str) -> Optional[RoutingEntry]:
        """Return routing metadata for a chat if present."""
        return self.chats.get(chat_id)

    def get_session_id(self, chat_id: str) -> Optional[str]:
        """Return the routed session_id for a chat if present."""
        entry = self.get_entry(chat_id)
        return entry["session_id"] if entry else None

    def is_single_chat(self, chat_id: str) -> bool:
        """Whether the routed chat is known to be a single chat."""
        entry = self.get_entry(chat_id)
        return bool(entry and entry["is_single_chat"])

    def set_entry(
        self,
        chat_id: str,
        session_id: str,
        *,
        is_single_chat: Optional[bool] = None,
    ) -> bool:
        """Upsert a chat routing entry. Returns True when the payload changed."""
        current = self.get_entry(chat_id)
        next_is_single_chat = (
            current["is_single_chat"]
            if current is not None and is_single_chat is None
            else (is_single_chat if is_single_chat is not None else False)
        )
        new_entry: RoutingEntry = {
            "session_id": session_id,
            "is_single_chat": next_is_single_chat,
        }
        if current == new_entry:
            return False
        self.chats[chat_id] = new_entry
        return True

    def remove_chat(self, chat_id: str) -> Optional[RoutingEntry]:
        """Remove and return routing entry for a chat."""
        return self.chats.pop(chat_id, None)

    # ── Open-ID-based queries ─────────────────────────────────────────

    def get_session_id_by_open_id(self, open_id: str) -> Optional[str]:
        """Return the session_id mapped to an open_id, if any."""
        return self.open_ids.get(open_id)

    def set_open_id(self, open_id: str, session_id: str) -> None:
        """Map an open_id to a session_id."""
        self.open_ids[open_id] = session_id

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize to the routing.json on-disk format."""
        return {
            self._CHATS_KEY: dict(self.chats),
            self._OPEN_IDS_KEY: dict(self.open_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoutingTable":
        """Deserialize from routing.json, supporting both new and legacy formats.

        New format::
            {"chats": {chat_id: RoutingEntry, ...}, "open_ids": {open_id: session_id, ...}}

        Legacy flat format::
            {chat_id: RoutingEntry | session_id, ..., "__open_id_index__": {...}}
        """
        table = cls()
        if not isinstance(data, dict):
            return table

        # Detect format
        is_new_format = cls._CHATS_KEY in data
        chats_raw: dict = {}
        open_ids_raw: dict = {}

        if is_new_format:
            chats_raw = data.get(cls._CHATS_KEY, {})
            open_ids_raw = data.get(cls._OPEN_IDS_KEY, {})
        else:
            # Legacy flat format
            chats_raw = {
                k: v for k, v in data.items()
                if k != "__open_id_index__"
            }
            legacy_oid = data.get("__open_id_index__")
            if isinstance(legacy_oid, dict):
                open_ids_raw = legacy_oid
            logger.info(
                "Detected legacy flat routing format, will migrate on next persist"
            )

        # Normalize chat entries
        if isinstance(chats_raw, dict):
            for chat_id, raw_entry in chats_raw.items():
                if not isinstance(chat_id, str):
                    continue
                entry = _normalize_routing_entry(chat_id, raw_entry)
                if entry is not None:
                    table.chats[chat_id] = entry

        # Normalize open_id index
        if isinstance(open_ids_raw, dict):
            table.open_ids = {
                k: v for k, v in open_ids_raw.items()
                if isinstance(k, str) and isinstance(v, str)
            }

        return table


def _normalize_routing_entry(
    chat_id: str, raw_entry: object,
) -> Optional[RoutingEntry]:
    """Normalize persisted routing data into the current structured format."""
    if isinstance(raw_entry, str):
        # Legacy format: chat_id -> session_id
        return {"session_id": raw_entry, "is_single_chat": False}

    if not isinstance(raw_entry, dict):
        logger.debug(
            "Skipping IM routing entry for chat_id=%s: unsupported type=%s",
            chat_id, type(raw_entry).__name__,
        )
        return None

    session_id = raw_entry.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        logger.debug(
            "Skipping IM routing entry for chat_id=%s: invalid session_id=%r",
            chat_id, session_id,
        )
        return None

    return {
        "session_id": session_id,
        "is_single_chat": bool(raw_entry.get("is_single_chat", False)),
    }


def _clear_target_inject_info_on_resume(
    session: Optional["RunningSession"],
) -> None:
    """Acknowledge the target session's pending inject_info upon switch-in.

    Cross-session IPC routing is driven by ``inject_info.json`` on the session
    the user is CURRENTLY talking to (it means "you have an unseen injection,
    route away on the next message").  When the user explicitly switches INTO
    a session — e.g. via ``/resume``, session cache hit, or a fully-resumed
    slow-path — any pending inject_info on that target must be cleared,
    otherwise the very next message on that session would route the user
    right back out again.

    This does NOT touch the source session's inject_info — routing consumption
    is handled by ``ThreadSessionRouter._check_session_injected_content``.
    """
    try:
        state = getattr(session, "state", None)
        fs = getattr(state, "openai_session", None) if state is not None else None
        if fs is not None and hasattr(fs, "clear_inject_info"):
            fs.clear_inject_info()
    except Exception as e:
        logger.debug("clear target inject_info on resume failed: %s", e)



class ImController(abc.ABC):
    """Abstract IM controller that bridges messaging platforms to SiadaRunner.

    Provides session routing infrastructure at the base class level:
    - _routing: persistent RoutingTable (chats + open_ids), serialized to routing.json
    - _session_cache: in-memory cache of session_id -> RunningSession
    - resolve_session / set_session_for_chat / create_new_session / clear_session

    Subclasses must implement:
    - start(): connect transport and begin processing messages
    - stop(): gracefully disconnect and clean up
    - is_running: property indicating whether the controller is active
    - owner_type: the SessionOwner enum value for ownership tracking
    - workspace: the workspace path used by the controller (for session ownership)
    """

    def __init__(self):
        self._routing = RoutingTable()
        # Separate routing table for group chats (persisted as group_routing.json)
        self._group_routing = RoutingTable()
        # Session cache: session_id -> RunningSession (in-memory only)
        self._session_cache: dict[str, "RunningSession"] = {}
        # App identifier for state isolation (set by subclasses)
        self._app_id: Optional[str] = None
        # Per-chat last user-activity timestamp (epoch seconds). Persisted to
        # last_activity.json and reloaded on startup so idle-based session
        # resets survive daemon restarts.
        self._last_activity_ts: dict[str, float] = {}
        # Timestamp of the most recent _load_routing() call (i.e. when the
        # controller became ready to receive messages).  Used as a fallback
        # reference when last_activity is absent for a chat_id so that idle
        # resets work correctly even on the very first message after a restart.
        self._controller_start_ts: float = time.time()

    # ── Session source marking ────────────────────────────────────────

    def _mark_session_source(self, session_id: str, workspace: str) -> None:
        """Record session_source in metadata when a session is first created by this IM controller."""
        try:
            from siada.utils import DirectoryUtils
            session_dir = Path(DirectoryUtils.get_global_sessions_dir(workspace)) / session_id
            SessionOwnershipManager.set_session_source(session_dir, self.owner_type)
            logger.debug(
                "Marked session_source=%s for session_id=%s",
                self.owner_type.value, session_id,
            )
        except Exception as e:
            logger.warning("Failed to mark session_source for %s: %s", session_id, e)

    # ── Routing persistence ──────────────────────────────────────────

    def _get_im_state_dir(self) -> Path:
        """Return the state directory for this controller instance.

        Path layout: SIADA_HOME/im/{platform_name}/{app_id}/
        When _app_id is set, state files are isolated per bot so that
        switching app_id in conf.yaml does not cause routing conflicts.
        Falls back to SIADA_HOME/im/{platform_name}/ when _app_id is not set.
        """
        from siada.foundation.constants import SIADA_HOME

        im_dir = SIADA_HOME / "im" / self.platform_name
        if self._app_id:
            im_dir = im_dir / self._app_id
        im_dir.mkdir(parents=True, exist_ok=True)
        return im_dir

    def _get_routing_file_path(self) -> Path:
        """Return path to routing.json under the IM state directory.

        Project-agnostic: routing is global across all workspaces.
        Platform-specific: each IM platform (lark, wecom, etc.) has its own file.
        App-specific: each app_id has its own subdirectory to avoid conflicts.
        """
        return self._get_im_state_dir() / "routing.json"

    def _get_group_routing_file_path(self) -> Path:
        """Return path to group_routing.json under the IM state directory.

        Separate file for group chat routing to isolate group sessions from P2P sessions.
        """
        return self._get_im_state_dir() / "group_routing.json"

    @staticmethod
    def _get_fallback_workspace() -> str:
        """Fallback workspace when self.workspace is None."""
        import os
        return os.getcwd()

    @staticmethod
    def _normalize_routing_entry(
        chat_id: str, raw_entry: object
    ) -> Optional[RoutingEntry]:
        """Normalize persisted routing data into the current structured format."""
        if isinstance(raw_entry, str):
            # Legacy format: chat_id -> session_id
            return {"session_id": raw_entry, "is_single_chat": False}

        if not isinstance(raw_entry, dict):
            logger.debug(
                "Skipping IM routing entry for chat_id=%s: unsupported type=%s",
                chat_id,
                type(raw_entry).__name__,
            )
            return None

        session_id = raw_entry.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            logger.debug(
                "Skipping IM routing entry for chat_id=%s: invalid session_id=%r",
                chat_id,
                session_id,
            )
            return None

        return {
            "session_id": session_id,
            "is_single_chat": bool(raw_entry.get("is_single_chat", False)),
        }

    def _select_routing(self, *, is_group: bool = False) -> "RoutingTable":
        """Return the appropriate routing table based on chat type.

        Group chats use a separate routing table to isolate their sessions
        from P2P (single chat) sessions.
        """
        return self._group_routing if is_group else self._routing

    def _get_routing_entry(
        self, chat_id: str, *, is_group: bool = False,
    ) -> Optional[RoutingEntry]:
        """Return routing metadata for a chat if present."""
        return self._select_routing(is_group=is_group).get_entry(chat_id)

    def _get_routed_session_id(
        self, chat_id: str, *, open_id: Optional[str] = None,
        is_group: bool = False,
    ) -> Optional[str]:
        """Return the routed session_id, trying chat_id first then open_id fallback."""
        table = self._select_routing(is_group=is_group)
        session_id = table.get_session_id(chat_id)
        if session_id:
            return session_id
        if open_id:
            return table.get_session_id_by_open_id(open_id) or None
        return None

    def _get_session_id_by_open_id(self, open_id: str) -> Optional[str]:
        """Return the session_id mapped to an open_id, if any."""
        return self._routing.get_session_id_by_open_id(open_id)

    def _set_open_id_index(self, open_id: str, session_id: str) -> None:
        """Map an open_id to a session_id in the index."""
        self._routing.set_open_id(open_id, session_id)

    def _is_single_chat(self, chat_id: str) -> bool:
        """Whether the routed chat is known to be a single chat."""
        return self._routing.is_single_chat(chat_id)

    def _is_group_chat(self, *, is_single_chat: Optional[bool] = None) -> bool:
        """Determine if the chat is a group chat based on is_single_chat flag."""
        return is_single_chat is not None and not is_single_chat

    def _set_routing_entry(
        self,
        chat_id: str,
        session_id: str,
        *,
        is_single_chat: Optional[bool] = None,
    ) -> bool:
        """Upsert a routing entry to the appropriate table (P2P or group).

        Returns True when the persisted routing payload changed.
        """
        import traceback
        is_group = self._is_group_chat(is_single_chat=is_single_chat)
        table = self._select_routing(is_group=is_group)
        caller = "".join(traceback.format_stack(limit=4)[:-1]).strip()
        logger.info(
            "Routing upsert requested: chat_id=%s, session_id=%s, is_single_chat=%s, "
            "table=%s\n  caller: %s",
            chat_id, session_id, is_single_chat,
            "group" if is_group else "p2p", caller,
        )
        old = table.get_entry(chat_id)
        changed = table.set_entry(
            chat_id, session_id, is_single_chat=is_single_chat,
        )
        if changed:
            logger.info(
                "Routing entry updated: chat_id=%s, old=%s -> new=%s (table=%s)",
                chat_id, old, table.get_entry(chat_id),
                "group" if is_group else "p2p",
            )
        else:
            logger.debug("Routing entry unchanged for chat_id=%s", chat_id)
        return changed

    def _load_routing(self) -> None:
        """Load P2P and group routing tables from disk."""
        # Load P2P routing
        try:
            path = self._get_routing_file_path()
            logger.info("Loading IM routing table from %s", path)
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                self._routing = RoutingTable.from_dict(data)
                logger.info(
                    "Loaded IM routing table with %d chat entries, "
                    "%d open_id index entries from %s",
                    len(self._routing.chats), len(self._routing.open_ids), path,
                )
            else:
                logger.info("IM routing file does not exist yet: %s", path)
        except Exception as e:
            logger.warning(f"Failed to load IM routing table: {e}")

        # Load group routing
        try:
            group_path = self._get_group_routing_file_path()
            logger.info("Loading IM group routing table from %s", group_path)
            if group_path.exists():
                data = json.loads(group_path.read_text(encoding="utf-8"))
                self._group_routing = RoutingTable.from_dict(data)
                logger.info(
                    "Loaded IM group routing table with %d chat entries from %s",
                    len(self._group_routing.chats), group_path,
                )
            else:
                logger.info("IM group routing file does not exist yet: %s", group_path)
        except Exception as e:
            logger.warning(f"Failed to load IM group routing table: {e}")

        # Migration: move existing group entries from P2P routing to group routing
        self._migrate_group_entries_from_p2p_routing()

        # Restore per-chat last-activity timestamps for idle-based resets
        self._load_last_activity()

        # Refresh the ready-timestamp so idle-reset comparisons are anchored to
        # the moment this routing load completed (i.e. when the controller is
        # about to start receiving messages).  For relay mode this happens after
        # Gateway auth, so it correctly reflects the actual ready time rather
        # than the earlier __init__ call.
        self._controller_start_ts = time.time()

    # ── Last-activity persistence ─────────────────────────────────────

    def _get_last_activity_file_path(self) -> Path:
        """Return path to last_activity.json under the IM state directory."""
        return self._get_im_state_dir() / "last_activity.json"

    def _load_last_activity(self) -> None:
        """Load per-chat last-activity timestamps from disk (best-effort)."""
        import datetime

        try:
            path = self._get_last_activity_file_path()
            if not path.exists():
                logger.info("Last-activity file does not exist yet: %s", path)
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._last_activity_ts = {
                    str(chat_id): float(ts)
                    for chat_id, ts in data.items()
                    if isinstance(ts, (int, float))
                }
                now = time.time()
                detail_lines = []
                for chat_id, ts in self._last_activity_ts.items():
                    dt_str = datetime.datetime.fromtimestamp(ts).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    idle_secs = now - ts
                    detail_lines.append(
                        f"  {chat_id}: last_activity={dt_str} (idle {idle_secs:.0f}s ago)"
                    )
                detail_str = "\n".join(detail_lines) if detail_lines else "  (none)"
                logger.info(
                    "Loaded %d last-activity entries from %s:\n%s",
                    len(self._last_activity_ts), path, detail_str,
                )
        except Exception as e:
            logger.warning("Failed to load IM last-activity timestamps: %s", e)

    def _persist_last_activity(self) -> None:
        """Write per-chat last-activity timestamps to disk (best-effort)."""
        try:
            path = self._get_last_activity_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self._last_activity_ts, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to persist IM last-activity timestamps: %s", e)

    def _migrate_group_entries_from_p2p_routing(self) -> None:
        """One-time migration: move non-single-chat entries from _routing to _group_routing."""
        to_migrate: list[tuple[str, RoutingEntry]] = []
        for chat_id, entry in list(self._routing.chats.items()):
            if not entry.get("is_single_chat", False):
                to_migrate.append((chat_id, entry))

        if not to_migrate:
            return

        for chat_id, entry in to_migrate:
            if chat_id not in self._group_routing.chats:
                self._group_routing.chats[chat_id] = entry
            self._routing.chats.pop(chat_id)

        self._persist_routing()
        self._persist_group_routing()
        logger.info(
            "Migrated %d group chat entries from P2P routing to group routing",
            len(to_migrate),
        )

    def _persist_routing(self) -> None:
        """Write P2P routing table to disk via ``RoutingTable.to_dict``."""
        try:
            path = self._get_routing_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(
                "Persisting IM routing table (%d chats, %d open_ids) to %s",
                len(self._routing.chats), len(self._routing.open_ids), path,
            )
            path.write_text(
                json.dumps(self._routing.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to persist IM routing table: {e}")

    def _persist_group_routing(self) -> None:
        """Write group routing table to disk."""
        try:
            path = self._get_group_routing_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(
                "Persisting IM group routing table (%d chats) to %s",
                len(self._group_routing.chats), path,
            )
            path.write_text(
                json.dumps(self._group_routing.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to persist IM group routing table: {e}")

    def _persist_routing_for(self, *, is_group: bool = False) -> None:
        """Persist the appropriate routing table based on chat type."""
        if is_group:
            self._persist_group_routing()
        else:
            self._persist_routing()

    # ── Session resolution ───────────────────────────────────────────

    def resolve_session(
        self,
        chat_id: str,
        running_config: "RunningConfig",
        *,
        is_single_chat: Optional[bool] = None,
        open_id: Optional[str] = None,
    ) -> "RunningSession":
        """Resolve or create the session bound to a chat_id.

        Resolution flow:
        1. Look up session_id in routing table
        2. If not found, generate new timestamp-based session_id and persist
        3. Check session cache for existing RunningSession
        4. If cached, refresh FileSession and config, return cached session
        5. If not cached, create new RunningSession, cache and return
        """
        from siada.session.session_manager import RunningSessionManager

        is_group = self._is_group_chat(is_single_chat=is_single_chat)
        session_id = self._get_routed_session_id(
            chat_id, open_id=open_id, is_group=is_group,
        )

        if session_id is None:
            # No routing entry — create new session_id (timestamp + uuid)
            from siada.foundation.id_generator import generate_session_id
            session_id = generate_session_id()
            self._set_routing_entry(
                chat_id, session_id, is_single_chat=is_single_chat
            )
            self._persist_routing_for(is_group=is_group)
            logger.info(
                f"Created new routing: chat_id={chat_id} -> session_id={session_id} "
                f"(table={'group' if is_group else 'p2p'})"
            )
        elif self._set_routing_entry(
            chat_id, session_id, is_single_chat=is_single_chat
        ):
            self._persist_routing_for(is_group=is_group)

        # Return cached session directly — its state (including workspace
        # and FileSession) is already correct from the initial creation
        # or from switch_and_resume_session.
        cached = self._session_cache.get(session_id)
        if cached is not None:
            logger.info(
                f"Reusing cached session: chat_id={chat_id}, session_id={session_id}"
            )
            return cached

        # No cached session — create brand new one
        logger.info(
            f"Creating new session: chat_id={chat_id}, session_id={session_id}"
        )
        session = RunningSessionManager.create_session(
            siada_config=running_config,
            session_id=session_id,
        )
        self._mark_session_source(session_id, running_config.workspace)
        self._session_cache[session_id] = session
        return session

    # ── Session switching ────────────────────────────────────────────

    def switch_and_resume_session(
        self, chat_id: str, target_session_id: str, running_config: "RunningConfig",
        *, is_single_chat: Optional[bool] = None,
    ) -> Optional["RunningSession"]:
        """Switch a chat to a different session with full resume (history + api_messages).

        Uses ResumeService to load the target session data from disk and
        restore it into a fresh RunningSession, preserving message history,
        api_messages, task_message_state, and compaction state.

        Returns the restored RunningSession on success, or None if the resume
        failed (caller should fall back to resolve_session).
        """
        from siada.session.session_manager import RunningSessionManager
        from siada.support.resume_service import ResumeService

        # Fast path: if the target session is already in memory cache,
        # just update routing and return it — no disk I/O needed.
        cached = self._session_cache.get(target_session_id)
        if cached is not None:
            self.set_session_for_chat(
                chat_id, target_session_id, is_single_chat=is_single_chat,
            )
            logger.info(
                "switch_and_resume_session: using cached session %s for chat_id=%s",
                target_session_id, chat_id,
            )
            _clear_target_inject_info_on_resume(cached)
            return cached

        try:
            # Phase 1: discover the target session's project_root via a
            # lightweight lookup (scope='all' scans all projects).
            discovery_workspace = self.workspace or self._get_fallback_workspace()
            discovery_svc = ResumeService(discovery_workspace)
            session_info = discovery_svc.get_session_info(target_session_id)
            if session_info is None:
                logger.warning(
                    "switch_and_resume_session: session %s not found",
                    target_session_id,
                )
                return None

            # Phase 2: create ResumeService rooted at the target session's
            # own project so that path resolution is correct.
            target_workspace = session_info.project_root or discovery_workspace
            resume_svc = ResumeService(target_workspace)
            result = resume_svc.execute(target_session_id)
            if result is None or result[0] is None:
                err_msg = result[1] if result else "unknown error"
                logger.warning(
                    "switch_and_resume_session: failed to load session %s: %s",
                    target_session_id, err_msg,
                )
                return None

            session_data, info_msg = result
            logger.info("switch_and_resume_session: loaded session data — %s", info_msg)

            # Override workspace in running_config to match the target
            # session's project, so that FileSession paths resolve correctly.
            import dataclasses
            target_config = dataclasses.replace(running_config, workspace=target_workspace)

            # Create a fresh RunningSession as the restore target
            session = RunningSessionManager.create_session(
                siada_config=target_config,
                session_id=target_session_id,
            )

            # Full restore: message_history, api_messages, token count, etc.
            resume_svc.restore_to_running_session(session_data, session)

            # Update routing and cache
            self.set_session_for_chat(
                chat_id, target_session_id, is_single_chat=is_single_chat,
            )
            self._session_cache[target_session_id] = session
            _clear_target_inject_info_on_resume(session)
            logger.info(
                "switch_and_resume_session: chat_id=%s now on session_id=%s (fully resumed)",
                chat_id, target_session_id,
            )
            return session

        except Exception as e:
            logger.error(
                "switch_and_resume_session failed for session %s: %s",
                target_session_id, e, exc_info=True,
            )
            return None

    def set_session_for_chat(
        self,
        chat_id: str,
        session_id: str,
        *,
        is_single_chat: Optional[bool] = None,
        open_id: Optional[str] = None,
    ) -> None:
        """Programmatically switch a chat to a different session.

        Validates target, evicts old session from cache, updates and persists routing.
        """
        is_group = self._is_group_chat(is_single_chat=is_single_chat)
        old_session_id = self._get_routed_session_id(
            chat_id, open_id=open_id, is_group=is_group,
        )
        if old_session_id:
            self._session_cache.pop(old_session_id, None)

        self._set_routing_entry(
            chat_id, session_id, is_single_chat=is_single_chat
        )
        self._persist_routing_for(is_group=is_group)
        logger.info(
            f"Switched session for chat_id={chat_id}: "
            f"{old_session_id} -> {session_id} (table={'group' if is_group else 'p2p'})"
        )

    def create_new_session(
        self,
        chat_id: str,
        running_config: "RunningConfig",
        *,
        is_single_chat: Optional[bool] = None,
        open_id: Optional[str] = None,
    ) -> "RunningSession":
        """Create a brand new session and bind it to the chat.

        Previous session is preserved on disk (can be switched back later).
        """
        from siada.session.session_manager import RunningSessionManager

        is_group = self._is_group_chat(is_single_chat=is_single_chat)
        old_session_id = self._get_routed_session_id(
            chat_id, open_id=open_id, is_group=is_group,
        )
        if old_session_id:
            self._session_cache.pop(old_session_id, None)

        from siada.foundation.id_generator import generate_session_id
        new_session_id = generate_session_id()
        session = RunningSessionManager.create_session(
            siada_config=running_config,
            session_id=new_session_id,
        )
        self._mark_session_source(new_session_id, running_config.workspace)
        self._set_routing_entry(
            chat_id, new_session_id, is_single_chat=is_single_chat
        )
        self._session_cache[new_session_id] = session
        self._persist_routing_for(is_group=is_group)
        logger.info(
            f"Created new session for chat_id={chat_id}: "
            f"{old_session_id} -> {new_session_id} (table={'group' if is_group else 'p2p'})"
        )
        return session

    def clear_session(self, chat_id: str) -> None:
        """Clear routing and cache for a chat (checks both P2P and group tables)."""
        # Try P2P routing first, then group routing
        old_entry = self._routing.remove_chat(chat_id)
        is_group = False
        if old_entry is None:
            old_entry = self._group_routing.remove_chat(chat_id)
            is_group = True
        old_session_id = old_entry["session_id"] if old_entry else None
        if old_session_id:
            self._session_cache.pop(old_session_id, None)
        self._persist_routing_for(is_group=is_group)
        logger.info(
            f"Cleared session for chat_id={chat_id} (was: {old_session_id}, "
            f"table={'group' if is_group else 'p2p'})"
        )

    # ── Legacy migration ─────────────────────────────────────────────

    def _migrate_legacy_sessions(self) -> None:
        """Auto-migrate lark_* format sessions into routing table.

        Scans session directories for legacy lark_{mode}_{uid}_{chat_id} patterns
        and adds them to the routing table if not already present.
        """
        from siada.utils import DirectoryUtils

        workspace = self.workspace or self._get_fallback_workspace()
        sessions_dir = Path(DirectoryUtils.get_global_sessions_dir(workspace))
        if not sessions_dir.exists():
            return

        migrated = 0
        for session_dir in sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            name = session_dir.name
            # Match pattern: lark_{mode}_{uid}_{chat_id}
            if name.startswith("lark_"):
                parts = name.split("_", 3)
                if len(parts) >= 4:
                    chat_id = parts[3]
                    if chat_id not in self._routing.chats:
                        self._set_routing_entry(
                            chat_id,
                            name,
                            is_single_chat=True,
                        )
                        migrated += 1

        if migrated > 0:
            self._persist_routing()
            logger.info(f"Migrated {migrated} legacy lark sessions into routing table")

    # ── Abstract interface ───────────────────────────────────────────

    @abc.abstractmethod
    async def start(self) -> None:
        """Connect transport and start the message processing loop."""
        ...

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop the controller and disconnect transport."""
        ...

    @property
    @abc.abstractmethod
    def is_running(self) -> bool:
        """Whether the controller is currently running."""
        ...

    @property
    @abc.abstractmethod
    def owner_type(self) -> SessionOwner:
        """The session owner type for ownership tracking."""
        ...

    @property
    @abc.abstractmethod
    def workspace(self) -> Optional[str]:
        """The workspace path used by this controller."""
        ...

    @property
    @abc.abstractmethod
    def platform_name(self) -> str:
        """The IM platform identifier (e.g. 'lark', 'wecom', 'dingtalk').

        Used for platform-specific routing and index file paths under
        SIADA_HOME/im/{platform_name}/.
        """
        ...

    @classmethod
    @abc.abstractmethod
    def create_if_configured(cls) -> Optional["ImController"]:
        """Factory method: load config and create controller if properly configured.

        Returns:
            An ImController instance if config exists and is valid, None otherwise.
        """
        ...