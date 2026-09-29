"""
BrowserGym environment management for browser automation.

This module provides a singleton BrowserGym environment manager that handles
the lifecycle of browser environments using the Gymnasium interface.
The chat functionality is disabled to prevent UI assistant chat windows.
"""

import atexit
import threading
import queue
import time
from typing import Optional, Any, Dict, Tuple
import gymnasium as gym
from browsergym.core.action.highlevel import HighLevelActionSet
from browsergym.core.env import BrowserEnv
from browsergym.core.task import OpenEndedTask
from siada.foundation.logging import logger 


class NoUIChatPatch:
    """Replacement Chat class that doesn't create any UI."""
    
    def __init__(self, *args, **kwargs):
        """Initialize without creating any UI."""
        self.messages = []
        self.recording_start_time = None
        self.page = None
    
    def add_message(self, role: str, msg: str):
        """Add message to internal list but don't display anything."""
        self.messages.append({
            "role": role,
            "message": msg,
            "timestamp": time.time()
        })
    
    def wait_for_user_message(self):
        """Do nothing - no waiting."""
        pass
    
    def close(self):
        """Do nothing - no cleanup needed."""
        pass


def _apply_chat_patch():
    """Apply monkey patch to disable Chat UI creation."""
    import browsergym.core.chat
    import browsergym.core.env
    
    browsergym.core.chat.Chat = NoUIChatPatch
    browsergym.core.env.Chat = NoUIChatPatch


class BrowserGymWorkerThread:
    """Dedicated worker thread for BrowserGym operations."""
    
    def __init__(self):
        self.env: Optional[gym.Env] = None
        self.action_set: Optional[HighLevelActionSet] = None
        self._initialized = False
        self._stop_event = threading.Event()
        self._command_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._thread = None
        self._browser_pids: set = set()  # Track browser process PIDs spawned by this environment
        
    def start(self):
        """Start the worker thread."""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._thread.start()
    
    def stop(self):
        """Stop the worker thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
    
    def _worker_loop(self):
        """Main worker thread loop."""
        # Create and set an event loop for this thread
        # This is required by Playwright/BrowserGym which uses asyncio internally
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            while not self._stop_event.is_set():
                try:
                    try:
                        command = self._command_queue.get(timeout=1.0)
                    except queue.Empty:
                        continue
                    
                    try:
                        result = self._process_command(command)
                        self._result_queue.put(('success', result))
                    except Exception as e:
                        self._result_queue.put(('error', str(e)))
                    finally:
                        self._command_queue.task_done()
                        
                except Exception:
                    pass  # Silently continue on worker thread errors
        finally:
            # Clean up the event loop when the worker thread exits
            loop.close()
    
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
                return True
            
            # Apply chat patch to disable UI
            _apply_chat_patch()
            
            # Chromium path should already be set by browser_operate_by_gym
            # If not set, the environment variable will be checked
            import os
            if 'PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH' in os.environ:
                logger.debug(f"Using Chromium at: {os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH']}")
            
            # Initialize action set
            self.action_set = HighLevelActionSet(
                subsets=["bid"],
                strict=False,
                multiaction=False
            )
            
            # Create the environment using patched Chat class
            # Set larger viewport only if start_url contains /card suffix
            env_kwargs = {
                "task_entrypoint": OpenEndedTask,
                "task_kwargs": {"start_url": start_url},
                "headless": headless,
                "wait_for_user_message": False
            }
            
            if "card=true" in start_url:
                env_kwargs["viewport"] = {"width": 1080, "height": 1440}
            
            self.env = BrowserEnv(**env_kwargs)
            
            # Reset the environment to initial state
            obs, info = self.env.reset()
            
            # Capture browser PIDs spawned by this Python process
            # Since _get_chromium_pids only finds child processes of current Python process,
            # no need to calculate difference - all found PIDs belong to our browser
            time.sleep(0.5)  # Brief wait for browser processes to fully start
            self._browser_pids = self._get_chromium_pids()
            logger.info(f"Captured browser PIDs: {self._browser_pids}")
            
            # Inject cursor functionality
            self._inject_cursor_functionality()
            
            self._initialized = True
            return True
            
        except Exception as e:
            self.env = None
            self.action_set = None
            self._initialized = False
            raise
    
    def _step_env(self, action: str) -> Tuple[Dict[str, Any], float, bool, bool, Dict[str, Any]]:
        """Execute step in worker thread."""
        if not self._initialized or self.env is None:
            raise RuntimeError("BrowserGym environment not initialized")
        
        # Parse action for cursor visualization
        action_type, action_params = self._parse_action_string(action)
        
        # Execute action with cursor visualization if possible
        if action_type in ['click', 'fill'] and action_params.get('bid'):
            return self._execute_action_with_cursor(action_type, action_params, action)
        else:
            return self.env.step(action)
    
    def _parse_action_string(self, action: str) -> tuple[str, dict]:
        """Parse action string to extract action type and parameters."""
        try:
            if action.startswith('click('):
                import re
                match = re.search(r"click\('([^']+)'", action)
                if match:
                    return 'click', {'bid': match.group(1)}
            elif action.startswith('fill('):
                import re
                match = re.search(r"fill\('([^']+)',\s*'([^']*)'", action)
                if match:
                    return 'fill', {'bid': match.group(1), 'value': match.group(2)}
            
            return 'unknown', {}
        except Exception:
            return 'unknown', {}
    
    def _execute_action_with_cursor(self, action_type: str, params: dict, original_action: str):
        """Execute action with cursor visualization."""
        try:
            # Get the browser page
            page = self._get_browser_page()
            if not page:
                return self.env.step(original_action)
            
            bid = params.get('bid', '')
            if not bid:
                return self.env.step(original_action)
            
            # Show cursor movement and click indicator
            try:
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
                
                result = page.evaluate(element_js)
                if result and result.get('found'):
                    x, y = result['x'], result['y']
                    
                    # Move cursor and show click indicator
                    try:
                        page.evaluate(f"window.moveSiadaCursor && window.moveSiadaCursor({x}, {y}, true);")
                        time.sleep(0.3)
                        
                        if action_type == 'click':
                            page.evaluate(f"window.showSiadaClick && window.showSiadaClick({x}, {y});")
                            time.sleep(0.2)
                    except Exception:
                        pass  # Non-critical cursor operations
                
            except Exception:
                pass  # Non-critical JavaScript operations
            
            return self.env.step(original_action)
            
        except Exception:
            return self.env.step(original_action)
    
    def _get_browser_page(self):
        """Get the browser page from the environment."""
        if hasattr(self.env, 'page') and self.env.page:
            return self.env.page
        elif hasattr(self.env, '_page') and self.env._page:
            return self.env._page
        elif hasattr(self.env, 'unwrapped') and hasattr(self.env.unwrapped, 'page'):
            return self.env.unwrapped.page
        elif hasattr(self.env, 'env') and hasattr(self.env.env, 'page'):
            return self.env.env.page
        return None
    
    def _get_observation(self) -> Optional[Dict[str, Any]]:
        """Get current observation in worker thread."""
        if not self._initialized or self.env is None:
            return None
        
        try:
            return getattr(self.env, '_last_obs', None)
        except Exception:
            return None
    
    def _close_env(self) -> bool:
        """Close environment in worker thread."""
        try:
            if self.env is not None:
                # Get page reference for cleanup
                page = self._get_browser_page()
                
                # Clean up custom elements and event listeners on the page
                if page:
                    try:
                        cleanup_js = """
                        (function() {
                            // Remove all Siada related elements
                            const elements = document.querySelectorAll('.siada-cursor, .siada-cursor-trail, .siada-click-indicator');
                            elements.forEach(el => el.remove());
                            
                            // Clean up global variables
                            delete window.siadaCursor;
                            delete window.moveSiadaCursor;
                            delete window.showSiadaClick;
                        })();
                        """
                        page.evaluate(cleanup_js)
                    except Exception:
                        pass  # Ignore cleanup errors
                
                # Close the environment
                try:
                    self.env.close()
                except Exception:
                    # If normal close fails, try to force kill the browser process
                    try:
                        if hasattr(self.env, 'browser') and self.env.browser:
                            self.env.browser.close()
                    except Exception:
                        pass
            
            self.env = None
            self.action_set = None
            self._initialized = False
            return True
            
        except Exception:
            # Even on exception, mark as uninitialized
            self.env = None
            self.action_set = None
            self._initialized = False
            return False
    
    def execute_command(self, command: Dict[str, Any], timeout: float = 30.0) -> Any:
        """Execute a command and wait for result."""
        self.start()
        self._command_queue.put(command)
        
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

    def _get_chromium_pids(self) -> set:
        """Get all chromium/chrome process PIDs spawned by current Python process.
        
        Uses psutil to traverse the process tree starting from current Python process,
        finding all child processes that are browser-related (chrome, chromium, msedge).
        This approach is more reliable than depending on Playwright's internal API.
        
        Returns:
            A set of PIDs for browser processes spawned by this Python process
        """
        import psutil
        import os
        
        pids = set()
        try:
            current_pid = os.getpid()
            parent = psutil.Process(current_pid)
            
            # Recursively find all child processes
            for child in parent.children(recursive=True):
                try:
                    name = child.name().lower()
                    # Match common browser process names
                    if any(browser in name for browser in ['chrome', 'chromium', 'msedge', 'headless']):
                        pids.add(child.pid)
                        logger.debug(f"Found browser child process: PID={child.pid}, name={child.name()}")
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # Process may have terminated or we don't have permission
                    continue
        except Exception as e:
            logger.debug(f"Error getting chromium PIDs via psutil: {e}")
        
        return pids
    
    def _capture_browser_pid(self) -> Optional[int]:
        """Capture the main browser process PID from child processes.
        
        This method uses psutil to find browser processes spawned by the current
        Python process. It returns the first (usually main) browser process PID found.
        
        Returns:
            The browser process PID if found, None otherwise
        """
        try:
            browser_pids = self._get_chromium_pids()
            if browser_pids:
                # Return the first (main) browser PID
                main_pid = min(browser_pids)  # Usually the main process has the smallest PID
                logger.debug(f"Captured browser PID via psutil: {main_pid}")
                return main_pid
            
            logger.debug("Could not capture browser PID via psutil - no browser child processes found")
            return None
            
        except Exception as e:
            logger.debug(f"Error capturing browser PID: {e}")
            return None

    def _inject_cursor_functionality(self):
        """Inject cursor functionality into the browser page."""
        try:
            page = self._get_browser_page()
            if not page:
                return
            
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
            })();
            """
            
            page.evaluate(cursor_js)
            
        except Exception:
            pass  # Non-critical cursor injection


class BrowserGymEnvManager:
    """Singleton BrowserGym environment manager.
    
    This class manages a single BrowserGym environment instance that can be
    shared across multiple browser operations while maintaining thread safety.
    The chat functionality is automatically disabled to prevent UI windows.
    """
    
    _instance: Optional['BrowserGymEnvManager'] = None
    _lock = threading.Lock()
    
    def __init__(self):
        """Initialize the BrowserGym environment manager."""
        self._worker = BrowserGymWorkerThread()
        
        # Register cleanup hook to kill browser processes on program exit
        atexit.register(self._kill_chromium_processes)
        
    @classmethod
    def get_instance(cls) -> 'BrowserGymEnvManager':
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
            logger.error(f"Failed to initialize BrowserGym environment: {str(e)}")
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
            logger.error(f"Failed to execute action '{action}': {str(e)}")
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
            logger.error(f"Failed to get current observation: {str(e)}")
            return None
    
    def close(self, timeout: float = 30.0) -> bool:
        """Close the BrowserGym environment and clean up resources.
        
        Note: We intentionally do NOT stop the worker thread or reset the singleton
        instance here. This is because Playwright maintains global state (Selectors)
        that is bound to the event loop created in the worker thread. If we stop
        the worker thread, the event loop is destroyed but Playwright's global state
        still references it, causing "no running event loop" errors on browser reopen.
        
        Instead, we only close the BrowserEnv but keep the worker thread running.
        The worker thread is a daemon thread and will be automatically terminated
        when the main process exits.
        
        Args:
            timeout: Maximum time to wait for close operation (default 30s)
        
        Returns:
            bool: True if cleanup was successful, False otherwise
        """
        try:
            command = {'type': 'close'}
            result = self._worker.execute_command(command, timeout=timeout)
            # NOTE: Do NOT call self._worker.stop() here!
            # This keeps the event loop alive for Playwright's global Selectors object
            return result
        except Exception as e:
            logger.error(f"Error closing BrowserGym environment: {str(e)}")
            return False
    
    def _kill_chromium_processes(self):
        """Forcefully kill browser processes spawned by this environment.
        
        This is a last resort when normal close fails and we need to exit immediately.
        Uses the captured _browser_pids set which already contains all browser processes
        (main process + renderer/GPU/utility processes) discovered via psutil.
        This approach avoids collateral damage to other browser instances.
        """
        import os
        import signal
        
        try:
            browser_pids = set()
            
            # Get the browser PIDs we captured during initialization
            if self._worker and self._worker._browser_pids:
                browser_pids = self._worker._browser_pids.copy()
            
            if browser_pids:
                logger.info(f"Killing {len(browser_pids)} browser processes: {browser_pids}")
                
                # Kill all captured browser processes
                # Sort in reverse order to kill child processes before parent processes
                for pid in sorted(browser_pids, reverse=True):
                    try:
                        os.kill(pid, signal.SIGKILL)
                        logger.debug(f"Killed browser process: {pid}")
                    except ProcessLookupError:
                        pass  # Process already terminated
                    except PermissionError:
                        logger.warning(f"No permission to kill process {pid}")
                    except Exception as e:
                        logger.debug(f"Error killing process {pid}: {e}")
                    
            else:
                # Fallback: No PIDs captured, log a warning but don't use pkill
                # to avoid killing unrelated browser processes
                logger.warning(
                    "No browser PIDs captured - cannot perform precise cleanup. "
                    "The browser process may need to be closed manually."
                )
            
            # Mark worker as uninitialized and clear the PIDs
            if self._worker:
                self._worker._initialized = False
                self._worker.env = None
                self._worker.action_set = None
                self._worker._browser_pids = set()
                
        except Exception as e:
            logger.error(f"Error killing browser processes: {e}")
    
    def is_initialized(self) -> bool:
        """Check if the environment is initialized.
        
        Returns:
            bool: True if initialized, False otherwise
        """
        try:
            command = {'type': 'is_initialized'}
            return self._worker.execute_command(command)
        except Exception as e:
            logger.error(f"Failed to check initialization status: {str(e)}")
            return False
    
    def get_action_description(self) -> str:
        """Get description of available actions.
        
        Returns:
            str: Description of the action space
        """
        try:
            action_set = HighLevelActionSet(
                subsets=["bid"],
                strict=False,
                multiaction=False
            )
            return action_set.describe(with_long_description=True, with_examples=True)
        except Exception as e:
            logger.error(f"Failed to get action description: {str(e)}")
            return "Failed to get action description"
    
    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (mainly for testing purposes)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
                cls._instance = None
