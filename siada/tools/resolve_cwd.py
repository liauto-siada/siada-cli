"""CWD resolution utility for mode-aware tool execution."""

from agents import RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext


def resolve_cwd(context: RunContextWrapper[CodeAgentContext], model_cwd: str | None) -> str:
    """Resolve effective cwd based on running mode.

    - IM mode: allow model-specified cwd, fallback to root_dir
    - Non-IM mode (TUI): always force root_dir, model input is ignored
    """
    if model_cwd:
        return model_cwd
    return context.context.root_dir
