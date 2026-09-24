@echo off
REM ======================================================================
REM  Background remover - Windows launcher
REM
REM   * Double-click          : processes all images in this folder
REM   * Drag and drop         : drop images and/or folders onto this file
REM   * Command line          : remove_background.bat [folders/files] [options]
REM
REM  Results go into an "output" subfolder next to the images.
REM
REM  On first run this sets up a private Python environment in
REM  %LOCALAPPDATA%\BackgroundRemover (nothing is installed system-wide,
REM  except Python itself if it is missing and you agree to install it).
REM
REM  Environment variables (optional):
REM    BGR_NO_PAUSE=1   don't wait for a key press at the end (automation)
REM    BGR_REINSTALL=1  force a fresh setup of the Python environment
REM ======================================================================
setlocal EnableExtensions DisableDelayedExpansion

REM Folder of this .bat file (always ends with a backslash)
set "APPDIR=%~dp0"
set "SCRIPT=%APPDIR%remove_background.py"
set "REQS=%APPDIR%requirements.txt"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PYTHONNOUSERSITE=1"

if not exist "%SCRIPT%" (
    echo ERROR: remove_background.py was not found next to this .bat file.
    echo Keep remove_background.bat, remove_background.py and requirements.txt together
    echo in the same folder. If you opened this from inside a ZIP file, extract the ZIP first.
    goto :fail
)
if not exist "%REQS%" (
    echo ERROR: requirements.txt was not found next to this .bat file.
    goto :fail
)

REM Where the private environment lives (outside the app folder, so it also
REM works from read-only / synced folders like OneDrive or a USB stick)
set "DATADIR=%LOCALAPPDATA%\BackgroundRemover"
if "%LOCALAPPDATA%"=="" set "DATADIR=%APPDIR%.bgr-data"
set "VENV=%DATADIR%\venv"
set "VPY=%VENV%\Scripts\python.exe"
set "STAMP=%VENV%\installed-requirements.txt"
set "LOG=%DATADIR%\setup.log"

if not exist "%DATADIR%\" mkdir "%DATADIR%" 2>nul
if not exist "%DATADIR%\" (
    echo ERROR: could not create folder "%DATADIR%".
    goto :fail
)

if defined BGR_REINSTALL goto :setup

REM ---- Is the environment already set up and healthy? -----------------
if not exist "%VPY%" goto :setup
if not exist "%STAMP%" goto :setup
fc /b "%REQS%" "%STAMP%" >nul 2>&1 || goto :setup
"%VPY%" -c "import cv2, numpy" >nul 2>&1 || goto :setup
goto :run


REM ======================================================================
:setup
echo.
echo === First-time setup (only needed once, takes a minute or two) ===
echo.
call :find_python
if not defined PY call :install_python
if not defined PY goto :fail

echo Using Python:
%PY% -c "import sys; print('  ' + sys.executable + '  (' + sys.version.split()[0] + ')')"

if exist "%VENV%\" (
    echo Removing old environment...
    rmdir /s /q "%VENV%" 2>nul
)
if exist "%VENV%\" (
    echo ERROR: could not delete the old environment in
    echo   "%VENV%"
    echo Close other windows that may be using it ^(or restart the PC^) and try again.
    goto :fail
)

echo Creating environment...
%PY% -m venv "%VENV%" > "%LOG%" 2>&1
if errorlevel 1 (
    type "%LOG%"
    echo.
    echo ERROR: could not create the Python environment ^(details above^).
    goto :fail
)
if not exist "%VPY%" (
    echo ERROR: Python environment was created but python.exe is missing.
    goto :fail
)

echo Installing required libraries ^(numpy, OpenCV^)...
"%VPY%" -m pip install --upgrade pip >> "%LOG%" 2>&1
call :pip_install
if errorlevel 1 (
    echo   ...first attempt failed, retrying...
    timeout /t 3 /nobreak >nul 2>&1
    call :pip_install
)
if errorlevel 1 (
    echo.
    echo ---- last lines of the setup log ----
    powershell -NoProfile -Command "Get-Content -LiteralPath $env:LOG -Tail 25" 2>nul
    echo -------------------------------------
    echo.
    echo ERROR: installing the libraries failed.
    echo  - Check your internet connection ^(and proxy / firewall^).
    echo  - Full log: "%LOG%"
    goto :fail
)

"%VPY%" -c "import cv2, numpy" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo ERROR: libraries were installed but cannot be loaded. See "%LOG%".
    echo If it mentions a missing DLL, install the Microsoft Visual C++ Redistributable:
    echo   https://aka.ms/vs/17/release/vc_redist.x64.exe
    goto :fail
)
copy /y "%REQS%" "%STAMP%" >nul
echo Setup complete.
echo.


REM ======================================================================
:run
"%VPY%" "%SCRIPT%" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo Finished with errors ^(exit code %RC%^).
)
call :maybe_pause
exit /b %RC%


:fail
echo.
echo Nothing was processed.
call :maybe_pause
exit /b 1


REM ======================================================================
REM  Subroutines
REM ======================================================================

:maybe_pause
if not defined BGR_NO_PAUSE (
    echo.
    pause
)
exit /b 0


:pip_install
"%VPY%" -m pip install --no-input --only-binary=:all: --prefer-binary -r "%REQS%" >> "%LOG%" 2>&1
exit /b %ERRORLEVEL%


:find_python
REM Sets PY to a working 64-bit Python 3.9+ command, or leaves it undefined.
set "PY="
call :try_python py -3-64
if defined PY exit /b 0
call :try_python py -3
if defined PY exit /b 0
call :try_python python
if defined PY exit /b 0
call :try_python python3
if defined PY exit /b 0
REM Not on PATH? Look in the usual install locations (newest first).
for /f "delims=" %%D in ('dir /b /ad /o-n "%LOCALAPPDATA%\Programs\Python\Python3*" 2^>nul') do (
    if not defined PY call :try_python "%LOCALAPPDATA%\Programs\Python\%%D\python.exe"
)
if defined PY exit /b 0
for /f "delims=" %%D in ('dir /b /ad /o-n "%ProgramFiles%\Python3*" 2^>nul') do (
    if not defined PY call :try_python "%ProgramFiles%\%%D\python.exe"
)
if defined PY exit /b 0
for /f "delims=" %%D in ('dir /b /ad /o-n "%SystemDrive%\Python3*" 2^>nul') do (
    if not defined PY call :try_python "%SystemDrive%\%%D\python.exe"
)
exit /b 0


:try_python
REM Rejects the Microsoft Store "python" placeholder, Python 2, too old
REM versions and 32-bit Python (no OpenCV/numpy builds for those).
%* -c "import sys, struct; sys.exit(0 if sys.version_info >= (3, 9) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 set "PY=%*"
exit /b 0


:install_python
echo No suitable Python ^(64-bit, version 3.9 or newer^) was found.
where winget >nul 2>&1
if errorlevel 1 goto :manual_python
echo.
choice /c YN /m "Install Python 3.12 now (for your user only, via winget)"
if errorlevel 2 goto :manual_python
winget install --exact --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
REM The new Python is not on PATH in this window yet -> look for it directly
call :find_python
if defined PY exit /b 0
call :try_python "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined PY exit /b 0
echo.
echo Python was installed but could not be found yet.
echo Please close this window and run remove_background.bat again.
exit /b 1

:manual_python
echo.
echo Please install Python from https://www.python.org/downloads/
echo  - choose the "Windows installer (64-bit)"
echo  - tick "Add python.exe to PATH" on the first installer screen
echo Then run remove_background.bat again.
start "" "https://www.python.org/downloads/windows/" >nul 2>&1
exit /b 1
