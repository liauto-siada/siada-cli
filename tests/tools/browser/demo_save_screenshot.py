#!/usr/bin/env python3
"""
Demo script for the new save_screenshot functionality.

This script demonstrates how to use the new save_screenshot method
to save browser screenshots to files.
"""

import asyncio
import os
from pathlib import Path
from siada.tools.browser import BrowserActionTool, BrowserSettings

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


async def demo_save_screenshot():
    """Demonstrate the save_screenshot functionality."""
    print("🚀 Browser Screenshot Save Demo")
    print("=" * 50)
    
    # Create browser settings
    settings = BrowserSettings(
        viewport={"width": 1200, "height": 800},
        headless=True,  # Run in headless mode for demo
        timeout=30000
    )
    
    # Create browser tool
    tool = BrowserActionTool(settings)
    
    try:
        print("📱 Launching browser and navigating to Baidu...")
        # Launch browser and navigate to Baidu
        result = await tool.execute_action("launch", url="https://www.baidu.com")
        
        if result.success:
            print("✅ Browser launched successfully!")
            
            # Save screenshot to project root directory
            screenshot_path = PROJECT_ROOT / "baidu_homepage_demo.jpg"
            print(f"📸 Saving screenshot to: {screenshot_path}")
            
            success = await tool.save_screenshot(str(screenshot_path))
            
            if success:
                print("✅ Screenshot saved successfully!")
                
                # Check file size
                if os.path.exists(screenshot_path):
                    file_size = os.path.getsize(screenshot_path)
                    print(f"📊 File size: {file_size:,} bytes")
                    print(f"📁 File path: {os.path.abspath(screenshot_path)}")
                else:
                    print("❌ Screenshot file not found!")
            else:
                print("❌ Failed to save screenshot!")
        else:
            print(f"❌ Failed to launch browser: {result.error}")
            
    except Exception as e:
        print(f"❌ Demo failed with error: {str(e)}")
        
    finally:
        # Clean up - close browser
        print("🔒 Closing browser...")
        await tool.execute_action("close")
        print("✅ Demo completed!")


async def demo_save_multiple_screenshots():
    """Demonstrate saving multiple screenshots with different actions."""
    print("\n🎯 Multiple Screenshots Demo")
    print("=" * 50)
    
    settings = BrowserSettings(
        viewport={"width": 1200, "height": 800},
        headless=True,
        timeout=30000
    )
    
    tool = BrowserActionTool(settings)
    
    try:
        # Launch browser
        print("📱 Launching browser...")
        result = await tool.execute_action("launch", url="https://www.baidu.com")
        
        if result.success:
            # Save initial screenshot to project root
            initial_path = PROJECT_ROOT / "baidu_step1_initial.jpg"
            await tool.save_screenshot(str(initial_path))
            print(f"📸 Saved: {initial_path}")
            
            # Scroll down and save another screenshot
            await tool.execute_action("scroll_down")
            scrolled_path = PROJECT_ROOT / "baidu_step2_scrolled.jpg"
            await tool.save_screenshot(str(scrolled_path))
            print(f"📸 Saved: {scrolled_path}")
            
            # Create a directory in project root and save screenshot there
            screenshots_dir = PROJECT_ROOT / "screenshots"
            screenshots_dir.mkdir(exist_ok=True)
            final_path = screenshots_dir / "baidu_final.jpg"
            await tool.save_screenshot(str(final_path))
            print(f"📸 Saved: {final_path}")
            
            print("✅ All screenshots saved successfully!")
            
    except Exception as e:
        print(f"❌ Demo failed: {str(e)}")
        
    finally:
        await tool.execute_action("close")


if __name__ == "__main__":
    print("🎬 Starting Browser Screenshot Save Demos")
    print("This demo showcases the new save_screenshot functionality")
    print("that was added to the BrowserActionTool.\n")
    
    # Run the demos
    asyncio.run(demo_save_screenshot())
    asyncio.run(demo_save_multiple_screenshots())
    
    print("\n🎉 All demos completed!")
    print("Check the generated screenshot files to see the results.")
