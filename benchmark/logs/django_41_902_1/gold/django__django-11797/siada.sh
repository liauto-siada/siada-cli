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
    conda create -p /tmp/siada_env_django__django-11797 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_django__django-11797/
    # conda create -p /tmp/siada_env_django__django-11797 python=3.12 -y
    conda activate /tmp/siada_env_django__django-11797
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_django__django-11797.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Filtering on query result overrides GROUP BY of internal query
Description
	
from django.contrib.auth import models
a = models.User.objects.filter(email__isnull=True).values('email').annotate(m=Max('id')).values('m')
print(a.query) # good
# SELECT MAX("auth_user"."id") AS "m" FROM "auth_user" WHERE "auth_user"."email" IS NULL GROUP BY "auth_user"."email"
print(a[:1].query) # good
# SELECT MAX("auth_user"."id") AS "m" FROM "auth_user" WHERE "auth_user"."email" IS NULL GROUP BY "auth_user"."email" LIMIT 1
b = models.User.objects.filter(id=a[:1])
print(b.query) # GROUP BY U0."id" should be GROUP BY U0."email"
# SELECT ... FROM "auth_user" WHERE "auth_user"."id" = (SELECT U0."id" FROM "auth_user" U0 WHERE U0."email" IS NULL GROUP BY U0."id" LIMIT 1)

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_django__django-11797/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_django__django-11797 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_django__django-11797
    