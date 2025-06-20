#!/bin/bash

# SiadaHub 安装脚本
# 用于本地安装构建的 wheel 包

set -e  # 遇到错误时退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 检查是否需要构建
check_build() {
    if [ ! -d "$PROJECT_DIR/dist" ] || [ -z "$(ls -A "$PROJECT_DIR/dist" 2>/dev/null)" ]; then
        log_warning "未找到构建文件，开始构建..."
        "$SCRIPT_DIR/build.sh"
    else
        log_info "发现已有构建文件"
    fi
}

# 查找最新的 wheel 文件
find_wheel() {
    local wheel_file
    wheel_file=$(find "$PROJECT_DIR/dist" -name "*.whl" -type f | head -n 1)
    
    if [ -z "$wheel_file" ]; then
        log_error "未找到 wheel 文件"
        exit 1
    fi
    
    echo "$wheel_file"
}

# 检查 Python 和 pip
check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装"
        exit 1
    fi
    
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3 未安装"
        exit 1
    fi
    
    log_info "Python 版本: $(python3 --version)"
    log_info "pip 版本: $(pip3 --version)"
}

# 卸载旧版本
uninstall_old() {
    log_info "检查是否已安装旧版本..."
    
    if pip3 show siada-api &> /dev/null; then
        log_warning "发现已安装的版本，正在卸载..."
        pip3 uninstall siada-api -y
        log_success "旧版本卸载完成"
    else
        log_info "未发现已安装的版本"
    fi
}

# 安装 wheel 包
install_wheel() {
    local wheel_file="$1"
    
    log_info "安装 wheel 包: $(basename "$wheel_file")"
    
    # 使用 pip 安装
    pip3 install "$wheel_file" --force-reinstall
    
    if [ $? -eq 0 ]; then
        log_success "安装成功"
    else
        log_error "安装失败"
        exit 1
    fi
}

# 验证安装
verify_installation() {
    log_info "验证安装..."
    
    # 检查命令是否可用
    if command -v siadahub &> /dev/null; then
        log_success "siadahub 命令已可用"
        
        # 显示帮助信息
        echo ""
        log_info "命令帮助信息:"
        siadahub --help
        
    else
        log_error "siadahub 命令不可用"
        log_warning "可能需要重新加载 shell 或检查 PATH 环境变量"
        exit 1
    fi
}

# 显示使用说明
show_usage() {
    echo ""
    echo "========================================"
    echo "           使用说明"
    echo "========================================"
    echo ""
    echo "基本用法:"
    echo "  siadahub --help                    # 显示帮助"
    echo "  siadahub bugfix \"修复某个问题\"     # 使用 bugfix agent"
    echo ""
    echo "示例:"
    echo "  siadahub bugfix \"完成一个需求\""
    echo ""
}

# 主函数
main() {
    echo "========================================"
    echo "       SiadaHub 安装脚本"
    echo "========================================"
    echo ""
    
    # 切换到项目目录
    cd "$PROJECT_DIR"
    
    check_python
    check_build
    
    local wheel_file
    wheel_file=$(find_wheel)
    
    uninstall_old
    install_wheel "$wheel_file"
    verify_installation
    show_usage
    
    echo ""
    log_success "安装完成！"
}

# 执行主函数
main "$@"
