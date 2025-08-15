#!/bin/bash

# SiadaHub Build Script
# For building cross-platform wheel packages

# set -e  # Exit on error - commented out for better debugging

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
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

# Check if Poetry is installed
check_poetry() {
    if ! command -v poetry &> /dev/null; then
        log_error "Poetry is not installed, please install Poetry first"
        log_info "Install command: curl -sSL https://install.python-poetry.org | python3 -"
        return 1
    fi
    log_info "Poetry version: $(poetry --version)"
    return 0
}

# Clean build files
clean_build() {
    log_info "Cleaning previous build files..."
    
    # Clean Poetry build artifacts
    if [ -d "dist" ]; then
        rm -rf dist
        log_info "Deleted dist/ directory"
    fi
    
    if [ -d "build" ]; then
        rm -rf build
        log_info "Deleted build/ directory"
    fi
    
    # Clean egg-info directories
    find . -name "*.egg-info" -type d -exec rm -rf {} + 2>/dev/null || true
    
    # Clean Python cache
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true
    
    log_success "Build file cleanup completed"
}

# Validate project configuration
validate_project() {
    log_info "Validating project configuration..."
    
    if [ ! -f "pyproject.toml" ]; then
        log_error "pyproject.toml file not found"
        return 1
    fi
    
    if [ ! -d "siada" ]; then
        log_error "siada package directory not found"
        return 1
    fi
    
    if [ ! -f "siada/entrypoint/cli.py" ] && [ ! -f "siada/entrypoint/siadahub.py" ]; then
        log_error "CLI entry file not found"
        return 1
    fi
    
    log_success "Project configuration validation passed"
    return 0
}

# Build wheel package
build_wheel() {
    log_info "Starting wheel package build..."
    
    # Use Poetry to build
    log_info "Executing command: poetry build"
    if poetry build; then
        log_success "Wheel package build successful"
        return 0
    else
        log_error "Wheel package build failed, exit code: $?"
        log_error "Please check Poetry configuration and dependencies"
        return 1
    fi
}

# Show build results
show_build_results() {
    log_info "Build results:"
    
    if [ -d "dist" ]; then
        echo ""
        echo "Generated files:"
        ls -la dist/
        echo ""
        
        # Show wheel file information
        for wheel in dist/*.whl; do
            if [ -f "$wheel" ]; then
                log_info "Wheel file: $(basename "$wheel")"
                log_info "File size: $(du -h "$wheel" | cut -f1)"
            fi
        done
    else
        log_warning "dist directory not found"
    fi
}

# Main function
main() {
    echo "========================================"
    echo "       SiadaHub Build Script"
    echo "========================================"
    echo ""
    
    # Execute step by step, show detailed info on error but don't exit shell
    if ! check_poetry; then
        log_error "Poetry check failed"
        return 1
    fi
    
    if ! validate_project; then
        log_error "Project validation failed"
        return 1
    fi
    
    if ! clean_build; then
        log_error "Build file cleanup failed"
        return 1
    fi
    
    if ! build_wheel; then
        log_error "Wheel package build failed"
        return 1
    fi
    
    show_build_results
    
    echo ""
    log_success "Build completed!"
    log_info "Use 'scripts/install.sh' to install the built package"
    return 0
}

# Execute main function
main "$@"
