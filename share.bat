@echo off
rem ======================================================================
rem  Share the app on the internet through a free Cloudflare quick tunnel.
rem  Your PC runs the app; Cloudflare gives it a temporary public https link.
rem  The link works only while this window is open, and changes every time.
rem ======================================================================
setlocal
cd /d "%~dp0"
if "%PORT%"=="" set "PORT=8000"

if not exist "backend\.venv\Scripts\python.exe" (
  echo [X] Run run.bat once first: it installs the app.
  pause
  exit /b 1
)

rem Anyone with the link could use your Gemini credit, so a password is required.
rem Each check sets a flag only on success, so any failure stops the script.
set "HAS_PASSWORD="
findstr /r /c:"^ACCESS_PASSWORD=..*" "backend\.env" >nul 2>nul && set "HAS_PASSWORD=1"
if not defined HAS_PASSWORD (
  echo [X] Set an access password before sharing.
  echo     Open backend\.env in Notepad and add a line like:
  echo         ACCESS_PASSWORD=choose-a-password
  echo     Visitors must type it before they can use the app. Then run this file again.
  pause
  exit /b 1
)

set "HAS_TUNNEL="
where cloudflared >nul 2>nul && set "HAS_TUNNEL=1"
if not defined HAS_TUNNEL (
  echo [X] cloudflared is not installed. Install it once with:
  echo         winget install --id Cloudflare.cloudflared
  echo     then close this window, open a new one, and run this file again.
  pause
  exit /b 1
)

echo Opening the tunnel in a second window. Your public link is the
echo https://....trycloudflare.com address printed there. Send it with the password.
start "Public link - close to stop sharing" cloudflared tunnel --url http://127.0.0.1:%PORT%
call "%~dp0run.bat"
