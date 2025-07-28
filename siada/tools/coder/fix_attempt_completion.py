from agents import function_tool, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.observation.observation import FunctionCallResult
from siada.tools.coder.observation.file_observation import FileReadObservation


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
                - What bug was fixed
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
    
    completion_message += """
Task Status: COMPLETED ✓

The bug fix task has been successfully completed. All necessary changes have been made and the issue should now be resolved.
"""
    
    # Show system notification (simulated)
    notification_message = result.replace('\n', ' ')
    #print(f""" showSystemNotification({{ subtitle: "Fix Completed",message: "{notification_message}",}})""")
    
    return FileReadObservation(
        content=completion_message,
        path="fix_completion_summary",
        impl_source="fix_attempt_completion"
    )