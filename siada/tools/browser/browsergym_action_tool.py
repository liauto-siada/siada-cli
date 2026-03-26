"""
BrowserGym automation tool for browser operations.

This module provides browser automation capabilities using BrowserGym,
which offers element-based interactions through browser element IDs (bids)
instead of coordinate-based clicking.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any, Coroutine, TypeVar, List

from agents import function_tool, RunContextWrapper, ToolOutputImage, ToolOutputText

from .chromium_installer import ChromiumAutoInstaller
from .browsergym_env import BrowserGymEnvManager
from .browsergym_utils import (
    format_action_command,
    validate_action_parameters,
    create_browsergym_result,
    format_accessibility_tree,
    extract_bids_from_observation
)
from .models import BrowserOperateResult
from ...foundation.code_agent_context import CodeAgentContext
from ...tools.coder.observation.error import ErrorObservation

# Type alias for the tool return type
ValidToolOutputPydanticModels = ToolOutputImage | ToolOutputText
T = TypeVar('T')

# Module-level logger
logger = logging.getLogger(__name__)

# Models that support browser operations (require image processing capability)
SUPPORTED_BROWSER_MODELS = {"claude", "gemini"}

# Documentation for the browser operate tool
BROWSERGYM_OPERATE_DOC = """
Request to interact with a BrowserGym-controlled browser using element IDs (bids). Every action, except `close`, will be responded to with a screenshot of the browser's current state, along with the accessibility tree showing available interactive elements.

**Key Advantages over coordinate-based tools:**
- **Element-based interaction**: Use semantic element IDs instead of pixel coordinates
- **Accessibility tree**: Get structured information about all interactive elements
- **More reliable**: Not affected by page layout changes or screen resolution
- **Advanced operations**: Support for drag-and-drop, file uploads, and complex interactions

**Usage Flow:**
1. The sequence of actions **must always start with** `launch` to initialize the browser at a URL
2. Use other actions to interact with page elements using their `bid` values
3. The sequence **must always end with** `close` to clean up resources. If you need to visit a new URL that is not possible to navigate to from the current webpage, you must first close the browser, then launch again at the new URL.

**Important Notes:**
- While the browser is active, only the `browser_operate` tool can be used. No other tools should be called during this time. You may proceed to use other tools only after closing the browser. For example if you run into an error and need to fix a file, you must close the browser, then use other tools to make the necessary changes, then re-launch the browser to verify the result.
- Each action returns both a screenshot and accessibility tree information
- Use the accessibility tree to find available element `bid` values for interaction
- The browser automatically handles page loading and element detection
- The accessibility tree filters out non-interactive nodes to reduce output size:
  - Text rendering: InlineTextBox, StaticText, LineBreak
  - Empty/ignored: none, ignored
  - Generic containers: generic
  - Text styling: strong, emphasis
  - Structural containers: paragraph
  - List containers: listitem

**PARAMETER TYPES AND REQUIREMENTS:**

**Required Parameters:**
    action (str): The action type to execute. ALWAYS REQUIRED.

**Action-Specific Required Parameters:**
    - "launch": url (str) - Target website URL
    - "click", "hover", "focus", "clear", "dblclick": bid (str) - Element ID
    - "fill": bid (str) + value (str) - Element ID and text content
    - "select_option": bid (str) + value (str) - Element ID and option value
    - "press": bid (str) + key (str) - Element ID and key name
    - "drag_and_drop": bid (str) + target_bid (str) - Source and target element IDs
    - "upload_file": bid (str) + file_path (str) - Element ID and file path
    - "scroll": delta_x (float) and/or delta_y (float) - Scroll distances
    - "close": No additional parameters required

**Optional Parameters (with defaults):**
    url (str, default=None): Only used with "launch" action
    bid (str, default=None): Element ID for element-based actions
    value (str, default=None): Text content for "fill" and "select_option"
    target_bid (str, default=None): Target element for "drag_and_drop"
    file_path (str, default=None): File path for "upload_file"
    delta_x (float, default=0): Horizontal scroll distance (NOT used for click actions)
    delta_y (float, default=0): Vertical scroll distance (NOT used for click actions)
    key (str, default=None): Key name for "press" action
    button (str, default="left"): Mouse button for click actions ("left", "middle", "right")
    modifiers (list, default=[]): Keyboard modifiers for click actions (e.g., ["Alt", "Control"])

**DETAILED ACTION SPECIFICATIONS:**

**"launch"** - Initialize browser and navigate to URL
    Required: action="launch", url="https://example.com"
    Optional: None
    Ignored: bid, value, target_bid, file_path, delta_x, delta_y, key, button, modifiers
    Example: {"action": "launch", "url": "https://www.google.com"}

**"click"** - Click on an element
    Required: action="click", bid="element_id"
    Optional: button="left", modifiers=[]
    Ignored: url, value, target_bid, file_path, delta_x, delta_y, key
    Examples: 
        {"action": "click", "bid": "submit_button"}
        {"action": "click", "bid": "link_1", "button": "right"}
        {"action": "click", "bid": "menu_item", "modifiers": ["Control"]}

**"fill"** - Enter text into input field
    Required: action="fill", bid="input_id", value="text_content"
    Optional: None
    Ignored: url, target_bid, file_path, delta_x, delta_y, key, button, modifiers
    Example: {"action": "fill", "bid": "search_box", "value": "hello world"}

**"select_option"** - Select option from dropdown
    Required: action="select_option", bid="select_id", value="option_value"
    Optional: None
    Ignored: url, target_bid, file_path, delta_x, delta_y, key, button, modifiers
    Example: {"action": "select_option", "bid": "country_select", "value": "US"}

**"scroll"** - Scroll the page
    Required: action="scroll"
    Optional: delta_x=0, delta_y=0 (at least one should be non-zero)
    Ignored: url, bid, value, target_bid, file_path, key, button, modifiers
    Examples:
        {"action": "scroll", "delta_y": 300}  # Scroll down
        {"action": "scroll", "delta_y": -200}  # Scroll up
        {"action": "scroll", "delta_x": 100, "delta_y": 200}  # Scroll right and down

**"press"** - Press a key on an element
    Required: action="press", bid="element_id", key="key_name"
    Optional: None
    Ignored: url, value, target_bid, file_path, delta_x, delta_y, button, modifiers
    Examples:
        {"action": "press", "bid": "input_field", "key": "Enter"}
        {"action": "press", "bid": "text_area", "key": "Tab"}

**"hover"** - Hover mouse over element
    Required: action="hover", bid="element_id"
    Optional: None
    Ignored: url, value, target_bid, file_path, delta_x, delta_y, key, button, modifiers
    Example: {"action": "hover", "bid": "menu_trigger"}

**"focus"** - Set focus on element
    Required: action="focus", bid="element_id"
    Optional: None
    Ignored: url, value, target_bid, file_path, delta_x, delta_y, key, button, modifiers
    Example: {"action": "focus", "bid": "input_field"}

**"clear"** - Clear content of input field
    Required: action="clear", bid="input_id"
    Optional: None
    Ignored: url, value, target_bid, file_path, delta_x, delta_y, key, button, modifiers
    Example: {"action": "clear", "bid": "search_box"}

**"dblclick"** - Double-click on element
    Required: action="dblclick", bid="element_id"
    Optional: button="left", modifiers=[]
    Ignored: url, value, target_bid, file_path, delta_x, delta_y, key
    Example: {"action": "dblclick", "bid": "file_item"}

**"drag_and_drop"** - Drag element to target
    Required: action="drag_and_drop", bid="source_id", target_bid="target_id"
    Optional: None
    Ignored: url, value, file_path, delta_x, delta_y, key, button, modifiers
    Example: {"action": "drag_and_drop", "bid": "item1", "target_bid": "dropzone"}

**"upload_file"** - Upload file to file input
    Required: action="upload_file", bid="file_input_id", file_path="/path/to/file"
    Optional: None
    Ignored: url, value, target_bid, delta_x, delta_y, key, button, modifiers
    Example: {"action": "upload_file", "bid": "file_input", "file_path": "/tmp/document.pdf"}

**"close"** - Close browser and cleanup
    Required: action="close"
    Optional: None
    Ignored: All other parameters
    Example: {"action": "close"}

**COMMON MISTAKES TO AVOID:**
1. Using delta_x/delta_y with click actions (they are only for scroll)
2. Passing empty string "" for modifiers (use empty list [] instead)
3. Forgetting required parameters for specific actions
4. Using wrong parameter types (e.g., string instead of list for modifiers)

Returns:
    str: JSON string containing:
         - action: The browser action that was executed
         - success: Boolean indicating if action was successful
         - error: Error message if action failed (null if successful)
         - page_info: Current page URL, title, and metadata
         - available_bids_count: Number of available element IDs on the page
         - axtree: Formatted accessibility tree with element bids (use this to find specific bid values)
         - has_screenshot: Boolean indicating if a screenshot is available
         
    Note: The full list of available_bids is NOT included to save context space.
    Use the accessibility tree (axtree) to find specific element bids for interaction.
"""


def _get_env_manager() -> BrowserGymEnvManager:
    """Get the current BrowserGymEnv singleton instance.
    
    Returns:
        BrowserGymEnv: The singleton instance
    """
    return BrowserGymEnvManager.get_instance()


def _launch(url: str) -> Dict[str, Any]:
    """Launch BrowserGym environment and navigate to URL.
    
    Args:
        url: The URL to navigate to
        
    Returns:
        Dict[str, Any]: Result with initial page state
    """
    try:
        env_manager = _get_env_manager()
        # Initialize the environment
        success = env_manager.initialize(start_url=url, headless=False)
        if not success:
            raise RuntimeError("Failed to initialize BrowserGym environment")
        
        # Wait for page to load, then get observation
        time.sleep(2)
        
        # Get fresh observation by performing a no-op action
        obs, _, _, _, _ = env_manager.step("scroll(0, 0)")
        
        return create_browsergym_result(obs, success=True, action="launch")
        
    except Exception as e:
        logger.error(f"Failed to launch BrowserGym environment: {str(e)}")
        return create_browsergym_result(
            obs=None,
            success=False,
            error=f"Launch failed: {str(e)}"
        )


def _close() -> Dict[str, Any]:
    """Close BrowserGym environment and cleanup resources.
    
    Returns:
        Dict[str, Any]: Result indicating cleanup status
    """
    try:
        env_manager = _get_env_manager()
        success = env_manager.close()
        
        if success:
            return {
                "success": True,
                "screenshot": "",
                "axtree": "",
                "page_info": {},
                "available_bids": [],
                "error": None
            }
        else:
            raise RuntimeError("Failed to close BrowserGym environment")
            
    except Exception as e:
        logger.error(f"Error closing BrowserGym environment: {str(e)}")
        return create_browsergym_result(
            obs=None,
            success=False,
            error=f"Close failed: {str(e)}"
        )


def _execute_browser_action(action: str, **kwargs) -> Dict[str, Any]:
    """Execute a browser action in the BrowserGym environment.
    
    Args:
        action: The action type
        **kwargs: Action parameters
        
    Returns:
        Dict[str, Any]: Result with updated page state
    """
    try:
        env_manager = _get_env_manager()
        # Format the action command
        command = format_action_command(action, **kwargs)
        
        # Execute the action
        obs, reward, terminated, truncated, info = env_manager.step(command)
        
        # For actions that might cause page changes, wait and get fresh observation
        if action in ["click", "fill", "press"] and not (terminated or truncated):
            time.sleep(1)
            try:
                fresh_obs, _, _, _, _ = env_manager.step("scroll(0, 0)")
                if fresh_obs:
                    obs = fresh_obs
            except Exception:
                pass  # Use original observation if refresh fails
        
        # Check if action was successful
        success = not (terminated or truncated)
        error_msg = None
        
        if terminated or truncated:
            error_msg = f"Action terminated unexpectedly. Info: {info}"
        
        return create_browsergym_result(obs, success=success, error=error_msg, action=action)
        
    except Exception as e:
        logger.error(f"Failed to execute action '{action}': {str(e)}")
        return create_browsergym_result(
            obs=None,
            success=False,
            error=f"Action execution failed: {str(e)}"
        )


def execute_action(
    action: str,
    url: Optional[str] = None,
    bid: Optional[str] = None,
    value: Optional[str] = None,
    target_bid: Optional[str] = None,
    file_path: Optional[str] = None,
    delta_x: float = 0,
    delta_y: float = 0,
    key: Optional[str] = None,
    button: str = "left",
    modifiers: Optional[list] = None
) -> Dict[str, Any]:
    """Execute a browser action using BrowserGym.
    
    Args:
        action: The action type to execute
        url: Target URL (for launch action)
        bid: Browser element ID
        value: Text value (for fill/select actions)
        target_bid: Target element ID (for drag_and_drop)
        file_path: File path (for upload_file)
        delta_x: Horizontal scroll distance
        delta_y: Vertical scroll distance
        key: Key name (for press action)
        button: Mouse button for click actions
        modifiers: Keyboard modifiers for click actions
        
    Returns:
        Dict[str, Any]: Result dictionary with screenshot, axtree, and metadata
    """
    try:
        if action == "launch":
            return _launch(url or "https://www.google.com")
        elif action == "close":
            return _close()
        else:
            env_manager = _get_env_manager()
            # Validate that environment is initialized
            if not env_manager.is_initialized():
                raise RuntimeError("BrowserGym environment not initialized. Use 'launch' action first.")
            
            # Prepare action parameters
            action_params = {
                "bid": bid,
                "value": value,
                "target_bid": target_bid,
                "file_path": file_path,
                "delta_x": delta_x,
                "delta_y": delta_y,
                "key": key,
                "button": button,
                "modifiers": modifiers or []
            }
            
            # Validate parameters
            is_valid, error_msg = validate_action_parameters(action, **action_params)
            if not is_valid:
                raise ValueError(error_msg)
            
            # Execute the action
            return _execute_browser_action(action, **action_params)
            
    except Exception as e:
        logger.error(f"BrowserGym action failed: {str(e)}")
        return create_browsergym_result(
            obs=None,
            success=False,
            error=str(e)
        )


@function_tool(
    name_override="browser_operate",
    description_override=BROWSERGYM_OPERATE_DOC
)
def browser_operate_by_gym(
    context: RunContextWrapper[CodeAgentContext],
    action: str,
    url: Optional[str] = None,
    bid: Optional[str] = None,
    value: Optional[str] = None,
    target_bid: Optional[str] = None,
    file_path: Optional[str] = None,
    delta_x: float = 0,
    delta_y: float = 0,
    key: Optional[str] = None,
    button: str = "left",
    modifiers: Optional[list] = None
) -> List[ValidToolOutputPydanticModels]:

    # Check if current model supports browser operations
    model_name = context.context.model_run_config.model_name.lower()
    if not any(m in model_name for m in SUPPORTED_BROWSER_MODELS):
        return ErrorObservation(
            content=f"Current model '{model_name}' does not support browser operations. "
            f"Browser operations require image processing capability. "
            f"Stop the Task Immediately. Always Only Tell user to 'Sorry. I can't do that operation' ",
            display_content="Current model does not support browser operations. Select claude or gemini model to enable this feature.\n",
        )

    def run_async_from_sync(coro: Coroutine[Any, Any, T]) -> T:
        """Run async function from sync context"""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()

    # Get io from context if available
    io = None
    if hasattr(context.context, 'session') and context.context.session:
        if hasattr(context.context.session, 'siada_config') and context.context.session.siada_config:
            io = getattr(context.context.session.siada_config, 'io', None)
    
    # Ensure Chromium is available and set environment variable
    import os
    installer = ChromiumAutoInstaller(io=io)
    chromium_path = run_async_from_sync(installer.ensure_chromium_available())
    os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'] = chromium_path

    try:
        # Handle parameter type conversion for common mistakes
        actual_modifiers = modifiers
        if isinstance(actual_modifiers, str):
            actual_modifiers = [] if actual_modifiers == "" else None
        
        # Execute the action using module-level function
        result = execute_action(
            action=action,
            url=url,
            bid=bid,
            value=value,
            target_bid=target_bid,
            file_path=file_path,
            delta_x=delta_x,
            delta_y=delta_y,
            key=key,
            button=button,
            modifiers=actual_modifiers
        )
        
        # Get observation for accessibility tree
        obs = result.get("_obs") if result else None
        env_manager = _get_env_manager()
        if obs is None and hasattr(env_manager, '_last_obs'):
            obs = getattr(env_manager, '_last_obs', None)
        
        # Extract accessibility tree data
        formatted_axtree = format_accessibility_tree(obs) if obs else ""
        available_bids = extract_bids_from_observation(obs) if obs else result.get("available_bids", [])
        
        # Create BrowserOperateResult using factory method
        browser_result = BrowserOperateResult.create(
            action=action,
            success=result.get("success", False),
            error=result.get("error"),
            page_info=result.get("page_info", {}),
            available_bids=available_bids,
            axtree=formatted_axtree,
            screenshot=result.get("screenshot")
        )
        
        # Store the result in context for potential UI display
        if hasattr(context.context, '_last_browser_result'):
            context.context._last_browser_result = browser_result
        else:
            context.context._last_browser_result = browser_result
        
        return browser_result.get_api_output_items()
            
    except Exception as e:
        # Return error as ToolOutputText
        error_message = f"BrowserGym action '{action}' failed with error: {str(e)}"
        return [ToolOutputText(text=error_message)]
