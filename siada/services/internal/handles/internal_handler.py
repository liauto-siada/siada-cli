import sys
from typing import Tuple, Optional
from ...version_checker.base import VersionHandler as BaseVersionHandler


class VersionHandler(BaseVersionHandler):
    """
    Internal version handler
    Handles both version checking and installation for internal versions
    """
    
    def __init__(self):
        self.install_script_url = "https://bj.bcebos.com/prod-cnhb01-siada/cli-install/prod/remote_install.sh"
        self.install_cmd = "curl -s https://bj.bcebos.com/prod-cnhb01-siada/cli-install/prod/remote_install.sh | sh"
        self.timeout = 5
    
    def get_version(self) -> Tuple[Optional[str], str]:
        """Get version from install script by extracting wheel filename"""
        try:
            import requests
            import re
            
            response = requests.get(self.install_script_url, timeout=self.timeout)
            
            if response.status_code == 200:
                script_content = response.text
                # Extract version from wheel filename pattern: siada_cli-X.Y.Z-py3-none-any.whl
                version_pattern = r'siada_cli-(\d+\.\d+\.\d+)-py3-none-any\.whl'
                match = re.search(version_pattern, script_content)
                
                if match:
                    version = match.group(1)
                    return version, "success"
        except Exception:
            pass
        
        return None, "error"
    
    def get_install_message(self, latest_version: Optional[str] = None) -> str:
        """Get installation prompt message"""
        if latest_version:
            return f"Newer version v{latest_version} is available."
        else:
            return "New version available."
    
    def install(self, io, latest_version: Optional[str] = None) -> bool:
        """Install version using install script"""
        message = self.get_install_message(latest_version)
        io.print_warning(message)
        
        if not io.confirm_ask("Run install script?", default="y", subject=self.install_cmd):
            return False
        
        success, output = self.run_command_with_spinner(
            self.install_cmd, 
            "Running install script", 
            shell=True
        )
        
        if success:
            io.print_info("Re-run siada-cli to use new version.")
            sys.exit()
            return True
        else:
            io.print_error(output)
            print()
            print("Install failed, try running this command manually:")
            print(self.install_cmd)
            return False
