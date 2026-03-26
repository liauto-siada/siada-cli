"""
Proactive Agent Prompts

Contains:
- system_prompt: The general system prompt for ProactiveAgent
- task_templates: Specific task instruction templates for different proactive tasks
"""

from siada.agent_hub.proactive.prompts.system_prompt import PROACTIVE_SYSTEM_PROMPT
from siada.agent_hub.proactive.prompts.task_templates import (
    get_discover_tasks_instruction,
    get_update_personal_style_instruction,
    get_daily_summary_instruction,
    get_recent_task_instruction,
    # WORK_PLAN_INSTRUCTION,
)

__all__ = [
    "PROACTIVE_SYSTEM_PROMPT",
    "get_discover_tasks_instruction",
    "get_update_personal_style_instruction",
    "get_daily_summary_instruction",
    "get_recent_task_instruction",
    # "WORK_PLAN_INSTRUCTION",
]
