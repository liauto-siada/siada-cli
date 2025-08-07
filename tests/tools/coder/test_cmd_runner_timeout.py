#!/usr/bin/env python3
"""
Test script to verify the timeout functionality in cmd_runner.py
"""

import sys
import os
import time

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from siada.tools.coder.cmd_runner import run_cmd_impl, COMMAND_TIMEOUT


def test_subprocess_timeout():
    """Test timeout functionality for run_cmd_subprocess"""
    print("=== Testing run_cmd_subprocess timeout ===")
    
    # Command that will definitely take longer than the timeout
    long_running_command = "sleep 70"  # Sleep for 70 seconds (longer than 60s timeout)
    
    print(f"Running command: {long_running_command}")
    print(f"Expected timeout: {COMMAND_TIMEOUT} seconds")
    
    start_time = time.time()
    exit_code, output = run_cmd_impl(long_running_command, verbose=True)
    end_time = time.time()
    
    elapsed_time = end_time - start_time
    
    print(f"Exit code: {exit_code}")
    print(f"Output: {output}")
    print(f"Elapsed time: {elapsed_time:.2f} seconds")
    
    # Verify timeout behavior
    if exit_code == 1 and "timed out" in output.lower():
        print("✅ SUCCESS: Command was properly timed out")
        return True
    else:
        print("❌ FAILED: Command was not properly timed out")
        return False


def test_quick_command():
    """Test that quick commands work normally"""
    print("\n=== Testing quick command (no timeout) ===")
    
    quick_command = "echo 'Hello, World!'"
    
    print(f"Running command: {quick_command}")
    
    start_time = time.time()
    exit_code, output = run_cmd_impl(quick_command, verbose=True)
    end_time = time.time()
    
    elapsed_time = end_time - start_time
    
    print(f"Exit code: {exit_code}")
    print(f"Output: {output}")
    print(f"Elapsed time: {elapsed_time:.2f} seconds")
    
    # Verify normal behavior
    if exit_code == 0 and "Hello, World!" in output:
        print("✅ SUCCESS: Quick command executed normally")
        return True
    else:
        print("❌ FAILED: Quick command did not execute properly")
        return False


if __name__ == "__main__":
    print("Testing cmd_runner timeout functionality...")
    print(f"Current timeout setting: {COMMAND_TIMEOUT} seconds")
    
    results = []
    
    # Test quick command first
    results.append(test_quick_command())
    
    # Test timeout functionality
    print(f"\nNote: The next test will take approximately {COMMAND_TIMEOUT} seconds...")
    results.append(test_subprocess_timeout())
    
    print(f"\n=== SUMMARY ===")
    print(f"Tests passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 All tests PASSED! Timeout functionality is working correctly.")
        sys.exit(0)
    else:
        print("💥 Some tests FAILED. Please check the implementation.")
        sys.exit(1)
