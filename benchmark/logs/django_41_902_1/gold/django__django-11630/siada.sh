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
    conda create -p /tmp/siada_env_django__django-11630 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_django__django-11630/
    # conda create -p /tmp/siada_env_django__django-11630 python=3.12 -y
    conda activate /tmp/siada_env_django__django-11630
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_django__django-11630.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Django throws error when different apps with different models have the same name table name.
Description
	
Error message:
table_name: (models.E028) db_table 'table_name' is used by multiple models: base.ModelName, app2.ModelName.
We have a Base app that points to a central database and that has its own tables. We then have multiple Apps that talk to their own databases. Some share the same table names.
We have used this setup for a while, but after upgrading to Django 2.2 we're getting an error saying we're not allowed 2 apps, with 2 different models to have the same table names. 
Is this correct behavior? We've had to roll back to Django 2.0 for now.

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_django__django-11630/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_django__django-11630 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_django__django-11630
    