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
    conda create -p /tmp/siada_env_pylint-dev__pylint-7993 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_pylint-dev__pylint-7993/
    # conda create -p /tmp/siada_env_pylint-dev__pylint-7993 python=3.12 -y
    conda activate /tmp/siada_env_pylint-dev__pylint-7993
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_pylint-dev__pylint-7993.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Using custom braces in message template does not work
### Bug description

Have any list of errors:

On pylint 1.7 w/ python3.6 - I am able to use this as my message template
```
$ pylint test.py --msg-template='{{ "Category": "{category}" }}'
No config file found, using default configuration
************* Module [redacted].test
{ "Category": "convention" }
{ "Category": "error" }
{ "Category": "error" }
{ "Category": "convention" }
{ "Category": "convention" }
{ "Category": "convention" }
{ "Category": "error" }
```

However, on Python3.9 with Pylint 2.12.2, I get the following:
```
$ pylint test.py --msg-template='{{ "Category": "{category}" }}'
[redacted]/site-packages/pylint/reporters/text.py:206: UserWarning: Don't recognize the argument '{ "Category"' in the --msg-template. Are you sure it is supported on the current version of pylint?
  warnings.warn(
************* Module [redacted].test
" }
" }
" }
" }
" }
" }
```

Is this intentional or a bug?

### Configuration

_No response_

### Command used

```shell
pylint test.py --msg-template='{{ "Category": "{category}" }}'
```


### Pylint output

```shell
[redacted]/site-packages/pylint/reporters/text.py:206: UserWarning: Don't recognize the argument '{ "Category"' in the --msg-template. Are you sure it is supported on the current version of pylint?
  warnings.warn(
************* Module [redacted].test
" }
" }
" }
" }
" }
" }
```


### Expected behavior

Expect the dictionary to print out with `"Category"` as the key.

### Pylint version

```shell
Affected Version:
pylint 2.12.2
astroid 2.9.2
Python 3.9.9+ (heads/3.9-dirty:a2295a4, Dec 21 2021, 22:32:52) 
[GCC 4.8.5 20150623 (Red Hat 4.8.5-44)]


Previously working version:
No config file found, using default configuration
pylint 1.7.4, 
astroid 1.6.6
Python 3.6.8 (default, Nov 16 2020, 16:55:22) 
[GCC 4.8.5 20150623 (Red Hat 4.8.5-44)]
```


### OS / Environment

_No response_

### Additional dependencies

_No response_

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_pylint-dev__pylint-7993/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_pylint-dev__pylint-7993 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_pylint-dev__pylint-7993
    