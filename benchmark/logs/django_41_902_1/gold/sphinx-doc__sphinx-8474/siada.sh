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
    conda create -p /tmp/siada_env_sphinx-doc__sphinx-8474 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_sphinx-doc__sphinx-8474/
    # conda create -p /tmp/siada_env_sphinx-doc__sphinx-8474 python=3.12 -y
    conda activate /tmp/siada_env_sphinx-doc__sphinx-8474
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_sphinx-doc__sphinx-8474.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
v3.3 upgrade started generating "WARNING: no number is assigned for table" warnings
We've updated to Sphinx 3.3 in our documentation, and suddenly the following warning started popping up in our builds when we build either `singlehtml` or `latex`.:

`WARNING: no number is assigned for table:`

I looked through the changelog but it didn't seem like there was anything related to `numref` that was changed, but perhaps I missed something? Could anyone point me to a change in the numref logic so I can figure out where these warnings are coming from?

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_sphinx-doc__sphinx-8474/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_sphinx-doc__sphinx-8474 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_sphinx-doc__sphinx-8474
    