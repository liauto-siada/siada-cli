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
    conda create -p /tmp/siada_env_scikit-learn__scikit-learn-11040 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_scikit-learn__scikit-learn-11040/
    # conda create -p /tmp/siada_env_scikit-learn__scikit-learn-11040 python=3.12 -y
    conda activate /tmp/siada_env_scikit-learn__scikit-learn-11040
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_scikit-learn__scikit-learn-11040.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Missing parameter validation in Neighbors estimator for float n_neighbors
```python
from sklearn.neighbors import NearestNeighbors
from sklearn.datasets import make_blobs
X, y = make_blobs()
neighbors = NearestNeighbors(n_neighbors=3.)
neighbors.fit(X)
neighbors.kneighbors(X)
```
```
~/checkout/scikit-learn/sklearn/neighbors/binary_tree.pxi in sklearn.neighbors.kd_tree.NeighborsHeap.__init__()

TypeError: 'float' object cannot be interpreted as an integer
```
This should be caught earlier and a more helpful error message should be raised (or we could be lenient and cast to integer, but I think a better error might be better).

We need to make sure that 
```python
neighbors.kneighbors(X, n_neighbors=3.)
```
also works.

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_scikit-learn__scikit-learn-11040/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_scikit-learn__scikit-learn-11040 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_scikit-learn__scikit-learn-11040
    