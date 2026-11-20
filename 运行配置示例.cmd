@echo off
setlocal
call "%~dp0scripts\run_python.cmd" "%~dp0scripts\guide_menu.py"
set "MAKER_RESULT=%errorlevel%"
echo Exit code: %MAKER_RESULT%
pause
exit /b %MAKER_RESULT%
