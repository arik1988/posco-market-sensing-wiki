@echo off
rem Resolve a real Python interpreter, skipping Windows Store app aliases.
set "WIKI_PYTHON="

for %%P in (
  "%LocalAppData%\Programs\Python\Python314\python.exe"
  "%LocalAppData%\Programs\Python\Python313\python.exe"
  "%UserProfile%\.openharness-venv\Scripts\python.exe"
) do (
  if not defined WIKI_PYTHON if exist "%%~P" (
    "%%~P" -c "import sys" >nul 2>&1
    if not errorlevel 1 set "WIKI_PYTHON=%%~P"
  )
)

for /d %%D in ("%LocalAppData%\Programs\Python\Python*") do (
  if not defined WIKI_PYTHON if exist "%%~fD\python.exe" (
    "%%~fD\python.exe" -c "import sys" >nul 2>&1
    if not errorlevel 1 set "WIKI_PYTHON=%%~fD\python.exe"
  )
)

for /d %%D in ("%ProgramFiles%\Python*") do (
  if not defined WIKI_PYTHON if exist "%%~fD\python.exe" (
    "%%~fD\python.exe" -c "import sys" >nul 2>&1
    if not errorlevel 1 set "WIKI_PYTHON=%%~fD\python.exe"
  )
)

if not defined WIKI_PYTHON (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined WIKI_PYTHON (
      "%%P" -c "import sys" >nul 2>&1
      if not errorlevel 1 set "WIKI_PYTHON=%%P"
    )
  )
)

if not defined WIKI_PYTHON exit /b 1
exit /b 0
