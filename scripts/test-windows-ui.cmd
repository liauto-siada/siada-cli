@echo off
setlocal
set "siada_test_venv=%USERPROFILE%\.local\share\siada_cli_venv_3.12"
set "SIADA_PYTHON_PATH=%siada_test_venv%\Scripts\python.exe"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONSAFEPATH=1"
"%siada_test_venv%\node\node.exe" "%~dp0..\siada_cli_ui\bundle\siada-ui.js" --use-module-mode --python-path "%SIADA_PYTHON_PATH%" --siada-module "%siada_test_venv%\Lib\site-packages" "%CD%" %*
exit /b %ERRORLEVEL%