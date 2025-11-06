from pathlib import Path
from typing import List

from agents import RunContextWrapper, RunResult, RunResultStreaming, \
    TResponseInputItem

from siada.agent_hub.coder.prompt.card_prompt.card_prompt import get_system_prompt
from siada.agent_hub.siada_agent import SiadaAgent
from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.coder.prompt import card_prompt
from siada.foundation.setting import settings
from siada.tools.browser.browsergym_action_tool import browser_operate_by_gym
from siada.tools.browser.local_server_tool import start_local_html_server, stop_local_html_server
from siada.tools.cca.compile_card import compile_card
from siada.tools.cca.zip_project import zip_project
from siada.tools.coder.ask_followup_question import ask_followup_question
from siada.tools.coder.file_operator import edit
from siada.tools.coder.run_cmd import run_cmd
import logging


logging.getLogger().setLevel(logging.INFO)
class CardAgent(SiadaAgent[CodeAgentContext]):
    root_path = None

    def __init__(self, *args, **kwargs):
        self.root_path = self._check_cca_directory()

        super().__init__(
            name="CardAgent",
            tools=[edit, run_cmd, ask_followup_question, compile_card, zip_project, browser_operate_by_gym, start_local_html_server, stop_local_html_server],
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        # Get preferred language and agent name from session config
        preferred_language = run_context.context.session.siada_config.preferred_language
        agent_name = run_context.context.session.siada_config.agent_name
        system_prompt = get_system_prompt(self.root_path, preferred_language=preferred_language, agent_name=agent_name)
        return system_prompt

    async def get_context(self) -> CodeAgentContext:
        context = CodeAgentContext()
        return context


    def _check_cca_directory(self):
        """
        Find the directory path containing mindui-components folder
        
        Returns:
            Directory path containing mindui-components folder
        """
        current_path = Path.cwd()

        # Search upward from current directory
        for path in [current_path] + list(current_path.parents):
            cca_path = path / "mindui-components"
            if cca_path.exists() and cca_path.is_dir():
                return str(cca_path)

        # If not found, execute get_cca_resource and return current working directory
        return str(current_path)

    def assemble_user_input(
            self, user_input: str | List[TResponseInputItem], context: CodeAgentContext
    ) -> any:
        if isinstance(user_input, list):
            return user_input
        task = f"<task>\n{user_input}\n</task>\n\n【Development Directory Path: {self.root_path}】"
        return task

    async def run(self, user_input: str| List[TResponseInputItem], context: CodeAgentContext) -> RunResult:
        input_with_env = self.assemble_user_input(user_input, context)
        result = await self.run_impl(
            starting_agent=self,
            input=input_with_env,
            max_turns=settings.MAX_TURNS,
            context=context,
        )

        return result

    async def run_streamed(
            self, user_input: str| List[TResponseInputItem], context: CodeAgentContext
    ) -> RunResultStreaming:
        """
        Execute code generation task with streaming output.

        Args:
            user_input: User's code generation request with requirements and specifications
            context: Context object providing project information
        Returns:
            A streaming result of the generation, containing final output and execution details.
        """

        input_with_env = self.assemble_user_input(user_input, context)

        result = await self.run_streamed_impl(
            starting_agent=self,
            input=input_with_env,
            context=context,
            max_turns=settings.MAX_TURNS,
        )

        return result


async def main():
    agent = CardAgent()
    context = await agent.get_context()
    await agent.run_streamed("？", context)


if __name__ == '__main__':
    import asyncio
    import warnings

    warnings.filterwarnings("ignore")
    asyncio.run(main())
