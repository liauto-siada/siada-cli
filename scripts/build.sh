#!/bin/bash

# SiadaHub 构建脚本
# 用于构建跨平台的 wheel 包

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

# 检查 Poetry 是否安装
check_poetry() {
    if ! command -v poetry &> /dev/null; then
        log_error "Poetry 未安装，请先安装 Poetry"
        log_info "安装命令: curl -sSL https://install.python-poetry.org | python3 -"
        exit 1
    fi
    log_info "Poetry 版本: $(poetry --version)"
}

# 清理构建文件
clean_build() {
    log_info "清理之前的构建文件..."
    
    # 清理 Poetry 构建产物
    if [ -d "dist" ]; then
        rm -rf dist
        log_info "已删除 dist/ 目录"
    fi
    
    if [ -d "build" ]; then
        rm -rf build
        log_info "已删除 build/ 目录"
    fi
    
    # 清理 egg-info 目录
    find . -name "*.egg-info" -type d -exec rm -rf {} + 2>/dev/null || true
    
    # 清理 Python 缓存
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true
    
    log_success "构建文件清理完成"
}

# 验证项目配置
validate_project() {
    log_info "验证项目配置..."
    
    if [ ! -f "pyproject.toml" ]; then
        log_error "未找到 pyproject.toml 文件"
        exit 1
    fi
    
    if [ ! -d "siada" ]; then
        log_error "未找到 siada 包目录"
        exit 1
    fi
    
    if [ ! -f "siada/entrypoint/cli.py" ]; then
        log_error "未找到 CLI 入口文件"
        exit 1
    fi
    
    log_success "项目配置验证通过"
}

# 构建 wheel 包
build_wheel() {
    log_info "开始构建 wheel 包..."
    
    # 使用 Poetry 构建
    poetry build
    
    if [ $? -eq 0 ]; then
        log_success "Wheel 包构建成功"
    else
        log_error "Wheel 包构建失败"
        exit 1
    fi
}

# 显示构建结果
show_build_results() {
    log_info "构建结果:"
    
    if [ -d "dist" ]; then
        echo ""
        echo "生成的文件:"
        ls -la dist/
        echo ""
        
        # 显示 wheel 文件信息
        for wheel in dist/*.whl; do
            if [ -f "$wheel" ]; then
                log_info "Wheel 文件: $(basename "$wheel")"
                log_info "文件大小: $(du -h "$wheel" | cut -f1)"
            fi
        done
    else
        log_warning "未找到 dist 目录"
    fi
}

# 主函数
main() {
    echo "========================================"
    echo "       SiadaHub 构建脚本"
    echo "========================================"
    echo ""
    
    check_poetry
    validate_project
    clean_build
    build_wheel
    show_build_results
    
    echo ""
    log_success "构建完成！"
    log_info "使用 'scripts/install.sh' 来安装构建的包"
}

# 执行主函数
main "$@"
