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
    conda create -p /tmp/siada_env_scikit-learn__scikit-learn-12471 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_scikit-learn__scikit-learn-12471/
    # conda create -p /tmp/siada_env_scikit-learn__scikit-learn-12471 python=3.12 -y
    conda activate /tmp/siada_env_scikit-learn__scikit-learn-12471
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_scikit-learn__scikit-learn-12471.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
OneHotEncoder ignore unknown error when categories are strings 
#### Description

This bug is very specific, but it happens when you set OneHotEncoder to ignore unknown entries.
and your labels are strings. The memory of the arrays is not handled safely and it can lead to a ValueError

Basically, when you call the transform method it will sets all the unknown strings on your array to OneHotEncoder.categories_[i][0] which is the first category alphabetically sorted given for fit
If this OneHotEncoder.categories_[i][0] is a long string, and the array that you want to transform has small strings, then it is impossible to fit the whole  OneHotEncoder.categories_[i][0] into the entries of the array we want to transform. So  OneHotEncoder.categories_[i][0]  is truncated and this raise the ValueError.



#### Steps/Code to Reproduce
```

import numpy as np
from sklearn.preprocessing import OneHotEncoder


# It needs to be numpy arrays, the error does not appear 
# is you have lists of lists because it gets treated like an array of objects.
train  = np.array([ '22','333','4444','11111111' ]).reshape((-1,1))
test   = np.array([ '55555',  '22' ]).reshape((-1,1))

ohe = OneHotEncoder(dtype=bool,handle_unknown='ignore')

ohe.fit( train )
enc_test = ohe.transform( test )

```


#### Expected Results
Here we should get an sparse matrix 2x4 false everywhere except at (1,1) the '22' that is known

#### Actual Results

> ValueError: y contains previously unseen labels: ['111111']


#### Versions
System:
    python: 2.7.12 (default, Dec  4 2017, 14:50:18)  [GCC 5.4.0 20160609]
   machine: Linux-4.4.0-138-generic-x86_64-with-Ubuntu-16.04-xenial
executable: /usr/bin/python

BLAS:
    macros: HAVE_CBLAS=None
cblas_libs: openblas, openblas
  lib_dirs: /usr/lib

Python deps:
    Cython: 0.25.2
     scipy: 0.18.1
setuptools: 36.7.0
       pip: 9.0.1
     numpy: 1.15.2
    pandas: 0.19.1
   sklearn: 0.21.dev0



#### Comments

I already implemented a fix for this issue, where I check the size of the elements in the array before, and I cast them into objects if necessary.

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_scikit-learn__scikit-learn-12471/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_scikit-learn__scikit-learn-12471 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_scikit-learn__scikit-learn-12471
    