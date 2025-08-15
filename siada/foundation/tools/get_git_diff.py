import subprocess
import re
from typing import List, Optional
from pathlib import Path
import os

class GitDiffUtil:
    """工具类，用于获取 Git 仓库的 diff 信息，排除测试文件。"""

    @staticmethod
    def get_git_diff(repo_path: str = ".") -> str:
        """
        获取当前 Git 仓库的完整 diff。

        Args:
            repo_path: Git 仓库的路径，默认为当前目录。

        Returns:
            str: 返回完整的 diff 信息。
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
        获取当前 Git 仓库的完整 diff，排除测试文件。

        Args:
            repo_path: Git 仓库的路径，默认为当前目录。

        Returns:
            str: 返回排除测试文件后的 diff 信息。
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
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise Exception(f"Git diff failed: {e.stderr}")


    @staticmethod
    def _find_git_root(path: Path) -> Optional[Path]:
        """
        向上查找 Git 仓库根目录
        Args:
            path: 起始查找路径
        Returns:
            Git 仓库根目录路径，如果未找到则返回 None
        """
        current = path.resolve()
        
        while current != current.parent:
            if (current / '.git').exists():
                return current
            current = current.parent
        
        return None

if __name__ == "__main__":
    # from siada.foundation.tools.get_git_diff import GitDiffUtil
    # 示例用法
    try:
        diff = GitDiffUtil.get_git_diff_exclude_test_files(repo_path="/Users/caoxin/Projects/AgentHub/siada-agenthub")
        print("Git diff (excluding test files):")
        print(diff)
    except Exception as e:
        print(f"Error: {e}")