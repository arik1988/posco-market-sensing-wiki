@echo off
cd /d "%~dp0"
set "WIKI_ROOT=%CD%"
set "PROJECT_TOOLS=%CD%\tools\project"

call "%PROJECT_TOOLS%\resolve_python.bat"
if errorlevel 1 (
  echo [ERROR] A working Python 3 interpreter was not found.
  echo Install Python 3.10 or newer and run installer.bat again.
  pause
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm was not found.
  echo Install the Node.js LTS release and run installer.bat again.
  pause
  exit /b 1
)

echo Installing packages required by the MkDocs wiki...
"%WIKI_PYTHON%" -m pip install -r "%PROJECT_TOOLS%\requirements-docs.txt"
if errorlevel 1 (
  echo.
  echo [ERROR] Package installation failed.
  pause
  exit /b 1
)

echo.
echo Installing the project-local CodeGraph...
call npm install --prefix "%PROJECT_TOOLS%" --no-audit --no-fund
if errorlevel 1 (
  echo.
  echo [ERROR] CodeGraph installation failed.
  pause
  exit /b 1
)

if exist ".git\" (
  git config --local core.excludesFile "%PROJECT_TOOLS%\.gitignore" >nul 2>&1
)

copy /Y "%PROJECT_TOOLS%\codegraph.json" "%WIKI_ROOT%\codegraph.json" >nul
attrib +h "%WIKI_ROOT%\codegraph.json" >nul 2>&1

pushd "%PROJECT_TOOLS%"
call "%PROJECT_TOOLS%\node_modules\.bin\codegraph.cmd" telemetry off >nul 2>&1

echo.
if exist "%WIKI_ROOT%\.codegraph\" (
  echo Updating the CodeGraph index...
  call "%PROJECT_TOOLS%\node_modules\.bin\codegraph.cmd" sync "%WIKI_ROOT%"
) else (
  echo Initializing and indexing CodeGraph...
  call "%PROJECT_TOOLS%\node_modules\.bin\codegraph.cmd" init --index "%WIKI_ROOT%"
)
set "CODEGRAPH_EXIT=%ERRORLEVEL%"
popd
if not "%CODEGRAPH_EXIT%"=="0" (
  echo.
  echo [ERROR] CodeGraph indexing failed.
  pause
  exit /b 1
)

echo.
echo Installation complete.
echo Run wiki_run.bat to start the wiki.
pause
