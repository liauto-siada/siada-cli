import asyncio
from agents import function_tool, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.observation.observation import FunctionCallResult


class AskFollowupQuestionResult(FunctionCallResult):

    answer: str

    error: str

    def __init__(self, answer: str = None, error: str = None):
        super().__init__(content=answer)
        self.answer = answer
        self.error = error

    def format_for_display(self) -> str:
        if self.error:
            return f"I can't get the answer from the user, because {self.error} occurred"
        elif self.answer:
            return "Siada has received the answer!"
        else:
            return "Siada has not received the answer yet!"

    def __str__(self) -> str:
        if self.error:
            return f"Unable to retrieve user's answer due to error: {self.error}"
        elif self.answer:
            return f"The user's answer is : {self.answer}"
        else:
            return f"the user has not answered the question"


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

    try:
        code_agent_context : CodeAgentContext = context.context
        # 在线程中运行同步的prompt_ask以避免异步冲突
        answer = await asyncio.to_thread(code_agent_context.session.get_input)
        
    except Exception as e:
        return AskFollowupQuestionResult(error=str(e))

    return AskFollowupQuestionResult(answer=answer) 
