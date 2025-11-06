import subprocess
import re
from typing import List, Optional
from pathlib import Path
import os
import pandas as pd

class GitDiffUtil:
    """Utility class for getting Git repository diff information, excluding test files."""

    @staticmethod
    def get_git_diff(repo_path: str = ".") -> str:
        """
        Get the complete diff of the current Git repository.

        Args:
            repo_path: Path to the Git repository, defaults to current directory.

        Returns:
            str: Returns the complete diff information.
        """
        if repo_path == ".":
            repo_path = Path.cwd()
        else:
            repo_path = Path(repo_path).resolve()
        
        if not (repo_path / ".git").exists():
            raise ValueError(f"Git diff failed: Path {repo_path} is not a valid Git repository.")
        
        cmd = ['git', 'diff']
        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise Exception(f"Git diff failed: {e.stderr}")

    @staticmethod
    def get_git_diff_exclude_test_files(repo_path: str = ".") -> str:
        """
        Get the complete diff of the current Git repository, excluding test files.

        Args:
            repo_path: Path to the Git repository, defaults to current directory.

        Returns:
            str: Returns the diff information excluding test files.
        """
        if repo_path == ".":
            repo_path = Path.cwd()
        else:
            repo_path = Path(repo_path).resolve()
        print(f"try to get git diff from {repo_path}\n")
        if not (repo_path / ".git").exists():
            git_dir = GitDiffUtil._find_git_root(repo_path)
            if git_dir:
                repo_path = git_dir
            else:
                raise ValueError(f"Git diff failed: Path {repo_path} is not a valid Git repository.")
        
        cmd = ['git', 'diff', '--', ':(exclude)test*/', ':(exclude)**/*test*']
        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            if result.stdout.strip() == "":
                cmd = ['git', 'diff', '--', 'src/']
                result = subprocess.run(
                    cmd,
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=True
                )
            print(f"git diff result: {result.stdout}\n")
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise Exception(f"Git diff failed: {e.stderr}")


    @staticmethod
    def _find_git_root(path: Path) -> Optional[Path]:
        """
        Search upward for Git repository root directory
        
        Args:
            path: Starting search path
            
        Returns:
            Git repository root directory path, or None if not found
        """
        current = path.resolve()
        
        while current != current.parent:
            if (current / '.git').exists():
                return current
            current = current.parent
        
        return None


    @staticmethod
    def get_git_diff_analysis(repo_path: str = ".") -> dict:
        """
        Get Git diff analysis results, including added, deleted, total lines and net changes.

        Args:
            repo_path: Path to the Git repository, defaults to current directory.

        Returns:
            dict: Dictionary containing added, deleted, total lines and net changes.
        """
        diff_text = GitDiffUtil.get_git_diff_exclude_test_files(repo_path)
        
        return {
            'diff_patch': diff_text,
            'line_changes': GitDiffUtil.parse_diff_lines(diff_text),
            'patch_complexity': GitDiffUtil.analyze_patch_complexity(diff_text)
        }

    def parse_diff_lines(diff_text: str) -> dict:
        """
        Analyze git diff to count added, deleted, and total changed lines.
        
        Args:
            diff_text (str): git diff text
        
        Returns:
            dict: including added, deleted, total, and net changes
        """
        if not diff_text or pd.isna(diff_text):
            return {'added': 0, 'deleted': 0, 'total': 0, 'net': 0}
        
        lines = diff_text.split('\n')
        added_lines = 0
        deleted_lines = 0
        
        for line in lines:
            if (line.startswith('diff --git') or 
                line.startswith('index ') or 
                line.startswith('--- ') or 
                line.startswith('+++ ') or 
                line.startswith('@@')):
                continue
            
            if line.startswith('+') and not line.startswith('+++'):
                added_lines += 1
            elif line.startswith('-') and not line.startswith('---'):
                deleted_lines += 1
        
        total_changes = added_lines + deleted_lines
        net_changes = added_lines - deleted_lines
        
        return {
            'added': added_lines,
            'deleted': deleted_lines,
            'total': total_changes,
            'net': net_changes
        }
    
    def analyze_patch_complexity(diff_text:str) -> dict:
        """
        Analyze the complexity of the patch from git diff text.
        
        Args:
            diff_text (str): git diff text  
        
        Returns:
            dict: including number of files changed and whether function definitions were changed
        """
        if not diff_text or pd.isna(diff_text):
            return {'files_changed': 0, 'has_function_changes': False}
        
        file_pattern = r'diff --git a/(.*?) b/'
        files_changed = len(re.findall(file_pattern, diff_text))
        
        function_patterns = [
            r'[+-]\s*def\s+\w+',  
            r'[+-]\s*function\s+\w+',  
            r'[+-]\s*class\s+\w+', 
        ]
        
        has_function_changes = any(re.search(pattern, diff_text) for pattern in function_patterns)
        
        return {
            'files_changed': files_changed,
            'has_function_changes': has_function_changes
        }

# Example usage
if __name__ == "__main__":
    # from siada.foundation.tools.get_git_diff import GitDiffUtil
    # Example usage
    try:
        diff = GitDiffUtil.get_git_diff_exclude_test_files(repo_path="/Users/caoxin/Projects/AgentHub/siada-agenthub")
        print("Git diff (excluding test files):")
        print(diff)
    except Exception as e:
        print(f"Error: {e}")
