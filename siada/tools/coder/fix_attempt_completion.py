from agents import function_tool, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.observation.observation import FunctionCallResult


class FixAttemptCompletionResult(FunctionCallResult):

    def __init__(self, content: str):
        super().__init__(content=content)

    def __str__(self):
        return self.content

    def format_for_display(self):
        return "Bug Fix Task Status: COMPLETED"


@function_tool(
    name_override="fix_attempt_completion",
    description_override="Complete the bug fix task and mark it as finished. This tool MUST be called to properly complete any bug fix task. Failure to call this tool means the bug fix task is incomplete and unacceptable."
)
async def fix_attempt_completion(
    context: RunContextWrapper[CodeAgentContext],
    result: str,
) -> FunctionCallResult:
    """
    Complete the bug fix task and mark it as finished.
    
    IMPORTANT NOTE: This tool MUST be called to properly complete any bug fix task. Failure to call this tool means the bug fix task is incomplete and unacceptable. Before completing any bug fix work, you must ask yourself if you have successfully fixed all the bugs mentioned in the task. If not, then DO NOT use this tool until all bugs are fixed.
    
    Args:
        context: The run context wrapper containing agent context
        result: (required) A detailed summary of the bug fix work completed, including:
                - Summary of the bug fix logic
                - What changes were made
                - What files were modified
                - Any testing or verification performed        
    Returns:
        Observation: A completion observation with the fix summary
        
    Example:
        fix_attempt_completion(
            result="Successfully fixed the login authentication bug. Modified auth.py to properly validate user credentials and updated the password hashing algorithm. All tests are now passing.",
        )
    """
    
    # Format the completion message
    completion_message = f"""
=== Bug Fix Completed ===

{result}

"""


    return FixAttemptCompletionResult(
        content=completion_message,
    )