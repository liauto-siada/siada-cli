#!/usr/bin/env python3
"""
综合压缩演示脚本

整合了压缩功能演示、WebP压缩对比和截图保存功能。
实际访问网站并保存不同压缩级别的截图到根目录，展示真实的图片质量和文件大小。
"""

import asyncio
import os
import sys
from pathlib import Path
from io import BytesIO

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from siada.tools.browser.browser_action_tool import BrowserActionTool
from siada.tools.browser.models import (
    BrowserSettings, 
    ScreenshotConfig, 
    CompressionLevel
)
from PIL import Image

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


async def demo_real_website_compression():
    """演示真实网站截图的不同压缩效果"""
    print("🚀 浏览器截图压缩综合演示")
    print("=" * 60)
    print("访问真实网站并保存不同压缩级别的截图到根目录")
    print("=" * 60)
    
    # 压缩级别配置
    compression_configs = [
        ("低压缩_高质量", CompressionLevel.LOW, "png"),
        ("中等压缩_WebP", CompressionLevel.MEDIUM, "webp"), 
        ("高压缩_WebP", CompressionLevel.HIGH, "webp"),
    ]
    
    # 测试网站列表
    test_sites = [
        ("百度首页", "https://www.baidu.com", "baidu"),
        ("GitHub首页", "https://github.com", "github"),
    ]
    
    for site_name, url, filename_prefix in test_sites:
        print(f"\n📱 正在访问: {site_name} ({url})")
        print("-" * 50)
        
        for config_name, level, expected_format in compression_configs:
            print(f"\n🔧 测试配置: {config_name}")
            
            # 创建截图配置
            screenshot_config = ScreenshotConfig(compression_level=level)
            settings = screenshot_config.get_optimized_settings()
            
            # 创建浏览器设置
            browser_settings = BrowserSettings(
                viewport={"width": 1200, "height": 800},
                headless=True,
                timeout=30000,
                screenshot_config=screenshot_config
            )
            
            # 创建浏览器工具
            tool = BrowserActionTool(browser_settings)
            
            try:
                # 启动浏览器并访问网站
                result = await tool.execute_action("launch", url=url)
                
                if result.success:
                    # 等待页面完全加载
                    await asyncio.sleep(2)
                    
                    # 保存截图到根目录
                    screenshot_filename = f"{filename_prefix}_{config_name.lower()}.{expected_format}"
                    screenshot_path = PROJECT_ROOT / screenshot_filename
                    
                    success = await tool.save_screenshot(str(screenshot_path))
                    
                    if success and os.path.exists(screenshot_path):
                        file_size = os.path.getsize(screenshot_path)
                        print(f"✅ 截图已保存: {screenshot_filename}")
                        print(f"📊 文件大小: {file_size:,} bytes ({file_size/1024:.1f} KB)")
                        print(f"🎯 格式: {settings['format'].upper()}")
                        if 'webp_quality' in settings:
                            print(f"🎨 WebP质量: {settings['webp_quality']}")
                        elif 'jpeg_quality' in settings:
                            print(f"🎨 JPEG质量: {settings['jpeg_quality']}")
                        print(f"📐 分辨率限制: {settings['max_width']}x{settings['max_height']}")
                    else:
                        print(f"❌ 截图保存失败: {screenshot_filename}")
                        
                else:
                    print(f"❌ 浏览器启动失败: {result.error}")
                    
            except Exception as e:
                print(f"❌ 处理失败: {str(e)}")
                
            finally:
                # 关闭浏览器
                await tool.execute_action("close")
                await asyncio.sleep(1)  # 等待清理完成


async def demo_synthetic_image_compression():
    """演示合成图像的压缩效果对比"""
    print(f"\n🎨 合成图像压缩效果对比")
    print("=" * 60)
    
    # 创建测试图像
    test_images = [
        ("简单UI界面", create_simple_ui_image()),
        ("复杂渐变图像", create_complex_image()),
        ("文本密集图像", create_text_heavy_image()),
    ]
    
    # 创建浏览器工具用于压缩测试
    settings = BrowserSettings(
        viewport={"width": 800, "height": 600},
        headless=True,
        timeout=30000
    )
    tool = BrowserActionTool(settings)
    
    print(f"\n📊 压缩效果对比:")
    print("-" * 70)
    print(f"{'图像类型':<15} | {'PNG':<10} | {'JPEG':<10} | {'WebP':<10} | {'WebP节省':<10}")
    print("-" * 70)
    
    for image_name, test_image in test_images:
        # 保存原始PNG图像到根目录
        png_path = PROJECT_ROOT / f"test_{image_name.replace(' ', '_')}_original.png"
        test_image.save(str(png_path))
        
        # 转换为字节用于压缩测试
        png_buffer = BytesIO()
        test_image.save(png_buffer, format="PNG")
        original_bytes = png_buffer.getvalue()
        
        # 测试不同压缩格式
        formats_to_test = [
            ("PNG", {"format": "png", "jpeg_quality": 90, "webp_quality": 90, "max_width": 0, "max_height": 0}),
            ("JPEG", {"format": "jpeg", "jpeg_quality": 75, "webp_quality": 75, "max_width": 0, "max_height": 0}),
            ("WebP", {"format": "webp", "jpeg_quality": 75, "webp_quality": 75, "max_width": 0, "max_height": 0}),
        ]
        
        sizes = {}
        for format_name, compression_settings in formats_to_test:
            compressed_bytes = await tool._compress_screenshot(original_bytes, compression_settings)
            sizes[format_name] = len(compressed_bytes)
            
            # 保存压缩后的图像到根目录
            compressed_path = PROJECT_ROOT / f"test_{image_name.replace(' ', '_')}_{format_name.lower()}.{compression_settings['format']}"
            with open(compressed_path, 'wb') as f:
                f.write(compressed_bytes)
        
        # 计算WebP相比JPEG的节省
        webp_savings = (1 - sizes["WebP"] / sizes["JPEG"]) * 100 if sizes["JPEG"] > 0 else 0
        
        print(f"{image_name:<15} | {sizes['PNG']//1000:>7}KB | {sizes['JPEG']//1000:>7}KB | {sizes['WebP']//1000:>7}KB | {webp_savings:>7.1f}%")


def create_simple_ui_image():
    """创建简单UI界面图像"""
    image = Image.new("RGB", (800, 600), color="white")
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    
    # 头部
    draw.rectangle([0, 0, 800, 80], fill="#2196F3")
    # 侧边栏
    draw.rectangle([0, 80, 200, 600], fill="#F5F5F5")
    # 内容区域
    draw.rectangle([220, 100, 780, 200], fill="#E3F2FD")
    draw.rectangle([220, 220, 780, 320], fill="#E8F5E8")
    draw.rectangle([220, 340, 780, 440], fill="#FFF3E0")
    
    return image


def create_complex_image():
    """创建复杂渐变图像"""
    image = Image.new("RGB", (800, 600), color="white")
    from PIL import ImageDraw
    import random
    
    draw = ImageDraw.Draw(image)
    
    # 添加渐变效果
    for y in range(0, 600, 3):
        for x in range(0, 800, 3):
            r = int(255 * (x / 800))
            g = int(255 * (y / 600))
            b = int(255 * ((x + y) / 1400))
            # 添加噪点
            r = max(0, min(255, r + random.randint(-20, 20)))
            g = max(0, min(255, g + random.randint(-20, 20)))
            b = max(0, min(255, b + random.randint(-20, 20)))
            draw.rectangle([x, y, x+3, y+3], fill=(r, g, b))
    
    return image


def create_text_heavy_image():
    """创建文本密集图像"""
    image = Image.new("RGB", (800, 600), color="white")
    from PIL import ImageDraw, ImageFont
    
    draw = ImageDraw.Draw(image)
    
    try:
        font = ImageFont.load_default()
    except:
        font = None
    
    # 添加文本内容
    text_lines = [
        "WebP压缩功能演示",
        "这是一个文本密集的图像，用于测试压缩效果",
        "WebP格式在文本和简单图形方面表现优异",
        "",
        "WebP的主要优势:",
        "• 相比JPEG压缩率提升25-35%",
        "• 支持透明度，比JPEG更灵活", 
        "• 现代浏览器广泛支持",
        "• 在相同文件大小下质量更好",
        "",
        "技术规格:",
        "- 支持有损和无损压缩模式",
        "- 相比等效JPEG文件小25-35%",
        "- 支持动画(WebP动画)",
        "- 最大尺寸: 16383 x 16383 像素",
        "",
        "应用场景:",
        "- 网页图片优化",
        "- 移动应用图片压缩",
        "- API响应图片传输",
        "- 截图工具压缩",
    ]
    
    y_offset = 30
    for line in text_lines:
        if line:
            draw.text((30, y_offset), line, fill="black", font=font)
        y_offset += 25
    
    # 添加几何图形
    draw.rectangle([30, 450, 770, 550], outline="blue", width=2)
    draw.ellipse([600, 460, 760, 540], outline="red", width=2)
    
    return image


async def show_compression_summary():
    """显示压缩功能总结"""
    print(f"\n💡 压缩功能总结")
    print("=" * 60)
    print("✅ 已生成的文件 (保存在项目根目录):")
    print()
    
    # 列出生成的文件
    generated_files = []
    for file_path in PROJECT_ROOT.glob("*.png"):
        if file_path.name.startswith(("baidu_", "github_", "test_")):
            generated_files.append(file_path)
    for file_path in PROJECT_ROOT.glob("*.webp"):
        if file_path.name.startswith(("baidu_", "github_", "test_")):
            generated_files.append(file_path)
    for file_path in PROJECT_ROOT.glob("*.jpeg"):
        if file_path.name.startswith(("baidu_", "github_", "test_")):
            generated_files.append(file_path)
    for file_path in PROJECT_ROOT.glob("*.jpg"):
        if file_path.name.startswith(("baidu_", "github_", "test_")):
            generated_files.append(file_path)
    
    # 按文件大小排序
    generated_files.sort(key=lambda x: os.path.getsize(x) if x.exists() else 0, reverse=True)
    
    print(f"{'文件名':<40} | {'大小':<10} | {'格式':<6}")
    print("-" * 60)
    
    for file_path in generated_files:
        if file_path.exists():
            file_size = os.path.getsize(file_path)
            file_format = file_path.suffix[1:].upper()
            print(f"{file_path.name:<40} | {file_size//1000:>7}KB | {file_format:<6}")
    
    print(f"\n🎯 使用建议:")
    print("• 低压缩(PNG): 适用于需要最高质量的场景")
    print("• 中等压缩(WebP): 推荐的默认设置，平衡质量和大小")
    print("• 高压缩(WebP): 适用于对文件大小敏感的场景")
    print()
    print("🔍 请查看生成的图片文件，对比不同压缩级别的:")
    print("  - 视觉质量差异")
    print("  - 文件大小差异")
    print("  - 适用场景选择")


if __name__ == "__main__":
    async def main():
        print("🎬 启动浏览器截图压缩综合演示")
        print("本演示将访问真实网站并生成不同压缩级别的截图")
        print("同时测试合成图像的压缩效果，所有文件保存到项目根目录\n")
        
        try:
            # 演示真实网站截图压缩
            await demo_real_website_compression()
            
            # 演示合成图像压缩
            await demo_synthetic_image_compression()
            
            # 显示总结
            await show_compression_summary()
            
            print(f"\n🎉 演示完成！")
            print("请检查项目根目录中生成的图片文件，对比压缩效果。")
            
        except Exception as e:
            print(f"❌ 演示过程中出现错误: {str(e)}")
    
    asyncio.run(main())
