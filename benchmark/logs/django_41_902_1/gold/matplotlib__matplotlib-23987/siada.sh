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
    conda create -p /tmp/siada_env_matplotlib__matplotlib-23987 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_matplotlib__matplotlib-23987/
    # conda create -p /tmp/siada_env_matplotlib__matplotlib-23987 python=3.12 -y
    conda activate /tmp/siada_env_matplotlib__matplotlib-23987
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_matplotlib__matplotlib-23987.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
[Bug]: Constrained layout UserWarning even when False
### Bug summary

When using layout settings such as `plt.subplots_adjust` or `bbox_inches='tight`, a UserWarning is produced due to incompatibility with constrained_layout, even if constrained_layout = False. This was not the case in previous versions.

### Code for reproduction

```python
import matplotlib.pyplot as plt
import numpy as np
a = np.linspace(0,2*np.pi,100)
b = np.sin(a)
c = np.cos(a)
fig,ax = plt.subplots(1,2,figsize=(8,2),constrained_layout=False)
ax[0].plot(a,b)
ax[1].plot(a,c)
plt.subplots_adjust(wspace=0)
```


### Actual outcome

The plot works fine but the warning is generated

`/var/folders/ss/pfgdfm2x7_s4cyw2v0b_t7q80000gn/T/ipykernel_76923/4170965423.py:7: UserWarning: This figure was using a layout engine that is incompatible with subplots_adjust and/or tight_layout; not calling subplots_adjust.
  plt.subplots_adjust(wspace=0)`

### Expected outcome

no warning

### Additional information

Warning disappears when constrained_layout=False is removed

### Operating system

OS/X

### Matplotlib Version

3.6.0

### Matplotlib Backend

_No response_

### Python version

_No response_

### Jupyter version

_No response_

### Installation

conda

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_matplotlib__matplotlib-23987/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_matplotlib__matplotlib-23987 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_matplotlib__matplotlib-23987
    