"""
BrowserGym automation tool for browser operations.

This module provides browser automation capabilities using BrowserGym,
which offers element-based interactions through browser element IDs (bids)
instead of coordinate-based clicking.
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Dict, Any
from dataclasses import asdict

from agents import function_tool, RunContextWrapper

from .browsergym_env import BrowserGymEnv
from .browsergym_utils import (
    format_action_command,
    validate_action_parameters,
    create_browsergym_result,
    format_accessibility_tree,
    extract_bids_from_observation
)
from .models import ImageResult
from ...foundation.code_agent_context import CodeAgentContext

# Documentation for the browser operate tool
BROWSERGYM_OPERATE_DOC = """
Request to interact with a BrowserGym-controlled browser using element IDs (bids). Every action, except `close`, will be responded to with a screenshot of the browser's current state, along with the accessibility tree showing available interactive elements.

**Key Advantages over coordinate-based tools:**
- **Element-based interaction**: Use semantic element IDs instead of pixel coordinates
- **Accessibility tree**: Get structured information about all interactive elements
- **More reliable**: Not affected by page layout changes or screen resolution
- **Advanced operations**: Support for drag-and-drop, file uploads, and complex interactions

**Usage Flow:**
1. **Must start with `launch`** to initialize the browser environment
2. Use other actions to interact with page elements using their `bid` values
3. **Must end with `close`** to clean up resources

**Important Notes:**
- While the browser is active, only the `browsergym_operate` tool should be used
- Each action returns both a screenshot and accessibility tree information
- Use the accessibility tree to find available element `bid` values for interaction
- The browser automatically handles page loading and element detection

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
         - type: "image_url"
         - image_url: Object with:
           - url: Base64-encoded screenshot of current browser state
           - axtree_info: Object containing:
             - axtree: Formatted accessibility tree with element bids
             - available_bids: List of all available element IDs
             - page_info: Current page URL, title, and metadata
             - success: Boolean indicating if action was successful
             - error: Error message if action failed (null if successful)
"""


class BrowserGymActionTool:
    """BrowserGym automation tool class.
    
    Provides browser automation capabilities using BrowserGym, including:
    - Element-based interactions using browser IDs (bids)
    - Accessibility tree information
    - Advanced browser operations (drag-and-drop, file upload, etc.)
    - Automatic element detection and interaction
    """

    def __init__(self):
        """Initialize the BrowserGym action tool."""
        self.env_manager = BrowserGymEnv.get_instance()
        self.logger = logging.getLogger(__name__)

    def execute_action(
        self,
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
                return self._launch(url or "https://www.google.com")
            elif action == "close":
                return self._close()
            else:
                # Validate that environment is initialized
                if not self.env_manager.is_initialized():
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
                return self._execute_browser_action(action, **action_params)
                
        except Exception as e:
            self.logger.error(f"BrowserGym action failed: {str(e)}")
            return create_browsergym_result(
                obs=None,
                success=False,
                error=str(e)
            )

    def _launch(self, url: str) -> Dict[str, Any]:
        """Launch BrowserGym environment and navigate to URL.
        
        Args:
            url: The URL to navigate to
            
        Returns:
            Dict[str, Any]: Result with initial page state
        """
        try:
            # Initialize the environment
            success = self.env_manager.initialize(start_url=url, headless=False)
            if not success:
                raise RuntimeError("Failed to initialize BrowserGym environment")
            
            # Wait for page to load, then get observation
            import time
            time.sleep(2)
            
            # Get fresh observation by performing a no-op action
            obs, _, _, _, _ = self.env_manager.step("scroll(0, 0)")
            
            return create_browsergym_result(obs, success=True, action="launch")
            
        except Exception as e:
            self.logger.error(f"Failed to launch BrowserGym environment: {str(e)}")
            return create_browsergym_result(
                obs=None,
                success=False,
                error=f"Launch failed: {str(e)}"
            )

    def _close(self) -> Dict[str, Any]:
        """Close BrowserGym environment and cleanup resources.
        
        Returns:
            Dict[str, Any]: Result indicating cleanup status
        """
        try:
            success = self.env_manager.close()
            
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
            self.logger.error(f"Error closing BrowserGym environment: {str(e)}")
            return create_browsergym_result(
                obs=None,
                success=False,
                error=f"Close failed: {str(e)}"
            )

    def _execute_browser_action(self, action: str, **kwargs) -> Dict[str, Any]:
        """Execute a browser action in the BrowserGym environment.
        
        Args:
            action: The action type
            **kwargs: Action parameters
            
        Returns:
            Dict[str, Any]: Result with updated page state
        """
        try:
            # Format the action command
            command = format_action_command(action, **kwargs)
            
            # Execute the action
            obs, reward, terminated, truncated, info = self.env_manager.step(command)
            
            # For actions that might cause page changes, wait and get fresh observation
            if action in ["click", "fill", "press"] and not (terminated or truncated):
                import time
                time.sleep(1)
                try:
                    fresh_obs, _, _, _, _ = self.env_manager.step("scroll(0, 0)")
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
            self.logger.error(f"Failed to execute action '{action}': {str(e)}")
            return create_browsergym_result(
                obs=None,
                success=False,
                error=f"Action execution failed: {str(e)}"
            )


@function_tool(
    name_override="browser_operate_by_gym",
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
) -> str:
    import weakref

    # Get or create browser tool instance from context
    if not hasattr(context.context, '_browsergym_tool'):
        context.context._browsergym_tool = BrowserGymActionTool()
        
        # Register cleanup function
        def cleanup_browsergym():
            if hasattr(context.context, '_browsergym_tool') and context.context._browsergym_tool:
                try:
                    context.context._browsergym_tool._close()
                except Exception:
                    pass  # Ignore cleanup errors
        
        # Use weakref to register cleanup callback
        weakref.finalize(context.context, cleanup_browsergym)

    tool = context.context._browsergym_tool

    try:
        # Handle parameter type conversion for common mistakes
        if isinstance(modifiers, str):
            modifiers = [] if modifiers == "" else None
        
        # Execute the action
        result = tool.execute_action(
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
            modifiers=modifiers
        )
        
        # If close action is successful, remove the tool instance
        if action == "close" and result.get("success", False):
            if hasattr(context.context, '_browsergym_tool'):
                delattr(context.context, '_browsergym_tool')
        
        # Convert result to ImageResult format for consistency with other browser tools
        if result.get("screenshot") and result.get("success", False):
            # Extract base64 data
            screenshot_data = result["screenshot"].split(",")[-1] if "," in result["screenshot"] else result["screenshot"]
            
            # Get the observation from the result to format accessibility tree
            obs = result.get("_obs") if result else None
            
            # Extract data from the same observation for consistency
            formatted_axtree = format_accessibility_tree(obs) if obs else ""
            available_bids = extract_bids_from_observation(obs) if obs else []
            
            # Create axtree_info with consistent data
            axtree_info = {
                "axtree": formatted_axtree,
                "available_bids": available_bids,
                "page_info": result.get("page_info", {}),
                "success": result.get("success", False),
                "error": result.get("error")
            }
            
            # Create ImageResult with axtree_info in ImageUrl
            from .models import ImageUrl
            image_result = ImageResult(
                type="image_url",
                image_url=ImageUrl(
                    url=f"data:image/jpeg;base64,{screenshot_data}",
                    axtree_info=axtree_info
                )
            )
            
            return json.dumps(asdict(image_result))
        else:
            # Handle cases where screenshot is None or operation failed
            # Still try to get accessibility tree information even without screenshot
            obs = getattr(tool.env_manager, '_last_obs', None) if hasattr(tool.env_manager, '_last_obs') else None
            formatted_axtree = format_accessibility_tree(obs) if obs else ""
            
            axtree_info = {
                "axtree": formatted_axtree,
                "available_bids": result.get("available_bids", []),
                "page_info": result.get("page_info", {}),
                "success": result.get("success", False),
                "error": result.get("error")
            }
            
            from .models import ImageUrl
            image_result = ImageResult(
                type="image_url",
                image_url=ImageUrl(
                    url="data:image/jpeg;base64,",
                    axtree_info=axtree_info
                )
            )
            
            return json.dumps(asdict(image_result))
            
    except Exception as e:
        # If browser operation fails, remove the tool instance
        if hasattr(context.context, '_browsergym_tool'):
            delattr(context.context, '_browsergym_tool')
        
        # Return error result
        image_result = ImageResult.from_base64("", "jpeg")
        response_data = {
            **asdict(image_result),
            "browsergym_info": {
                "success": False,
                "error": str(e),
                "axtree": "",
                "page_info": {},
                "available_bids": []
            }
        }
        return json.dumps(response_data)
