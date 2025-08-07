"""
浏览器滚动功能演示.

专门测试浏览器的滚动功能：
1. 向下滚动测试
2. 向上滚动测试
3. 连续滚动测试
4. 滚动时页面内容变化验证
"""

import asyncio
import logging
from siada.tools.browser import BrowserActionTool, BrowserSettings


async def test_browser_scroll_functionality():
    """测试浏览器滚动功能."""
    print("📜 浏览器滚动功能演示")
    print("验证上下滚动操作的正确性")
    
    logging.basicConfig(level=logging.INFO)
    
    settings = BrowserSettings(
        viewport={"width": 1200, "height": 800},
        headless=False,
        timeout=30000
    )
    
    async with BrowserActionTool(settings) as tool:
        print("\n=== 测试1: 浏览器启动和页面加载 ===")
        print("🎯 启动浏览器并加载虎嗅网站（内容丰富，适合滚动测试）")
        
        result = await tool.execute_action("launch", url="https://www.huxiu.com")
        
        if not result.success:
            print(f"❌ 启动失败: {result.error}")
            return
        
        print("✅ 浏览器启动成功")
        print("⏰ 等待8秒让页面完全加载...")
        await asyncio.sleep(8)
        
        print("\n=== 测试2: 向下滚动测试 ===")
        print("🎯 测试向下滚动功能")
        print("👀 请观察页面内容是否向上移动")
        print("⏳ 3秒后开始向下滚动...")
        await asyncio.sleep(3)
        
        for i in range(3):
            print(f"\n--- 向下滚动 {i+1}/3 ---")
            result = await tool.execute_action("scroll_down")
            if result.success:
                print("✅ 向下滚动成功")
                print("🔍 等待3秒观察滚动效果...")
                await asyncio.sleep(3)
            else:
                print(f"❌ 向下滚动失败: {result.error}")
        
        print("\n=== 测试3: 向上滚动测试 ===")
        print("🎯 测试向上滚动功能")
        print("👀 请观察页面内容是否向下移动")
        print("⏳ 3秒后开始向上滚动...")
        await asyncio.sleep(3)
        
        for i in range(3):
            print(f"\n--- 向上滚动 {i+1}/3 ---")
            result = await tool.execute_action("scroll_up")
            if result.success:
                print("✅ 向上滚动成功")
                print("🔍 等待3秒观察滚动效果...")
                await asyncio.sleep(3)
            else:
                print(f"❌ 向上滚动失败: {result.error}")
        
        print("\n=== 测试4: 快速连续滚动测试 ===")
        print("🎯 测试快速连续滚动的稳定性")
        print("👀 验证连续滚动操作是否流畅")
        print("⏳ 2秒后开始快速滚动...")
        await asyncio.sleep(2)
        
        # 快速向下滚动
        print("\n快速向下滚动:")
        for i in range(5):
            print(f"快速向下滚动 {i+1}/5")
            result = await tool.execute_action("scroll_down")
            if result.success:
                print("✅ 快速向下滚动成功")
                await asyncio.sleep(1)  # 较短的等待时间
            else:
                print(f"❌ 快速向下滚动失败: {result.error}")
        
        print("\n等待2秒...")
        await asyncio.sleep(2)
        
        # 快速向上滚动
        print("\n快速向上滚动:")
        for i in range(5):
            print(f"快速向上滚动 {i+1}/5")
            result = await tool.execute_action("scroll_up")
            if result.success:
                print("✅ 快速向上滚动成功")
                await asyncio.sleep(1)  # 较短的等待时间
            else:
                print(f"❌ 快速向上滚动失败: {result.error}")
        
        print("\n=== 测试5: 滚动与点击结合测试 ===")
        print("🎯 测试滚动后点击功能的正确性")
        print("👀 验证滚动不会影响点击坐标的准确性")
        print("⏳ 3秒后开始测试...")
        await asyncio.sleep(3)
        
        # 先滚动
        print("\n向下滚动后点击测试:")
        result = await tool.execute_action("scroll_down")
        if result.success:
            print("✅ 向下滚动成功")
            await asyncio.sleep(2)
            
            # 然后点击页面中心
            print("点击页面中心位置...")
            result = await tool.execute_action("click", coordinate="600,400")
            if result.success:
                print("✅ 滚动后点击成功")
                await asyncio.sleep(3)
            else:
                print(f"❌ 滚动后点击失败: {result.error}")
        
        print("\n🎉 浏览器滚动功能演示完成!")
        print("\n📋 测试结果总结:")
        print("请确认以下几点:")
        print("✅ 向下滚动时页面内容向上移动")
        print("✅ 向上滚动时页面内容向下移动")
        print("✅ 连续滚动操作流畅稳定")
        print("✅ 快速滚动不会出现卡顿或错误")
        print("✅ 滚动后其他操作（如点击）仍然正常")
        
        print("\n💡 功能说明:")
        print("📜 scroll_down = 向下滚动一个页面高度")
        print("📜 scroll_up = 向上滚动一个页面高度")
        print("⚡ 滚动操作不影响其他浏览器功能")


async def main():
    """运行浏览器滚动功能演示."""
    print("🚀 浏览器滚动功能演示")
    print("=" * 60)
    print("本次演示测试以下滚动功能:")
    print()
    print("📜 基础滚动:")
    print("   ✅ 向下滚动 (scroll_down)")
    print("   ✅ 向上滚动 (scroll_up)")
    print()
    print("⚡ 高级测试:")
    print("   ✅ 连续滚动稳定性")
    print("   ✅ 快速滚动性能")
    print("   ✅ 滚动与其他操作的兼容性")
    print()
    print("👀 观察要点:")
    print("   📄 页面内容移动方向正确")
    print("   🔄 滚动操作响应及时")
    print("   ⚡ 连续操作无卡顿")
    print("   🎯 滚动后点击坐标准确")
    print()
    
    try:
        await test_browser_scroll_functionality()
        
    except KeyboardInterrupt:
        print("\n⏹️ 演示被用户中断")
    except Exception as e:
        print(f"\n💥 演示失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("启动浏览器滚动功能演示...")
    print("这将专门测试浏览器的滚动操作！")
    print()
    
    asyncio.run(main())
