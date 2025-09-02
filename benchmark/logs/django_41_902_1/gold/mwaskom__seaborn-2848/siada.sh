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
    conda create -p /tmp/siada_env_mwaskom__seaborn-2848 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_mwaskom__seaborn-2848/
    # conda create -p /tmp/siada_env_mwaskom__seaborn-2848 python=3.12 -y
    conda activate /tmp/siada_env_mwaskom__seaborn-2848
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_mwaskom__seaborn-2848.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
pairplot fails with hue_order not containing all hue values in seaborn 0.11.1
In seaborn < 0.11, one could plot only a subset of the values in the hue column, by passing a hue_order list containing only the desired values. Points with hue values not in the list were simply not plotted.
```python
iris = sns.load_dataset("iris")`
# The hue column contains three different species; here we want to plot two
sns.pairplot(iris, hue="species", hue_order=["setosa", "versicolor"])
```

This no longer works in 0.11.1. Passing a hue_order list that does not contain some of the values in the hue column raises a long, ugly error traceback. The first exception arises in seaborn/_core.py:
```
TypeError: ufunc 'isnan' not supported for the input types, and the inputs could not be safely coerced to any supported types according to the casting rule ''safe''
```
seaborn version: 0.11.1
matplotlib version: 3.3.2
matplotlib backends: MacOSX, Agg or jupyter notebook inline.
SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_mwaskom__seaborn-2848/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_mwaskom__seaborn-2848 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_mwaskom__seaborn-2848
    