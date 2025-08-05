#!/bin/bash

# SiadaHub Installation Script
# For local installation of built wheel packages

set -e  # Exit on error

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

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Check if build is needed
check_build() {
    if [ ! -d "$PROJECT_DIR/dist" ] || [ -z "$(ls -A "$PROJECT_DIR/dist" 2>/dev/null)" ]; then
        log_warning "Build files not found, starting build..."
        "$SCRIPT_DIR/build.sh"
    else
        log_info "Found existing build files"
    fi
}

# Find the latest wheel file
find_wheel() {
    local wheel_file
    wheel_file=$(find "$PROJECT_DIR/dist" -name "*.whl" -type f | head -n 1)
    
    if [ -z "$wheel_file" ]; then
        log_error "Wheel file not found"
        exit 1
    fi
    
    echo "$wheel_file"
}

# Check Python and pip
check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 is not installed"
        exit 1
    fi
    
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3 is not installed"
        exit 1
    fi
    
    log_info "Python version: $(python3 --version)"
    log_info "pip version: $(pip3 --version)"
}

# Uninstall old version
uninstall_old() {
    log_info "Checking for previously installed version..."
    
    if pip3 show siada-agenthub &> /dev/null; then
        log_warning "Found installed version, uninstalling..."
        pip3 uninstall siada-agenthub -y
        log_success "Old version uninstalled"
    else
        log_info "No previously installed version found"
    fi
}

# Install wheel package
install_wheel() {
    local wheel_file="$1"
    
    log_info "Installing wheel package: $(basename "$wheel_file")"
    
    # Use pip to install
    pip3 install "$wheel_file" --force-reinstall
    
    if [ $? -eq 0 ]; then
        log_success "Installation successful"
    else
        log_error "Installation failed"
        exit 1
    fi
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."
    
    # Check if command is available
    if command -v siada-cli &> /dev/null; then
        log_success "siadahub-cli command is available"
        
        # Show help information
        echo ""
        log_info "Command help information:"
        siadahub-cli --help
        
    else
        log_error "siadahub-cli command is not available"
        log_warning "You may need to reload shell or check PATH environment variable"
        exit 1
    fi
}

# Show usage instructions
show_usage() {
    echo ""
    echo "========================================"
    echo "           Usage Instructions"
    echo "========================================"
    echo ""
    echo "Basic usage:"
    echo "  siadahub-cli --help                    # Show help"
    echo "  siadahub-cli bugfix \"Fix some issue\"  # Use bugfix agent"
    echo ""
    echo "Examples:"
    echo "  siadahub-cli bugfix \"Complete a requirement\""
    echo ""
}

# Main function
main() {
    echo "========================================"
    echo "       SiadaHub Installation Script"
    echo "========================================"
    echo ""
    
    # Switch to project directory
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
    log_success "Installation completed!"
}

# Execute main function
main "$@"
