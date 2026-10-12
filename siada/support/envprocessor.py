import json
import os
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
    # The UI launcher forwards --set-env through inherited environment values.
    # Preserve only those explicit assignments across the usual .env override
    # order. Consume the names-only marker before any agent tool can inherit it.
    explicit_values = {}
    encoded_keys = os.environ.pop("_SIADA_CLI_ENV_KEYS", None)
    if encoded_keys:
        try:
            keys = json.loads(encoded_keys)
            if isinstance(keys, list):
                explicit_values = {
                    key: os.environ[key]
                    for key in keys
                    if isinstance(key, str) and key in os.environ
                }
        except (ValueError, TypeError):
            pass

    # Standard .env file search path
    dotenv_files = generate_search_path_list(
        ".env",
        git_root,
        dotenv_fname,
    )

    loaded = []
    try:
        for fname in dotenv_files:
            try:
                if Path(fname).exists():
                    load_dotenv(fname, override=True, encoding=encoding)
                    loaded.append(fname)
            except Exception as exc:
                print(
                    f"Unable to load environment file {fname}: "
                    f"{type(exc).__name__}",
                    file=sys.stderr,
                )
    finally:
        os.environ.update(explicit_values)
    return loaded