import os
import subprocess
import json
import sys
import time
import socket
import signal
import threading
import http.server
import socketserver
import urllib.request
from pathlib import Path
from typing import Optional


class CardCompiler:
    """卡片编译器类"""

    def __init__(self):
        self.mindui_path = None
        self.card_name = None

    def compile_card(self, file_path: str):
        """
        编译卡片并返回本地服务地址
        
        Args:
            file_path: 卡片文件路径
        """
        try:
            # 1. 初始化编译环境
            self._initialize(file_path)

            # 2. 检查并安装 Node.js 和 npm
            self._check_and_install_node_npm()

            # 3. 安装依赖
            self._install_dependencies()

            # 4. 执行构建
            self._build_card()

            print(f"🎉 编译完成！")

        except Exception as e:
            print(f"❌ 编译失败: {str(e)}")
            raise

    def _initialize(self, file_path: str) -> None:
        """初始化编译环境"""
        # 获取卡片名称
        self.card_name = Path(file_path).stem
        print(f"🎯 开始编译卡片: {self.card_name}")

        def find_mindui_dir(start_path):
            """
            从给定的路径开始向上递归查找，直到找到名为'mindui'的目录

            :param start_path: 起始路径(可以是文件或目录路径)
            :return: 找到的mindui目录Path对象，如果没找到则返回None
            """
            current_path = Path(start_path).resolve()  # 转换为绝对路径

            # 如果是文件路径，从父目录开始查找
            if current_path.is_file():
                current_path = current_path.parent

            # 向上查找
            while True:
                # 检查当前目录名是否为'mindui'
                if current_path.name == 'mindui':
                    return current_path

                # 如果已经到达根目录，停止查找
                if current_path.parent == current_path:
                    return None

                # 向上移动一级目录
                current_path = current_path.parent

        self.mindui_path = find_mindui_dir(file_path)
        if not self.mindui_path.exists() or not self.mindui_path:
            raise Exception(f"❌ mindui 项目路径不存在: {self.mindui_path}")

        print(f"📁 mindui 项目路径: {self.mindui_path}")

    def _check_and_install_node_npm(self) -> None:
        """检查并安装 Node.js 和 npm"""
        print("🔍 检查 Node.js 和 npm 版本...")

        # 检查 Node.js 版本
        self._check_node_version()

        # 检查 npm 版本
        self._check_npm_version()

    def _check_node_version(self) -> None:
        """检查 Node.js 版本"""
        try:
            result = subprocess.run(['node', '--version'], capture_output=True, text=True, check=True)
            node_version = result.stdout.strip()
            print(f"✅ Node.js 版本: {node_version}")

            # 检查版本是否满足要求（需要 16+）
            major_version = int(node_version[1:].split('.')[0])
            if major_version < 16:
                raise Exception(f"❌ Node.js 版本过低，需要 16+，当前版本: {node_version}")

        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ Node.js 未安装，请先安装 Node.js 16+ 版本")
            raise Exception("Node.js 未安装或版本不符合要求")

    def _check_npm_version(self) -> None:
        """检查 npm 版本"""
        try:
            result = subprocess.run(['npm', '--version'], capture_output=True, text=True, check=True)
            npm_version = result.stdout.strip()
            print(f"✅ npm 版本: {npm_version}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ npm 未安装，请先安装 npm")
            raise Exception("npm 未安装")

    def _install_dependencies(self) -> None:
        """安装项目依赖"""
        print("📦 安装项目依赖...")

        # 检查 node_modules 是否存在
        node_modules_path = self.mindui_path / "node_modules"
        package_lock_path = self.mindui_path / "package-lock.json"

        if node_modules_path.exists() and package_lock_path.exists():
            print("✅ 依赖已存在，跳过安装")
            return

        try:
            # 切换到 mindui 目录并安装依赖
            result = subprocess.run(
                ['npm', 'install'],
                cwd=self.mindui_path,
                capture_output=True,
                text=True,
                check=True
            )
            print("✅ 依赖安装完成")
        except subprocess.CalledProcessError as e:
            print(f"❌ 依赖安装失败: {e.stderr}")
            raise Exception(f"npm install 失败: {e.stderr}")

    def _build_card(self) -> None:
        """构建卡片"""
        print(f"🔨 构建卡片: {self.card_name}")

        try:
            # 执行构建命令
            result = subprocess.run(
                ['node', 'scripts/build.js', self.card_name],
                cwd=self.mindui_path,
                capture_output=True,
                text=True,
                check=True
            )
            print("✅ 卡片构建完成")

            # 检查构建结果
            dist_path = self.mindui_path / "dist" / self.card_name / "index.html"
            if not dist_path.exists():
                raise Exception(f"❌ 构建产物不存在: {dist_path}")

        except subprocess.CalledProcessError as e:
            print(f"❌ 卡片构建失败: {e.stderr}")
            raise Exception(f"构建失败: {e.stderr}")



if __name__ == "__main__":
    file_path = "/Users/youzijun/siada/siada-agenthub/tests/tools/cca/resource/ccatest/mindui/src/cards/GreetingCard.tsx"
    compiler = CardCompiler()
    compiler.compile_card(file_path)

