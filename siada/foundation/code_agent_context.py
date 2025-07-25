from typing import Optional
from pydantic import BaseModel, ConfigDict

from siada.session.session_models import Session

class CodeAgentContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    root_dir: Optional[str] = None

    session: Optional[Session] = None