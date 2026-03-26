from dataclasses import dataclass
from typing import Optional

from siada.tools.coder.observation.observation import FunctionCallResult
import token


@dataclass
class ErrorObservation(FunctionCallResult):
    """This data class represents an error encountered by the agent.

    This is the type of error that LLM can recover from.
    E.g., Linter error after editing a file.
    """

    observation: str = 'error'
    error_id: str = ''
    display_content : Optional[str] = None

    @property
    def message(self) -> str:
        return self.content
    
    def format_for_display(self) -> str:
        if self.display_content:
            return self.display_content
        return f"✗ Error encountered. Details: {self.content}"

    def __str__(self) -> str:
        return f'**ErrorObservation**\n{self.content}'
