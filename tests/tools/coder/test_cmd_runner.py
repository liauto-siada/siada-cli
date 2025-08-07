import time
import unittest
from unittest.mock import patch
import sys
import os

# Add the project root to the path so we can import siada modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from siada.tools.coder.cmd_runner import run_cmd_subprocess, run_cmd_impl, COMMAND_TIMEOUT


class TestCmdRunner(unittest.TestCase):
    """Test cases for cmd_runner module"""

    def test_simple_command_success(self):
        """Test that a simple command executes successfully"""
        returncode, output = run_cmd_subprocess("echo 'Hello World'", verbose=False)
        self.assertEqual(returncode, 0)
        self.assertIn("Hello World", output)

    def test_command_with_multiple_lines(self):
        """Test command that outputs multiple lines"""
        returncode, output = run_cmd_subprocess("echo 'Line 1'; echo 'Line 2'; echo 'Line 3'", verbose=False)
        self.assertEqual(returncode, 0)
        self.assertIn("Line 1", output)
        self.assertIn("Line 2", output)
        self.assertIn("Line 3", output)

    def test_character_by_character_reading(self):
        """Test that output is captured character by character"""
        # Use a command that outputs characters with delays to test real-time reading
        command = "python3 -c \"import sys, time; [print(f'char{i}', end='', flush=True) or time.sleep(0.1) for i in range(5)]; print()\""
        
        start_time = time.time()
        returncode, output = run_cmd_subprocess(command, verbose=False)
        end_time = time.time()
        
        self.assertEqual(returncode, 0)
        self.assertIn("char0", output)
        self.assertIn("char1", output)
        self.assertIn("char2", output)
        self.assertIn("char3", output)
        self.assertIn("char4", output)
        
        # The command should take at least 0.5 seconds (5 chars * 0.1s delay)
        # but less than the timeout (3 seconds)
        self.assertGreater(end_time - start_time, 0.4)
        self.assertLess(end_time - start_time, COMMAND_TIMEOUT)

    def test_timeout_functionality(self):
        """Test that commands timeout after the specified duration"""
        # Command that sleeps longer than the timeout
        command = f"sleep {COMMAND_TIMEOUT + 1}"
        
        start_time = time.time()
        returncode, output = run_cmd_subprocess(command, verbose=False)
        end_time = time.time()
        
        # Should return error code 1 for timeout
        self.assertEqual(returncode, 1)
        self.assertIn("timed out", output.lower())
        self.assertIn(str(COMMAND_TIMEOUT), output)
        
        # Should timeout around the specified time (with some tolerance)
        execution_time = end_time - start_time
        self.assertGreater(execution_time, COMMAND_TIMEOUT - 0.5)
        self.assertLess(execution_time, COMMAND_TIMEOUT + 1.5)

    def test_command_failure(self):
        """Test handling of commands that fail"""
        returncode, output = run_cmd_subprocess("exit 1", verbose=False)
        self.assertEqual(returncode, 1)

    def test_nonexistent_command(self):
        """Test handling of nonexistent commands"""
        returncode, output = run_cmd_subprocess("nonexistent_command_12345", verbose=False)
        # Shell returns 127 for command not found, not 1
        self.assertEqual(returncode, 127)

    def test_verbose_mode(self):
        """Test that verbose mode works without errors"""
        # This test mainly ensures verbose mode doesn't break functionality
        returncode, output = run_cmd_subprocess("echo 'test'", verbose=True)
        self.assertEqual(returncode, 0)
        self.assertIn("test", output)

    def test_working_directory(self):
        """Test that working directory parameter works"""
        # Create a temporary directory for testing
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            returncode, output = run_cmd_subprocess("pwd", verbose=False, cwd=temp_dir)
            self.assertEqual(returncode, 0)
            self.assertIn(temp_dir, output)

    def test_run_cmd_impl_function(self):
        """Test the main run_cmd_impl function"""
        returncode, output = run_cmd_impl("echo 'impl test'", verbose=False)
        self.assertEqual(returncode, 0)
        self.assertIn("impl test", output)

    def test_progressive_output_capture(self):
        """Test that output is captured progressively, not all at once"""
        # Command that outputs text with delays
        command = "python3 -c \"import time; print('start', flush=True); time.sleep(0.5); print('middle', flush=True); time.sleep(0.5); print('end', flush=True)\""
        
        returncode, output = run_cmd_subprocess(command, verbose=False)
        
        self.assertEqual(returncode, 0)
        self.assertIn("start", output)
        self.assertIn("middle", output)
        self.assertIn("end", output)
        
        # Verify the order is maintained
        start_pos = output.find("start")
        middle_pos = output.find("middle")
        end_pos = output.find("end")
        
        self.assertLess(start_pos, middle_pos)
        self.assertLess(middle_pos, end_pos)


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)
