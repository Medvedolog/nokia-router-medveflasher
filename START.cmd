@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "NOKIA_LANG="
set "PYEXE="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3"
if defined PYEXE goto run
python -c "import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)" >nul 2>&1
if not errorlevel 1 set "PYEXE=python"
if defined PYEXE goto run
echo ERROR / OSHIBKA: Python 3 was not found / Python 3 ne nayden.
echo Install Python 3 and enable Add Python to PATH.
choice /C YN /N /M "Open python.org now? [Y/N]: "
if errorlevel 2 goto no_python_exit
start "" "https://www.python.org/downloads/windows/"
:no_python_exit
pause
endlocal
exit /b 1
:run
%PYEXE% "data\master.py" wizard
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" goto success
echo.
echo ERROR / OSHIBKA: master exited with code %RC%.
echo Review the localized message above. Do not remove power during NAND writes.
pause
endlocal & exit /b %RC%
:success
echo.
echo SUCCESS / USPESHNO.
echo Press any key to close this window.
pause >nul
endlocal & exit /b 0
