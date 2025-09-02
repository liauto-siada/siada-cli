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
    conda create -p /tmp/siada_env_scikit-learn__scikit-learn-15512 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_scikit-learn__scikit-learn-15512/
    # conda create -p /tmp/siada_env_scikit-learn__scikit-learn-15512 python=3.12 -y
    conda activate /tmp/siada_env_scikit-learn__scikit-learn-15512
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_scikit-learn__scikit-learn-15512.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Return values of non converged affinity propagation clustering
The affinity propagation Documentation states: 
"When the algorithm does not converge, it returns an empty array as cluster_center_indices and -1 as label for each training sample."

Example:
```python
from sklearn.cluster import AffinityPropagation
import pandas as pd

data = pd.DataFrame([[1,0,0,0,0,0],[0,1,1,1,0,0],[0,0,1,0,0,1]])
af = AffinityPropagation(affinity='euclidean', verbose=True, copy=False, max_iter=2).fit(data)

print(af.cluster_centers_indices_)
print(af.labels_)

```
I would expect that the clustering here (which does not converge) prints first an empty List and then [-1,-1,-1], however, I get [2] as cluster center and [0,0,0] as cluster labels. 
The only way I currently know if the clustering fails is if I use the verbose option, however that is very unhandy. A hacky solution is to check if max_iter == n_iter_ but it could have converged exactly 15 iterations before max_iter (although unlikely).
I am not sure if this is intended behavior and the documentation is wrong?

For my use-case within a bigger script, I would prefer to get back -1 values or have a property to check if it has converged, as otherwise, a user might not be aware that the clustering never converged.


#### Versions
System:
    python: 3.6.7 | packaged by conda-forge | (default, Nov 21 2018, 02:32:25)  [GCC 4.8.2 20140120 (Red Hat 4.8.2-15)]
executable: /home/jenniferh/Programs/anaconda3/envs/TF_RDKit_1_19/bin/python
   machine: Linux-4.15.0-52-generic-x86_64-with-debian-stretch-sid
BLAS:
    macros: SCIPY_MKL_H=None, HAVE_CBLAS=None
  lib_dirs: /home/jenniferh/Programs/anaconda3/envs/TF_RDKit_1_19/lib
cblas_libs: mkl_rt, pthread
Python deps:
    pip: 18.1
   setuptools: 40.6.3
   sklearn: 0.20.3
   numpy: 1.15.4
   scipy: 1.2.0
   Cython: 0.29.2
   pandas: 0.23.4



SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_scikit-learn__scikit-learn-15512/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_scikit-learn__scikit-learn-15512 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_scikit-learn__scikit-learn-15512
    