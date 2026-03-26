"""
Example: Running ProactiveAgent with Daily Summary Task

This script demonstrates how to use ProactiveAgent to generate a daily work summary.
It reads today's session history and creates a comprehensive summary.

Usage:
    python -m tests.agent_hub.proactive.examples.run_daily_summary
"""
import asyncio
import os
from pathlib import Path
from datetime import datetime

from siada.services.siada_runner import SiadaRunner
from siada.session.session_manager import RunningSessionManager
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig
from siada.agent_hub.proactive.prompts.task_templates.daily_summary import DAILY_SUMMARY_INSTRUCTION


async def main():
    """
    Main function to run ProactiveAgent with daily summary task.
    
    This example demonstrates the correct way to run ProactiveAgent:
    1. Create a RunningSession with proper configuration
    2. Use SiadaRunner.run_agent() to execute the agent
    3. The agent will use company internal provider automatically
    """
    print("=" * 80)
    print("ProactiveAgent Daily Summary Example")
    print("=" * 80)
    
    # Step 1: Setup configuration
    print("\n[Step 1] Setting up configuration...")
    
    # Get current working directory
    current_dir = os.getcwd()
    agent_name = "proactive"
    
    # Get default LLM config (uses company internal provider)
    llm_config = ModelRunConfig.get_default_config()
    print(f"  LLM Provider: {llm_config.provider}")
    print(f"  LLM Model: {llm_config.model_name}")
    
    # Create IO handler
    io = InputOutput()
    
    # Create running configuration
    siada_config = RunningConfig(
        llm_config=llm_config,
        io=io,
        workspace=current_dir,
        agent_name=agent_name,
        console_output=True,   # Enable console output for debugging
        interactive=False,     # Non-interactive mode
    )
    
    # Step 2: Create session
    print("\n[Step 2] Creating session...")
    session = RunningSessionManager.create_session(siada_config)
    print(f"  Session ID: {session.session_id}")
    print(f"  Workspace: {session.siada_config.workspace}")
    
    # Step 3: Prepare task instruction
    print("\n[Step 3] Preparing daily summary task instruction...")
    user_input = DAILY_SUMMARY_INSTRUCTION
    print(f"  Task instruction loaded from DAILY_SUMMARY_INSTRUCTION")
    print(f"  Instruction length: {len(user_input)} characters")
    
    # Display instruction preview
    print("\n--- Task Instruction Preview ---")
    preview_lines = user_input.split('\n')[:15]
    for line in preview_lines:
        print(f"  {line}")
    print("  ... (truncated, full instruction will be sent to agent)")
    print("--- End Preview ---")
    
    # Step 4: Explain what the agent will do
    print("\n[Step 4] Understanding the task...")
    print("  The agent will:")
    print("    1. List today's session files from ~/.siada-cli/workspace/memory/session/")
    print("    2. Read and summarize each session incrementally (to avoid context overflow)")
    print("    3. Extract facts, tasks, status, and user satisfaction from each session")
    print("    4. Generate aggregated daily summary with session citations")
    print("    5. Save to ~/.siada-cli/workspace/memory/summary/YYYY-MM-DD_summary.md")
    
    # Step 5: Run agent using SiadaRunner
    print("\n[Step 5] Running ProactiveAgent using SiadaRunner...")
    print("  Note: SiadaRunner handles all model provider setup automatically")
    print("-" * 80)
    
    try:
        # Run the agent using SiadaRunner
        # This is the correct way to run agents in production:
        # - Automatically uses company internal provider
        # - Handles session management
        # - Supports checkpoint functionality
        # - Saves conversation history
        # - Supports user memory and rule memory
        result = await SiadaRunner.run_agent(
            agent_name=agent_name,
            user_input=user_input,
            workspace=current_dir,
            session=session  # Pass session for full functionality
        )
        
        # Step 6: Display results
        print("\n" + "=" * 80)
        print("[Step 6] Agent Execution Completed")
        print("=" * 80)
        
        print(f"\nResult type: {type(result)}")
        
        # Convert result to input list format
        if hasattr(result, 'to_input_list'):
            messages = result.to_input_list()
            print(f"Total messages in result: {len(messages)}")
            
            # Display assistant messages
            print("\n--- Agent Output ---")
            for msg in messages:
                if msg.get('role') == 'assistant':
                    content = msg.get('content', '')
                    if isinstance(content, str) and content.strip():
                        # Truncate long output for readability
                        if len(content) > 1000:
                            print(content[:1000] + "\n... (truncated)")
                        else:
                            print(content)
            print("--- End Agent Output ---")
        
        # Step 7: Check if summary file was created
        print("\n[Step 7] Checking generated summary file...")
        today = datetime.now().strftime("%Y-%m-%d")
        summary_file = Path.home() / ".siada-cli" / "workspace" / "memory" / "summary" / f"{today}_summary.md"
        
        if summary_file.exists():
            print(f"\n✓ Summary file created successfully!")
            print(f"  Location: {summary_file}")
            print(f"  Size: {summary_file.stat().st_size} bytes")
            
            # Display summary content preview
            print("\n--- Summary File Preview ---")
            with open(summary_file, 'r', encoding='utf-8') as f:
                content = f.read()
                preview = content[:800] if len(content) > 800 else content
                print(preview)
                if len(content) > 800:
                    print("\n... (truncated, see full file for complete summary)")
            print("--- End Preview ---")
        else:
            print(f"\n⚠ Summary file not found at: {summary_file}")
            print("Possible reasons:")
            print("  1. No session files found for today")
            print("  2. Agent encountered an error during execution")
            print("  3. File was saved to a different location")
        
        print("\n" + "=" * 80)
        print("Example Completed Successfully")
        print("=" * 80)
        
        return result
        
    except Exception as e:
        print(f"\n✗ Error during agent execution: {e}")
        import traceback
        traceback.print_exc()
        print("\nTroubleshooting:")
        print("  1. Check if model provider is configured correctly")
        print("  2. Verify session files exist in ~/.siada-cli/workspace/memory/session/")
        print("  3. Check agent logs for detailed error information")
        raise


def run_main():
    """Entry point for running the example."""
    asyncio.run(main())


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("ProactiveAgent Daily Summary Example")
    print("=" * 80)
    print("\nThis example demonstrates how to:")
    print("  • Create RunningSession with proper configuration")
    print("  • Use SiadaRunner to run ProactiveAgent")
    print("  • Generate daily work summary from session history")
    print("  • Save summary to memory system")
    print("\nStarting...\n")
    
    run_main()
    
    print("\n" + "=" * 80)
    print("Example completed! Check the logs and summary file above.")
    print("=" * 80 + "\n")
