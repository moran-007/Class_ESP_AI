@echo off
setlocal
call "%~dp0..\..\scripts\run_python.cmd" "%~dp0wifi_screen.py" %*
set "MAKER_EXIT=%errorlevel%"
pause
exit /b %MAKER_EXIT%
