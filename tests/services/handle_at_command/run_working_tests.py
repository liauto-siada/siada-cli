"""
Test runner for HandleAtCommand - Core tests only
"""

import unittest
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_parser import TestAtCommandParser
from test_integration import TestHandleAtCommandIntegration


async def main():
    """Run core HandleAtCommand tests"""
    print("HandleAtCommand Core Test Suite")
    print("=" * 50)
    
    # Run parser tests (sync)
    print("\n1. Parser Tests")
    print("-" * 30)
    suite = unittest.TestSuite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestAtCommandParser))
    runner = unittest.TextTestRunner(verbosity=2)
    parser_result = runner.run(suite)
    
    # Run integration tests (async)
    print("\n2. Integration Tests")
    print("-" * 30)
    
    integration_tests = [
        'test_end_to_end_single_file',
        'test_end_to_end_multiple_files',
        'test_end_to_end_no_at_commands',
        'test_end_to_end_performance'
    ]
    
    integration_passed = 0
    integration_total = len(integration_tests)
    
    for test_name in integration_tests:
        print(f"Running {test_name}...", end=" ")
        try:
            test_instance = TestHandleAtCommandIntegration()
            if hasattr(test_instance, 'asyncSetUp'):
                await test_instance.asyncSetUp()
            
            await getattr(test_instance, test_name)()
            
            if hasattr(test_instance, 'asyncTearDown'):
                await test_instance.asyncTearDown()
            
            print("✅ PASS")
            integration_passed += 1
        except Exception as e:
            print(f"❌ FAIL: {e}")
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    print(f"Parser Tests: {parser_result.testsRun - len(parser_result.failures) - len(parser_result.errors)}/{parser_result.testsRun} passed")
    print(f"Integration Tests: {integration_passed}/{integration_total} passed")
    
    total_passed = (parser_result.testsRun - len(parser_result.failures) - len(parser_result.errors)) + integration_passed
    total_tests = parser_result.testsRun + integration_total
    
    print(f"Overall: {total_passed}/{total_tests} passed ({total_passed/total_tests*100:.1f}%)")
    
    success = len(parser_result.failures) == 0 and len(parser_result.errors) == 0 and integration_passed == integration_total
    print(f"Result: {'✅ ALL TESTS PASSED' if success else '❌ SOME TESTS FAILED'}")
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    asyncio.run(main())
