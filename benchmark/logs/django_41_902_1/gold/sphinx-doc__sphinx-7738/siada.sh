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
    conda create -p /tmp/siada_env_sphinx-doc__sphinx-7738 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_sphinx-doc__sphinx-7738/
    # conda create -p /tmp/siada_env_sphinx-doc__sphinx-7738 python=3.12 -y
    conda activate /tmp/siada_env_sphinx-doc__sphinx-7738
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_sphinx-doc__sphinx-7738.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
overescaped trailing underscore on attribute with napoleon
**Describe the bug**
Attribute name `hello_` shows up as `hello\_` in the html (visible backslash) with napoleon.

**To Reproduce**
Steps to reproduce the behavior:

empty `__init__.py`
`a.py` contains
```python
class A:
    """
    Attributes
    ----------
    hello_: int
        hi
    """
    pass
```
run `sphinx-quickstart`
add `'sphinx.ext.autodoc', 'sphinx.ext.napoleon'` to extensions in conf.py.
add `.. autoclass:: a.A` to index.rst
PYTHONPATH=. make clean html
open _build/html/index.html in web browser and see the ugly backslash.

**Expected behavior**
No backslash, a similar output to what I get for
```rst
    .. attribute:: hello_
        :type: int

        hi
```
(the type shows up differently as well, but that's not the point here)
Older versions like 2.4.3 look ok to me.

**Environment info**
- OS: Linux debian testing
- Python version: 3.8.3
- Sphinx version: 3.0.4
- Sphinx extensions:  sphinx.ext.autodoc, sphinx.ext.napoleon
- Extra tools:

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_sphinx-doc__sphinx-7738/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_sphinx-doc__sphinx-7738 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_sphinx-doc__sphinx-7738
    