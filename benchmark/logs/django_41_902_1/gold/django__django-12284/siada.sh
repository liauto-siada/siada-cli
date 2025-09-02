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
    conda create -p /tmp/siada_env_django__django-12284 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_django__django-12284/
    # conda create -p /tmp/siada_env_django__django-12284 python=3.12 -y
    conda activate /tmp/siada_env_django__django-12284
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_django__django-12284.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Model.get_FOO_display() does not work correctly with inherited choices.
Description
	 
		(last modified by Mariusz Felisiak)
	 
Given a base model with choices A containing 3 tuples
Child Model inherits the base model overrides the choices A and adds 2 more tuples
get_foo_display does not work correctly for the new tuples added
Example:
class A(models.Model):
 foo_choice = [("A","output1"),("B","output2")]
 field_foo = models.CharField(max_length=254,choices=foo_choice)
 class Meta:
	 abstract = True
class B(A):
 foo_choice = [("A","output1"),("B","output2"),("C","output3")]
 field_foo = models.CharField(max_length=254,choices=foo_choice)
Upon invoking get_field_foo_display() on instance of B , 
For value "A" and "B" the output works correctly i.e. returns "output1" / "output2"
but for value "C" the method returns "C" and not "output3" which is the expected behaviour

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_django__django-12284/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_django__django-12284 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_django__django-12284
    