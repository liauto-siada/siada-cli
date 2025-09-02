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
    conda create -p /tmp/siada_env_pylint-dev__pylint-6506 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_pylint-dev__pylint-6506/
    # conda create -p /tmp/siada_env_pylint-dev__pylint-6506 python=3.12 -y
    conda activate /tmp/siada_env_pylint-dev__pylint-6506
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_pylint-dev__pylint-6506.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Traceback printed for unrecognized option
### Bug description

A traceback is printed when an unrecognized option is passed to pylint.

### Configuration

_No response_

### Command used

```shell
pylint -Q
```


### Pylint output

```shell
************* Module Command line
Command line:1:0: E0015: Unrecognized option found: Q (unrecognized-option)
Traceback (most recent call last):
  File "/Users/markbyrne/venv310/bin/pylint", line 33, in <module>
    sys.exit(load_entry_point('pylint', 'console_scripts', 'pylint')())
  File "/Users/markbyrne/programming/pylint/pylint/__init__.py", line 24, in run_pylint
    PylintRun(argv or sys.argv[1:])
  File "/Users/markbyrne/programming/pylint/pylint/lint/run.py", line 135, in __init__
    args = _config_initialization(
  File "/Users/markbyrne/programming/pylint/pylint/config/config_initialization.py", line 85, in _config_initialization
    raise _UnrecognizedOptionError(options=unrecognized_options)
pylint.config.exceptions._UnrecognizedOptionError
```


### Expected behavior

The top part of the current output is handy:
`Command line:1:0: E0015: Unrecognized option found: Q (unrecognized-option)`

The traceback I don't think is expected & not user-friendly.
A usage tip, for example:
```python
mypy -Q
usage: mypy [-h] [-v] [-V] [more options; see below]
            [-m MODULE] [-p PACKAGE] [-c PROGRAM_TEXT] [files ...]
mypy: error: unrecognized arguments: -Q
```

### Pylint version

```shell
pylint 2.14.0-dev0
astroid 2.11.3
Python 3.10.0b2 (v3.10.0b2:317314165a, May 31 2021, 10:02:22) [Clang 12.0.5 (clang-1205.0.22.9)]
```


### OS / Environment

_No response_

### Additional dependencies

_No response_

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_pylint-dev__pylint-6506/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_pylint-dev__pylint-6506 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_pylint-dev__pylint-6506
    