"""Shared tail of the "resume a persisted session from disk" paths.

Both the ACP runtime (``acp_server.runtime.restore_session``) and the IM
controller (``entrypoint.interaction.im_controller.switch_and_resume_session``)
finish the same way: create a fresh :class:`RunningSession` configured for the
target workspace and restore the persisted :class:`SessionData` into it.

The *locating* of the session on disk stays intentionally divergent in the
callers:

- the ACP runtime locates via the workspace's project-hash directory
  (``SessionManager.resolve_session_path``, an O(1) lookup),
- the IM controller scans across all projects (``ResumeService`` with
  ``scope='all'``), because a chat session may belong to any project.

Only the create + restore tail below is shared.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from siada.entrypoint.interaction.running_config import RunningConfig
    from siada.services.session_management import SessionData
    from siada.session.session_models import RunningSession


def restore_into_fresh_session(
    session_data: "SessionData",
    *,
    target_workspace: str,
    siada_config: "RunningConfig",
    session_id: str,
) -> "RunningSession":
    """Create a fresh RunningSession and restore session_data into it (shared tail of all disk-resume paths)."""
    from siada.session.session_manager import RunningSessionManager
    from siada.support.resume_service import ResumeService

    running_session = RunningSessionManager.create_session(
        siada_config=siada_config,
        session_id=session_id,
    )
    # A fresh ResumeService instance is equivalent to reusing the caller's:
    # restore_to_running_session only reads session_data / running_session and
    # calls stateless helpers — it never consults self.session_manager.
    ResumeService(target_workspace).restore_to_running_session(
        session_data, running_session
    )
    return running_session