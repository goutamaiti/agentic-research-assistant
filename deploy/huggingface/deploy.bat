@echo off
rem Publish this project to a Hugging Face Space (run run.bat once first to set up Python).
setlocal
cd /d "%~dp0..\.."
if not exist "backend\.venv\Scripts\python.exe" (
  echo Run run.bat once first: it sets up the Python environment this script uses.
  pause
  exit /b 1
)
set "SPACE=%~1"
if "%SPACE%"=="" set /p "SPACE=Space ID (yourname/agentic-research-assistant): "
if "%SPACE%"=="" exit /b 1
"backend\.venv\Scripts\python.exe" deploy\huggingface\push_space.py --space "%SPACE%" --secrets
pause
