
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _find_project_root() -> Path:
    """
    Find the project root directory by looking for common project markers.
    
    Returns:
        Path to the project root directory
    """
    current_path = Path(__file__).resolve()
    
    # Look for project root markers
    root_markers = [
        'pyproject.toml',
        'poetry.lock', 
        '.git',
        'README.md',
        'agent_config.yaml'
    ]
    
    # Start from current file directory and go up
    for parent in [current_path.parent] + list(current_path.parents):
        for marker in root_markers:
            if (parent / marker).exists():
                print(f"Found project root at: {parent}")
                return parent
    
    # Fallback to current working directory
    print("Warning: Could not find project root, using current working directory")
    return Path.cwd()


def get_cca_resource():
    """
    Get all CCA resources from a Java GitLab repository.
    
    This function clones the cockpit-create-agent repository and copies
    the cca_agent resources to the project's .cca directory.
    """
    # Configuration
    repo_url = "https://gitlab.chehejia.com/ai-system/cockpit-create-agent.git"
    branch = "develop"
    project_root = _find_project_root()
    
    # Create temporary directory
    temp_dir = tempfile.mkdtemp(prefix="cca_temp_")
    temp_path = Path(temp_dir)
    
    try:
        # Step 1: Clone repository
        _clone_repository(repo_url, branch, temp_path)
        
        # Step 2: Copy CCA resources
        _copy_cca_resources(temp_path, project_root)
        
        print("CCA resource retrieval completed successfully")
        
    except Exception as e:
        print(f"Failed to get CCA resources: {e}")
        raise
    finally:
        # Step 3: Clean up temporary directory
        _cleanup_temp_directory(temp_dir)


def _clone_repository(repo_url: str, branch: str, temp_path: Path) -> None:
    """Clone the repository to temporary directory."""
    print(f"Cloning repository to: {temp_path}")
    
    clone_command = [
        "git", "clone",
        "--branch", branch,
        "--single-branch",
        "--depth", "1",
        repo_url,
        str(temp_path)
    ]
    
    try:
        subprocess.run(clone_command, capture_output=True, text=True, check=True)
        print("Repository cloned successfully")
    except subprocess.CalledProcessError as e:
        print(f"Git clone failed: {e}")
        print(f"Error output: {e.stderr}")
        raise


def _copy_cca_resources(temp_path: Path, project_root: Path) -> None:
    """Copy CCA agent resources from cloned repo to project .cca directory."""
    source_path_api = temp_path / "agent" / "app" / "src" / "main" / "resources" / "cca_agent"
    source_path_mindui = temp_path / "agent" / "app" / "src" / "main" / "resources" / "mindui-components"
    target_path_api = project_root / ".cca" / "api"
    target_path_mindui = project_root / ".cca" / "mindui"
    
    # Validate source exists
    if not source_path_api.exists():
        raise FileNotFoundError(f"Source directory not found: {source_path_api}")
    if not source_path_mindui.exists():
        raise FileNotFoundError(f"Source directory not found: {source_path_mindui}")
    
    # Remove existing target if present
    if target_path_api.exists():
        shutil.rmtree(target_path_api)
        print("Removed existing .cca api directory")

    if target_path_mindui.exists():
        shutil.rmtree(target_path_mindui)
        print("Removed existing .cca mindui directory")
    
    # Copy resources
    shutil.copytree(source_path_api, target_path_api)
    shutil.copytree(source_path_mindui, target_path_mindui)
    print(f"Successfully copied CCA resources to: {target_path_api}")
    print(f"Successfully copied CCA resources to: {target_path_mindui}")


def _cleanup_temp_directory(temp_dir: str) -> None:
    """Clean up the temporary directory."""
    try:
        shutil.rmtree(temp_dir)
        print(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        print(f"Warning: Failed to clean up temporary directory: {e}")


def main():
    """Main function for testing the CCA resource retrieval."""
    print("Starting CCA resource retrieval test...")
    print("=" * 50)
    
    try:
        get_cca_resource()
        print("=" * 50)
        print("Test completed successfully!")
        
        # Check if .cca directory was created in project root
        project_root = _find_project_root()
        cca_path = project_root / ".cca"
        if cca_path.exists():
            print(f"✅ .cca directory created at: {cca_path}")
            
            # List contents of .cca directory
            contents = list(cca_path.iterdir())
            if contents:
                print(f"📁 Contents ({len(contents)} items):")
                for item in contents[:10]:  # Show first 10 items
                    item_type = "📁" if item.is_dir() else "📄"
                    print(f"   {item_type} {item.name}")
                if len(contents) > 10:
                    print(f"   ... and {len(contents) - 10} more items")
            else:
                print("⚠️  .cca directory is empty")
        else:
            print("❌ .cca directory was not created")
            
    except Exception as e:
        print("=" * 50)
        print(f"❌ Test failed with error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
