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
    conda create -p /tmp/siada_env_matplotlib__matplotlib-26011 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_matplotlib__matplotlib-26011/
    # conda create -p /tmp/siada_env_matplotlib__matplotlib-26011 python=3.12 -y
    conda activate /tmp/siada_env_matplotlib__matplotlib-26011
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_matplotlib__matplotlib-26011.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
xlim_changed not emitted on shared axis
<!--To help us understand and resolve your issue, please fill out the form to the best of your ability.-->
<!--You can feel free to delete the sections that do not apply.-->

### Bug report

**Bug summary**

When an axis is shared with another its registered "xlim_changed" callbacks does not get called when the change is induced by a shared axis (via sharex=). 

In _base.py the set_xlim for sibling axis are called with emit=False:

```
matplotlib/lib/matplotlib/axes/_base.py:

/.../
def set_xlim(...)
/.../
        if emit:
            self.callbacks.process('xlim_changed', self)
            # Call all of the other x-axes that are shared with this one
            for other in self._shared_x_axes.get_siblings(self):
                if other is not self:
                    other.set_xlim(self.viewLim.intervalx,
                                   emit=False, auto=auto)
```

I'm very new to matplotlib, so perhaps there is a good reason for this? emit=False seems to disable both continued "inheritance" of axis (why?) and triggering of change callbacks (looking at the code above).

It seems like one would at least want to trigger the xlim_changed callbacks as they would be intended to react to any change in axis limits.

Edit: Setting emit=True seems to introduce a recursion issue (not sure why but as inheritance seems to be passed along anyway it doesn't really matter). Moving the callback call to outside of the "if emit:"-statement seems to solve the issue as far as I can see when trying it out. Any reason to keep it inside the if-statement? 


SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_matplotlib__matplotlib-26011/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_matplotlib__matplotlib-26011 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_matplotlib__matplotlib-26011
    