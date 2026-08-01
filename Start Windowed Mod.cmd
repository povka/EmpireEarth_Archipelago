@echo off
REM Pin Empire Earth to a monitor and stop it minimising when you tab out.
REM Edit MONITOR below: run with --list once to see the numbering.
setlocal
set MONITOR=1
set FILL=--fill

cd /d "%~dp0"
echo Empire Earth window manager
echo   monitor : %MONITOR%
echo   fill    : %FILL%
echo.
echo Leave this window open while you play. Ctrl+C to stop.
echo.
py "world\empire_earth\WindowManager.py" --monitor %MONITOR% %FILL%
pause
