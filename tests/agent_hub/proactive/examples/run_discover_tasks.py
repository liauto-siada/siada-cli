"""
Example: Running ProactiveAgent with Task Discovery

This script demonstrates how to use ProactiveAgent to discover pending tasks
from recent work summaries and task history.

Usage:
    python -m tests.agent_hub.proactive.examples.run_discover_tasks
"""
import asyncio
import os
from pathlib import Path

from siada.services.siada_runner import SiadaRunner
from siada.session.session_manager import RunningSessionManager
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig
from siada.agent_hub.proactive.prompts.task_templates.discover_tasks import get_discover_tasks_instruction


async def main():
    """
    Main function to run ProactiveAgent with task discovery task.
    
    This example demonstrates the correct way to run ProactiveAgent:
    1. Create a RunningSession with proper configuration
    2. Use SiadaRunner.run_agent() to execute the agent
    3. The agent will use company internal provider automatically
    """
    print("=" * 80)
    print("ProactiveAgent Task Discovery Example")
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
    print("\n[Step 3] Preparing task discovery instruction...")
    user_input = get_discover_tasks_instruction()
    print(f"  Task instruction loaded from get_discover_tasks_instruction()")
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
    print("    1. List and read last 7 days summary files from summary/ directory")
    print("    2. Read ~/.siada-cli/workspace/memory/recent_task.md for task context")
    print("    3. Cross-reference findings, optionally check session details if needed")
    print("    4. Extract pending tasks with confidence scores and priorities")

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
        
        # Step 7: Check if task list was saved
        print("\n[Step 7] Task discovery summary...")
        print("  Check the agent output above for discovered tasks")
        print("  Tasks should include:")
        print("    • Title, description, priority, category")
        print("    • Status, confidence score, confirmation needs")
        print("    • Source citations from summaries or recent_task.md")
        print("    • Suggested actions")
        
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
        print("  2. Verify summary files exist in ~/.siada-cli/workspace/memory/summary/")
        print("  3. Verify recent_task.md exists in ~/.siada-cli/workspace/memory/")
        print("  4. Check agent logs for detailed error information")
        raise


def run_main():
    """Entry point for running the example."""
    asyncio.run(main())


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("ProactiveAgent Task Discovery Example")
    print("=" * 80)
    print("\nThis example demonstrates how to:")
    print("  • Create RunningSession with proper configuration")
    print("  • Use SiadaRunner to run ProactiveAgent")
    print("  • Discover pending tasks from work summaries")
    print("  • Extract tasks with priorities and confidence scores")
    print("\nStarting...\n")
    
    run_main()
    
    print("\n" + "=" * 80)
    print("Example completed! Check the agent output above for discovered tasks.")
    print("=" * 80 + "\n")
