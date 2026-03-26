"""
Example: Running ProactiveAgent to Update Personal Style

This script demonstrates how to use ProactiveAgent to update the personal style
memory file based on the most recent day's structured event files.

Usage:
    python -m tests.agent_hub.proactive.examples.run_update_personal_style
"""
import asyncio
import os

from siada.services.siada_runner import SiadaRunner
from siada.session.session_manager import RunningSessionManager
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig
from siada.agent_hub.proactive.prompts.task_templates.personal_style import get_update_personal_style_instruction


async def main():
    print("=" * 80)
    print("ProactiveAgent Update Personal Style Example")
    print("=" * 80)

    print("\n[Step 1] Setting up configuration...")
    current_dir = os.getcwd()
    agent_name = "proactive"

    llm_config = ModelRunConfig.get_default_config()
    print(f"  LLM Provider: {llm_config.provider}")
    print(f"  LLM Model: {llm_config.model_name}")

    io = InputOutput()
    siada_config = RunningConfig(
        llm_config=llm_config,
        io=io,
        workspace=current_dir,
        agent_name=agent_name,
        console_output=True,
        interactive=False,
    )

    print("\n[Step 2] Creating session...")
    session = RunningSessionManager.create_session(siada_config)
    print(f"  Session ID: {session.session_id}")
    print(f"  Workspace: {session.siada_config.workspace}")

    print("\n[Step 3] Preparing task instruction...")
    user_input = get_update_personal_style_instruction()
    print(f"  Instruction length: {len(user_input)} characters")

    print("\n--- Task Instruction Preview ---")
    for line in user_input.split('\n')[:15]:
        print(f"  {line}")
    print("  ... (truncated)")
    print("--- End Preview ---")

    print("\n[Step 4] Running ProactiveAgent using SiadaRunner...")
    print("-" * 80)

    try:
        result = await SiadaRunner.run_agent(
            agent_name=agent_name,
            user_input=user_input,
            workspace=current_dir,
            session=session,
        )

        print("\n" + "=" * 80)
        print("[Step 5] Agent Execution Completed")
        print("=" * 80)

        if hasattr(result, 'to_input_list'):
            messages = result.to_input_list()
            print("\n--- Agent Output ---")
            for msg in messages:
                if msg.get('role') == 'assistant':
                    content = msg.get('content', '')
                    if isinstance(content, str) and content.strip():
                        print(content[:1000] + "\n... (truncated)" if len(content) > 1000 else content)
            print("--- End Agent Output ---")

        return result

    except Exception as e:
        print(f"\n✗ Error during agent execution: {e}")
        import traceback
        traceback.print_exc()
        raise


def run_main():
    asyncio.run(main())


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("ProactiveAgent Update Personal Style Example")
    print("=" * 80)
    print("\nStarting...\n")
    run_main()
    print("\n" + "=" * 80)
    print("Example completed!")
    print("=" * 80 + "\n")
