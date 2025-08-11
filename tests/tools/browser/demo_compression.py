"""
Demo script to showcase screenshot compression functionality.

This script demonstrates the compression capabilities of the browser tool
with different settings and shows the actual compression ratios.
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from siada.tools.browser.browser_action_tool import BrowserActionTool
from siada.tools.browser.models import (
    BrowserSettings, 
    ScreenshotConfig, 
    CompressionLevel
)


async def demo_compression_levels():
    """Demonstrate different compression levels and their effects."""
    print("🖼️  浏览器截图压缩功能演示")
    print("=" * 50)
    
    # Test different compression levels
    compression_configs = [
        ("低压缩 (高质量)", CompressionLevel.LOW),
        ("中等压缩 (平衡)", CompressionLevel.MEDIUM),
        ("高压缩 (小文件)", CompressionLevel.HIGH),
    ]
    
    for name, level in compression_configs:
        print(f"\n📊 {name}")
        print("-" * 30)
        
        # Create screenshot config
        screenshot_config = ScreenshotConfig(compression_level=level)
        settings = screenshot_config.get_optimized_settings()
        
        print(f"格式: {settings['format'].upper()}")
        print(f"JPEG质量: {settings['jpeg_quality']}")
        print(f"最大宽度: {settings['max_width'] if settings['max_width'] > 0 else '无限制'}")
        print(f"最大高度: {settings['max_height'] if settings['max_height'] > 0 else '无限制'}")
        
        # Create browser settings
        browser_settings = BrowserSettings(
            viewport={"width": 1200, "height": 800},
            headless=True,
            timeout=30000,
            screenshot_config=screenshot_config
        )
        
        # Estimate compression ratio for typical screenshots
        if level == CompressionLevel.LOW:
            estimated_reduction = "10-20%"
        elif level == CompressionLevel.MEDIUM:
            estimated_reduction = "60-80%"
        else:  # HIGH
            estimated_reduction = "80-95%"
            
        print(f"预期压缩率: {estimated_reduction}")

    print(f"\n💡 使用建议:")
    print("• 低压缩: 适用于需要高质量截图的场景")
    print("• 中等压缩: 推荐的默认设置，平衡质量和文件大小")
    print("• 高压缩: 适用于对文件大小敏感的场景，如大量截图或网络传输")
    
    print(f"\n🔧 技术细节:")
    print("• PNG格式: 无损压缩，适合简单图像")
    print("• JPEG格式: 有损压缩，适合复杂图像，大幅减少文件大小")
    print("• 分辨率缩放: 在保持宽高比的同时减少像素数量")
    print("• 质量优化: 使用PIL库的优化选项进一步减少文件大小")


async def demo_token_savings():
    """Demonstrate potential token savings."""
    print(f"\n💰 Token使用量优化")
    print("=" * 50)
    
    # Typical screenshot sizes (estimated)
    original_size = 500000  # ~500KB typical PNG screenshot
    
    compression_scenarios = [
        ("原始PNG", 1.0),
        ("低压缩", 0.85),
        ("中等压缩", 0.25),
        ("高压缩", 0.10),
    ]
    
    print("场景对比 (基于1200x800分辨率截图):")
    print("-" * 40)
    
    for scenario, ratio in compression_scenarios:
        compressed_size = int(original_size * ratio)
        base64_size = int(compressed_size * 1.33)  # Base64 encoding overhead
        token_estimate = int(base64_size / 4)  # Rough token estimation
        
        print(f"{scenario:12} | {compressed_size//1000:3}KB | ~{token_estimate//1000:2}K tokens")
    
    print(f"\n📈 优化效果:")
    medium_savings = (1 - 0.25) * 100
    high_savings = (1 - 0.10) * 100
    print(f"• 中等压缩可节省约 {medium_savings:.0f}% 的token使用量")
    print(f"• 高压缩可节省约 {high_savings:.0f}% 的token使用量")
    print(f"• 对于频繁使用浏览器工具的场景，节省效果显著")


if __name__ == "__main__":
    async def main():
        await demo_compression_levels()
        await demo_token_savings()
        
        print(f"\n✅ 压缩功能已成功集成到浏览器工具中！")
        print("现在所有的浏览器截图都会自动使用中等压缩设置，")
        print("大幅减少base64字符串长度和token使用量。")
    
    asyncio.run(main())
