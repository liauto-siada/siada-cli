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
    conda create -p /tmp/siada_env_scikit-learn__scikit-learn-13496 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_scikit-learn__scikit-learn-13496/
    # conda create -p /tmp/siada_env_scikit-learn__scikit-learn-13496 python=3.12 -y
    conda activate /tmp/siada_env_scikit-learn__scikit-learn-13496
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_scikit-learn__scikit-learn-13496.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Expose warm_start in Isolation forest
It seems to me that `sklearn.ensemble.IsolationForest` supports incremental addition of new trees with the `warm_start` parameter of its parent class, `sklearn.ensemble.BaseBagging`.

Even though this parameter is not exposed in `__init__()` , it gets inherited from `BaseBagging` and one can use it by changing it to `True` after initialization. To make it work, you have to also increment `n_estimators` on every iteration. 

It took me a while to notice that it actually works, and I had to inspect the source code of both `IsolationForest` and `BaseBagging`. Also, it looks to me that the behavior is in-line with `sklearn.ensemble.BaseForest` that is behind e.g. `sklearn.ensemble.RandomForestClassifier`.

To make it more easier to use, I'd suggest to:
* expose `warm_start` in `IsolationForest.__init__()`, default `False`;
* document it in the same way as it is documented for `RandomForestClassifier`, i.e. say:
```py
    warm_start : bool, optional (default=False)
        When set to ``True``, reuse the solution of the previous call to fit
        and add more estimators to the ensemble, otherwise, just fit a whole
        new forest. See :term:`the Glossary <warm_start>`.
```
* add a test to make sure it works properly;
* possibly also mention in the "IsolationForest example" documentation entry;


SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_scikit-learn__scikit-learn-13496/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_scikit-learn__scikit-learn-13496 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_scikit-learn__scikit-learn-13496
    