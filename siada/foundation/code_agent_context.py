from pydantic import BaseModel

class CodeAgentContext(BaseModel):
    root_dir: str | None = None