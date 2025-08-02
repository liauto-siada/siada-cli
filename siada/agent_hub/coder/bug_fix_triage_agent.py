from agents import Agent, Runner, RunContextWrapper, TContext, RunResult
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

from siada.foundation.config import settings
from siada.provider.li.li_provider import LiProvider


class BugFixTriageAgent(Agent):

    def __init__(self, *args, **kwargs):
        provider = LiProvider()
        model = provider.get_model(settings.Claude_4_0_SONNET)
        instructions = (
            f"{RECOMMENDED_PROMPT_PREFIX} "
            "You are a helpful triaging agent. You can use your tools to delegate the task to other appropriate agents."
            "The BugFixAgent fixes issues, and the TestAgent verifies the fixes. If verification fails, the BugFixAgent continues fixing until the issue is resolved."
            "Your job is to assign tasks to the appropriate agent at each stage."
        ),

        super().__init__(
            name="BugFixTriageAgent",
            handoff_description="A triage agent that can delegate the bug fix task to the appropriate agent.",
            model=model,
            instructions=instructions,
            *args,
            **kwargs
        )

    @staticmethod
    def run_triage(result: RunResult, task: str) -> RunResult:
        pass




