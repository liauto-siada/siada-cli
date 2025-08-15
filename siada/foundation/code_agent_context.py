from typing import Optional
from pydantic import BaseModel, ConfigDict

from siada.session.session_models import RunningSession
from typing import List
from agents import TResponseInputItem
from pydantic import BaseModel, Field


class CodeAgentContext(BaseModel):

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session: Optional[RunningSession] = None

    root_dir: str | None = None

    provider: str | None = None

    # 交互模式标识，True为交互模式，False为非交互模式
    interactive_mode: bool = True

    # 完整的消息历史列表
    message_history: List[TResponseInputItem] = Field(default_factory=list)

    def add_message(self, message: TResponseInputItem) -> None:
        self.message_history.append(message)

    def add_messages(self, messages: List[TResponseInputItem]) -> None:
        self.message_history.extend(messages)

    def remove_old_messages(self, remove_count: int) -> List[TResponseInputItem]:
        """删除旧消息，返回剩余的消息列表，永远保留第一条消息"""
        if remove_count <= 0:
            return self.message_history.copy()

        # 如果历史记录为空或只有一条消息，不删除任何消息
        if len(self.message_history) <= 1:
            return self.message_history.copy()

        # 计算实际可删除的消息数量（保留第一条消息）
        max_removable = len(self.message_history) - 1
        actual_remove_count = min(remove_count, max_removable)

        # 删除第1条消息之后的N条消息（索引1到1+actual_remove_count）
        # 保留第一条消息和剩余的消息
        self.message_history = [self.message_history[0]] + self.message_history[1 + actual_remove_count:]
        return self.message_history.copy()
