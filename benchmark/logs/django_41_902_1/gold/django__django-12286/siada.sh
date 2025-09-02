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
    conda create -p /tmp/siada_env_django__django-12286 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_django__django-12286/
    # conda create -p /tmp/siada_env_django__django-12286 python=3.12 -y
    conda activate /tmp/siada_env_django__django-12286
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_django__django-12286.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
translation.E004 shouldn't be raised on sublanguages when a base language is available.
Description
	
According to Django documentation:
If a base language is available but the sublanguage specified is not, Django uses the base language. For example, if a user specifies de-at (Austrian German) but Django only has de available, Django uses de.
However, when using Django 3.0.2, if my settings.py has
LANGUAGE_CODE = "de-at"
I get this error message:
SystemCheckError: System check identified some issues:
ERRORS:
?: (translation.E004) You have provided a value for the LANGUAGE_CODE setting that is not in the LANGUAGES setting.
If using
LANGUAGE_CODE = "es-ar"
Django works fine (es-ar is one of the translations provided out of the box).

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_django__django-12286/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_django__django-12286 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_django__django-12286
    