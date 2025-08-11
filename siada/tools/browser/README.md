# Browser Automation Tool

A comprehensive browser automation tool using Playwright with advanced WebP screenshot compression, designed to optimize token usage while maintaining high-quality visual feedback.

## Overview

This module provides cross-browser automation capabilities with intelligent screenshot compression that reduces file sizes by 25-87% compared to traditional formats, significantly lowering token consumption in AI applications.

## Key Features

### Core Automation
- **Cross-browser support** using Playwright (Chromium, Firefox, WebKit)
- **Coordinate-based interactions** with viewport validation
- **Real-time console log monitoring**
- **Automatic Chromium installation** - zero setup required
- **Visual feedback system** with cursor persistence and click indicators

### Advanced WebP Compression
- **Multi-format support**: PNG, JPEG, and WebP with intelligent format selection
- **Three compression levels**: Low (PNG), Medium (WebP), High (WebP)
- **Smart scaling**: Resolution optimization while maintaining aspect ratio
- **Optimized encoding**: Uses PIL's best compression methods (method=6, optimize=True)

## Quick Start

### Basic Usage

```python
import asyncio
from siada.tools.browser import BrowserActionTool, BrowserSettings

async def demo():
    settings = BrowserSettings(
        viewport={"width": 1200, "height": 800},
        headless=False
    )
    
    async with BrowserActionTool(settings) as tool:
        # Launch browser
        await tool.execute_action("launch", url="https://example.com")
        
        # Interact with page
        await tool.execute_action("click", coordinate="450,300")
        await tool.execute_action("type", text="Hello World!")
        await tool.execute_action("scroll_down")

asyncio.run(demo())
```

### Custom Compression Configuration

```python
from siada.tools.browser.models import ScreenshotConfig, CompressionLevel

# High compression for token-sensitive scenarios
screenshot_config = ScreenshotConfig(
    compression_level=CompressionLevel.HIGH,
    format="webp",
    webp_quality=60,
    max_width=800,
    max_height=600
)

settings = BrowserSettings(
    viewport={"width": 1200, "height": 800},
    screenshot_config=screenshot_config
)
```

## Compression Technology

### WebP Implementation

The tool uses WebP format as the default compression method, providing superior compression ratios compared to traditional formats:

```python
# Core compression algorithm
elif settings["format"] == "webp":
    webp_quality = settings.get("webp_quality", 75)
    image.save(
        output_buffer, 
        format="WEBP", 
        quality=webp_quality,
        optimize=True,
        method=6  # Best compression method (0-6)
    )
```

### Compression Levels

| Level | Format | Quality | Resolution | Compression Ratio | Use Case |
|-------|--------|---------|------------|------------------|----------|
| **Low** | PNG | Lossless | Unlimited | 10-20% | High quality needs |
| **Medium** | WebP | 75 | 1200x800 | 60-80% | **Default recommended** |
| **High** | WebP | 60 | 800x600 | 80-87% | Token-sensitive scenarios |

### Real-World Performance

Based on actual testing with live websites:

**Baidu Homepage:**
- PNG (Low): 129KB
- WebP (Medium): 36KB (72% reduction)
- WebP (High): 17KB (87% reduction)

**GitHub Homepage:**
- PNG (Low): 119KB
- WebP (Medium): 27KB (77% reduction)
- WebP (High): 15KB (87% reduction)

## API Reference

### Core Classes

#### BrowserSettings
```python
@dataclass
class BrowserSettings:
    viewport: Dict[str, int]                    # Browser window size
    headless: bool = False                      # Headless mode
    timeout: int = 30000                        # Operation timeout (ms)
    screenshot_config: Optional[ScreenshotConfig] = None
```

#### ScreenshotConfig
```python
@dataclass
class ScreenshotConfig:
    compression_level: CompressionLevel = CompressionLevel.MEDIUM
    format: str = "webp"                        # "png", "jpeg", "webp"
    webp_quality: int = 75                      # WebP quality (1-100)
    jpeg_quality: int = 75                      # JPEG quality (1-100)
    max_width: int = 1200                       # Max width (0 = unlimited)
    max_height: int = 800                       # Max height (0 = unlimited)
```

### Available Actions

#### `launch`
Start browser and navigate to URL
```python
await tool.execute_action("launch", url="https://example.com")
```

#### `click`
Click at specific coordinates with visual feedback
```python
await tool.execute_action("click", coordinate="450,300")
```

#### `type`
Simulate keyboard input with typewriter effect
```python
await tool.execute_action("type", text="Hello World!")
```

#### `scroll_down` / `scroll_up`
Scroll page with smooth animation
```python
await tool.execute_action("scroll_down")
await tool.execute_action("scroll_up")
```

#### `close`
Close browser and cleanup resources
```python
await tool.execute_action("close")
```

## Implementation Architecture

### Compression Pipeline

1. **Screenshot Capture**: Playwright captures PNG screenshot
2. **Format Detection**: Determines optimal format based on compression level
3. **Image Processing**: PIL handles format conversion and scaling
4. **Optimization**: Applies best compression parameters
5. **Base64 Encoding**: Converts to base64 for API transmission

### Visual Enhancement System

- **Cursor Persistence**: Maintains cursor position across operations
- **Click Indicators**: Red pulsating circles show click locations
- **Smooth Animations**: CSS transitions for cursor movement
- **Auto-focus**: Brings browser window to foreground automatically

### Error Handling

Comprehensive error handling with automatic fallbacks:
- Compression failures fall back to original PNG
- Network timeouts with retry mechanisms
- Coordinate validation with boundary checking
- Resource cleanup on exceptions

## Token Usage Optimization

### Before vs After WebP Implementation

```
Typical 1200x800 screenshot:
├── Original PNG: ~500KB → ~166K tokens
├── JPEG (75%): ~125KB → ~41K tokens (75% savings)
└── WebP (75%): ~65KB → ~21K tokens (87% savings)
```

### Compression Effectiveness by Content Type

| Content Type | PNG Size | JPEG Size | WebP Size | WebP vs JPEG Savings |
|--------------|----------|-----------|-----------|---------------------|
| Simple UI | 2KB | 7KB | 1KB | 74.2% |
| Complex Images | 77KB | 84KB | 66KB | 21.6% |
| Text-heavy | 23KB | 28KB | 14KB | 48.3% |

## Future Optimization Plans

### Short-term Enhancements

1. **AVIF Format Support**
   - Next-generation image format with even better compression
   - 20-30% smaller than WebP with similar quality
   - Implementation: Add AVIF encoder to compression pipeline

2. **Adaptive Quality Control**
   - Dynamic quality adjustment based on content analysis
   - Text detection for quality preservation
   - Gradient analysis for optimal compression settings

3. **Progressive Loading**
   - Multi-resolution screenshot generation
   - Thumbnail + full-size approach
   - Bandwidth-aware quality selection

### Medium-term Improvements

1. **AI-Powered Compression**
   - Machine learning models for optimal compression parameter selection
   - Content-aware quality adjustment
   - Perceptual quality metrics integration

2. **Streaming Compression**
   - Real-time compression during screenshot capture
   - Reduced memory footprint for large screenshots
   - Parallel processing for multiple screenshots

3. **Smart Caching**
   - Screenshot similarity detection
   - Delta compression for sequential screenshots
   - Intelligent cache invalidation

### Long-term Vision

1. **Vector-based Screenshots**
   - SVG generation for UI elements
   - Hybrid raster/vector approach
   - Infinite scalability with minimal file size

2. **Semantic Compression**
   - Understanding of UI elements and content
   - Selective compression based on importance
   - Context-aware quality preservation

## Performance Considerations

### Compression Overhead
- **Processing time**: +50-200ms per screenshot
- **Memory usage**: Temporary increase during compression
- **CPU impact**: Minimal on modern systems

### Browser Performance
- **Startup time**: 1-3 seconds for initial launch
- **Memory usage**: ~50-100MB per browser instance
- **Screenshot capture**: ~100-500ms including compression

## Testing and Validation

### Comprehensive Test Suite
```bash
# Run all browser tool tests
python -m pytest tests/tools/browser/ -v

# Test compression functionality
python tests/tools/browser/test_screenshot_compression.py

# Demo compression effects
python tests/tools/browser/demo_comprehensive_compression.py
```

### Test Coverage
- ✅ WebP format validation and encoding
- ✅ Compression ratio verification
- ✅ Quality parameter testing
- ✅ Resolution scaling accuracy
- ✅ Error handling and fallback mechanisms
- ✅ Real-world website testing

## Troubleshooting

### Common Issues

**Compression Failures**
- Check PIL WebP support: `python -c "from PIL import Image; print(Image.EXTENSION)"`
- Verify WebP codec availability
- Tool automatically falls back to PNG on failure

**Browser Launch Issues**
- Automatic Chromium installation handles most cases
- Check system permissions for browser execution
- Verify network connectivity for downloads

**Performance Issues**
- Use higher compression levels for better performance
- Consider headless mode for server environments
- Monitor memory usage with large screenshots

### Debug Mode
```python
import logging
logging.getLogger('siada.tools.browser').setLevel(logging.DEBUG)
# Enables detailed compression statistics and error reporting
```

## Compatibility

- **Python**: 3.8+
- **Playwright**: 1.40.0+
- **PIL/Pillow**: Latest version with WebP support
- **Operating Systems**: Windows, macOS, Linux
- **Browsers**: Chromium (default), Firefox, WebKit

## Changelog

### v2.0.0 - WebP Compression Upgrade
- ✨ **WebP format support** with 25-87% file size reduction
- ✨ **Three-tier compression system** (Low/Medium/High)
- ✨ **Intelligent format selection** based on content type
- ✨ **Optimized encoding parameters** (method=6, optimize=True)
- 🔧 **Backward compatibility** maintained for existing code
- 📊 **Real-world testing** with live websites
- 📝 **Comprehensive documentation** and examples

### v1.0.0 - Initial Release
- 🚀 Core browser automation functionality
- 📸 Screenshot capture with PNG format
- 🖱️ Visual interaction system
- 🔧 Automatic Chromium installation

---

This browser automation tool represents a significant advancement in screenshot compression technology, making it ideal for AI applications where token efficiency is crucial while maintaining high-quality visual feedback.
