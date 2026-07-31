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
        header_title="📬 跨会话消息",
        switch_tip="回复这条消息或者直接发送新消息，都会切到来源session。",
        stay_tip="若想留在当前session，请回复本session中更早的一条消息。",
        source_label="来源",
        current_label="当前",
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
        switched_message="🔄 已切换到会话 {session_id}",
        subsequent_hint="后续消息将在此会话上下文中处理。",
        switch_back_with_id="如需切回，请执行 `/resume {previous_sid}`",
        switch_back_generic="使用 `/resume <session_id>` 切换到其他会话。",
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
            "✅ Siada 已成功连接到飞书（direct 模式）。\n"
            "现在你可以直接在飞书里和 Siada 对话。"
        ),
        disconnected_message=(
            "🔴 Siada daemon 已停止，飞书 IM 连接已断开。\n"
            "你发送的消息将不会被处理。\n"
            "请重启 Siada-CLI 后继续。"
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
            "✅ Siada 已成功连接到飞书 IM Gateway。\n"
            "您现在可以通过飞书与 Siada 进行对话了。"
        ),
        disconnected_message=(
            "🔴 Siada 守护进程已停止运行，飞书 IM 连接已断开。\n"
            "您发送的消息将不会被处理。\n"
            "如需继续使用，请重新启动 Siada-CLI。"
        ),
        kicked_message=(
            "⚠️ 您的 Siada 连接已被断开：您的账号在另一台设备上登录了。\n"
            "当前设备的连接已终止，不会自动重连。\n"
            "如需继续使用，请重新启动一次 Siada-CLI。"
        ),
        email_mismatch_message=(
            "❌ Siada 连接被拒绝（4005 EMAIL_MISMATCH）：\n"
            "配置中填写的 email 与 IDaaS token 对应的身份不符。\n"
            "请检查 relay 配置中的 email 是否与当前登录账号一致，修复后重新启动 Siada-CLI。"
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
            "🆕 由于超过 {idle_minutes} 分钟没有新消息，已为你开启一个全新的会话。"
        ),
        resume_hint="如需回到上一个会话，请发送 `/resume {previous_sid}`",
        resume_hint_generic="使用 `/resume <session_id>` 可切换回之前的会话。",
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
        return f"设备：{device_info}\n版本：{version}"
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
        header_title="Siada 每日总结",
    )
