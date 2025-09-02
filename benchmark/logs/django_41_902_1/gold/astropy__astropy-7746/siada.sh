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
    conda create -p /tmp/siada_env_astropy__astropy-7746 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_astropy__astropy-7746/
    # conda create -p /tmp/siada_env_astropy__astropy-7746 python=3.12 -y
    conda activate /tmp/siada_env_astropy__astropy-7746
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_astropy__astropy-7746.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Issue when passing empty lists/arrays to WCS transformations
The following should not fail but instead should return empty lists/arrays:

```
In [1]: from astropy.wcs import WCS

In [2]: wcs = WCS('2MASS_h.fits')

In [3]: wcs.wcs_pix2world([], [], 0)
---------------------------------------------------------------------------
InconsistentAxisTypesError                Traceback (most recent call last)
<ipython-input-3-e2cc0e97941a> in <module>()
----> 1 wcs.wcs_pix2world([], [], 0)

~/Dropbox/Code/Astropy/astropy/astropy/wcs/wcs.py in wcs_pix2world(self, *args, **kwargs)
   1352         return self._array_converter(
   1353             lambda xy, o: self.wcs.p2s(xy, o)['world'],
-> 1354             'output', *args, **kwargs)
   1355     wcs_pix2world.__doc__ = """
   1356         Transforms pixel coordinates to world coordinates by doing

~/Dropbox/Code/Astropy/astropy/astropy/wcs/wcs.py in _array_converter(self, func, sky, ra_dec_order, *args)
   1267                     "a 1-D array for each axis, followed by an origin.")
   1268 
-> 1269             return _return_list_of_arrays(axes, origin)
   1270 
   1271         raise TypeError(

~/Dropbox/Code/Astropy/astropy/astropy/wcs/wcs.py in _return_list_of_arrays(axes, origin)
   1223             if ra_dec_order and sky == 'input':
   1224                 xy = self._denormalize_sky(xy)
-> 1225             output = func(xy, origin)
   1226             if ra_dec_order and sky == 'output':
   1227                 output = self._normalize_sky(output)

~/Dropbox/Code/Astropy/astropy/astropy/wcs/wcs.py in <lambda>(xy, o)
   1351             raise ValueError("No basic WCS settings were created.")
   1352         return self._array_converter(
-> 1353             lambda xy, o: self.wcs.p2s(xy, o)['world'],
   1354             'output', *args, **kwargs)
   1355     wcs_pix2world.__doc__ = """

InconsistentAxisTypesError: ERROR 4 in wcsp2s() at line 2646 of file cextern/wcslib/C/wcs.c:
ncoord and/or nelem inconsistent with the wcsprm.
```

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_astropy__astropy-7746/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_astropy__astropy-7746 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_astropy__astropy-7746
    