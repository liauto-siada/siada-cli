from typing import List, Literal
from pydantic import BaseModel


class TodoItem(BaseModel):
    content: str        # imperative form, e.g. "Fix authentication bug"
    active_form: str    # present continuous, e.g. "Fixing authentication bug"
    status: Literal["pending", "in_progress", "completed"]


TodoList = List[TodoItem]
