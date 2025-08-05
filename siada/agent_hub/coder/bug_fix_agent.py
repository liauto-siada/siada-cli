import ast
import os

from agents import RunContextWrapper, RunConfig, RunResult, RunResultStreaming, Runner

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.issue_review_agent import IssueReviewAgent
from siada.agent_hub.coder.prompt.bug_prompt import bug_fix_prompt
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.config import settings
from siada.foundation.tools.get_git_diff import GitDiffUtil
from siada.services.fix_result_check import FixResultChecker
from siada.tools.ast.ast_tool import list_code_definition_names
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.fix_attempt_completion import fix_attempt_completion



class BugFixAgent(CodeGenAgent):
    fix_result_checker: FixResultChecker
    issue_review_agent: IssueReviewAgent  # Forward declaration for type hinting

    def __init__(self, *args, **kwargs):

        self.fix_result_checker = FixResultChecker()
        self.issue_review_agent = IssueReviewAgent()

        super().__init__(
            name="BugFixAgent",
            tools=[edit, regex_search_files, run_cmd, fix_attempt_completion, list_code_definition_names],
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

        # 将 context 值赋给 model 对象
        if hasattr(self, 'model') and hasattr(self.model, 'context'):
            self.model.context = context

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
        #config = RunConfig(tracing_disabled=False)
        #set_trace_processors([create_detailed_logger()])
        input_with_env = self.assemble_user_input(user_input, context)

        max_turns = 5
        current_turn = 0
        task_message = {"content": input_with_env, "role": "user"}
        input_list = [task_message]

        while current_turn < max_turns:
            # Run BugFixAgent for fixing
            result = await self.run_impl(
                starting_agent=self,
                input=input_list,
                max_turns=settings.MAX_TURNS,
                context=context
            )

            # input_list = result.to_input_list()

            # Check if the issue is fixed using run_checker
            try:
                check_result = await self.run_checker_by_agent(user_input, context)
                
                if check_result.get("is_fixed", False):
                    # Issue is fixed, break the loop
                    print(f"Fix_check_result, Issue fixed: {check_result.get('check_summary', 'Fix verified')}")
                    break
                else:
                    # Issue not fixed, add the check_summary to input_list for next iteration
                    check_summary = check_result.get("check_summary", "Fix verification failed")
                    print(f"Fix_check_result, Issue not fixed, continue fixing (round {current_turn + 1}): {check_summary}")

                    # Add the unfixed check_summary to input_list for next round
                    feedback_message = {
                        "content": f"Here is the previous fix logic:\n{result.final_output}"
                                   f"Here is the current code diff:\n{check_result.get('code_diff', '')}"
                                   f"But previous fix attempt was not sufficient. Reason: {check_summary}.\n"
                                   f"**Please continue fixing.**",
                        "role": "user"
                    }
                    input_list = [task_message, feedback_message]
            except Exception as e:
                # If checker fails, log error and continue to next round
                print(f"Fix result checker failed: {e}, stopping verification.")
                break

            current_turn += 1

        return result

    async def run_checker_by_agent(self, user_input: str, context: CodeAgentContext):

        result = await self.issue_review_agent.run(user_input, context)

        output = ast.literal_eval(result.final_output)
        return output


    async def run_checker(self, user_input: str, context: CodeAgentContext) -> dict:

        diff_patch = GitDiffUtil.get_git_diff_exclude_test_files(context.root_dir)

        check_result = await self.fix_result_checker.check(
            issue_desc=user_input,
            fix_code=diff_patch,
            context=context
        )

        check_result["code_diff"] = diff_patch
        return check_result

        # return {
        #     "is_fixed": False,
        #     "check_summary": "没有考虑长字符串场景",
        #     "analysis": "未提供分析说明",
        #     "code_diff": diff_patch
        # }




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
