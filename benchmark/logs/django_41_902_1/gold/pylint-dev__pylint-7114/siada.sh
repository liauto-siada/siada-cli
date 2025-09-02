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
    conda create -p /tmp/siada_env_pylint-dev__pylint-7114 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_pylint-dev__pylint-7114/
    # conda create -p /tmp/siada_env_pylint-dev__pylint-7114 python=3.12 -y
    conda activate /tmp/siada_env_pylint-dev__pylint-7114
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_pylint-dev__pylint-7114.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Linting fails if module contains module of the same name
### Steps to reproduce

Given multiple files:
```
.
`-- a/
    |-- a.py
    `-- b.py
```
Which are all empty, running `pylint a` fails:

```
$ pylint a
************* Module a
a/__init__.py:1:0: F0010: error while code parsing: Unable to load file a/__init__.py:
[Errno 2] No such file or directory: 'a/__init__.py' (parse-error)
$
```

However, if I rename `a.py`, `pylint a` succeeds:

```
$ mv a/a.py a/c.py
$ pylint a
$
```
Alternatively, I can also `touch a/__init__.py`, but that shouldn't be necessary anymore.

### Current behavior

Running `pylint a` if `a/a.py` is present fails while searching for an `__init__.py` file.

### Expected behavior

Running `pylint a` if `a/a.py` is present should succeed.

### pylint --version output

Result of `pylint --version` output:

```
pylint 3.0.0a3
astroid 2.5.6
Python 3.8.5 (default, Jan 27 2021, 15:41:15) 
[GCC 9.3.0]
```

### Additional info

This also has some side-effects in module resolution. For example, if I create another file `r.py`:

```
.
|-- a
|   |-- a.py
|   `-- b.py
`-- r.py
```

With the content:

```
from a import b
```

Running `pylint -E r` will run fine, but `pylint -E r a` will fail. Not just for module a, but for module r as well.

```
************* Module r
r.py:1:0: E0611: No name 'b' in module 'a' (no-name-in-module)
************* Module a
a/__init__.py:1:0: F0010: error while code parsing: Unable to load file a/__init__.py:
[Errno 2] No such file or directory: 'a/__init__.py' (parse-error)
```

Again, if I rename `a.py` to `c.py`, `pylint -E r a` will work perfectly.

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_pylint-dev__pylint-7114/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_pylint-dev__pylint-7114 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_pylint-dev__pylint-7114
    