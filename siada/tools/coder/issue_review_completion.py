from agents import RunContextWrapper, function_tool

from siada.foundation.code_agent_context import CodeAgentContext


ISSUE_REVIEW_COMPLETION_DOCS = f"""Issue Review Completion Tool

This tool is called when completing an issue review process. It captures the final assessment of whether an issue has been successfully resolved.

Parameters:
- is_fixed (bool): Indicates whether the issue has been fixed. True if the issue is fixed, False if the issue is not fixed.
- check_summary (str): The review conclusion summary. When is_fixed is False, this summary must be very detailed, explaining what aspects of the issue remain unresolved, what problems were found during the review, and what additional work is needed. Must include:
   - Specific basis for fix status judgment
   - If not fixed, clearly explain reasons for non-fix
   - If fixed, assess implementation quality and potential risks
   - Specific improvement suggestions or alternative solutions

"""


@function_tool(
    name_override="issue_review_completion", description_override=ISSUE_REVIEW_COMPLETION_DOCS, failure_error_function=None
)
async def issue_review_completion(context: RunContextWrapper[CodeAgentContext], is_fixed: bool,
                                  check_summary: str) -> dict:
    return {
        "is_fixed": is_fixed,
        "check_summary": check_summary
    }
