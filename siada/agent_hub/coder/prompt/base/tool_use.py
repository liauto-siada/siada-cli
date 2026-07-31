"""Build the TOOL USE section of the system prompt.

The rendered text varies by model family:

- GPT-5 series: native parallel tool calls -> aggressive parallel guidance
  (includes an explicit call-out of IO-heavy tools).
- Claude (with ``parallel_tool_calls`` flag on): parallel guidance only.
- Others: sequential mode ("one tool per message").

Public API is kept backward-compatible with earlier call sites:

- :func:`get_tool_use_section`
- :func:`should_enable_parallel_tool_calls_in_prompt`
- :func:`get_objective_step2` — shared OBJECTIVE step-2 sentence that stays
  in sync with the TOOL USE section across all coder prompts.
"""

import logging
from enum import Enum
from typing import Optional

from siada.foundation.log_category import LogCategory

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Internal rendering mode
# --------------------------------------------------------------------------- #

class _ParallelMode(Enum):
    """Rendering branch selector for the TOOL USE body.

    Centralizes the (model, config) -> branch decision so the renderer never
    has to re-check model names.
    """

    SEQUENTIAL = "sequential"              # default: one tool per message
    PARALLEL = "parallel"                  # e.g. Claude with parallel flag on
    PARALLEL_AGGRESSIVE = "parallel_gpt5"  # GPT-5 series (extra tool-name hint)


# --------------------------------------------------------------------------- #
# Text fragments — single source of truth for easier diff / maintenance
# --------------------------------------------------------------------------- #

# Shared base description for parallel-capable branches (previously duplicated
# between the GPT-5 branch and the Claude branch).
_BASE_PARALLEL_DESC = (
    "You can call multiple tools in a single response."
    " If you intend to call multiple tools and there are no dependencies between them,"
    " make all independent tool calls in parallel."
    " Maximize use of parallel tool calls where possible to increase efficiency."
    " However, if some tool calls depend on previous calls to inform dependent values,"
    " do NOT call these tools in parallel and instead call them sequentially."
    " For instance, if one operation must complete before another starts,"
    " run these operations sequentially instead."
)

# GPT-5 only: explicitly point out IO-heavy tools that benefit from parallelism.
# Preserved verbatim from the original inline string to keep model behavior stable.
_GPT5_EXTRA = (
    "\n\n"
    "Parallelize tool calls whenever possible — especially file operations, such as"
    " `edit`, `regex_search_files`, `list_code_definition_names`, `run_cmd`."
    " This significantly speeds up IO-intensive operations."
)

# Detailed guidance for independent operations (appended to parallel branches).
# The last bullet is a safety-net because other prompt sections
# (rules.py / capabilities.py) may still contain "one tool at a time" phrasing.
_PARALLEL_GUIDANCE = (
    "\n\n"
    # "Guidance for parallel tool calls (applies whenever operations are independent):"
    # "\n- Operations are independent if they do not depend on each other's outputs"
    # " (e.g., reading multiple files, searching different patterns, listing unrelated directories)."
    # "\n- When possible, decompose the task into independent sub-tasks before selecting tools,"
    # " then complete them in a single turn with parallel tool calls rather than across multiple turns."
    # "\n- Before calling tools, quickly determine whether multiple independent operations can be"
    # " executed together; if yes, issue them in one response."
    # "\n- Prefer completing independent operations in a single turn using parallel tool calls,"
    # " even if multiple tools are needed — fewer turns is more efficient than fewer tool calls per turn."
    # "\n- Using multiple tools in parallel for independent operations is NOT considered"
    # " over-engineering; it is the preferred, efficient behavior."
    # "\n- This guidance takes priority over any later phrasing that could be read as"
    # " 'use tools one at a time' for independent operations."
)

# Sequential branch (models that don't / shouldn't use parallel calls).
_SEQUENTIAL_DESC = (
    "You have access to a set of tools. You can use one tool per message,"
    " and will receive the execution results of the tool."
    " You use tools step-by-step to accomplish a given task,"
    " with each tool use informed by the result of the previous tool use."
)

_OUTER_TEMPLATE = """====

TOOL USE

{body}

===="""


# --------------------------------------------------------------------------- #
# OBJECTIVE step-2 fragments — shared across all coder prompt files
# --------------------------------------------------------------------------- #
#
# The OBJECTIVE section in every coder prompt (`bug_reproduce_prompt.py`,
# `bug_fix_prompt.py`, `fe_gen_prompt.py`, `issue_review_prompt.py`,
# `test_prompt.py`, `code_gen_prompt.py`) contains a step-2 sentence that must
# stay semantically consistent with the TOOL USE body above. Hard-coding a
# parallel-flavored sentence there would contradict the sequential TOOL USE
# body when the model runs in sequential mode, so the wording is derived from
# the same ``enable_parallel_tool_calls`` flag here.
#
# Two styles are provided to cover the existing variants used across call
# sites; add new styles here rather than re-introducing divergent wording in
# individual prompt files.

# Default wording — used by bug_reproduce, bug_fix, fe_gen, issue_review, test.
_OBJECTIVE_STEP2_DEFAULT_PARALLEL = (
    "Work through these goals sequentially, utilizing available tools efficiently, "
    "preferring parallel tool calls for independent operations. "
    "Each goal should correspond to a distinct step in your problem-solving process."
)
_OBJECTIVE_STEP2_DEFAULT_SEQUENTIAL = (
    "Work through these goals sequentially, utilizing available tools one at a time as necessary. "
    "Each goal should correspond to a distinct step in your problem-solving process."
)

# Extended wording — used by code_gen_prompt.OBJECTIVE. Adds the tail sentence
# "You will be informed on the work completed and what's remaining as you go."
# which is already part of the agent's interaction contract and should be kept
# regardless of the tool-call mode.
_OBJECTIVE_STEP2_EXTENDED_PARALLEL = (
    "Work through these goals sequentially, utilizing available tools as necessary. "
    "You may call multiple independent tools in a single response to work efficiently. "
    "Each goal should correspond to a distinct step in your problem-solving process. "
    "You will be informed on the work completed and what's remaining as you go."
)
_OBJECTIVE_STEP2_EXTENDED_SEQUENTIAL = (
    "Work through these goals sequentially, utilizing available tools one at a time as necessary. "
    "Each goal should correspond to a distinct step in your problem-solving process. "
    "You will be informed on the work completed and what's remaining as you go."
)

_OBJECTIVE_STEP2_STYLES = {
    "default": (_OBJECTIVE_STEP2_DEFAULT_PARALLEL, _OBJECTIVE_STEP2_DEFAULT_SEQUENTIAL),
    "extended": (_OBJECTIVE_STEP2_EXTENDED_PARALLEL, _OBJECTIVE_STEP2_EXTENDED_SEQUENTIAL),
}


def get_objective_step2(
    enable_parallel_tool_calls: bool = False,
    style: str = "default",
) -> str:
    """Return the OBJECTIVE step-2 sentence, adapted to the active tool mode.

    All coder prompt files should call this helper instead of hard-coding the
    sentence so that the OBJECTIVE stays consistent with the TOOL USE body
    rendered by :func:`get_tool_use_section`.

    Args:
        enable_parallel_tool_calls: Same flag passed to
            :func:`get_tool_use_section`. When True the caller will receive a
            parallel-flavored sentence; otherwise a sequential one.
        style: Wording variant. ``"default"`` matches the phrasing used by
            the majority of prompts; ``"extended"`` appends the extra sentence
            used by the code-generation prompt ("You will be informed ...").

    Returns:
        The plain-text sentence (no leading list marker, no trailing newline).
        Callers are responsible for prefixing it with ``"2. "`` and any
        indentation required by the surrounding OBJECTIVE block.

    Raises:
        ValueError: If ``style`` is not a known variant.
    """
    try:
        parallel_text, sequential_text = _OBJECTIVE_STEP2_STYLES[style]
    except KeyError as exc:
        raise ValueError(
            f"Unknown OBJECTIVE step-2 style: {style!r}. "
            f"Valid styles: {sorted(_OBJECTIVE_STEP2_STYLES)}"
        ) from exc
    return parallel_text if enable_parallel_tool_calls else sequential_text


# --------------------------------------------------------------------------- #
# Mode selection & rendering
# --------------------------------------------------------------------------- #

def _resolve_mode(
    enable_parallel_tool_calls: bool,
    model_name: Optional[str],
) -> _ParallelMode:
    """Decide which rendering branch to use.

    GPT-5 has native parallel support, so it takes precedence regardless of
    the ``enable_parallel_tool_calls`` flag (which historically applied only
    to Claude).
    """
    from .gpt5_instructions import is_gpt5_model

    if is_gpt5_model(model_name):
        return _ParallelMode.PARALLEL_AGGRESSIVE
    if enable_parallel_tool_calls:
        return _ParallelMode.PARALLEL
    return _ParallelMode.SEQUENTIAL


def _render_body(mode: _ParallelMode) -> str:
    """Map a mode to its body text."""
    if mode is _ParallelMode.PARALLEL_AGGRESSIVE:
        return _BASE_PARALLEL_DESC + _GPT5_EXTRA + _PARALLEL_GUIDANCE
    if mode is _ParallelMode.PARALLEL:
        return _BASE_PARALLEL_DESC + _PARALLEL_GUIDANCE
    return _SEQUENTIAL_DESC


# --------------------------------------------------------------------------- #
# Public API (signatures preserved for backward compatibility)
# --------------------------------------------------------------------------- #

def get_tool_use_section(
    enable_parallel_tool_calls: bool = False,
    model_name: Optional[str] = None,
) -> str:
    """Render the TOOL USE section of the system prompt.

    Args:
        enable_parallel_tool_calls: Whether to emit parallel-call guidance.
            **Ignored for GPT-5 models**, which always receive aggressive
            parallel guidance (native support).
        model_name: Model name used to detect GPT-5 series.

    Returns:
        The fully-formatted TOOL USE section (including ``====`` delimiters).
    """
    mode = _resolve_mode(enable_parallel_tool_calls, model_name)
    return _OUTER_TEMPLATE.format(body=_render_body(mode))


def should_enable_parallel_tool_calls_in_prompt(run_context) -> bool:
    """Determine whether parallel tool-call guidance should be injected.

    Returns True for:
    - GPT-5 models (native parallel tool calls), regardless of config.
    - Any other model whose effective ``llm_config.parallel_tool_calls`` is
      truthy. That flag originates from the model's
      :class:`~siada.models.model_base_config.ModelBaseConfig.parallel_tool_calls`
      capability and is then optionally overridden by CLI
      (``--parallel-tool-calls`` / ``--no-parallel-tool-calls``) or
      ``~/.siada-cli/conf.yaml`` ``llm_config.parallel_tool_calls`` in the
      :mod:`siada.entrypoint.helpers.model_setup` pipeline. In other words,
      declaring ``parallel_tool_calls=True`` on a ``ModelBaseConfig`` entry
      is sufficient to make this function return True for that model — no
      additional model-name hard-coding required.

    Any missing attribute on ``run_context`` causes a fallback to False so
    prompt building never breaks.
    """
    try:
        from .gpt5_instructions import is_gpt5_model
        from siada.foundation.context import get_context_var, LLM_CONFIG

        llm_config = get_context_var(LLM_CONFIG)
        if llm_config is None:
            return False

        model_name = llm_config.model_name

        # GPT-5 models always support parallel tool calls natively.
        if is_gpt5_model(model_name):
            return True

        # Single source of truth for every other model: the effective
        # parallel_tool_calls flag carried on llm_config.
        return bool(llm_config.parallel_tool_calls)
    except (AttributeError, TypeError) as e:
        logger.error(
            "Failed to resolve parallel tool calls flag from run_context; falling back to False. Error: %s",
            e,
            exc_info=True,
            extra={'log_category': LogCategory.MODEL_ERROR},
        )
        return False
