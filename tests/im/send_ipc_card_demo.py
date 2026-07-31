"""Demo script to send IPC notification card to a Feishu user by email.

Usage:
    poetry run python tests/im/send_ipc_card_demo.py [email] [language]

Default email: zhangmeng20@lixiang.com
Default language: zh-CN
"""

import json
import sys

import lark_oapi as lark
from lark_oapi.api.contact.v3 import (
    BatchGetIdUserRequest,
    BatchGetIdUserRequestBody,
)
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
)

from siada.im.feishu.ipc_handler import build_ipc_notification_card

# Credentials
APP_ID = "cli_xxxxx"
APP_SECRET = "xxxxx"
DEFAULT_EMAIL = "xxx@lixiang.com"


def main():
    email = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMAIL
    preferred_language = sys.argv[2] if len(sys.argv) > 2 else "zh-CN"

    # Build card
    card = build_ipc_notification_card(
        content=(
            "这是一条来自 **代码生成** 任务的跨会话消息。\n\n"
            "文件已生成：\n"
            "- `src/main.py`\n"
            "- `src/utils.py`"
        ),
        source_session_id="feishu_direct_ou_abc123def456_oc_xyz789_1713000000000",
        current_session_id="feishu_direct_ou_0731f7e587fe_oc_b28d25f3124a_1713099999000",
        preferred_language=preferred_language,
    )

    print(f"Using preferred_language={preferred_language}")

    # Create client
    client = (
        lark.Client.builder()
        .app_id(APP_ID)
        .app_secret(APP_SECRET)
        .domain(lark.FEISHU_DOMAIN)
        .build()
    )

    # Resolve open_id from email
    resolve_req = (
        BatchGetIdUserRequest.builder()
        .user_id_type("open_id")
        .request_body(
            BatchGetIdUserRequestBody.builder()
            .emails([email])
            .include_resigned(False)
            .build()
        )
        .build()
    )
    resolve_resp = client.contact.v3.user.batch_get_id(resolve_req)
    if not resolve_resp.success():
        print(f"Failed to resolve email: {resolve_resp.code} {resolve_resp.msg}")
        return

    user_list = resolve_resp.data.user_list if resolve_resp.data else []
    if not user_list or not user_list[0].user_id:
        print(f"No user found for email: {email}")
        return

    open_id = user_list[0].user_id
    print(f"Resolved open_id={open_id} from email={email}")

    # Send card
    msg_req = (
        CreateMessageRequest.builder()
        .receive_id_type("open_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(open_id)
            .msg_type("interactive")
            .content(json.dumps(card, ensure_ascii=False))
            .build()
        )
        .build()
    )
    msg_resp = client.im.v1.message.create(msg_req)
    if msg_resp.success():
        print(f"Card sent! message_id={msg_resp.data.message_id}")
    else:
        print(f"Send failed: {msg_resp.code} {msg_resp.msg}")


if __name__ == "__main__":
    main()
