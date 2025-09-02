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
    conda create -p /tmp/siada_env_sphinx-doc__sphinx-7686 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_sphinx-doc__sphinx-7686/
    # conda create -p /tmp/siada_env_sphinx-doc__sphinx-7686 python=3.12 -y
    conda activate /tmp/siada_env_sphinx-doc__sphinx-7686
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_sphinx-doc__sphinx-7686.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
autosummary: The members variable for module template contains imported members
**Describe the bug**
autosummary: The members variable for module template contains imported members even if autosummary_imported_members is False.

**To Reproduce**

```
# _templates/autosummary/module.rst
{{ fullname | escape | underline }}

.. automodule:: {{ fullname }}

   .. autosummary::
   {% for item in members %}
      {{ item }}
   {%- endfor %}

```
```
# example.py
import os
```
```
# index.rst
.. autosummary::
   :toctree: generated

   example
```
```
# conf.py
autosummary_generate = True
autosummary_imported_members = False
```

As a result, I got following output:
```
# generated/example.rst
example
=======

.. automodule:: example

   .. autosummary::

      __builtins__
      __cached__
      __doc__
      __file__
      __loader__
      __name__
      __package__
      __spec__
      os
```

**Expected behavior**
The template variable `members` should not contain imported members when `autosummary_imported_members` is False.

**Your project**
No

**Screenshots**
No

**Environment info**
- OS: Mac
- Python version: 3.8.2
- Sphinx version: 3.1.0dev
- Sphinx extensions:  sphinx.ext.autosummary
- Extra tools: No

**Additional context**
No


SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_sphinx-doc__sphinx-7686/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_sphinx-doc__sphinx-7686 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_sphinx-doc__sphinx-7686
    