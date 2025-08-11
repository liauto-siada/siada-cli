# Browser Automation Tool

This module provides browser automation capabilities using Playwright, offering functionality equivalent to the TypeScript version with full screenshot and console log capture support, enhanced with advanced screenshot compression to optimize token usage.

## Features

### Core Functionality
- **Cross-browser automation** using Playwright (Chromium, Firefox, WebKit)
- **Screenshot capture** with base64 encoding and advanced compression
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

### Screenshot Compression
- **🎯 Multi-level compression**: Reduce file size by 60-95% to minimize token usage
- **🔧 Smart format conversion**: PNG → JPEG with quality control
- **📏 Intelligent scaling**: Resolution scaling while maintaining aspect ratio
- **⚡ Optimized compression**: Using PIL library optimization options
- **🔄 Transparency handling**: Automatic white background for JPEG format

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

## Screenshot Compression

### Overview

To solve the issue of excessively long base64 strings from browser screenshots causing token limits, we've implemented a multi-level compression strategy that can reduce file sizes by 60-95%, significantly lowering token usage.

### Compression Levels

| Level | Format | JPEG Quality | Max Resolution | Expected Compression | Use Case |
|-------|--------|--------------|----------------|---------------------|----------|
| **Low** | PNG | 90 | Unlimited | 10-20% | High quality screenshots |
| **Medium** | JPEG | 75 | 1200x800 | 60-80% | Default recommended setting |
| **High** | JPEG | 60 | 800x600 | 80-95% | File size sensitive scenarios |

### Token Savings

Based on 1200x800 resolution screenshot estimates:

```
Original PNG:    500KB → ~166K tokens
Low compression: 425KB → ~141K tokens (15% savings)
Medium compression: 125KB → ~41K tokens (75% savings)
High compression: 50KB → ~16K tokens (90% savings)
```

### Technical Implementation

- **Format conversion**: PNG → JPEG for significant file size reduction
- **Quality control**: Adjustable JPEG quality parameter (1-100)
- **Smart scaling**: Resolution scaling while maintaining aspect ratio
- **Optimized compression**: Using PIL library's optimize option
- **Transparency handling**: Automatic white background when JPEG doesn't support transparency

## Usage

### Basic Example

```python
import asyncio
from siada.tools.browser import BrowserActionTool, BrowserSettings

async def demo_browser_automation():
    # Create browser settings with default medium compression
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

### Custom Compression Configuration

```python
from siada.tools.browser.models import (
    BrowserSettings, 
    ScreenshotConfig, 
    CompressionLevel
)

# High compression configuration
screenshot_config = ScreenshotConfig(
    compression_level=CompressionLevel.HIGH,
    jpeg_quality=60,
    max_width=800,
    max_height=600,
    format="jpeg"
)

settings = BrowserSettings(
    viewport={"width": 1200, "height": 800},
    headless=False,
    timeout=30000,
    screenshot_config=screenshot_config
)

tool = BrowserActionTool(settings)
```

### Manual Compression Settings

```python
# Fully customized compression
screenshot_config = ScreenshotConfig(
    compression_level=CompressionLevel.MEDIUM,
    jpeg_quality=80,        # Custom quality
    max_width=1000,         # Custom max width
    max_height=700,         # Custom max height
    format="jpeg"           # Specify format
)
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
    viewport: Dict[str, int]                    # Browser viewport size {"width": 900, "height": 600}
    headless: bool = False                      # Run in headless mode
    timeout: int = 30000                        # Default timeout in milliseconds
    screenshot_config: Optional[ScreenshotConfig] = None  # Screenshot compression settings
```

### ScreenshotConfig

Configuration class for screenshot compression settings.

```python
@dataclass
class ScreenshotConfig:
    compression_level: CompressionLevel = CompressionLevel.MEDIUM  # Compression level
    jpeg_quality: int = 75                      # JPEG quality (1-100)
    max_width: int = 1200                       # Maximum width (0 = unlimited)
    max_height: int = 800                       # Maximum height (0 = unlimited)
    format: str = "jpeg"                        # Image format ("png" or "jpeg")
```

### CompressionLevel

Enumeration for compression levels.

```python
class CompressionLevel(Enum):
    LOW = "low"         # Low compression, high quality
    MEDIUM = "medium"   # Medium compression, balanced
    HIGH = "high"       # High compression, small file size
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

## Compression Configuration Details

### Compression Algorithm

#### 1. Format Selection
- **PNG**: Lossless compression, suitable for simple images and transparency needs
- **JPEG**: Lossy compression, suitable for complex images with smaller file sizes

#### 2. Resolution Scaling
```python
def _scale_image(self, image, max_width, max_height):
    # Calculate scaling ratio while maintaining aspect ratio
    scale_x = max_width / original_width if max_width > 0 else 1.0
    scale_y = max_height / original_height if max_height > 0 else 1.0
    scale_factor = min(scale_x, scale_y, 1.0)  # Never upscale
    
    # Use high-quality resampling
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
```

#### 3. Quality Optimization
- PNG: Uses `optimize=True` and `compress_level=6`
- JPEG: Uses `optimize=True` and configurable quality parameter

### Best Practices

#### 1. Choose Appropriate Compression Level
- **Development/Debug**: Use low compression for screenshot quality
- **Production**: Use medium compression for balanced quality and performance
- **Batch Processing**: Use high compression to maximize resource savings

#### 2. Adjust Settings Based on Content
- **Simple pages**: PNG format works better
- **Complex pages**: JPEG format has higher compression ratio
- **Text-heavy content**: Increase JPEG quality appropriately

#### 3. Monitor Compression Effects
```python
# Check compression information in logs
# Screenshot compression: 500000 -> 125000 bytes (75.0% reduction)
```

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
- Compression failures (automatically falls back to original screenshot)

## Screenshot and Console Logs

Every action (except `close`) returns:
- **Screenshot**: Base64-encoded image of current browser state (compressed by default)
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

### Custom Browser Settings with Compression

```python
# High-resolution viewport with high compression
screenshot_config = ScreenshotConfig(
    compression_level=CompressionLevel.HIGH,
    jpeg_quality=50,
    max_width=800,
    max_height=600
)

settings = BrowserSettings(
    viewport={"width": 1920, "height": 1080},
    headless=True,  # Run without GUI
    timeout=60000,  # 60 second timeout
    screenshot_config=screenshot_config
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

## Testing and Validation

### Running Tests

```bash
# Basic functionality tests
python tests/tools/browser/test_browser_action_tool.py

# Screenshot compression tests
python tests/tools/browser/test_screenshot_compression.py

# Compression effect demonstration
python tests/tools/browser/demo_compression.py
```

### Test Coverage

- ✅ Compression level configuration validation
- ✅ Image format conversion testing
- ✅ Resolution scaling functionality
- ✅ Quality parameter validation
- ✅ Actual compression ratio testing
- ✅ Error handling and fallback mechanisms

## Performance Considerations

### Compression Performance
- **Additional processing time**: ~50-200ms (depending on image size and compression settings)
- **Minimal impact**: Negligible effect on overall browser operation time

### Memory Usage
- **Compression process**: Temporarily increases memory usage during processing
- **Memory cleanup**: Memory is released after compression completion
- **Large screenshots**: Recommend using high compression settings for large resolution screenshots

### Browser Performance
- **Browser startup**: Initial launch takes 1-3 seconds
- **Screenshot capture**: Adds ~100-500ms per action (including compression)
- **Memory usage**: Each browser instance uses ~50-100MB RAM
- **Cleanup**: Always use context managers or manual close() calls

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

5. **Compression failures**
   - Check logs for compression error messages
   - Tool automatically falls back to original screenshot on compression failure
   - Verify PIL library is properly installed

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Browser actions will now log detailed information including compression stats
```

### Debugging Compression

```python
# Enable detailed logging for compression
import logging
logging.getLogger('siada.tools.browser').setLevel(logging.DEBUG)

# Logs will show: "Screenshot compression: X -> Y bytes (Z% reduction)"
```

## Backward Compatibility

- ✅ Existing code requires no modifications
- ✅ Medium compression enabled by default
- ✅ Option to fall back to original PNG format
- ✅ All original API interfaces maintained

## Compatibility

- **Python**: 3.8+
- **Playwright**: 1.40.0+
- **PIL/Pillow**: For image compression functionality
- **Operating Systems**: Windows, macOS, Linux
- **Browsers**: Chromium (default), Firefox, WebKit

## Changelog

### v1.0.0 (2025-01-08)
- ✨ Added multi-level compression strategy
- ✨ Support for JPEG format output
- ✨ Intelligent resolution scaling
- ✨ Configurable compression parameters
- ✨ Automatic format detection and conversion
- 🐛 Fixed transparency handling issues
- 📝 Comprehensive documentation and test cases

---

This browser automation tool with advanced screenshot compression provides significant token usage optimization, making it particularly suitable for automation scenarios requiring frequent screenshots.
