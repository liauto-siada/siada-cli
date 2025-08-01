"""
Test for BugFixAgent.run_checker_by_agent method
Tests that the method returns a dictionary with is_fixed and check_summary fields
"""
import unittest
import asyncio

from siada.agent_hub.coder.bug_fix_agent import BugFixAgent
from siada.foundation.code_agent_context import CodeAgentContext


class RunCheckerByAgent:
    """Test the run_checker_by_agent method"""

    def setUp(self):
        """Set up test environment"""
        self.agent = BugFixAgent()
        self.root_dir = "/Users/yunan/code/test/test_ai"
        self.context = CodeAgentContext(root_dir=self.root_dir)
        
        # Issue description for testing
        self.user_input = """
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

    async def run_checker_by_agent_returns_dict_with_required_fields(self):
        """
        Test that run_checker_by_agent returns a dictionary containing is_fixed and check_summary fields.
        If the return value is not a dictionary or missing required fields, the test should fail.
        """
        # Execute the method under test
        result = await self.agent.run_checker_by_agent(self.user_input, self.context)
        
        # Assert that the result is a dictionary
        assert isinstance(result, dict), \
            f"Expected result to be a dict, but got {type(result).__name__}: {result}"
        
        # Assert that the dictionary contains the required 'is_fixed' field
        assert 'is_fixed' in result, \
            f"Expected 'is_fixed' field in result dictionary. Got keys: {list(result.keys())}"
        
        # Assert that the dictionary contains the required 'check_summary' field
        assert 'check_summary' in result, \
            f"Expected 'check_summary' field in result dictionary. Got keys: {list(result.keys())}"
        
        # Optional: Print the result for debugging purposes
        print(f"Test passed! Result: {result}")


def main():
    checker = RunCheckerByAgent()
    checker.setUp()
    asyncio.run(checker.run_checker_by_agent_returns_dict_with_required_fields())

if __name__ == '__main__':
    main()
