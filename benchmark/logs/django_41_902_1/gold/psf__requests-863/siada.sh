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
    conda create -p /tmp/siada_env_psf__requests-863 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_psf__requests-863/
    # conda create -p /tmp/siada_env_psf__requests-863 python=3.12 -y
    conda activate /tmp/siada_env_psf__requests-863
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_psf__requests-863.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Allow lists in the dict values of the hooks argument
Currently the Request class has a .register_hook() method but it parses the dictionary it expects from it's hooks argument weirdly: the argument can only specify one hook function per hook.  If you pass in a list of hook functions per hook the code in Request.**init**() will wrap the list in a list which then fails when the hooks are consumed (since a list is not callable).  This is especially annoying since you can not use multiple hooks from a session.  The only way to get multiple hooks now is to create the request object without sending it, then call .register_hook() multiple times and then finally call .send().

This would all be much easier if Request.**init**() parsed the hooks parameter in a way that it accepts lists as it's values.


SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_psf__requests-863/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_psf__requests-863 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_psf__requests-863
    