@echo off
cd /d "%~dp0"

set "PROJECT_TOOLS=%~dp0tools\project"
call "%PROJECT_TOOLS%\resolve_python.bat"
if errorlevel 1 (
  echo [ERROR] A working Python 3 interpreter was not found.
  echo Install Python 3.10 or newer and run installer.bat again.
  pause
  exit /b 1
)

"%WIKI_PYTHON%" -c "import mkdocs, mkdocs_enumerate_headings_plugin" >nul 2>&1
if errorlevel 1 (
  echo MkDocs is not installed. Installing the documentation dependencies...
  "%WIKI_PYTHON%" -m pip install -r "%PROJECT_TOOLS%\requirements-docs.txt"
  if errorlevel 1 (
    echo [ERROR] Package installation failed.
    pause
    exit /b 1
  )
)

set NO_MKDOCS_2_WARNING=true
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_TOOLS%\wiki_run.ps1"
pause
