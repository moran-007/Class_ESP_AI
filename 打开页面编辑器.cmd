@echo off
setlocal
call "%~dp0scripts\run_python.cmd" "%~dp0scripts\start_page_editor.py"
set "MAKER_EXIT=%errorlevel%"
if not "%MAKER_EXIT%"=="0" pause
exit /b %MAKER_EXIT%
