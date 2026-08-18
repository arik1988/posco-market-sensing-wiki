@echo off
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was not found.
  echo Run installer.bat first.
  pause
  exit /b 1
)

python -m mkdocs --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] MkDocs is not installed.
  echo Run installer.bat first.
  pause
  exit /b 1
)

set NO_MKDOCS_2_WARNING=true
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\project\wiki_run.ps1"
pause
