import getpass
import os
import platform
import subprocess

import pandas as pd

from siada.foundation.logging import logger
from benchmark.swe.tools.git_util import reset_git_changes, checkout_to_commit
from benchmark.swe.tools.swe_const import MAP_REPO_VERSION_TO_SPECS


def create_env(instance: pd.Series):
    absolute_workspace, _, _ = _get_swebench_workspace_dir_name(instance)
    instance_id = instance.instance_id

    # 1. 删除仓库的所有变更内容
    reset_git_changes(absolute_workspace)

    # 2. 切换至当前issue的指针
    checkout_to_commit(absolute_workspace, instance.base_commit)

    # 3. 应用测试patch
    # apply_patch(absolute_workspace, instance.test_patch)
    # 应用原始patch

    logger.info("Start to create conda env")
    is_create_new = create_conda_env(instance_id=instance_id, repo=instance.repo, version=instance.version, is_delete_old=False)
    logger.info("complete to create conda env")
    if is_create_new:
        # 安装依赖
        logger.info("Start to install requirements")
        install_requirements(instance_id, absolute_workspace, repo=instance.repo, version=instance.version)
        logger.info("Complete to install requirements")

    return instance_id


def _get_swebench_workspace_dir_name(instance: pd.Series) -> tuple[str, str, str]:
    # return f'{instance.repo}__{instance.version}'.replace('/', '__')
    workspace = f'{instance.repo}'.replace('/', '__')
    username = getpass.getuser()
    system = platform.system()
    if system == 'Linux':
        parent_path = f'/home/{username}/code/swe/swe-data-repo/'
    else:
        parent_path = f'/Users/{username}/code/swe/swe-data-repo/'
    absolute_workspace = parent_path + workspace
    if system == 'Linux':
        absolute_workspace = f'/testbed'
        return absolute_workspace, "/", "testbed"
    return absolute_workspace, parent_path, workspace


def get_repo_config(repo: str, version: str) -> dict:
    """
    根据 repo 和 version 从 swe_const 中获取对应的配置
    
    Args:
        repo (str): 仓库名称，格式如 "django/django"
        version (str): 版本号
    
    Returns:
        dict: 配置字典，包含 python 版本、packages、install 命令等
    """
    if repo not in MAP_REPO_VERSION_TO_SPECS:
        logger.warning(f"Repository {repo} not found in MAP_REPO_VERSION_TO_SPECS")
        return {}

    repo_specs = MAP_REPO_VERSION_TO_SPECS[repo]

    if version in repo_specs:
        return repo_specs[version]
    else:
        logger.warning(f"Version {version} not found for repository {repo}")
        return {}


def generate_conda_env_script(env_name: str, config: dict) -> str:
    """
    根据配置生成创建 conda 环境的脚本字符串
    
    Args:
        env_name (str): 环境名称
        config (dict): 配置字典
    
    Returns:
        str: 完整的脚本字符串
    """
    python_version = config.get("python", "3.8")
    packages = config.get("packages", "")

    script_lines = [
        "#!/bin/bash",
        "set -e",
        "",
        f"# 创建 conda 环境: {env_name}",
        f"echo 'Creating conda environment {env_name} with Python {python_version}'",
        ""
    ]

    # 检查环境是否存在
    script_lines.extend([
        "# 检查环境是否已存在",
        f"if conda env list | grep -q '{env_name}'; then",
        f"    echo 'Environment {env_name} already exists'",
        "    exit 0",
        "fi",
        ""
    ])

    # 创建环境
    if packages and packages != "requirements.txt" and packages != "environment.yml":
        script_lines.append(f"conda create -n {env_name} python={python_version} {packages} -y")
    else:
        script_lines.append(f"conda create -n {env_name} python={python_version} -y")

    script_lines.extend([
        "",
        f"echo 'Successfully created conda environment {env_name}'",
        ""
    ])

    return "\n".join(script_lines)


def generate_install_requirements_script(env_name: str, config: dict, root_path: str) -> str:
    """
    根据配置生成安装依赖的脚本字符串
    
    Args:
        env_name (str): 环境名称
        config (dict): 配置字典
        root_path (str): 项目根路径
    
    Returns:
        str: 完整的脚本字符串
    """
    script_lines = [
        "#!/bin/bash",
        "set -e",
        "",
        f"# 安装依赖到环境: {env_name}",
        f"cd {root_path}",
        ""
    ]

    # 预安装命令
    pre_install = config.get("pre_install", [])
    if pre_install:
        processed_pre_install = []
        for cmd in pre_install:
            if "pip install" in cmd:
                # 在包含 pip install 的命令前加上 conda run
                processed_pre_install.append(f"conda run -n {env_name} python -m {cmd}")
            else:
                processed_pre_install.append(cmd)

        script_lines.extend([
            "# 预安装命令",
            *processed_pre_install,
            ""
        ])

    # # 主安装命令
    #     # install_cmd = config.get("install", "python -m pip install -e .")
    #     # script_lines.extend([
    #     #     "# 主安装命令",
    #     #     f"conda run -n {env_name} {install_cmd}",
    #     #     ""
    #     # ])

    # 安装 pip 包
    pip_packages = config.get("pip_packages", [])
    if pip_packages:
        script_lines.extend([
            "# 安装 pip 包",
            f"conda run -n {env_name} python -m pip install {' '.join(pip_packages)}",
            ""
    ])

    # 评估命令
    eval_commands = config.get("eval_commands", [])
    if eval_commands:
        script_lines.extend([
            "# 评估命令",
            *eval_commands,
            ""
        ])

    script_lines.extend([
        f"echo 'Successfully installed requirements for {env_name}'",
        ""
    ])

    return "\n".join(script_lines)


def create_conda_env(instance_id: str, repo: str = None, version: str = None, is_delete_old: bool = False) -> bool:
    """
    根据 instance_id 创建对应名字的虚拟环境，并根据 repo 和 version 获取对应的配置
    
    Args:
        instance_id (str): 实例ID，用作环境名称
        repo (str): 仓库名称，用于获取配置
        version (str): 版本号，用于获取配置
        is_delete_old (bool): 是否删除已存在的环境
    
    Returns:
        bool: 是否创建了新环境
    """
    env_name = instance_id

    logger.info(f"检查已存在的环境列表")
    try:
        env_list = subprocess.run(["conda", "env", "list"], check=True, stdout=subprocess.PIPE).stdout.decode()
    except subprocess.CalledProcessError as e:
        logger.error(f"获取 conda 环境列表失败: {e}")
        return False

    # 检查环境是否存在
    if env_name in env_list:
        if is_delete_old:
            remove_conda_env(env_name)
        else:
            logger.info(f"环境已存在: {env_name}")
            return False

    # 获取配置
    config = {}
    if repo and version:
        config = get_repo_config(repo, version)

    # 生成并执行脚本
    script = generate_conda_env_script(env_name, config)

    logger.info(f"开始创建环境 '{env_name}'")
    logger.debug(f"执行脚本:\n{script}")

    try:
        # 执行脚本
        result = subprocess.run(script, shell=True, check=True, capture_output=True, text=True)
        logger.info(f"成功创建 conda 环境 '{env_name}'")
        logger.debug(f"脚本输出: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"创建环境失败: {e}")
        logger.error(f"错误输出: {e.stderr}")
        return False


def remove_conda_env(env_name: str):
    """
    Remove the specified conda environment.

    Args:
        env_name (str): The name of the conda environment to remove.

    Returns:
        None
    """
    # Remove the conda environment
    subprocess.run(["conda", "remove", "-n", env_name, "--all", "-y"], check=True)
    print(f"Successfully removed conda environment '{env_name}'")


def install_requirements(env_name: str, root_path: str, repo: str = None, version: str = None):
    """
    根据环境名称和配置安装依赖，使用脚本字符串执行
    
    Args:
        env_name (str): 环境名称
        root_path (str): 项目根路径
        repo (str): 仓库名称，用于获取配置
        version (str): 版本号，用于获取配置
    """
    # 获取配置
    config = {}
    if repo and version:
        config = get_repo_config(repo, version)

    # 生成并执行脚本
    script = generate_install_requirements_script(env_name, config, root_path)

    logger.info(f"开始安装依赖到环境 '{env_name}'")
    logger.debug(f"执行脚本:\n{script}")

    try:
        # 执行脚本
        # 获取当前环境变量的副本
        env = os.environ.copy()

        # 指定 Conda 虚拟环境的路径
        conda_env_path = "/Users/youzijun/miniconda3/envs/" + env_name  # 替换为你的虚拟环境名称

        # 修改 PATH 环境变量，使其优先使用虚拟环境中的可执行文件
        env["PATH"] = f"{conda_env_path}/bin:{env['PATH']}"

        # 修改 CONDA_PREFIX 环境变量，确保 Conda 知道当前激活的环境
        env["CONDA_PREFIX"] = conda_env_path

        # 修改 CONDA_DEFAULT_ENV 环境变量，确保 Conda 知道当前激活的环境名称
        env["CONDA_DEFAULT_ENV"] = env_name  # 替换为你的虚拟环境名称

        result = subprocess.run(script, shell=True, check=True, capture_output=True, text=True, env=env)
        logger.info(f"成功安装依赖到环境 '{env_name}'")
        logger.debug(f"脚本输出: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"安装依赖失败: {e}")
        logger.error(f"错误输出: {e.stderr}")
        raise


if __name__ == "__main__":
    # 测试场景：测试 Django 项目的环境创建和依赖安装
    # print("=== 测试 conda 环境创建和依赖安装 ===")
    #
    # # 测试参数
    test_instance_id = "astropy__astropy-12907"
    test_repo = "astropy/astropy"
    test_version = "5.1"
    # test_root_path = "/Users/youzijun/code/swe/swe-data-repo/astropy__astropy"
    #
    # print(f"测试实例ID: {test_instance_id}")
    # print(f"测试仓库: {test_repo}")
    # print(f"测试版本: {test_version}")
    # print()
    #
    # # 1. 测试获取配置
    # print("1. 测试获取仓库配置...")
    # config = get_repo_config(test_repo, test_version)
    # print(f"获取到的配置: {config}")
    # print()
    #
    # # 2. 测试生成创建环境脚本
    # print("2. 测试生成创建环境脚本...")
    # env_script = generate_conda_env_script(test_instance_id, config)
    # print("生成的环境创建脚本:")
    # print(env_script)
    # print()
    #
    # # 3. 测试生成安装依赖脚本
    # print("3. 测试生成安装依赖脚本...")
    # install_script = generate_install_requirements_script(test_instance_id, config, test_root_path)
    # print("生成的依赖安装脚本:")
    # print(install_script)
    # print()
    instance = pd.Series({
        "instance_id": test_instance_id,
        "repo": test_repo,
        "version": test_version,
        "base_commit": "a5917978be39d13cd90b517e1de4e7a539ffaa48"
    })

    create_env(instance, {"create_env": "true"})

