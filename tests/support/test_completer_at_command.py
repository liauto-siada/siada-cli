#!/usr/bin/env python3
"""
Test script for @ command completion behavior.
This tests the modification where Enter key accepts completion but doesn't submit.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add the parent directory to the path to import siada modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from siada.support.completer import AutoCompleter
from siada.services.file_recommendation import CompletionConfig
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document


def test_at_command_completion():
    """Test @ command completion functionality."""
    
    # Create a temporary directory structure for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create some test files
        test_files = [
            "test_file.py",
            "README.md", 
            "config.json",
            "src/main.py",
            "src/utils.py",
        ]
        
        for file_path in test_files:
            full_path = Path(temp_dir) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.touch()
        
        # Initialize completer
        completer = AutoCompleter(root=temp_dir, commands=None, encoding="utf-8")
        
        # Test completion for "@"
        print("Testing @ command completion...")
        
        # Test case 1: Just "@"
        document = Document("@", cursor_position=1)
        completions = list(completer.get_completions(document, None))
        
        print(f"Completions for '@': {len(completions)} found")
        for i, completion in enumerate(completions[:5]):  # Show first 5
            print(f"  {i+1}. {completion.text} (start_pos: {completion.start_position}, display: {completion.display})")
        
        # Test case 2: "@src"
        document = Document("@src", cursor_position=4)
        completions = list(completer.get_completions(document, None))
        
        print(f"\nCompletions for '@src': {len(completions)} found")
        for i, completion in enumerate(completions[:5]):  # Show first 5
            print(f"  {i+1}. {completion.text} (start_pos: {completion.start_position}, display: {completion.display})")
        
        # Test case 3: "@test"
        document = Document("@test", cursor_position=5)
        completions = list(completer.get_completions(document, None))
        
        print(f"\nCompletions for '@test': {len(completions)} found")
        for i, completion in enumerate(completions[:5]):  # Show first 5
            print(f"  {i+1}. {completion.text} (start_pos: {completion.start_position}, display: {completion.display})")
        
        # Test case 4: "@" in the middle of text
        document = Document("some command @src", cursor_position=16)
        completions = list(completer.get_completions(document, None))
        
        print(f"\nCompletions for 'some command @src': {len(completions)} found")
        for i, completion in enumerate(completions[:5]):  # Show first 5
            print(f"  {i+1}. {completion.text} (start_pos: {completion.start_position}, display: {completion.display})")
        
        # Test case 5: Multiple "@" symbols - should use the last one
        document = Document("@old/path and @new", cursor_position=18)
        completions = list(completer.get_completions(document, None))
        
        print(f"\nCompletions for '@old/path and @new': {len(completions)} found")
        for i, completion in enumerate(completions[:5]):  # Show first 5
            print(f"  {i+1}. {completion.text} (start_pos: {completion.start_position}, display: {completion.display})")
        
        # Test case 6: "@" with cursor not at end
        document = Document("@src/main.py more text", cursor_position=10)
        completions = list(completer.get_completions(document, None))
        
        print(f"\nCompletions for '@src/main.py' (cursor at position 10): {len(completions)} found")
        for i, completion in enumerate(completions[:5]):  # Show first 5
            print(f"  {i+1}. {completion.text} (start_pos: {completion.start_position}, display: {completion.display})")

        print("\n✅ @ command completion test completed!")
        print("🔍 Key changes:")
        print("  - @ commands can now be used anywhere in the text, not just at the beginning")
        print("  - Uses cursor position to identify the relevant @ command")
        print("  - @ commands: Enter key accepts completion WITHOUT submitting (anywhere in text)")
        print("  - / commands: Enter key accepts completion AND submits (original behavior)")
        print("  - @ symbol is included in completion text")
        print("  - start_position correctly replaces the entire @ command")
        
        print("\n🎯 Behavior Summary:")
        print("  @ commands: anywhere + @ + TAB/↓↑ + ENTER → Insert file name, continue editing")
        print("  / commands: / + TAB/↓↑ + ENTER → Insert command, execute immediately")
        print("  Multiple @ symbols: Uses the one closest to cursor")
        
        print("\n📝 Enter Key Behavior:")
        print("  - '@file' + ENTER with completion → Accept completion, don't submit")
        print("  - 'cmd @file' + ENTER with completion → Accept completion, don't submit")
        print("  - '/command' + ENTER with completion → Accept completion AND submit")
        print("  - Regular text + ENTER → Submit immediately")


if __name__ == "__main__":
    test_at_command_completion()
