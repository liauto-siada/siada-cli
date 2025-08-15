from agents import Agent, RunContextWrapper, RunHooks, Runner, TContext, Tool
from siada.foundation.code_agent_context import CodeAgentContext



class IoRunHooks(RunHooks):


    def __init__(self):
        super().__init__()

    async def on_tool_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
    ) -> None:
        ## implements until this function args contains arguments
        pass

    async def on_tool_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
        result: str,
    ) -> None:
        pass


