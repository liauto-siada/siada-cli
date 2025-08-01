from dataclasses import dataclass

from siada.tools.coder.observation.observation import FunctionCallResult


@dataclass
class ErrorObservation(FunctionCallResult):
    """This data class represents an error encountered by the agent.

    This is the type of error that LLM can recover from.
    E.g., Linter error after editing a file.
    """

    observation: str = 'error'
    error_id: str = ''

    @property
    def message(self) -> str:
        return self.content

    def __str__(self) -> str:
        return f'**ErrorObservation**\n{self.content}'
