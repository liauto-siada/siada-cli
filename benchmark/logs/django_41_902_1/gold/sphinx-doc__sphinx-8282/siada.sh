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
    conda create -p /tmp/siada_env_sphinx-doc__sphinx-8282 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_sphinx-doc__sphinx-8282/
    # conda create -p /tmp/siada_env_sphinx-doc__sphinx-8282 python=3.12 -y
    conda activate /tmp/siada_env_sphinx-doc__sphinx-8282
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_sphinx-doc__sphinx-8282.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
autodoc_typehints does not effect to overloaded callables
**Describe the bug**
autodoc_typehints does not effect to overloaded callables.

**To Reproduce**

```
# in conf.py
autodoc_typehints = 'none'
```
```
# in index.rst
.. automodule:: example
   :members:
   :undoc-members:
```
```
# in example.py
from typing import overload


@overload
def foo(x: int) -> int:
    ...


@overload
def foo(x: float) -> float:
    ...


def foo(x):
    return x
```

**Expected behavior**
All typehints for overloaded callables are obeyed `autodoc_typehints` setting.

**Your project**
No

**Screenshots**
No

**Environment info**
- OS: Mac
- Python version: 3.8.2
- Sphinx version: 3.1.0dev
- Sphinx extensions: sphinx.ext.autodoc
- Extra tools: No

**Additional context**
No

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_sphinx-doc__sphinx-8282/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_sphinx-doc__sphinx-8282 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_sphinx-doc__sphinx-8282
    