import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv


def generate_search_path_list(default_file, git_root, command_line_file):
    files = []
    files.append(Path.home() / default_file)  # homedir
    if git_root:
        files.append(Path(git_root) / default_file)  # git root
    files.append(default_file)
    if command_line_file:
        files.append(command_line_file)

    resolved_files = []
    for fn in files:
        try:
            resolved_files.append(Path(fn).resolve())
        except OSError:
            pass

    files = resolved_files
    files.reverse()
    uniq = []
    for fn in files:
        if fn not in uniq:
            uniq.append(fn)
    uniq.reverse()
    files = uniq
    files = list(map(str, files))
    files = list(dict.fromkeys(files))

    return files


def load_dotenv_files(git_root, dotenv_fname, encoding="utf-8"):
    marker = os.environ.pop("_SIADA_CLI_ENV_KEYS", None)
    protected = {}
    if marker:
        try:
            names = json.loads(marker)
            if not isinstance(names, list) or any(
                not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
                for name in names
            ):
                raise ValueError("Invalid environment variable names")
            protected = {name: os.environ.get(name) for name in names}
        except (ValueError, TypeError):
            pass
    # Standard .env file search path
    dotenv_files = generate_search_path_list(
        ".env",
        git_root,
        dotenv_fname,
    )

    loaded = []
    for fname in dotenv_files:
        try:
            if Path(fname).exists():
                load_dotenv(fname, override=True, encoding=encoding)
                loaded.append(fname)
        except Exception as error:
            print(f"Warning: Could not load .env ({type(error).__name__}).", file=sys.stderr)
        finally:
            for name, value in protected.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
    return loaded