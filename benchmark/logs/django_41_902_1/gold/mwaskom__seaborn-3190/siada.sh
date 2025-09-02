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
    conda create -p /tmp/siada_env_mwaskom__seaborn-3190 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_mwaskom__seaborn-3190/
    # conda create -p /tmp/siada_env_mwaskom__seaborn-3190 python=3.12 -y
    conda activate /tmp/siada_env_mwaskom__seaborn-3190
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_mwaskom__seaborn-3190.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Color mapping fails with boolean data
```python
so.Plot(["a", "b"], [1, 2], color=[True, False]).add(so.Bar())
```
```python-traceback
---------------------------------------------------------------------------
TypeError                                 Traceback (most recent call last)
...
File ~/code/seaborn/seaborn/_core/plot.py:841, in Plot._plot(self, pyplot)
    838 plotter._compute_stats(self, layers)
    840 # Process scale spec for semantic variables and coordinates computed by stat
--> 841 plotter._setup_scales(self, common, layers)
    843 # TODO Remove these after updating other methods
    844 # ---- Maybe have debug= param that attaches these when True?
    845 plotter._data = common

File ~/code/seaborn/seaborn/_core/plot.py:1252, in Plotter._setup_scales(self, p, common, layers, variables)
   1250     self._scales[var] = Scale._identity()
   1251 else:
-> 1252     self._scales[var] = scale._setup(var_df[var], prop)
   1254 # Everything below here applies only to coordinate variables
   1255 # We additionally skip it when we're working with a value
   1256 # that is derived from a coordinate we've already processed.
   1257 # e.g., the Stat consumed y and added ymin/ymax. In that case,
   1258 # we've already setup the y scale and ymin/max are in scale space.
   1259 if axis is None or (var != coord and coord in p._variables):

File ~/code/seaborn/seaborn/_core/scales.py:351, in ContinuousBase._setup(self, data, prop, axis)
    349 vmin, vmax = axis.convert_units((vmin, vmax))
    350 a = forward(vmin)
--> 351 b = forward(vmax) - forward(vmin)
    353 def normalize(x):
    354     return (x - a) / b

TypeError: numpy boolean subtract, the `-` operator, is not supported, use the bitwise_xor, the `^` operator, or the logical_xor function instead.
```

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_mwaskom__seaborn-3190/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_mwaskom__seaborn-3190 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_mwaskom__seaborn-3190
    