@echo off
rem ===========================================================================
rem  build.bat - fetches the toolchain and builds the Windows release of Tanks
rem
rem    build.bat            install missing dependencies, build, test, package
rem    build.bat clean      same, from a fresh build directory
rem    build.bat update     also run a full MSYS2 system update first
rem
rem  Dependencies come from MSYS2 (MinGW64): gcc, cmake, ninja, SDL3, zlib and
rem  python. MSYS2 is installed with winget when it is missing. Set MSYS2_ROOT
rem  to use an MSYS2 installed somewhere other than C:\msys64.
rem
rem  Output: dist\Tanks\ (tanks.exe + tanks.swf + docs) and dist\Tanks-windows-x64.zip
rem ===========================================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "BUILD_DIR=build-release"
set "DIST_DIR=dist\Tanks"
set "ZIP=dist\Tanks-windows-x64.zip"
set "PKGS=mingw-w64-x86_64-gcc mingw-w64-x86_64-cmake mingw-w64-x86_64-ninja mingw-w64-x86_64-sdl3 mingw-w64-x86_64-zlib mingw-w64-x86_64-python"
if not defined MSYS2_ROOT set "MSYS2_ROOT=C:\msys64"

set "DO_CLEAN=0"
set "DO_UPDATE=0"
:args
if "%~1"=="" goto args_done
if /i "%~1"=="clean" set "DO_CLEAN=1"
if /i "%~1"=="update" set "DO_UPDATE=1"
shift
goto args
:args_done

if not exist "tanks.swf" (
    echo [error] tanks.swf is missing: put it next to build.bat.
    goto fail
)

rem ---------------------------------------------------------------- MSYS2
if exist "%MSYS2_ROOT%\usr\bin\bash.exe" goto have_msys
echo [deps] MSYS2 not found at %MSYS2_ROOT%
where winget >nul 2>nul
if errorlevel 1 goto no_winget
echo [deps] installing MSYS2 with winget...
winget install -e --id MSYS2.MSYS2 --accept-source-agreements --accept-package-agreements
if exist "%MSYS2_ROOT%\usr\bin\bash.exe" goto msys_first_run
echo [error] winget finished but %MSYS2_ROOT%\usr\bin\bash.exe is still missing.
echo         If MSYS2 went elsewhere, run:  set MSYS2_ROOT=X:\path\to\msys64
goto fail
:no_winget
echo [error] winget is not available. Install MSYS2 from https://www.msys2.org/
echo         (default folder C:\msys64), then run build.bat again.
goto fail

:msys_first_run
rem a fresh MSYS2 needs its first-run setup and a full update before installing packages
set "DO_UPDATE=1"

:have_msys
set "MSYS_BASH=%MSYS2_ROOT%\usr\bin\bash.exe"
set "CHERE_INVOKING=1"
set "MSYSTEM=MINGW64"

if "%DO_UPDATE%"=="0" goto check_pkgs
echo [deps] updating MSYS2 (run twice: the first pass may only update the core)...
"%MSYS_BASH%" -lc "pacman -Syuu --noconfirm"
"%MSYS_BASH%" -lc "pacman -Syuu --noconfirm"

:check_pkgs
"%MSYS_BASH%" -lc "pacman -Q %PKGS% >/dev/null 2>&1"
if not errorlevel 1 goto deps_ok
echo [deps] installing build dependencies...
"%MSYS_BASH%" -lc "pacman -S --needed --noconfirm %PKGS%"
if errorlevel 1 (
    echo [deps] install failed; refreshing the package database and retrying...
    "%MSYS_BASH%" -lc "pacman -Sy --needed --noconfirm %PKGS%"
    if errorlevel 1 goto fail
)
:deps_ok
echo [deps] gcc, cmake, ninja, SDL3, zlib and python are installed.

rem ---------------------------------------------------------------- build
rem only MinGW64 tools on PATH, so another compiler or Python is never picked up
set "PATH=%MSYS2_ROOT%\mingw64\bin;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\WindowsPowerShell\v1.0"

if "%DO_CLEAN%"=="1" if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"

echo [build] configuring...
cmake -G Ninja -S . -B "%BUILD_DIR%" -DCMAKE_BUILD_TYPE=Release -DTANKS_STATIC=ON ^
    -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ ^
    -DPython3_EXECUTABLE="%MSYS2_ROOT%\mingw64\bin\python.exe"
if errorlevel 1 goto fail

echo [build] compiling...
cmake --build "%BUILD_DIR%"
if errorlevel 1 goto fail

rem ---------------------------------------------------------------- smoke test
echo [test] running 300 headless frames...
"%BUILD_DIR%\tanks.exe" --test 300 "%BUILD_DIR%\tanks.swf"
if errorlevel 1 (
    echo [error] the headless test run failed.
    goto fail
)

rem ---------------------------------------------------------------- package
echo [dist] packaging...
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
mkdir "%DIST_DIR%"
copy /y "%BUILD_DIR%\tanks.exe" "%DIST_DIR%\" >nul || goto fail
copy /y "tanks.swf" "%DIST_DIR%\" >nul || goto fail
copy /y "README.md" "%DIST_DIR%\" >nul
copy /y "THIRD-PARTY-LICENSES.txt" "%DIST_DIR%\" >nul
copy /y "LICENSE-IsaacRecomp.txt" "%DIST_DIR%\" >nul
if exist "%ZIP%" del /q "%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path '%DIST_DIR%\*' -DestinationPath '%ZIP%' -Force"
if errorlevel 1 echo [dist] warning: could not create %ZIP% (the folder is still ready)

echo.
echo [done] %DIST_DIR%\tanks.exe
if exist "%ZIP%" echo [done] %ZIP%
endlocal
exit /b 0

:fail
echo.
echo [failed] see the messages above.
endlocal
exit /b 1
