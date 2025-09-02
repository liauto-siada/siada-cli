import ast
from datetime import datetime
import os

from agents import RunContextWrapper, RunResult, RunResultStreaming, Runner

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.select_agent import SelectAgent
from siada.agent_hub.coder.prompt.bug_prompt import bug_fix_prompt
from siada.agent_hub.coder.tracing.bug_fix_trace_collector import BugFixTraceCollector,create_custom_bug_fix_trace_collector
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.setting import settings
from siada.foundation.tools.get_git_diff import GitDiffUtil
from siada.services.bug_desc_optimizer import BugDescOptimizer
from siada.services.fix_result_check import FixResultChecker
from siada.services.issue_type_checker import IssueTypeChecker
from siada.services.execution_trace_collector import ExecutionTrace, ModelCall, ToolCall
from siada.services.strict_fix_result_check import StrictFixResultChecker
from siada.tools.ast.ast_tool import list_code_definition_names
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.fix_attempt_completion import fix_attempt_completion
from siada.services.enhanced_fix_result_check import EnhancedFixResultChecker
from typing import Optional, List, Dict, Any
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage
import json
from agents import add_trace_processor

class BugFixAgent(CodeGenAgent):
    fix_result_checker: FixResultChecker
    strict_fix_result_checker: StrictFixResultChecker
    bug_desc_optimizer: BugDescOptimizer
    enhanced_fix_result_checker: EnhancedFixResultChecker
    is_minimal: bool = False
    def __init__(self, *args, **kwargs):

        self.fix_result_checker = FixResultChecker()
        self.strict_fix_result_checker = StrictFixResultChecker()
        self.enhanced_fix_result_checker = EnhancedFixResultChecker()
        self.bug_desc_optimizer = BugDescOptimizer()
        self.guidance=""
        self.code_patch_list = []
        self.select_agent = SelectAgent()

        self.trace_collector = create_custom_bug_fix_trace_collector()

        super().__init__(
            name="BugFixAgent",
            tools=[edit, regex_search_files, run_cmd, fix_attempt_completion, list_code_definition_names],
            tool_use_behavior={
                "stop_at_tool_names": ["fix_attempt_completion"],
            },
            *args,
            **kwargs,
        )

    async def get_system_prompt(
        self, run_context: RunContextWrapper[CodeAgentContext]
    ) -> str | None:
        root_dir = run_context.context.root_dir
        # Get user memory from context
        user_memory = run_context.context.user_memory
        system_prompt = bug_fix_prompt.get_system_prompt(root_dir, is_minimal=self.is_minimal, new_rule=self.guidance, user_memory=user_memory)
        return system_prompt

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        context = CodeAgentContext(root_dir=current_working_dir)

        if hasattr(self, "model") and hasattr(self.model, "context"):
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

        run_config, _ = await self.prepare_run_config_and_session(context)
        add_trace_processor(self.trace_collector)


        print(f"\nStarting bug desc optimize")
        opt_user_input = await self.bug_desc_optimizer.optimize(description=user_input, context=context, trace_collector=self.trace_collector)
        print(f"Bug desc optimize result:{opt_user_input}\n")

        input_with_env = self.struct_user_input(opt_user_input)
        max_turns = 3
        current_turn = 0
        task_message = {"content": input_with_env, "role": "user"}
        input_list = [task_message]

        print(f"2. Issue fix stage: (1) Propose fix; (2) Verify fix; (3) Confirm fix")


        while current_turn < max_turns:
            self.is_minimal = current_turn >= 3
            print(f"\n Fix round {current_turn+1}")

            self.trace_collector.start_run_round([
                {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                for msg in input_list
            ])

            result = await Runner.run(
                starting_agent=self,
                input=input_list,
                max_turns=settings.MAX_TURNS,
                run_config=run_config,
                context=context,
            )

            self.trace_collector.end_run_round(str(result.final_output))

            try:
                should_break, conbine_task_message_with_check_summary = await self.check(
                    opt_user_input, result, context, task_message, current_turn
                )
                if should_break:
                    break
                else:
                    input_list = conbine_task_message_with_check_summary
            
            except Exception as e:
                print(f"Fix result checker failed: {e}, stopping verification.")
                break

            current_turn += 1

        self.trace_collector.collect_submission_diff(context)

        trace_path_v2 = self.trace_collector.export_to_json("trace_test.json")
        print(f"successfully export v2 format: {trace_path_v2}")

        return result

    def test_best_patch_selection(self, context: CodeAgentContext) -> bool:
        self.trace_collector.load_from_json(f"/siada-agenthub/trace_test.json")
        patch_list=self.trace_collector.trace_session.patch_selection.input_patches
        self.select_agent._apply_selected_patch(patch_list[1], context)

    def struct_user_input(self, user_input: str) -> str:
        task = f"""
                **Issue Description:**
                <task>
                {user_input}
                </task>
                """

        return task

    async def run_checker_by_agent(self, user_input: str, context: CodeAgentContext):

        result = await self.issue_review_agent.run(user_input, context)

        output = ast.literal_eval(result.final_output)
        return output

    async def run_checker(self, user_input: str, context: CodeAgentContext, trace_collector: Optional[BugFixTraceCollector] = None) -> dict:

        diff_patch = GitDiffUtil.get_git_diff_exclude_test_files(context.root_dir)

        check_result = await self.fix_result_checker.check(
            issue_desc=user_input,
            fix_code=diff_patch,
            context=context,
            trace_collector=trace_collector
        )

        check_result["code_diff"] = diff_patch
        return check_result

    async def run_enhanced_checker(
        self,
        user_input: str,
        context: CodeAgentContext,
        run_result: Optional[RunResult] = None,
    ) -> dict:
        """

        Args:
            user_input: problem description provided by the user
            context: to get the root directory and other context informatio
            run_result: for extracting execution trace if available

        Returns:
        the enhanced check result, which includes:
            - check_summary: Summary of the fix result check
            - execution_stats: Statistics about model and tool calls during the fix
            - strategy_suggestions: Suggestions for improving the fixing strategy
            - trace_analysis: Analysis of the execution trace if available
        """

        diff_patch = GitDiffUtil.get_git_diff_exclude_test_files(context.root_dir)
        execution_trace = None
        if run_result:
            try:
                execution_trace = self._extract_execution_trace_from_run_result(run_result)
            except Exception as e:
                print(f"Failed to extract execution trace: {e}")
                execution_trace = None

        enhanced_result = await self.enhanced_fix_result_checker.check_with_trace(
            issue_desc=user_input,
            fix_code=diff_patch,
            context=context,
            execution_trace=execution_trace,
        )

        enhanced_result["code_diff"] = diff_patch
        return enhanced_result

    def run_streamed(
        self, user_input: str, context: CodeAgentContext
    ) -> RunResultStreaming:
        """
        Execute bug fixing task in streaming mode

        Args:
            user_input: User-described bug problem, including error messages, related file paths, etc.
            context: Context object for providing contextual information
        Returns:
            Fix result, including final output, execution rounds, and other information
        """
        pass

    def _extract_execution_trace_from_run_result(
        self, run_result: RunResult
    ) -> Optional[Dict[str, Any]]:
        """
        Extract execution trace from RunResult if available
        """
        model_calls = []
        tool_calls = []

        if hasattr(run_result, "new_items"):
            new_items = run_result.new_items
        else:
            raise ValueError("RunResult does not have 'new_items' attribute")

        for i in range(len(new_items)):
            item = new_items[i]

            if hasattr(item, "type"):
                item_type = item.type
            else:
                raise ValueError("Item does not have 'type' attribute")

            if item_type == "message_output_item":
                raw_item = item.raw_item
                model_calls.append(
                    self._extract_model_call_from_item(len(model_calls) + 1, raw_item)
                )
            elif item_type == "tool_call_output_item":
                tool_call_output_raw_item = item.raw_item
                if i > 0 and new_items[i - 1].type == "tool_call_item":
                    tool_calls_raw_item = new_items[i - 1].raw_item
                else:
                    raise ValueError(
                        "ToolCallOutputItem does not have a preceding ToolCallItem"
                    )
                tool_calls.append(
                    self._extract_tool_call_from_item(
                        len(tool_calls) + 1,
                        tool_call_output_raw_item,
                        tool_calls_raw_item,
                    )
                )

        return ExecutionTrace(
            trace_id=f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            workflow_name="bug_fix",
            start_time=datetime.now(),
            model_calls=model_calls,
            tool_calls=tool_calls,
        )

    def _extract_model_call_from_item(
        self, call_id: int, raw_item: ResponseOutputMessage
    ) -> ModelCall:
        model_call = ModelCall(
            call_id=call_id,
            model=None,
            input_messages="",
            output_messages=[{"role": "assistant", "content": str(raw_item.content)}],
            usage=None,
            timestamp=datetime.now(),
            duration_ms=0,
        )
        return model_call

    def _extract_tool_call_from_item(
        self,
        call_id: int,
        tool_call_output_raw_item: dict,
        tool_call_raw_item: ResponseFunctionToolCall,
    ) -> ModelCall:
        tool_call = ToolCall(
            call_id=call_id,
            tool_name="",
            timestamp=datetime.now(),
            duration_ms=0,
            success=True,
            error_message=None,
            input_args=tool_call_raw_item.arguments,
            output_result=(tool_call_output_raw_item.get("output", None)),
        )

        return tool_call

    def _build_enhanced_feedback(
        self,
        current_turn: int,
        result: dict,
        check_result: dict,
        check_summary: str,
        enhanced_check_result: dict,
    ) -> str:
        """
        Build enhanced feedback message for the next round of fixing

        Args:
            current_turn: Current turn number
            result: Current run result
            check_result: Result from the fix result checker
            check_summary: Summary of the fix result check
            enhanced_check_result: Result from the enhanced fix result checker

        Returns:
            Formatted feedback message for the next round
        """

        enhanced_feedback_content = f"""## Previous Fix Attempt (Round {current_turn + 1})
**Fix Logic:**
{result.final_output}

**Current Code Diff:**
{check_result.get('code_diff', 'No changes detected')}

## Primary Check Result
**Fix Status:** ❌ Not Fixed
**Primary Analysis:** {check_summary}

## Enhanced Analysis"""

        overall_score = enhanced_check_result.get("overall_score")
        if overall_score is not None:
            enhanced_feedback_content += f"\n**Quality Score:** {overall_score:.1f}/10"

        enhanced_summary = enhanced_check_result.get("check_summary")
        if enhanced_summary:
            enhanced_feedback_content += f"\n**Enhanced Summary:** {enhanced_summary}"

        execution_stats = enhanced_check_result.get("execution_stats")
        if execution_stats:
            enhanced_feedback_content += f"""

**Execution Statistics:**
- Model calls: {execution_stats.get('model_calls', 0)}
- Tool calls: {execution_stats.get('tool_calls', 0)}"""

        strategy_suggestions = self._extract_strategy_suggestions(enhanced_check_result)
        if strategy_suggestions:
            enhanced_feedback_content += "\n\n**Strategy Improvement Suggestions:"
            for i, suggestion in enumerate(strategy_suggestions[:3], 1):
                enhanced_feedback_content += f"\n{i}. {suggestion}"

        trace_analysis = enhanced_check_result.get("trace_analysis")
        if trace_analysis:
            enhanced_feedback_content += (
                f"\n\n**Execution Trace Analysis:**\n{trace_analysis}"
            )

        enhanced_feedback_content += f"""

## Next Steps
The previous fix attempt was not sufficient. Please analyze the above feedback and continue fixing the issue.
**Primary Focus:** {check_summary}"""

        fix_analysis = enhanced_check_result.get("fix_analysis")
        if fix_analysis:
            enhanced_feedback_content += f"\n**Additional Focus:** {fix_analysis}"

        return enhanced_feedback_content

    def _extract_strategy_suggestions(self, enhanced_check_result: dict) -> List[str]:
        prof_rec = enhanced_check_result.get("professional_recommendations", {})
        strategic_improvements = prof_rec.get("strategic_improvements", [])

        if not strategic_improvements:
            strategic_improvements = enhanced_check_result.get(
                "strategy_suggestions", []
            )

        return strategic_improvements

    def _format_execution_trace_input(self, user_input: str, result: RunResult) -> str:
        """
        Format user input with execution trace for anomaly check

        Args:
            user_input: Original user input
            result: RunResult containing execution trace

        Returns:
            Combined input string with formatted execution trace
        """
        execution_trace = result.to_input_list()

        try:
            import json
            trace_str = json.dumps(
                execution_trace, indent=2, ensure_ascii=False
            )
        except (TypeError, ValueError):
            print("fail to resolved JSON, fallback to str")
            trace_str = str(execution_trace)

        combined_input = f"{user_input}\n\n## Execution Trace\nThe following is the execution trace from the previous fix attempt:\n{trace_str}"
        return combined_input

    async def check(
        self,
        user_input: str,
        result: RunResult,
        context: CodeAgentContext,
        task_message: dict,
        current_turn: int
    ) -> tuple[bool, list]:
        """
        Handle web framework specific checking logic

        Args:
            user_int: user input
            result: Current run result
            context: Code agent context
            task_message: Task message
            current_turn: Current turn number

        Returns:
            Tuple of (should_break, input_list)
        """
        print(f"Starting fix result verification")
        check_result = await self.run_checker(user_input, context, trace_collector=self.trace_collector)
        enhanced_check_result = await self.run_enhanced_checker(user_input, context, run_result=result)
        if check_result.get("is_fixed", False):
            # Issue is fixed, break the loop
            print(
                f"Fix_check_result, Issue fixed: {check_result.get('check_summary', 'Fix verified')}"
            )
            return True, []
        else:
            # Issue not fixed, add the check_summary to input_list for next iteration
            check_summary = check_result.get(
                "check_summary", "Fix verification failed"
            )
            # if current_turn<3:
            # feedback_message = {
            #     "content": f"Here is the previous fix logic:\n{result.final_output}"
            #             f"Here is the current code diff:\n{check_result.get('code_diff', '')}"
            #             f"But previous fix attempt was not sufficient. Reason: {check_summary}.\n"
            #             f"**Please continue fixing.**",
            #     "role": "user"
            # }
            # else:
            #     feedback_message = {
            #         "content": f"Here is the previous fix logic:\n{result.final_output}"
            #                 f"Here is the current code diff:\n{check_result.get('code_diff', '')}"
            #                 f"But previous fix attempt was not sufficient. Reason: {check_summary}.\n"
            #                 f"**Please use git to discard changes in the working, and continue fixing.**",
            #         "role": "user"
            #     }
            self.code_patch_list.append(check_result.get('code_diff', ''))
            enhanced_feedback_content = self._build_enhanced_feedback(
                current_turn, result, check_result, check_summary, enhanced_check_result
            )

            print(
                f"Fix_check_result, Issue not fixed, continue fixing (round {current_turn + 1}): {check_summary}"
            )
            feedback_message = {
                "content": enhanced_feedback_content,
                "role": "user"
            }

            input_list = [task_message, feedback_message]
            return False, input_list
