"""
System Theme Detector

Detects the current terminal theme (background color) and system theme.
"""
import os
import platform
import subprocess
import sys
from typing import Literal, Optional

from siada.foundation.logging import logger
if not logger.handlers:
    from siada.foundation.logging import setup_logger
    logger = setup_logger()

ThemeMode = Literal['dark', 'light', 'unknown']


class SystemThemeDetector:
    """Detects terminal and system theme across different operating systems."""
    
    @staticmethod
    def detect_theme() -> ThemeMode:
        """
        Detect the current terminal theme by checking terminal background color.
        Falls back to system theme if terminal detection fails.
        
        Returns:
            'dark', 'light', or 'unknown' if detection fails
        """
        # First try to detect terminal background color
        logger.info("=== Starting theme detection ===")
        terminal_theme = SystemThemeDetector._detect_terminal_theme()
        if terminal_theme != 'unknown':
            return terminal_theme
        
        # Fall back to system theme detection
        return 'dark'
    
    @staticmethod
    def _detect_terminal_theme() -> ThemeMode:
        """
        Detect terminal background color using various methods.
        
        Returns:
            'dark', 'light', or 'unknown' if detection fails
        """
        
        # Method 2: Platform-specific terminal detection
        system = platform.system()
        
        # Linux: Check for GNOME Terminal
        if system == 'Linux':
            # gnome_theme = SystemThemeDetector._detect_gnome_terminal_theme()
            gnome_theme = SystemThemeDetector._detect_linux_theme()
            if gnome_theme != 'unknown':
                return gnome_theme
        
        # Windows: Only adapt Git Bash, other terminals default to dark
        if system == 'Windows':
            logger.info("=== Windows terminal detection ===")
            
            # Try Git Bash (MinTTY)
            logger.info("Checking for Git Bash (MinTTY)...")
            gitbash_theme = SystemThemeDetector._detect_gitbash_theme()
            if gitbash_theme != 'unknown':
                logger.info(f"✓ Git Bash theme detected: {gitbash_theme}")
                return gitbash_theme
            else:
                logger.info("Git Bash not detected, defaulting to 'dark' for other Windows terminals")
                return 'dark'
        
        # Method 3: Check terminal-specific environment variables
        term_program = os.environ.get('TERM_PROGRAM', '').lower()
        
        # macOS Terminal.app specific
        if system == 'Darwin' and term_program == 'apple_terminal':
            # terminal_app_theme = SystemThemeDetector._detect_terminal_app_theme()
            terminal_app_theme = SystemThemeDetector._detect_macos_theme()
            if terminal_app_theme != 'unknown':
                return terminal_app_theme
        
        # iTerm2 specific
        if 'iterm' in term_program:
            # Try to get iTerm2 background color using AppleScript
            iterm_theme = SystemThemeDetector._detect_iterm2_theme()
            # print(f"*****{iterm_theme}")
            if iterm_theme != 'unknown':
                return iterm_theme
            
            # Fallback: check ITERM_PROFILE environment variable
            iterm_profile = os.environ.get('ITERM_PROFILE', '').lower()
            if iterm_profile:
                if 'dark' in iterm_profile or 'solarized dark' in iterm_profile:
                    return 'dark'
                elif 'light' in iterm_profile or 'solarized light' in iterm_profile:
                    return 'light'
        
        # VS Code integrated terminal
        if 'vscode' in term_program or os.environ.get('TERM_PROGRAM_VERSION', ''):
            # VS Code sets VSCODE_GIT_IPC_HANDLE when running in integrated terminal
            if os.environ.get('VSCODE_GIT_IPC_HANDLE'):
                # Try to infer from color scheme (this is a heuristic)
                # Most VS Code dark themes have dark terminals
                return 'dark'  # Default assumption for VS Code
        
        # Method 3: Try OSC 11 query (works in xterm-compatible terminals)
        # This is more reliable but requires terminal interaction
        if sys.stdout.isatty():
            try:
                terminal_bg = SystemThemeDetector._query_terminal_background()
                if terminal_bg != 'unknown':
                    return terminal_bg
            except Exception:
                pass
        
        return 'unknown'
    
    @staticmethod
    def _detect_terminal_app_theme() -> ThemeMode:
        """
        Detect macOS Terminal.app background color using AppleScript.
        
        Returns:
            'dark', 'light', or 'unknown'
        """
        try:
            # AppleScript to get Terminal.app background color
            applescript = '''
            tell application "Terminal"
                get background color of current settings of selected tab of front window
            end tell
            '''
            
            result = subprocess.run(
                ['osascript', '-e', applescript],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                # Parse the RGB values from output
                # Format is typically: "R, G, B" where values are 0-65535
                output = result.stdout.strip()
                if output:
                    try:
                        # Split by comma and convert to integers
                        rgb_parts = [int(x.strip()) for x in output.split(',')]
                        if len(rgb_parts) >= 3:
                            # Convert from 0-65535 range to 0-255 range
                            r = rgb_parts[0] / 65535 * 255
                            g = rgb_parts[1] / 65535 * 255
                            b = rgb_parts[2] / 65535 * 255
                            
                            # Calculate perceived brightness
                            brightness = (0.299 * r + 0.587 * g + 0.114 * b)
                            
                            # Threshold: < 128 is dark, >= 128 is light
                            return 'dark' if brightness < 128 else 'light'
                    except (ValueError, IndexError) as e:
                        pass
            else:
                # Debug: print error if command failed
                pass
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            pass
        
        return 'unknown'
    
    @staticmethod
    def _detect_gnome_terminal_theme() -> ThemeMode:
        """
        Detect GNOME Terminal background color.
        
        Returns:
            'dark', 'light', or 'unknown'
        """
        # Check if running in GNOME Terminal
        if not (os.environ.get('GNOME_TERMINAL_SERVICE') or 
                os.environ.get('VTE_VERSION')):
            return 'unknown'
        
        try:
            # Get the default profile ID
            result = subprocess.run(
                ['gsettings', 'get', 'org.gnome.Terminal.ProfilesList', 'default'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                # Remove quotes from profile ID
                profile_id = result.stdout.strip().strip("'\"")
                
                if profile_id:
                    profile_path = f'org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{profile_id}/'
                    
                    # Check if using system theme colors
                    result = subprocess.run(
                        ['gsettings', 'get', profile_path, 'use-theme-colors'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    
                    if result.returncode == 0:
                        use_theme_colors = result.stdout.strip().lower()
                        # If using system theme colors, detect system theme instead
                        if use_theme_colors == 'true':
                            return SystemThemeDetector._detect_linux_theme()
                    
                    # Get background color for this profile
                    result = subprocess.run(
                        ['gsettings', 'get', profile_path, 'background-color'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    
                    if result.returncode == 0:
                        color_str = result.stdout.strip().strip("'\"")
                        
                        # Parse color string (format: 'rgb(r,g,b)' or '#RRGGBB')
                        if 'rgb' in color_str:
                            # Format: rgb(r,g,b) where values are 0-255
                            import re
                            match = re.search(r'rgb\((\d+),(\d+),(\d+)\)', color_str)
                            if match:
                                r, g, b = map(int, match.groups())
                                brightness = (0.299 * r + 0.587 * g + 0.114 * b)
                                return 'dark' if brightness < 128 else 'light'
                        elif color_str.startswith('#'):
                            # Format: #RRGGBB
                            if len(color_str) >= 7:
                                r = int(color_str[1:3], 16)
                                g = int(color_str[3:5], 16)
                                b = int(color_str[5:7], 16)
                                brightness = (0.299 * r + 0.587 * g + 0.114 * b)
                                return 'dark' if brightness < 128 else 'light'
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
        
        return 'unknown'
    
    @staticmethod
    def _detect_windows_terminal_theme() -> ThemeMode:
        """
        Detect Windows Terminal theme.
        
        Returns:
            'dark', 'light', or 'unknown'
        """
        # Check if running in Windows Terminal
        if not os.environ.get('WT_SESSION'):
            return 'unknown'
        
        try:
            import json
            from pathlib import Path
            
            # Windows Terminal settings location
            localappdata = os.environ.get('LOCALAPPDATA')
            if not localappdata:
                return 'unknown'
            
            settings_path = Path(localappdata) / 'Packages' / \
                           'Microsoft.WindowsTerminal_8wekyb3d8bbwe' / \
                           'LocalState' / 'settings.json'
            
            if settings_path.exists():
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    
                    # Check global theme setting
                    theme = settings.get('theme', '').lower()
                    if 'dark' in theme:
                        return 'dark'
                    elif 'light' in theme:
                        return 'light'
                    
                    # Check color scheme of current profile
                    current_profile_id = os.environ.get('WT_PROFILE_ID')
                    if current_profile_id:
                        profiles = settings.get('profiles', {}).get('list', [])
                        for profile in profiles:
                            if profile.get('guid') == current_profile_id:
                                color_scheme = profile.get('colorScheme', '').lower()
                                if 'dark' in color_scheme or 'campbell' in color_scheme:
                                    return 'dark'
                                elif 'light' in color_scheme or 'one half light' in color_scheme:
                                    return 'light'
                                break
                    
                    # Check default profile's color scheme
                    default_profile = settings.get('profiles', {}).get('defaults', {})
                    color_scheme = default_profile.get('colorScheme', '').lower()
                    if 'dark' in color_scheme:
                        return 'dark'
                    elif 'light' in color_scheme:
                        return 'light'
                    
        except (FileNotFoundError, json.JSONDecodeError, Exception):
            pass
        
        return 'unknown'
    
    def _detect_gitbash_theme() -> ThemeMode:
        """        
        MinTTY loads configuration with the following priority (high to low):
        1. Command line arguments (-o BackgroundColour=R,G,B) - Cannot detect from process
        2. User configuration file (~/.minttyrc or %USERPROFILE%\\.minttyrc)
        3. Theme file (if ThemeFile is specified in config)
        4. System global configuration (/etc/minttyrc or Git installation config)
        5. Hard-coded defaults (BackgroundColour=0,0,0 - black background)
        
        
        Returns:
            'dark', 'light', or 'unknown'
        """
        import re

        # === Step 1: Verify Git Bash / MinTTY environment ===
        msystem = os.environ.get('MSYSTEM', '')
        term = os.environ.get('TERM', '')
        is_likely_gitbash = False

        # Check for Git Bash indicators
        if msystem:  # MINGW64, MINGW32, MSYS, etc.
            is_likely_gitbash = True
            logger.info(f"✓ Detected Git Bash via MSYSTEM: {msystem}")

        if 'xterm' in term and platform.system() == 'Windows':
            is_likely_gitbash = True
            logger.info(f"✓ Detected Git Bash via TERM: {term}")

        if os.environ.get('MINTTY_SHORTCUT') or os.environ.get('EXEPATH'):
            is_likely_gitbash = True
            logger.info("✓ Detected Git Bash via MinTTY environment variables")

        if not is_likely_gitbash:
            logger.info("No Git Bash indicators found, skipping MinTTY detection")
            return 'unknown'

        logger.info("=== Starting MinTTY configuration cascade detection ===")

        # === Step 2: Helper function to parse RGB color and determine theme ===
        def rgb_to_theme(r: int, g: int, b: int) -> ThemeMode:
            """Calculate brightness and determine if theme is dark or light."""
            brightness = (0.299 * r + 0.587 * g + 0.114 * b)
            return 'dark' if brightness < 128 else 'light'

        def parse_background_color(content: str) -> Optional[tuple]:
            """Extract BackgroundColour from config content. Returns (r, g, b) or None."""
            match = re.search(r'^\s*BackgroundColour\s*=\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', 
                            content, re.MULTILINE)
            if match:
                return tuple(map(int, match.groups()))
            return None

        def parse_theme_file(content: str) -> Optional[str]:
            """Extract ThemeFile path from config content."""
            match = re.search(r'^\s*ThemeFile\s*=\s*(.+)$', content, re.MULTILINE)
            if match:
                return match.group(1).strip().strip('"\'')
            return None

        # === Step 3: Load user configuration (~/.minttyrc) - Priority 2 ===
        logger.info("→ Checking user configuration file...")
        home = os.path.expanduser('~')
        user_config_path = os.path.join(home, '.minttyrc')

        user_bg_color = None
        theme_file_path = None

        if os.path.exists(user_config_path):
            logger.info(f"  ✓ Found: {user_config_path}")
            try:
                with open(user_config_path, 'r', encoding='utf-8') as f:
                    user_config_content = f.read()

                    # Check for BackgroundColour
                    user_bg_color = parse_background_color(user_config_content)
                    if user_bg_color:
                        r, g, b = user_bg_color
                        theme = rgb_to_theme(r, g, b)
                        logger.info(f"  ✓ Found BackgroundColour={r},{g},{b} → theme: {theme}")
                        return theme

                    # Check for ThemeFile reference
                    theme_file_path = parse_theme_file(user_config_content)
                    if theme_file_path:
                        logger.info(f"  ✓ Found ThemeFile: {theme_file_path}")
                    else:
                        logger.info("  ⊘ No BackgroundColour or ThemeFile set in user config")

            except (IOError, OSError) as e:
                logger.warning(f"  ✗ Failed to read user config: {e}")
        else:
            logger.info(f"  ⊘ User config not found: {user_config_path}")

        # === Step 4: Load theme file (if specified) - Priority 3 ===
        if theme_file_path:
            logger.info(f"→ Checking theme file: {theme_file_path}")

            # Expand environment variables and resolve path
            theme_file_path = os.path.expandvars(os.path.expanduser(theme_file_path))

            # If relative path, try common theme directories
            if not os.path.isabs(theme_file_path):
                possible_paths = [
                    os.path.join(home, theme_file_path),
                    os.path.join(r'C:\Program Files\Git\usr\share\mintty\themes', theme_file_path),
                    os.path.join(r'C:\Program Files (x86)\Git\usr\share\mintty\themes', theme_file_path),
                ]

                for possible_path in possible_paths:
                    if os.path.exists(possible_path):
                        theme_file_path = possible_path
                        break

            if os.path.exists(theme_file_path):
                logger.info(f"  ✓ Theme file exists: {theme_file_path}")
                try:
                    with open(theme_file_path, 'r', encoding='utf-8') as f:
                        theme_content = f.read()
                        theme_bg_color = parse_background_color(theme_content)

                        if theme_bg_color:
                            r, g, b = theme_bg_color
                            theme = rgb_to_theme(r, g, b)
                            logger.info(f"  ✓ Theme file BackgroundColour={r},{g},{b} → theme: {theme}")
                            return theme
                        else:
                            logger.info("  ⊘ No BackgroundColour in theme file")

                except (IOError, OSError) as e:
                    logger.warning(f"  ✗ Failed to read theme file: {e}")
            else:
                logger.warning(f"  ✗ Theme file not found: {theme_file_path}")

        # === Step 5: Load system global configuration - Priority 4 ===
        logger.info("→ Checking system global configuration...")
        global_config_paths = []

        # Try to find Git installation path
        git_path = os.environ.get('EXEPATH')
        if git_path:
            git_etc_config = os.path.join(os.path.dirname(git_path), '..', 'etc', 'minttyrc')
            git_etc_config = os.path.normpath(git_etc_config)
            global_config_paths.append(git_etc_config)

        # Common Git installation paths
        global_config_paths.extend([
            r'C:\Program Files\Git\etc\minttyrc',
            r'C:\Program Files (x86)\Git\etc\minttyrc',
            '/etc/minttyrc',  # Unix-style path
        ])

        for global_path in global_config_paths:
            if os.path.exists(global_path):
                logger.info(f"  ✓ Found: {global_path}")
                try:
                    with open(global_path, 'r', encoding='utf-8') as f:
                        global_content = f.read()
                        global_bg_color = parse_background_color(global_content)

                        if global_bg_color:
                            r, g, b = global_bg_color
                            theme = rgb_to_theme(r, g, b)
                            logger.info(f"  ✓ Global BackgroundColour={r},{g},{b} → theme: {theme}")
                            return theme
                        else:
                            logger.info("  ⊘ No BackgroundColour in global config")

                except (IOError, OSError) as e:
                    logger.warning(f"  ✗ Failed to read global config: {e}")
                break
        else:
            logger.info("  ⊘ No global config found")

        # === Step 6: Use hard-coded default (0,0,0 - black background) - Priority 5 ===
        logger.info("→ Using MinTTY hard-coded default")
        logger.info("  ✓ Default BackgroundColour=0,0,0 (black) → theme: dark")
        return 'dark'
    
    @staticmethod
    def _detect_windows_console_theme() -> ThemeMode:
        """
        Detect Windows Console (CMD/PowerShell) theme by reading registry.
        
        Returns:
            'dark', 'light', or 'unknown'
        """
        try:
            import winreg
            
            # Try to open Console registry key
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r'Console',
                    0,
                    winreg.KEY_READ
                )
            except FileNotFoundError:
                return 'unknown'
            
            try:
                # Try to read ScreenColors (contains both foreground and background)
                # Format: 0xBF where B=background (high nibble), F=foreground (low nibble)
                screen_colors, _ = winreg.QueryValueEx(key, 'ScreenColors')
                
                # Extract background color (high nibble)
                bg_color = (screen_colors >> 4) & 0x0F
                
                # Windows console colors: 0=black, 7=light gray, 15=white
                # 0-6, 8 are dark colors, 7, 15 are light colors
                if bg_color in (0, 1, 2, 3, 4, 5, 6, 8):
                    winreg.CloseKey(key)
                    return 'dark'
                elif bg_color in (7, 15):
                    winreg.CloseKey(key)
                    return 'light'
                    
            except FileNotFoundError:
                # ScreenColors not found, try ColorTable00 (background color)
                try:
                    # ColorTable00 is the background color in COLORREF format (0x00BBGGRR)
                    color_table_00, _ = winreg.QueryValueEx(key, 'ColorTable00')
                    
                    # Extract RGB components
                    r = color_table_00 & 0xFF
                    g = (color_table_00 >> 8) & 0xFF
                    b = (color_table_00 >> 16) & 0xFF
                    
                    # Calculate brightness
                    brightness = (0.299 * r + 0.587 * g + 0.114 * b)
                    
                    winreg.CloseKey(key)
                    return 'dark' if brightness < 128 else 'light'
                    
                except FileNotFoundError:
                    pass
            
            winreg.CloseKey(key)
            
        except (ImportError, OSError, Exception):
            pass
        
        return 'unknown'
    
    @staticmethod
    def _detect_iterm2_theme() -> ThemeMode:
        """
        Detect iTerm2 background color using AppleScript.
        
        Returns:
            'dark', 'light', or 'unknown'
        """
        try:
            # AppleScript to get iTerm2 background color
            applescript = '''
            tell application "iTerm2"
                tell current session of current window
                    get background color
                end tell
            end tell
            '''
            
            result = subprocess.run(
                ['osascript', '-e', applescript],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                # Parse the RGB values from output
                # Format is typically: "R, G, B" where values are 0-65535
                output = result.stdout.strip()
                if output:
                    try:
                        # Split by comma and convert to integers
                        rgb_parts = [int(x.strip()) for x in output.split(',')]
                        if len(rgb_parts) >= 3:
                            # Convert from 0-65535 range to 0-255 range
                            r = rgb_parts[0] / 65535 * 255
                            g = rgb_parts[1] / 65535 * 255
                            b = rgb_parts[2] / 65535 * 255
                            
                            # Calculate perceived brightness
                            brightness = (0.299 * r + 0.587 * g + 0.114 * b)
                            
                            # Threshold: < 128 is dark, >= 128 is light
                            return 'dark' if brightness < 128 else 'light'
                    except (ValueError, IndexError):
                        pass
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
        
        return 'unknown'
    
    @staticmethod
    def _query_terminal_background() -> ThemeMode:
        """
        Query terminal background color using OSC 11 escape sequence.
        This works with xterm-compatible terminals.
        
        Returns:
            'dark', 'light', or 'unknown'
        """
        try:
            import termios
            import tty
            import select
            
            # Save terminal settings
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            
            try:
                # Set terminal to raw mode
                tty.setraw(fd)
                
                # Query background color using OSC 11
                sys.stdout.write('\033]11;?\033\\')
                sys.stdout.flush()
                
                # Wait for response with timeout
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    response = ''
                    while True:
                        if select.select([sys.stdin], [], [], 0.05)[0]:
                            char = sys.stdin.read(1)
                            response += char
                            # Response ends with ESC \ or BEL
                            if char == '\\' or char == '\a':
                                break
                        else:
                            break
                    
                    # Parse response: format is typically ESC]11;rgb:RRRR/GGGG/BBBB ESC\
                    if 'rgb:' in response:
                        # Extract RGB values
                        rgb_part = response.split('rgb:')[1].split('\\')[0].split('\a')[0]
                        rgb_values = rgb_part.split('/')
                        
                        if len(rgb_values) >= 3:
                            # Convert hex to int (take first 2 chars of each component)
                            r = int(rgb_values[0][:2], 16) if len(rgb_values[0]) >= 2 else 0
                            g = int(rgb_values[1][:2], 16) if len(rgb_values[1]) >= 2 else 0
                            b = int(rgb_values[2][:2], 16) if len(rgb_values[2]) >= 2 else 0
                            
                            # Calculate perceived brightness (using standard formula)
                            brightness = (0.299 * r + 0.587 * g + 0.114 * b)
                            
                            # Threshold: < 128 is dark, >= 128 is light
                            return 'dark' if brightness < 128 else 'light'
            finally:
                # Restore terminal settings
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                
        except (ImportError, OSError, Exception):
            pass
        
        return 'unknown'
    
    @staticmethod
    def _detect_system_theme() -> ThemeMode:
        """
        Detect the system theme (OS-level dark/light mode).
        
        Returns:
            'dark', 'light', or 'unknown' if detection fails
        """
        system = platform.system()
        
        if system == 'Darwin':  # macOS
            return SystemThemeDetector._detect_macos_theme()
        elif system == 'Windows':
            return SystemThemeDetector._detect_windows_theme()
        elif system == 'Linux':
            return SystemThemeDetector._detect_linux_theme()
        else:
            return 'unknown'
    
    @staticmethod
    def _detect_macos_theme() -> ThemeMode:
        """
        Detect theme on macOS.
        
        Strategy for Terminal.app:
        - Basic profile and user custom profiles: Follow system theme
        - Other built-in profiles: Follow terminal background color
        
        For other terminals: Fall back to system theme
        
        Returns:
            'dark', 'light', or 'unknown'
        """
        # Check if running in Terminal.app
        term_program = os.environ.get('TERM_PROGRAM', '').lower()
        if term_program == 'apple_terminal':
            # Check if the current profile follows system theme
            if SystemThemeDetector._terminal_app_follows_system_theme():
                # Basic and custom profiles: follow system theme
                logger.info("Terminal.app profile follows system theme, detecting system theme")
                try:
                    result = subprocess.run(
                        ['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0 and 'Dark' in result.stdout:
                        return 'dark'
                    else:
                        return 'light'
                except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                    return 'unknown'
            else:
                # Other built-in profiles: detect terminal background color
                logger.info("Terminal.app profile uses custom colors, detecting terminal background")
                terminal_bg_theme = SystemThemeDetector._detect_terminal_app_background()
                if terminal_bg_theme != 'unknown':
                    return terminal_bg_theme
        
        # Fall back to system theme detection for non-Terminal.app
        try:
            result = subprocess.run(
                ['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                capture_output=True,
                text=True,
                timeout=2
            )
            # If the command succeeds and returns 'Dark', it's dark mode
            if result.returncode == 0 and 'Dark' in result.stdout:
                return 'dark'
            else:
                # If the key doesn't exist or returns something else, it's light mode
                return 'light'
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return 'unknown'
    
    @staticmethod
    def _terminal_app_follows_system_theme() -> bool:
        """
        Check if Terminal.app is configured to follow system theme.
        
        Returns:
            True if Terminal.app follows system theme, False otherwise
        """
        try:
            # Get the current profile name
            applescript_profile = '''
            tell application "Terminal"
                get name of current settings of selected tab of front window
            end tell
            '''
            
            result = subprocess.run(
                ['osascript', '-e', applescript_profile],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                profile_name = result.stdout.strip()
                try:
                    system_profiles = [ 'Pro', 'Grass', 'Homebrew', 'Man Page', 
                                     'Novel', 'Ocean', 'Red Sands', 'Silver Aerogel']
                    
                    if profile_name not in system_profiles:
                        return True
                    return False
                    
                except Exception:
                    pass
                    
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
        
        # If we can't determine, assume it doesn't follow system theme
        # This way we'll detect the actual background color
        return False
    
    @staticmethod
    def _detect_terminal_app_background() -> ThemeMode:
        """
        Detect macOS Terminal.app background color using AppleScript.
        
        Returns:
            'dark', 'light', or 'unknown'
        """
        try:
            # AppleScript to get Terminal.app background color
            applescript = '''
            tell application "Terminal"
                get background color of current settings of selected tab of front window
            end tell
            '''
            
            result = subprocess.run(
                ['osascript', '-e', applescript],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                # Parse the RGB values from output
                # Format is typically: "R, G, B" where values are 0-65535
                output = result.stdout.strip()
                if output:
                    try:
                        # Split by comma and convert to integers
                        rgb_parts = [int(x.strip()) for x in output.split(',')]
                        if len(rgb_parts) >= 3:
                            # Convert from 0-65535 range to 0-255 range
                            r = rgb_parts[0] / 65535 * 255
                            g = rgb_parts[1] / 65535 * 255
                            b = rgb_parts[2] / 65535 * 255
                            
                            # Calculate perceived brightness
                            brightness = (0.299 * r + 0.587 * g + 0.114 * b)
                            
                            # Threshold: < 128 is dark, >= 128 is light
                            return 'dark' if brightness < 128 else 'light'
                    except (ValueError, IndexError):
                        pass
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
        
        return 'unknown'
    
    @staticmethod
    def _detect_windows_theme() -> ThemeMode:
        """Detect theme on Windows."""
        try:
            import winreg
            
            # Check Windows Registry for theme setting
            registry_path = r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path)
            
            try:
                # AppsUseLightTheme: 0 = dark, 1 = light
                value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
                winreg.CloseKey(key)
                
                return 'light' if value == 1 else 'dark'
            except FileNotFoundError:
                winreg.CloseKey(key)
                return 'unknown'
                
        except (ImportError, OSError, Exception):
            return 'unknown'
    
    @staticmethod
    def _detect_linux_theme() -> ThemeMode:
        """Detect theme on Linux with detailed logging."""
        logger.info("=== Starting Linux theme detection ===")
        
        try:
            # Step 1: Get default profile ID
            logger.info("Step 1: Getting default GNOME Terminal profile ID")
            profile_result = subprocess.run([
                'gsettings', 'get', 'org.gnome.Terminal.ProfilesList', 'default'
            ], capture_output=True, text=True, timeout=2)
            
            logger.info(f"Profile query returncode: {profile_result.returncode}")
            logger.info(f"Profile query stdout: {profile_result.stdout.strip()}")
            logger.info(f"Profile query stderr: {profile_result.stderr.strip()}")
            
            if profile_result.returncode == 0:
                profile_id = profile_result.stdout.strip().strip("'")
                logger.info(f"✓ Got profile ID: {profile_id}")
                
                # Step 2: Check if using theme colors
                logger.info("Step 2: Checking use-theme-colors setting")
                theme_color_result = subprocess.run([
                    'gsettings', 'get',
                    f'org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{profile_id}/',
                    'use-theme-colors'
                ], capture_output=True, text=True, timeout=2)
                
                logger.info(f"use-theme-colors returncode: {theme_color_result.returncode}")
                logger.info(f"use-theme-colors value: {theme_color_result.stdout.strip()}")

                if theme_color_result.returncode == 0 and theme_color_result.stdout.strip().lower() == 'true':
                    logger.info("✓ Terminal is using system theme colors")
                    logger.warning("⚠️ GTK theme detection is currently disabled (commented out)")
                    logger.info("→ Returning 'dark' as default")
                    return 'dark'   
                else:
                    # Step 3: Read terminal custom background color
                    logger.info("Step 3: Terminal uses custom colors, reading background-color")
                    bg_result = subprocess.run([
                        'gsettings', 'get',
                        f'org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{profile_id}/',
                        'background-color'
                    ], capture_output=True, text=True, timeout=2)
                    
                    logger.info(f"background-color returncode: {bg_result.returncode}")
                    logger.info(f"background-color value: {bg_result.stdout.strip()}")
                    
                    if bg_result.returncode == 0:
                        color_str = bg_result.stdout.strip().strip("'\"")
                        logger.info(f"Parsed color string: {color_str}")
                        
                        # Parse color string (format: 'rgb(r,g,b)' or '#RRGGBB')
                        if 'rgb' in color_str:
                            logger.info("Detected RGB format")
                            import re
                            match = re.search(r'rgb\(([\d.]+),([\d.]+),([\d.]+)\)', color_str)
                            if match:
                                rgb_values = [float(x) for x in match.groups()]
                                logger.info(f"Raw RGB values: {rgb_values}")
                                
                                if all(v <= 1.0 for v in rgb_values):
                                    r, g, b = [v * 255 for v in rgb_values]
                                    logger.info(f"Float RGB format (0-1) detected, converted to 0-255 range")
                                else:
                                    r, g, b = rgb_values
                                    logger.info(f"Integer RGB format (0-255) detected, using values directly")
                                
                                brightness = (0.299 * r + 0.587 * g + 0.114 * b)
                                theme = 'dark' if brightness < 128 else 'light'
                                logger.info(f"Final RGB values: R={r:.1f}, G={g:.1f}, B={b:.1f}")
                                logger.info(f"Calculated brightness: {brightness:.2f}")
                                logger.info(f"✓ Detected theme: {theme}")
                                return theme
                            else:
                                logger.warning(f"Failed to parse RGB format: {color_str}")
                        elif color_str.startswith('#'):
                            logger.info("Detected HEX format")
                            if len(color_str) >= 7:
                                r = int(color_str[1:3], 16)
                                g = int(color_str[3:5], 16)
                                b = int(color_str[5:7], 16)
                                brightness = (0.299 * r + 0.587 * g + 0.114 * b)
                                theme = 'dark' if brightness < 128 else 'light'
                                logger.info(f"HEX values: R={r}, G={g}, B={b}")
                                logger.info(f"Calculated brightness: {brightness:.2f}")
                                logger.info(f"✓ Detected theme: {theme}")
                                return theme
                            else:
                                logger.warning(f"Invalid HEX color length: {color_str}")
                        else:
                            logger.warning(f"Unknown color format: {color_str}")
                    else:
                        logger.warning("Failed to get background-color")
            else:
                logger.warning("Failed to get profile ID, trying fallback methods")
            
            logger.info("Step 4: Trying GNOME color-scheme (newer versions)")
            result = subprocess.run(
                ['gsettings', 'get', 'org.gnome.desktop.interface', 'color-scheme'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            logger.info(f"color-scheme returncode: {result.returncode}")
            logger.info(f"color-scheme value: {result.stdout.strip()}")
            
            if result.returncode == 0:
                color_scheme = result.stdout.strip().lower()
                if 'dark' in color_scheme:
                    logger.info("✓ Detected 'dark' from color-scheme")
                    return 'dark'
                elif 'light' in color_scheme or color_scheme:
                    logger.info("✓ Detected 'light' from color-scheme")
                    return 'light'
            else:
                logger.info("color-scheme not available")
            
            logger.info("Step 5: Trying KDE Plasma ColorScheme")
            result = subprocess.run(
                ['kreadconfig5', '--group', 'General', '--key', 'ColorScheme'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            logger.info(f"KDE ColorScheme returncode: {result.returncode}")
            logger.info(f"KDE ColorScheme value: {result.stdout.strip()}")
            
            if result.returncode == 0:
                color_scheme = result.stdout.strip().lower()
                if 'dark' in color_scheme:
                    logger.info("✓ Detected 'dark' from KDE")
                    return 'dark'
                elif color_scheme:
                    logger.info("✓ Detected 'light' from KDE")
                    return 'light'
            else:
                logger.info("KDE ColorScheme not available")
                    
        except subprocess.TimeoutExpired as e:
            logger.error(f"Timeout during theme detection: {e}")
        except FileNotFoundError as e:
            logger.error(f"Command not found: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during theme detection: {e}", exc_info=True)
        
        logger.warning("✗ All detection methods failed, returning 'unknown'")
        return 'unknown'
    
    @staticmethod
    def get_theme_for_config(
        user_theme: Optional[str] = None,
        auto_follow: Optional[bool] = None
    ) -> str:
        """
        Get the appropriate theme based on user configuration.
        
        Args:
            user_theme: User's theme preference ('auto', 'dark', 'light', 'default', or None)
            auto_follow: Whether to auto-follow system theme (deprecated, use user_theme='auto')
        
        Returns:
            Theme name to use: 'dark', 'light', or 'default'
        """
        # Handle legacy auto_follow parameter
        if auto_follow is True and user_theme is None:
            user_theme = 'auto'
        
        # If user explicitly set a theme (not 'auto'), use it
        if user_theme and user_theme != 'auto':
            return user_theme
        
        # If theme is 'auto' or auto_follow is enabled, detect system theme
        if user_theme == 'auto' or auto_follow is True:
            detected = SystemThemeDetector.detect_theme()
            if detected in ('dark', 'light'):
                return detected
            # If detection fails, fall back to default
            return 'default'
        
        # Default case
        return 'default'
