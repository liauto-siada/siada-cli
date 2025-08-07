"""
Utility functions for BrowserGym browser automation.

This module provides utility functions for image processing, data conversion,
and other helper functions needed by the BrowserGym browser tool.
"""

import base64
import logging
import time
import os
from datetime import datetime
from typing import Any, Dict, Optional
from io import BytesIO
import numpy as np
from PIL import Image


def image_to_base64_url(image_array: np.ndarray, format: str = "JPEG", quality: int = 75) -> str:
    """Convert numpy image array to base64 data URL.
    
    Args:
        image_array: Numpy array representing the image
        format: Image format ('JPEG' or 'PNG')
        quality: JPEG quality (1-100, only used for JPEG)
        
    Returns:
        str: Base64 data URL string
    """
    try:
        # Convert numpy array to PIL Image
        if image_array.dtype != np.uint8:
            image_array = (image_array * 255).astype(np.uint8)
        
        image = Image.fromarray(image_array)
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Save to bytes buffer
        buffer = BytesIO()
        save_kwargs = {"format": format}
        if format.upper() == "JPEG":
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True
        
        image.save(buffer, **save_kwargs)
        
        # Convert to base64
        image_bytes = buffer.getvalue()
        base64_string = base64.b64encode(image_bytes).decode('utf-8')
        
        # Create data URL
        mime_type = f"image/{format.lower()}"
        data_url = f"data:{mime_type};base64,{base64_string}"
        
        return data_url
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to convert image to base64: {str(e)}")
        return ""


def observation_to_text(obs: Dict[str, Any]) -> str:
    """Convert BrowserGym observation to text representation.
    
    Args:
        obs: BrowserGym observation dictionary
        
    Returns:
        str: Text representation of the observation
    """
    try:
        text_parts = []
        
        # Add accessibility tree if available
        if 'axtree' in obs and obs['axtree']:
            text_parts.append("=== Accessibility Tree ===")
            text_parts.append(str(obs['axtree']))
        
        # Add page info if available
        if 'page_info' in obs:
            page_info = obs['page_info']
            text_parts.append("\n=== Page Information ===")
            if 'url' in page_info:
                text_parts.append(f"URL: {page_info['url']}")
            if 'title' in page_info:
                text_parts.append(f"Title: {page_info['title']}")
        
        # Add any error messages
        if 'error' in obs and obs['error']:
            text_parts.append(f"\n=== Error ===")
            text_parts.append(str(obs['error']))
        
        # Add other relevant information
        for key, value in obs.items():
            if key not in ['screenshot', 'axtree', 'page_info', 'error'] and value:
                text_parts.append(f"\n=== {key.title()} ===")
                text_parts.append(str(value))
        
        return "\n".join(text_parts) if text_parts else "No text information available"
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to convert observation to text: {str(e)}")
        return f"Error processing observation: {str(e)}"


def format_action_command(action: str, **kwargs) -> str:
    """Format an action command string for BrowserGym.
    
    Args:
        action: The action type
        **kwargs: Action parameters
        
    Returns:
        str: Formatted action command
    """
    try:
        if action == "click":
            bid = kwargs.get("bid", "")
            button = kwargs.get("button", "left")
            modifiers = kwargs.get("modifiers", [])
            if modifiers:
                return f"click('{bid}', button='{button}', modifiers={modifiers})"
            else:
                return f"click('{bid}', button='{button}')"
        
        elif action == "fill":
            bid = kwargs.get("bid", "")
            value = kwargs.get("value", "")
            return f"fill('{bid}', '{value}')"
        
        elif action == "select_option":
            bid = kwargs.get("bid", "")
            value = kwargs.get("value", "")
            return f"select_option('{bid}', '{value}')"
        
        elif action == "scroll":
            delta_x = kwargs.get("delta_x", 0)
            delta_y = kwargs.get("delta_y", 0)
            return f"scroll({delta_x}, {delta_y})"
        
        elif action == "press":
            bid = kwargs.get("bid", "")
            key = kwargs.get("key", "")
            return f"press('{bid}', '{key}')"
        
        elif action == "hover":
            bid = kwargs.get("bid", "")
            return f"hover('{bid}')"
        
        elif action == "focus":
            bid = kwargs.get("bid", "")
            return f"focus('{bid}')"
        
        elif action == "clear":
            bid = kwargs.get("bid", "")
            return f"clear('{bid}')"
        
        elif action == "dblclick":
            bid = kwargs.get("bid", "")
            button = kwargs.get("button", "left")
            modifiers = kwargs.get("modifiers", [])
            if modifiers:
                return f"dblclick('{bid}', button='{button}', modifiers={modifiers})"
            else:
                return f"dblclick('{bid}', button='{button}')"
        
        elif action == "drag_and_drop":
            bid = kwargs.get("bid", "")
            target_bid = kwargs.get("target_bid", "")
            return f"drag_and_drop('{bid}', '{target_bid}')"
        
        elif action == "upload_file":
            bid = kwargs.get("bid", "")
            file_path = kwargs.get("file_path", "")
            return f"upload_file('{bid}', '{file_path}')"
        
        else:
            # Generic action format
            params = ", ".join([f"{k}={repr(v)}" for k, v in kwargs.items()])
            return f"{action}({params})" if params else f"{action}()"
            
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to format action command: {str(e)}")
        return f"{action}()"


def execute_cursor_action(env, action: str, **kwargs):
    """Execute an action with cursor visualization.
    
    Args:
        env: BrowserGym environment
        action: The action type
        **kwargs: Action parameters
        
    Returns:
        The result of the action execution
    """
    try:
        # Get the browser page from BrowserGym environment
        page = None
        if hasattr(env, 'page') and env.page:
            page = env.page
        elif hasattr(env, '_page') and env._page:
            page = env._page
        elif hasattr(env, 'unwrapped') and hasattr(env.unwrapped, 'page'):
            page = env.unwrapped.page
        elif hasattr(env, 'env') and hasattr(env.env, 'page'):
            page = env.env.page
        
        if not page:
            logging.getLogger(__name__).warning("Could not find browser page for cursor action")
            return env.step(format_action_command(action, **kwargs))
        
        # Handle different action types with cursor visualization
        if action == "click":
            bid = kwargs.get("bid", "")
            if bid:
                # Try to get element position and show cursor movement
                try:
                    # Get element position using JavaScript
                    element_js = f"""
                    (function() {{
                        const element = document.querySelector('[bid="{bid}"]') || 
                                      document.getElementById('{bid}') ||
                                      document.querySelector('#{bid}') ||
                                      document.querySelector('.{bid}') ||
                                      document.querySelector('[name="{bid}"]');
                        if (element) {{
                            const rect = element.getBoundingClientRect();
                            const x = rect.left + rect.width / 2;
                            const y = rect.top + rect.height / 2;
                            return {{x: x, y: y, found: true}};
                        }}
                        return {{x: 0, y: 0, found: false}};
                    }})();
                    """
                    
                    result = page.evaluate(element_js)
                    if result.get('found'):
                        x, y = result['x'], result['y']
                        
                        # Move cursor to element position
                        page.evaluate(f"window.moveSiadaCursor && window.moveSiadaCursor({x}, {y}, true);")
                        
                        # Wait for cursor movement animation
                        time.sleep(0.5)
                        
                        # Show click indicator
                        page.evaluate(f"window.showSiadaClick && window.showSiadaClick({x}, {y});")
                        
                        # Wait for click animation
                        time.sleep(0.3)
                        
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Failed to show cursor for click: {str(e)}")
        
        elif action == "fill":
            bid = kwargs.get("bid", "")
            if bid:
                # Try to get input element position and show cursor movement
                try:
                    element_js = f"""
                    (function() {{
                        const element = document.querySelector('[bid="{bid}"]') || 
                                      document.getElementById('{bid}') ||
                                      document.querySelector('#{bid}') ||
                                      document.querySelector('[name="{bid}"]');
                        if (element) {{
                            const rect = element.getBoundingClientRect();
                            const x = rect.left + rect.width / 2;
                            const y = rect.top + rect.height / 2;
                            return {{x: x, y: y, found: true}};
                        }}
                        return {{x: 0, y: 0, found: false}};
                    }})();
                    """
                    
                    result = page.evaluate(element_js)
                    if result.get('found'):
                        x, y = result['x'], result['y']
                        
                        # Move cursor to input element
                        page.evaluate(f"window.moveSiadaCursor && window.moveSiadaCursor({x}, {y}, true);")
                        
                        # Wait for cursor movement
                        time.sleep(0.5)
                        
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Failed to show cursor for fill: {str(e)}")
        
        # Execute the actual action
        return env.step(format_action_command(action, **kwargs))
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to execute cursor action: {str(e)}")
        return env.step(format_action_command(action, **kwargs))


def format_accessibility_tree(obs: Dict[str, Any]) -> str:
    """Format accessibility tree into a flat, numbered structure.
    
    Args:
        obs: BrowserGym observation dictionary
        
    Returns:
        str: Formatted accessibility tree string
    """
    try:
        if not obs:
            return ""
        
        # Get element properties for bid mapping
        element_props = obs.get('extra_element_properties', {})
        
        # Try to get accessibility tree from different sources
        axtree_data = None
        
        # First try axtree_object (newer format)
        if 'axtree_object' in obs and obs['axtree_object']:
            axtree_data = obs['axtree_object']
        # Fallback to axtree string (legacy format)
        elif 'axtree' in obs and obs['axtree']:
            axtree_str = str(obs['axtree'])
            # Try to parse the string format
            return _format_axtree_from_string(axtree_str)
        
        if not axtree_data:
            return ""
        
        # Format the tree structure
        formatted_lines = []
        formatted_lines.append("============== BEGIN accessibility tree ==============")
        
        # Process nodes if available
        if isinstance(axtree_data, dict) and 'nodes' in axtree_data:
            nodes = axtree_data['nodes']
            if isinstance(nodes, (list, tuple)):
                counter = [1]  # Use list to allow modification in nested function
                _format_nodes_recursive(nodes, formatted_lines, counter, 0, element_props)
        
        formatted_lines.append("============== END accessibility tree ==============")
        
        return "\n".join(formatted_lines)
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to format accessibility tree: {str(e)}")
        return ""


def _format_axtree_from_string(axtree_str: str) -> str:
    """Format accessibility tree from string representation.
    
    Args:
        axtree_str: String representation of accessibility tree
        
    Returns:
        str: Formatted accessibility tree
    """
    try:
        lines = []
        lines.append("============== BEGIN accessibility tree ==============")
        
        # Simple parsing of string format - this is a fallback
        # Extract basic information using regex
        import re
        
        # Look for patterns like: role="button" name="Search" bid="123"
        pattern = r'role="([^"]*)"[^>]*name="([^"]*)"[^>]*(?:bid="([^"]*)")?'
        matches = re.findall(pattern, axtree_str)
        
        counter = 1
        for role, name, bid in matches:
            if role and name:
                bid_info = f" {{bid: '{bid}'}}" if bid else ""
                lines.append(f"[{counter}] {role} '{name}'{bid_info}")
                counter += 1
        
        lines.append("============== END accessibility tree ==============")
        
        return "\n".join(lines)
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to format axtree from string: {str(e)}")
        return ""


def _format_nodes_recursive(nodes, formatted_lines, counter, depth, element_props=None):
    """Recursively format accessibility tree nodes.
    
    Args:
        nodes: List of accessibility tree nodes
        formatted_lines: List to append formatted lines to
        counter: Counter for node numbering (list with single element)
        depth: Current depth for indentation
        element_props: Dictionary of element properties for bid mapping
    """
    try:
        indent = "  " * depth
        
        for node in nodes:
            if not isinstance(node, dict):
                continue
            
            # Extract node information with proper handling of complex structures
            role = node.get('role', 'unknown')
            name = node.get('name', '')
            tag = node.get('tag', '')
            
            # 直接使用browsergym_id作为bid（修复核心问题）
            bid = node.get('browsergym_id', '')
            
            # 如果没有browsergym_id，尝试其他方式（保持兼容性）
            if not bid:
                # 尝试从旧的bid字段获取
                bid = node.get('bid', '')
                
                # 如果还是没有，尝试从element_props中查找
                if not bid and element_props:
                    node_id = node.get('nodeId') or node.get('backendNodeId')
                    if node_id and str(node_id) in element_props:
                        # 检查element_props中是否有对应的browsergym_id
                        element_data = element_props.get(str(node_id), {})
                        if isinstance(element_data, dict) and 'browsergym_id' in element_data:
                            bid = str(element_data['browsergym_id'])
                        else:
                            # 作为最后的备选方案使用nodeId
                            bid = str(node_id)
            
            # Handle complex role structure
            if isinstance(role, dict):
                if 'value' in role:
                    role = role['value']
                elif 'type' in role and role['type'] == 'internalRole':
                    role = role.get('value', 'unknown')
                else:
                    role = 'unknown'
            
            # Handle complex name structure
            if isinstance(name, dict):
                if 'value' in name:
                    name = name['value']
                else:
                    name = ''
            
            # Handle complex tag structure
            if isinstance(tag, dict):
                if 'value' in tag:
                    tag = tag['value']
                else:
                    tag = ''
            
            # Format the line - ensure all parts are strings
            line_parts = [f"[{counter[0]}]", str(role)]
            
            if name:
                line_parts.append(f"'{str(name)}'")
            
            if tag:
                line_parts.append(f"<{str(tag)}>")
            
            if bid:
                line_parts.append(f"{{bid: '{str(bid)}'}}")
            
            formatted_line = indent + " ".join(line_parts)
            formatted_lines.append(formatted_line)
            counter[0] += 1
            
            # Process children if they exist
            if 'children' in node and node['children']:
                _format_nodes_recursive(node['children'], formatted_lines, counter, depth + 1, element_props)
                
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to format nodes recursively: {str(e)}")


def extract_bids_from_observation(obs: Dict[str, Any]) -> list[str]:
    """Extract available browser element IDs (bids) from observation.
    
    优先使用browsergym_id，确保与accessibility tree一致
    
    Args:
        obs: BrowserGym observation dictionary
        
    Returns:
        list[str]: List of available bid strings
    """
    try:
        bids = []
        
        # 优先从accessibility tree object中提取browsergym_id
        if 'axtree_object' in obs and obs['axtree_object']:
            axtree_obj = obs['axtree_object']
            if isinstance(axtree_obj, dict) and 'nodes' in axtree_obj:
                nodes = axtree_obj['nodes']
                if isinstance(nodes, (list, tuple)):
                    def extract_browsergym_ids(nodes_list):
                        for node in nodes_list:
                            if isinstance(node, dict):
                                # 优先使用browsergym_id
                                browsergym_id = node.get('browsergym_id')
                                if browsergym_id:
                                    bids.append(str(browsergym_id))
                                
                                # 递归处理子节点
                                children = node.get('childIds', [])
                                if children:
                                    # 在nodes中查找子节点
                                    child_nodes = [n for n in nodes_list if n.get('nodeId') in children]
                                    extract_browsergym_ids(child_nodes)
                    
                    extract_browsergym_ids(nodes)
        
        # 备选方案：从extra_element_properties提取
        if not bids and 'extra_element_properties' in obs and obs['extra_element_properties']:
            element_props = obs['extra_element_properties']
            if isinstance(element_props, dict):
                for prop_data in element_props.values():
                    if isinstance(prop_data, dict) and 'browsergym_id' in prop_data:
                        bids.append(str(prop_data['browsergym_id']))
                
                # 如果没有browsergym_id，使用keys作为备选
                if not bids:
                    bids.extend(element_props.keys())
        
        # 最后的备选方案：从legacy axtree field提取
        if not bids and 'axtree' in obs and obs['axtree']:
            axtree_str = str(obs['axtree'])
            import re
            # 优先查找browsergym_id
            browsergym_id_pattern = r'browsergym_id["\']:\s*["\']([^"\']+)["\']'
            matches = re.findall(browsergym_id_pattern, axtree_str)
            if matches:
                bids.extend(matches)
            else:
                # 备选：查找bid属性
                bid_pattern = r'bid="([^"]+)"'
                matches = re.findall(bid_pattern, axtree_str)
                bids.extend(matches)
        
        # 去重并返回
        return list(set(bids))
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to extract bids from observation: {str(e)}")
        return []


def validate_action_parameters(action: str, **kwargs) -> tuple[bool, str]:
    """Validate action parameters.
    
    Args:
        action: The action type
        **kwargs: Action parameters
        
    Returns:
        tuple[bool, str]: (is_valid, error_message)
    """
    try:
        if action in ["click", "fill", "select_option", "press", "hover", "focus", "clear", "dblclick"]:
            if not kwargs.get("bid"):
                return False, f"Action '{action}' requires 'bid' parameter"
        
        if action == "fill":
            if not kwargs.get("value"):
                return False, "Action 'fill' requires 'value' parameter"
        
        if action == "select_option":
            if not kwargs.get("value"):
                return False, "Action 'select_option' requires 'value' parameter"
        
        if action == "press":
            if not kwargs.get("key"):
                return False, "Action 'press' requires 'key' parameter"
        
        if action == "drag_and_drop":
            if not kwargs.get("bid") or not kwargs.get("target_bid"):
                return False, "Action 'drag_and_drop' requires both 'bid' and 'target_bid' parameters"
        
        if action == "upload_file":
            if not kwargs.get("bid") or not kwargs.get("file_path"):
                return False, "Action 'upload_file' requires both 'bid' and 'file_path' parameters"
        
        return True, ""
        
    except Exception as e:
        return False, f"Error validating parameters: {str(e)}"


def create_browsergym_result(obs: Dict[str, Any], success: bool = True, error: Optional[str] = None, action: str = "screenshot") -> Dict[str, Any]:
    """Create a standardized result dictionary for BrowserGym operations.
    
    Args:
        obs: BrowserGym observation dictionary
        success: Whether the operation was successful
        error: Error message if operation failed
        action: The action type for screenshot naming
        
    Returns:
        Dict[str, Any]: Standardized result dictionary
    """
    try:
        result = {
            "success": success,
            "screenshot": "",
            "axtree": "",
            "page_info": {},
            "available_bids": [],
            "error": error,
            "_obs": obs  # Store original observation for later use
        }
        
        if obs:
            # Convert screenshot to base64 if available
            if 'screenshot' in obs and obs['screenshot'] is not None:
                result["screenshot"] = image_to_base64_url(obs['screenshot'])
                
                # Save screenshot to file if conversion was successful
                if result["screenshot"] and success:
                    # Extract base64 data (remove data URL prefix if present)
                    screenshot_data = result["screenshot"].split(",")[-1] if "," in result["screenshot"] else result["screenshot"]
                    save_screenshot_to_file(screenshot_data, action)
            
            # Extract accessibility tree (try both old and new formats)
            if 'axtree' in obs:
                result["axtree"] = str(obs['axtree']) if obs['axtree'] else ""
            elif 'axtree_object' in obs:
                result["axtree"] = str(obs['axtree_object']) if obs['axtree_object'] else ""
            
            # Extract page info (construct from available fields)
            page_info = {}
            if 'url' in obs:
                page_info['url'] = obs['url']
            if 'open_pages_titles' in obs and obs['open_pages_titles']:
                titles = obs['open_pages_titles']
                if titles and len(titles) > 0:
                    page_info['title'] = titles[0] if isinstance(titles, (list, tuple)) else str(titles)
            if 'focused_element_bid' in obs:
                page_info['focused_element_bid'] = obs['focused_element_bid']
            if 'last_action' in obs:
                page_info['last_action'] = obs['last_action']
            if 'last_action_error' in obs:
                page_info['last_action_error'] = obs['last_action_error']
            
            result["page_info"] = page_info
            
            # Extract available bids
            result["available_bids"] = extract_bids_from_observation(obs)
        
        return result
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to create BrowserGym result: {str(e)}")
        return {
            "success": False,
            "screenshot": "",
            "axtree": "",
            "page_info": {},
            "available_bids": [],
            "error": f"Error creating result: {str(e)}",
            "_obs": None
        }


def save_screenshot_to_file(base64_data: str, action: str = "screenshot") -> Optional[str]:
    """
    保存截屏到文件系统
    
    Args:
        base64_data: base64编码的图片数据
        action: 操作类型，用于文件命名
        
    Returns:
        保存的文件路径，如果保存失败则返回None
    """
    try:
        # 创建screenshots目录
        screenshots_dir = "screenshots"
        if not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir)
        
        # 生成文件名：时间戳_操作类型.png
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{action}.png"
        filepath = os.path.join(screenshots_dir, filename)
        
        # 解码base64数据并保存
        image_data = base64.b64decode(base64_data)
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        logging.getLogger(__name__).info(f"Screenshot saved to: {filepath}")
        return filepath
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to save screenshot: {str(e)}")
        return None
