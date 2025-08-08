# Browser Automation Tool

This module provides browser automation capabilities using Playwright, offering functionality equivalent to the TypeScript version with full screenshot and console log capture support.

## Features

### Core Functionality
- **Cross-browser automation** using Playwright (Chromium, Firefox, WebKit)
- **Screenshot capture** with base64 encoding
- **Console log monitoring** in real-time
- **Coordinate-based clicking** with viewport validation
- **Keyboard input simulation**
- **Page scrolling** operations
- **Async context manager** support for resource cleanup
- **Comprehensive error handling** with detailed error messages

### Enhanced User Experience
- **🖱️ Cursor Persistence**: Mouse cursor remains at click position, mimicking natural browser usage
- **🔴 Visual Click Indicators**: Red pulsating circles show exactly where clicks occur
- **⌨️ Typewriter Effect**: Text input with 50ms delay between characters for visibility
- **🪟 Auto Window Focus**: Browser window automatically comes to foreground
- **📍 Smart Cursor Management**: Cursor position maintained across scrolling and other operations

## Installation

The browser tool includes **automatic Chromium installation** - no manual setup required! The tool will automatically detect and install Chromium when first used.

### Automatic Installation (Recommended)

Simply use the browser tool - it will handle everything automatically:

```python
from siada.tools.browser import BrowserActionTool, BrowserSettings

# The tool will automatically install Chromium if needed
async with BrowserActionTool(settings) as tool:
    await tool.execute_action("launch", url="https://example.com")
```

### Manual Installation (Optional)

If you prefer manual control, you can pre-install Playwright and Chromium:

```bash
# Install Playwright (already included in project dependencies)
poetry add playwright

# Install browser binaries
playwright install chromium
```

### Installation Priority

The tool automatically searches for Chromium in this order:
1. **Environment variable**: `CHROMIUM_BINARY_PATH`
2. **Playwright installation**: `~/.cache/ms-playwright/chromium-*/`
3. **System browsers**: Chrome/Chromium installed on your system
4. **Auto-install**: Downloads Chromium via Playwright if none found

## Usage

### Basic Example

```python
import asyncio
from siada.tools.browser import BrowserActionTool, BrowserSettings

async def demo_browser_automation():
    # Create browser settings
    settings = BrowserSettings(
        viewport={"width": 900, "height": 600},
        headless=False,  # Set to True for headless mode
        timeout=30000
    )
    
    # Use async context manager for automatic cleanup
    async with BrowserActionTool(settings) as tool:
        # Launch browser and navigate to URL
        result = await tool.execute_action("launch", url="https://example.com")
        if result.success:
            print("✓ Browser launched successfully")
            print(f"Console logs: {result.console_logs}")
        
        # Click at coordinates (450, 300)
        result = await tool.execute_action("click", coordinate="450,300")
        if result.success:
            print("✓ Click successful")
        
        # Type text
        result = await tool.execute_action("type", text="Hello World!")
        if result.success:
            print("✓ Text input successful")
        
        # Scroll down
        result = await tool.execute_action("scroll_down")
        if result.success:
            print("✓ Scroll successful")

# Run the demo
asyncio.run(demo_browser_automation())
```

### Manual Resource Management

```python
async def manual_browser_control():
    settings = BrowserSettings(viewport={"width": 1200, "height": 800})
    tool = BrowserActionTool(settings)
    
    try:
        # Launch browser
        await tool.execute_action("launch", url="https://httpbin.org/forms/post")
        
        # Perform actions
        await tool.execute_action("click", coordinate="300,200")
        await tool.execute_action("type", text="Test input")
        await tool.execute_action("scroll_down")
        
    finally:
        # Always close browser
        await tool.execute_action("close")
```

## API Reference

### BrowserSettings

Configuration class for browser automation settings.

```python
@dataclass
class BrowserSettings:
    viewport: Dict[str, int]  # Browser viewport size {"width": 900, "height": 600}
    headless: bool = False    # Run in headless mode
    timeout: int = 30000      # Default timeout in milliseconds
```

### BrowserActionResult

Result object returned by all browser actions.

```python
@dataclass
class BrowserActionResult:
    success: bool                    # Whether the operation succeeded
    screenshot: Optional[str]        # Base64-encoded screenshot (None for close action)
    console_logs: List[str]         # Console log messages
    error: Optional[str] = None     # Error message if operation failed
```

### BrowserActionTool

Main browser automation class.

#### Methods

##### `execute_action(action: str, **kwargs) -> BrowserActionResult`

Execute a browser action. Supported actions:

- **`launch`**: Start browser and navigate to URL
  - `url` (required): URL to navigate to
  
- **`click`**: Click at specific coordinates
  - `coordinate` (required): Coordinates in "x,y" format
  
- **`type`**: Type text using keyboard simulation
  - `text` (required): Text to type
  
- **`scroll_down`**: Scroll down by one page height
  
- **`scroll_up`**: Scroll up by one page height
  
- **`close`**: Close browser and clean up resources

## Action Sequence Requirements

1. **Always start with `launch`** - This must be the first action
2. **Always end with `close`** - This must be the final action
3. **One action per call** - Wait for each action to complete before the next
4. **Coordinate validation** - Click coordinates must be within viewport bounds

## Error Handling

The tool provides comprehensive error handling:

```python
result = await tool.execute_action("click", coordinate="invalid")
if not result.success:
    print(f"Action failed: {result.error}")
    print(f"Console logs: {result.console_logs}")
```

Common error scenarios:
- Invalid coordinate format or out-of-bounds coordinates
- Browser not launched before performing actions
- Network timeouts during page loading
- Invalid URLs or unreachable websites

## Screenshot and Console Logs

Every action (except `close`) returns:
- **Screenshot**: Base64-encoded image of current browser state
- **Console logs**: Array of console messages from the browser

```python
result = await tool.execute_action("launch", url="https://example.com")
if result.screenshot:
    # Save screenshot to file
    import base64
    with open("screenshot.png", "wb") as f:
        f.write(base64.b64decode(result.screenshot))

# Print console logs
for log in result.console_logs:
    print(f"Browser console: {log}")
```

## Advanced Configuration

### Custom Browser Settings

```python
# High-resolution viewport
settings = BrowserSettings(
    viewport={"width": 1920, "height": 1080},
    headless=True,  # Run without GUI
    timeout=60000   # 60 second timeout
)
```

### Multiple Browser Instances

```python
async def multiple_browsers():
    settings1 = BrowserSettings(viewport={"width": 800, "height": 600})
    settings2 = BrowserSettings(viewport={"width": 1200, "height": 800})
    
    async with BrowserActionTool(settings1) as browser1, \
               BrowserActionTool(settings2) as browser2:
        
        await browser1.execute_action("launch", url="https://site1.com")
        await browser2.execute_action("launch", url="https://site2.com")
        
        # Perform different actions on each browser
        await browser1.execute_action("click", coordinate="400,300")
        await browser2.execute_action("scroll_down")
```

## Integration with Agents

The browser tool is designed to integrate seamlessly with Siada agents:

```python
from siada.tools.browser import BrowserActionTool, BrowserSettings

class WebAutomationAgent:
    def __init__(self):
        self.browser_settings = BrowserSettings(
            viewport={"width": 900, "height": 600},
            headless=False
        )
    
    async def automate_web_task(self, url: str):
        async with BrowserActionTool(self.browser_settings) as browser:
            # Launch and perform automation
            result = await browser.execute_action("launch", url=url)
            
            if result.success:
                # Continue with automation logic
                await browser.execute_action("click", coordinate="450,300")
                await browser.execute_action("type", text="automation test")
                
            return result
```

## Troubleshooting

### Common Issues

1. **Playwright not installed**
   ```bash
   poetry add playwright
   playwright install chromium
   ```

2. **Browser fails to launch**
   - Check if running in headless mode on systems without display
   - Verify Playwright browser binaries are installed

3. **Coordinate clicks not working**
   - Ensure coordinates are within viewport bounds
   - Check if page has finished loading before clicking

4. **Screenshots are empty**
   - Verify page has loaded completely
   - Check if browser is in headless mode (screenshots still work)

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Browser actions will now log detailed information
```

## Performance Considerations

- **Browser startup**: Initial launch takes 1-3 seconds
- **Screenshot capture**: Adds ~100-500ms per action
- **Memory usage**: Each browser instance uses ~50-100MB RAM
- **Cleanup**: Always use context managers or manual close() calls

## Compatibility

- **Python**: 3.8+
- **Playwright**: 1.40.0+
- **Operating Systems**: Windows, macOS, Linux
- **Browsers**: Chromium (default), Firefox, WebKit
