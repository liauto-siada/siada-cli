"""
Test script for tree structure generation in search_files_with_walk
"""

import asyncio
import os
from siada.tools.read_many_files_tool import read_files_by_patterns


async def test_tree_structure():
    """Test the tree structure generation"""
    print("Testing tree structure generation...")
    print("=" * 60)
    
    # Test with Python files in siada/tools directory
    result = await read_files_by_patterns(
        paths=["siada/tools/**/*.py"],
        exclude=["**/__pycache__/**", "**/test_*.py"],
        target_dir=os.getcwd()
    )
    
    print("\n=== LLM Content (first 2000 chars) ===")
    if result.llmContent:
        first_content = result.llmContent[0]
        if isinstance(first_content, str):
            print(first_content)
    
    print("\n=== Display Message ===")
    print(result.returnDisplay)
    
    print("\n=== Statistics ===")
    print(f"Total files found: {len(result.llmContent) - 1}")  # -1 for tree structure
    

if __name__ == "__main__":
    asyncio.run(test_tree_structure())
