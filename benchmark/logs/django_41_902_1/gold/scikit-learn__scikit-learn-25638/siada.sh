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
    conda create -p /tmp/siada_env_scikit-learn__scikit-learn-25638 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_scikit-learn__scikit-learn-25638/
    # conda create -p /tmp/siada_env_scikit-learn__scikit-learn-25638 python=3.12 -y
    conda activate /tmp/siada_env_scikit-learn__scikit-learn-25638
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_scikit-learn__scikit-learn-25638.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Support nullable pandas dtypes in `unique_labels`
### Describe the workflow you want to enable

I would like to be able to pass the nullable pandas dtypes ("Int64", "Float64", "boolean") into sklearn's `unique_labels` function. Because the dtypes become `object` dtype when converted to numpy arrays we get `ValueError: Mix type of y not allowed, got types {'binary', 'unknown'}`:

Repro with sklearn 1.2.1
```py 
    import pandas as pd
    import pytest
    from sklearn.utils.multiclass import unique_labels
    
    for dtype in ["Int64", "Float64", "boolean"]:
        y_true = pd.Series([1, 0, 0, 1, 0, 1, 1, 0, 1], dtype=dtype)
        y_predicted = pd.Series([0, 0, 1, 1, 0, 1, 1, 1, 1], dtype="int64")

        with pytest.raises(ValueError, match="Mix type of y not allowed, got types"):
            unique_labels(y_true, y_predicted)
```

### Describe your proposed solution

We should get the same behavior as when `int64`, `float64`, and `bool` dtypes are used, which is no error:  

```python
    import pandas as pd
    from sklearn.utils.multiclass import unique_labels
    
    for dtype in ["int64", "float64", "bool"]:
        y_true = pd.Series([1, 0, 0, 1, 0, 1, 1, 0, 1], dtype=dtype)
        y_predicted = pd.Series([0, 0, 1, 1, 0, 1, 1, 1, 1], dtype="int64")

        unique_labels(y_true, y_predicted)
```

### Describe alternatives you've considered, if relevant

Our current workaround is to convert the data to numpy arrays with the corresponding dtype that works prior to passing it into `unique_labels`.

### Additional context

_No response_

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_scikit-learn__scikit-learn-25638/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_scikit-learn__scikit-learn-25638 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_scikit-learn__scikit-learn-25638
    