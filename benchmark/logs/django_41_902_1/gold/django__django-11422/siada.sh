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
    conda create -p /tmp/siada_env_django__django-11422 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_django__django-11422/
    # conda create -p /tmp/siada_env_django__django-11422 python=3.12 -y
    conda activate /tmp/siada_env_django__django-11422
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_django__django-11422.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Autoreloader with StatReloader doesn't track changes in manage.py.
Description
	 
		(last modified by Mariusz Felisiak)
	 
This is a bit convoluted, but here we go.
Environment (OSX 10.11):
$ python -V
Python 3.6.2
$ pip -V
pip 19.1.1
$ pip install Django==2.2.1
Steps to reproduce:
Run a server python manage.py runserver
Edit the manage.py file, e.g. add print(): 
def main():
	print('sth')
	os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ticket_30479.settings')
	...
Under 2.1.8 (and prior), this will trigger the auto-reloading mechanism. Under 2.2.1, it won't. As far as I can tell from the django.utils.autoreload log lines, it never sees the manage.py itself.

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_django__django-11422/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_django__django-11422 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_django__django-11422
    