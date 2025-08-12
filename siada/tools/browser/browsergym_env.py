"""
BrowserGym environment management for browser automation.

This module provides a singleton BrowserGym environment manager that handles
the lifecycle of browser environments using the Gymnasium interface.
"""

import logging
import threading
import asyncio
import queue
import time
from typing import Optional, Any, Dict, Callable, Tuple
import gymnasium as gym
from browsergym.core.action.highlevel import HighLevelActionSet


class BrowserGymWorkerThread:
    """Dedicated worker thread for BrowserGym operations."""
    
    def __init__(self):
        self.env: Optional[gym.Env] = None
        self.action_set: Optional[HighLevelActionSet] = None
        self.logger = logging.getLogger(__name__)
        self._initialized = False
        self._stop_event = threading.Event()
        self._command_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._thread = None
        
    def start(self):
        """Start the worker thread."""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._thread.start()
            self.logger.info("BrowserGym worker thread started")
    
    def stop(self):
        """Stop the worker thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            self.logger.info("BrowserGym worker thread stopped")
    
    def _worker_loop(self):
        """Main worker thread loop."""
        while not self._stop_event.is_set():
            try:
                # Wait for commands with timeout
                try:
                    command = self._command_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Process command
                try:
                    result = self._process_command(command)
                    self._result_queue.put(('success', result))
                except Exception as e:
                    self.logger.error(f"Worker thread error: {str(e)}")
                    self._result_queue.put(('error', str(e)))
                finally:
                    self._command_queue.task_done()
                    
            except Exception as e:
                self.logger.error(f"Worker thread loop error: {str(e)}")
    
    def _process_command(self, command: Dict[str, Any]) -> Any:
        """Process a command in the worker thread."""
        cmd_type = command.get('type')
        
        if cmd_type == 'initialize':
            return self._initialize_env(command['start_url'], command['headless'])
        elif cmd_type == 'step':
            return self._step_env(command['action'])
        elif cmd_type == 'get_observation':
            return self._get_observation()
        elif cmd_type == 'close':
            return self._close_env()
        elif cmd_type == 'is_initialized':
            return self._initialized
        else:
            raise ValueError(f"Unknown command type: {cmd_type}")
    
    def _initialize_env(self, start_url: str, headless: bool) -> bool:
        """Initialize the environment in worker thread."""
        try:
            if self._initialized and self.env is not None:
                self.logger.debug("BrowserGym environment already initialized")
                return True
            
            # Initialize action set
            self.action_set = HighLevelActionSet(
                subsets=["bid"],  # Use bid (browser element ID) subset
                strict=False,     # Less strict parsing
                multiaction=False # Single action at a time
            )
            
            # Create the environment
            self.env = gym.make(
                "browsergym/openended",
                task_kwargs={"start_url": start_url},
                headless=headless
            )
            
            # Reset the environment to initial state
            obs, info = self.env.reset()
            
            # Inject cursor functionality
            self._inject_cursor_functionality()
            
            self._initialized = True
            self.logger.info(f"BrowserGym environment initialized in worker thread with start_url: {start_url}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Worker thread initialization failed: {str(e)}")
            self.env = None
            self.action_set = None
            self._initialized = False
            raise
    
    def _step_env(self, action: str) -> Tuple[Dict[str, Any], float, bool, bool, Dict[str, Any]]:
        """Execute step in worker thread."""
        if not self._initialized or self.env is None:
            raise RuntimeError("BrowserGym environment not initialized")
        
        try:
            self.logger.debug(f"Executing action in worker thread: {action}")
            
            # Parse action to extract type and parameters for cursor visualization
            action_type, action_params = self._parse_action_string(action)
            
            # Execute action with cursor visualization if possible
            if action_type in ['click', 'fill'] and action_params.get('bid'):
                return self._execute_action_with_cursor(action_type, action_params, action)
            else:
                return self.env.step(action)
                
        except Exception as e:
            self.logger.error(f"Worker thread step failed: {str(e)}")
            raise
    
    def _parse_action_string(self, action: str) -> tuple[str, dict]:
        """Parse action string to extract action type and parameters."""
        try:
            # Simple parsing for common actions
            if action.startswith('click('):
                # Extract bid from click('bid', ...)
                import re
                match = re.search(r"click\('([^']+)'", action)
                if match:
                    return 'click', {'bid': match.group(1)}
            elif action.startswith('fill('):
                # Extract bid from fill('bid', 'value')
                import re
                match = re.search(r"fill\('([^']+)',\s*'([^']*)'", action)
                if match:
                    return 'fill', {'bid': match.group(1), 'value': match.group(2)}
            
            return 'unknown', {}
        except Exception as e:
            self.logger.warning(f"Failed to parse action string: {str(e)}")
            return 'unknown', {}
    
    def _execute_action_with_cursor(self, action_type: str, params: dict, original_action: str):
        """Execute action with cursor visualization."""
        try:
            # Get the browser page from BrowserGym environment
            page = None
            if hasattr(self.env, 'page') and self.env.page:
                page = self.env.page
            elif hasattr(self.env, '_page') and self.env._page:
                page = self.env._page
            elif hasattr(self.env, 'unwrapped') and hasattr(self.env.unwrapped, 'page'):
                page = self.env.unwrapped.page
            elif hasattr(self.env, 'env') and hasattr(self.env.env, 'page'):
                page = self.env.env.page
            
            if not page:
                self.logger.warning("Could not find browser page for cursor visualization")
                return self.env.step(original_action)
            
            bid = params.get('bid', '')
            if not bid:
                return self.env.step(original_action)
            
            # Try to get element position and show cursor movement
            # Wrap in try-catch to handle greenlet thread switching errors
            try:
                # Get element position using JavaScript
                element_js = f"""
                (function() {{
                    const element = document.querySelector('[browsergym_id="{bid}"]') || 
                                  document.querySelector('[bid="{bid}"]') ||
                                  document.getElementById('{bid}') ||
                                  document.querySelector('#{bid}') ||
                                  document.querySelector('.{bid}') ||
                                  document.querySelector('[name="{bid}"]') ||
                                  document.querySelector('[data-bid="{bid}"]');
                    if (element) {{
                        const rect = element.getBoundingClientRect();
                        const x = rect.left + rect.width / 2;
                        const y = rect.top + rect.height / 2;
                        return {{x: x, y: y, found: true}};
                    }}
                    return {{x: 0, y: 0, found: false}};
                }})();
                """
                
                # Use a safer approach for JavaScript evaluation
                try:
                    result = page.evaluate(element_js)
                    if result and result.get('found'):
                        x, y = result['x'], result['y']
                        
                        # Move cursor to element position (with error handling)
                        try:
                            page.evaluate(f"window.moveSiadaCursor && window.moveSiadaCursor({x}, {y}, true);")
                        except Exception as cursor_error:
                            self.logger.debug(f"Cursor movement failed (non-critical): {str(cursor_error)}")
                        
                        # Wait for cursor movement animation
                        import time
                        time.sleep(0.3)  # Reduced sleep time
                        
                        if action_type == 'click':
                            # Show click indicator (with error handling)
                            try:
                                page.evaluate(f"window.showSiadaClick && window.showSiadaClick({x}, {y});")
                                time.sleep(0.2)  # Reduced sleep time
                            except Exception as click_error:
                                self.logger.debug(f"Click indicator failed (non-critical): {str(click_error)}")
                
                except Exception as js_error:
                    # Log JavaScript evaluation errors as debug (non-critical)
                    self.logger.debug(f"JavaScript evaluation failed (non-critical): {str(js_error)}")
                    
            except Exception as e:
                # Log cursor visualization errors as debug (non-critical)
                self.logger.debug(f"Cursor visualization failed (non-critical): {str(e)}")
            
            # Execute the actual action (this is the critical part)
            return self.env.step(original_action)
            
        except Exception as e:
            self.logger.error(f"Failed to execute action with cursor: {str(e)}")
            return self.env.step(original_action)
    
    def _get_observation(self) -> Optional[Dict[str, Any]]:
        """Get current observation in worker thread."""
        if not self._initialized or self.env is None:
            return None
        
        try:
            return getattr(self.env, '_last_obs', None)
        except Exception as e:
            self.logger.error(f"Worker thread get observation failed: {str(e)}")
            return None
    
    def _close_env(self) -> bool:
        """Close environment in worker thread."""
        try:
            if self.env is not None:
                self.env.close()
                self.logger.info("BrowserGym environment closed in worker thread")
            
            self.env = None
            self.action_set = None
            self._initialized = False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Worker thread close failed: {str(e)}")
            return False
    
    def execute_command(self, command: Dict[str, Any], timeout: float = 30.0) -> Any:
        """Execute a command and wait for result."""
        # Ensure worker thread is running
        self.start()
        
        # Send command
        self._command_queue.put(command)
        
        # Wait for result
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                status, result = self._result_queue.get(timeout=1.0)
                if status == 'success':
                    return result
                else:
                    raise RuntimeError(result)
            except queue.Empty:
                continue
        
        raise TimeoutError(f"Command timed out after {timeout} seconds")
    
    def _inject_cursor_functionality(self):
        """Inject cursor functionality into the browser page."""
        try:
            # Get the browser page from BrowserGym environment
            if hasattr(self.env, 'page') and self.env.page:
                page = self.env.page
            elif hasattr(self.env, '_page') and self.env._page:
                page = self.env._page
            elif hasattr(self.env, 'unwrapped') and hasattr(self.env.unwrapped, 'page'):
                page = self.env.unwrapped.page
            else:
                # Try to access through the environment's internal structure
                if hasattr(self.env, 'env') and hasattr(self.env.env, 'page'):
                    page = self.env.env.page
                else:
                    self.logger.warning("Could not find browser page object for cursor injection")
                    return
            
            # JavaScript code for cursor functionality
            cursor_js = """
            (function() {
                // Remove any existing cursors
                const existingCursors = document.querySelectorAll('.siada-cursor, .siada-cursor-trail, .siada-click-indicator');
                existingCursors.forEach(el => el.remove());
                
                // Create cursor styles
                const style = document.createElement('style');
                style.textContent = `
                    .siada-cursor {
                        position: fixed;
                        width: 20px;
                        height: 20px;
                        background: rgba(0, 123, 255, 0.8);
                        border: 2px solid rgba(255, 255, 255, 0.9);
                        border-radius: 50%;
                        pointer-events: none;
                        z-index: 999999;
                        transition: all 0.3s ease;
                        box-shadow: 0 0 10px rgba(0, 123, 255, 0.5);
                        animation: pulse 2s infinite;
                    }
                    
                    .siada-cursor-trail {
                        position: fixed;
                        width: 16px;
                        height: 16px;
                        background: rgba(40, 167, 69, 0.7);
                        border: 1px solid rgba(255, 255, 255, 0.8);
                        border-radius: 50%;
                        pointer-events: none;
                        z-index: 999998;
                        transition: all 0.8s cubic-bezier(0.25, 0.46, 0.45, 0.94);
                    }
                    
                    .siada-click-indicator {
                        position: fixed;
                        width: 40px;
                        height: 40px;
                        border: 3px solid rgba(220, 53, 69, 0.8);
                        border-radius: 50%;
                        pointer-events: none;
                        z-index: 999997;
                        animation: clickRipple 0.6s ease-out;
                    }
                    
                    @keyframes pulse {
                        0% { transform: scale(1); opacity: 0.8; }
                        50% { transform: scale(1.1); opacity: 1; }
                        100% { transform: scale(1); opacity: 0.8; }
                    }
                    
                    @keyframes clickRipple {
                        0% { transform: scale(0.5); opacity: 1; }
                        100% { transform: scale(2); opacity: 0; }
                    }
                `;
                document.head.appendChild(style);
                
                // Create main cursor
                const cursor = document.createElement('div');
                cursor.className = 'siada-cursor';
                cursor.style.left = '50%';
                cursor.style.top = '50%';
                cursor.style.transform = 'translate(-50%, -50%)';
                document.body.appendChild(cursor);
                
                // Store cursor reference globally
                window.siadaCursor = cursor;
                
                // Function to move cursor
                window.moveSiadaCursor = function(x, y, showTrail = true) {
                    if (!window.siadaCursor) return;
                    
                    const currentX = parseInt(window.siadaCursor.style.left) || window.innerWidth / 2;
                    const currentY = parseInt(window.siadaCursor.style.top) || window.innerHeight / 2;
                    
                    if (showTrail) {
                        // Create trail cursor
                        const trail = document.createElement('div');
                        trail.className = 'siada-cursor-trail';
                        trail.style.left = currentX + 'px';
                        trail.style.top = currentY + 'px';
                        trail.style.transform = 'translate(-50%, -50%)';
                        document.body.appendChild(trail);
                        
                        // Animate trail to new position
                        setTimeout(() => {
                            trail.style.left = x + 'px';
                            trail.style.top = y + 'px';
                        }, 10);
                        
                        // Remove trail after animation
                        setTimeout(() => {
                            if (trail.parentNode) {
                                trail.parentNode.removeChild(trail);
                            }
                        }, 800);
                    }
                    
                    // Move main cursor
                    window.siadaCursor.style.left = x + 'px';
                    window.siadaCursor.style.top = y + 'px';
                };
                
                // Function to show click indicator
                window.showSiadaClick = function(x, y) {
                    const clickIndicator = document.createElement('div');
                    clickIndicator.className = 'siada-click-indicator';
                    clickIndicator.style.left = x + 'px';
                    clickIndicator.style.top = y + 'px';
                    clickIndicator.style.transform = 'translate(-50%, -50%)';
                    document.body.appendChild(clickIndicator);
                    
                    // Remove click indicator after animation
                    setTimeout(() => {
                        if (clickIndicator.parentNode) {
                            clickIndicator.parentNode.removeChild(clickIndicator);
                        }
                    }, 600);
                };
                
                console.log('Siada cursor functionality injected successfully');
            })();
            """
            
            # Execute the JavaScript
            page.evaluate(cursor_js)
            self.logger.info("Cursor functionality injected successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to inject cursor functionality: {str(e)}")


class BrowserGymEnv:
    """Singleton BrowserGym environment manager.
    
    This class manages a single BrowserGym environment instance that can be
    shared across multiple browser operations while maintaining thread safety.
    """
    
    _instance: Optional['BrowserGymEnv'] = None
    _lock = threading.Lock()
    
    def __init__(self):
        """Initialize the BrowserGym environment manager."""
        self.logger = logging.getLogger(__name__)
        self._worker = BrowserGymWorkerThread()
        
    @classmethod
    def get_instance(cls) -> 'BrowserGymEnv':
        """Get the singleton instance of BrowserGymEnv.
        
        Returns:
            BrowserGymEnv: The singleton instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def initialize(self, start_url: str = "https://www.google.com", headless: bool = False) -> bool:
        """Initialize the BrowserGym environment.
        
        Args:
            start_url: The initial URL to navigate to
            headless: Whether to run in headless mode
            
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        try:
            command = {
                'type': 'initialize',
                'start_url': start_url,
                'headless': headless
            }
            return self._worker.execute_command(command)
        except Exception as e:
            self.logger.error(f"Failed to initialize BrowserGym environment: {str(e)}")
            return False
    
    def step(self, action: str) -> tuple[Dict[str, Any], float, bool, bool, Dict[str, Any]]:
        """Execute an action in the BrowserGym environment.
        
        Args:
            action: The action string to execute
            
        Returns:
            tuple: (observation, reward, terminated, truncated, info)
            
        Raises:
            RuntimeError: If environment is not initialized
        """
        try:
            command = {
                'type': 'step',
                'action': action
            }
            return self._worker.execute_command(command)
        except Exception as e:
            self.logger.error(f"Failed to execute action '{action}': {str(e)}")
            raise
    
    def get_current_observation(self) -> Optional[Dict[str, Any]]:
        """Get the current observation from the environment.
        
        Returns:
            Optional[Dict[str, Any]]: Current observation or None if not available
        """
        try:
            command = {'type': 'get_observation'}
            return self._worker.execute_command(command)
        except Exception as e:
            self.logger.error(f"Failed to get current observation: {str(e)}")
            return None
    
    def close(self) -> bool:
        """Close the BrowserGym environment and clean up resources.
        
        Returns:
            bool: True if cleanup was successful, False otherwise
        """
        try:
            command = {'type': 'close'}
            result = self._worker.execute_command(command)
            self._worker.stop()
            return result
        except Exception as e:
            self.logger.error(f"Error closing BrowserGym environment: {str(e)}")
            return False
    
    def is_initialized(self) -> bool:
        """Check if the environment is initialized.
        
        Returns:
            bool: True if initialized, False otherwise
        """
        try:
            command = {'type': 'is_initialized'}
            return self._worker.execute_command(command)
        except Exception as e:
            self.logger.error(f"Failed to check initialization status: {str(e)}")
            return False
    
    def get_action_description(self) -> str:
        """Get description of available actions.
        
        Returns:
            str: Description of the action space
        """
        # This doesn't need to go through the worker thread
        try:
            from browsergym.core.action.highlevel import HighLevelActionSet
            action_set = HighLevelActionSet(
                subsets=["bid"],
                strict=False,
                multiaction=False
            )
            return action_set.describe(with_long_description=True, with_examples=True)
        except Exception as e:
            self.logger.error(f"Failed to get action description: {str(e)}")
            return "Failed to get action description"
    
    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (mainly for testing purposes)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
                cls._instance = None
