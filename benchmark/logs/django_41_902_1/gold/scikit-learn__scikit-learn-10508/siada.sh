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
    conda create -p /tmp/siada_env_scikit-learn__scikit-learn-10508 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_scikit-learn__scikit-learn-10508/
    # conda create -p /tmp/siada_env_scikit-learn__scikit-learn-10508 python=3.12 -y
    conda activate /tmp/siada_env_scikit-learn__scikit-learn-10508
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_scikit-learn__scikit-learn-10508.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
LabelEncoder transform fails for empty lists (for certain inputs)
Python 3.6.3, scikit_learn 0.19.1

Depending on which datatypes were used to fit the LabelEncoder, transforming empty lists works or not. Expected behavior would be that empty arrays are returned in both cases.

```python
>>> from sklearn.preprocessing import LabelEncoder
>>> le = LabelEncoder()
>>> le.fit([1,2])
LabelEncoder()
>>> le.transform([])
array([], dtype=int64)
>>> le.fit(["a","b"])
LabelEncoder()
>>> le.transform([])
Traceback (most recent call last):
  File "[...]\Python36\lib\site-packages\numpy\core\fromnumeric.py", line 57, in _wrapfunc
    return getattr(obj, method)(*args, **kwds)
TypeError: Cannot cast array data from dtype('float64') to dtype('<U32') according to the rule 'safe'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
  File "[...]\Python36\lib\site-packages\sklearn\preprocessing\label.py", line 134, in transform
    return np.searchsorted(self.classes_, y)
  File "[...]\Python36\lib\site-packages\numpy\core\fromnumeric.py", line 1075, in searchsorted
    return _wrapfunc(a, 'searchsorted', v, side=side, sorter=sorter)
  File "[...]\Python36\lib\site-packages\numpy\core\fromnumeric.py", line 67, in _wrapfunc
    return _wrapit(obj, method, *args, **kwds)
  File "[...]\Python36\lib\site-packages\numpy\core\fromnumeric.py", line 47, in _wrapit
    result = getattr(asarray(obj), method)(*args, **kwds)
TypeError: Cannot cast array data from dtype('float64') to dtype('<U32') according to the rule 'safe'
```

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_scikit-learn__scikit-learn-10508/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_scikit-learn__scikit-learn-10508 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_scikit-learn__scikit-learn-10508
    