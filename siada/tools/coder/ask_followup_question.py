from agents import function_tool, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.observation.observation import FunctionCallResult

ASK_FOLLOWUP_QUESTION_DOCS = """Ask Follow-up Question Tool

Ask the user a question to gather additional information needed to complete the task. This tool should be used when you encounter ambiguities, need clarification, or require more details to proceed effectively. It allows for interactive problem-solving by enabling direct communication with the user. Use this tool judiciously to maintain a balance between gathering necessary information and avoiding excessive back-and-forth.

Args:
    question: (required) The question to ask the user. This should be a clear, specific question that addresses the information you need.
"""

@function_tool(
    name_override="ask_followup_question",
    description_override=ASK_FOLLOWUP_QUESTION_DOCS
)
async def ask_followup_question(
    context: RunContextWrapper[CodeAgentContext],
    question: str,
) -> FunctionCallResult:
    """
    Asks a followup question to the user to get more information.
    
    Args:
        context: The run context wrapper.
        question: The question to ask the user.
        
    Returns:
        An observation containing the question for the user.
    """
    ## TODO: 这里需要调用ask_followup_question_tool
    return FunctionCallResult(content=question) 