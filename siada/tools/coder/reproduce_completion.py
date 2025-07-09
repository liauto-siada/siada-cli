from agents import RunContextWrapper, function_tool

from siada.foundation.code_agent_context import CodeAgentContext

REPRODUCE_COMPLETION_DOCS = f"""ISSUE Reproduction Completion Tool
Use this tool to submit your work results to the user whenever the ISSUE has been successfully reproduced—that is, when executing the test cases you generated can reliably reproduce the ISSUE. Include a brief description of your reproduction process.
IMPORTANT NOTE: Do not invoke this tool unless the issue has been confirmed as reproduced.
Args:
    test_case: The full path of the test case used to reproduce the issue in the task.
    bug_analysis: Analysis of the cause of the bug, including the involved code files, methods, and other relevant components.
"""


@function_tool(
    name_override="reproduce_completion", description_override=REPRODUCE_COMPLETION_DOCS, failure_error_function=None
)
async def reproduce_completion(context: RunContextWrapper[CodeAgentContext], test_case: str, bug_analysis: str) -> str:
    # 获取 session_id
    return (f"====\n"
            f"This issue can be reproduced using test case : {test_case}.\n Analysis of the issue: {bug_analysis} \n"
            f"When you start fixing the issue, you must thoroughly refer to this information."
            f"\n====")
