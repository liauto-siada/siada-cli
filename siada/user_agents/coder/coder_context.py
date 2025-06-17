from pydantic import BaseModel


class CoderAgentContext(BaseModel):
    root_dir: str | None = None
