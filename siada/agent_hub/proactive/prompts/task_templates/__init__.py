"""
Task instruction templates for ProactiveAgent.

These templates are used by the scheduling system to instruct
the ProactiveAgent to perform specific proactive tasks.
"""

from siada.agent_hub.proactive.prompts.task_templates.discover_tasks import get_discover_tasks_instruction
from siada.agent_hub.proactive.prompts.task_templates.personal_style import get_update_personal_style_instruction
from siada.agent_hub.proactive.prompts.task_templates.daily_summary import get_daily_summary_instruction
from siada.agent_hub.proactive.prompts.task_templates.recent_task import get_recent_task_instruction
# from siada.agent_hub.proactive.prompts.task_templates.work_plan import WORK_PLAN_INSTRUCTION

__all__ = [
    "get_discover_tasks_instruction",
    "get_update_personal_style_instruction",
    "get_daily_summary_instruction",
    "get_recent_task_instruction",
    # "WORK_PLAN_INSTRUCTION",
]
