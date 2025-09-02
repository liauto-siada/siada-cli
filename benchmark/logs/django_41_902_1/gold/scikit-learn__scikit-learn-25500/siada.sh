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
    conda create -p /tmp/siada_env_scikit-learn__scikit-learn-25500 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_scikit-learn__scikit-learn-25500/
    # conda create -p /tmp/siada_env_scikit-learn__scikit-learn-25500 python=3.12 -y
    conda activate /tmp/siada_env_scikit-learn__scikit-learn-25500
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_scikit-learn__scikit-learn-25500.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
CalibratedClassifierCV doesn't work with `set_config(transform_output="pandas")`
### Describe the bug

CalibratedClassifierCV with isotonic regression doesn't work when we previously set `set_config(transform_output="pandas")`.
The IsotonicRegression seems to return a dataframe, which is a problem for `_CalibratedClassifier`  in `predict_proba` where it tries to put the dataframe in a numpy array row `proba[:, class_idx] = calibrator.predict(this_pred)`.

### Steps/Code to Reproduce

```python
import numpy as np
from sklearn import set_config
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import SGDClassifier

set_config(transform_output="pandas")
model = CalibratedClassifierCV(SGDClassifier(), method='isotonic')
model.fit(np.arange(90).reshape(30, -1), np.arange(30) % 2)
model.predict(np.arange(90).reshape(30, -1))
```

### Expected Results

It should not crash.

### Actual Results

```
../core/model_trainer.py:306: in train_model
    cv_predictions = cross_val_predict(pipeline,
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/sklearn/model_selection/_validation.py:968: in cross_val_predict
    predictions = parallel(
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/joblib/parallel.py:1085: in __call__
    if self.dispatch_one_batch(iterator):
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/joblib/parallel.py:901: in dispatch_one_batch
    self._dispatch(tasks)
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/joblib/parallel.py:819: in _dispatch
    job = self._backend.apply_async(batch, callback=cb)
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/joblib/_parallel_backends.py:208: in apply_async
    result = ImmediateResult(func)
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/joblib/_parallel_backends.py:597: in __init__
    self.results = batch()
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/joblib/parallel.py:288: in __call__
    return [func(*args, **kwargs)
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/joblib/parallel.py:288: in <listcomp>
    return [func(*args, **kwargs)
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/sklearn/utils/fixes.py:117: in __call__
    return self.function(*args, **kwargs)
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/sklearn/model_selection/_validation.py:1052: in _fit_and_predict
    predictions = func(X_test)
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/sklearn/pipeline.py:548: in predict_proba
    return self.steps[-1][1].predict_proba(Xt, **predict_proba_params)
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/sklearn/calibration.py:477: in predict_proba
    proba = calibrated_classifier.predict_proba(X)
../../../../.anaconda3/envs/strategy-training/lib/python3.9/site-packages/sklearn/calibration.py:764: in predict_proba
    proba[:, class_idx] = calibrator.predict(this_pred)
E   ValueError: could not broadcast input array from shape (20,1) into shape (20,)
```

### Versions

```shell
System:
    python: 3.9.15 (main, Nov 24 2022, 14:31:59)  [GCC 11.2.0]
executable: /home/philippe/.anaconda3/envs/strategy-training/bin/python
   machine: Linux-5.15.0-57-generic-x86_64-with-glibc2.31

Python dependencies:
      sklearn: 1.2.0
          pip: 22.2.2
   setuptools: 62.3.2
        numpy: 1.23.5
        scipy: 1.9.3
       Cython: None
       pandas: 1.4.1
   matplotlib: 3.6.3
       joblib: 1.2.0
threadpoolctl: 3.1.0

Built with OpenMP: True

threadpoolctl info:
       user_api: openmp
   internal_api: openmp
         prefix: libgomp
       filepath: /home/philippe/.anaconda3/envs/strategy-training/lib/python3.9/site-packages/scikit_learn.libs/libgomp-a34b3233.so.1.0.0
        version: None
    num_threads: 12

       user_api: blas
   internal_api: openblas
         prefix: libopenblas
       filepath: /home/philippe/.anaconda3/envs/strategy-training/lib/python3.9/site-packages/numpy.libs/libopenblas64_p-r0-742d56dc.3.20.so
        version: 0.3.20
threading_layer: pthreads
   architecture: Haswell
    num_threads: 12

       user_api: blas
   internal_api: openblas
         prefix: libopenblas
       filepath: /home/philippe/.anaconda3/envs/strategy-training/lib/python3.9/site-packages/scipy.libs/libopenblasp-r0-41284840.3.18.so
        version: 0.3.18
threading_layer: pthreads
   architecture: Haswell
    num_threads: 12
```


SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_scikit-learn__scikit-learn-25500/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_scikit-learn__scikit-learn-25500 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_scikit-learn__scikit-learn-25500
    