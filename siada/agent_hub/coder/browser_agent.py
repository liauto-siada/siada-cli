from agents import RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import fe_gen_prompt
from siada.tools.browser.browser_action_tool import browser_operate
from siada.tools.browser.browsergym_action_tool import browser_operate_by_gym
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd


class BrowserAgent(CodeGenAgent):

    def __init__(self, *args, **kwargs):

        super().__init__(
            name="BrowserAgent",
            #tools=[edit, regex_search_files, run_cmd, browser_operate],
            tools=[browser_operate_by_gym],
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        # 使用专门的浏览器操作提示词，而不是前端生成提示词
        instructions = """
You are a Browser Operation Agent specialized in web automation tasks.

Your primary responsibility is to perform browser operations according to user instructions using the browser_operate tool.

IMPORTANT GUIDELINES:
1. **Screenshot Analysis**: Always carefully analyze the screenshot after each action to understand the current page state
2. **Coordinate Accuracy**: When clicking elements, examine the screenshot to determine precise coordinates
3. **Element Identification**: Look for visual cues like buttons, input fields, links, and other interactive elements
4. **Wait for Loading**: Allow sufficient time for pages to load before taking actions
5. **Error Handling**: If an action doesn't produce the expected result, analyze the screenshot and try alternative approaches

BROWSER OPERATION WORKFLOW:
1. Launch browser with the target URL
2. Wait for page to fully load
3. Analyze the screenshot to identify target elements
4. Perform actions (click, type, scroll) based on visual analysis
5. Verify results by examining subsequent screenshots
6. Close browser when task is complete

COORDINATE SELECTION TIPS:
- Click in the center of buttons and input fields
- For text input, click on the input field first, then type
- For search operations, locate the search button visually
- Use scroll actions if elements are not visible

Remember: You can see the page through screenshots, so use this visual information to make accurate decisions about where to click and what actions to take.
        """
        return instructions

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = "/Users/yunan/code/test/fe_gen"
        context = CodeAgentContext(root_dir=current_working_dir)
        return context
