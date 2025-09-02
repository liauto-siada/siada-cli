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
    conda create -p /tmp/siada_env_matplotlib__matplotlib-23562 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_matplotlib__matplotlib-23562/
    # conda create -p /tmp/siada_env_matplotlib__matplotlib-23562 python=3.12 -y
    conda activate /tmp/siada_env_matplotlib__matplotlib-23562
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_matplotlib__matplotlib-23562.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
'Poly3DCollection' object has no attribute '_facecolors2d'
The following minimal example demonstrates the issue:

```
import numpy as np
import matplotlib.tri as mtri
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

y,x = np.ogrid[1:10:100j, 1:10:100j]
z2 = np.cos(x)**3 - np.sin(y)**2
fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')
r = ax.plot_surface(x,y,z2, cmap='hot')
r.get_facecolors()
```

It fails on the last line with the following traceback:

```
AttributeError                            Traceback (most recent call last)
<ipython-input-13-de0f41d662cd> in <module>()
----> 1 r.get_facecolors()

/home/oliver/.virtualenvs/mpl/local/lib/python2.7/site-packages/mpl_toolkits/mplot3d/art3d.pyc in get_facecolors(self)
    634
    635     def get_facecolors(self):
--> 636         return self._facecolors2d
    637     get_facecolor = get_facecolors
    638

AttributeError: 'Poly3DCollection' object has no attribute '_facecolors2d'
```

Tested with mpl versions 1.3.1 and 1.4.2.

Sent here by Benjamin, from the mpl users mailing list (mail with the same title). Sorry for dumping this without more assistance, I'm not yet at a python level where I can help in debugging, I think (well, it seems daunting).


SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_matplotlib__matplotlib-23562/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_matplotlib__matplotlib-23562 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_matplotlib__matplotlib-23562
    