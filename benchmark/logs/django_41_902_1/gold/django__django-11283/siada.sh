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
    conda create -p /tmp/siada_env_django__django-11283 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_django__django-11283/
    # conda create -p /tmp/siada_env_django__django-11283 python=3.12 -y
    conda activate /tmp/siada_env_django__django-11283
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_django__django-11283.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Migration auth.0011_update_proxy_permissions fails for models recreated as a proxy.
Description
	 
		(last modified by Mariusz Felisiak)
	 
I am trying to update my project to Django 2.2. When I launch python manage.py migrate, I get this error message when migration auth.0011_update_proxy_permissions is applying (full stacktrace is available ​here):
django.db.utils.IntegrityError: duplicate key value violates unique constraint "idx_18141_auth_permission_content_type_id_01ab375a_uniq" DETAIL: Key (co.ntent_type_id, codename)=(12, add_agency) already exists.
It looks like the migration is trying to re-create already existing entries in the auth_permission table. At first I though it cloud because we recently renamed a model. But after digging and deleting the entries associated with the renamed model from our database in the auth_permission table, the problem still occurs with other proxy models.
I tried to update directly from 2.0.13 and 2.1.8. The issues appeared each time. I also deleted my venv and recreated it without an effect.
I searched for a ticket about this on the bug tracker but found nothing. I also posted this on ​django-users and was asked to report this here.

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_django__django-11283/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_django__django-11283 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_django__django-11283
    