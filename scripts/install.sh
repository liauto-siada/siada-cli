#!/bin/bash

# SiadaHub Installation Script
# For local installation of built wheel packages

# Remove set -e to handle errors manually
# set -e  # Exit on error

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

# Error handling function
handle_error() {
    local exit_code=$1
    local error_msg="$2"
    local suggestion="$3"
    
    log_error "$error_msg"
    if [ -n "$suggestion" ]; then
        echo -e "${YELLOW}[SUGGESTION]${NC} $suggestion"
    fi
    echo -e "${RED}[FAILED]${NC} Installation failed with exit code: $exit_code"
    echo "Please check the error messages above and try again."
    return $exit_code
}

# Get script directory  
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Get project directory (parent of scripts directory, which should be siada-agenthub)
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Debug: Print paths
echo "DEBUG: SCRIPT_DIR = $SCRIPT_DIR"
echo "DEBUG: PROJECT_DIR = $PROJECT_DIR"
echo "DEBUG: Current working directory = $(pwd)"
echo "DEBUG: PROJECT_DIR basename = $(basename "$PROJECT_DIR")"

# Check if build is needed
check_build() {
    # Check if we have wheel files in the current directory dist
    if [ -d "./dist" ] && [ -n "$(ls -A ./dist/*.whl 2>/dev/null)" ]; then
        log_info "Found existing build files in current directory"
        return 0
    fi
    
    # Check if we have wheel files in PROJECT_DIR/dist  
    if [ -d "$PROJECT_DIR/dist" ] && [ -n "$(ls -A "$PROJECT_DIR/dist"/*.whl 2>/dev/null)" ]; then
        log_info "Found existing build files in PROJECT_DIR"
        return 0
    fi
    
    log_warning "Build files not found, starting build..."
    # Change to script directory first
    local current_dir=$(pwd)
    cd "$SCRIPT_DIR" || {
        handle_error 1 "Failed to change to scripts directory" "Check directory permissions"
        return 1
    }
    
    if bash build.sh; then
        log_success "Build completed successfully"
        cd "$current_dir"
        return 0
    else
        local exit_code=$?
        cd "$current_dir"
        handle_error $exit_code "Build failed" "Make sure you have poetry installed and project dependencies are correct"
        return 1
    fi
}

# Find the latest wheel file
find_wheel() {
    local wheel_file
    
    # First try to find in current directory
    wheel_file=$(find "./dist" -name "*.whl" -type f 2>/dev/null | head -n 1)
    
    # If not found, try PROJECT_DIR
    if [ -z "$wheel_file" ]; then
        wheel_file=$(find "$PROJECT_DIR/dist" -name "*.whl" -type f 2>/dev/null | head -n 1)
    fi
    
    if [ -z "$wheel_file" ]; then
        handle_error 1 "Wheel file not found in ./dist or $PROJECT_DIR/dist" "Run build.sh first to create wheel packages"
        return 1
    fi
    
    echo "$wheel_file"
    return 0
}

# Check Python and pip
check_python() {
    if ! command -v python3 &> /dev/null; then
        handle_error 1 "Python3 is not installed" "Please install Python3 first or make sure it's in your PATH"
        return 1
    fi
    
    if ! command -v pip3 &> /dev/null; then
        handle_error 1 "pip3 is not installed" "Please install pip3 first or make sure it's in your PATH"
        return 1
    fi
    
    log_info "Python version: $(python3 --version 2>&1)"
    log_info "pip version: $(pip3 --version 2>&1)"
    return 0
}

# Uninstall old version
uninstall_old() {
    log_info "Checking for previously installed version..."
    
    if pip3 show siada-agenthub &> /dev/null; then
        log_warning "Found installed version, uninstalling..."
        if pip3 uninstall siada-agenthub -y; then
            log_success "Old version uninstalled"
            return 0
        else
            handle_error $? "Failed to uninstall old version" "You may need to run with sudo or check permissions"
            return 1
        fi
    else
        log_info "No previously installed version found"
        return 0
    fi
}

# Install wheel package
install_wheel() {
    local wheel_file="$1"
    
    log_info "Installing wheel package: $(basename "$wheel_file")"
    
    # Use pip to install
    if pip3 install "$wheel_file" --force-reinstall; then
        log_success "Installation successful"
        return 0
    else
        local exit_code=$?
        handle_error $exit_code "Installation failed" "Check if you have write permissions or try with sudo. Also verify the wheel file is not corrupted."
        return $exit_code
    fi
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."
    
    # Check if command is available
    if command -v siada-cli &> /dev/null; then
        log_success "siada-cli command is available"
        
        # Show help information
        echo ""
        log_info "Command help information:"
        if siada-cli --help; then
            return 0
        else
            handle_error $? "Failed to run siada-cli --help" "The command is installed but may not be working properly"
            return 1
        fi
    else
        handle_error 1 "siada-cli command is not available" "You may need to reload shell, check PATH environment variable, or install failed"
        return 1
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
    echo "  siada-cli --help                    # Show help"
    echo "  siada-cli bugfix \"Fix some issue\"  # Use bugfix agent"
    echo ""
    echo "Examples:"
    echo "  siada-cli bugfix \"Complete a requirement\""
    echo ""
}

# Main function
main() {
    echo "========================================"
    echo "       SiadaHub Installation Script"
    echo "========================================"
    echo ""
    
    # Note: We don't change the working directory to preserve user's location
    # Instead, we use absolute paths when needed
    
    # Check each step and handle errors gracefully
    if ! check_python; then
        return 1
    fi
    
    if ! check_build; then
        handle_error 1 "Failed to check/build project" "Make sure you have proper build tools installed"
        return 1
    fi
    
    local wheel_file
    if ! wheel_file=$(find_wheel); then
        # Error already handled in find_wheel function
        return 1
    fi
    
    if ! uninstall_old; then
        log_warning "Failed to uninstall old version, continuing anyway..."
    fi
    
    if ! install_wheel "$wheel_file"; then
        return 1
    fi
    
    if ! verify_installation; then
        log_warning "Installation verification failed, but package may still be installed"
        return 1
    fi
    
    show_usage
    
    echo ""
    log_success "Installation completed successfully!"
    return 0
}

# Execute main function
main "$@"
