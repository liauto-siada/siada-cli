import os

import git

from patch_ng import PatchSet

from siada.foundation.logging import logger


def reset_git_changes(repo_path="."):
    try:
        # 加载仓库
        repo = git.Repo(repo_path)

        # 撤销所有未提交的更改（相当于 `git reset --hard`）
        repo.head.reset(index=True, working_tree=True)

        # 删除所有未追踪的文件和目录（相当于 `git clean -fd`）
        repo.git.clean("-fd")

        logger.info_process("Successfully reverted all changes.")
    except Exception as e:
        logger.error(f"Error: {e}")


def checkout_to_commit(repo_path: str, commit: str):
    # 切换到指定的 commit
    os.system(f"cd {repo_path} && git checkout {commit}")


def apply_patch(repo: str, patch_text: str):
    """
    将patch应用到指定的代码仓库

    Args:
        repo (str): 代码仓库的路径
        patch_text (str): patch的内容
    """
    logger.info('apply_patch executed')

    # 确保patch文本格式正确
    if not patch_text.startswith('diff --git'):
        raise ValueError("Invalid patch format")

    try:
        # 创建PatchSet对象并解析patch
        patch_set = PatchSet()
        lines = [line.encode('utf-8') for line in patch_text.splitlines(True)]
        success = patch_set.parse(lines)

        if not success:
            raise Exception("Failed to parse patch")

        # 切换到目标目录
        original_dir = os.getcwd()
        os.chdir(repo)

        try:
            # 应用补丁集
            apply_status = patch_set.apply(root=repo, strip=0)
            if not apply_status:
                raise Exception(f"Failed to apply patch")
            _handle_renames(patch_text, repo)
            logger.info('apply_patch success')

        finally:
            # 确保总是切回原始目录
            os.chdir(original_dir)

    except Exception as e:
        logger.info(f"Error applying patch: {str(e)}")
        raise


def _handle_renames(patch_text, repo):
    lines = patch_text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("rename from "):
            # 获取原文件和目标文件
            original_file = os.path.join(repo, line.split("rename from ")[1].strip())
            renamed_file = os.path.join(repo, lines[i + 1].split("rename to ")[1].strip())

            # 确保原文件存在，然后重命名
            if os.path.exists(original_file):
                os.rename(original_file, renamed_file)
                print(f"Renamed: {original_file} -> {renamed_file}")
            else:
                print(f"File not found for rename: {original_file}")
