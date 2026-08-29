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
  echo MkDocs packages are not installed. Installing dependencies...
  "%WIKI_PYTHON%" -m pip install -r "%PROJECT_TOOLS%\requirements-docs.txt"
  if errorlevel 1 (
    echo [ERROR] Package installation failed.
    pause
    exit /b 1
  )
)

if not exist "%~dp0.venv-agent\Scripts\python.exe" (
  echo Creating the project-local AI research environment...
  "%WIKI_PYTHON%" -m venv "%~dp0.venv-agent"
  if errorlevel 1 (
    echo [ERROR] AI research virtual environment creation failed.
    pause
    exit /b 1
  )
)

"%~dp0.venv-agent\Scripts\python.exe" -c "import deepagents, httpx, langchain_openai, openai_codex" >nul 2>&1
if errorlevel 1 (
  echo Installing standalone AI research packages...
  "%~dp0.venv-agent\Scripts\python.exe" -m pip install -r "%PROJECT_TOOLS%\requirements-agent.txt"
  if errorlevel 1 (
    echo [ERROR] AI research package installation failed.
    pause
    exit /b 1
  )
)

set NO_MKDOCS_2_WARNING=true
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_TOOLS%\wiki_run.ps1"
pause
