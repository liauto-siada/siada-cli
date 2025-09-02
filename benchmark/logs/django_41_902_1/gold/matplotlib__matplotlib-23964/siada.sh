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
    conda create -p /tmp/siada_env_matplotlib__matplotlib-23964 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_matplotlib__matplotlib-23964/
    # conda create -p /tmp/siada_env_matplotlib__matplotlib-23964 python=3.12 -y
    conda activate /tmp/siada_env_matplotlib__matplotlib-23964
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_matplotlib__matplotlib-23964.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
[Bug]: Text label with empty line causes a "TypeError: cannot unpack non-iterable NoneType object" in PostScript backend
### Bug summary

When saving a figure with the PostScript backend, a
> TypeError: cannot unpack non-iterable NoneType object

happens if the figure contains a multi-line text label with an empty line (see example).

### Code for reproduction

```python
from matplotlib.figure import Figure

figure = Figure()
ax = figure.add_subplot(111)
# ax.set_title('\nLower title')  # this would cause an error as well
ax.annotate(text='\nLower label', xy=(0, 0))
figure.savefig('figure.eps')
```


### Actual outcome

$ ./venv/Scripts/python save_ps.py
Traceback (most recent call last):
  File "C:\temp\matplotlib_save_ps\save_ps.py", line 7, in <module>
    figure.savefig('figure.eps')
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\figure.py", line 3272, in savefig
    self.canvas.print_figure(fname, **kwargs)
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\backend_bases.py", line 2338, in print_figure
    result = print_method(
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\backend_bases.py", line 2204, in <lambda>
    print_method = functools.wraps(meth)(lambda *args, **kwargs: meth(
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\_api\deprecation.py", line 410, in wrapper
    return func(*inner_args, **inner_kwargs)
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\backends\backend_ps.py", line 869, in _print_ps
    printer(fmt, outfile, dpi=dpi, dsc_comments=dsc_comments,
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\backends\backend_ps.py", line 927, in _print_figure
    self.figure.draw(renderer)
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\artist.py", line 74, in draw_wrapper
    result = draw(artist, renderer, *args, **kwargs)
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\artist.py", line 51, in draw_wrapper
    return draw(artist, renderer)
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\figure.py", line 3069, in draw
    mimage._draw_list_compositing_images(
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\image.py", line 131, in _draw_list_compositing_images
    a.draw(renderer)
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\artist.py", line 51, in draw_wrapper
    return draw(artist, renderer)
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\axes\_base.py", line 3106, in draw
    mimage._draw_list_compositing_images(
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\image.py", line 131, in _draw_list_compositing_images
    a.draw(renderer)
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\artist.py", line 51, in draw_wrapper
    return draw(artist, renderer)
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\text.py", line 1995, in draw
    Text.draw(self, renderer)
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\artist.py", line 51, in draw_wrapper
    return draw(artist, renderer)
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\text.py", line 736, in draw
    textrenderer.draw_text(gc, x, y, clean_line,
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\backends\backend_ps.py", line 248, in wrapper
    return meth(self, *args, **kwargs)
  File "C:\temp\matplotlib_save_ps\venv\lib\site-packages\matplotlib\backends\backend_ps.py", line 673, in draw_text
    for ps_name, xs_names in stream:
TypeError: cannot unpack non-iterable NoneType object


### Expected outcome

The figure can be saved as `figure.eps` without error.

### Additional information

- seems to happen if a text label or title contains a linebreak with an empty line
- works without error for other backends such as PNG, PDF, SVG, Qt
- works with matplotlib<=3.5.3
- adding `if curr_stream:` before line 669 of `backend_ps.py` seems to fix the bug 

### Operating system

Windows

### Matplotlib Version

3.6.0

### Matplotlib Backend

_No response_

### Python version

3.9.13

### Jupyter version

_No response_

### Installation

pip

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_matplotlib__matplotlib-23964/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_matplotlib__matplotlib-23964 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_matplotlib__matplotlib-23964
    