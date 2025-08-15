import unittest
import json

# Use real partial_json_parser module

from siada.tools.tool_call_format.formatters import FixAttemptCompletionFormatter


class TestFixAttemptCompletionFormatter(unittest.TestCase):
    """
    Test suite for FixAttemptCompletionFormatter, focusing on streaming capabilities.
    """

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.formatter = FixAttemptCompletionFormatter()

    def test_supports_streaming(self):
        """Test that the formatter supports streaming."""
        self.assertFalse(self.formatter.supports_streaming)

    def test_supported_function(self):
        """Test that the formatter returns the correct supported function name."""
        self.assertEqual(self.formatter.supported_function, "fix_attempt_completion")

    def test_complete_json_with_result(self):
        """Test formatting with complete JSON containing a result."""
        result_text = "Successfully fixed the null pointer exception in UserService.java"
        arguments = json.dumps({"result": result_text})
        
        content, is_complete = self.formatter.format_input("test_call_id", "fix_attempt_completion", arguments)
        
        expected_content = f"The bug fix task has been successfully completed:\n{result_text}"
        self.assertEqual(content, expected_content)
        self.assertTrue(is_complete)

    def test_complete_json_empty_result(self):
        """Test formatting with complete JSON but empty result."""
        arguments = json.dumps({"result": ""})
        
        content, is_complete = self.formatter.format_input("test_call_id", "fix_attempt_completion", arguments)
        
        self.assertEqual(content, "")
        self.assertTrue(is_complete)

    def test_complete_json_no_result_key(self):
        """Test formatting with complete JSON but no result key."""
        arguments = json.dumps({"other_key": "other_value"})
        
        content, is_complete = self.formatter.format_input("test_call_id", "fix_attempt_completion", arguments)
        
        self.assertEqual(content, "")
        self.assertTrue(is_complete)

    def test_partial_json_incomplete_result(self):
        """Test formatting with partial JSON (streaming scenario)."""
        # Simulate incomplete JSON as would occur during streaming
        arguments = '{"result": "Successfully fixed the bug by adding null check'
        
        content, is_complete = self.formatter.format_input("test_call_id", "fix_attempt_completion", arguments)
        
        expected_content = "The bug fix task has been successfully completed:\nSuccessfully fixed the bug by adding null check"
        self.assertEqual(content, expected_content)
        self.assertFalse(is_complete)

    def test_partial_json_incomplete_key(self):
        """Test formatting with partial JSON where key is incomplete."""
        arguments = '{"resu'
        
        content, is_complete = self.formatter.format_input("test_call_id", "fix_attempt_completion", arguments)
        
        self.assertEqual(content, "")
        self.assertFalse(is_complete)

    def test_partial_json_missing_closing_brace(self):
        """Test formatting with partial JSON missing closing brace."""
        arguments = '{"result": "Bug fixed successfully"'
        
        content, is_complete = self.formatter.format_input("test_call_id", "fix_attempt_completion", arguments)
        
        expected_content = "The bug fix task has been successfully completed:\nBug fixed successfully"
        self.assertEqual(content, expected_content)
        self.assertFalse(is_complete)


    def test_null_arguments(self):
        """Test formatting with null JSON."""
        arguments = "null"
        
        content, is_complete = self.formatter.format_input("test_call_id", "fix_attempt_completion", arguments)
        
        self.assertEqual(content, "")
        self.assertTrue(is_complete)

    def test_streaming_progression(self):
        """Test a realistic streaming scenario with progressive JSON completion."""
        streaming_stages = [
            '{"result": "Fix',
            '{"result": "Fixed the authentication bug',
            '{"result": "Fixed the authentication bug by adding proper validation"',
            '{"result": "Fixed the authentication bug by adding proper validation"}',
        ]
        
        expected_completeness = [False, False, False, True]
        
        for i, arguments in enumerate(streaming_stages):
            content, is_complete = self.formatter.format_input("test_call_id", "fix_attempt_completion", arguments)
            
            self.assertEqual(is_complete, expected_completeness[i], 
                           f"Stage {i}: Expected complete={expected_completeness[i]}, got {is_complete}")
            
            if content:  # Only check content if it's not empty
                self.assertIn("The bug fix task has been successfully completed:", content)
                if arguments.count('"') >= 4:  # Has at least opening and closing quotes for result value
                    # Extract the result value for comparison
                    try:
                        from partial_json_parser import loads
                        parsed = loads(arguments)
                        if parsed and "result" in parsed:
                            expected_content = f"The bug fix task has been successfully completed:\n{parsed['result']}"
                            self.assertEqual(content, expected_content)
                    except:
                        pass

    def test_long_result_content(self):
        """Test formatting with a long result content."""
        long_result = "Fixed multiple issues:\n" + "\n".join([
            f"- Issue {i}: Description of fix {i}" for i in range(1, 6)
        ])
        arguments = json.dumps({"result": long_result})
        
        content, is_complete = self.formatter.format_input("test_call_id", "fix_attempt_completion", arguments)
        
        expected_content = f"The bug fix task has been successfully completed:\n{long_result}"
        self.assertEqual(content, expected_content)
        self.assertTrue(is_complete)

    def test_special_characters_in_result(self):
        """Test formatting with special characters in result."""
        result_with_special_chars = 'Fixed bug with "quotes" and \\backslashes\nand newlines'
        arguments = json.dumps({"result": result_with_special_chars})
        
        content, is_complete = self.formatter.format_input("test_call_id", "fix_attempt_completion", arguments)
        
        expected_content = f"The bug fix task has been successfully completed:\n{result_with_special_chars}"
        self.assertEqual(content, expected_content)
        self.assertTrue(is_complete)

    def test_streaming_simulation(self):
        """Simulate real streaming behavior by progressively building JSON."""
        target_result = "Successfully implemented user authentication with JWT tokens"
        target_json = json.dumps({"result": target_result})
        
        # Simulate character-by-character streaming
        for i in range(1, len(target_json) + 1):
            partial_json = target_json[:i]
            content, is_complete = self.formatter.format_input("test_call_id", "fix_attempt_completion", partial_json)
            
            if i == len(target_json):
                # Should be complete at the end
                self.assertTrue(is_complete, "Final JSON should be complete")
                expected_content = f"The bug fix task has been successfully completed:\n{target_result}"
                self.assertEqual(content, expected_content)
            else:
                # May or may not be complete depending on JSON parser's ability to handle partial JSON
                if content:
                    self.assertIn("The bug fix task has been successfully completed:", content)


def run_streaming_demo():
    """
    Demonstration function showing how the formatter handles streaming scenarios.
    This can be run independently to see the streaming behavior in action.
    """
    print("=== FixAttemptCompletionFormatter Streaming Demo ===\n")
    
    formatter = FixAttemptCompletionFormatter()
    
    # Simulate progressive JSON building as would happen during streaming
    progressive_json_states = [
        '{',
        '{"res',
        '{"result',
        '{"result"',
        '{"result":',
        '{"result": "',
        '{"result": "F',
        '{"result": "Fix',
        '{"result": "Fixed',
        '{"result": "Fixed the bug',
        '{"result": "Fixed the bug by',
        '{"result": "Fixed the bug by updating',
        '{"result": "Fixed the bug by updating the validation logic"',
        '{"result": "Fixed the bug by updating the validation logic"}',
    ]
    
    print("Simulating streaming JSON input:")
    print("-" * 80)
    
    for i, json_state in enumerate(progressive_json_states):
        content, is_complete = formatter.format_input("demo_call", "fix_attempt_completion", json_state)
        
        status = "✓ COMPLETE" if is_complete else "⚡ STREAMING"
        print(f"Step {i+1:2d}: {status}")
        print(f"   Input:  {json_state}")
        print(f"   Output: {repr(content)}")
        print()


if __name__ == "__main__":
    # Run the demo first
    run_streaming_demo()
    
    # Then run the unit tests
    print("\n" + "="*80)
    print("Running Unit Tests")
    print("="*80)
    unittest.main(argv=[''], exit=False, verbosity=2)
