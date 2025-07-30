from typing import Optional
from pydantic import BaseModel, ConfigDict

from siada.session.session_models import RunningSession

class CodeAgentContext(BaseModel):
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    root_dir: Optional[str] = None

    session: Optional[RunningSession] = None