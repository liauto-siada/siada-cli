
import asyncio
import os
import tempfile

from siada.services.siada_runner import SiadaRunner


# Workspace used by this demo script. It defaults to a synthetic directory under
# the system temp dir so the script never points at a developer's local checkout.
DEMO_WORKSPACE = os.environ.get(
    "SIADA_DEMO_WORKSPACE",
    os.path.join(tempfile.gettempdir(), "siada-demo-workspace"),
)


async def run_test():
    # 演示工作目录（合成路径）
    current_dir = DEMO_WORKSPACE

    # Define the user input and agent name
    agent_name: str = "test"

    test_input = "Test the email validity verification function"

    # Run the agent and get the result
    result = await SiadaRunner.run_agent(agent_name=agent_name, user_input=test_input, workspace=current_dir)

    # Print the result
    print(result)


def main():
    """Main function to run the codegen test."""
    asyncio.run(run_test())


if __name__ == "__main__":
    main()


