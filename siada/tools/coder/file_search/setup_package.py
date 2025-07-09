"""
Package configuration helper script.
Ensures ripgrep binary files are properly included during packaging.
"""

import os
import stat
from pathlib import Path


def setup_package_data():
    """
    Setup package data configuration for distribution.
    Returns configuration for setup.py or pyproject.toml.
    """
    package_data = {
        'siada.tools.coder.file_search': [
            'bin/*',
            'README.md',
        ]
    }
    
    return package_data


def ensure_binary_permissions():
    """
    Ensure all binary files have correct execution permissions.
    Call this function before packaging.
    """
    bin_dir = Path(__file__).parent / "bin"
    
    if not bin_dir.exists():
        print(f"Warning: bin directory does not exist: {bin_dir}")
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
                current_mode = binary_path.stat().st_mode
                new_mode = current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                os.chmod(binary_path, new_mode)
                print(f"✓ Set execution permissions: {binary_path}")
            except (OSError, PermissionError) as e:
                print(f"✗ Failed to set permissions for {binary_path}: {e}")
        else:
            print(f"⚠ Binary file not found: {binary_path}")


def get_pyproject_toml_config():
    """
    Returns configuration snippet for pyproject.toml.
    """
    config = '''
[tool.setuptools.package-data]
"siada.tools.coder.file_search" = ["bin/*", "README.md"]

[tool.setuptools.packages.find]
where = ["siada"]
include = ["siada.tools.coder.file_search*"]
'''
    return config


def get_setup_py_config():
    """
    Returns configuration snippet for setup.py.
    """
    config = '''
package_data={
    'siada.tools.coder.file_search': [
        'bin/*',
        'README.md',
    ],
},
include_package_data=True,
'''
    return config


def validate_package_structure():
    """
    Validate package structure is correct.
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
    
    print("Validating package structure...")
    
    for file_name in required_files:
        file_path = base_dir / file_name
        if file_path.exists():
            print(f"✓ {file_name}")
        else:
            print(f"✗ Missing file: {file_name}")
    
    for dir_name in required_dirs:
        dir_path = base_dir / dir_name
        if dir_path.exists() and dir_path.is_dir():
            print(f"✓ {dir_name}/")
            if dir_name == "bin":
                bin_files = list(dir_path.glob("*"))
                if bin_files:
                    print(f"  Contains {len(bin_files)} binary files")
                    for bin_file in bin_files:
                        if bin_file.is_file():
                            print(f"    - {bin_file.name}")
                else:
                    print(f"  ⚠ bin directory is empty")
        else:
            print(f"✗ Missing directory: {dir_name}/")


if __name__ == "__main__":
    print("File Search - Package Configuration Check")
    print("=" * 40)
    
    validate_package_structure()
    
    print("\n" + "=" * 40)
    
    ensure_binary_permissions()
    
    print("\n" + "=" * 40)
    print("Package configuration info:")
    print("\n1. pyproject.toml config:")
    print(get_pyproject_toml_config())
    
    print("\n2. setup.py config:")
    print(get_setup_py_config())
    
    print("\n3. Package data config:")
    print(setup_package_data())
