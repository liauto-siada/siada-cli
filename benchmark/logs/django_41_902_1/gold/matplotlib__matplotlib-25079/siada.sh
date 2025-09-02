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
    conda create -p /tmp/siada_env_matplotlib__matplotlib-25079 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_matplotlib__matplotlib-25079/
    # conda create -p /tmp/siada_env_matplotlib__matplotlib-25079 python=3.12 -y
    conda activate /tmp/siada_env_matplotlib__matplotlib-25079
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_matplotlib__matplotlib-25079.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
[Bug]: Setting norm with existing colorbar fails with 3.6.3
### Bug summary

Setting the norm to a `LogNorm` after the colorbar has been created (e.g. in interactive code) fails with an `Invalid vmin` value in matplotlib 3.6.3.

The same code worked in previous matplotlib versions.

Not that vmin and vmax are explicitly set to values valid for `LogNorm` and no negative values (or values == 0) exist in the input data.

### Code for reproduction

```python
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np

# create some random data to fill a 2d plot
rng = np.random.default_rng(0)
img = rng.uniform(1, 5, (25, 25))

# plot it
fig, ax = plt.subplots(layout="constrained")
plot = ax.pcolormesh(img)
cbar = fig.colorbar(plot, ax=ax)

vmin = 1
vmax = 5

plt.ion()
fig.show()
plt.pause(0.5)

plot.norm = LogNorm(vmin, vmax)
plot.autoscale()
plt.pause(0.5)
```


### Actual outcome

```
Traceback (most recent call last):
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/backends/backend_qt.py", line 454, in _draw_idle
    self.draw()
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/backends/backend_agg.py", line 405, in draw
    self.figure.draw(self.renderer)
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/artist.py", line 74, in draw_wrapper
    result = draw(artist, renderer, *args, **kwargs)
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/artist.py", line 51, in draw_wrapper
    return draw(artist, renderer)
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/figure.py", line 3082, in draw
    mimage._draw_list_compositing_images(
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/image.py", line 131, in _draw_list_compositing_images
    a.draw(renderer)
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/artist.py", line 51, in draw_wrapper
    return draw(artist, renderer)
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/axes/_base.py", line 3100, in draw
    mimage._draw_list_compositing_images(
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/image.py", line 131, in _draw_list_compositing_images
    a.draw(renderer)
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/artist.py", line 51, in draw_wrapper
    return draw(artist, renderer)
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/collections.py", line 2148, in draw
    self.update_scalarmappable()
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/collections.py", line 891, in update_scalarmappable
    self._mapped_colors = self.to_rgba(self._A, self._alpha)
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/cm.py", line 511, in to_rgba
    x = self.norm(x)
  File "/home/mnoethe/.local/conda/envs/cta-dev/lib/python3.9/site-packages/matplotlib/colors.py", line 1694, in __call__
    raise ValueError("Invalid vmin or vmax")
ValueError: Invalid vmin or vmax
```

### Expected outcome

Works, colorbar and mappable are updated with new norm.

### Additional information

_No response_

### Operating system

Linux

### Matplotlib Version

3.6.3 (works with 3.6.2)

### Matplotlib Backend

Multpiple backends tested, same error in all (Qt5Agg, TkAgg, agg, ...)

### Python version

3.9.15

### Jupyter version

not in jupyter

### Installation

conda

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_matplotlib__matplotlib-25079/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_matplotlib__matplotlib-25079 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_matplotlib__matplotlib-25079
    