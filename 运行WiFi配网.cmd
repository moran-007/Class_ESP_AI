@echo off
setlocal
call "%~dp0scripts\run_python.cmd" "%~dp0examples\portable\17_wifi.py" %*
set "MAKER_EXIT=%errorlevel%"
pause
exit /b %MAKER_EXIT%
