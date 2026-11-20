@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONHOME="
set "PYTHONPATH="
set "MAKER_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%MAKER_PYTHON%" goto check
python -c "import sys; assert sys.version_info >= (3, 11) and sys.prefix == sys.base_prefix, 'Use a system Python 3.11+ to create the project environment'"
if errorlevel 1 goto failed
python -m venv "%~dp0.venv"
if errorlevel 1 goto failed
:check
"%MAKER_PYTHON%" -I "%~dp0scripts\check_python.py" >nul 2>&1
if errorlevel 1 goto install
"%MAKER_PYTHON%" -I -m pip --disable-pip-version-check check >nul 2>&1
if not errorlevel 1 (
    echo Already installed. Reusing the project environment.
    goto ready
)
:install
"%MAKER_PYTHON%" -I -m pip install --disable-pip-version-check -e "%~dp0sdk\python[drawing]"
if errorlevel 1 goto failed
"%MAKER_PYTHON%" -I -m pip --disable-pip-version-check check
if errorlevel 1 goto failed
:ready
"%MAKER_PYTHON%" -I "%~dp0scripts\check_python.py"
if errorlevel 1 goto failed
echo Ready. IDE interpreter: "%MAKER_PYTHON%"
if /i not "%~1"=="--no-pause" pause
exit /b 0
:failed
echo Setup failed. Use a system Python 3.11+ with pip and Tcl/Tk, then retry.
if /i not "%~1"=="--no-pause" pause
exit /b 1
