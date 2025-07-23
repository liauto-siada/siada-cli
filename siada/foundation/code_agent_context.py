from pydantic import BaseModel

from siada.session.session_models import Session

class CodeAgentContext(BaseModel):
    
    root_dir: str | None = None

    session: Session | None = None