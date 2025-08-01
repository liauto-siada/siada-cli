issue_desc = """
## Issue Description

In validators.py
Email verification function incorrectly accepts email addresses with purely numeric domain names as valid.

## Affected Email Formats

The following email address patterns are incorrectly validated as __valid__:

- `user@123.com` - Domain name consists entirely of numbers
- `admin@999.org` - Domain name consists entirely of numbers
- `test@12345.net` - Domain name consists entirely of numbers
- `spam@888.net` - Domain name consists entirely of numbers
- `admin@1.co` - Single digit domain name
- `user@0.com` - Zero as domain name
- `fake@777.org` - Domain name consists entirely of numbers

## Expected Behavior

These email addresses should be rejected as invalid because domain names consisting entirely of numeric characters are not standard practice and are rarely used in legitimate email systems.

## Current Behavior

The validator accepts all of the above email formats as valid, allowing potentially problematic email addresses to pass validation.

"""

import asyncio
from siada.services.siada_runner import SiadaRunner


async def run_bugfix():
    # 获取当前工作目录
    current_dir = '/Users/yunan/code/test/test_ai'

    # Define the user input and agent name
    agent_name: str = "bugfix"

    # Run the agent and get the result
    result = await SiadaRunner.run_agent(agent_name=agent_name, user_input=issue_desc, workspace=current_dir)

    # Print the result
    print(result)


def main():
    """Main function to run the codegen test."""
    asyncio.run(run_bugfix())


if __name__ == "__main__":
    main()