@echo off
setlocal
set "PYTHONUTF8=1"
set "MAKER_PYTHON=python"
if exist "%~dp0..\.venv\Scripts\python.exe" set "MAKER_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if "%~1"=="menu" (
  "%MAKER_PYTHON%" "%~dp0quick_menu.py"
) else (
  "%MAKER_PYTHON%" "%~dp0..\tests\quick\%~1"
)
set "MAKER_RESULT=%errorlevel%"
echo.
echo Exit code: %MAKER_RESULT%
pause
exit /b %MAKER_RESULT%
