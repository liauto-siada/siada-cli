"""Localized notification templates for Feishu IM messages."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_NOTIFICATION_LANGUAGE = "en"


@dataclass(frozen=True)
class IpcNotificationCardTemplate:
    """Localized copy used by IPC notification cards."""

    header_title: str
    switch_tip: str
    stay_tip: str
    source_label: str
    current_label: str


@dataclass(frozen=True)
class DirectTransportNotificationTemplate:
    """Localized copy used by direct transport status notifications."""

    connected_message: str
    disconnected_message: str


_IPC_NOTIFICATION_CARD_TEMPLATES: dict[str, IpcNotificationCardTemplate] = {
    "en": IpcNotificationCardTemplate(
        header_title="📬 Cross-Session Message",
        switch_tip="Reply here to switch to the source session.",
        stay_tip="To stay here, reply to an earlier message in this session.",
        source_label="Source",
        current_label="Current",
    ),
    "zh-CN": IpcNotificationCardTemplate(
        header_title="📬 Cross-Session Message",
        switch_tip="Reply to this message, or send a new one, to switch to the source session.",
        stay_tip="To stay in the current session, reply to an earlier message in this session.",
        source_label="Source",
        current_label="Current",
    ),
}


@dataclass(frozen=True)
class SessionSwitchNotificationTemplate:
    """Localized copy used by session-switch notifications."""

    switched_message: str  # contains {session_id} placeholder
    subsequent_hint: str
    switch_back_with_id: str  # contains {previous_sid} placeholder
    switch_back_generic: str


_SESSION_SWITCH_NOTIFICATION_TEMPLATES: dict[str, SessionSwitchNotificationTemplate] = {
    "en": SessionSwitchNotificationTemplate(
        switched_message="🔄 Switched to session {session_id}",
        subsequent_hint="Subsequent messages will be processed in this session context.",
        switch_back_with_id="To switch back, run `/resume {previous_sid}`",
        switch_back_generic="Use `/resume <session_id>` to switch to another session.",
    ),
    "zh-CN": SessionSwitchNotificationTemplate(
        switched_message="🔄 Switched to session {session_id}",
        subsequent_hint="Subsequent messages will be processed in this session context.",
        switch_back_with_id="To switch back, run `/resume {previous_sid}`",
        switch_back_generic="Use `/resume <session_id>` to switch to another session.",
    ),
}


_DIRECT_TRANSPORT_NOTIFICATION_TEMPLATES: dict[str, DirectTransportNotificationTemplate] = {
    "en": DirectTransportNotificationTemplate(
        connected_message=(
            "✅ Siada has successfully connected to Lark (direct mode).\n"
            "You can now chat with Siada via Lark."
        ),
        disconnected_message=(
            "🔴 Siada daemon has stopped. The Lark IM connection is disconnected.\n"
            "Messages you send will not be processed.\n"
            "Please restart Siada-CLI to continue."
        ),
    ),
    "zh-CN": DirectTransportNotificationTemplate(
        connected_message=(
            "✅ Siada has successfully connected to Lark (direct mode).\n"
            "You can now chat with Siada directly in Lark."
        ),
        disconnected_message=(
            "🔴 Siada daemon has stopped. The Lark IM connection is disconnected.\n"
            "Messages you send will not be processed.\n"
            "Please restart Siada-CLI to continue."
        ),
    ),
}


@dataclass(frozen=True)
class RelayTransportNotificationTemplate:
    """Localized copy used by relay transport status notifications."""

    connected_message: str
    disconnected_message: str
    kicked_message: str
    email_mismatch_message: str


_RELAY_TRANSPORT_NOTIFICATION_TEMPLATES: dict[str, RelayTransportNotificationTemplate] = {
    "en": RelayTransportNotificationTemplate(
        connected_message=(
            "✅ Siada has successfully connected to the Lark IM Gateway.\n"
            "You can now chat with Siada via Lark."
        ),
        disconnected_message=(
            "🔴 The Siada daemon has stopped and the Lark IM connection is closed.\n"
            "Messages you send will not be processed.\n"
            "Please restart Siada-CLI to continue."
        ),
        kicked_message=(
            "⚠️ Your Siada connection has been terminated: your account was "
            "logged in on another device.\n"
            "The connection on this device has ended and will not auto-reconnect.\n"
            "To continue, please restart Siada-CLI."
        ),
        email_mismatch_message=(
            "❌ Siada connection rejected (4005 EMAIL_MISMATCH):\n"
            "The email in the relay config does not match the IDaaS token identity.\n"
            "Please verify that the email in the relay config matches the currently "
            "logged-in account, then restart Siada-CLI."
        ),
    ),
    "zh-CN": RelayTransportNotificationTemplate(
        connected_message=(
            "✅ Siada has successfully connected to the Lark IM Gateway.\n"
            "You can now chat with Siada via Lark."
        ),
        disconnected_message=(
            "🔴 The Siada daemon has stopped and the Lark IM connection is closed.\n"
            "Messages you send will not be processed.\n"
            "Please restart Siada-CLI to continue."
        ),
        kicked_message=(
            "⚠️ Your Siada connection has been terminated: your account was "
            "logged in on another device.\n"
            "The connection on this device has ended and will not auto-reconnect.\n"
            "To continue, please restart Siada-CLI."
        ),
        email_mismatch_message=(
            "❌ Siada connection rejected (4005 EMAIL_MISMATCH):\n"
            "The email in the relay config does not match the IDaaS token identity.\n"
            "Please verify that the email in the relay config matches the currently "
            "logged-in account, then restart Siada-CLI."
        ),
    ),
}


@dataclass(frozen=True)
class IdleSessionResetNotificationTemplate:
    """Localized copy used when a new session is auto-created after idle timeout."""

    reset_message: str  # contains {idle_minutes} placeholder
    resume_hint: str  # contains {previous_sid} placeholder
    resume_hint_generic: str


_IDLE_SESSION_RESET_NOTIFICATION_TEMPLATES: dict[str, IdleSessionResetNotificationTemplate] = {
    "en": IdleSessionResetNotificationTemplate(
        reset_message=(
            "🆕 You've been idle for over {idle_minutes} minutes, so a fresh "
            "session has been started for this conversation."
        ),
        resume_hint="To go back to the previous conversation, run `/resume {previous_sid}`",
        resume_hint_generic="Use `/resume <session_id>` to switch back to a previous session.",
    ),
    "zh-CN": IdleSessionResetNotificationTemplate(
        reset_message=(
            "🆕 You've been idle for over {idle_minutes} minutes, so a fresh "
            "session has been started for this conversation."
        ),
        resume_hint="To go back to the previous conversation, run `/resume {previous_sid}`",
        resume_hint_generic="Use `/resume <session_id>` to switch back to a previous session.",
    ),
}


def normalize_notification_language(language: str | None) -> str:
    """Normalize language code to a supported notification language."""
    if not language:
        return DEFAULT_NOTIFICATION_LANGUAGE
    if language.startswith("zh"):
        return "zh-CN"
    if language == "en":
        return "en"
    return DEFAULT_NOTIFICATION_LANGUAGE


def get_ipc_notification_card_template(
    language: str | None,
) -> IpcNotificationCardTemplate:
    """Return localized template for IPC notification cards."""
    normalized_language = normalize_notification_language(language)
    return _IPC_NOTIFICATION_CARD_TEMPLATES[normalized_language]


def get_session_switch_notification_template(
    language: str | None,
) -> SessionSwitchNotificationTemplate:
    """Return localized template for session-switch notifications."""
    normalized_language = normalize_notification_language(language)
    return _SESSION_SWITCH_NOTIFICATION_TEMPLATES[normalized_language]


def get_direct_transport_notification_template(
    language: str | None,
) -> DirectTransportNotificationTemplate:
    """Return localized template for direct transport notifications."""
    normalized_language = normalize_notification_language(language)
    return _DIRECT_TRANSPORT_NOTIFICATION_TEMPLATES[normalized_language]


def get_relay_transport_notification_template(
    language: str | None,
) -> RelayTransportNotificationTemplate:
    """Return localized template for relay transport notifications."""
    normalized_language = normalize_notification_language(language)
    return _RELAY_TRANSPORT_NOTIFICATION_TEMPLATES[normalized_language]


def get_notification_footer(
    language: str | None, device_info: str, version: str
) -> str:
    """Return the localized device/version footer appended to notifications.

    Used by both direct and relay transports for connect/disconnect messages
    so the footer (start/stop) is consistent with the message language.
    """
    if normalize_notification_language(language) == "zh-CN":
        return f"Device: {device_info}\nVersion: {version}"
    return f"Device: {device_info}\nVersion: {version}"


def get_idle_session_reset_notification_template(
    language: str | None,
) -> IdleSessionResetNotificationTemplate:
    """Return localized template for idle-triggered new-session notifications."""
    normalized_language = normalize_notification_language(language)
    return _IDLE_SESSION_RESET_NOTIFICATION_TEMPLATES[normalized_language]


# ── Daily summary notification ────────────────────────────────────────


@dataclass(frozen=True)
class DailySummaryNotificationTemplate:
    """Localized copy used by proactive daily summary notifications."""

    header_title: str


def get_daily_summary_notification_template(
    language: str | None = None,
) -> DailySummaryNotificationTemplate:
    """Card header template for proactive daily summary IPC notifications."""
    if (language or "").lower().startswith("en"):
        return DailySummaryNotificationTemplate(
            header_title="Siada Daily Summary",
        )
    return DailySummaryNotificationTemplate(
        header_title="Siada Daily Summary",
    )
