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
    conda create -p /tmp/siada_env_scikit-learn__scikit-learn-14092 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_scikit-learn__scikit-learn-14092/
    # conda create -p /tmp/siada_env_scikit-learn__scikit-learn-14092 python=3.12 -y
    conda activate /tmp/siada_env_scikit-learn__scikit-learn-14092
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_scikit-learn__scikit-learn-14092.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
NCA fails in GridSearch due to too strict parameter checks
NCA checks its parameters to have a specific type, which can easily fail in a GridSearch due to how param grid is made.

Here is an example:
```python
import numpy as np

from sklearn.pipeline import Pipeline
from sklearn.model_selection import GridSearchCV
from sklearn.neighbors import NeighborhoodComponentsAnalysis
from sklearn.neighbors import KNeighborsClassifier

X = np.random.random_sample((100, 10))
y = np.random.randint(2, size=100)

nca = NeighborhoodComponentsAnalysis()
knn = KNeighborsClassifier()

pipe = Pipeline([('nca', nca),
                 ('knn', knn)])
                
params = {'nca__tol': [0.1, 0.5, 1],
          'nca__n_components': np.arange(1, 10)}
          
gs = GridSearchCV(estimator=pipe, param_grid=params, error_score='raise')
gs.fit(X,y)
```

The issue is that for `tol`: 1 is not a float, and for  `n_components`: np.int64 is not int

Before proposing a fix for this specific situation, I'd like to have your general opinion about parameter checking.  
I like this idea of common parameter checking tool introduced with the NCA PR. What do you think about extending it across the code-base (or at least for new or recent estimators) ?

Currently parameter checking is not always done or often partially done, and is quite redundant. For instance, here is the input validation of lda:
```python
def _check_params(self):
        """Check model parameters."""
        if self.n_components <= 0:
            raise ValueError("Invalid 'n_components' parameter: %r"
                             % self.n_components)

        if self.total_samples <= 0:
            raise ValueError("Invalid 'total_samples' parameter: %r"
                             % self.total_samples)

        if self.learning_offset < 0:
            raise ValueError("Invalid 'learning_offset' parameter: %r"
                             % self.learning_offset)

        if self.learning_method not in ("batch", "online"):
            raise ValueError("Invalid 'learning_method' parameter: %r"
                             % self.learning_method)
```
most params aren't checked and for those who are there's a lot of duplicated code.

A propose to be upgrade the new tool to be able to check open/closed intervals (currently only closed) and list membership.

The api would be something like that:
```
check_param(param, name, valid_options)
```
where valid_options would be a dict of `type: constraint`. e.g for the `beta_loss` param of `NMF`, it can be either a float or a string in a list, which would give
```
valid_options = {numbers.Real: None,  # None for no constraint
                 str: ['frobenius', 'kullback-leibler', 'itakura-saito']}
```
Sometimes a parameter can only be positive or within a given interval, e.g. `l1_ratio` of `LogisticRegression` must be between 0 and 1, which would give
```
valid_options = {numbers.Real: Interval(0, 1, closed='both')}
```
positivity of e.g. `max_iter` would be `numbers.Integral: Interval(left=1)`.

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_scikit-learn__scikit-learn-14092/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_scikit-learn__scikit-learn-14092 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_scikit-learn__scikit-learn-14092
    