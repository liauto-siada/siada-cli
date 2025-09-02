#!/bin/bash
    set -e

    # Random sleep to avoid concurrent network connection errors
    SLEEP_TIME=$((RANDOM % 56 + 5))  # Random number between 5 and 60
    # echo "Sleeping for $SLEEP_TIME seconds to avoid concurrent connections..."
    # sleep $SLEEP_TIME

    conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
    conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
    conda config --set show_channel_urls yes

    # export http_proxy="http://127.0.0.1:7890"
    # export https_proxy="http://127.0.0.1:7890"
    # export HTTP_PROXY="http://127.0.0.1:7890"
    # export HTTPS_PROXY="http://127.0.0.1:7890"

    # 将预装环境注册到 conda
    source $(conda info --base)/etc/profile.d/conda.sh
    ln -sf /siada-agenthub/python312_standalone $(conda info --base)/envs/python312_base

    # 使用 conda 克隆环境（这会自动处理路径问题）
    conda create -p /tmp/siada_env_django__django-11583 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_django__django-11583/
    # conda create -p /tmp/siada_env_django__django-11583 python=3.12 -y
    conda activate /tmp/siada_env_django__django-11583
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_django__django-11583.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Auto-reloading with StatReloader very intermittently throws "ValueError: embedded null byte".
Description
	
Raising this mainly so that it's tracked, as I have no idea how to reproduce it, nor why it's happening. It ultimately looks like a problem with Pathlib, which wasn't used prior to 2.2.
Stacktrace:
Traceback (most recent call last):
 File "manage.py" ...
	execute_from_command_line(sys.argv)
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/core/management/__init__.py", line 381, in execute_from_command_line
	utility.execute()
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/core/management/__init__.py", line 375, in execute
	self.fetch_command(subcommand).run_from_argv(self.argv)
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/core/management/base.py", line 323, in run_from_argv
	self.execute(*args, **cmd_options)
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/core/management/commands/runserver.py", line 60, in execute
	super().execute(*args, **options)
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/core/management/base.py", line 364, in execute
	output = self.handle(*args, **options)
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/core/management/commands/runserver.py", line 95, in handle
	self.run(**options)
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/core/management/commands/runserver.py", line 102, in run
	autoreload.run_with_reloader(self.inner_run, **options)
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/utils/autoreload.py", line 577, in run_with_reloader
	start_django(reloader, main_func, *args, **kwargs)
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/utils/autoreload.py", line 562, in start_django
	reloader.run(django_main_thread)
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/utils/autoreload.py", line 280, in run
	self.run_loop()
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/utils/autoreload.py", line 286, in run_loop
	next(ticker)
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/utils/autoreload.py", line 326, in tick
	for filepath, mtime in self.snapshot_files():
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/utils/autoreload.py", line 342, in snapshot_files
	for file in self.watched_files():
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/utils/autoreload.py", line 241, in watched_files
	yield from iter_all_python_module_files()
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/utils/autoreload.py", line 103, in iter_all_python_module_files
	return iter_modules_and_files(modules, frozenset(_error_files))
 File "/Userz/kez/path/to/venv/lib/python3.6/site-packages/django/utils/autoreload.py", line 132, in iter_modules_and_files
	results.add(path.resolve().absolute())
 File "/Users/kez/.pyenv/versions/3.6.2/lib/python3.6/pathlib.py", line 1120, in resolve
	s = self._flavour.resolve(self, strict=strict)
 File "/Users/kez/.pyenv/versions/3.6.2/lib/python3.6/pathlib.py", line 346, in resolve
	return _resolve(base, str(path)) or sep
 File "/Users/kez/.pyenv/versions/3.6.2/lib/python3.6/pathlib.py", line 330, in _resolve
	target = accessor.readlink(newpath)
 File "/Users/kez/.pyenv/versions/3.6.2/lib/python3.6/pathlib.py", line 441, in readlink
	return os.readlink(path)
ValueError: embedded null byte
I did print(path) before os.readlink(path) in pathlib and ended up with:
/Users/kez
/Users/kez/.pyenv
/Users/kez/.pyenv/versions
/Users/kez/.pyenv/versions/3.6.2
/Users/kez/.pyenv/versions/3.6.2/lib
/Users/kez/.pyenv/versions/3.6.2/lib/python3.6
/Users/kez/.pyenv/versions/3.6.2/lib/python3.6/asyncio
/Users/kez/.pyenv/versions/3.6.2/lib/python3.6/asyncio/selector_events.py
/Users
It always seems to be /Users which is last
It may have already printed /Users as part of another .resolve() multiple times (that is, the order is not deterministic, and it may have traversed beyond /Users successfully many times during startup.
I don't know where to begin looking for the rogue null byte, nor why it only exists sometimes.
Best guess I have is that there's a mountpoint in /Users to a samba share which may not have been connected to yet? I dunno.
I have no idea if it's fixable without removing the use of pathlib (which tbh I think should happen anyway, because it's slow) and reverting to using os.path.join and friends. 
I have no idea if it's fixed in a later Python version, but with no easy way to reproduce ... dunno how I'd check.
I have no idea if it's something specific to my system (pyenv, OSX 10.11, etc)

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_django__django-11583/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_django__django-11583 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_django__django-11583
    