import os
from typing import Optional


def get_language_from_file_extension(filename: str) -> str:
    """
    Get the language identifier for markdown code fences based on file extension.
    
    Args:
        filename: The name of the file (can include path)
        
    Returns:
        Language identifier string for markdown code fences
    """
    if not filename:
        return ""
    
    # Extract the file extension (convert to lowercase for case-insensitive matching)
    _, ext = os.path.splitext(filename.lower())
    
    # Remove the leading dot
    ext = ext.lstrip('.')
    
    # Mapping of file extensions to language identifiers
    extension_to_language = {
        # Python
        'py': 'python',
        'pyw': 'python',
        'pyi': 'python',
        
        # JavaScript/TypeScript
        'js': 'javascript',
        'mjs': 'javascript',
        'jsx': 'jsx',
        'ts': 'typescript',
        'tsx': 'tsx',
        
        # Java/JVM languages
        'java': 'java',
        'kt': 'kotlin',
        'kts': 'kotlin',
        'scala': 'scala',
        'sc': 'scala',
        'groovy': 'groovy',
        'gradle': 'gradle',
        
        # C/C++
        'c': 'c',
        'h': 'c',
        'cpp': 'cpp',
        'cxx': 'cpp',
        'cc': 'cpp',
        'c++': 'cpp',
        'hpp': 'cpp',
        'hxx': 'cpp',
        'hh': 'cpp',
        
        # C#
        'cs': 'csharp',
        
        # Go
        'go': 'go',
        
        # Rust
        'rs': 'rust',
        
        # PHP
        'php': 'php',
        'php3': 'php',
        'php4': 'php',
        'php5': 'php',
        'phtml': 'php',
        
        # Ruby
        'rb': 'ruby',
        'rbw': 'ruby',
        'rake': 'ruby',
        'gemspec': 'ruby',
        
        # Swift
        'swift': 'swift',
        
        # Objective-C
        'm': 'objective-c',
        'mm': 'objective-c',
        
        # Dart
        'dart': 'dart',
        
        # R
        'r': 'r',
        
        # Shell scripting
        'sh': 'bash',
        'bash': 'bash',
        'zsh': 'zsh',
        'fish': 'fish',
        'csh': 'csh',
        'tcsh': 'tcsh',
        
        # PowerShell
        'ps1': 'powershell',
        'psm1': 'powershell',
        'psd1': 'powershell',
        
        # SQL
        'sql': 'sql',
        'mysql': 'sql',
        'pgsql': 'sql',
        'plsql': 'sql',
        
        # Web technologies
        'html': 'html',
        'htm': 'html',
        'xhtml': 'html',
        'css': 'css',
        'scss': 'scss',
        'sass': 'sass',
        'less': 'less',
        'styl': 'stylus',
        
        # Markup and data formats
        'xml': 'xml',
        'xsl': 'xml',
        'xslt': 'xml',
        'svg': 'xml',
        'json': 'json',
        'yaml': 'yaml',
        'yml': 'yaml',
        'toml': 'toml',
        'ini': 'ini',
        'cfg': 'ini',
        'conf': 'ini',
        'properties': 'properties',
        
        # Documentation
        'md': 'markdown',
        'markdown': 'markdown',
        'mdown': 'markdown',
        'mkd': 'markdown',
        'rst': 'rst',
        'tex': 'latex',
        'latex': 'latex',
        
        # Docker
        'dockerfile': 'dockerfile',
        
        # Other scripting languages
        'lua': 'lua',
        'pl': 'perl',
        'pm': 'perl',
        'py': 'python',
        'vim': 'vim',
        'vimrc': 'vim',
        
        # Functional languages
        'hs': 'haskell',
        'lhs': 'haskell',
        'elm': 'elm',
        'ml': 'ocaml',
        'mli': 'ocaml',
        'fs': 'fsharp',
        'fsi': 'fsharp',
        'fsx': 'fsharp',
        'clj': 'clojure',
        'cljs': 'clojure',
        'cljc': 'clojure',
        'edn': 'clojure',
        
        # Assembly
        'asm': 'assembly',
        's': 'assembly',
        
        # Other formats
        'cmake': 'cmake',
        'make': 'makefile',
        'makefile': 'makefile',
        'dockerfile': 'dockerfile',
        'gitignore': 'gitignore',
        'gitconfig': 'gitconfig',
        'editorconfig': 'editorconfig',
    }
    
    # Return the mapped language or the extension itself if not found
    return extension_to_language.get(ext, ext if ext else "text")


def get_language_from_filename(filename: str) -> str:
    """
    Alias for get_language_from_file_extension for backward compatibility.
    
    Args:
        filename: The name of the file (can include path)
        
    Returns:
        Language identifier string for markdown code fences
    """
    return get_language_from_file_extension(filename)


def is_supported_language(filename: str) -> bool:
    """
    Check if the file extension is supported (has a known language mapping).
    
    Args:
        filename: The name of the file (can include path)
        
    Returns:
        True if the language is explicitly supported, False otherwise
    """
    if not filename:
        return False
    
    _, ext = os.path.splitext(filename.lower())
    ext = ext.lstrip('.')
    
    supported_extensions = {
        'py', 'pyw', 'pyi', 'js', 'mjs', 'jsx', 'ts', 'tsx', 'java', 'kt', 'kts',
        'scala', 'sc', 'groovy', 'gradle', 'c', 'h', 'cpp', 'cxx', 'cc', 'c++',
        'hpp', 'hxx', 'hh', 'cs', 'go', 'rs', 'php', 'php3', 'php4', 'php5',
        'phtml', 'rb', 'rbw', 'rake', 'gemspec', 'swift', 'm', 'mm', 'dart', 'r',
        'sh', 'bash', 'zsh', 'fish', 'csh', 'tcsh', 'ps1', 'psm1', 'psd1', 'sql',
        'mysql', 'pgsql', 'plsql', 'html', 'htm', 'xhtml', 'css', 'scss', 'sass',
        'less', 'styl', 'xml', 'xsl', 'xslt', 'svg', 'json', 'yaml', 'yml', 'toml',
        'ini', 'cfg', 'conf', 'properties', 'md', 'markdown', 'mdown', 'mkd', 'rst',
        'tex', 'latex', 'dockerfile', 'lua', 'pl', 'pm', 'vim', 'vimrc', 'hs', 'lhs',
        'elm', 'ml', 'mli', 'fs', 'fsi', 'fsx', 'clj', 'cljs', 'cljc', 'edn', 'asm',
        's', 'cmake', 'make', 'makefile', 'gitignore', 'gitconfig', 'editorconfig'
    }
    
    return ext in supported_extensions
