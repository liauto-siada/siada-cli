import unittest
import sys
import os

# Add the project root to the path so we can import siada modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from siada.tools.coder.cmd_runner import run_cmd_subprocess, run_cmd_pexpect, MAX_OUTPUT_LENGTH


class TestCmdRunnerOutputTruncation(unittest.TestCase):
    """Test cases for output truncation functionality in cmd_runner module"""

    def test_subprocess_output_truncation(self):
        """Test that run_cmd_subprocess truncates output when it exceeds MAX_OUTPUT_LENGTH"""
        # Create a command that generates more than MAX_OUTPUT_LENGTH characters
        # Each 'A' is 1 character, so we generate MAX_OUTPUT_LENGTH + 1000 characters
        excess_chars = 1000
        total_chars = MAX_OUTPUT_LENGTH + excess_chars
        command = f"python3 -c \"print('A' * {total_chars})\""
        
        returncode, output = run_cmd_subprocess(command, verbose=False)
        
        self.assertEqual(returncode, 0)
        self.assertLess(len(output), total_chars)
        self.assertIn("Output truncated", output)
        self.assertIn(str(MAX_OUTPUT_LENGTH), output)

    def test_subprocess_normal_output_not_truncated(self):
        """Test that normal output under the limit is not truncated"""
        command = "echo 'This is a normal short output'"
        
        returncode, output = run_cmd_subprocess(command, verbose=False)
        
        self.assertEqual(returncode, 0)
        self.assertNotIn("Output truncated", output)
        self.assertIn("This is a normal short output", output)

    def test_subprocess_output_at_limit(self):
        """Test output exactly at the limit"""
        # Generate exactly MAX_OUTPUT_LENGTH characters (minus newline)
        chars_needed = MAX_OUTPUT_LENGTH - 1  # Account for newline
        command = f"python3 -c \"print('B' * {chars_needed}, end='')\""
        
        returncode, output = run_cmd_subprocess(command, verbose=False)
        
        self.assertEqual(returncode, 0)
        self.assertLessEqual(len(output), MAX_OUTPUT_LENGTH + 100)  # Allow some margin for truncation message
        # Should not be truncated if exactly at limit
        if len(output) <= MAX_OUTPUT_LENGTH:
            self.assertNotIn("Output truncated", output)

    def test_subprocess_progressive_truncation(self):
        """Test that truncation works during progressive output"""
        # Command that outputs characters progressively
        chars_per_batch = 1000
        num_batches = (MAX_OUTPUT_LENGTH // chars_per_batch) + 2  # Ensure we exceed the limit
        command = f"python3 -c \"import time; [print('C' * {chars_per_batch}, end='', flush=True) or time.sleep(0.01) for _ in range({num_batches})]\""
        
        returncode, output = run_cmd_subprocess(command, verbose=False)
        
        self.assertEqual(returncode, 0)
        self.assertIn("Output truncated", output)
        self.assertIn(str(MAX_OUTPUT_LENGTH), output)

    def test_max_output_length_constant(self):
        """Test that MAX_OUTPUT_LENGTH is set to expected value"""
        self.assertEqual(MAX_OUTPUT_LENGTH, 20000)

    def test_truncation_message_format(self):
        """Test that truncation message has the expected format"""
        # Generate output that will be truncated
        excess_chars = 1000
        total_chars = MAX_OUTPUT_LENGTH + excess_chars
        command = f"python3 -c \"print('D' * {total_chars})\""
        
        returncode, output = run_cmd_subprocess(command, verbose=False)
        
        self.assertEqual(returncode, 0)
        self.assertIn("... [Output truncated, exceeded 20000 character limit] ...", output)


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)
