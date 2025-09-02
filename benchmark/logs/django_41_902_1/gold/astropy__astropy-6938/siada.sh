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
    conda create -p /tmp/siada_env_astropy__astropy-6938 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_astropy__astropy-6938/
    # conda create -p /tmp/siada_env_astropy__astropy-6938 python=3.12 -y
    conda activate /tmp/siada_env_astropy__astropy-6938
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_astropy__astropy-6938.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Possible bug in io.fits related to D exponents
I came across the following code in ``fitsrec.py``:

```python
        # Replace exponent separator in floating point numbers
        if 'D' in format:
            output_field.replace(encode_ascii('E'), encode_ascii('D'))
```

I think this may be incorrect because as far as I can tell ``replace`` is not an in-place operation for ``chararray`` (it returns a copy). Commenting out this code doesn't cause any tests to fail so I think this code isn't being tested anyway.

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_astropy__astropy-6938/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_astropy__astropy-6938 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_astropy__astropy-6938
    