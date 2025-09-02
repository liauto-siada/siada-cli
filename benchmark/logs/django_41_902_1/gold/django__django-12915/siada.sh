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
    conda create -p /tmp/siada_env_django__django-12915 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_django__django-12915/
    # conda create -p /tmp/siada_env_django__django-12915 python=3.12 -y
    conda activate /tmp/siada_env_django__django-12915
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_django__django-12915.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Add get_response_async for ASGIStaticFilesHandler
Description
	
It looks like the StaticFilesHandlerMixin is missing the the async response function.
Without this, when trying to use the ASGIStaticFilesHandler, this is the traceback:
Exception inside application: 'NoneType' object is not callable
Traceback (most recent call last):
 File ".../lib/python3.7/site-packages/daphne/cli.py", line 30, in asgi
	await self.app(scope, receive, send)
 File ".../src/django/django/contrib/staticfiles/handlers.py", line 86, in __call__
	return await super().__call__(scope, receive, send)
 File ".../src/django/django/core/handlers/asgi.py", line 161, in __call__
	response = await self.get_response_async(request)
 File ".../src/django/django/core/handlers/base.py", line 148, in get_response_async
	response = await self._middleware_chain(request)
TypeError: 'NoneType' object is not callable

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_django__django-12915/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_django__django-12915 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_django__django-12915
    