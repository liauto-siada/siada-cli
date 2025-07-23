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
    # Standard .env file search path
    dotenv_files = generate_search_path_list(
        ".env",
        git_root,
        dotenv_fname,
    )

    # Explicitly add the OAuth keys file to the beginning of the list
    oauth_keys_file = Path.home() / ".siadahub" / "oauth-keys.env"
    if oauth_keys_file.exists():
        # Insert at the beginning so it's loaded first (and potentially overridden)
        dotenv_files.insert(0, str(oauth_keys_file.resolve()))
        # Remove duplicates if it somehow got included by generate_search_path_list
        dotenv_files = list(dict.fromkeys(dotenv_files))

    loaded = []
    for fname in dotenv_files:
        try:
            if Path(fname).exists():
                load_dotenv(fname, override=True, encoding=encoding)
                loaded.append(fname)
        except OSError as e:
            print(f"OSError loading {fname}: {e}")
        except Exception as e:
            print(f"Error loading {fname}: {e}")
    return loaded