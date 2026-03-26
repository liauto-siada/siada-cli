from .code_gen_prompt import get_system_prompt as get_code_gen_system_prompt


# Browser capability description for BrowserAgent
BROWSER_CAPABILITY = """- You can use the browser_operate tool to interact with websites (including html files and locally running development servers) through a BrowserGym-controlled browser when you feel it is necessary in accomplishing the user's task. This tool is particularly useful for web development tasks as it allows you to launch a browser, navigate to pages, interact with elements through clicks and keyboard input, and capture the results through screenshots and console logs. This tool may be useful at key stages of web development tasks-such as after implementing new features, making substantial changes, when troubleshooting issues, or to verify the result of your work. You can analyze the provided screenshots to ensure correct rendering or identify errors, and review console logs for runtime issues.
	- For example, if asked to add a component to a react website, you might create the necessary files, use execute_command to run the site locally, then use browser_operate to launch the browser, navigate to the local server, and verify the component renders & functions correctly before closing the browser."""


def get_system_prompt(cwd: str = "/default/path", interactive_mode: bool = True, user_memory: str = None,
                      preferred_language: str = None, agent_name: str = None, pre_plan: bool = False,
                      enable_parallel_tool_calls: bool = False) -> str:
    """Generate the system prompt for the browser agent.

    This uses the code_gen_prompt with additional browser capability.

    Args:
        cwd: Current working directory path.
        interactive_mode: Whether the agent is running in interactive mode.
        user_memory: User memory content (loaded from the `siada.md` file).
        preferred_language: Preferred language code ("en" or "zh-CN").
        agent_name: Name of the agent.
        pre_plan: Whether to include pre-plan section.

    Returns:
        The formatted system prompt string.
    """
    return get_code_gen_system_prompt(
        cwd=cwd,
        interactive_mode=interactive_mode,
        user_memory=user_memory,
        preferred_language=preferred_language,
        agent_name=agent_name,
        pre_plan=pre_plan,
        extra_capabilities=[BROWSER_CAPABILITY],
        enable_parallel_tool_calls=enable_parallel_tool_calls
    )
