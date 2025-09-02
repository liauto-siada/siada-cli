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
    conda create -p /tmp/siada_env_django__django-12184 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_django__django-12184/
    # conda create -p /tmp/siada_env_django__django-12184 python=3.12 -y
    conda activate /tmp/siada_env_django__django-12184
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_django__django-12184.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Optional URL params crash some view functions.
Description
	
My use case, running fine with Django until 2.2:
URLConf:
urlpatterns += [
	...
	re_path(r'^module/(?P<format>(html|json|xml))?/?$', views.modules, name='modules'),
]
View:
def modules(request, format='html'):
	...
	return render(...)
With Django 3.0, this is now producing an error:
Traceback (most recent call last):
 File "/l10n/venv/lib/python3.6/site-packages/django/core/handlers/exception.py", line 34, in inner
	response = get_response(request)
 File "/l10n/venv/lib/python3.6/site-packages/django/core/handlers/base.py", line 115, in _get_response
	response = self.process_exception_by_middleware(e, request)
 File "/l10n/venv/lib/python3.6/site-packages/django/core/handlers/base.py", line 113, in _get_response
	response = wrapped_callback(request, *callback_args, **callback_kwargs)
Exception Type: TypeError at /module/
Exception Value: modules() takes from 1 to 2 positional arguments but 3 were given

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_django__django-12184/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_django__django-12184 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_django__django-12184
    