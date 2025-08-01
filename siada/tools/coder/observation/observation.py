from dataclasses import dataclass
from enum import Enum

class ObservationType(str, Enum):
    READ = 'read'
    """The content of a file
    """

    WRITE = 'write'

    EDIT = 'edit'

    BROWSE = 'browse'
    """The HTML content of a URL
    """

    RUN = 'run'
    """The output of a command
    """

    RUN_IPYTHON = 'run_ipython'
    """Runs a IPython cell.
    """

    CHAT = 'chat'
    """A message from the user
    """

    DELEGATE = 'delegate'
    """The result of a task delegated to another agent
    """

    MESSAGE = 'message'

    ERROR = 'error'

    SUCCESS = 'success'

    NULL = 'null'

    THINK = 'think'

    AGENT_STATE_CHANGED = 'agent_state_changed'

    USER_REJECTED = 'user_rejected'

    CONDENSE = 'condense'
    """Result of a condensation operation."""

    RECALL = 'recall'
    """Result of a recall operation. This can be the workspace context, a microagent, or other types of information."""

    MCP = 'mcp'
    """Result of a MCP Server operation"""


class FileReadSource(str, Enum):
    OH_ACI = 'oh_aci'  # openhands-aci
    DEFAULT = 'default'

class FileEditSource(str, Enum):
    LLM_BASED_EDIT = 'llm_based_edit'
    OH_ACI = 'oh_aci'  # openhands-aci


@dataclass
class FunctionCallResult:
    content: str

    def format_for_display(self) -> str:
        return self.__str__()
