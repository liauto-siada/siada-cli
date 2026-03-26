import subprocess
from pathlib import Path

from agents import function_tool, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.observation.observation import FunctionCallResult

COMIPLE_CARD_DOCS = """Compile Card Tool

Given a absolute path, this tool can execute the compilation of a card, which is a web application.

Args:
    path: (required) The path of the card.
"""

@function_tool(
    name_override="compile_card", description_override="Compile the card from its path"
)
async def compile_card(
    context: RunContextWrapper[CodeAgentContext],
    path: str,
) -> FunctionCallResult:
    print("compile card: " + path)
    card_compiler = CardCompiler()
    result = card_compiler.compile_card(path)
    return FunctionCallResult(result)



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
            # 1. Initialize compilation environment
            self._initialize(file_path)

            # 2. Check and install Node.js and npm
            self._check_and_install_node_npm()

            # 3. Install dependencies
            self._install_dependencies()

            # 4. Execute build
            self._build_card()

            return f"✅ 编译成功"

        except Exception as e:
            return f"❌ 编译失败，报错情况: {str(e)}"

    def _initialize(self, file_path: str) -> None:
        """初始化编译环境"""
        # Get card name
        self.card_name = Path(file_path).stem
        print(f"🎯 开始编译卡片: {self.card_name}")

        def find_mindui_dir(start_path):
            """
            从给定的路径开始向上递归查找，直到找到名为'mindui'的目录

            :param start_path: 起始路径(可以是文件或目录路径)
            :return: 找到的mindui目录Path对象，如果没找到则返回None
            """
            current_path = Path(start_path).resolve()  # Convert to absolute path

            # If it is a file path, start searching from the parent directory
            if current_path.is_file():
                current_path = current_path.parent

            # Search upward
            while True:
                # Check if current directory name is 'mindui'
                if current_path.name == 'mindui-components':
                    return current_path

                # Stop searching if we have reached the root directory
                if current_path.parent == current_path:
                    return None

                # Move up one directory level
                current_path = current_path.parent

        self.mindui_path = find_mindui_dir(file_path)
        if not self.mindui_path.exists() or not self.mindui_path:
            raise Exception(f"❌ mindui 项目路径不存在: {self.mindui_path}")

        print(f"📁 mindui 项目路径: {self.mindui_path}")

    def _check_and_install_node_npm(self) -> None:
        """检查并安装 Node.js 和 npm"""
        print("🔍 检查 Node.js 和 npm 版本...")

        # Check Node.js version
        self._check_node_version()

        # Check npm version
        self._check_npm_version()

    def _check_node_version(self) -> None:
        """检查 Node.js 版本"""
        try:
            result = subprocess.run(['node', '--version'], capture_output=True, text=True, check=True)
            node_version = result.stdout.strip()
            print(f"✅ Node.js 版本: {node_version}")

            # Check if version meets requirements (requires 16+)
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

        # Check if node_modules exists
        node_modules_path = self.mindui_path / "node_modules"
        package_lock_path = self.mindui_path / "package-lock.json"

        if node_modules_path.exists() and package_lock_path.exists():
            print("✅ 依赖已存在，跳过安装")
            return

        try:
            # Switch to mindui directory and install dependencies
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
            # Execute build command
            result = subprocess.run(
                ['node', 'scripts/build.js', self.card_name],
                cwd=self.mindui_path,
                capture_output=True,
                text=True,
                check=True
            )
            print("✅ 卡片构建完成")

            # Check build result
            dist_path = self.mindui_path / "dist" / self.card_name / "index.html"
            if not dist_path.exists():
                raise Exception(f"❌ 构建产物不存在: {dist_path}")

        except subprocess.CalledProcessError as e:
            print(f"❌ 卡片构建失败: {e.stderr}")
            raise Exception(f"构建失败: {e.stderr}")



if __name__ == "__main__":
    file_path = "/Users/youzijun/siada/siada-agenthub/.cca/mindui/src/cards/HoroscopeCard.tsx"
    compiler = CardCompiler()
    compiler.compile_card(file_path)

