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
    conda create -p /tmp/siada_env_django__django-11564 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_django__django-11564/
    # conda create -p /tmp/siada_env_django__django-11564 python=3.12 -y
    conda activate /tmp/siada_env_django__django-11564
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_django__django-11564.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Add support for SCRIPT_NAME in STATIC_URL and MEDIA_URL
Description
	 
		(last modified by Rostyslav Bryzgunov)
	 
By default, {% static '...' %} tag just appends STATIC_URL in the path. When running on sub-path, using SCRIPT_NAME WSGI param, it results in incorrect static URL - it doesn't prepend SCRIPT_NAME prefix.
This problem can be solved with prepending SCRIPT_NAME to STATIC_URL in settings.py but that doesn't work when SCRIPT_NAME is a dynamic value.
This can be easily added into default Django static tag and django.contrib.staticfiles tag as following:
def render(self, context):
	url = self.url(context)
	# Updating url here with request.META['SCRIPT_NAME'] 
	if self.varname is None:
		return url
	context[self.varname] = url
		return ''
On more research I found that FileSystemStorage and StaticFilesStorage ignores SCRIPT_NAME as well. 
We might have to do a lot of changes but I think it's worth the efforts.

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_django__django-11564/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_django__django-11564 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_django__django-11564
    