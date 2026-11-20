@echo off
setlocal
if "%~1"=="menu" (
  call "%~dp0run_python.cmd" "%~dp0quick_menu.py"
) else (
  call "%~dp0run_python.cmd" "%~dp0..\tests\quick\%~1"
)
set "MAKER_RESULT=%errorlevel%"
echo.
echo Exit code: %MAKER_RESULT%
pause
exit /b %MAKER_RESULT%
