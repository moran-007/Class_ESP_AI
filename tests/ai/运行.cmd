@echo off
setlocal
call "%~dp0..\..\scripts\run_python.cmd" "%~dp0ai_test.py"
set "MAKER_RESULT=%errorlevel%"
pause
exit /b %MAKER_RESULT%
