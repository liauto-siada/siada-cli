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
    conda create -p /tmp/siada_env_matplotlib__matplotlib-25442 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_matplotlib__matplotlib-25442/
    # conda create -p /tmp/siada_env_matplotlib__matplotlib-25442 python=3.12 -y
    conda activate /tmp/siada_env_matplotlib__matplotlib-25442
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_matplotlib__matplotlib-25442.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
[Bug]: Attribute Error combining matplotlib 3.7.1 and mplcursor on data selection
### Bug summary

If you combine mplcursor and matplotlib 3.7.1, you'll get an `AttributeError: 'NoneType' object has no attribute 'canvas'` after clicking a few data points. Henceforth, selecting a new data point will trigger the same traceback. Otherwise, it works fine. 

### Code for reproduction

```python
import numpy as np
import matplotlib.pyplot as plt
import mplcursors as mpl

x = np.arange(1, 11)    
y1 = x

plt.scatter(x,y1)

mpl.cursor()
plt.show()
```


### Actual outcome

```
Traceback (most recent call last):
  File "C:\Users\MrAni\Python\miniconda3\lib\site-packages\matplotlib\cbook\__init__.py", line 304, in process
    func(*args, **kwargs)
  File "C:\Users\MrAni\Python\miniconda3\lib\site-packages\matplotlib\offsetbox.py", line 1550, in on_release
    if self._check_still_parented() and self.got_artist:
  File "C:\Users\MrAni\Python\miniconda3\lib\site-packages\matplotlib\offsetbox.py", line 1560, in _check_still_parented
    self.disconnect()
  File "C:\Users\MrAni\Python\miniconda3\lib\site-packages\matplotlib\offsetbox.py", line 1568, in disconnect
    self.canvas.mpl_disconnect(cid)
  File "C:\Users\MrAni\Python\miniconda3\lib\site-packages\matplotlib\offsetbox.py", line 1517, in <lambda>
    canvas = property(lambda self: self.ref_artist.figure.canvas)
AttributeError: 'NoneType' object has no attribute 'canvas'
```

### Expected outcome

No terminal output

### Additional information

Using matplotlib 3.7.0 or lower works fine. Using a conda install or pip install doesn't affect the output. 

### Operating system

Windows 11 and Windwos 10 

### Matplotlib Version

3.7.1

### Matplotlib Backend

QtAgg

### Python version

3.9.16

### Jupyter version

_No response_

### Installation

conda

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_matplotlib__matplotlib-25442/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_matplotlib__matplotlib-25442 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_matplotlib__matplotlib-25442
    