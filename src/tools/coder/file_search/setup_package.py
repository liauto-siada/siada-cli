"""
打包配置辅助脚本
用于确保 ripgrep 二进制文件在打包时被正确包含
"""

import os
import stat
from pathlib import Path


def setup_package_data():
    """
    设置打包所需的数据文件配置
    返回用于 setup.py 或 pyproject.toml 的配置
    """
    package_data = {
        'src.tools.coder.file_search': [
            'bin/*',
            'README.md',
        ]
    }
    
    return package_data


def ensure_binary_permissions():
    """
    确保所有二进制文件有正确的执行权限
    在打包前调用此函数
    """
    bin_dir = Path(__file__).parent / "bin"
    
    if not bin_dir.exists():
        print(f"警告: bin 目录不存在: {bin_dir}")
        return
    
    binary_files = [
        "rg.exe",
        "rg-macos-arm64", 
        "rg-macos-x64",
        "rg-linux-arm64",
        "rg-linux-x64"
    ]
    
    for binary_name in binary_files:
        binary_path = bin_dir / binary_name
        if binary_path.exists():
            try:
                # 设置执行权限
                current_mode = binary_path.stat().st_mode
                new_mode = current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                os.chmod(binary_path, new_mode)
                print(f"✓ 设置执行权限: {binary_path}")
            except (OSError, PermissionError) as e:
                print(f"✗ 无法设置权限 {binary_path}: {e}")
        else:
            print(f"⚠ 二进制文件不存在: {binary_path}")


def get_pyproject_toml_config():
    """
    返回用于 pyproject.toml 的配置片段
    """
    config = '''
[tool.setuptools.package-data]
"src.tools.coder.file_search" = ["bin/*", "README.md"]

[tool.setuptools.packages.find]
where = ["src"]
include = ["src.tools.coder.file_search*"]
'''
    return config


def get_setup_py_config():
    """
    返回用于 setup.py 的配置片段
    """
    config = '''
package_data={
    'src.tools.coder.file_search': [
        'bin/*',
        'README.md',
    ],
},
include_package_data=True,
'''
    return config


def validate_package_structure():
    """
    验证包结构是否正确
    """
    base_dir = Path(__file__).parent
    required_files = [
        "__init__.py",
        "search.py", 
        "README.md",
    ]
    
    required_dirs = [
        "bin",
    ]
    
    print("验证包结构...")
    
    # 检查必需文件
    for file_name in required_files:
        file_path = base_dir / file_name
        if file_path.exists():
            print(f"✓ {file_name}")
        else:
            print(f"✗ 缺少文件: {file_name}")
    
    # 检查必需目录
    for dir_name in required_dirs:
        dir_path = base_dir / dir_name
        if dir_path.exists() and dir_path.is_dir():
            print(f"✓ {dir_name}/")
            # 检查 bin 目录中的文件
            if dir_name == "bin":
                bin_files = list(dir_path.glob("*"))
                if bin_files:
                    print(f"  包含 {len(bin_files)} 个二进制文件")
                    for bin_file in bin_files:
                        if bin_file.is_file():
                            print(f"    - {bin_file.name}")
                else:
                    print(f"  ⚠ bin 目录为空")
        else:
            print(f"✗ 缺少目录: {dir_name}/")


if __name__ == "__main__":
    print("File Search - 打包配置检查")
    print("=" * 40)
    
    # 验证包结构
    validate_package_structure()
    
    print("\n" + "=" * 40)
    
    # 设置二进制文件权限
    ensure_binary_permissions()
    
    print("\n" + "=" * 40)
    print("打包配置信息:")
    print("\n1. pyproject.toml 配置:")
    print(get_pyproject_toml_config())
    
    print("\n2. setup.py 配置:")
    print(get_setup_py_config())
    
    print("\n3. 包数据配置:")
    print(setup_package_data())
