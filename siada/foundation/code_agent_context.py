from typing import Optional
from pydantic import BaseModel

from siada.session.session_models import Session

class CodeAgentContext(BaseModel):
    
    root_dir: Optional[str] = None

    session: Optional[Session] = None