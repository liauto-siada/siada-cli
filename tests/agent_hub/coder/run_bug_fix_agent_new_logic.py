"""
Test for the new BugFixAgent logic using run_checker instead of TestAgent
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from siada.agent_hub.coder.bug_fix_agent import BugFixAgent
from siada.foundation.code_agent_context import CodeAgentContext


class TestBugFixAgentNewLogic(unittest.IsolatedAsyncioTestCase):
    """Test the new BugFixAgent logic with run_checker"""

    def setUp(self):
        """Set up test environment"""
        self.agent = BugFixAgent()
        self.context = CodeAgentContext(root_dir="/test/dir")
        self.user_input = "Test bug description"

    async def test_run_checker_method(self):
        """Test that run_checker method works correctly"""
        # Mock the dependencies
        with patch('siada.foundation.tools.get_git_diff.GitDiffUtil.get_git_diff_exclude_test_files') as mock_git_diff:
            mock_git_diff.return_value = "test diff content"
            
            # Mock the fix_result_checker.check method
            self.agent.fix_result_checker.check = AsyncMock(return_value={
                "is_fixed": True,
                "reason": "Issue has been resolved",
                "analysis": "Detailed analysis"
            })
            
            # Test run_checker
            result = await self.agent.run_checker(self.user_input, self.context)
            
            # Verify the result
            self.assertTrue(result["is_fixed"])
            self.assertEqual(result["reason"], "Issue has been resolved")
            self.assertEqual(result["analysis"], "Detailed analysis")
            
            # Verify that the correct parameters were passed
            self.agent.fix_result_checker.check.assert_called_once_with(
                issue_desc=self.user_input,
                fix_code="test diff content"
            )

    async def test_run_method_with_fixed_issue(self):
        """Test run method when issue is fixed on first attempt"""
        # Mock Runner.run
        mock_result = MagicMock()
        mock_result.to_input_list.return_value = [{"content": "result", "role": "assistant"}]
        
        with patch('agents.Runner.run', new_callable=AsyncMock) as mock_runner:
            mock_runner.return_value = mock_result
            
            # Mock run_checker to return fixed
            with patch.object(self.agent, 'run_checker', new_callable=AsyncMock) as mock_run_checker:
                mock_run_checker.return_value = {
                    "is_fixed": True,
                    "reason": "Issue resolved successfully",
                    "analysis": "Fix analysis"
                }
                
                # Mock assemble_user_input
                with patch.object(self.agent, 'assemble_user_input') as mock_assemble:
                    mock_assemble.return_value = "assembled input"
                    
                    # Test run method
                    result = await self.agent.run(self.user_input, self.context)
                    
                    # Verify that Runner.run was called once (issue fixed on first attempt)
                    self.assertEqual(mock_runner.call_count, 1)
                    
                    # Verify that run_checker was called once
                    mock_run_checker.assert_called_once_with(self.user_input, self.context)
                    
                    # Verify the result is returned
                    self.assertEqual(result, mock_result)

    async def test_run_method_with_unfixed_issue(self):
        """Test run method when issue is not fixed and requires multiple attempts"""
        # Mock Runner.run
        mock_result = MagicMock()
        mock_result.to_input_list.return_value = [{"content": "result", "role": "assistant"}]
        
        with patch('agents.Runner.run', new_callable=AsyncMock) as mock_runner:
            mock_runner.return_value = mock_result
            
            # Mock run_checker to return not fixed for first 2 calls, then fixed
            check_results = [
                {"is_fixed": False, "reason": "Still has issues", "analysis": "Analysis 1"},
                {"is_fixed": False, "reason": "More issues found", "analysis": "Analysis 2"},
                {"is_fixed": True, "reason": "Finally fixed", "analysis": "Analysis 3"}
            ]
            
            with patch.object(self.agent, 'run_checker', new_callable=AsyncMock) as mock_run_checker:
                mock_run_checker.side_effect = check_results
                
                # Mock assemble_user_input
                with patch.object(self.agent, 'assemble_user_input') as mock_assemble:
                    mock_assemble.return_value = "assembled input"
                    
                    # Test run method
                    result = await self.agent.run(self.user_input, self.context)
                    
                    # Verify that Runner.run was called 3 times
                    self.assertEqual(mock_runner.call_count, 3)
                    
                    # Verify that run_checker was called 3 times
                    self.assertEqual(mock_run_checker.call_count, 3)
                    
                    # Verify the result is returned
                    self.assertEqual(result, mock_result)

    async def test_run_method_with_checker_exception(self):
        """Test run method when run_checker raises an exception"""
        # Mock Runner.run
        mock_result = MagicMock()
        mock_result.to_input_list.return_value = [{"content": "result", "role": "assistant"}]
        
        with patch('agents.Runner.run', new_callable=AsyncMock) as mock_runner:
            mock_runner.return_value = mock_result
            
            # Mock run_checker to raise exception on first call, then succeed
            with patch.object(self.agent, 'run_checker', new_callable=AsyncMock) as mock_run_checker:
                mock_run_checker.side_effect = [
                    Exception("Checker failed"),
                    {"is_fixed": True, "reason": "Fixed after error", "analysis": "Analysis"}
                ]
                
                # Mock assemble_user_input
                with patch.object(self.agent, 'assemble_user_input') as mock_assemble:
                    mock_assemble.return_value = "assembled input"
                    
                    # Test run method
                    result = await self.agent.run(self.user_input, self.context)
                    
                    # Verify that Runner.run was called twice
                    self.assertEqual(mock_runner.call_count, 2)
                    
                    # Verify that run_checker was called twice
                    self.assertEqual(mock_run_checker.call_count, 2)
                    
                    # Verify the result is returned
                    self.assertEqual(result, mock_result)

    async def test_run_method_max_turns_reached(self):
        """Test run method when max turns is reached without fixing"""
        # Mock Runner.run
        mock_result = MagicMock()
        mock_result.to_input_list.return_value = [{"content": "result", "role": "assistant"}]
        
        with patch('agents.Runner.run', new_callable=AsyncMock) as mock_runner:
            mock_runner.return_value = mock_result
            
            # Mock run_checker to always return not fixed
            with patch.object(self.agent, 'run_checker', new_callable=AsyncMock) as mock_run_checker:
                mock_run_checker.return_value = {
                    "is_fixed": False,
                    "reason": "Still not fixed",
                    "analysis": "Analysis"
                }
                
                # Mock assemble_user_input
                with patch.object(self.agent, 'assemble_user_input') as mock_assemble:
                    mock_assemble.return_value = "assembled input"
                    
                    # Test run method
                    result = await self.agent.run(self.user_input, self.context)
                    
                    # Verify that Runner.run was called max_turns (3) times
                    self.assertEqual(mock_runner.call_count, 3)
                    
                    # Verify that run_checker was called 3 times
                    self.assertEqual(mock_run_checker.call_count, 3)
                    
                    # Verify the result is returned
                    self.assertEqual(result, mock_result)


if __name__ == '__main__':
    unittest.main()
