#!/usr/bin/env python3
"""
Siada automated test runner
Automatically discovers and runs all test_*.py files
"""

import subprocess
import sys
from pathlib import Path
import argparse

class AutoTestRunner:
    def __init__(self, test_root: str = None):
        if test_root is None:
            # Auto-detect: if current directory is tests, use current directory; otherwise use tests subdirectory
            current_dir = Path.cwd()
            if current_dir.name == "tests":
                self.test_root = Path(".")
            else:
                self.test_root = Path("tests")
        else:
            self.test_root = Path(test_root)
    
    def discover_tests(self) -> list[Path]:
        """Automatically discover all test_*.py files"""
        return list(self.test_root.rglob("test_*.py"))
    
    def run_tests(self, verbose: bool = True) -> bool:
        """Run all automated tests"""
        test_files = self.discover_tests()
        
        if not test_files:
            print("❌ No automated test files found (test_*.py)")
            return False
        
        print(f"🔍 Found {len(test_files)} automated test files")
        
        if verbose:
            for test_file in test_files:
                print(f"  - {test_file}")
        
        print(f"\n🧪 Starting automated tests...")
        
        # Use pytest to run tests
        cmd = [
            sys.executable, "-m", "pytest",
            str(self.test_root),
            "-v" if verbose else "-q",
            "--tb=short",  # Show brief error information
            "--color=yes"
        ]
        
        result = subprocess.run(cmd)
        
        success = result.returncode == 0
        print(f"\n{'✅ All tests passed!' if success else '❌ Some tests failed!'}")
        
        return success

def main():
    parser = argparse.ArgumentParser(
        description="Siada automated test runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  python run_tests.py           # Run all automated tests
  python run_tests.py --quiet   # Run in quiet mode
  python run_tests.py --list    # Only list test files
        """
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode")
    parser.add_argument("--list", "-l", action="store_true", help="Only list test files, don't run")
    
    args = parser.parse_args()
    
    runner = AutoTestRunner()
    
    if args.list:
        test_files = runner.discover_tests()
        print(f"Found {len(test_files)} automated test files:")
        for test_file in test_files:
            print(f"  - {test_file}")
        return
    
    success = runner.run_tests(verbose=not args.quiet)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
