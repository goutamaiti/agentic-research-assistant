@echo off
rem ======================================================================
rem  Agentic Research Assistant - one-click launcher for Windows
rem  First run: creates the Python environment, installs dependencies,
rem  builds the web interface and asks for an API key (about 5-10 minutes).
rem  Later runs: starts the app at once. Close this window to stop it.
rem ======================================================================
setlocal EnableExtensions EnableDelayedExpansion
title Agentic Research Assistant
cd /d "%~dp0"
if "%PORT%"=="" set "PORT=8000"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

echo.
echo === Agentic Research Assistant ===
echo.

rem ---- 1. Python 3.12 or newer ---------------------------------------
set "PY="
for %%C in ("py -3" "python") do (
  if not defined PY (
    %%~C -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul && set "PY=%%~C"
  )
)
if not defined PY (
  echo [X] Python 3.12 or newer was not found.
  echo     Install it from https://www.python.org/downloads/
  echo     and tick "Add python.exe to PATH" during setup. Then run this file again.
  pause
  exit /b 1
)

rem ---- Windows path-length check -------------------------------------
rem Some PyTorch files sit ~150 characters deep inside the project, and Windows limits
rem paths to 260 characters unless long paths are enabled.
set "LONGPATHS="
for /f "skip=2 tokens=3" %%v in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled 2^>nul') do set "LONGPATHS=%%v"
if not "%LONGPATHS%"=="0x1" if not exist "backend\.venv\installed-requirements.txt" (
  for /f %%n in ('powershell -NoProfile -Command "('%~dp0').Length"') do set "PATHLEN=%%n"
  if !PATHLEN! GTR 100 (
    echo [X] This folder's path is too long for Windows ^(!PATHLEN! characters, limit about 100^):
    echo     %~dp0
    echo     Move the folder somewhere shorter, for example C:\Projects\, and run this file again.
    echo     ^(Or enable Windows long paths: https://pip.pypa.io/warnings/enable-long-paths^)
    pause
    exit /b 1
  )
)

rem ---- 2. Python environment and packages ----------------------------
if not exist "backend\.venv\Scripts\python.exe" (
  echo [1/4] Creating the Python environment...
  %PY% -m venv backend\.venv || goto :failed
)
fc /b "backend\requirements.txt" "backend\.venv\installed-requirements.txt" >nul 2>nul
if errorlevel 1 (
  echo [2/4] Installing Python packages ^(first run takes several minutes^)...
  "backend\.venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  "backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt || goto :failed
  copy /y "backend\requirements.txt" "backend\.venv\installed-requirements.txt" >nul
) else (
  echo [2/4] Python packages are up to date.
)

rem ---- 3. Web interface (needs Node.js only to build it) -------------
where npm >nul 2>nul
if errorlevel 1 (
  if exist "frontend\dist\index.html" (
    echo [3/4] Node.js not found; using the existing web interface build.
  ) else (
    echo [X] Node.js is needed once to build the web interface.
    echo     Install the LTS version from https://nodejs.org/ and run this file again.
    pause
    exit /b 1
  )
) else (
  echo [3/4] Building the web interface...
  pushd frontend
  if not exist "node_modules" (
    call npm ci --no-audit --no-fund || (popd & goto :failed)
  )
  call npm run build >nul || (popd & goto :failed)
  popd
)

rem ---- 4. Settings and API key ---------------------------------------
if not exist "backend\.env" (
  copy "backend\.env.example" "backend\.env" >nul
  echo.
  echo [4/4] Paste your Google Gemini API key ^(or an OpenRouter key starting with sk-or-^)
  echo       and press Enter. Leave it empty to skip: papers are then indexed but not analysed.
  echo       The key is stored only in backend\.env on this computer.
  set "APIKEY="
  set /p "APIKEY=API key: "
  if defined APIKEY (
    powershell -NoProfile -Command "$p = Resolve-Path 'backend\.env'; $lines = (Get-Content $p) -replace '^GEMINI_API_KEY=.*', ('GEMINI_API_KEY=' + $env:APIKEY); [IO.File]::WriteAllLines($p, $lines)" || goto :failed
  )
  set "APIKEY="
) else (
  echo [4/4] Using settings from backend\.env
)

rem ---- Start ----------------------------------------------------------
echo.
echo Starting... the browser opens at http://127.0.0.1:%PORT%
echo The first analysis downloads the embedding model ^(about 420 MB^).
echo Close this window to stop the app.
echo.
start "" cmd /c "timeout /t 8 >nul & start http://127.0.0.1:%PORT%"
cd backend
".venv\Scripts\python.exe" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port %PORT%
exit /b %errorlevel%

:failed
echo.
echo [X] Setup failed. Read the messages above, fix the problem, and run this file again.
pause
exit /b 1
