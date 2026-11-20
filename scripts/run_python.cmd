@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHONHOME="
set "PYTHONPATH="
set "MAKER_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if not exist "%MAKER_PYTHON%" (
    echo Python environment missing. Run the setup CMD in "%~dp0.." first.
    exit /b 1
)
"%MAKER_PYTHON%" %*
exit /b %errorlevel%
