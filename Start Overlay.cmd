@echo off
REM Archipelago message overlay for Empire Earth.
REM Add --solid while positioning it; drop it for the transparent version.
setlocal
set ANCHOR=topleft
set OPTS=--anchor %ANCHOR% --width 520 --font-size 14

cd /d "%~dp0"
echo Empire Earth Archipelago overlay  (%ANCHOR%)
echo Leave this window open while you play. Close it to stop the overlay.
echo.
py "world\empire_earth\Overlay.py" %OPTS%
pause
