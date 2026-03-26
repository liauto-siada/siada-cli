import asyncio
import os
import logging

# 屏蔽不必要的日志输出，只保留用户与模型的交互
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("siada.api").setLevel(logging.WARNING)

# Set working directory for the agent
WORK_DIR = '/Users/chenhan6/demo'
if not os.path.exists(WORK_DIR):
    print(f"⚠️  Warning: Work directory '{WORK_DIR}' does not exist. Creating it...")
    os.makedirs(WORK_DIR, exist_ok=True)

os.chdir(WORK_DIR)
print(f"📁 Working directory set to: {os.getcwd()}\n")

from google.genai import types
from google.adk.runners import InMemoryRunner
from siada.agent_hub.a2a.code_agent.code_agent import root_agent
from siada.foundation.logging import remove_console_handler


def print_separator(char="=", length=70):
    """Print a separator line"""
    print(char * length)


async def interactive_test():
    """Run interactive test session with Code Agent"""
    
    # 屏蔽所有不必要的日志输出
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # 移除 siada.api 的 console handler，只保留文件日志
    siada_logger = logging.getLogger("siada.api")
    remove_console_handler(siada_logger)
    
    # Create runner
    runner = InMemoryRunner(
        agent=root_agent,
        app_name='code_agent_interactive',
    )
    
    # Create session
    session = await runner.session_service.create_session(
        app_name='code_agent_interactive',
        user_id='interactive_user'
    )
    
    # Welcome message
    print_separator()
    print("🤖 Code Agent 交互式测试")
    print_separator()
    print("\n欢迎使用 Code Agent！")
    print("\n可用功能:")
    print("  • 文件编辑 (edit_for_adk)")
    print("  • 代码搜索 (regex_search_for_adk)")
    print("  • 命令执行 (run_command_for_adk)")
    print("  • 代码分析 (list_code_definitions_for_adk)")
    print("\n命令:")
    print("  • 'exit' 或 'quit' - 退出")
    print("  • 'clear' - 清空对话历史")
    print_separator()
    print()
    
    # Suggested prompts
    print("💡 示例问题:")
    print("  1. 帮我创建一个 Python 函数计算斐波那契数列")
    print("  2. 查看当前目录下有哪些 Python 文件")
    print("  3. 搜索项目中所有包含 'TODO' 的代码")
    print("  4. 运行 'ls -la' 命令")
    print()
    print_separator()
    
    conversation_count = 0
    
    while True:
        # Get user input
        try:
            user_input = input("\n💬 你: ")
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 再见!")
            break
        
        # Handle commands
        if user_input.strip().lower() in ['exit', 'quit']:
            print("\n👋 再见!")
            break
        
        if user_input.strip().lower() == 'clear':
            # Create new session
            session = await runner.session_service.create_session(
                app_name='code_agent_interactive',
                user_id='interactive_user'
            )
            conversation_count = 0
            print("\n✅ 对话历史已清空")
            continue
        
        if not user_input.strip():
            continue
        
        conversation_count += 1
        
        # Create content
        content = types.Content(
            role='user',
            parts=[types.Part.from_text(text=user_input)]
        )
        
        # Send to agent and display response
        print(f"\n🤖 Agent:")
        print_separator("-", 70)
        
        try:
            response_text = ""
            async for event in runner.run_async(
                user_id='interactive_user',
                session_id=session.id,
                new_message=content,
            ):
                if event.content.parts and event.content.parts[0].text:
                    text = event.content.parts[0].text
                    print(text, end='', flush=True)
                    response_text += text
            
            print()  # New line after response
            
            if not response_text:
                print("(无响应)")
            
        except Exception as e:
            print(f"\n❌ 错误: {e}")
            import traceback
            traceback.print_exc()
        
        print_separator("-", 70)
        print(f"[对话轮数: {conversation_count}]")


def main():
    """Main entry point"""
    try:
        asyncio.run(interactive_test())
    except KeyboardInterrupt:
        print("\n\n👋 再见!")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
