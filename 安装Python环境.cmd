@echo off
setlocal
cd /d "%~dp0"
python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'"
if errorlevel 1 goto failed
if not exist "%~dp0.venv\Scripts\python.exe" python -m venv "%~dp0.venv"
if errorlevel 1 goto failed
"%~dp0.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -e "%~dp0sdk\python[drawing]"
if errorlevel 1 goto failed
echo Ready. IDE interpreter: %~dp0.venv\Scripts\python.exe
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.11+ with pip and retry.
pause
exit /b 1
