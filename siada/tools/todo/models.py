from typing import List, Literal
from pydantic import AliasChoices, BaseModel, Field


class TodoItem(BaseModel):
    content: str        # imperative form, e.g. "Fix authentication bug"
    active_form: str = Field(validation_alias=AliasChoices("active_form", "activeForm"))
    status: Literal["pending", "in_progress", "completed"]


TodoList = List[TodoItem]
