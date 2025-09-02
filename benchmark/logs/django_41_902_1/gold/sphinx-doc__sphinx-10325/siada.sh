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
    conda create -p /tmp/siada_env_sphinx-doc__sphinx-10325 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_sphinx-doc__sphinx-10325/
    # conda create -p /tmp/siada_env_sphinx-doc__sphinx-10325 python=3.12 -y
    conda activate /tmp/siada_env_sphinx-doc__sphinx-10325
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_sphinx-doc__sphinx-10325.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
inherited-members should support more than one class
**Is your feature request related to a problem? Please describe.**
I have two situations:
- A class inherits from multiple other classes. I want to document members from some of the base classes but ignore some of the base classes
- A module contains several class definitions that inherit from different classes that should all be ignored (e.g., classes that inherit from list or set or tuple). I want to ignore members from list, set, and tuple while documenting all other inherited members in classes in the module.

**Describe the solution you'd like**
The :inherited-members: option to automodule should accept a list of classes. If any of these classes are encountered as base classes when instantiating autoclass documentation, they should be ignored.

**Describe alternatives you've considered**
The alternative is to not use automodule, but instead manually enumerate several autoclass blocks for a module. This only addresses the second bullet in the problem description and not the first. It is also tedious for modules containing many class definitions.



SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_sphinx-doc__sphinx-10325/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_sphinx-doc__sphinx-10325 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_sphinx-doc__sphinx-10325
    