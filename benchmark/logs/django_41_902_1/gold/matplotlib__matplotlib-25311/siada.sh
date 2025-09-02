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
    conda create -p /tmp/siada_env_matplotlib__matplotlib-25311 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_matplotlib__matplotlib-25311/
    # conda create -p /tmp/siada_env_matplotlib__matplotlib-25311 python=3.12 -y
    conda activate /tmp/siada_env_matplotlib__matplotlib-25311
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_matplotlib__matplotlib-25311.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
[Bug]: Unable to pickle figure with draggable legend
### Bug summary

I am unable to pickle figure with draggable legend. Same error comes for draggable annotations.





### Code for reproduction

```python
import matplotlib.pyplot as plt
import pickle

fig = plt.figure()
ax = fig.add_subplot(111)

time=[0,1,2,3,4]
speed=[40,43,45,47,48]

ax.plot(time,speed,label="speed")

leg=ax.legend()
leg.set_draggable(True) #pickling works after removing this line 

pickle.dumps(fig)
plt.show()
```


### Actual outcome

`TypeError: cannot pickle 'FigureCanvasQTAgg' object`

### Expected outcome

Pickling successful

### Additional information

_No response_

### Operating system

Windows 10

### Matplotlib Version

3.7.0

### Matplotlib Backend

_No response_

### Python version

3.10

### Jupyter version

_No response_

### Installation

pip

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_matplotlib__matplotlib-25311/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_matplotlib__matplotlib-25311 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_matplotlib__matplotlib-25311
    