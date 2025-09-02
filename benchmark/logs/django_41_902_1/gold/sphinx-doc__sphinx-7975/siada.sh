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
    conda create -p /tmp/siada_env_sphinx-doc__sphinx-7975 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_sphinx-doc__sphinx-7975/
    # conda create -p /tmp/siada_env_sphinx-doc__sphinx-7975 python=3.12 -y
    conda activate /tmp/siada_env_sphinx-doc__sphinx-7975
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_sphinx-doc__sphinx-7975.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Two sections called Symbols in index
When using index entries with the following leading characters: _@_, _£_, and _←_ I get two sections called _Symbols_ in the HTML output, the first containing all _@_ entries before ”normal” words and the second containing _£_ and _←_ entries after the ”normal” words.  Both have the same anchor in HTML so the links at the top of the index page contain two _Symbols_ links, one before the letters and one after, but both lead to the first section.


SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_sphinx-doc__sphinx-7975/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_sphinx-doc__sphinx-7975 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_sphinx-doc__sphinx-7975
    