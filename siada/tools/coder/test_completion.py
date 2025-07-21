from agents import RunContextWrapper, function_tool

from siada.foundation.code_agent_context import CodeAgentContext

TEST_COMPLETION_DOCS = f"""Test Completion Tool
Use this tool to submit your test work results to the user whenever the test task has been completed. This tool reports whether tests passed or failed and provides detailed information about the test execution.
IMPORTANT NOTE: Do not invoke this tool unless the test task has been confirmed as completed.
Args:
    is_passed: Integer type, 0 indicates test failed, 1 indicates test passed.
    test_detail: String type. If tests passed, describe which test cases were executed. If tests failed, describe each failed test case and the failure reason.
"""


@function_tool(
    name_override="test_completion", description_override=TEST_COMPLETION_DOCS, failure_error_function=None
)
async def test_completion(context: RunContextWrapper[CodeAgentContext], is_passed: int, test_detail: str) -> str:
    # 获取 session_id
    test_result = "Tests passed" if is_passed == 1 else "Tests failed"

    return {
        "is_passed": is_passed,
        "test_detail": test_result + ":" + test_detail
    }

