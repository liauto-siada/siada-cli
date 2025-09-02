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
    conda create -p /tmp/siada_env_matplotlib__matplotlib-24265 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_matplotlib__matplotlib-24265/
    # conda create -p /tmp/siada_env_matplotlib__matplotlib-24265 python=3.12 -y
    conda activate /tmp/siada_env_matplotlib__matplotlib-24265
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_matplotlib__matplotlib-24265.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
[Bug]: Setting matplotlib.pyplot.style.library['seaborn-colorblind'] result in key error on matplotlib v3.6.1
### Bug summary

I have code that executes:
```
import matplotlib.pyplot as plt
the_rc = plt.style.library["seaborn-colorblind"]
```

Using version 3.4.3 of matplotlib, this works fine. I recently installed my code on a machine with matplotlib version 3.6.1 and upon importing my code, this generated a key error for line `the_rc = plt.style.library["seaborn-colorblind"]` saying "seaborn-colorblind" was a bad key.

### Code for reproduction

```python
import matplotlib.pyplot as plt
the_rc = plt.style.library["seaborn-colorblind"]
```


### Actual outcome

Traceback (most recent call last):
KeyError: 'seaborn-colorblind'

### Expected outcome

seaborn-colorblind should be set as the matplotlib library style and I should be able to continue plotting with that style.

### Additional information

- Bug occurs with matplotlib version 3.6.1
- Bug does not occur with matplotlib version 3.4.3
- Tested on MacOSX and Ubuntu (same behavior on both)

### Operating system

OS/X

### Matplotlib Version

3.6.1

### Matplotlib Backend

MacOSX

### Python version

3.9.7

### Jupyter version

_No response_

### Installation

pip

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_matplotlib__matplotlib-24265/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_matplotlib__matplotlib-24265 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_matplotlib__matplotlib-24265
    