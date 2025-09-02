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
    conda create -p /tmp/siada_env_scikit-learn__scikit-learn-10949 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_scikit-learn__scikit-learn-10949/
    # conda create -p /tmp/siada_env_scikit-learn__scikit-learn-10949 python=3.12 -y
    conda activate /tmp/siada_env_scikit-learn__scikit-learn-10949
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_scikit-learn__scikit-learn-10949.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
warn_on_dtype with DataFrame
#### Description

``warn_on_dtype`` has no effect when input is a pandas ``DataFrame``

#### Steps/Code to Reproduce
```python
from sklearn.utils.validation import check_array
import pandas as pd
df = pd.DataFrame([[1, 2, 3], [2, 3, 4]], dtype=object)
checked = check_array(df, warn_on_dtype=True)
```

#### Expected result: 

```python-traceback
DataConversionWarning: Data with input dtype object was converted to float64.
```

#### Actual Results
No warning is thrown

#### Versions
Linux-4.4.0-116-generic-x86_64-with-debian-stretch-sid
Python 3.6.3 |Anaconda, Inc.| (default, Nov  3 2017, 19:19:16) 
[GCC 7.2.0]
NumPy 1.13.1
SciPy 0.19.1
Scikit-Learn 0.20.dev0
Pandas 0.21.0

warn_on_dtype with DataFrame
#### Description

``warn_on_dtype`` has no effect when input is a pandas ``DataFrame``

#### Steps/Code to Reproduce
```python
from sklearn.utils.validation import check_array
import pandas as pd
df = pd.DataFrame([[1, 2, 3], [2, 3, 4]], dtype=object)
checked = check_array(df, warn_on_dtype=True)
```

#### Expected result: 

```python-traceback
DataConversionWarning: Data with input dtype object was converted to float64.
```

#### Actual Results
No warning is thrown

#### Versions
Linux-4.4.0-116-generic-x86_64-with-debian-stretch-sid
Python 3.6.3 |Anaconda, Inc.| (default, Nov  3 2017, 19:19:16) 
[GCC 7.2.0]
NumPy 1.13.1
SciPy 0.19.1
Scikit-Learn 0.20.dev0
Pandas 0.21.0


SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_scikit-learn__scikit-learn-10949/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_scikit-learn__scikit-learn-10949 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_scikit-learn__scikit-learn-10949
    