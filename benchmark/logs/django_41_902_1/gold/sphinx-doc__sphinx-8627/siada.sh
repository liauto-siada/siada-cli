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
    conda create -p /tmp/siada_env_sphinx-doc__sphinx-8627 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_sphinx-doc__sphinx-8627/
    # conda create -p /tmp/siada_env_sphinx-doc__sphinx-8627 python=3.12 -y
    conda activate /tmp/siada_env_sphinx-doc__sphinx-8627
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_sphinx-doc__sphinx-8627.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
autodoc isn't able to resolve struct.Struct type annotations
**Describe the bug**
If `struct.Struct` is declared in any type annotations, I get `class reference target not found: Struct`

**To Reproduce**
Simple `index.rst`
```
Hello World
===========

code docs
=========

.. automodule:: helloworld.helloworld
```

Simple `helloworld.py`
```
import struct
import pathlib

def consume_struct(_: struct.Struct) -> None:
    pass

def make_struct() -> struct.Struct:
    mystruct = struct.Struct('HH')
    return mystruct

def make_path() -> pathlib.Path:
    return pathlib.Path()
```

Command line:
```
python3 -m sphinx -b html docs/ doc-out -nvWT
```

**Expected behavior**
If you comment out the 2 functions that have `Struct` type annotations, you'll see that `pathlib.Path` resolves fine and shows up in the resulting documentation. I'd expect that `Struct` would also resolve correctly.

**Your project**
n/a

**Screenshots**
n/a

**Environment info**
- OS: Ubuntu 18.04, 20.04
- Python version: 3.8.2
- Sphinx version: 3.2.1
- Sphinx extensions:  'sphinx.ext.autodoc',
              'sphinx.ext.autosectionlabel',
              'sphinx.ext.intersphinx',
              'sphinx.ext.doctest',
              'sphinx.ext.todo'
- Extra tools: 

**Additional context**


- [e.g. URL or Ticket]



SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_sphinx-doc__sphinx-8627/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_sphinx-doc__sphinx-8627 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_sphinx-doc__sphinx-8627
    