import os

from agents import RunContextWrapper, RunConfig, RunResult, RunResultStreaming, Runner, add_trace_processor

from siada.agent_hub.coder.bug_reproduce_agent import BugReproduceAgent
from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.test_agent import TestAgent
from siada.agent_hub.coder.prompt.bug_prompt import bug_fix_prompt
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.config import settings
from siada.provider.li.li_provider import SiadaProvider
from siada.tools.ast.ast_tool import list_code_definition_names
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.fix_attempt_completion import fix_attempt_completion
from agents import set_trace_processors
from siada.agent_hub.coder.tracing import create_detailed_logger
import json


class BugFixAgent(CodeGenAgent):
    test_agent: TestAgent

    def __init__(self, *args, **kwargs):
        provider = SiadaProvider()
        model = provider.get_model(settings.Claude_4_0_SONNET)

        self.test_agent = TestAgent()

        super().__init__(
            name="BugFixAgent",
            tools=[edit, regex_search_files, run_cmd, fix_attempt_completion, list_code_definition_names],
            model=model,
            tool_use_behavior={
                "stop_at_tool_names": ["fix_attempt_completion"],
            },
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        system_prompt = bug_fix_prompt.get_system_prompt(root_dir)
        return system_prompt


    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        context = CodeAgentContext(root_dir=current_working_dir)
        return context

    async def run(self, user_input: str, context: CodeAgentContext) -> RunResult:
        """
        Execute bug fixing task.
        Use reproduce_agent to reproduce the issue, then use current Agent to fix it.

        Args:
            user_input: User-described bug problem, including error messages, related file paths, etc.
            context: Context object for providing contextual information
        Returns:
            Fix result, including final output, execution rounds, and other information
        """
        config = RunConfig(tracing_disabled=False)
        set_trace_processors([create_detailed_logger()])
        input_with_env = self.assemble_user_input(user_input, context)

        max_turns = 3
        current_turn = 0
        current_agent_name = self.name
        task_message = {"content": input_with_env, "role": "user"}
        input_list = [task_message]

        while current_turn < max_turns:
            # Run BugFixAgent for fixing
            result = await Runner.run(
                starting_agent=self,
                input=input_list,
                max_turns=settings.MAX_TURNS,
                run_config=config,
                context=context
            )

            input_list = result.to_input_list()

            if current_agent_name == self.name:
                # Run TestAgent for testing
                test_result = await Runner.run(
                    starting_agent=self.test_agent,
                    input=input_list,
                    max_turns=settings.MAX_TURNS,
                    run_config=config,
                    context=context
                )

                # Parse test results
                try:
                    # test_result.final_output should contain JSON data returned by test_completion
                    if isinstance(test_result.final_output, dict):
                        test_output = test_result.final_output
                    else:
                        test_output = json.loads(test_result.final_output)

                    is_passed = test_output.get("is_passed", 0)
                    test_detail = test_output.get("test_detail", "")

                    if is_passed == 1:
                        # Test passed, break the loop
                        print(f"Test passed: {test_detail}")
                        break
                    else:
                        # Test failed, continue to next round of fixing
                        print(f"Test failed, continue fixing (round {current_turn + 1}): {test_detail}")
                        # Update input with test failure information for next round of fixing
                        input_list = result.to_input_list()

                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    # Parsing failed, log error and continue to next round
                    print(f"Failed to parse test results: {e}, continue to next round of fixing")

            current_turn += 1

        return result

    def run_streamed(self, user_input: str, context: CodeAgentContext) -> RunResultStreaming:
        """
        Execute bug fixing task in streaming mode

        Args:
            user_input: User-described bug problem, including error messages, related file paths, etc.
            context: Context object for providing contextual information
        Returns:
            Fix result, including final output, execution rounds, and other information
        """
        pass
